"""Synthetic regression tests for the P2.3 geometry pipeline.

Correctness tests only — real-data accuracy is reported as measured.
"""

import numpy as np
import open3d as o3d
import pytest

from r3p.geometry.camera import make_K
from r3p.geometry.se3 import apply as apply_T, invert, make_T, matrix_from_axis_angle, rotation_error_deg
from r3p.pose.geo_init import (
    hypothesis_rotations,
    icp_refine,
    initial_pose,
    object_point_cloud,
    pca_analysis,
)


@pytest.fixture(scope="module")
def blob():
    """Asymmetric model blob (model frame, meters): distinct PCA eigenvalues."""
    rng = np.random.default_rng(11)
    pts = rng.normal(scale=[0.03, 0.05, 0.09], size=(1500, 3))
    pts -= pts.mean(axis=0)
    return pts


def test_hypothesis_rotations_are_24_proper_and_distinct():
    scene_axes, _ = pca_analysis(np.random.default_rng(1).normal(size=(500, 3)) * [0.03, 0.05, 0.09])
    model_axes, _ = pca_analysis(np.random.default_rng(2).normal(size=(500, 3)) * [0.03, 0.05, 0.09])
    rots = hypothesis_rotations(scene_axes, model_axes)
    assert len(rots) == 24
    for R in rots:
        assert np.allclose(R.T @ R, np.eye(3), atol=1e-12)
        assert np.linalg.det(R) == pytest.approx(1.0, abs=1e-12)
    uniq = {tuple(np.round(R, 6).ravel()) for R in rots}
    assert len(uniq) == 24, "hypotheses must be distinct"


def test_pca_and_icp_recover_synthetic_pose(blob):
    """Scene cloud = GT-transformed model blob. PCA of an identical cloud is
    identical, so one hypothesis starts at ~GT; selection-by-fitness + ICP
    must return the GT pose to numerical precision."""
    rng = np.random.default_rng(3)
    t_gt = np.array([0.02, -0.01, 0.75])
    R_gt = matrix_from_axis_angle([1.0, 2.0, 3.0], 0.9)
    T_gt = make_T(R_gt, t_gt)

    scene_pts = apply_T(T_gt, blob)
    scene_pcd = o3d.geometry.PointCloud()
    scene_pcd.points = o3d.utility.Vector3dVector(scene_pts)

    model_axes, _ = pca_analysis(blob)
    scene_axes, _ = pca_analysis(scene_pts)
    model_centroid = blob.mean(axis=0)
    scene_centroid = scene_pts.mean(axis=0)

    model_pcd = o3d.geometry.PointCloud()
    model_pcd.points = o3d.utility.Vector3dVector(blob)
    model_pcd.estimate_normals(search_param=o3d.geometry.KDTreeSearchParamHybrid(radius=0.03, max_nn=30))

    best = None
    for R in hypothesis_rotations(scene_axes, model_axes):
        T_init = initial_pose(R, scene_centroid, model_centroid)
        res = icp_refine(scene_pcd, model_pcd, invert(T_init))
        if best is None or res.fitness > best[1].fitness:
            best = (R, res)
    R_sel, res_sel = best
    assert res_sel.fitness > 0.95, f"fitness {res_sel.fitness}"
    T_cam_model = invert(res_sel.T_model_scene)
    assert rotation_error_deg(T_cam_model[:3, :3], R_gt) < 1.0
    assert np.linalg.norm(T_cam_model[:3, 3] - t_gt) < 2e-3


def test_icp_improves_perturbed_initialization(blob):
    """ICP must reduce pose error relative to a slightly perturbed init
    (the 'ICP refines a reasonable initial pose' requirement)."""
    rng = np.random.default_rng(5)
    t_gt = np.array([0.0, 0.0, 0.8])
    R_gt = matrix_from_axis_angle([0.3, 1.0, 0.4], 0.4)
    T_gt = make_T(R_gt, t_gt)
    scene_pts = apply_T(T_gt, blob)

    R_init = matrix_from_axis_angle([0.0, 0.0, 1.0], np.deg2rad(12)) @ R_gt  # 12 deg roll error
    t_init = t_gt + np.array([0.004, -0.003, 0.005])
    T_init = make_T(R_init, t_init)

    scene_pcd = o3d.geometry.PointCloud()
    scene_pcd.points = o3d.utility.Vector3dVector(scene_pts)
    model_pcd = o3d.geometry.PointCloud()
    model_pcd.points = o3d.utility.Vector3dVector(blob)
    model_pcd.estimate_normals(search_param=o3d.geometry.KDTreeSearchParamHybrid(radius=0.03, max_nn=30))

    res = icp_refine(scene_pcd, model_pcd, invert(T_init))
    assert res.fitness > 0.8
    T_out = invert(res.T_model_scene)
    err_before = rotation_error_deg(R_init, R_gt)
    err_after = rotation_error_deg(T_out[:3, :3], R_gt)
    assert err_after < err_before - 5.0, f"ICP barely improved: {err_before:.1f} -> {err_after:.1f} deg"
    assert err_after < 3.0
    assert np.linalg.norm(T_out[:3, 3] - t_gt) < np.linalg.norm(t_init - t_gt)


def test_object_point_cloud_filters_and_guards():
    K = make_K(570.0, 570.0, 320.0, 240.0)
    depth = np.zeros((480, 640), dtype=np.float32)
    depth[100:140, 300:360] = 0.8
    mask = np.zeros((480, 640), dtype=bool)
    mask[100:140, 300:360] = True
    pcd = object_point_cloud(depth, mask, K, voxel_m=0.003)
    pts = np.asarray(pcd.points)
    assert len(pts) > 0
    assert np.abs(pts[:, 2] - 0.8).max() < 1e-6

    empty_mask = np.zeros_like(mask)
    with pytest.raises(AssertionError):
        object_point_cloud(depth, empty_mask, K)
