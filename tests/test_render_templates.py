"""P2.1 regression tests: rendered-template geometry self-consistency.

Skipped when the local model subset is absent. These tests lock the render
path (PLY/UV parsing, raycasting, barycentric UV sampling, camera pose) to the
project's SE(3)/pinhole conventions — they are correctness tests, not
appearance-quality claims.
"""

from pathlib import Path

import cv2
import numpy as np
import pytest

from r3p.geometry.camera import make_K, project
from r3p.geometry.se3 import apply as apply_T
from r3p.pose.render_templates import (
    TexturedModel,
    build_rendered_library,
    fibonacci_directions,
    render_view,
)

MODEL_PLY = Path("data/ycbv/models/obj_000005.ply")
pytestmark = pytest.mark.skipif(not MODEL_PLY.exists(), reason="local YCB-V model not present")

K = make_K(1066.778, 1067.487, 312.987, 241.311)
SIZE = (480, 640)


@pytest.fixture(scope="module")
def model():
    return TexturedModel.from_ply(MODEL_PLY)


def test_fibonacci_directions_deterministic_and_normalized():
    d1 = fibonacci_directions(16)
    d2 = fibonacci_directions(16)
    assert np.allclose(d1, d2)
    assert np.allclose(np.linalg.norm(d1, axis=1), 1.0)
    # coverage sanity: directions spread across both hemispheres
    assert (d1[:, 2] > 0).sum() > 0 and (d1[:, 2] < 0).sum() > 0


def test_render_known_view_reprojection_consistency(model):
    """THE check: every stored template 3D point, transformed by the recorded
    render camera pose and projected with the pinhole model, must land exactly
    on its own pixel (catches any ray/pose/convention bug)."""
    tpl = render_view(model, K, SIZE, direction=[0.3, -0.4, 1.0], radius=0.9)
    assert len(tpl.points_model) > 1000, "rendered view has too few hit pixels"
    uv, _ = project(K, apply_T(tpl.T_cam_model, tpl.points_model))
    err = np.abs(uv - tpl.pixels).max()
    assert err < 1e-2, f"template 3D->pixel consistency broken: {err:.4f} px"
    # depth must be physically plausible z-depth around the camera radius
    # (bottle max extent ~0.1 m from center; radius 0.9 -> z in [0.75, 1.05])
    assert tpl.depth_m[tpl.depth_m > 0].min() > 0.7
    assert tpl.depth_m.max() < 1.1


def test_build_rendered_library_anti_zero_and_units(model):
    templates, lib = build_rendered_library(model, K, SIZE, n_views=4, radius=0.9)
    assert len(templates) == 4
    assert len(lib) > 0, "library empty after 4 rendered views (anti-false-pass)"
    assert lib.descriptors.shape[1] == 128
    # model-frame units: points must lie inside the mustard bottle's bbox (~0.2 m)
    assert np.abs(lib.points_model).max() < 0.15
    # descriptors must come from textured pixels: each view contributed keypoints
    n_kp = sum(len(t.keypoints or []) for t in templates)
    assert n_kp > 0 and len(lib) <= n_kp


def test_render_view_is_deterministic(model):
    t1 = render_view(model, K, SIZE, direction=[0.0, 0.0, 1.0], radius=0.9)
    t2 = render_view(model, K, SIZE, direction=[0.0, 0.0, 1.0], radius=0.9)
    assert np.array_equal(t1.rgb, t2.rgb)
    assert np.allclose(t1.points_model, t2.points_model)
