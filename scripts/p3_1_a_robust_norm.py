"""P3.1-A: Robust normalization ablation (single-variable experiment).

Frozen: same checkpoint, same CoordNet, same 10 frames, same seeds,
        same RANSAC/ICP params, same metrics.
Changed: normalization scale = percentile(radii, 95) instead of max(radii).

Records both baseline (max) and robust (p95) scale per frame for comparison.
"""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path

import cv2
import numpy as np
import open3d as o3d
import torch

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from r3p.geometry.camera import deproject
from r3p.geometry.se3 import make_T, invert, apply as apply_T
from r3p.learn.coord_net import CoordNet, normalize_points
from r3p.learn.umeyama import ransac_umeyama
from r3p.pose.geo_init import object_point_cloud, load_model_cloud, icp_refine
from r3p.evaluation.metrics import compute_all

MM_TO_M = 1e-3


def normalize_points_robust(xyz: np.ndarray, percentile: float = 95.0
                            ) -> tuple[np.ndarray, np.ndarray, float]:
    """Center at centroid + scale to percentile of radii.

    Same center computation as normalize_points (centroid).
    Only the scale differs: percentile(radii, p) instead of max(radii).
    """
    center = xyz.mean(axis=0)
    radii = np.linalg.norm(xyz - center, axis=1)
    scale = float(np.percentile(radii, percentile))
    if scale < 1e-9:
        scale = 1.0
    return (xyz - center) / scale, center, scale


def load_frame(data_root: Path, scene: int, im_id: int, obj_id: int) -> dict:
    sdir = data_root / "test" / f"{scene:06d}"
    cam = json.loads((sdir / "scene_camera.json").read_text("utf-8"))
    gt = json.loads((sdir / "scene_gt.json").read_text("utf-8"))
    gt_info = json.loads((sdir / "scene_gt_info.json").read_text("utf-8"))
    im_key = str(im_id)
    cam_entry = cam[im_key]
    K = np.array(cam_entry["cam_K"], dtype=np.float64).reshape(3, 3)
    depth_scale = float(cam_entry["depth_scale"])
    rgb = cv2.imread(str(sdir / "rgb" / f"{im_id:06d}.png"), cv2.IMREAD_COLOR)
    rgb = cv2.cvtColor(rgb, cv2.COLOR_BGR2RGB)
    depth_raw = cv2.imread(str(sdir / "depth" / f"{im_id:06d}.png"), cv2.IMREAD_UNCHANGED)
    depth = (depth_raw.astype(np.float32) * np.float32(depth_scale * 1e-3)).astype(np.float32)
    instances = gt[im_key]
    gt_pose = None
    mask = None
    visib_fract = None
    for gid, inst in enumerate(instances):
        if int(inst["obj_id"]) == obj_id:
            R = np.array(inst["cam_R_m2c"], dtype=np.float64).reshape(3, 3)
            t = np.array(inst["cam_t_m2c"], dtype=np.float64).reshape(3) * MM_TO_M
            gt_pose = make_T(R, t)
            m = cv2.imread(str(sdir / "mask_visib" / f"{im_id:06d}_{gid:06d}.png"), cv2.IMREAD_UNCHANGED)
            mask = m > 0
            visib_fract = float(gt_info[im_key][gid]["visib_fract"])
            break
    assert gt_pose is not None
    assert mask is not None
    mesh = o3d.io.read_triangle_mesh(str(data_root / "models" / f"obj_{obj_id:06d}.ply"))
    model_points_m = np.asarray(mesh.vertices, dtype=np.float64) * MM_TO_M
    return {"rgb": rgb, "depth": depth, "K": K, "mask": mask,
            "gt_pose": gt_pose, "model_points_m": model_points_m,
            "visib_fract": visib_fract}


def run_frame(frame: dict, obj_id: int, net: CoordNet, model_pcd,
              cfg: dict, frame_seed: int) -> dict:
    """Full pipeline with robust normalization. Returns result dict."""
    res = {"frame_seed": frame_seed}
    K = frame["K"]
    depth = frame["depth"]
    mask = frame["mask"]
    rgb = frame["rgb"]
    gt_pose = frame["gt_pose"]

    cam_xyz = deproject(K, depth, mask=mask)
    cam_rgb = rgb[mask]
    res["n_mask_pixels"] = int(mask.sum())
    res["n_deprojected_pts"] = int(len(cam_xyz))

    scene_pcd = object_point_cloud(depth, mask, K, voxel_m=cfg["icp"]["voxel_m"])
    res["n_voxel_pts"] = int(len(np.asarray(scene_pcd.points)))

    n_pts = cfg["model"]["n_points"]
    if len(cam_xyz) < n_pts:
        res["error"] = f"insufficient points: {len(cam_xyz)} < {n_pts}"
        return res

    rng = np.random.default_rng(frame_seed)
    idx = rng.choice(len(cam_xyz), size=n_pts, replace=False)
    cam_sampled = cam_xyz[idx]
    rgb_sampled = cam_rgb[idx]

    # --- Baseline normalization (for comparison, NOT used for pipeline) ---
    _, base_center, base_scale = normalize_points(cam_sampled)
    res["baseline_scale"] = round(base_scale, 6)

    # --- Robust normalization (USED for pipeline) ---
    cam_norm, robust_center, robust_scale = normalize_points_robust(cam_sampled, percentile=95.0)
    res["robust_scale"] = round(robust_scale, 6)
    res["scale_ratio"] = round(base_scale / robust_scale, 4) if robust_scale > 1e-9 else float("inf")

    features = np.concatenate([cam_norm, rgb_sampled / 255.0], axis=1).astype(np.float32)

    # --- Normalized XYZ stats ---
    res["norm_xyz_std"] = [round(float(cam_norm[:, a].std()), 6) for a in range(3)]

    # --- CoordNet forward ---
    net.eval()
    with torch.no_grad():
        pred_canonical = net(torch.from_numpy(features)).numpy()

    # --- GT canonical for comparison ---
    gt_canonical = apply_T(invert(gt_pose), cam_sampled)
    canonical_err = np.linalg.norm(pred_canonical - gt_canonical, axis=1)
    res["canonical_err_mm"] = {
        "mean": round(float(canonical_err.mean()) * 1e3, 3),
        "median": round(float(np.median(canonical_err)) * 1e3, 3),
        "p90": round(float(np.percentile(canonical_err, 90)) * 1e3, 3),
        "max": round(float(canonical_err.max()) * 1e3, 3),
    }

    # --- Per-axis correlation ---
    axis_corr = {}
    for ax in range(3):
        c = np.corrcoef(pred_canonical[:, ax], gt_canonical[:, ax])[0, 1]
        axis_corr[f"axis{ax}_corr"] = round(float(c), 4)
    res["axis_correlation"] = axis_corr

    # --- CoordNet prediction stats ---
    res["pred_canonical_std"] = [round(float(pred_canonical[:, a].std()), 6) for a in range(3)]
    res["pred_canonical_range"] = {
        "x": [round(float(pred_canonical[:, 0].min()), 6), round(float(pred_canonical[:, 0].max()), 6)],
        "y": [round(float(pred_canonical[:, 1].min()), 6), round(float(pred_canonical[:, 1].max()), 6)],
        "z": [round(float(pred_canonical[:, 2].min()), 6), round(float(pred_canonical[:, 2].max()), 6)],
    }

    # --- RANSAC ---
    ransac_cfg = cfg["ransac_umeyama"]
    rr = ransac_umeyama(
        src=pred_canonical, dst=cam_sampled,
        threshold_m=ransac_cfg["threshold_m"],
        iters=ransac_cfg["iters"],
        seed=ransac_cfg["seed"])

    T_cam_model_ransac = make_T(rr.R, rr.t)
    T_model_cam_ransac = invert(T_cam_model_ransac)

    ransac_metrics = compute_all(frame["model_points_m"], T_cam_model_ransac, gt_pose)
    res["ransac"] = {
        "inlier_count": int(rr.inliers.sum()),
        "inlier_ratio": round(rr.inlier_ratio, 4),
        "mean_inlier_residual_m": round(rr.mean_inlier_residual, 6),
        "success": bool(rr.inliers.sum() >= 3),
        "add_mm": round(float(ransac_metrics["add"]) * 1e3, 3),
        "adds_mm": round(float(ransac_metrics["adds"]) * 1e3, 3),
        "trans_mm": round(float(ransac_metrics["trans"]) * 1e3, 3),
        "rot_deg": round(float(ransac_metrics["rot_deg"]), 3),
    }

    if not res["ransac"]["success"]:
        res["error"] = "ransac_failed: fewer than 3 inliers"
        return res

    # --- ICP ---
    icp_cfg = cfg["icp"]
    icp_res = icp_refine(
        scene_pcd, model_pcd, T_model_cam_ransac,
        corr_schedule_m=icp_cfg["corr_schedule_m"],
        max_iter_per_stage=icp_cfg["max_iter_per_stage"])

    T_cam_model_final = invert(icp_res.T_model_scene)

    icp_metrics = compute_all(frame["model_points_m"], T_cam_model_final, gt_pose)
    res["icp"] = {
        "fitness": round(icp_res.fitness, 4),
        "rmse_m": round(icp_res.inlier_rmse, 6),
    }
    res["pose"] = {
        "add_mm": round(float(icp_metrics["add"]) * 1e3, 3),
        "adds_mm": round(float(icp_metrics["adds"]) * 1e3, 3),
        "trans_mm": round(float(icp_metrics["trans"]) * 1e3, 3),
        "rot_deg": round(float(icp_metrics["rot_deg"]), 3),
    }

    return res


def main():
    import yaml
    cfg = yaml.safe_load(Path("configs/p3_0_gate3.yaml").read_text("utf-8"))
    data_root = Path(cfg["data"]["root"])

    out_root = Path("outputs/p3_1_a_robust_norm")
    out_root.mkdir(parents=True, exist_ok=True)

    net = CoordNet()
    ckpt = cfg["model"]["checkpoint"]
    net.load_state_dict(torch.load(ckpt, weights_only=True))
    print(f"[p3.1-a] checkpoint: {ckpt}")
    print(f"[p3.1-a] CoordNet params: {sum(p.numel() for p in net.parameters())}")
    print(f"[p3.1-a] normalization: percentile(radii, 95) instead of max(radii)")

    all_results = {}
    base_seed = cfg["ransac_umeyama"]["seed"]

    for obj_cfg in cfg["objects"]:
        obj_id = obj_cfg["obj_id"]
        scene = obj_cfg["scene"]
        frames = obj_cfg["test_frames"]
        metric = obj_cfg["success_metric"]
        threshold = obj_cfg["threshold_01d_mm"]

        model_pcd, _ = load_model_cloud(str(data_root / "models" / f"obj_{obj_id:06d}.ply"))

        print(f"\n{'='*70}")
        print(f"obj_id={obj_id} scene={scene} metric={metric} threshold={threshold}mm")
        print(f"{'='*70}")

        obj_frames = []
        for i, im_id in enumerate(frames):
            frame_seed = base_seed + i * 1000 + obj_id * 10000
            frame = load_frame(data_root, scene, im_id, obj_id)
            tag = f"{scene:06d}/{im_id:06d}"
            print(f"\n  [{tag}] visib={frame['visib_fract']:.3f} mask_px={frame['mask'].sum()}")

            t0 = time.time()
            res = run_frame(frame, obj_id, net, model_pcd, cfg, frame_seed)
            dt = time.time() - t0
            res["frame_id"] = tag
            res["obj_id"] = obj_id
            res["time_s"] = round(dt, 2)

            print(f"    scale: baseline={res['baseline_scale']:.4f}m "
                  f"robust={res['robust_scale']:.4f}m "
                  f"ratio={res['scale_ratio']:.2f}x")
            print(f"    norm_xyz_std: {res['norm_xyz_std']}")
            ce = res["canonical_err_mm"]
            print(f"    canonical err: mean={ce['mean']:.2f}mm median={ce['median']:.2f}mm "
                  f"p90={ce['p90']:.2f}mm max={ce['max']:.2f}mm")
            print(f"    axis_corr: {res['axis_correlation']}")

            if "pose" in res:
                primary = res["pose"][metric + "_mm"]
                ok = primary < threshold
                res["success"] = ok
                tag_result = "SUCCESS" if ok else "FAIL"
                print(f"    ransac: inliers={res['ransac']['inlier_count']} "
                      f"ratio={res['ransac']['inlier_ratio']:.3f} "
                      f"resid={res['ransac']['mean_inlier_residual_m']*1e3:.2f}mm")
                print(f"    ransac pose: ADD={res['ransac']['add_mm']:.2f}mm "
                      f"rot={res['ransac']['rot_deg']:.1f}deg")
                print(f"    icp: fitness={res['icp']['fitness']:.3f} "
                      f"rmse={res['icp']['rmse_m']*1e3:.2f}mm")
                print(f"    final: {metric}={primary:.2f}mm [{tag_result}] "
                      f"trans={res['pose']['trans_mm']:.1f}mm "
                      f"rot={res['pose']['rot_deg']:.1f}deg")
            else:
                res["success"] = False
                print(f"    FAILED: {res.get('error', 'unknown')}")

            obj_frames.append(res)

        n_ok = sum(1 for r in obj_frames if r.get("success", False))
        summary = {
            "obj_id": obj_id, "scene": scene, "metric": metric,
            "threshold_mm": threshold, "n_frames": len(frames),
            "n_success": n_ok, "success_rate": round(n_ok / len(frames), 3),
        }
        for m_key in ("add_mm", "adds_mm"):
            vals = [r["pose"][m_key] for r in obj_frames if "pose" in r]
            if vals:
                summary[m_key] = {"mean": round(np.mean(vals), 3),
                                  "median": round(np.median(vals), 3),
                                  "max": round(np.max(vals), 3)}

        all_results[f"obj_{obj_id:02d}"] = {"summary": summary, "frames": obj_frames}
        print(f"\n  >> obj{obj_id:02d}: {n_ok}/{len(frames)} success")
        for m_key in ("add_mm", "adds_mm"):
            if m_key in summary:
                s = summary[m_key]
                print(f"     {m_key}: mean={s['mean']:.2f} median={s['median']:.2f} max={s['max']:.2f}")

    out_path = out_root / "p3_1_a_results.json"
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(all_results, f, indent=2, ensure_ascii=False)
    print(f"\nresults saved: {out_path}")


if __name__ == "__main__":
    main()
