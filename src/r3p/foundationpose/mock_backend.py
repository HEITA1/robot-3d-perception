"""Mock backend for the FoundationPose integration (Phase 4-B).

Returns a DETERMINISTIC, clearly-marked mock pose so the project-side chain
(BOP -> adapter -> validation -> backend -> evaluator -> visualization ->
manifest) can be exercised on a CPU-only laptop. It performs NO pose
estimation: the rotation is identity and the translation is the masked-depth
centroid (a GT-free depth heuristic, chosen only so the output is a valid
SE(3) object for the downstream stages).

Guardrails:
  - every result dict carries backend="mock" and is_mock=True
  - run_foundationpose_exp013 refuses to write mock output into the official
    results location (mock runs go to .../mock_smoke/)
"""

from __future__ import annotations

import numpy as np

from .schema import InferenceInput


class MockFoundationPoseBackend:
    backend = "mock"

    def run_register(self, inp: InferenceInput) -> dict:
        valid = inp.depth_m > 0
        assert valid.any(), "no valid depth for mock backend"
        z = inp.depth_m[valid]
        ys, xs = np.nonzero(valid)
        # GT-free depth-centroid translation (same heuristic class as
        # FoundationPose's guess_translation; IDENTITY rotation by design).
        cx = float((xs * z).sum() / z.sum())
        cy = float((ys * z).sum() / z.sum())
        cz = float(np.median(z))
        x = (cx - inp.K[0, 2]) * cz / inp.K[0, 0]
        y = (cy - inp.K[1, 2]) * cz / inp.K[1, 1]
        T = np.eye(4)
        T[:3, 3] = [x, y, cz]
        return {
            "T_cam_model": T,
            "backend": self.backend,
            "is_mock": True,
            "note": "MOCK RESULT - identity rotation + depth-centroid translation; "
                    "never a FoundationPose estimate",
        }


class FoundationPoseRuntimeUnavailable(RuntimeError):
    """Raised when the real backend is requested but the runtime is absent
    (no GPU / no nvdiffrast / no FoundationPose source / no checkpoints)."""


class FoundationPoseBackend:
    """Placeholder for the real runtime integration on the 3090 machine.

    Wiring point (Phase 4 execution, on GPU hardware):
      1. sys.path / import of the official NVlabs/FoundationPose checkout
      2. construct estimater.FoundationPose(model_pts, model_normals, mesh, ...)
      3. call est.register(K=..., rgb=..., depth=..., ob_mask=...)
      4. return {"T_cam_model": pose, "backend": "foundationpose", "is_mock": False}

    Until that wiring exists on GPU hardware this backend refuses to run --
    it must never silently fall back to CPU or to the mock.
    """

    backend = "foundationpose"

    def __init__(self, repo_root: str | None = None, checkpoint_dir: str | None = None):
        self.repo_root = repo_root
        self.checkpoint_dir = checkpoint_dir

    def run_register(self, inp: InferenceInput) -> dict:
        raise FoundationPoseRuntimeUnavailable(
            "FoundationPose runtime is not available on this machine "
            "(requires NVIDIA GPU + CUDA + nvdiffrast + official repo + checkpoints). "
            "Run scripts/foundationpose_env_check.py on the 3090 machine and follow "
            "docs/PHASE4_PREFLIGHT.md section 9. This backend never falls back to "
            "CPU or to the mock."
        )
