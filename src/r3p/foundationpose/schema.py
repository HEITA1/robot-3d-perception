"""Schemas and unit rules for the FoundationPose integration (Phase 4-B).

Structural anti-leakage guarantee: :class:`InferenceInput` has NO gt_pose
field and cannot hold one (frozen dataclass with fixed slots). The GT pose
lives only in :class:`EvaluationData`. ``to_manifest`` serializes the
inference side WITHOUT any evaluation data, and :func:`assert_no_gt_pose`
recursively rejects any ``gt_pose`` key -- tested in test_foundationpose_adapter.

Unit rules (explicit, asserted -- never implicit):
  BOP depth raw (uint16) --[* depth_scale * 1e-3]--> meters
      ycbv: depth_scale = 0.1  ->  one raw unit = 0.1 mm
  BOP mesh vertices (mm) --[* 1e-3]--> meters
Everything crossing into FoundationPose runtime space is meters.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np

MM_TO_M = 1e-3


def bop_depth_to_meters(raw_depth: np.ndarray, depth_scale: float) -> np.ndarray:
    """BOP uint16 depth -> meters (raw * depth_scale * 1e-3)."""
    return raw_depth.astype(np.float32) * np.float32(depth_scale * 1e-3)


def bop_mesh_to_meters(vertices_mm: np.ndarray) -> np.ndarray:
    """BOP mesh vertices (mm) -> meters. The 1000x error this guards against
    is caught by :func:`assert_mesh_units_plausible` (bbox extent check)."""
    return np.asarray(vertices_mm, dtype=np.float64) * MM_TO_M


def assert_depth_units_plausible(depth_m: np.ndarray) -> None:
    """Real frames in our subset are 0.5-5 m from the camera. A mm/m mix-up
    produces depths ~1000x outside this band. Uses p5/p95 (not min/max/p1)
    because real masks contain a small tail of near-zero edge junk pixels."""
    valid = depth_m[depth_m > 0]
    assert valid.size > 0, "depth has no valid pixels"
    lo = float(np.percentile(valid, 5))
    hi = float(np.percentile(valid, 95))
    assert 0.05 < lo and hi < 10.0, f"depth values outside meter band: [p5={lo}, p95={hi}] m"


def assert_mesh_units_plausible(mesh_m: np.ndarray) -> None:
    """Object meshes in our subset have max extent 0.1-0.3 m. A mm value kept
    as meters (or cm confusion) lands 3-4 orders of magnitude outside."""
    extent = float((mesh_m.max(axis=0) - mesh_m.min(axis=0)).max())
    assert 0.02 < extent < 1.0, f"mesh extent {extent:.3f} m outside meter band"


@dataclass(frozen=True)
class InferenceInput:
    """Everything FoundationPose register() receives. Deliberately EXCLUDES
    the GT pose (see module docstring)."""

    rgb: np.ndarray            # (H, W, 3) uint8, RGB order
    depth_m: np.ndarray        # (H, W) float32, meters, 0 = invalid
    K: np.ndarray              # (3, 3) float64
    mask: np.ndarray           # (H, W) bool, oracle mask_visib (declared condition)
    obj_id: int
    mesh_m: np.ndarray         # (N, 3) mesh vertices, METERS, model frame
    mask_source: str = "bop_gt_mask_visib"  # declared controlled condition

    def validate(self) -> list[str]:
        problems = []
        if self.rgb.ndim != 3 or self.rgb.shape[2] != 3:
            problems.append(f"rgb must be (H, W, 3), got {self.rgb.shape}")
        if self.depth_m.shape != self.rgb.shape[:2]:
            problems.append(f"depth shape {self.depth_m.shape} != rgb HxW {self.rgb.shape[:2]}")
        if self.mask.shape != self.rgb.shape[:2]:
            problems.append(f"mask shape {self.mask.shape} != rgb HxW {self.rgb.shape[:2]}")
        if self.K.shape != (3, 3):
            problems.append(f"K must be (3, 3), got {self.K.shape}")
        if not np.isfinite(self.K).all():
            problems.append("K contains non-finite values")
        if self.mask.sum() < 100:
            problems.append(f"mask too small: {int(self.mask.sum())} px")
        if self.mesh_m.ndim != 2 or self.mesh_m.shape[1] != 3 or len(self.mesh_m) < 100:
            problems.append(f"mesh must be (N>=100, 3), got {self.mesh_m.shape}")
        return problems

    def to_manifest(self) -> dict:
        """Serializable inference manifest: paths/ids/params only -- never
        arrays, never GT. Kept narrow on purpose."""
        return {
            "obj_id": self.obj_id,
            "mask_source": self.mask_source,
            "depth_unit": "meters",
            "mesh_unit": "meters",
            "K": self.K.round(6).tolist(),
        }


@dataclass(frozen=True)
class EvaluationData:
    """Evaluation-side information. NEVER passed to a runtime backend."""

    gt_pose: np.ndarray   # (4, 4) camera-frame SE(3), meters
    model_points_m: np.ndarray  # (N, 3) canonical points for ADD/ADD-S
    diameter_m: float

    def to_manifest(self) -> dict:
        return {"has_gt_pose": True, "diameter_m": self.diameter_m}


def assert_no_gt_pose(obj) -> None:
    """Recursively reject any key that HOLDS a GT pose in manifests /
    serialized inference inputs. Documentation-only keys (e.g.
    ``gt_pose_usage: "evaluation_only"``) are allowed; keys named
    ``gt_pose`` / ``*_gt_pose`` are not."""
    if isinstance(obj, dict):
        for k, v in obj.items():
            kl = str(k).lower()
            assert kl != "gt_pose" and not kl.endswith("_gt_pose"), \
                f"gt_pose leaked into manifest key: {k}"
            assert_no_gt_pose(v)
    elif isinstance(obj, (list, tuple)):
        for v in obj:
            assert_no_gt_pose(v)
