"""6D pose metrics: ADD, ADD-S, translation error, rotation error.

All metrics take model points (N, 3) in the model frame (meters) and 4x4
camera-frame poses. Symmetric objects must be judged by ADD-S (see
EXPERIMENT_LOG for the protocol notes; thresholds are decided in Phase 2).
"""

from __future__ import annotations

import numpy as np
from scipy.spatial.distance import cdist

from ..geometry.se3 import apply, rotation_error_deg


def add(model_points: np.ndarray, T_est: np.ndarray, T_gt: np.ndarray) -> float:
    """Average Distance: mean over model points of ||p_est_i - p_gt_i|| (meters)."""
    p_est = apply(T_est, model_points)
    p_gt = apply(T_gt, model_points)
    return float(np.linalg.norm(p_est - p_gt, axis=1).mean())


def adds(model_points: np.ndarray, T_est: np.ndarray, T_gt: np.ndarray) -> float:
    """ADD-S: mean over model points of min_j ||p_est_i - p_gt_j|| (meters).

    Symmetry-robust: invariant under pose changes that map the *model point
    set* to itself (e.g. a 180-degree flip of a box, any spin of a cylinder).
    """
    p_est = apply(T_est, model_points)
    p_gt = apply(T_gt, model_points)
    return float(cdist(p_est, p_gt).min(axis=1).mean())


def translation_error(T_est: np.ndarray, T_gt: np.ndarray) -> float:
    """||t_est - t_gt|| in meters."""
    return float(np.linalg.norm(np.asarray(T_est)[:3, 3] - np.asarray(T_gt)[:3, 3]))


def rotation_error(T_est: np.ndarray, T_gt: np.ndarray) -> float:
    """Geodesic rotation error in degrees."""
    return rotation_error_deg(np.asarray(T_est)[:3, :3], np.asarray(T_gt)[:3, :3])


def compute_all(model_points: np.ndarray, T_est: np.ndarray, T_gt: np.ndarray) -> dict:
    """All four metrics in one call; keys: add, adds, trans, rot_deg (meters / degrees)."""
    return {
        "add": add(model_points, T_est, T_gt),
        "adds": adds(model_points, T_est, T_gt),
        "trans": translation_error(T_est, T_gt),
        "rot_deg": rotation_error(T_est, T_gt),
    }
