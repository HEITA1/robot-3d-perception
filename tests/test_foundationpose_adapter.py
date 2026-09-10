"""Tests for the FoundationPose integration (Phase 4-B).

Real-data tests are skipped automatically when the local subset is absent.
"""

from pathlib import Path

import numpy as np
import pytest

from r3p.foundationpose import AdapterConfig, EvaluationData, Exp013Config, FoundationPoseAdapter, FoundationPoseBackend, FoundationPoseRuntimeUnavailable, InferenceInput, MockFoundationPoseBackend, assert_depth_units_plausible, assert_mesh_units_plausible, assert_no_gt_pose, bop_depth_to_meters, bop_mesh_to_meters
from r3p.foundationpose.evaluator import evaluate_fp_result, save_gt_pred_overlay
from r3p.geometry.se3 import make_T, matrix_from_axis_angle

DATA_ROOT = Path("data/ycbv")
HAS_DATA = (DATA_ROOT / "models" / "obj_000005.ply").is_file() and (DATA_ROOT / "test" / "000050").is_dir()

CFG = FoundationPoseAdapter(AdapterConfig(
    data_root="data/ycbv", obj_id=5, mesh_relpath="models/obj_000005.ply",
    depth_scale=0.1, diameter_m=0.196463,
))


# ---------------------------------------------------------------- units ----
def test_bop_depth_conversion_units():
    """depth_scale=0.1: raw 10000 must be exactly 1.0 m (the mm/m mix-up this
    project guards against would give 10000 m or 10 m)."""
    raw = np.array([[10000, 5000]], dtype=np.uint16)
    out = bop_depth_to_meters(raw, depth_scale=0.1)
    assert out.dtype == np.float32
    assert out[0, 0] == pytest.approx(1.0, abs=1e-6)
    assert out[0, 1] == pytest.approx(0.5, abs=1e-6)


def test_bop_mesh_conversion_units():
    """mm -> m: a 100 mm edge becomes 0.1 m, not 100 m."""
    verts_mm = np.array([[0.0, 0.0, 0.0], [100.0, 0.0, 0.0]])
    out = bop_mesh_to_meters(verts_mm)
    assert np.abs(out[1, 0] - 0.1) < 1e-12


def test_unit_assertions_catch_mixups():
    good = np.random.default_rng(0).normal(scale=0.03, size=(200, 3)) + [0.1, 0, 0.8]
    bop_mesh_to_meters(good * 1e3)  # mm input is the intended usage: fine
    with pytest.raises(AssertionError):
        # meter values fed through the mm->m conversion again -> 0.1mm cloud
        assert_mesh_units_plausible(bop_mesh_to_meters(good))
    bad_depth = np.full((10, 10), 800.0, dtype=np.float32)  # 800 "m" = mm kept
    bad_depth[2:8, 2:8] = 0.8
    with pytest.raises(AssertionError):
        from r3p.foundationpose import assert_depth_units_plausible
        assert_depth_units_plausible(bad_depth)


# ---------------------------------------------------------- anti-leakage ----
def test_inference_input_has_no_gt_pose_field():
    fields = {f.name for f in InferenceInput.__dataclass_fields__.values()}
    assert "gt_pose" not in fields
    assert fields == {"rgb", "depth_m", "K", "mask", "obj_id", "mesh_m", "mask_source"}


def test_manifest_rejects_gt_pose_key():
    with pytest.raises(AssertionError):
        assert_no_gt_pose({"obj_id": 5, "gt_pose": np.eye(4)})
    with pytest.raises(AssertionError):
        assert_no_gt_pose({"obj_id": 5, "eval_gt_pose": np.eye(4)})
    # documentation-only key (declared usage, no pose data) is allowed
    assert_no_gt_pose({"gt_pose_usage": "evaluation_only"})


@pytest.mark.skipif(not HAS_DATA, reason="local YCB-V subset not present")
def test_prepare_input_strips_gt_pose():
    from r3p.datasets.ycbv_bop import YcbvBopDataset

    ds = YcbvBopDataset(DATA_ROOT, obj_ids=(5,), scene_ids=[50], load_masks=True)
    obs = ds[0]
    assert "gt_poses" in obs  # the raw observation does carry GT...
    inp = CFG.prepare_input(obs, obj_id=5)
    manifest = inp.to_manifest()
    assert "gt_pose" not in manifest
    import json

    assert "gt_pose" not in json.dumps(manifest)  # serialized form is clean
    assert inp.mask_source == "bop_gt_mask_visib"


# ------------------------------------------------- EXP-013 frozen config ----
def test_exp013_config_frozen_values():
    c = Exp013Config()
    assert c.object_id == 5 and c.scene_id == 50
    assert c.frame_ids == (620, 653, 721, 1044, 1113)
    assert c.mask_source == "bop_gt_mask_visib"
    assert c.initialization_mode == "none"
    assert c.success_metric == "add"
    assert c.threshold_mm == pytest.approx(19.65, abs=0.01)
    assert c.depth_scale == 0.1
    assert c.backend == "mock"  # laptop default
    m = c.to_manifest()
    assert m["gt_pose_usage"] == "evaluation_only"
    assert_no_gt_pose(m)


# ------------------------------------------------- evaluator integration ----
def test_evaluate_fp_result_matches_compute_all():
    from r3p.evaluation.metrics import compute_all

    rng = np.random.default_rng(0)
    pts = rng.normal(scale=0.05, size=(300, 3))
    T_gt = make_T(matrix_from_axis_angle([1, 2, 3], 0.5), [0.1, 0, 0.8])
    T_pred = make_T(matrix_from_axis_angle([1, 2, 3], 0.55), [0.1, 0.01, 0.79])
    ev = EvaluationData(gt_pose=T_gt, model_points_m=pts, diameter_m=0.196463)
    out = evaluate_fp_result(T_pred, ev)
    ref = compute_all(pts, T_pred, T_gt)
    assert out["add_mm"] == pytest.approx(ref["add"] * 1e3, abs=1e-3)
    assert out["adds_mm"] == pytest.approx(ref["adds"] * 1e3, abs=1e-3)
    assert out["translation_error_mm"] == pytest.approx(ref["trans"] * 1e3, abs=1e-3)
    assert out["rotation_error_deg"] == pytest.approx(ref["rot_deg"], abs=1e-3)
    assert out["threshold_mm"] == pytest.approx(19.6463, abs=0.01)
    # exact GT pose must be a success with ~0 error
    ok = evaluate_fp_result(T_gt, ev)
    assert ok["success"] and ok["add_mm"] < 1e-6


# ------------------------------------------------------- mock end-to-end ----
@pytest.mark.skipif(not HAS_DATA, reason="local YCB-V subset not present")
def test_mock_end_to_end_pipeline(tmp_path):
    """BOP -> adapter -> validation -> mock backend -> evaluator -> viz -> manifest."""
    from r3p.datasets.ycbv_bop import YcbvBopDataset

    ds = YcbvBopDataset(DATA_ROOT, obj_ids=(5,), scene_ids=[50], load_masks=True)
    obs = ds[0]
    inp = CFG.prepare_input(obs, obj_id=5)
    assert not CFG.validate_input(inp)

    result = CFG.run(inp, backend="mock")
    assert result["is_mock"] is True and result["backend"] == "mock"

    ev = CFG.evaluation_data(obs, obj_id=5)
    out = evaluate_fp_result(result["T_cam_model"], ev)
    assert isinstance(out["success"], bool)

    viz = save_gt_pred_overlay(inp.rgb, inp.K, ev.model_points_m, ev.gt_pose,
                               result["T_cam_model"], tmp_path / "mock_overlay.png",
                               title="MOCK")
    assert viz.exists() and viz.stat().st_size > 0


def test_mock_backend_is_deterministic_and_gt_free():
    rng = np.random.default_rng(1)
    depth = np.zeros((60, 80), dtype=np.float32)
    depth[20:40, 30:50] = 0.8
    mask = depth > 0
    K = np.array([[100.0, 0, 40.0], [0, 100.0, 30.0], [0, 0, 1.0]])
    mesh = rng.normal(scale=0.03, size=(200, 3))
    a = MockFoundationPoseBackend().run_register(
        InferenceInput(rgb=np.zeros((60, 80, 3), np.uint8), depth_m=depth, K=K,
                       mask=mask, obj_id=5, mesh_m=mesh))
    b = MockFoundationPoseBackend().run_register(
        InferenceInput(rgb=np.zeros((60, 80, 3), np.uint8), depth_m=depth, K=K,
                       mask=mask, obj_id=5, mesh_m=mesh))
    assert np.array_equal(a["T_cam_model"], b["T_cam_model"])
    assert a["is_mock"] and a["backend"] == "mock"


# -------------------------------------------------- real backend refusal ----
def test_foundationpose_backend_refuses_without_runtime():
    with pytest.raises(FoundationPoseRuntimeUnavailable):
        FoundationPoseBackend().run_register(
            InferenceInput(rgb=np.zeros((8, 8, 3), np.uint8),
                           depth_m=np.full((8, 8), 0.8, np.float32),
                           K=np.eye(3), mask=np.ones((8, 8), bool),
                           obj_id=5, mesh_m=np.random.default_rng(0).normal(size=(200, 3))))
