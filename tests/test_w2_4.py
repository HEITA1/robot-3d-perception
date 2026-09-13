"""W2-4 / EXP-015 expanded baseline guards.

- Protocol fingerprint: the frozen icp/selection/success parameter blocks must
  stay identical across p2_4 (EXP-006), w2_3 (EXP-014) and w2_4 (EXP-015);
  the recorded sha256 fingerprint fails if anyone touches a frozen parameter.
- Config: object list / full-scene coverage (75) / scenes / pre-registered
  metrics must match the W2-3 registry policy.
- Expanded run invariants (data-dependent): full coverage, four-layer
  consistency, failures retained — checked without presuming outcomes.
- Comparison script unit test on synthetic runs.
"""

from __future__ import annotations

import csv
import hashlib
import importlib.util
import json
from pathlib import Path

import pytest
import yaml

P2_4_CONFIG = Path("configs/p2_4.yaml")
W2_3_CONFIG = Path("configs/w2_3_multibaseline.yaml")
W2_4_CONFIG = Path("configs/w2_4_expanded_baseline.yaml")
REGISTRY = Path("configs/evaluation_objects.yaml")
P24_RUN = Path("outputs/p2_4/20260830-161911")
W2_4_RUNS = Path("outputs/w2_4")

# sha256[:16] of the canonical JSON of the frozen icp/selection/success block
# (identical in p2_4 / w2_3 / w2_4). Update ONLY via a new approved protocol.
FROZEN_FINGERPRINT = "584da3b46fa28ed4"
FROZEN_SECTIONS = ("icp", "selection", "success")
EXPECTED_OBJECTS = {2: ("add", 50), 6: ("adds", 48), 10: ("add", 50), 14: ("add", 48), 15: ("add", 50)}


def _load(path: Path) -> dict:
    with open(path, encoding="utf-8") as f:
        return yaml.safe_load(f)


def _frozen_block(cfg: dict) -> str:
    return json.dumps({k: cfg[k] for k in FROZEN_SECTIONS}, sort_keys=True)


def _load_compare():
    spec = importlib.util.spec_from_file_location("w2_4_compare", Path("scripts/w2_4_compare.py"))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_protocol_fingerprint_unchanged():
    """Any change to a frozen baseline parameter breaks this hash — parameter
    changes require a new protocol/experiment, never a silent edit."""
    block = _frozen_block(_load(W2_4_CONFIG))
    assert hashlib.sha256(block.encode()).hexdigest()[:16] == FROZEN_FINGERPRINT


def test_frozen_params_identical_across_exp006_exp014_exp015():
    blocks = {_frozen_block(_load(p)) for p in (P2_4_CONFIG, W2_3_CONFIG, W2_4_CONFIG)}
    assert len(blocks) == 1, "frozen baseline parameters diverged between experiments"


def test_w2_4_config_full_scene_coverage_and_registry_metrics():
    cfg = _load(W2_4_CONFIG)
    objects = {o["obj_id"]: o for o in cfg["objects"]}
    assert set(objects) == set(EXPECTED_OBJECTS)
    with open(REGISTRY, encoding="utf-8") as f:
        registry = {o["id"]: o for o in yaml.safe_load(f)["objects"]}
    for obj_id, (metric, scene) in EXPECTED_OBJECTS.items():
        o = objects[obj_id]
        assert o["n_frames"] == 75, "W2-4 coverage must stay full-scene (75)"
        assert o["eval_scene"] == scene
        assert o["success_metric"] == metric == registry[obj_id]["primary_metric"]
        assert scene in registry[obj_id]["scenes"]


def _write_run(run_dir: Path, obj_id: int, rows: list[dict]) -> None:
    run_dir.mkdir(parents=True, exist_ok=True)
    fields = ["failure_tag", "pose_success", "solver_success", "add_mm", "adds_mm", "trans_mm", "rot_deg"]
    with open(run_dir / f"per_frame_obj{obj_id}.csv", "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


def _row(tag: str, add: str = "", pose: str = "0") -> dict:
    return {"failure_tag": tag, "pose_success": pose, "solver_success": "1" if tag != "insufficient_observation" else "0",
            "add_mm": add, "adds_mm": add, "trans_mm": add, "rot_deg": add}


def test_w2_4_compare_synthetic(tmp_path):
    comp = _load_compare()
    initial = tmp_path / "initial"
    expanded = tmp_path / "expanded"
    # the comparison iterates ALL non-anchor registry objects — write CSVs for each
    rows_by_tag = {
        "success": _row("success", "2.0", "1"),
        "roll": _row("roll_symmetry_ambiguity", "60.0"),
        "insufficient": _row("insufficient_observation"),
    }
    for oid in (2, 6, 10, 14, 15):
        _write_run(initial, oid, [rows_by_tag["success"], rows_by_tag["roll"], rows_by_tag["success"]])
        _write_run(expanded, oid, [rows_by_tag["success"], rows_by_tag["roll"],
                                   rows_by_tag["success"], rows_by_tag["success"],
                                   rows_by_tag["insufficient"]])
    out = tmp_path / "cmp"
    sys_argv = ["--initial-run", str(initial), "--expanded-run", str(expanded), "--output-dir", str(out)]
    comp.main(sys_argv)
    text = (out / "w2_3_vs_w2_4_comparison.md").read_text(encoding="utf-8")
    assert "3 → 5" in text and "2 → 3" in text and "66.7% → 60.0%" in text
    assert "+insufficient_observation" in text  # expanded-only tag detected as a change
    payload = json.loads((out / "w2_3_vs_w2_4_comparison.json").read_text(encoding="utf-8"))
    assert len(payload["rows"]) == 5
    assert payload["rows"][0]["expanded"]["total"] == 5


@pytest.mark.skipif(not W2_4_RUNS.is_dir() or not any(W2_4_RUNS.glob("*/per_frame_obj2.csv")),
                    reason="local W2-4 outputs not present")
def test_expanded_run_invariants():
    """Outcome-independent invariants: full coverage, four-layer consistency,
    failures retained. No expected success rates are asserted here."""
    agg_spec = importlib.util.spec_from_file_location(
        "w2_3_unified_table", Path("scripts/w2_3_unified_table.py"))
    agg = importlib.util.module_from_spec(agg_spec)
    agg_spec.loader.exec_module(agg)
    run_dir = sorted(d for d in W2_4_RUNS.iterdir() if d.is_dir())[-1]
    with open(REGISTRY, encoding="utf-8") as f:
        registry = yaml.safe_load(f)
    for obj in registry["objects"]:
        if obj.get("eval_source") == "EXP-006":
            continue
        rows = agg.load_rows(run_dir / f"per_frame_obj{obj['id']}.csv")
        r = agg.object_row(obj, rows, "EXP-015 (W2-4)")
        assert r["total"] == 75, f"obj{obj['id']}: expanded coverage must be 75"
        assert r["valid"] == 75
        states = r["state_counts"]
        assert states["pre_solver_insufficient"] + states["runtime_error"] + r["attempted"] == 75
        assert states["solver_gate_failure"] + states["pose_success"] + states["pose_metric_failure"] == r["attempted"]
        assert sum(r["failure_tags"].values()) == 75  # no frame dropped


@pytest.mark.skipif(not P24_RUN.is_dir(), reason="local P2.4 outputs not present")
def test_unified_table_reproduces_frozen_anchor_numbers():
    """Anchor regression (W2-4 table): obj5 = 1.30mm / obj13 = 2.67mm."""
    agg_spec = importlib.util.spec_from_file_location(
        "w2_3_unified_table", Path("scripts/w2_3_unified_table.py"))
    agg = importlib.util.module_from_spec(agg_spec)
    agg_spec.loader.exec_module(agg)
    run_dir = sorted(d for d in W2_4_RUNS.iterdir() if d.is_dir())[-1] if W2_4_RUNS.is_dir() else P24_RUN
    rows = agg.build(run_dir, P24_RUN, "EXP-015 (W2-4)")
    by_id = {r["object"]: r for r in rows}
    assert by_id[5]["success"] == 70 and by_id[5]["total"] == 75
    assert by_id[5]["median_ADD_mm"] == 1.30
    assert by_id[13]["success"] == 58 and by_id[13]["total"] == 75
    assert by_id[13]["median_ADD-S_mm"] == 2.67
