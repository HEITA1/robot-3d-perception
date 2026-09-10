"""FoundationPose project-side adapter (Phase 4-B).

Builds validated :class:`InferenceInput` objects from the local BOP subset and
dispatches to a backend. The real FoundationPose runtime is a future wiring
point (GPU hardware); on CPU-only machines only the mock backend may run, and
its outputs are permanently flagged as mock.

BOP -> FoundationPose unit rules (see schema.py):
  depth: raw uint16 * depth_scale(0.1) * 1e-3  -> meters
  mesh : vertices(mm) * 1e-3                   -> meters
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import numpy as np
import open3d as o3d

from .mock_backend import FoundationPoseBackend, FoundationPoseRuntimeUnavailable, MockFoundationPoseBackend
from .schema import (
    EvaluationData,
    InferenceInput,
    assert_depth_units_plausible,
    assert_mesh_units_plausible,
    assert_no_gt_pose,
    bop_depth_to_meters,
    bop_mesh_to_meters,
)


@dataclass
class AdapterConfig:
    data_root: str
    obj_id: int
    mesh_relpath: str
    depth_scale: float          # BOP scene_camera depth_scale (ycbv: 0.1)
    mesh_mm_to_m: float = 1e-3
    diameter_m: float = 0.196463  # obj5 default; override per object


class FoundationPoseAdapter:
    """Project-side adapter: BOP frame -> validated InferenceInput -> backend."""

    def __init__(self, cfg: AdapterConfig):
        self.cfg = cfg

    # -- input preparation -------------------------------------------------
    def prepare_input(self, obs: dict, obj_id: int | None = None) -> InferenceInput:
        """Build InferenceInput from a YcbvBopDataset observation dict.

        The observation contains gt_poses, but prepare_input deliberately does
        NOT copy it into the InferenceInput (structural anti-leakage).

        NOTE: obs["depth"] is ALREADY in meters (YcbvBopDataset contract,
        Phase 1 verified). It must NOT be converted again -- the unit
        assertion below is exactly what catches such double conversion.
        """
        obj_id = obj_id or self.cfg.obj_id
        # NOTE: obs["model_points"] are ALREADY meters (dataset contract,
        # Phase 1 verified: max pairwise distance == models_info diameter).
        # Do NOT convert again -- the unit assertion catches double conversion.
        mesh_m = np.asarray(obs["model_points"][obj_id], dtype=np.float64)
        # model_points are surface samples; for the runtime the adapter also
        # provides the full mesh vertices via mesh_vertices_m (same units).
        depth_m = np.asarray(obs["depth"], dtype=np.float32)
        assert_depth_units_plausible(depth_m)
        mask = obs["masks"][obj_id]
        inp = InferenceInput(
            rgb=np.ascontiguousarray(obs["rgb"]),
            depth_m=depth_m.astype(np.float32),
            K=np.asarray(obs["K"], dtype=np.float64),
            mask=np.asarray(mask, dtype=bool),
            obj_id=int(obj_id),
            mesh_m=mesh_m,
        )
        problems = self.validate_input(inp)
        if problems:
            raise ValueError("invalid inference input: " + "; ".join(problems))
        return inp

    def mesh_vertices_m(self, data_root: str | Path) -> np.ndarray:
        """Full mesh vertices (meters) for the FoundationPose runtime, with an
        explicit unit-plausibility assertion (mm kept as mm fails loudly)."""
        mesh = o3d.io.read_triangle_mesh(str(Path(data_root) / self.cfg.mesh_relpath))
        verts_m = bop_mesh_to_meters(np.asarray(mesh.vertices))
        assert_mesh_units_plausible(verts_m)
        return verts_m

    def evaluation_data(self, obs: dict, obj_id: int | None = None) -> EvaluationData:
        """Evaluation-side bundle (GT pose + canonical points + diameter).
        Never pass this to a backend."""
        obj_id = obj_id or self.cfg.obj_id
        return EvaluationData(
            gt_pose=np.asarray(obs["gt_poses"][obj_id], dtype=np.float64),
            model_points_m=np.asarray(obs["model_points"][obj_id], dtype=np.float64),
            diameter_m=self.cfg.diameter_m,
        )

    # -- validation --------------------------------------------------------
    def validate_input(self, inp: InferenceInput) -> list[str]:
        problems = list(inp.validate())
        try:
            assert_depth_units_plausible(inp.depth_m)
        except AssertionError as e:
            problems.append(str(e))
        try:
            assert_mesh_units_plausible(inp.mesh_m)
        except AssertionError as e:
            problems.append(str(e))
        try:
            assert_no_gt_pose(inp.to_manifest())
        except AssertionError as e:
            problems.append(f"anti-leakage: {e}")
        return problems

    # -- backend dispatch ----------------------------------------------------
    def run(self, inp: InferenceInput, backend: str = "mock",
            fp_repo_root: str | None = None, fp_checkpoint_dir: str | None = None) -> dict:
        assert_no_gt_pose(inp.to_manifest())
        if backend == "mock":
            return MockFoundationPoseBackend().run_register(inp)
        if backend == "foundationpose":
            return FoundationPoseBackend(fp_repo_root, fp_checkpoint_dir).run_register(inp)
        raise ValueError(f"unknown backend: {backend!r} (use 'mock' or 'foundationpose')")
