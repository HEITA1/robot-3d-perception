"""Unit tests for the synthetic scene dataset (shapes, units, symmetry, roundtrip)."""

import numpy as np
import pytest
from scipy.spatial.distance import cdist

from r3p.datasets.synthetic import (
    SyntheticSceneDataset,
    render_depth,
    sample_box_surface,
    sample_cylinder_surface,
)
from r3p.geometry.camera import deproject, project
from r3p.geometry.se3 import make_T


def test_box_surface_symmetry():
    """The box point set must be invariant under a 180-degree flip about z."""
    pts = sample_box_surface((0.1, 0.07, 0.05), 500)
    S = np.diag([-1.0, -1.0, 1.0])
    d = cdist(pts, pts @ S.T)
    assert d.min(axis=1).max() < 1e-9


def test_cylinder_surface_symmetry():
    pts = sample_cylinder_surface(0.04, 0.1, 500, n_ang=32)
    ang = 2.0 * np.pi / 32.0
    R = np.array(
        [
            [np.cos(ang), -np.sin(ang), 0.0],
            [np.sin(ang), np.cos(ang), 0.0],
            [0.0, 0.0, 1.0],
        ]
    )
    d = cdist(pts, pts @ R.T)
    assert d.min(axis=1).max() < 1e-9


def test_dataset_observation_contract():
    ds = SyntheticSceneDataset()
    assert len(ds) == 1
    obs = ds[0]
    H, W = 480, 640
    assert obs["rgb"].shape == (H, W, 3) and obs["rgb"].dtype == np.uint8
    assert obs["depth"].shape == (H, W) and obs["depth"].dtype == np.float32
    assert obs["K"].shape == (3, 3)
    assert obs["masks"]["box"].dtype == np.bool_
    T = obs["gt_poses"]["box"]
    assert T.shape == (4, 4) and np.allclose(T[3], [0.0, 0.0, 0.0, 1.0])
    assert obs["model_points"]["box"].shape[1] == 3
    with pytest.raises(IndexError):
        ds[1]


def test_render_depth_reprojection_roundtrip():
    """Every valid rendered pixel must reproject exactly from its deprojected 3D point."""
    ds = SyntheticSceneDataset(n_render_points=50000)
    obs = ds[0]
    depth = obs["depth"]
    mask = depth > 0
    assert mask.sum() > 1000, "object must be visibly rendered"

    cloud = deproject(obs["K"], depth)
    uv, z = project(obs["K"], cloud)
    v_idx, u_idx = np.nonzero(mask)
    assert np.allclose(uv[:, 0], u_idx, atol=1e-6)
    assert np.allclose(uv[:, 1], v_idx, atol=1e-6)
    assert np.allclose(z, depth[v_idx, u_idx], atol=1e-6)


def test_render_depth_zbuffer_keeps_closest():
    """Two overlapping model points at different depths: the depth image keeps the near one."""
    K = np.array([[100.0, 0.0, 5.0], [0.0, 100.0, 5.0], [0.0, 0.0, 1.0]])
    pts = np.array([[0.0, 0.0, 1.0], [0.0, 0.0, 2.0]])  # both project to pixel (5, 5)
    depth = render_depth(pts, make_T(np.eye(3), [0.0, 0.0, 0.0]), K, (10, 10))
    assert depth[5, 5] == pytest.approx(1.0)
    assert depth.sum() == pytest.approx(1.0)
