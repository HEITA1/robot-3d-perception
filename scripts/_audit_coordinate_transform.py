"""Coordinate / Transform Audit for Gate 3 failure localization.

Pure analysis — no code modification, no retraining, no parameter changes.
"""

import json
import sys
from pathlib import Path

import numpy as np
import torch

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from r3p.geometry.se3 import apply as apply_T, invert, make_T
from r3p.learn.coord_net import CoordNet, normalize_points
from r3p.learn.umeyama import umeyama_alignment, ransac_umeyama

MM_TO_M = 1e-3

print("=" * 80)
print("COORDINATE / TRANSFORM AUDIT — Gate 3 Failure Localization")
print("=" * 80)

# ============================================================================
# 1. SYNTHETIC DATA COORDINATE DEFINITION
# ============================================================================
print("\n[1] SYNTHETIC DATA (Gate 1 training)")
print("-" * 80)

# Load one synthetic sample
sample_path = Path("data_synth/bottle/train/sample_0000.npz")
if not sample_path.exists():
    print(f"ERROR: {sample_path} not found")
    sys.exit(1)

s = np.load(sample_path)
xyz_cam = s["xyz"]  # camera-frame points (meters)
coords = s["coords"]  # canonical/model-frame points (meters)
T_cam_model = s["T"]  # camera pose (4x4)
rgb = s["rgb"]  # RGB colors

print(f"Sample: {sample_path.name}")
print(f"  xyz (camera frame): shape={xyz_cam.shape}, dtype={xyz_cam.dtype}, unit=meters")
print(f"    range: x=[{xyz_cam[:,0].min():.4f}, {xyz_cam[:,0].max():.4f}]")
print(f"           y=[{xyz_cam[:,1].min():.4f}, {xyz_cam[:,1].max():.4f}]")
print(f"           z=[{xyz_cam[:,2].min():.4f}, {xyz_cam[:,2].max():.4f}]")
print(f"  coords (model frame): shape={coords.shape}, dtype={coords.dtype}, unit=meters")
print(f"    range: x=[{coords[:,0].min():.4f}, {coords[:,0].max():.4f}]")
print(f"           y=[{coords[:,1].min():.4f}, {coords[:,1].max():.4f}]")
print(f"           z=[{coords[:,2].min():.4f}, {coords[:,2].max():.4f}]")
print(f"  T_cam_model: shape={T_cam_model.shape}, dtype={T_cam_model.dtype}")
print(f"    R det: {np.linalg.det(T_cam_model[:3,:3]):.6f}")
print(f"    t norm: {np.linalg.norm(T_cam_model[:3,3]):.4f} m")

# Verify coordinate consistency: xyz_cam should equal T_cam_model @ coords
xyz_cam_reconstructed = apply_T(T_cam_model, coords)
frame_err = np.abs(xyz_cam - xyz_cam_reconstructed).max()
print(f"  Frame consistency check: ||xyz_cam - T_cam_model @ coords||_max = {frame_err:.2e} m")
if frame_err < 1e-3:
    print(f"    ✅ PASS — xyz and coords are related by T_cam_model")
else:
    print(f"    ❌ FAIL — coordinate frame inconsistency!")

# ============================================================================
# 2. BOP MODEL COORDINATE DEFINITION
# ============================================================================
print("\n[2] BOP MODEL (Gate 3 inference)")
print("-" * 80)

import open3d as o3d
data_root = Path("data/ycbv")
mesh = o3d.io.read_triangle_mesh(str(data_root / "models" / "obj_000005.ply"))
model_points_m = np.asarray(mesh.vertices, dtype=np.float64) * MM_TO_M

print(f"BOP model: obj_000005.ply (mustard_bottle)")
print(f"  model_points_m: shape={model_points_m.shape}, dtype={model_points_m.dtype}, unit=meters")
print(f"    range: x=[{model_points_m[:,0].min():.4f}, {model_points_m[:,0].max():.4f}]")
print(f"           y=[{model_points_m[:,1].min():.4f}, {model_points_m[:,1].max():.4f}]")
print(f"           z=[{model_points_m[:,2].min():.4f}, {model_points_m[:,2].max():.4f}]")

# Compare synthetic coords vs BOP model points
print(f"\n  Comparison: synthetic coords vs BOP model points")
print(f"    synthetic coords range: x=[{coords[:,0].min():.4f}, {coords[:,0].max():.4f}]")
print(f"    BOP model range:        x=[{model_points_m[:,0].min():.4f}, {model_points_m[:,0].max():.4f}]")
print(f"    synthetic coords centroid: {coords.mean(axis=0)}")
print(f"    BOP model centroid:        {model_points_m.mean(axis=0)}")

# Check if synthetic coords are a subset of BOP model points
from scipy.spatial.distance import cdist
dists = cdist(coords, model_points_m)
min_dists = dists.min(axis=1)
print(f"    min distance from each synthetic coord to BOP model: mean={min_dists.mean():.6f} m, max={min_dists.max():.6f} m")
if min_dists.max() < 1e-3:
    print(f"    ✅ PASS — synthetic coords are subset of BOP model points")
else:
    print(f"    ⚠️  WARNING — synthetic coords do not exactly match BOP model points")

# ============================================================================
# 3. COORDNET PREDICTION ON SYNTHETIC DATA (sanity check)
# ============================================================================
print("\n[3] COORDNET PREDICTION ON SYNTHETIC DATA")
print("-" * 80)

net = CoordNet()
ckpt_path = Path("outputs/p3_0/gate1/coord_net_bottle.pt")
net.load_state_dict(torch.load(ckpt_path, map_location="cpu", weights_only=True))
net.eval()

# Prepare input (same as training)
cam_norm, center, scale = normalize_points(xyz_cam)
features = np.concatenate([cam_norm, rgb / 255.0], axis=1).astype(np.float32)

with torch.no_grad():
    pred_canonical = net(torch.from_numpy(features)).numpy()

print(f"CoordNet prediction on synthetic sample:")
print(f"  pred_canonical: shape={pred_canonical.shape}, dtype={pred_canonical.dtype}")
print(f"    range: x=[{pred_canonical[:,0].min():.4f}, {pred_canonical[:,0].max():.4f}]")
print(f"           y=[{pred_canonical[:,1].min():.4f}, {pred_canonical[:,1].max():.4f}]")
print(f"           z=[{pred_canonical[:,2].min():.4f}, {pred_canonical[:,2].max():.4f}]")
print(f"    centroid: {pred_canonical.mean(axis=0)}")

# Compare prediction with GT coords
pred_err = np.linalg.norm(pred_canonical - coords, axis=1)
print(f"  ||pred_canonical - coords||: mean={pred_err.mean():.6f} m, max={pred_err.max():.6f} m")

# Apply GT pose to prediction and compare with xyz_cam
pred_cam = apply_T(T_cam_model, pred_canonical)
cam_err = np.linalg.norm(pred_cam - xyz_cam, axis=1)
print(f"  ||T_cam_model @ pred - xyz_cam||: mean={cam_err.mean():.6f} m, max={cam_err.max():.6f} m")

# ============================================================================
# 4. RANSAC-UMEYAMA ON SYNTHETIC DATA (closed-loop sanity)
# ============================================================================
print("\n[4] RANSAC-UMEYAMA ON SYNTHETIC DATA (closed-loop test)")
print("-" * 80)

# src = pred_canonical (model frame), dst = xyz_cam (camera frame)
rr = ransac_umeyama(src=pred_canonical, dst=xyz_cam, threshold_m=0.01, iters=200, seed=0)
T_cam_model_recovered = make_T(rr.R, rr.t)

print(f"RANSAC-Umeyama result:")
print(f"  inliers: {rr.inliers.sum()}/{len(rr.inliers)} ({rr.inlier_ratio*100:.1f}%)")
print(f"  mean inlier residual: {rr.mean_inlier_residual*1e3:.3f} mm")
print(f"  recovered T_cam_model:")
print(f"    R det: {np.linalg.det(T_cam_model_recovered[:3,:3]):.6f}")
print(f"    t norm: {np.linalg.norm(T_cam_model_recovered[:3,3]):.4f} m")

# Compare recovered pose with GT pose
R_err = np.linalg.norm(T_cam_model_recovered[:3,:3] - T_cam_model[:3,:3], 'fro')
t_err = np.linalg.norm(T_cam_model_recovered[:3,3] - T_cam_model[:3,3])
print(f"  ||R_recovered - R_gt||_Fro = {R_err:.6f}")
print(f"  ||t_recovered - t_gt|| = {t_err:.6f} m")

# Check rotation angle
R_diff = T_cam_model[:3,:3].T @ T_cam_model_recovered[:3,:3]
trace = np.trace(R_diff)
cos_angle = (trace - 1.0) / 2.0
rot_angle_deg = np.degrees(np.arccos(np.clip(cos_angle, -1.0, 1.0)))
print(f"  rotation error: {rot_angle_deg:.2f}°")

if rot_angle_deg < 5.0 and t_err < 0.005:
    print(f"  ✅ PASS — closed-loop sanity check passed")
else:
    print(f"  ❌ FAIL — closed-loop sanity check failed!")
    print(f"      This indicates a coordinate transform bug in the pipeline.")

# ============================================================================
# 5. COORDINATE FRAME SUMMARY
# ============================================================================
print("\n[5] COORDINATE FRAME SUMMARY")
print("-" * 80)
print("Synthetic data (Gate 1 training):")
print("  xyz (camera frame) = T_cam_model @ coords (model frame)")
print("  coords = BOP model vertices (subset, from renderer)")
print("  T_cam_model = renderer camera pose (model→camera)")
print()
print("CoordNet training:")
print("  input: normalize(xyz_cam) + RGB/255")
print("  output: pred_canonical (model frame)")
print("  loss: ||T_cam_model @ pred_canonical - xyz_cam||")
print()
print("Gate 3 inference:")
print("  input: camera-frame points from real YCB-V depth")
print("  CoordNet output: predicted canonical coordinates (model frame)")
print("  RANSAC: src=pred_canonical, dst=cam_points → T_cam_model")
print("  ICP: refines T_cam_model")
print("  metric: compare T_cam_model_est vs T_cam_model_gt (BOP)")
print()
print("Key question:")
print("  Are synthetic 'coords' and BOP 'model_points_m' in the SAME frame?")
print(f"  Evidence: min distance = {min_dists.max():.6f} m (max over all synthetic coords)")
if min_dists.max() < 1e-3:
    print("  → YES, they are in the same frame (BOP model frame)")
else:
    print("  → NO, there is a coordinate frame mismatch!")

print("\n" + "=" * 80)
print("AUDIT COMPLETE")
print("=" * 80)
