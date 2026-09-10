"""EXP-013 frozen configuration: FoundationPose feasibility (model-based register).

Folder naming follows the Phase 4 convention (fp_exp004_feasibility);
the EXPERIMENT_LOG entry is EXP-013 (project log is at EXP-012).

This config is FROZEN: frames / object / scene / threshold / mask_source /
metric come from the approved Phase 4 plan and match P2.4 / P3.1 subsets for
same-frame comparability. Changes require explicit user approval.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class Exp013Config:
    experiment_id: str = "fp_exp004_feasibility"
    log_id: str = "EXP-013"
    method: str = "FoundationPose"
    mode: str = "register"            # estimation path; NO initial pose
    backend: str = "mock"             # laptop default; "foundationpose" only on 3090
    object_id: int = 5                # 006_mustard_bottle
    scene_id: int = 50
    frame_ids: tuple = (620, 653, 721, 1044, 1113)
    mask_source: str = "bop_gt_mask_visib"   # oracle mask: DECLARED controlled condition
    initialization_mode: str = "none"        # register() needs no initial pose
    success_metric: str = "add"              # asymmetric object -> ADD
    diameter_mm: float = 196.463
    threshold_mm: float = 19.6463            # 0.1 * diameter
    depth_scale: float = 0.1
    mesh_relpath: str = "models/obj_000005.ply"
    data_root: str = "data/ycbv"
    output_root: str = "outputs/phase4_foundationpose"
    foundationpose_repo_commit: str = "PENDING_3090"
    checkpoint_dir: str = "PENDING_3090"     # weights/ with refiner + scorer
    environment: str = "PENDING_3090"

    def to_manifest(self, **extra) -> dict:
        m = {
            "experiment_id": self.experiment_id,
            "log_id": self.log_id,
            "method": self.method,
            "mode": self.mode,
            "backend": self.backend,
            "object_id": self.object_id,
            "scene_id": self.scene_id,
            "frame_ids": list(self.frame_ids),
            "mask_source": self.mask_source,
            "initialization_mode": self.initialization_mode,
            "success_metric": self.success_metric,
            "threshold_mm": self.threshold_mm,
            "diameter_mm": self.diameter_mm,
            "depth_scale": self.depth_scale,
            "mesh": self.mesh_relpath,
            "mesh_unit": "meters",
            "depth_unit": "meters",
            "gt_pose_usage": "evaluation_only",
            "foundationpose_repo_commit": self.foundationpose_repo_commit,
            "checkpoint_dir": self.checkpoint_dir,
            "environment": self.environment,
        }
        m.update(extra)
        return m


def load_exp013() -> Exp013Config:
    return Exp013Config()
