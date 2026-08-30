"""SE(3) transforms and rotation representations.

Conventions
-----------
- Poses are 4x4 homogeneous matrices (float64). ``p_A = T_AB @ p_B_h`` maps
  points from frame B to frame A (the AB subscript is omitted in code).
- ``compose(T1, T2)`` equals ``T1 @ T2``: apply T2 first, then T1.
- Rotation error is the geodesic angle of ``R_gt.T @ R_est``, in degrees.
- Quaternions are ``(w, x, y, z)``.
- Units: meters and radians unless a name says otherwise (``*_deg``).
"""

from __future__ import annotations

import numpy as np

__all__ = [
    "make_T",
    "invert",
    "compose",
    "apply",
    "rot_x",
    "rot_y",
    "rot_z",
    "matrix_from_axis_angle",
    "matrix_from_quaternion",
    "quaternion_from_matrix",
    "rotation_angle",
    "rotation_error_deg",
]


def make_T(R: np.ndarray, t: np.ndarray) -> np.ndarray:
    """Build a 4x4 SE(3) matrix from a (3, 3) rotation and a (3,) translation."""
    R = np.asarray(R, dtype=np.float64)
    t = np.asarray(t, dtype=np.float64).reshape(3)
    if R.shape != (3, 3):
        raise ValueError(f"R must be (3, 3), got {R.shape}")
    T = np.eye(4)
    T[:3, :3] = R
    T[:3, 3] = t
    return T


def invert(T: np.ndarray) -> np.ndarray:
    """Exact SE(3) inverse: R^-1 = R^T, t^-1 = -R^T t."""
    R = T[:3, :3]
    return make_T(R.T, -(R.T @ T[:3, 3]))


def compose(T1: np.ndarray, T2: np.ndarray) -> np.ndarray:
    """T1 @ T2 (apply T2 first, then T1)."""
    return T1 @ T2


def apply(T: np.ndarray, points: np.ndarray) -> np.ndarray:
    """Transform an (N, 3) array of points by T."""
    pts = np.asarray(points, dtype=np.float64)
    return pts @ T[:3, :3].T + T[:3, 3]


def _axis_rotation(axis: np.ndarray, angle_rad: float) -> np.ndarray:
    return matrix_from_axis_angle(axis, angle_rad)


def rot_x(angle_rad: float) -> np.ndarray:
    return _axis_rotation([1.0, 0.0, 0.0], angle_rad)


def rot_y(angle_rad: float) -> np.ndarray:
    return _axis_rotation([0.0, 1.0, 0.0], angle_rad)


def rot_z(angle_rad: float) -> np.ndarray:
    return _axis_rotation([0.0, 0.0, 1.0], angle_rad)


def matrix_from_axis_angle(axis: np.ndarray, angle_rad: float) -> np.ndarray:
    """Rotation matrix from an axis (need not be normalized) and angle — Rodrigues formula."""
    a = np.asarray(axis, dtype=np.float64).reshape(3)
    norm = np.linalg.norm(a)
    if norm < 1e-12:
        raise ValueError("axis must be non-zero")
    a = a / norm
    c = np.cos(angle_rad)
    s = np.sin(angle_rad)
    C = 1.0 - c
    x, y, z = a
    return np.array(
        [
            [c + x * x * C, x * y * C - z * s, x * z * C + y * s],
            [y * x * C + z * s, c + y * y * C, y * z * C - x * s],
            [z * x * C - y * s, z * y * C + x * s, c + z * z * C],
        ]
    )


def matrix_from_quaternion(q: np.ndarray) -> np.ndarray:
    """Rotation matrix from a (w, x, y, z) quaternion (normalized internally)."""
    w, x, y, z = np.asarray(q, dtype=np.float64) / np.linalg.norm(q)
    return np.array(
        [
            [1 - 2 * (y * y + z * z), 2 * (x * y - z * w), 2 * (x * z + y * w)],
            [2 * (x * y + z * w), 1 - 2 * (x * x + z * z), 2 * (y * z - x * w)],
            [2 * (x * z - y * w), 2 * (y * z + x * w), 1 - 2 * (x * x + y * y)],
        ]
    )


def quaternion_from_matrix(R: np.ndarray) -> np.ndarray:
    """(w, x, y, z) quaternion from a rotation matrix (Shepperd's branch method)."""
    R = np.asarray(R, dtype=np.float64)
    trace = np.trace(R)
    if trace > 0.0:
        s = np.sqrt(trace + 1.0) * 2.0
        w = 0.25 * s
        x = (R[2, 1] - R[1, 2]) / s
        y = (R[0, 2] - R[2, 0]) / s
        z = (R[1, 0] - R[0, 1]) / s
    elif R[0, 0] > R[1, 1] and R[0, 0] > R[2, 2]:
        s = np.sqrt(1.0 + R[0, 0] - R[1, 1] - R[2, 2]) * 2.0
        w = (R[2, 1] - R[1, 2]) / s
        x = 0.25 * s
        y = (R[0, 1] + R[1, 0]) / s
        z = (R[0, 2] + R[2, 0]) / s
    elif R[1, 1] > R[2, 2]:
        s = np.sqrt(1.0 + R[1, 1] - R[0, 0] - R[2, 2]) * 2.0
        w = (R[0, 2] - R[2, 0]) / s
        x = (R[0, 1] + R[1, 0]) / s
        y = 0.25 * s
        z = (R[1, 2] + R[2, 1]) / s
    else:
        s = np.sqrt(1.0 + R[2, 2] - R[0, 0] - R[1, 1]) * 2.0
        w = (R[1, 0] - R[0, 1]) / s
        x = (R[0, 2] + R[2, 0]) / s
        y = (R[1, 2] + R[2, 1]) / s
        z = 0.25 * s
    q = np.array([w, x, y, z])
    return q / np.linalg.norm(q)


def rotation_angle(R: np.ndarray) -> float:
    """Geodesic rotation angle in radians, in [0, pi]."""
    cos = (np.trace(R) - 1.0) / 2.0
    return float(np.arccos(np.clip(cos, -1.0, 1.0)))


def rotation_error_deg(R_est: np.ndarray, R_gt: np.ndarray) -> float:
    """Rotation error in degrees: angle of ``R_gt.T @ R_est``."""
    return float(np.degrees(rotation_angle(np.asarray(R_gt).T @ np.asarray(R_est))))
