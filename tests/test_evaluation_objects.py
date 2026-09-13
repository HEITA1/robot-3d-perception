"""W2-2 evaluation object set registry validation.

Structural checks (parse, size, uniqueness, roles, evaluated-flag policy) run
everywhere; metadata cross-checks (names/diameters against models_info.json,
scene membership against scene_gt.json) run when the local BOP subset is
present. No experiment is run or implied — this validates the selection
registry only.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
import yaml

CONFIG = Path("configs/evaluation_objects.yaml")
DATA_ROOT = Path("data/ycbv")
ALLOWED_ROLES = {
    "anchor",
    "texture_diverse",
    "symmetry_challenging",
    "geometry_diverse",
    "robustness_oriented",
}
ANCHOR_IDS = {5, 13}  # the only objects with frozen experiment results (EXP-006)


@pytest.fixture(scope="module")
def registry() -> dict:
    with open(CONFIG, encoding="utf-8") as f:
        return yaml.safe_load(f)


def test_config_exists_and_parses(registry):
    assert isinstance(registry, dict)
    assert isinstance(registry["objects"], list)


def test_set_size_in_range(registry):
    assert 5 <= len(registry["objects"]) <= 8
    assert registry["set_size"] == len(registry["objects"])


def test_no_duplicate_ids(registry):
    ids = [o["id"] for o in registry["objects"]]
    assert len(ids) == len(set(ids))


def test_anchors_retained(registry):
    anchors = {o["id"] for o in registry["objects"] if o["role"] == "anchor"}
    assert ANCHOR_IDS <= anchors


def test_roles_valid(registry):
    assert all(o["role"] in ALLOWED_ROLES for o in registry["objects"])


def test_evaluated_flag_policy(registry):
    """Registry ≠ results: `evaluated: true` is allowed only for the anchors
    that actually carry frozen EXP-006 numbers."""
    for o in registry["objects"]:
        if o["id"] in ANCHOR_IDS:
            assert o["evaluated"] is True
            assert o["eval_source"] == "EXP-006"
        else:
            assert o["evaluated"] is False
            assert "eval_source" not in o


def test_required_metadata_fields(registry):
    for o in registry["objects"]:
        assert isinstance(o["id"], int)
        assert isinstance(o["name"], str) and o["name"]
        assert isinstance(o["scenes"], list) and o["scenes"]
        assert float(o["diameter_mm"]) > 0


@pytest.mark.skipif(not (DATA_ROOT / "test").is_dir(), reason="local YCB-V subset not present")
def test_names_and_diameters_match_bop_metadata(registry):
    from r3p.datasets.ycbv_bop import load_obj_names

    names = load_obj_names(DATA_ROOT)
    info = json.loads((DATA_ROOT / "models" / "models_info.json").read_text(encoding="utf-8"))
    for o in registry["objects"]:
        assert names[o["id"]] == o["name"], f"obj{o['id']} name mismatch"
        assert abs(float(info[str(o["id"])]["diameter"]) - float(o["diameter_mm"])) < 0.01


@pytest.mark.skipif(not (DATA_ROOT / "test").is_dir(), reason="local YCB-V subset not present")
def test_registered_scenes_actually_contain_object(registry):
    for o in registry["objects"]:
        for scene in o["scenes"]:
            gt = json.loads(
                (DATA_ROOT / "test" / f"{scene:06d}" / "scene_gt.json").read_text(encoding="utf-8")
            )
            present = {inst["obj_id"] for insts in gt.values() for inst in insts}
            assert o["id"] in present, f"obj{o['id']} listed for scene {scene} but absent there"
