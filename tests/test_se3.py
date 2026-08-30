"""Unit tests for SE(3) transforms and rotation representations."""

import numpy as np
import pytest

from r3p.geometry.se3 import (
    apply,
    compose,
    invert,
    make_T,
    matrix_from_axis_angle,
    matrix_from_quaternion,
    quaternion_from_matrix,
    rot_x,
    rot_z,
    rotation_angle,
    rotation_error_deg,
)

RNG = np.random.default_rng(7)


def random_rotation(rng) -> np.ndarray:
    axis = rng.normal(size=3)
    angle = rng.uniform(0.1, np.pi - 0.1)
    return matrix_from_axis_angle(axis, angle)


def random_pose(rng, t_scale: float = 0.5) -> np.ndarray:
    return make_T(random_rotation(rng), rng.normal(scale=t_scale, size=3))


def test_compose_with_inverse_is_identity():
    T1, T2 = random_pose(RNG), random_pose(RNG)
    assert np.allclose(compose(T1, invert(T1)), np.eye(4), atol=1e-12)
    assert np.allclose(invert(compose(T1, T2)), compose(invert(T2), invert(T1)), atol=1e-12)


def test_apply_known_transform():
    T = make_T(rot_z(np.pi / 2), [1.0, 0.0, 0.0])
    out = apply(T, [[1.0, 0.0, 0.0]])
    assert np.allclose(out, [[1.0, 1.0, 0.0]], atol=1e-12)


def test_rotation_is_orthonormal():
    R = random_rotation(RNG)
    assert np.allclose(R.T @ R, np.eye(3), atol=1e-12)
    assert np.isclose(np.linalg.det(R), 1.0, atol=1e-12)


def test_rotation_angle_known_values():
    assert rotation_angle(np.eye(3)) == pytest.approx(0.0, abs=1e-12)
    assert rotation_angle(rot_x(np.pi / 2)) == pytest.approx(np.pi / 2, abs=1e-12)
    assert rotation_angle(rot_z(np.pi)) == pytest.approx(np.pi, abs=1e-12)


def test_axis_angle_roundtrip_and_axis_fixed():
    for _ in range(20):
        axis = RNG.normal(size=3)
        angle = RNG.uniform(0.05, np.pi - 0.05)
        R = matrix_from_axis_angle(axis, angle)
        assert rotation_angle(R) == pytest.approx(angle, abs=1e-9)
        unit = axis / np.linalg.norm(axis)
        assert np.allclose(R @ unit, unit, atol=1e-9)


def test_quaternion_roundtrip():
    for _ in range(20):
        R = random_rotation(RNG)
        q = quaternion_from_matrix(R)
        assert np.allclose(matrix_from_quaternion(q), R, atol=1e-9)
    # sign ambiguity: q and -q represent the same rotation
    q = quaternion_from_matrix(random_rotation(RNG))
    assert np.allclose(matrix_from_quaternion(-q), matrix_from_quaternion(q), atol=1e-12)


def test_rotation_error_deg():
    R_gt = rot_z(np.radians(30.0))
    R_est = rot_z(np.radians(10.0)) @ R_gt
    assert rotation_error_deg(R_est, R_gt) == pytest.approx(10.0, abs=1e-9)
    assert rotation_error_deg(R_gt, R_gt) == pytest.approx(0.0, abs=1e-12)


def test_make_T_rejects_bad_rotation():
    with pytest.raises(ValueError):
        make_T(np.eye(2), [0.0, 0.0, 0.0])


def test_matrix_from_axis_angle_rejects_zero_axis():
    with pytest.raises(ValueError):
        matrix_from_axis_angle([0.0, 0.0, 0.0], 1.0)
