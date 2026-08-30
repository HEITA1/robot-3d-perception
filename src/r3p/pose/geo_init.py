"""Geometry-based coarse-to-fine 6D pose (P2.3, route A).

Pipeline per frame (inference, NO GT pose anywhere):

    oracle mask -> object point cloud (camera frame, meters, voxel-downsampled)
    -> PCA axes of the scene cloud
    -> 24 proper-rotation hypotheses (all signed axis permutations, det = +1)
    -> initial pose per hypothesis (rotation + centroid translation alignment)
    -> point-to-plane ICP each, schedule 3cm -> 1cm -> 3mm (frozen)
    -> select by ICP fitness (tie-break: lower RMSE)   [the ONLY selection signal]

ICP direction: source = scene cloud, target = model cloud. The returned
transformation maps scene -> model (T_model_cam); the caller inverts it to get
T_cam_model. This direction makes `fitness` = fraction of *observed* object
points explained by the model, which stays meaningful under single-view
partial visibility.

Oracle segmentation: the mask is GT mask_visib — a declared controlled
experimental condition (project decision D2), NOT a full-pose-system claim.
"""

from __future__ import annotations

from dataclasses import dataclass
from itertools import permutations, product

import numpy as np
import open3d as o3d

from ..geometry.camera import deproject
from ..geometry.se3 import invert


def object_point_cloud(depth: np.ndarray, mask: np.ndarray, K: np.ndarray, voxel_m: float = 0.005):
    """Masked depth -> camera-frame point cloud (meters), voxel-downsampled.

    Open3D's voxel_down_sample does not guarantee deterministic output ORDER
    (unordered internal buckets); ICP is sensitive to point order at the
    3rd-decimal level, which made knife-edge frames flip between runs. Points
    are therefore re-sorted lexicographically after downsampling: same point
    SET, canonical order, run-to-run reproducible."""
    pts = deproject(K, depth, mask=mask)
    assert len(pts) > 0, "object point cloud is empty (anti-false-pass)"
    pcd = o3d.geometry.PointCloud()
    pcd.points = o3d.utility.Vector3dVector(pts)
    if voxel_m > 0:
        pcd = pcd.voxel_down_sample(voxel_m)
    sorted_pts = np.asarray(pcd.points)[np.lexsort(np.asarray(pcd.points).T)]
    pcd.points = o3d.utility.Vector3dVector(sorted_pts)
    return pcd


def pca_analysis(points: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """Principal axes (columns, sorted by eigenvalue descending) + eigenvalues."""
    centered = points - points.mean(axis=0)
    cov = centered.T @ centered / len(centered)
    eigvals, eigvecs = np.linalg.eigh(cov)
    order = np.argsort(eigvals)[::-1]
    return eigvecs[:, order], eigvals[order]


def hypothesis_rotations(scene_axes: np.ndarray, model_axes: np.ndarray) -> list[np.ndarray]:
    """All 24 proper rotations aligning the sorted model PCA frame onto the
    sorted scene PCA frame: 6 axis permutations x 4 sign combinations (det=+1).

    R @ model_axes[:, i] maps the i-th model principal axis onto a signed
    scene principal axis. Declared a priori; the full set is always evaluated.
    """
    rotations = []
    for perm in permutations(range(3)):
        for signs in product((1.0, -1.0), repeat=3):
            A = scene_axes[:, perm] * signs
            R = A @ model_axes.T
            if np.linalg.det(R) > 0:
                rotations.append(R)
    assert len(rotations) == 24, f"expected 24 proper rotations, got {len(rotations)}"
    return rotations


def initial_pose(R: np.ndarray, scene_centroid: np.ndarray, model_centroid: np.ndarray) -> np.ndarray:
    """Rotation hypothesis + centroid translation alignment (meters)."""
    T = np.eye(4)
    T[:3, :3] = R
    T[:3, 3] = scene_centroid - R @ model_centroid
    return T


def load_model_cloud(mesh_path: str) -> tuple[o3d.geometry.PointCloud, np.ndarray]:
    """Mesh vertices (meters) as the model point cloud + estimated normals
    (target-side normals for point-to-plane ICP). BOP models are in mm."""
    mesh = o3d.io.read_triangle_mesh(str(mesh_path))
    assert len(mesh.vertices) > 0, f"empty mesh: {mesh_path}"
    pcd = o3d.geometry.PointCloud()
    pcd.points = o3d.utility.Vector3dVector(np.asarray(mesh.vertices) * 1e-3)
    pcd.estimate_normals(search_param=o3d.geometry.KDTreeSearchParamHybrid(radius=0.02, max_nn=30))
    return pcd, np.asarray(pcd.points)


@dataclass
class IcpResult:
    T_model_scene: np.ndarray  # scene -> model (invert for the camera-frame pose)
    fitness: float
    inlier_rmse: float  # meters


def icp_refine(scene_pcd: o3d.geometry.PointCloud, model_pcd: o3d.geometry.PointCloud,
               T_model_scene_init: np.ndarray, corr_schedule_m=(0.03, 0.01, 0.003),
               max_iter_per_stage: int = 60) -> IcpResult:
    """Chained point-to-plane ICP with the frozen coarse-to-fine schedule."""
    estimation = o3d.pipelines.registration.TransformationEstimationPointToPlane()
    criteria = o3d.pipelines.registration.ICPConvergenceCriteria(max_iteration=max_iter_per_stage)
    T = T_model_scene_init.copy()
    fitness, rmse = 0.0, float("inf")
    for max_corr in corr_schedule_m:
        result = o3d.pipelines.registration.registration_icp(
            scene_pcd, model_pcd, max_corr, T, estimation, criteria)
        T = result.transformation
        fitness, rmse = result.fitness, result.inlier_rmse
        if not (np.isfinite(T).all() and np.isfinite(fitness) and np.isfinite(rmse)):
            # degenerate correspondences can poison the transform; report as
            # non-converged instead of propagating NaNs downstream
            return IcpResult(T_model_scene=T_model_scene_init.copy(), fitness=0.0, inlier_rmse=float("inf"))
    return IcpResult(T_model_scene=T, fitness=float(fitness), inlier_rmse=float(rmse))


# --------------------------------------------------------------------------- #
# Replaceable per-frame inference interface (Phase 3 learning methods should
# implement the same signature and return the same structure).
# --------------------------------------------------------------------------- #
@dataclass
class PoseHypothesis:
    index: int
    T_cam_model_init: np.ndarray
    T_cam_model: np.ndarray | None  # post-ICP camera-frame pose (meters)
    fitness: float
    inlier_rmse: float  # meters


@dataclass
class GeometricPoseResult:
    scene_points: np.ndarray  # (N, 3) camera frame, meters (voxel-downsampled)
    pca_ratio_l2_l1: float
    pca_ratio_l3_l1: float
    hypotheses: list  # list[PoseHypothesis], len 24
    selected: PoseHypothesis | None  # fitness argmax, rmse tie-break
    scene_centroid: np.ndarray


def estimate_pose(depth, mask, K, model_pcd: o3d.geometry.PointCloud,
                  model_points_m: np.ndarray, voxel_m: float = 0.005,
                  corr_schedule_m=(0.03, 0.01, 0.003), max_iter_per_stage: int = 60,
                  min_cloud_pts: int = 500) -> GeometricPoseResult | None:
    """Full per-frame inference. Returns None if the observation is insufficient
    (fewer than min_cloud_pts valid masked depth points)."""
    cloud = object_point_cloud(depth, mask, K, voxel_m)
    if len(cloud.points) < min_cloud_pts:
        return None
    scene_pts = np.asarray(cloud.points)
    scene_axes, scene_vals = pca_analysis(scene_pts)
    model_axes, _ = pca_analysis(model_points_m)
    rots = hypothesis_rotations(scene_axes, model_axes)
    scene_centroid = scene_pts.mean(axis=0)
    model_centroid = model_points_m.mean(axis=0)

    hypotheses = []
    for j, R in enumerate(rots):
        T_init = initial_pose(R, scene_centroid, model_centroid)
        res = icp_refine(cloud, model_pcd, invert(T_init),
                         corr_schedule_m=corr_schedule_m, max_iter_per_stage=max_iter_per_stage)
        hypotheses.append(PoseHypothesis(
            index=j, T_cam_model_init=T_init, T_cam_model=invert(res.T_model_scene),
            fitness=res.fitness, inlier_rmse=res.inlier_rmse))
    selected = max(hypotheses, key=lambda h: (h.fitness, -h.inlier_rmse))
    return GeometricPoseResult(
        scene_points=scene_pts,
        pca_ratio_l2_l1=float(scene_vals[1] / scene_vals[0]),
        pca_ratio_l3_l1=float(scene_vals[2] / scene_vals[0]),
        hypotheses=hypotheses, selected=selected, scene_centroid=scene_centroid)
