"""P3.0-S Gate 3: sim-to-real feasibility test on real YCB-V frames.

Pipeline per frame (inference uses ZERO GT pose):
  1. oracle mask_visib -> masked depth deprojection -> camera-frame point cloud
  2. voxel downsample (5mm) -> random sample 1024 points
  3. normalize + concat RGB/255 -> CoordNet forward -> predicted canonical coords
  4. RANSAC-Umeyama (predicted canonical = src, camera xyz = dst) -> initial pose
  5. ICP refinement (P2.3 frozen schedule: 3cm->1cm->3mm)
  6. evaluate ADD / ADD-S / translation / rotation error vs GT
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

from r3p.geometry.camera import deproject, project
from r3p.geometry.se3 import make_T, invert, apply as apply_T
from r3p.learn.coord_net import CoordNet, normalize_points
from r3p.learn.umeyama import ransac_umeyama
from r3p.pose.geo_init import object_point_cloud, load_model_cloud, icp_refine
from r3p.evaluation.metrics import compute_all

MM_TO_M = 1e-3


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

    assert gt_pose is not None, f"obj_id {obj_id} not found in scene {scene} frame {im_id}"
    assert mask is not None

    mesh = o3d.io.read_triangle_mesh(str(data_root / "models" / f"obj_{obj_id:06d}.ply"))
    model_points_m = np.asarray(mesh.vertices, dtype=np.float64) * MM_TO_M

    return {"rgb": rgb, "depth": depth, "K": K, "mask": mask,
            "gt_pose": gt_pose, "model_points_m": model_points_m,
            "visib_fract": visib_fract}


def run_frame(frame: dict, obj_id: int, net: CoordNet, model_pcd,
              cfg: dict, frame_seed: int) -> dict:
    """Full pipeline on one frame. Returns result dict + estimated pose."""
    res = {"frame_seed": frame_seed}
    K = frame["K"]
    depth = frame["depth"]
    mask = frame["mask"]
    rgb = frame["rgb"]

    cam_xyz = deproject(K, depth, mask=mask)
    cam_rgb = rgb[mask]
    res["n_mask_pixels"] = int(mask.sum())
    res["n_deprojected_pts"] = int(len(cam_xyz))

    scene_pcd = object_point_cloud(depth, mask, K, voxel_m=cfg["icp"]["voxel_m"])
    scene_pts = np.asarray(scene_pcd.points)
    res["n_voxel_pts"] = int(len(scene_pts))

    n_pts = cfg["model"]["n_points"]
    if len(cam_xyz) < n_pts:
        res["error"] = f"insufficient points: {len(cam_xyz)} < {n_pts}"
        return res, None

    rng = np.random.default_rng(frame_seed)
    idx = rng.choice(len(cam_xyz), size=n_pts, replace=False)
    cam_sampled = cam_xyz[idx]
    rgb_sampled = cam_rgb[idx]

    cam_norm, center, scale = normalize_points(cam_sampled)
    features = np.concatenate([cam_norm, rgb_sampled / 255.0], axis=1).astype(np.float32)

    net.eval()
    with torch.no_grad():
        pred_canonical = net(torch.from_numpy(features)).numpy()
    res["n_correspondences"] = n_pts

    ransac_cfg = cfg["ransac_umeyama"]
    rr = ransac_umeyama(
        src=pred_canonical, dst=cam_sampled,
        threshold_m=ransac_cfg["threshold_m"],
        iters=ransac_cfg["iters"],
        seed=ransac_cfg["seed"])

    res["ransac"] = {
        "inlier_count": int(rr.inliers.sum()),
        "inlier_ratio": round(rr.inlier_ratio, 4),
        "mean_inlier_residual_m": round(rr.mean_inlier_residual, 6),
        "success": bool(rr.inliers.sum() >= 3),
    }

    if not res["ransac"]["success"]:
        res["error"] = "ransac_failed: fewer than 3 inliers"
        return res, None

    T_cam_model_ransac = make_T(rr.R, rr.t)
    T_model_cam_ransac = invert(T_cam_model_ransac)

    icp_cfg = cfg["icp"]
    icp_res = icp_refine(
        scene_pcd, model_pcd, T_model_cam_ransac,
        corr_schedule_m=icp_cfg["corr_schedule_m"],
        max_iter_per_stage=icp_cfg["max_iter_per_stage"])

    T_cam_model_final = invert(icp_res.T_model_scene)

    res["icp"] = {
        "fitness": round(icp_res.fitness, 4),
        "rmse_m": round(icp_res.inlier_rmse, 6),
    }

    metrics = compute_all(frame["model_points_m"], T_cam_model_final, frame["gt_pose"])
    res["pose"] = {
        "add_mm": round(metrics["add"] * 1e3, 3),
        "adds_mm": round(metrics["adds"] * 1e3, 3),
        "trans_mm": round(metrics["trans"] * 1e3, 3),
        "rot_deg": round(metrics["rot_deg"], 3),
    }

    return res, T_cam_model_final


def save_overlay(frame: dict, T_est: np.ndarray, out_path: Path):
    rgb = frame["rgb"].copy()
    K = frame["K"]
    model_pts = frame["model_points_m"]

    p_gt = apply_T(frame["gt_pose"], model_pts)
    uv_gt, z_gt = project(K, p_gt)
    valid = (z_gt > 0) & (uv_gt[:, 0] >= 0) & (uv_gt[:, 0] < rgb.shape[1]) & \
            (uv_gt[:, 1] >= 0) & (uv_gt[:, 1] < rgb.shape[0])
    for u, v in uv_gt[valid].astype(int):
        cv2.circle(rgb, (u, v), 1, (0, 255, 0), -1)

    if T_est is not None:
        p_est = apply_T(T_est, model_pts)
        uv_est, z_est = project(K, p_est)
        valid_e = (z_est > 0) & (uv_est[:, 0] >= 0) & (uv_est[:, 0] < rgb.shape[1]) & \
                  (uv_est[:, 1] >= 0) & (uv_est[:, 1] < rgb.shape[0])
        for u, v in uv_est[valid_e].astype(int):
            cv2.circle(rgb, (u, v), 1, (0, 0, 255), -1)

    out_path.parent.mkdir(parents=True, exist_ok=True)
    cv2.imwrite(str(out_path), cv2.cvtColor(rgb, cv2.COLOR_RGB2BGR))


def main():
    import yaml
    cfg = yaml.safe_load(Path("configs/p3_0_gate3.yaml").read_text("utf-8"))
    data_root = Path(cfg["data"]["root"])

    out_root = Path(cfg["output"]["root"]) / cfg["output"]["name"]
    out_root.mkdir(parents=True, exist_ok=True)

    net = CoordNet()
    ckpt = cfg["model"]["checkpoint"]
    net.load_state_dict(torch.load(ckpt, weights_only=True))
    n_params = sum(p.numel() for p in net.parameters())
    print(f"[gate3] checkpoint: {ckpt}")
    print(f"[gate3] CoordNet params: {n_params}")

    all_results = {}
    base_seed = cfg["ransac_umeyama"]["seed"]

    for obj_cfg in cfg["objects"]:
        obj_id = obj_cfg["obj_id"]
        scene = obj_cfg["scene"]
        frames = obj_cfg["test_frames"]
        metric = obj_cfg["success_metric"]
        threshold = obj_cfg["threshold_01d_mm"]

        model_pcd, _ = load_model_cloud(str(data_root / "models" / f"obj_{obj_id:06d}.ply"))

        print(f"\n{'='*60}")
        print(f"obj_id={obj_id} scene={scene} metric={metric} threshold={threshold}mm")
        print(f"{'='*60}")

        obj_frames = []
        for i, im_id in enumerate(frames):
            frame_seed = base_seed + i * 1000 + obj_id * 10000
            frame = load_frame(data_root, scene, im_id, obj_id)
            print(f"\n  [{scene:06d}/{im_id:06d}] visib={frame['visib_fract']:.3f} "
                  f"mask_px={frame['mask'].sum()}")

            t0 = time.time()
            res, T_est = run_frame(frame, obj_id, net, model_pcd, cfg, frame_seed)
            dt = time.time() - t0
            res["frame_id"] = f"{scene:06d}/{im_id:06d}"
            res["obj_id"] = obj_id
            res["time_s"] = round(dt, 2)

            if "pose" in res:
                primary = res["pose"][metric + "_mm"]
                ok = primary < threshold
                res["success"] = ok
                tag = "SUCCESS" if ok else "FAIL"
                print(f"    {metric}={primary:.2f}mm [{tag}] "
                      f"trans={res['pose']['trans_mm']:.1f}mm rot={res['pose']['rot_deg']:.1f}deg")
                print(f"    ransac: inliers={res['ransac']['inlier_count']} "
                      f"ratio={res['ransac']['inlier_ratio']:.3f} "
                      f"resid={res['ransac']['mean_inlier_residual_m']*1e3:.2f}mm")
                print(f"    icp: fitness={res['icp']['fitness']:.3f} "
                      f"rmse={res['icp']['rmse_m']*1e3:.2f}mm")
            else:
                res["success"] = False
                print(f"    FAILED: {res.get('error', 'unknown')}")

            overlay_path = out_root / f"obj{obj_id:02d}_{scene:06d}_{im_id:06d}_overlay.png"
            save_overlay(frame, T_est, overlay_path)
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

    out_path = out_root / "gate3_results.json"
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(all_results, f, indent=2, ensure_ascii=False)
    print(f"\nresults saved: {out_path}")

    go_min = cfg["success"]["go_min_frames"]
    weak_min = cfg["success"]["weak_min_frames"]
    print(f"\n{'='*60}")
    print(f"mechanical judgment (proposal thresholds, NOT frozen):")
    print(f"  GO>={go_min}, WEAK>={weak_min}, NO-GO<{weak_min}")
    print(f"{'='*60}")
    for key, od in all_results.items():
        s = od["summary"]
        n = s["n_success"]
        j = "GO" if n >= go_min else ("WEAK" if n >= weak_min else "NO-GO")
        print(f"  {key}: {n}/{s['n_frames']} -> {j}")


if __name__ == "__main__":
    main()
