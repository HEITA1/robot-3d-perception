"""Unit tests for 6D pose metrics, with hand-computed reference values."""

import numpy as np
import pytest

from r3p.datasets.synthetic import sample_box_surface
from r3p.evaluation.metrics import add, adds, compute_all, rotation_error, translation_error
from r3p.geometry.se3 import compose, make_T, matrix_from_axis_angle, rot_z

BOX_SIZE = (0.10, 0.07, 0.05)  # meters


def test_identity_pose_zero_error():
    model = sample_box_surface(BOX_SIZE, 500)
    T = make_T(rot_z(0.3), [0.1, -0.2, 0.8])
    m = compute_all(model, T, T)
    assert m["add"] == pytest.approx(0.0, abs=1e-12)
    assert m["adds"] == pytest.approx(0.0, abs=1e-12)
    assert m["trans"] == pytest.approx(0.0, abs=1e-12)
    assert m["rot_deg"] == pytest.approx(0.0, abs=1e-9)


def test_add_equals_translation_for_pure_shift():
    """For a pure translation, ADD equals ||dt|| exactly (per-point shift cancels)."""
    model = sample_box_surface(BOX_SIZE, 500)
    T_gt = make_T(np.eye(3), [0.0, 0.0, 0.8])
    T_est = make_T(np.eye(3), [0.01, 0.0, 0.8])
    assert add(model, T_est, T_gt) == pytest.approx(0.01, abs=1e-12)
    assert translation_error(T_est, T_gt) == pytest.approx(0.01, abs=1e-12)


def test_adds_invariant_under_exact_symmetry():
    """A 180-degree flip about z maps the box point set to itself: ADD-S ~ 0, ADD large."""
    model = sample_box_surface(BOX_SIZE, 2000)
    T_gt = make_T(matrix_from_axis_angle([1.0, 2.0, 3.0], 0.7), [0.02, -0.01, 0.8])
    R_sym = matrix_from_axis_angle([0.0, 0.0, 1.0], np.pi)
    T_est = compose(T_gt, make_T(R_sym, [0.0, 0.0, 0.0]))  # symmetric flip in object frame
    s = adds(model, T_est, T_gt)
    a = add(model, T_est, T_gt)
    assert s < 1e-6, f"ADD-S should vanish for an exactly symmetric flip, got {s}"
    assert a > 0.01, f"plain ADD should be large under the same flip, got {a}"


def test_rotation_error_value():
    T_gt = make_T(np.eye(3), [0.0, 0.0, 1.0])
    T_est = make_T(rot_z(np.radians(15.0)), [0.0, 0.0, 1.0])
    assert rotation_error(T_est, T_gt) == pytest.approx(15.0, abs=1e-9)
