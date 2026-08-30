"""Regression tests for the P3.0-S learning building blocks."""

import numpy as np
import pytest

torch = pytest.importorskip("torch", reason="torch (CPU) not installed")

from r3p.learn.coord_net import CoordNet, count_parameters, normalize_points
from r3p.learn.umeyama import ransac_umeyama, umeyama_alignment


def test_umeyama_exact_recovery():
    rng = np.random.default_rng(0)
    R_gt = np.linalg.qr(rng.normal(size=(3, 3)))[0]
    if np.linalg.det(R_gt) < 0:
        R_gt[:, 0] *= -1
    t_gt = rng.uniform(-1, 1, size=3)
    src = rng.normal(size=(200, 3))
    dst = src @ R_gt.T + t_gt
    R, t = umeyama_alignment(src, dst)
    assert np.allclose(R, R_gt, atol=1e-9)
    assert np.allclose(t, t_gt, atol=1e-9)


def test_ransac_umeyama_survives_outliers():
    rng = np.random.default_rng(1)
    R_gt = np.linalg.qr(rng.normal(size=(3, 3)))[0]
    if np.linalg.det(R_gt) < 0:
        R_gt[:, 1] *= -1
    t_gt = np.array([0.2, -0.1, 0.5])
    src_in = rng.normal(size=(70, 3)) * 0.1
    dst_in = src_in @ R_gt.T + t_gt + rng.normal(scale=1e-4, size=(70, 3))
    src_out = rng.normal(size=(30, 3)) * 0.1 + 5.0
    dst_out = rng.normal(size=(30, 3)) * 0.1 - 5.0
    src = np.vstack([src_in, src_out])
    dst = np.vstack([dst_in, dst_out])
    res = ransac_umeyama(src, dst, threshold_m=0.01, iters=300, seed=0)
    assert res.inlier_ratio == pytest.approx(0.7, abs=0.05)
    assert np.allclose(res.R, R_gt, atol=1e-3)
    assert np.allclose(res.t, t_gt, atol=1e-3)
    assert res.mean_inlier_residual < 1e-3


def test_coord_net_shape_and_size():
    net = CoordNet()
    n_params = count_parameters(net)
    assert 30_000 < n_params < 200_000, f"param count {n_params} outside minimal budget"
    x = torch.randn(4, 1024, 6)
    out = net(x)
    assert out.shape == (4, 1024, 3)


def test_coord_net_overfits_tiny_batch():
    """Smoke: the network must be able to drive a fixed regression task down."""
    torch.manual_seed(0)
    net = CoordNet()
    opt = torch.optim.Adam(net.parameters(), lr=1e-2)
    x = torch.randn(1, 64, 6)
    target = torch.randn(1, 64, 3)
    first = last = None
    for step in range(400):
        opt.zero_grad()
        loss = ((net(x) - target) ** 2).mean()
        if step == 0:
            first = float(loss)
        loss.backward()
        opt.step()
        last = float(loss)
    assert last < first * 0.05, f"loss did not collapse: {first:.4f} -> {last:.4f}"


def test_normalize_points_unit_ball():
    rng = np.random.default_rng(2)
    xyz = rng.normal(size=(500, 3)) * [0.02, 0.05, 0.09] + np.array([1.0, 2.0, 3.0])
    n, c, s = normalize_points(xyz)
    assert np.allclose(n.mean(axis=0), 0.0, atol=1e-12)
    assert np.linalg.norm(n, axis=1).max() == pytest.approx(1.0, abs=1e-9)
    # invertible
    assert np.allclose(n * s + c, xyz, atol=1e-12)
