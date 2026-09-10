"""P3.1-E: input sensitivity diagnostic (frozen multimodal checkpoint).

Question: is CoordNet's ~176.5 deg real-domain orientation bias driven mainly
by the RGB channel, the XYZ channel, or their point-wise association?

IMPORTANT: this is an INPUT SENSITIVITY probe of a frozen checkpoint that was
trained on XYZ+RGB. It is NOT a "RGB-only model vs geometry-only model"
ablation -- the checkpoint never saw single-modality inputs during training,
and no retraining happens here. Results may therefore reflect off-distribution
input behavior; collapse must be checked (prediction radius / std) before
interpreting "no bias".

Pre-registered conditions (NOTE: the approving message was truncated after
Condition A; B/C/D below are the standard sensitivity set, re-run is trivial
if the intended definitions differ):
  A full        : XYZ + RGB                     (Gate 3 baseline, bias ~176.5 deg expected)
  B rgb_mean    : XYZ + per-frame channel-mean RGB broadcast
                  (removes point-wise appearance, keeps RGB marginal)
  C xyz_zero    : normalized XYZ replaced by 0 (centroid) + RGB
                  (removes point-wise geometry)
  D rgb_shuffle : XYZ + RGB rows randomly permuted across points (fixed seed)
                  (destroys point-wise appearance-geometry association, keeps marginals)

Frozen: Gate 1 checkpoint, architecture, weights, max-radius normalization,
voxel, sampling seeds, oracle mask, 10 frames, RANSAC, ICP, metrics. GT pose is
used ONLY evaluation-side (canonical error / rigid rotation bias / pose error).
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

import p3_0_gate3 as g3
import yaml

from r3p.learn.coord_net import CoordNet, normalize_points
from r3p.learn.umeyama import umeyama_alignment, ransac_umeyama
from r3p.geometry.se3 import invert, make_T
from r3p.pose.geo_init import icp_refine
from r3p.evaluation.metrics import compute_all

CONDITIONS = ("full", "rgb_mean", "xyz_zero", "rgb_shuffle")


def rigid_rot_deg(pred: np.ndarray, gt: np.ndarray) -> tuple[float, float]:
    """P3.1-B protocol: Kabsch(pred -> gt), return (rotation angle deg, aligned residual mm)."""
    R, t = umeyama_alignment(pred, gt)
    resid = float(np.linalg.norm(pred @ R.T + t - gt, axis=1).mean()) * 1e3
    cos = np.clip((np.trace(R) - 1) / 2, -1, 1)
    return float(np.degrees(np.arccos(cos))), resid


def build_features(condition: str, cam_norm: np.ndarray, rgb: np.ndarray, rng) -> np.ndarray:
    if condition == "full":
        rgb_mod = rgb
    elif condition == "rgb_mean":
        rgb_mod = np.broadcast_to(rgb.mean(axis=0), rgb.shape)
    elif condition == "xyz_zero":
        return np.concatenate([np.zeros_like(cam_norm), rgb], axis=1).astype(np.float32)
    elif condition == "rgb_shuffle":
        rgb_mod = rgb[rng.permutation(len(rgb))]
    else:
        raise ValueError(condition)
    return np.concatenate([cam_norm, rgb_mod], axis=1).astype(np.float32)


def main():
    cfg = yaml.safe_load(Path("configs/p3_0_gate3.yaml").read_text("utf-8"))
    data_root = Path(cfg["data"]["root"])
    out_root = Path("outputs") / "p3_1_e_input_sensitivity"
    out_root.mkdir(parents=True, exist_ok=True)

    net = CoordNet()
    net.load_state_dict(torch.load(cfg["model"]["checkpoint"], weights_only=True))
    net.eval()

    results = {"conditions": CONDITIONS,
               "note": "input sensitivity probe of frozen checkpoint; NOT a modality ablation"}
    for obj_cfg in cfg["objects"]:
        obj_id, scene = obj_cfg["obj_id"], obj_cfg["scene"]
        metric, threshold = obj_cfg["success_metric"], obj_cfg["threshold_01d_mm"]
        model_pcd, _ = g3.load_model_cloud(str(data_root / f"models/obj_{obj_id:06d}.ply"))
        per_cond = {c: [] for c in CONDITIONS}

        print(f"\n=== obj {obj_id} (scene {scene}, metric {metric}) ===")
        for i, im_id in enumerate(obj_cfg["test_frames"]):
            frame_seed = cfg["ransac_umeyama"]["seed"] + i * 1000 + obj_id * 10000
            frame = g3.load_frame(data_root, scene, im_id, obj_id)
            T_gt = frame["gt_pose"]
            R_gt, t_gt = T_gt[:3, :3], T_gt[:3, 3]

            cam_xyz = g3.deproject(frame["K"], frame["depth"], mask=frame["mask"])
            cam_rgb = frame["rgb"][frame["mask"]]
            scene_pcd = g3.object_point_cloud(frame["depth"], frame["mask"], frame["K"],
                                              voxel_m=cfg["icp"]["voxel_m"])
            n_pts = cfg["model"]["n_points"]
            rng = np.random.default_rng(frame_seed)
            idx = rng.choice(len(cam_xyz), size=n_pts, replace=False)
            cam_sampled, rgb_sampled = cam_xyz[idx], cam_rgb[idx]
            cam_norm, _, _ = normalize_points(cam_sampled)
            gt_canonical = (cam_sampled - t_gt) @ R_gt  # evaluation-side GT canonical

            for condition in CONDITIONS:
                feat = build_features(condition, cam_norm, rgb_sampled / 255.0,
                                      np.random.default_rng(frame_seed + 7))
                with torch.no_grad():
                    pred = net(torch.from_numpy(feat[None]))[0].numpy()

                rot_deg, align_mm = rigid_rot_deg(pred, gt_canonical)
                canon_err = float(np.linalg.norm(pred - gt_canonical, axis=1).mean()) * 1e3
                pred_radius = float(np.linalg.norm(pred - pred.mean(axis=0), axis=1).mean()) * 1e3

                rr = ransac_umeyama(src=pred, dst=cam_sampled, threshold_m=0.01,
                                    iters=cfg["ransac_umeyama"]["iters"],
                                    seed=cfg["ransac_umeyama"]["seed"])
                pose = None
                if rr.inliers.sum() >= 3:
                    icp = icp_refine(scene_pcd, model_pcd, invert(make_T(rr.R.T, -(rr.R.T @ rr.t))),
                                     corr_schedule_m=cfg["icp"]["corr_schedule_m"],
                                     max_iter_per_stage=cfg["icp"]["max_iter_per_stage"])
                    met = compute_all(frame["model_points_m"], invert(icp.T_model_scene), T_gt)
                    pose = {"add_mm": round(met["add"] * 1e3, 2), "adds_mm": round(met["adds"] * 1e3, 2),
                            "fitness": round(icp.fitness, 3)}

                per_cond[condition].append({
                    "frame_id": f"{scene:06d}/{im_id:06d}",
                    "canon_err_mean_mm": round(canon_err, 2),
                    "bias_rot_deg": round(rot_deg, 2),
                    "aligned_residual_mm": round(align_mm, 2),
                    "pred_radius_mm": round(pred_radius, 2),
                    "ransac_inlier_ratio": round(float(rr.inlier_ratio), 3),
                    "pose": pose,
                })

        summary = {}
        for condition in CONDITIONS:
            rows = per_cond[condition]
            bias = sorted(r["bias_rot_deg"] for r in rows)
            med_bias = float(np.median(bias))
            radii = [r["pred_radius_mm"] for r in rows]
            primary = [ (r["pose"] or {}).get("add_mm" if metric == "add" else "adds_mm") for r in rows ]
            primary_ok = sum(1 for p in primary if p is not None and p < threshold)
            summary[condition] = {
                "median_bias_rot_deg": round(med_bias, 2),
                "bias_rot_deg_range": [bias[0], bias[-1]],
                "mean_canon_err_mm": round(float(np.mean([r["canon_err_mean_mm"] for r in rows])), 2),
                "mean_aligned_residual_mm": round(float(np.mean([r["aligned_residual_mm"] for r in rows])), 2),
                "mean_pred_radius_mm": round(float(np.mean(radii)), 2),
                "mean_ransac_inlier_ratio": round(float(np.mean([r["ransac_inlier_ratio"] for r in rows])), 3),
                "pose_success": f"{primary_ok}/{len(rows)}",
                "frames": rows,
            }
            print(f"  {condition:11s}: median bias {med_bias:7.2f} deg | canon err "
                  f"{summary[condition]['mean_canon_err_mm']:7.2f}mm | pred radius "
                  f"{summary[condition]['mean_pred_radius_mm']:6.2f}mm | pose {summary[condition]['pose_success']}")

        results[f"obj_{obj_id:02d}"] = {"obj_id": obj_id, "metric": metric,
                                        "threshold_mm": threshold, "conditions": summary}

    # ------------------------------------------------------------------
    # Synthetic control: same 4 conditions on Gate 2 val samples. Separates
    # "real-data-triggered flip" from "ablated-input artifact": if an ablated
    # condition biases on REAL but not on SYNTHETIC, the flip is triggered by
    # the real domain through that channel; if it biases on both, the ablated
    # input distribution itself (not realness) is responsible.
    # ------------------------------------------------------------------
    print("\n=== synthetic control (10 Gate 2 val samples, bottle) ===")
    val_files = sorted(Path("data_synth/bottle/val").glob("sample_*.npz"))[:10]
    assert val_files, "no synthetic val samples (anti-false-pass)"
    synth = {c: [] for c in CONDITIONS}
    for vf in val_files:
        d = np.load(vf)
        xyz, rgb = d["xyz"].astype(np.float64), d["rgb"]
        coords = d["coords"].astype(np.float64)
        rng = np.random.default_rng(123)
        idx = rng.choice(len(xyz), size=1024, replace=False)
        xyz_s, rgb_s, coords_s = xyz[idx], rgb[idx], coords[idx]
        cam_norm, _, _ = normalize_points(xyz_s)
        for condition in CONDITIONS:
            feat = build_features(condition, cam_norm, rgb_s / 255.0,
                                  np.random.default_rng(123))
            with torch.no_grad():
                pred = net(torch.from_numpy(feat[None]))[0].numpy()
            rot_deg, _ = rigid_rot_deg(pred, coords_s)
            radius = float(np.linalg.norm(pred - pred.mean(axis=0), axis=1).mean()) * 1e3
            synth[condition].append({"bias_rot_deg": round(rot_deg, 2),
                                     "pred_radius_mm": round(radius, 2)})
    synth_summary = {}
    for condition in CONDITIONS:
        bias = sorted(r["bias_rot_deg"] for r in synth[condition])
        synth_summary[condition] = {
            "median_bias_rot_deg": round(float(np.median(bias)), 2),
            "bias_rot_deg_range": [bias[0], bias[-1]],
            "mean_pred_radius_mm": round(float(np.mean([r["pred_radius_mm"] for r in synth[condition]])), 2),
        }
        print(f"  {condition:11s}: median bias {synth_summary[condition]['median_bias_rot_deg']:7.2f} deg "
              f"| pred radius {synth_summary[condition]['mean_pred_radius_mm']:6.2f}mm")
    results["synthetic_control"] = synth_summary

    with open(out_root / "p3_1_e_results.json", "w", encoding="utf-8") as f:
        json.dump(results, f, indent=2, ensure_ascii=False)
    print(f"\nsaved: {out_root / 'p3_1_e_results.json'}")


if __name__ == "__main__":
    main()
