"""P3.1-C: post-hoc canonical rotation diagnostic (single fixed rotation).

Question (per approved proposal): does ONE fixed canonical rotation of
~176.5 degrees explain the Gate 3 pose failures?

Pre-registered correction (BEFORE running, from completed P3.1-B evidence only):
  axis   = canonical (model-frame) Y
           -- from the P3.1-B per-axis correlation signature (-, +, -) on clean
              bottle frames: pred-vs-gt corr X=-0.84, Y=+0.57, Z=-0.997,
              matching a ~180 deg rotation about the canonical Y axis
  angle  = -176.5 deg (right-hand rule about +Y)
           -- magnitude from P3.1-B rigid-alignment means (clean bottle 176.6,
              bowl 176.5, all-real range 175.1-179.0); direction = inverse of
              the P3.1-B Kabsch(pred -> gt) mismatch rotation.
  known caveat, pre-registered: the SIGN of the axis-angle is not recoverable
  from the published P3.1-B evidence (rotations of +/-176.5 deg about +Y have
  the same first-order correlation signature). The wrong sign composes with the
  true mismatch to a residual of only ~7 deg (~10 mm at object radius), so the
  diagnostic stays informative under either sign; ambiguity is reported.

Everything else is bit-identical to scripts/p3_0_gate3.py (same checkpoint,
preprocessing, normalization, sampling seeds, RANSAC, ICP, frames, metrics).
Baseline numbers are READ from outputs/p3_0_gate3/gate3_results.json -- the
baseline pipeline is NOT re-run. This is a diagnostic experiment: Gate 3's
NO-GO verdict stands regardless of the outcome here.
"""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path

import cv2
import numpy as np
import torch

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import p3_0_gate3 as g3  # reuse load_frame / save_overlay / structure
import yaml

from r3p.learn.coord_net import CoordNet, normalize_points
from r3p.learn.umeyama import ransac_umeyama
from r3p.geometry.se3 import invert, make_T
from r3p.pose.geo_init import icp_refine
from r3p.evaluation.metrics import compute_all

# --- pre-registered single fixed diagnostic rotation (see module docstring) ---
CORRECTION_ANGLE_DEG = -176.5
CORRECTION_AXIS = "canonical Y"


def rot_y_deg(angle_deg: float) -> np.ndarray:
    th = np.deg2rad(angle_deg)
    c, s = np.cos(th), np.sin(th)
    return np.array([[c, 0.0, s], [0.0, 1.0, 0.0], [-s, 0.0, c]])


R_FIX = rot_y_deg(CORRECTION_ANGLE_DEG)


def run_frame_corrected(frame: dict, net: CoordNet, model_pcd, cfg: dict, frame_seed: int) -> dict:
    """scripts/p3_0_gate3.py run_frame with ONE insertion: the fixed rotation
    applied to the predicted canonical coordinates before RANSAC."""
    res: dict = {}
    K, depth, mask, rgb = frame["K"], frame["depth"], frame["mask"], frame["rgb"]

    from r3p.geometry.camera import deproject

    cam_xyz = deproject(K, depth, mask=mask)
    cam_rgb = rgb[mask]
    res["n_deprojected_pts"] = int(len(cam_xyz))

    scene_pcd = g3.object_point_cloud(depth, mask, K, voxel_m=cfg["icp"]["voxel_m"])

    n_pts = cfg["model"]["n_points"]
    if len(cam_xyz) < n_pts:
        res["error"] = f"insufficient points: {len(cam_xyz)} < {n_pts}"
        return res

    rng = np.random.default_rng(frame_seed)
    idx = rng.choice(len(cam_xyz), size=n_pts, replace=False)
    cam_sampled = cam_xyz[idx]
    rgb_sampled = cam_rgb[idx]

    cam_norm, _, _ = normalize_points(cam_sampled)
    features = np.concatenate([cam_norm, rgb_sampled / 255.0], axis=1).astype(np.float32)

    net.eval()
    with torch.no_grad():
        pred_raw = net(torch.from_numpy(features)).numpy()

    # === THE single diagnostic insertion =====================================
    pred_canonical = (R_FIX @ pred_raw.T).T
    # =========================================================================

    rr = ransac_umeyama(
        src=pred_canonical, dst=cam_sampled,
        threshold_m=cfg["ransac_umeyama"]["threshold_m"],
        iters=cfg["ransac_umeyama"]["iters"],
        seed=cfg["ransac_umeyama"]["seed"])
    res["ransac"] = {
        "inlier_count": int(rr.inliers.sum()),
        "inlier_ratio": round(rr.inlier_ratio, 4),
        "mean_inlier_residual_m": round(rr.mean_inlier_residual, 6),
    }
    if rr.inliers.sum() < 3:
        res["error"] = "ransac_failed"
        return res

    T_cam_model_ransac = make_T(rr.R, rr.t)
    icp_res = icp_refine(scene_pcd, model_pcd, invert(T_cam_model_ransac),
                         corr_schedule_m=cfg["icp"]["corr_schedule_m"],
                         max_iter_per_stage=cfg["icp"]["max_iter_per_stage"])
    T_cam_model_final = invert(icp_res.T_model_scene)
    res["icp"] = {"fitness": round(icp_res.fitness, 4),
                  "rmse_m": round(icp_res.inlier_rmse, 6)}
    metrics = compute_all(frame["model_points_m"], T_cam_model_final, frame["gt_pose"])
    # NOTE: only meter-valued metrics are scaled to mm; rot_deg stays degrees
    res["pose"] = {
        "add_mm": round(metrics["add"] * 1e3, 3),
        "adds_mm": round(metrics["adds"] * 1e3, 3),
        "trans_mm": round(metrics["trans"] * 1e3, 3),
        "rot_deg": round(metrics["rot_deg"], 3),
    }
    res["T_est"] = T_cam_model_final
    return res


def main():
    import yaml as _yaml  # noqa: F401  (g3.main reads yaml itself; config here too)

    cfg = _yaml.safe_load(Path("configs/p3_0_gate3.yaml").read_text("utf-8"))
    data_root = Path(cfg["data"]["root"])
    out_root = Path("outputs") / "p3_1_c_posthoc_rotation"
    out_root.mkdir(parents=True, exist_ok=True)

    baseline = json.loads((Path("outputs") / "p3_0_gate3" / "gate3_results.json").read_text("utf-8"))

    net = CoordNet()
    net.load_state_dict(torch.load(cfg["model"]["checkpoint"], weights_only=True))
    print(f"[p3.1-c] checkpoint: {cfg['model']['checkpoint']}")
    print(f"[p3.1-c] pre-registered correction: {CORRECTION_ANGLE_DEG} deg about {CORRECTION_AXIS}")

    base_seed = cfg["ransac_umeyama"]["seed"]
    all_results = {}
    for obj_cfg in cfg["objects"]:
        obj_id, scene = obj_cfg["obj_id"], obj_cfg["scene"]
        frames, metric = obj_cfg["test_frames"], obj_cfg["success_metric"]
        threshold = obj_cfg["threshold_01d_mm"]
        model_pcd, _ = g3.load_model_cloud(str(data_root / f"models/obj_{obj_id:06d}.ply"))
        base_obj = baseline[f"obj_{obj_id:02d}"]

        print(f"\n{'=' * 66}\nobj {obj_id} (scene {scene}, metric {metric}, thr {threshold}mm)\n{'=' * 66}")
        rows = []
        for i, im_id in enumerate(frames):
            frame_seed = base_seed + i * 1000 + obj_id * 10000
            frame = g3.load_frame(data_root, scene, im_id, obj_id)
            t0 = time.time()
            res = run_frame_corrected(frame, net, model_pcd, cfg, frame_seed)
            dt = time.time() - t0
            T_est = res.pop("T_est", None)

            base_frame = next(fr for fr in base_obj["frames"]
                              if fr.get("frame_id") == f"{scene:06d}/{im_id:06d}")
            row = {
                "frame_id": f"{scene:06d}/{im_id:06d}", "frame_seed": frame_seed,
                "baseline_add_mm": base_frame["pose"]["add_mm"] if "pose" in base_frame else None,
                "baseline_adds_mm": base_frame["pose"]["adds_mm"] if "pose" in base_frame else None,
                "baseline_rot_deg": base_frame["pose"]["rot_deg"] if "pose" in base_frame else None,
            }
            if "pose" in res:
                primary = res["pose"][metric + "_mm"]
                row.update({
                    "corrected_add_mm": res["pose"]["add_mm"], "corrected_adds_mm": res["pose"]["adds_mm"],
                    "corrected_trans_mm": res["pose"]["trans_mm"], "corrected_rot_deg": res["pose"]["rot_deg"],
                    "corrected_icp_fitness": res["icp"]["fitness"], "corrected_icp_rmse_mm": round(res["icp"]["rmse_m"] * 1e3, 2),
                    "corrected_ransac_ratio": res["ransac"]["inlier_ratio"],
                    "corrected_success": bool(primary < threshold),
                    "baseline_success": base_frame.get("success", False),
                    "delta_primary_mm": round(primary - (base_frame["pose"][metric + "_mm"] if "pose" in base_frame else float("nan")), 3),
                })
                print(f"  [{scene:06d}/{im_id:06d}] {metric}: {row['baseline_adds_mm' if metric=='adds' else 'baseline_add_mm']} -> "
                      f"{primary:.2f}mm (Δ{row['delta_primary_mm']:+.2f}) rot {row['corrected_rot_deg']:.1f}deg "
                      f"fit={res['icp']['fitness']:.3f} [{'SUCCESS' if row['corrected_success'] else 'fail'}] ({dt:.1f}s)")
            else:
                row["corrected_error"] = res.get("error")
                print(f"  [{scene:06d}/{im_id:06d}] corrected run failed: {res.get('error')}")

            g3.save_overlay(frame, T_est, out_root / f"obj{obj_id:02d}_{scene:06d}_{im_id:06d}_corrected_overlay.png")
            rows.append(row)

        n_ok = sum(1 for r in rows if r.get("corrected_success"))
        corrected_vals = [r[f"corrected_{'adds' if metric == 'adds' else 'add'}_mm"]
                          for r in rows if r.get("corrected_adds_mm") or r.get("corrected_add_mm")]
        all_results[f"obj_{obj_id:02d}"] = {
            "obj_id": obj_id, "metric": metric, "threshold_mm": threshold,
            "n_frames": len(rows), "n_success_corrected": n_ok,
            "baseline_n_success": base_obj["summary"]["n_success"],
            "corrected_primary_mean_mm": round(float(np.mean(corrected_vals)), 3) if corrected_vals else None,
            "corrected_primary_median_mm": round(float(np.median(corrected_vals)), 3) if corrected_vals else None,
            "frames": rows,
        }
        print(f"  >> obj{obj_id:02d}: baseline {base_obj['summary']['n_success']}/5 -> corrected {n_ok}/5")

    all_results["correction"] = {
        "angle_deg": CORRECTION_ANGLE_DEG, "axis": CORRECTION_AXIS,
        "matrix": R_FIX.tolist(),
        "provenance": "P3.1-B rigid-alignment means (176.6/176.5 deg) + per-axis "
                      "correlation signature (-,+,-); sign ambiguity pre-registered",
    }
    with open(out_root / "p3_1_c_results.json", "w", encoding="utf-8") as f:
        json.dump(all_results, f, indent=2, ensure_ascii=False)
    print(f"\nresults saved: {out_root / 'p3_1_c_results.json'}")


if __name__ == "__main__":
    main()
