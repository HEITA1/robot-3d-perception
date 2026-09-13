"""W2-3 / EXP-014 unified baseline evaluation guards.

- Config fairness: configs/w2_3_multibaseline.yaml must carry IDENTICAL frozen
  icp/selection/success parameters to configs/p2_4.yaml (EXP-006) — same
  baseline, only objects/frames change.
- Aggregator convention: scripts/w2_3_unified_table.py medians must follow the
  EXP-006 metrics.json convention (every frame that produced a metric value,
  solver-gate failures included), and anchor rows must reproduce the frozen
  headline numbers bit-exactly when historical outputs are present.
"""

from __future__ import annotations

import csv
import importlib.util
from pathlib import Path

import pytest
import yaml

W2_3_CONFIG = Path("configs/w2_3_multibaseline.yaml")
P2_4_CONFIG = Path("configs/p2_4.yaml")
P24_RUN = Path("outputs/p2_4/20260830-161911")
W2_3_RUNS = Path("outputs/w2_3")

EXPECTED_OBJECTS = {2: ("add", 50), 6: ("adds", 48), 10: ("add", 50), 14: ("add", 48), 15: ("add", 50)}


def _load(path: Path) -> dict:
    with open(path, encoding="utf-8") as f:
        return yaml.safe_load(f)


def _load_aggregator():
    spec = importlib.util.spec_from_file_location(
        "w2_3_unified_table", Path("scripts/w2_3_unified_table.py")
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_w2_3_config_uses_frozen_p2_4_parameters():
    w2_3, p2_4 = _load(W2_3_CONFIG), _load(P2_4_CONFIG)
    for section in ("icp", "selection", "success"):
        assert w2_3[section] == p2_4[section], f"frozen section {section} diverged from EXP-006"
    assert w2_3["data"]["root"] == p2_4["data"]["root"]


def test_w2_3_config_objects_and_pre_registered_metric():
    cfg = _load(W2_3_CONFIG)
    objects = {o["obj_id"]: o for o in cfg["objects"]}
    assert set(objects) == set(EXPECTED_OBJECTS)
    for obj_id, (metric, scene) in EXPECTED_OBJECTS.items():
        o = objects[obj_id]
        assert o["success_metric"] == metric, f"obj{obj_id} metric must stay pre-registered"
        assert o["eval_scene"] == scene
        assert o["n_frames"] == 10
        assert o["mesh"].startswith("models/obj_")


def test_unified_table_aggregation_convention(tmp_path):
    """Medians over every frame with metric values (gate failures included,
    insufficient frames excluded); success counts pose_success; N counts all."""
    agg = _load_aggregator()
    rows = [
        {"failure_tag": "success", "pose_success": "1", "solver_success": "1",
         "add_mm": "1.0", "adds_mm": "0.9", "trans_mm": "0.5", "rot_deg": "0.4"},
        {"failure_tag": "success", "pose_success": "1", "solver_success": "1",
         "add_mm": "3.0", "adds_mm": "2.8", "trans_mm": "1.5", "rot_deg": "1.2"},
        {"failure_tag": "icp_no_converge", "pose_success": "0", "solver_success": "0",
         "add_mm": "50.0", "adds_mm": "4.0", "trans_mm": "9.0", "rot_deg": "90.0"},
        {"failure_tag": "insufficient_observation", "pose_success": "0", "solver_success": "0",
         "add_mm": "", "adds_mm": "", "trans_mm": "", "rot_deg": ""},
    ]
    row = agg.object_row({"id": 2, "name": "003_cracker_box", "diameter_mm": 269.573}, rows, "EXP-014 (W2-3)")
    assert row["N"] == 4
    assert row["success"] == 2
    assert row["success_rate"] == 0.5
    assert row["median_ADD_mm"] == 3.0  # 1.0, 3.0, 50.0 -> 3.0 (gate failure kept)
    assert row["median_rot_deg"] == 1.2  # insufficient frame excluded
    assert row["failure_tags"] == {"icp_no_converge": 1, "insufficient_observation": 1, "success": 2}


@pytest.mark.skipif(not P24_RUN.is_dir(), reason="local P2.4 outputs not present")
def test_unified_table_reproduces_frozen_anchor_numbers():
    """The unified table's anchor rows must reproduce the frozen EXP-006
    headline numbers bit-exactly (93.3% / med 1.30mm; 77.3% / med 2.67mm)."""
    agg = _load_aggregator()
    run_dir = sorted(d for d in W2_3_RUNS.iterdir() if d.is_dir())[-1] if W2_3_RUNS.is_dir() else None
    rows = agg.build(run_dir if run_dir else P24_RUN, P24_RUN)
    by_id = {r["object"]: r for r in rows}
    assert by_id[5]["success"] == 70 and by_id[5]["N"] == 75
    assert by_id[5]["median_ADD_mm"] == 1.30
    assert by_id[13]["success"] == 58 and by_id[13]["N"] == 75
    assert by_id[13]["median_ADD-S_mm"] == 2.67
