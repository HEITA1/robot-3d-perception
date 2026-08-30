"""Umeyama rigid alignment + RANSAC (numpy, dependency-free).

Used by the P3.0-S learned-correspondence pipeline to turn predicted
per-point canonical coordinates into a pose hypothesis.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np


def umeyama_alignment(src: np.ndarray, dst: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """Rigid alignment (no scale): dst ~= R @ src + t. Returns (R, t)."""
    src_mean = src.mean(axis=0)
    dst_mean = dst.mean(axis=0)
    src_c = src - src_mean
    dst_c = dst - dst_mean
    H = src_c.T @ dst_c
    U, _, Vt = np.linalg.svd(H)
    d = np.sign(np.linalg.det(Vt.T @ U.T))
    R = Vt.T @ np.diag([1.0, 1.0, d]) @ U.T
    t = dst_mean - R @ src_mean
    return R, t


@dataclass
class RansacResult:
    R: np.ndarray
    t: np.ndarray
    inliers: np.ndarray  # bool (N,)
    inlier_ratio: float
    mean_inlier_residual: float  # meters


def ransac_umeyama(src: np.ndarray, dst: np.ndarray, threshold_m: float = 0.01,
                   iters: int = 200, seed: int = 0) -> RansacResult:
    """RANSAC over minimal 3-point Umeyama samples, then one refinement on the
    inlier set. src/dst are (N, 3) corresponding points."""
    assert len(src) >= 3 and len(src) == len(dst)
    rng = np.random.default_rng(seed)
    n = len(src)
    best = (-1, None, None, None)
    for _ in range(iters):
        idx = rng.choice(n, size=3, replace=False)
        R, t = umeyama_alignment(src[idx], dst[idx])
        resid = np.linalg.norm(src @ R.T + t - dst, axis=1)
        inliers = resid < threshold_m
        if int(inliers.sum()) > best[0]:
            best = (int(inliers.sum()), R, t, inliers)
    _, R, t, inliers = best
    if inliers.sum() >= 3:
        R, t = umeyama_alignment(src[inliers], dst[inliers])
    resid = np.linalg.norm(src @ R.T + t - dst, axis=1)
    inliers = resid < threshold_m
    mean_res = float(resid[inliers].mean()) if inliers.any() else float("inf")
    return RansacResult(R=R, t=t, inliers=inliers,
                        inlier_ratio=float(inliers.mean()), mean_inlier_residual=mean_res)
