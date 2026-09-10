"""FoundationPose integration package (Phase 4-B).

Project-side adapter + schemas + evaluator/visualization wrappers + mock
backend. The real FoundationPose runtime is a GPU-side wiring point (see
mock_backend.FoundationPoseBackend); on CPU-only machines only the mock runs.
"""

from .adapter import AdapterConfig, FoundationPoseAdapter
from .exp013 import Exp013Config, load_exp013
from .mock_backend import (
    FoundationPoseBackend,
    FoundationPoseRuntimeUnavailable,
    MockFoundationPoseBackend,
)
from .schema import (
    EvaluationData,
    InferenceInput,
    assert_depth_units_plausible,
    assert_mesh_units_plausible,
    assert_no_gt_pose,
    bop_depth_to_meters,
    bop_mesh_to_meters,
)

__all__ = [
    "AdapterConfig",
    "FoundationPoseAdapter",
    "Exp013Config",
    "load_exp013",
    "FoundationPoseBackend",
    "FoundationPoseRuntimeUnavailable",
    "MockFoundationPoseBackend",
    "EvaluationData",
    "InferenceInput",
    "assert_depth_units_plausible",
    "assert_mesh_units_plausible",
    "assert_no_gt_pose",
    "bop_depth_to_meters",
    "bop_mesh_to_meters",
]
