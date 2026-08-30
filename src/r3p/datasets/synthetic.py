"""Synthetic RGB-D scenes (Phase 0): zero-download pipeline testbed.

Renders a parametric box or cylinder into a depth image with a scatter
z-buffer over densely sampled surface points, plus the standard observation
dict consumed by evaluation and visualization.

Sampling is *structured* (per-face grids / rings), which preserves exact
symmetry groups — the ADD-S symmetry unit test relies on this. Appearance is
a depth-shaded placeholder; this is NOT a photorealistic renderer.
"""

from __future__ import annotations

import numpy as np

from .base import PoseDataset
from ..geometry.camera import make_K, project
from ..geometry.se3 import apply as apply_T
from ..geometry.se3 import make_T, matrix_from_axis_angle


def sample_box_surface(size, n_points: int) -> np.ndarray:
    """Sample points on the 6 faces of an axis-aligned box centered at origin.

    ``size`` = (sx, sy, sz) full extents in meters. Per-face grid resolutions
    are proportional to face area (uniform surface density) and grid
    coordinates are symmetric about 0, so the point set is invariant (up to
    float rounding) under 180-degree rotations about the x/y/z axes.
    """
    sx, sy, sz = (np.asarray(size, dtype=np.float64) / 2.0)
    # each face-pair area is 4*sx*sy (etc.), two faces per axis -> factor 8
    total_area = 8.0 * (sx * sy + sx * sz + sy * sz)
    unit = np.sqrt(max(n_points, 16) / total_area)  # samples per meter per axis
    nx = max(2, int(round(unit * 2 * sx)))
    ny = max(2, int(round(unit * 2 * sy)))
    nz = max(2, int(round(unit * 2 * sz)))

    xs = np.linspace(-sx, sx, nx)
    ys = np.linspace(-sy, sy, ny)
    zs = np.linspace(-sz, sz, nz)

    Yz, Zz = np.meshgrid(ys, zs, indexing="ij")  # for x = +/-sx faces
    Xz, Zx = np.meshgrid(xs, zs, indexing="ij")  # for y = +/-sy faces
    Xy, Yy = np.meshgrid(xs, ys, indexing="ij")  # for z = +/-sz faces

    parts = [
        np.stack([np.full(Yz.size, sx), Yz.ravel(), Zz.ravel()], axis=1),
        np.stack([np.full(Yz.size, -sx), Yz.ravel(), Zz.ravel()], axis=1),
        np.stack([Xz.ravel(), np.full(Xz.size, sy), Zx.ravel()], axis=1),
        np.stack([Xz.ravel(), np.full(Xz.size, -sy), Zx.ravel()], axis=1),
        np.stack([Xy.ravel(), Yy.ravel(), np.full(Xy.size, sz)], axis=1),
        np.stack([Xy.ravel(), Yy.ravel(), np.full(Xy.size, -sz)], axis=1),
    ]
    return np.concatenate(parts, axis=0)


def sample_cylinder_surface(radius: float, height: float, n_points: int, n_ang: int | None = None) -> np.ndarray:
    """Sample points on a cylinder (axis = z, centered at origin).

    Rings x angular samples on the side surface and both caps. Angular
    samples start at 0 with ``endpoint=False``, so the set is invariant under
    rotations of ``2*pi/n_ang`` about z (exact symmetry for ADD-S tests).
    """
    area = 2.0 * np.pi * radius * height + 2.0 * np.pi * radius**2
    unit = np.sqrt(max(n_points, 16) / area)
    if n_ang is None:
        n_ang = max(8, int(round(2.0 * np.pi * unit * radius)))
    n_h = max(2, int(round(unit * height)))
    n_rad = max(2, int(round(unit * radius)))

    angles = np.linspace(0.0, 2.0 * np.pi, n_ang, endpoint=False)
    hs = np.linspace(-height / 2.0, height / 2.0, n_h)
    rhos = np.linspace(0.0, radius, n_rad)

    ca, sa = np.cos(angles), np.sin(angles)

    side = np.stack(
        [radius * ca[None, :].repeat(n_h, 0), radius * sa[None, :].repeat(n_h, 0), hs[:, None].repeat(n_ang, 1)],
        axis=-1,
    ).reshape(-1, 3)

    Rg, Ag = np.meshgrid(rhos, angles, indexing="ij")
    cap_top = np.stack([(Rg * np.cos(Ag)).ravel(), (Rg * np.sin(Ag)).ravel(), np.full(Rg.size, height / 2.0)], axis=1)
    cap_bot = np.stack(
        [(Rg * np.cos(Ag)).ravel(), (Rg * np.sin(Ag)).ravel(), np.full(Rg.size, -height / 2.0)], axis=1
    )
    return np.concatenate([side, cap_top, cap_bot], axis=0)


def render_depth(points_model: np.ndarray, T_cam_model: np.ndarray, K: np.ndarray, image_size) -> np.ndarray:
    """Z-buffer render of sampled model points into a depth image (meters, 0 = empty)."""
    H, W = int(image_size[0]), int(image_size[1])
    pts_cam = apply_T(T_cam_model, points_model)
    uv, z = project(K, pts_cam)
    u = np.rint(uv[:, 0]).astype(np.int64)
    v = np.rint(uv[:, 1]).astype(np.int64)
    valid = (u >= 0) & (u < W) & (v >= 0) & (v < H)

    flat = np.full(H * W, np.inf)
    np.minimum.at(flat, v[valid] * W + u[valid], z[valid])
    depth = flat.reshape(H, W)
    depth[~np.isfinite(depth)] = 0.0
    return depth


def _rgb_from_depth(depth: np.ndarray) -> np.ndarray:
    """Placeholder appearance: grayscale depth ramp (closer = brighter)."""
    valid = depth > 0
    rgb = np.zeros((*depth.shape, 3), dtype=np.uint8)
    if valid.any():
        zmin, zmax = depth[valid].min(), depth[valid].max()
        norm = (depth[valid] - zmin) / max(zmax - zmin, 1e-9)
        g = (255 * (1.0 - norm)).astype(np.uint8)
        rgb[valid] = np.stack([g, g, g], axis=1)
    return rgb


class SyntheticSceneDataset(PoseDataset):
    """A single deterministic synthetic frame (box or cylinder).

    Args mirror ``configs/smoke.yaml``; units are meters.
    """

    def __init__(
        self,
        image_size=(480, 640),
        intrinsics=(570.0, 570.0, 320.0, 240.0),
        model: str = "box",
        model_size=(0.10, 0.07, 0.05),
        gt_rotation_axis=(1.0, 2.0, 3.0),
        gt_rotation_angle_deg: float = 30.0,
        gt_translation=(0.0, 0.0, 0.8),
        n_model_points: int = 2000,
        n_render_points: int = 200000,
        obj_id: str | None = None,
    ):
        if isinstance(intrinsics, dict):
            intrinsics = (intrinsics["fx"], intrinsics["fy"], intrinsics["cx"], intrinsics["cy"])
        self.image_size = (int(image_size[0]), int(image_size[1]))
        self.K = make_K(*intrinsics)
        self.model = model
        self.model_size = tuple(float(s) for s in model_size)
        self.obj_id = obj_id or model
        self.n_render_points = int(n_render_points)

        R = matrix_from_axis_angle(gt_rotation_axis, np.radians(gt_rotation_angle_deg))
        self.gt_pose = make_T(R, gt_translation)

        if model == "box":
            sampler = lambda n: sample_box_surface(self.model_size, n)  # noqa: E731
        elif model == "cylinder":
            sampler = lambda n: sample_cylinder_surface(self.model_size[0], self.model_size[1], n)  # noqa: E731
        else:
            raise ValueError(f"unknown model type: {model!r} (expected 'box' or 'cylinder')")
        self.model_points = sampler(n_model_points)
        self.render_points = sampler(self.n_render_points)

    def __len__(self) -> int:
        return 1

    def __getitem__(self, index: int) -> dict:
        if index != 0:
            raise IndexError("SyntheticSceneDataset contains a single frame (index 0)")
        depth = render_depth(self.render_points, self.gt_pose, self.K, self.image_size).astype(np.float32)
        return {
            "frame_id": "synthetic-0000",
            "rgb": _rgb_from_depth(depth),
            "depth": depth,
            "K": self.K,
            "masks": {self.obj_id: depth > 0},
            "gt_poses": {self.obj_id: self.gt_pose.copy()},
            "model_points": {self.obj_id: self.model_points.copy()},
        }
