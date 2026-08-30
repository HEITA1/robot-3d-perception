"""Textured model rendering via Open3D RaycastingScene (P2.1, Plan B).

The BOP YCB-V PLY models natively carry per-vertex texture UVs
(``texture_u/texture_v`` properties) and reference a texture PNG
(``comment TextureFile``), but Open3D's PLY reader ignores those custom
properties. This module parses the (ASCII) PLY directly — using the model's
OWN data, no reconstruction or external assets — and renders templates by
CPU ray casting: each pixel gets appearance (UV -> texture) and a 3D point in
the MODEL frame (meters). No OpenGL / GPU involved.

Coordinate conventions:
  - mesh vertices are stored in mm; everything exposed here is METERS
  - template points are in the MODEL frame (bbox-center origin), the same
    frame the GT poses and PnP object points use
  - each template records its render camera pose T_cam_model so any stored 3D
    point must reproject exactly onto its pixel (self-consistency check).
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import cv2
import numpy as np
import open3d as o3d

MM_TO_M = 1e-3


@dataclass
class TexturedModel:
    """Model frame mesh (meters) + UV + texture + CPU raycasting scene."""

    vertices_m: np.ndarray  # (N, 3) meters
    normals_m: np.ndarray  # (N, 3) vertex normals (unit-ish, from the PLY)
    uvs: np.ndarray  # (N, 2), texture_u/texture_v from the PLY
    faces: np.ndarray  # (M, 3) int64
    texture_bgr: np.ndarray  # (H, W, 3) uint8
    scene: o3d.t.geometry.RaycastingScene

    @classmethod
    def from_ply(cls, ply_path: str | Path, texture_path: str | Path | None = None) -> "TexturedModel":
        ply_path = Path(ply_path)
        if texture_path is None:
            header = ply_path.read_bytes()[:600].decode("ascii", errors="replace")
            for line in header.splitlines():
                if line.startswith("comment TextureFile"):
                    texture_path = ply_path.parent / line.split("TextureFile")[1].strip()
        assert texture_path is not None and Path(texture_path).exists(), "texture file not found"

        with open(ply_path, "rb") as f:
            raw = f.read()
        header_end = raw.index(b"end_header") + len(b"end_header\n")
        header = raw[:header_end].decode("ascii")
        assert "texture_u" in header and "texture_v" in header, "PLY has no texture UV properties"
        n_vertex = int(next(l for l in header.splitlines() if l.startswith("element vertex")).split()[2])
        n_face = int(next(l for l in header.splitlines() if l.startswith("element face")).split()[2])
        lines = raw[header_end:].decode("ascii").splitlines()
        vuv = np.loadtxt(lines[:n_vertex], dtype=np.float64)
        vertices_m = vuv[:, 0:3] * MM_TO_M
        normals_m = vuv[:, 3:6]
        uvs = vuv[:, 6:8]
        faces = np.array([l.split()[1:4] for l in lines[n_vertex:n_vertex + n_face]], dtype=np.int64)

        tm = o3d.t.geometry.TriangleMesh()
        tm.vertex.positions = o3d.core.Tensor(vertices_m.astype(np.float32))
        tm.triangle.indices = o3d.core.Tensor(faces.astype(np.uint32))
        scene = o3d.t.geometry.RaycastingScene()
        scene.add_triangles(tm)
        return cls(vertices_m, normals_m, uvs, faces, cv2.imread(str(texture_path), cv2.IMREAD_COLOR), scene)


@dataclass
class Template:
    """One rendered view: appearance + per-pixel model-frame 3D + camera pose."""

    rgb: np.ndarray  # (H, W, 3) uint8, RGB order
    depth_m: np.ndarray  # (H, W) float32, 0 = no hit
    points_model: np.ndarray  # (N, 3) meters, model frame, valid pixels only
    pixels: np.ndarray  # (N, 2) float, (u, v) of the corresponding pixel
    direction: np.ndarray  # (3,) unit viewing direction (world/model frame)
    T_cam_model: np.ndarray  # (4, 4) render camera pose
    keypoints: list | None = None  # filled by build_rendered_library


def fibonacci_directions(n: int) -> np.ndarray:
    """n deterministic, evenly spread unit directions (Fibonacci lattice)."""
    assert n > 0
    i = np.arange(n) + 0.5
    z = 1.0 - 2.0 * i / n
    phi = (1.0 + 5.0**0.5) / 2.0
    ang = 2.0 * np.pi * i / phi
    r = np.sqrt(np.maximum(0.0, 1.0 - z * z))
    return np.stack([r * np.cos(ang), r * np.sin(ang), z], axis=1)


def _camera_pose(direction: np.ndarray, center: np.ndarray, radius: float):
    """Camera on a sphere around the model center, looking at the center.
    Returns (T_cam_model, eye)."""
    d = np.asarray(direction, dtype=np.float64)
    d = d / np.linalg.norm(d)
    eye = center + d * radius
    z_ax = -d  # camera looks along -z (OpenCV convention)
    up = np.array([0.0, 0.0, 1.0]) if abs(z_ax[2]) < 0.95 else np.array([0.0, 1.0, 0.0])
    x_ax = np.cross(up, z_ax)
    x_ax /= np.linalg.norm(x_ax)
    y_ax = np.cross(z_ax, x_ax)
    T_cam_model = np.eye(4)
    T_cam_model[:3, :3] = np.stack([x_ax, y_ax, z_ax], axis=1).T  # world->cam (R_wc.T)
    T_cam_model[:3, 3] = -(np.stack([x_ax, y_ax, z_ax], axis=1).T @ eye)
    return T_cam_model, eye


def render_view(model: TexturedModel, K: np.ndarray, image_size, direction: np.ndarray,
                radius: float = 0.9, shading: bool = True, shading_ambient: float = 0.4) -> Template:
    """Cast one image worth of rays; return textured appearance + model-frame 3D."""
    H, W = int(image_size[0]), int(image_size[1])
    center = model.vertices_m.mean(axis=0)
    T_cam_model, eye = _camera_pose(direction, center, radius)
    R_wc = T_cam_model[:3, :3].T

    us, vs = np.meshgrid(np.arange(W, dtype=np.float64), np.arange(H, dtype=np.float64))
    dirs_cam = np.stack([(us - K[0, 2]) / K[0, 0], (vs - K[1, 2]) / K[1, 1], np.ones_like(us)], axis=-1)
    dirs = dirs_cam @ R_wc.T
    dirs /= np.linalg.norm(dirs, axis=2, keepdims=True)
    rays = np.concatenate([np.broadcast_to(eye, dirs.shape), dirs], axis=-1).reshape(-1, 6).astype(np.float32)

    ans = model.scene.cast_rays(o3d.core.Tensor(rays))
    t_hit = ans["t_hit"].numpy().reshape(H, W).astype(np.float64)
    prim_ids = ans["primitive_ids"].numpy().reshape(H, W)
    bary = ans["primitive_uvs"].numpy().reshape(H, W, 2)
    hit = np.isfinite(t_hit)

    # per-pixel UV: barycentric mix of the triangle's vertex UVs
    fids = prim_ids[hit]
    b = bary[hit]
    w0 = 1.0 - b[:, 0] - b[:, 1]
    tri = model.faces[fids]
    uv = model.uvs[tri[:, 0]] * w0[:, None] + model.uvs[tri[:, 1]] * b[:, 0:1] + model.uvs[tri[:, 2]] * b[:, 1:2]
    tex = model.texture_bgr
    tx = np.clip((uv[:, 0] * tex.shape[1]).astype(int), 0, tex.shape[1] - 1)
    ty = np.clip(((1.0 - uv[:, 1]) * tex.shape[0]).astype(int), 0, tex.shape[0] - 1)

    rgb = np.zeros((H, W, 3), np.uint8)
    hit_flat = hit.reshape(-1)
    colors = tex[ty, tx][:, ::-1].astype(np.float64)  # BGR -> RGB

    if shading:
        # simple Lambert headlight material (approved fallback): modulate the
        # texture with max(0, n·l), light at the camera; two-sided normals
        nrm = model.normals_m[tri[:, 0]] * w0[:, None] + model.normals_m[tri[:, 1]] * b[:, 0:1] + \
            model.normals_m[tri[:, 2]] * b[:, 1:2]
        l_vec = -dirs.reshape(-1, 3)[np.nonzero(hit_flat)[0]]
        l_vec /= np.linalg.norm(l_vec, axis=1, keepdims=True)
        nrm /= np.linalg.norm(nrm, axis=1, keepdims=True)
        ndl = np.abs(np.sum(nrm * l_vec, axis=1))  # two-sided: |n·l|
        shade = shading_ambient + (1.0 - shading_ambient) * ndl
        colors *= shade[:, None]

    rgb[hit] = np.clip(colors, 0, 255).astype(np.uint8)
    points = (np.broadcast_to(eye, dirs.shape) + dirs * t_hit[..., None]).reshape(-1, 3)[hit_flat]
    pixels = np.stack([us.reshape(-1), vs.reshape(-1)], axis=1)[hit_flat]
    # depth must follow the dataset convention: z-depth along the optical axis,
    # NOT the ray parameter t_hit (they differ for oblique rays)
    z_ax = T_cam_model[:3, 2]
    depth_z = np.zeros((H, W))
    depth_z[hit] = (points - eye) @ z_ax

    return Template(
        rgb=rgb,
        depth_m=np.where(hit, depth_z, 0.0).astype(np.float32),
        points_model=points,
        pixels=pixels,
        direction=np.asarray(direction, dtype=np.float64),
        T_cam_model=T_cam_model,
    )


def build_rendered_library(model: TexturedModel, K: np.ndarray, image_size, n_views: int,
                           radius: float = 0.9, sift=None) -> tuple[list[Template], object]:
    """Render n_views deterministic views and extract SIFT from each.

    Returns (templates, library-like matcher input). Descriptors and their
    model-frame 3D points are concatenated across views; each template keeps
    its own keypoints for debug visualizations.
    """
    assert n_views > 0, "n_views must be positive (anti-false-pass)"
    sift = sift or cv2.SIFT_create()
    templates: list[Template] = []
    descs, pts = [], []
    for direction in fibonacci_directions(n_views):
        tpl = render_view(model, K, image_size, direction, radius=radius)
        kp, desc = sift.detectAndCompute(tpl.rgb, None)
        tpl.keypoints = [] if kp is None else list(kp)
        if desc is None or len(kp) == 0:
            templates.append(tpl)
            continue
        # each descriptor's 3D point = the rendered 3D at its pixel
        ui = np.rint([k.pt[0] for k in kp]).astype(int)
        vi = np.rint([k.pt[1] for k in kp]).astype(int)
        H, W = tpl.depth_m.shape
        px_index = vi * W + ui
        # points/pixels are in row-major valid-pixel order; map pixel -> row
        valid_rows = -np.ones(H * W, dtype=np.int64)
        valid = np.nonzero(tpl.depth_m.reshape(-1) > 0)[0]
        valid_rows[valid] = np.arange(len(valid))
        rows = valid_rows[px_index]
        keep = rows >= 0
        descs.append(desc[keep])
        pts.append(tpl.points_model[rows[keep]])
        templates.append(tpl)
    assert len(templates) > 0
    library = ReferenceLibraryLite(
        descriptors=np.concatenate(descs, axis=0) if descs else np.zeros((0, 128), np.float32),
        points_model=np.concatenate(pts, axis=0) if pts else np.zeros((0, 3)),
    )
    return templates, library


@dataclass
class ReferenceLibraryLite:
    """Descriptors + model-frame points, drop-in compatible with match_query."""

    descriptors: np.ndarray
    points_model: np.ndarray

    def __len__(self) -> int:
        return len(self.descriptors)
