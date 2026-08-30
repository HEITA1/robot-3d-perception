"""Pinhole camera projection and RGB-D back-projection.

Units: meters, pixels. Skew is ignored (fx, fy, cx, cy only).
Depth convention: z along the optical axis, one depth value per pixel, 0 = invalid.
"""

from __future__ import annotations

import numpy as np


def make_K(fx: float, fy: float, cx: float, cy: float) -> np.ndarray:
    """3x3 intrinsics matrix."""
    return np.array([[fx, 0.0, cx], [0.0, fy, cy], [0.0, 0.0, 1.0]], dtype=np.float64)


def project(K: np.ndarray, points_cam: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """Project (N, 3) camera-frame points to pixel coords (N, 2) [u, v] and depths (N,)."""
    pts = np.asarray(points_cam, dtype=np.float64)
    z = pts[:, 2]
    if np.any(z <= 0):
        raise ValueError("project() requires all points in front of the camera (z > 0)")
    u = K[0, 0] * pts[:, 0] / z + K[0, 2]
    v = K[1, 1] * pts[:, 1] / z + K[1, 2]
    return np.stack([u, v], axis=1), z


def deproject(K: np.ndarray, depth: np.ndarray, mask: np.ndarray | None = None) -> np.ndarray:
    """Back-project a depth image (meters) to an (N, 3) point cloud in camera frame.

    Pixels with depth <= 0 (or outside ``mask``) are skipped. Output rows follow
    row-major pixel order (np.nonzero order).
    """
    depth = np.asarray(depth, dtype=np.float64)
    if mask is None:
        mask = depth > 0
    else:
        mask = np.asarray(mask, dtype=bool) & (depth > 0)
    v, u = np.nonzero(mask)
    z = depth[v, u]
    x = (u - K[0, 2]) * z / K[0, 0]
    y = (v - K[1, 2]) * z / K[1, 1]
    return np.stack([x, y, z], axis=1)
