"""P3.0-S Gate 3 failure debug: layer-by-layer audit of the 10 real frames.

Pure diagnostic — no model changes, no retraining, no parameter tuning.
Compares real pipeline intermediates against synthetic validation data.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import cv2
import numpy as np
import open3d as o3d
import torch

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from r3p.geometry.camera import deproject
from r3p.geometry.se3 import make_T, invert, apply as apply_T
from r3p.learn.coord_net import CoordNet, normalize_points
from r3p.learn.umeyama import ransac_umeyama, umeyama_alignment
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
    assert gt_pose is not None
    mesh = o3d.io.read_triangle_mesh(str(data_root / "models" / f"obj_{obj_id:06d}.ply"))
    model_points_m = np.asarray(mesh.vertices, dtype=np.float64) * MM_TO_M
    return {"rgb": rgb, "depth": depth, "K": K, "mask": mask,
            "gt_pose": gt_pose, "model_points_m": model_points_m,
            "visib_fract": visib_fract, "depth_scale": depth_scale}


def stats(arr, name=""):
    s = f"  shape={arr.shape} dtype={arr.dtype}"
    if arr.ndim >= 1 and arr.size > 0:
        flat = arr.flatten().astype(np.float64)
        s += f" min={flat.min():.6f} max={flat.max():.6f} mean={flat.mean():.6f} std={flat.std():.6f}"
    return s


def per_axis_stats(arr, name=""):
    lines = []
    for ax in range(arr.shape[1]):
        col = arr[:, ax]
        lines.append(f"    {name}[{ax}]: min={col.min():.6f} max={col.max():.6f} "
                      f"mean={col.mean():.6f} std={col.std():.6f}")
    return "\n".join(lines)


# ============================================================================
# MAIN
# ============================================================================
def main():
    import yaml
    cfg = yaml.safe_load(Path("configs/p3_0_gate3.yaml").read_text("utf-8"))
    data_root = Path(cfg["data"]["root"])

    net = CoordNet()
    ckpt = cfg["model"]["checkpoint"]
    net.load_state_dict(torch.load(ckpt, map_location="cpu", weights_only=True))
    net.eval()
    print(f"Checkpoint: {ckpt}")
    print(f"Params: {sum(p.numel() for p in net.parameters())}")

    out = {}

    # ========================================================================
    # SYNTHETIC VALIDATION BASELINE (Gate 2 data)
    # ========================================================================
    print("\n" + "=" * 80)
    print("SYNTHETIC VALIDATION BASELINE (Gate 2 val split)")
    print("=" * 80)

    synth_val_dir = Path("data_synth/bottle/val")
    synth_samples = []
    for p in sorted(synth_val_dir.glob("*.npz"))[:10]:
        s = np.load(p)
        synth_samples.append(s)

    print(f"\nLoaded {len(synth_samples)} synthetic val samples")

    synth_xyz_stats = []
    synth_coords_stats = []
    synth_norm_stats = []
    synth_pred_stats = []
    synth_cam_err_stats = []

    for s in synth_samples:
        xyz = s["xyz"].astype(np.float64)
        coords = s["coords"].astype(np.float64)
        T = s["T"]
        rgb = s["rgb"].astype(np.float64)

        xyz_norm, center, scale = normalize_points(xyz)
        features = np.concatenate([xyz_norm, rgb / 255.0], axis=1).astype(np.float32)
        with torch.no_grad():
            pred = net(torch.from_numpy(features)).numpy()

        pred_cam = apply_T(T, pred)
        cam_err = np.linalg.norm(pred_cam - xyz, axis=1)

        synth_xyz_stats.append(xyz)
        synth_coords_stats.append(coords)
        synth_norm_stats.append(xyz_norm)
        synth_pred_stats.append(pred)
        synth_cam_err_stats.append(cam_err)

    synth_xyz = np.concatenate(synth_xyz_stats)
    synth_coords = np.concatenate(synth_coords_stats)
    synth_norm = np.concatenate(synth_norm_stats)
    synth_pred = np.concatenate(synth_pred_stats)
    synth_cam_err = np.concatenate(synth_cam_err_stats)

    print(f"\nSynthetic camera-frame XYZ (10 val samples concatenated):")
    print(stats(synth_xyz, "xyz"))
    print(per_axis_stats(synth_xyz, "xyz"))

    print(f"\nSynthetic canonical coords (GT labels):")
    print(stats(synth_coords, "coords"))
    print(per_axis_stats(synth_coords, "coords"))

    print(f"\nSynthetic normalized XYZ (input to CoordNet):")
    print(stats(synth_norm, "norm"))
    print(per_axis_stats(synth_norm, "norm"))

    print(f"\nSynthetic CoordNet prediction (canonical):")
    print(stats(synth_pred, "pred"))
    print(per_axis_stats(synth_pred, "pred"))

    print(f"\nSynthetic ||T@pred - xyz_cam|| per-point error:")
    print(f"  mean={synth_cam_err.mean()*1e3:.3f}mm median={np.median(synth_cam_err)*1e3:.3f}mm "
          f"max={synth_cam_err.max()*1e3:.3f}mm")

    # ========================================================================
    # D1: REAL INPUT AUDIT
    # ========================================================================
    print("\n" + "=" * 80)
    print("D1: REAL INPUT AUDIT")
    print("=" * 80)

    real_all_cam_xyz = []
    real_all_cam_norm = []
    real_all_pred = []
    real_all_cam_sampled = []
    real_all_pred_canonical = []
    real_all_rgb = []
    real_all_depth = []
    real_all_masks = []
    real_all_voxel = []
    real_all_norm_params = []

    for obj_cfg in cfg["objects"]:
        obj_id = obj_cfg["obj_id"]
        scene = obj_cfg["scene"]
        frames = obj_cfg["test_frames"]

        model_pcd, model_pts = load_model_cloud(str(data_root / "models" / f"obj_{obj_id:06d}.ply"))

        print(f"\n--- obj{obj_id:02d} scene{scene} ---")

        for i, im_id in enumerate(frames):
            frame_seed = cfg["ransac_umeyama"]["seed"] + i * 1000 + obj_id * 10000
            frame = load_frame(data_root, scene, im_id, obj_id)
            tag = f"obj{obj_id:02d}/{scene:06d}/{im_id:06d}"
            print(f"\n  [{tag}] visib={frame['visib_fract']:.3f}")

            rgb = frame["rgb"]
            depth = frame["depth"]
            K = frame["K"]
            mask = frame["mask"]

            print(f"    RGB: shape={rgb.shape} dtype={rgb.dtype} min={rgb.min()} max={rgb.max()}")
            print(f"    Depth raw: shape={depth.shape} dtype={depth.dtype} "
                  f"min={depth.min():.4f}m max={depth.max():.4f}m median={np.median(depth[depth>0]):.4f}m")
            print(f"    Depth scale: {frame['depth_scale']}")
            print(f"    K: {K.flatten().tolist()}")
            print(f"    Mask pixels: {mask.sum()}")

            cam_xyz = deproject(K, depth, mask=mask)
            cam_rgb = rgb[mask]
            print(f"    Deprojected: {len(cam_xyz)} points")
            if len(cam_xyz) > 0:
                print(f"      XYZ range: x=[{cam_xyz[:,0].min():.4f},{cam_xyz[:,0].max():.4f}] "
                      f"y=[{cam_xyz[:,1].min():.4f},{cam_xyz[:,1].max():.4f}] "
                      f"z=[{cam_xyz[:,2].min():.4f},{cam_xyz[:,2].max():.4f}]")

            scene_pcd = object_point_cloud(depth, mask, K, voxel_m=cfg["icp"]["voxel_m"])
            scene_pts = np.asarray(scene_pcd.points)
            print(f"    Voxel pts: {len(scene_pts)}")

            n_pts = cfg["model"]["n_points"]
            rng = np.random.default_rng(frame_seed)
            idx = rng.choice(len(cam_xyz), size=n_pts, replace=False)
            cam_sampled = cam_xyz[idx]
            rgb_sampled = cam_rgb[idx]
            print(f"    Sampled: {n_pts} points")
            print(f"      cam_sampled centroid: {cam_sampled.mean(axis=0)}")
            print(f"      cam_sampled radius: {np.linalg.norm(cam_sampled - cam_sampled.mean(axis=0), axis=1).max():.4f}m")

            cam_norm, center, scale = normalize_points(cam_sampled)
            print(f"    Normalization: center={center} scale={scale:.6f}")
            print(f"      norm range: x=[{cam_norm[:,0].min():.4f},{cam_norm[:,0].max():.4f}] "
                  f"y=[{cam_norm[:,1].min():.4f},{cam_norm[:,1].max():.4f}] "
                  f"z=[{cam_norm[:,2].min():.4f},{cam_norm[:,2].max():.4f}]")
            print(f"      norm mean: {cam_norm.mean(axis=0)}")
            print(f"      norm std: {cam_norm.std(axis=0)}")

            features = np.concatenate([cam_norm, rgb_sampled / 255.0], axis=1).astype(np.float32)

            with torch.no_grad():
                pred_canonical = net(torch.from_numpy(features)).numpy()

            print(f"    CoordNet prediction (canonical):")
            print(f"      range: x=[{pred_canonical[:,0].min():.6f},{pred_canonical[:,0].max():.6f}] "
                  f"y=[{pred_canonical[:,1].min():.6f},{pred_canonical[:,1].max():.6f}] "
                  f"z=[{pred_canonical[:,2].min():.6f},{pred_canonical[:,2].max():.6f}]")
            print(f"      mean: {pred_canonical.mean(axis=0)}")
            print(f"      std: {pred_canonical.std(axis=0)}")
            pred_centroid = pred_canonical.mean(axis=0)
            pred_radius = np.linalg.norm(pred_canonical - pred_centroid, axis=1).max()
            print(f"      centroid: {pred_centroid} radius: {pred_radius:.6f}")

            # Compare with BOP model extent
            model_extent = np.linalg.norm(model_pts - model_pts.mean(axis=0), axis=1).max()
            print(f"      BOP model radius (from centroid): {model_extent:.6f}")
            print(f"      BOP model range: x=[{model_pts[:,0].min():.6f},{model_pts[:,0].max():.6f}] "
                  f"y=[{model_pts[:,1].min():.6f},{model_pts[:,1].max():.6f}] "
                  f"z=[{model_pts[:,2].min():.6f},{model_pts[:,2].max():.6f}]")

            # D3: Correspondence audit
            rr = ransac_umeyama(
                src=pred_canonical, dst=cam_sampled,
                threshold_m=cfg["ransac_umeyama"]["threshold_m"],
                iters=cfg["ransac_umeyama"]["iters"],
                seed=cfg["ransac_umeyama"]["seed"])

            # Compute all pairwise residuals for inliers
            T_cam_model_ransac = make_T(rr.R, rr.t)
            pred_transformed = apply_T(T_cam_model_ransac, pred_canonical)
            all_resid = np.linalg.norm(pred_transformed - cam_sampled, axis=1)
            inlier_resid = all_resid[rr.inliers]
            outlier_resid = all_resid[~rr.inliers]

            print(f"    RANSAC correspondence:")
            print(f"      inliers: {rr.inliers.sum()}/{len(rr.inliers)} ({rr.inlier_ratio*100:.1f}%)")
            print(f"      mean inlier resid: {rr.mean_inlier_residual*1e3:.3f}mm")
            if len(inlier_resid) > 0:
                print(f"      inlier resid: median={np.median(inlier_resid)*1e3:.3f}mm "
                      f"p90={np.percentile(inlier_resid, 90)*1e3:.3f}mm "
                      f"max={inlier_resid.max()*1e3:.3f}mm")
            if len(outlier_resid) > 0:
                print(f"      outlier resid: median={np.median(outlier_resid)*1e3:.3f}mm "
                      f"max={outlier_resid.max()*1e3:.3f}mm")

            # D4: RANSAC pose audit
            gt_pose = frame["gt_pose"]
            T_model_cam_ransac = invert(T_cam_model_ransac)

            ransac_metrics = compute_all(frame["model_points_m"], T_cam_model_ransac, gt_pose)
            print(f"    RANSAC pose vs GT:")
            print(f"      ADD={ransac_metrics['add']*1e3:.2f}mm ADD-S={ransac_metrics['adds']*1e3:.2f}mm "
                  f"trans={ransac_metrics['trans']*1e3:.2f}mm rot={ransac_metrics['rot_deg']:.2f}deg")

            # D5: ICP audit
            icp_res = icp_refine(
                scene_pcd, model_pcd, T_model_cam_ransac,
                corr_schedule_m=cfg["icp"]["corr_schedule_m"],
                max_iter_per_stage=cfg["icp"]["max_iter_per_stage"])
            T_cam_model_final = invert(icp_res.T_model_scene)

            icp_metrics = compute_all(frame["model_points_m"], T_cam_model_final, gt_pose)
            print(f"    ICP final pose vs GT:")
            print(f"      ADD={icp_metrics['add']*1e3:.2f}mm ADD-S={icp_metrics['adds']*1e3:.2f}mm "
                  f"trans={icp_metrics['trans']*1e3:.2f}mm rot={icp_metrics['rot_deg']:.2f}deg")
            print(f"      fitness={icp_res.fitness:.4f} rmse={icp_res.inlier_rmse*1e3:.3f}mm")

            # ICP delta
            rot_delta = abs(icp_metrics['rot_deg'] - ransac_metrics['rot_deg'])
            trans_delta = abs(icp_metrics['trans']*1e3 - ransac_metrics['trans']*1e3)
            print(f"    ICP delta from RANSAC: rot_delta={rot_delta:.2f}deg trans_delta={trans_delta:.2f}mm")

            # GT canonical coords for sampled points (what CoordNet SHOULD predict)
            gt_canonical = apply_T(invert(gt_pose), cam_sampled)
            print(f"    GT canonical (from GT pose, for comparison):")
            print(f"      range: x=[{gt_canonical[:,0].min():.6f},{gt_canonical[:,0].max():.6f}] "
                  f"y=[{gt_canonical[:,1].min():.6f},{gt_canonical[:,1].max():.6f}] "
                  f"z=[{gt_canonical[:,2].min():.6f},{gt_canonical[:,2].max():.6f}]")
            print(f"      mean: {gt_canonical.mean(axis=0)}")
            print(f"      centroid: {gt_canonical.mean(axis=0)} radius: {np.linalg.norm(gt_canonical - gt_canonical.mean(axis=0), axis=1).max():.6f}")

            # Per-point error: pred vs GT canonical
            canonical_err = np.linalg.norm(pred_canonical - gt_canonical, axis=1)
            print(f"    ||pred_canonical - gt_canonical||:")
            print(f"      mean={canonical_err.mean()*1e3:.3f}mm median={np.median(canonical_err)*1e3:.3f}mm "
                  f"max={canonical_err.max()*1e3:.3f}mm")

            # Check for axis flip between pred and GT canonical
            for ax in range(3):
                pred_ax_mean = pred_canonical[:, ax].mean()
                gt_ax_mean = gt_canonical[:, ax].mean()
                pred_ax_std = pred_canonical[:, ax].std()
                gt_ax_std = gt_canonical[:, ax].std()
                corr = np.corrcoef(pred_canonical[:, ax], gt_canonical[:, ax])[0, 1]
                neg_corr = np.corrcoef(pred_canonical[:, ax], -gt_canonical[:, ax])[0, 1]
                print(f"      axis {ax}: pred_mean={pred_ax_mean:.6f} gt_mean={gt_ax_mean:.6f} "
                      f"corr={corr:.4f} neg_corr={neg_corr:.4f}")

            # Collect for aggregate stats
            real_all_cam_xyz.append(cam_xyz)
            real_all_cam_norm.append(cam_norm)
            real_all_pred.append(pred_canonical)
            real_all_cam_sampled.append(cam_sampled)
            real_all_pred_canonical.append(pred_canonical)
            real_all_rgb.append(rgb_sampled)
            real_all_norm_params.append((center, scale))

    # ========================================================================
    # D6: AGGREGATE COMPARISON
    # ========================================================================
    print("\n" + "=" * 80)
    print("D6: SYNTHETIC vs REAL AGGREGATE COMPARISON")
    print("=" * 80)

    real_cam_xyz = np.concatenate(real_all_cam_xyz)
    real_norm = np.concatenate(real_all_cam_norm)
    real_pred = np.concatenate(real_all_pred)
    real_cam_sampled = np.concatenate(real_all_cam_sampled)

    print(f"\nCamera-frame XYZ:")
    print(f"  Synthetic: {stats(synth_xyz)}")
    print(f"  Real:      {stats(real_cam_xyz)}")

    print(f"\nNormalized XYZ (CoordNet input):")
    print(f"  Synthetic: {stats(synth_norm)}")
    print(f"  Real:      {stats(real_norm)}")

    print(f"\nCoordNet predicted canonical:")
    print(f"  Synthetic: {stats(synth_pred)}")
    print(f"  Real:      {stats(real_pred)}")

    print(f"\nSynthetic canonical GT labels:")
    print(f"  {stats(synth_coords)}")

    # Normalization parameter comparison
    print(f"\nNormalization parameters:")
    print(f"  Synthetic scales (per-sample): computed from val data")
    synth_scales = []
    for s in synth_samples:
        xyz = s["xyz"].astype(np.float64)
        _, _, sc = normalize_points(xyz)
        synth_scales.append(sc)
    print(f"    mean={np.mean(synth_scales):.6f} std={np.std(synth_scales):.6f} "
          f"min={min(synth_scales):.6f} max={max(synth_scales):.6f}")
    print(f"  Real scales (per-frame):")
    real_scales = [sp[1] for sp in real_all_norm_params]
    print(f"    mean={np.mean(real_scales):.6f} std={np.std(real_scales):.6f} "
          f"min={min(real_scales):.6f} max={max(real_scales):.6f}")

    print("\n" + "=" * 80)
    print("DEBUG AUDIT COMPLETE")
    print("=" * 80)


if __name__ == "__main__":
    main()
