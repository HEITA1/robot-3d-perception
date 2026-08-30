"""Synthetic regression tests for the P2.0 pose building blocks.

The synthetic PnP recovery thresholds (<1e-6) are CORRECTNESS regression tests
for conventions and units only — they are NOT precision expectations for real
data (real-data accuracy is reported as measured, never tuned to a number).
"""

import cv2
import numpy as np
import pytest

from r3p.geometry.camera import make_K, project
from r3p.geometry.se3 import make_T, matrix_from_axis_angle, rotation_error_deg
from r3p.pose.sift_pnp import ReferenceLibrary, match_query, solve_pnp

K = make_K(1066.778, 1067.487, 312.987, 241.311)


def test_pnp_recovers_synthetic_pose_exactly():
    """Zero-noise correspondences: solvePnPRansac output must pass through OUR
    project() with ~zero residual and recover the GT transform. Locks the
    OpenCV <-> r3p SE(3) convention and the meters/pixels units."""
    rng = np.random.default_rng(42)
    t_gt = np.array([0.05, -0.03, 0.80])
    R_gt = matrix_from_axis_angle([1.0, 2.0, 3.0], 0.7)
    T_gt = make_T(R_gt, t_gt)
    pts_model = rng.normal(scale=0.05, size=(300, 3))
    pts_cam = pts_model @ R_gt.T + t_gt
    assert (pts_cam[:, 2] > 0.3).all()

    uv, _ = project(K, pts_cam)
    res = solve_pnp(pts_model, uv, K, min_inliers=10)

    assert res.success
    assert res.n_inliers == 300
    assert res.residual_px < 1e-6
    assert rotation_error_deg(res.T[:3, :3], R_gt) < 1e-6
    assert np.allclose(res.T[:3, 3], t_gt, atol=1e-9)


def test_pnp_returns_failed_result_on_insufficient_data():
    pts3d = np.random.default_rng(0).normal(scale=0.05, size=(3, 3))
    pts2d = np.random.default_rng(1).uniform(50, 500, size=(3, 2))
    res = solve_pnp(pts3d, pts2d, K)
    assert not res.success and res.T is None and res.residual_px == float("inf")

    # enough points but below min_inliers
    pts3d5 = np.random.default_rng(2).normal(scale=0.05, size=(5, 3))
    pts2d5 = np.random.default_rng(3).uniform(50, 500, size=(5, 2))
    res5 = solve_pnp(pts3d5, pts2d5, K, min_inliers=6)
    assert not res5.success


def _textured_image(seed: int) -> np.ndarray:
    """A fixed-seed blob pattern with plenty of SIFT-detectable structure."""
    rng = np.random.default_rng(seed)
    img = (rng.random((240, 320)) * 255).astype(np.uint8)
    img = cv2.GaussianBlur(img, (0, 0), 6)
    for _ in range(40):
        c = (int(rng.integers(10, 310)), int(rng.integers(10, 230)))
        r = int(rng.integers(3, 12))
        shade = int(rng.integers(0, 255))
        cv2.circle(img, c, r, (shade,), -1)
    return img


def test_sift_ratio_matching_on_translated_pair():
    """Mechanical check of the SIFT + knn + Lowe-ratio path in match_query:
    a pure translation of a textured pattern must produce many good matches."""
    img_a = _textured_image(7)
    M = np.float64([[1, 0, 11.0], [0, 1, 6.0]])
    img_b = cv2.warpAffine(img_a, M, (320, 240))

    sift = cv2.SIFT_create()
    kp_a, desc_a = sift.detectAndCompute(img_a, None)
    assert desc_a is not None and len(kp_a) > 50, "SIFT found too few features on the synthetic pattern"

    # a library of zero-3D "features" reusing descriptors from image A
    lib = ReferenceLibrary(
        obj_id=5,
        descriptors=desc_a,
        points_model=np.zeros((len(kp_a), 3)),
    )
    res = match_query(img_b, lib, ratio=0.75, sift=sift)
    assert res.n_query_keypoints > 50
    assert res.n_matches_good > 30, f"ratio test kept only {res.n_matches_good} matches"
    # translation consistency: matched query points should sit ~(+11, +6) from
    # their library counterparts, which live at the un-shifted keypoint locations
    kp_b = {i: kp for i, kp in enumerate(res.query_keypoints)}
    disp = []
    for m in res.matches:
        pa = kp_a[m.trainIdx].pt
        pb = kp_b[m.queryIdx].pt
        disp.append((pb[0] - pa[0], pb[1] - pa[1]))
    disp = np.array(disp)
    assert np.abs(dsp := disp - np.array([11.0, 6.0])).max() < 2.0, (
        f"matched displacement off by {np.abs(dsp).max():.2f} px"
    )
