"""Real FoundationPose runtime wiring (Stage A-LOCAL bundle; validated on 3090).

This module is the ONLY place that imports the official NVlabs FoundationPose
checkout. It imports lazily and fails with :class:`FoundationPoseRuntimeUnavailable`
on machines without the checkout / GPU — the laptop can import this module and
run its tests, but never executes FoundationPose here (no CUDA, by design).

Wiring contract (from docs/PHASE4_PREFLIGHT.md §5, source-level audit of the
official run_ycb_video.py)::

    est = FoundationPose(model_pts=..., model_normals=..., mesh=...)
    pose = est.register(K, rgb, depth, ob_mask, ob_id, iteration=5)

- model_pts / model_normals / mesh are in METERS (official ycbv reader scales
  the mm PLY by 1e-3 exactly once — we do the same, guarded by
  ``assert_mesh_units_plausible``; double conversion is a known historical bug).
- register() receives NO GT pose and NO initial pose (estimation path).
- If the checked-out official commit changes the API, adjust ONLY this file and
  record the commit hash (see ``repo_commit``); never fork the algorithm.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import numpy as np

from .adapter import FoundationPoseRuntimeUnavailable
from .schema import InferenceInput, assert_mesh_units_plausible


class FoundationPoseRuntime:
    """Lazy wrapper around the official FoundationPose estimater.

    Construction validates paths only; the heavy imports (torch CUDA,
    nvdiffrast, estimater) happen on first use, so this module can be imported
    and unit-tested on a CPU laptop without pretending to run FoundationPose.
    """

    def __init__(self, fp_repo_root: str | Path, checkpoint_dir: str | Path):
        self.fp_repo_root = Path(fp_repo_root).expanduser().resolve()
        self.checkpoint_dir = Path(checkpoint_dir).expanduser().resolve()
        if not (self.fp_repo_root / "estimater.py").is_file():
            raise FoundationPoseRuntimeUnavailable(
                f"official FoundationPose checkout not found at {self.fp_repo_root} "
                "(expecting estimater.py at the repo root; clone https://github.com/NVlabs/FoundationPose)"
            )
        if not self.checkpoint_dir.is_dir():
            raise FoundationPoseRuntimeUnavailable(
                f"checkpoint directory not found: {self.checkpoint_dir} "
                "(refiner 2023-10-28-18-33-37 + scorer 2024-01-11-20-02-45, "
                "see delivery/foundationpose_3090/DOWNLOAD_WEIGHTS.md)"
            )
        self._estimater = None
        self._obj_id: int | None = None

    # ---------------------------------------------------------------- #
    @property
    def repo_commit(self) -> str:
        """Exact checkout commit (recorded into manifests; never guessed)."""
        try:
            out = subprocess.run(
                ["git", "-C", str(self.fp_repo_root), "rev-parse", "HEAD"],
                capture_output=True, text=True, check=True, timeout=30,
            )
            return out.stdout.strip()
        except Exception as exc:  # noqa: BLE001 — recorded as UNKNOWN, never faked
            return f"UNKNOWN ({exc})"

    def _load(self) -> None:
        """Import the official checkout and build the estimater (GPU required)."""
        if self._estimater is not None:
            return
        sys.path.insert(0, str(self.fp_repo_root))
        try:
            import estimater  # type: ignore # noqa: PLC0415 — official checkout
            import helper  # type: ignore # noqa: PLC0415 — official checkout
        except Exception as exc:  # noqa: BLE001
            raise FoundationPoseRuntimeUnavailable(
                f"failed to import the official FoundationPose checkout at "
                f"{self.fp_repo_root}: {exc!r} (GPU/driver/nvdiffrast problem — "
                "run CHECK_ENV.sh; do NOT fall back to CPU or mock)"
            ) from exc
        self._helper = helper

        mesh_path = self._mesh_path_mm
        import trimesh  # type: ignore # noqa: PLC0415 — FoundationPose dependency

        mesh = trimesh.load(str(mesh_path))
        mesh.apply_scale(1e-3)  # BOP PLY mm -> meters, EXACTLY ONCE
        model_pts = np.asarray(mesh.vertices, dtype=np.float16)
        model_normals = np.asarray(mesh.vertex_normals, dtype=np.float16)
        pts_m = np.asarray(mesh.vertices, dtype=np.float64)
        assert_mesh_units_plausible(pts_m)  # meter-band guard (double-conversion tripwire)

        self._estimater = estimater.FoundationPose(
            model_pts=model_pts, model_normals=model_normals, mesh=mesh,
        )
        if not hasattr(self._estimater, "register"):
            raise FoundationPoseRuntimeUnavailable(
                "estimater.FoundationPose has no register(); the official API "
                "differs from the audited commit — adjust this file only and "
                "record the new commit hash"
            )

    # ---------------------------------------------------------------- #
    def load_object(self, obj_id: int, mesh_path_mm: str | Path) -> None:
        """Register the target object (mesh PLY in mm, converted once)."""
        self._obj_id = int(obj_id)
        self._mesh_path_mm = Path(mesh_path_mm)

    def run_register(self, inp: InferenceInput, iteration: int = 5) -> dict:
        """One estimation-path register() call. Returns the same record shape
        as the mock backend (``T_cam_model`` 4x4, meters, camera frame)."""
        self._load()
        assert self._obj_id is not None and inp.obj_id == self._obj_id
        rgb = np.ascontiguousarray(inp.rgb, dtype=np.uint8)
        depth = np.ascontiguousarray(inp.depth_m, dtype=np.float32)
        ob_mask = np.ascontiguousarray(inp.mask.astype(np.uint8))
        pose = self._estimater.register(
            inp.K, rgb, depth, ob_mask, str(inp.obj_id), iteration=iteration,
        )
        T = np.asarray(pose, dtype=np.float64)
        if T.shape != (4, 4):
            raise FoundationPoseRuntimeUnavailable(
                f"register() returned {T.shape}, expected (4, 4) — official API "
                "differs from the audited commit; adjust this file only"
            )
        return {"T_cam_model": T, "backend": "foundationpose", "is_mock": False}
