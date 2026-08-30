"""Unit tests for pinhole projection / back-projection."""

import numpy as np
import pytest

from r3p.geometry.camera import deproject, make_K, project

K = make_K(570.0, 570.0, 320.0, 240.0)


def test_project_center_pixel():
    uv, z = project(K, [[0.0, 0.0, 1.0]])
    assert uv[0, 0] == pytest.approx(320.0, abs=1e-9)
    assert uv[0, 1] == pytest.approx(240.0, abs=1e-9)
    assert z[0] == pytest.approx(1.0)


def test_project_rejects_points_behind_camera():
    with pytest.raises(ValueError):
        project(K, [[0.0, 0.0, -1.0]])


def test_deproject_project_roundtrip():
    """Per-pixel synthetic depth -> deproject -> project must recover pixels and depths."""
    rng = np.random.default_rng(3)
    H, W = 48, 64
    depth = np.zeros((H, W))
    for v in range(8, H - 8, 2):
        for u in range(8, W - 8, 2):
            depth[v, u] = rng.uniform(0.5, 2.0)

    pts = deproject(K, depth)
    assert pts.shape == ((depth > 0).sum(), 3)

    uv, z = project(K, pts)
    v_idx, u_idx = np.nonzero(depth > 0)
    assert np.allclose(uv[:, 0], u_idx, atol=1e-6)
    assert np.allclose(uv[:, 1], v_idx, atol=1e-6)
    assert np.allclose(z, depth[v_idx, u_idx], atol=1e-9)


def test_deproject_respects_mask_and_invalid():
    depth = np.zeros((4, 4))
    depth[1, 2] = 2.0
    depth[2, 1] = -1.0  # invalid depth is skipped
    pts = deproject(K, depth)
    assert pts.shape == (1, 3)
    x = (2 - 320.0) * 2.0 / 570.0
    y = (1 - 240.0) * 2.0 / 570.0
    assert np.allclose(pts[0], [x, y, 2.0], atol=1e-12)


def test_deproject_with_explicit_mask():
    depth = np.zeros((4, 4))
    depth[1, 1] = 1.0
    depth[1, 2] = 1.0
    pts_all = deproject(K, depth)
    assert pts_all.shape == (2, 3)
    pts_masked = deproject(K, depth, mask=np.array([[0] * 4, [0, 1, 0, 0], [0] * 4, [0] * 4], dtype=bool))
    assert pts_masked.shape == (1, 3)
