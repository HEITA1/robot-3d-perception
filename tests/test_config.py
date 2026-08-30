"""Unit tests for config loading, dot access, and overrides."""

import pytest

from r3p.config import load_config

YAML_TEXT = """
experiment:
  name: smoke
  seed: 0
scene:
  image_size: [480, 640]
  intrinsics: {fx: 570.0, cy: 240.0}
"""


def write_config(tmp_path, text=YAML_TEXT):
    p = tmp_path / "cfg.yaml"
    p.write_text(text, encoding="utf-8")
    return str(p)


def test_load_and_dot_access(tmp_path):
    cfg = load_config(write_config(tmp_path))
    assert cfg["experiment.name"] == "smoke"
    assert cfg["scene.image_size"] == [480, 640]
    assert cfg.get("missing.key", 42) == 42
    assert "experiment.seed" in cfg
    assert "no.such.key" not in cfg


def test_scalar_and_nested_overrides(tmp_path):
    cfg = load_config(
        write_config(tmp_path),
        ["experiment.seed=7", "scene.intrinsics.fx=600", "extra.flag=true"],
    )
    assert cfg["experiment.seed"] == 7
    assert cfg["scene.intrinsics.fx"] == 600
    assert cfg["scene.intrinsics.cy"] == 240.0  # untouched sibling survives the merge
    assert cfg["extra.flag"] is True


def test_list_override(tmp_path):
    cfg = load_config(write_config(tmp_path), ["scene.image_size=[256, 256]"])
    assert cfg["scene.image_size"] == [256, 256]


def test_bad_override_raises(tmp_path):
    with pytest.raises(ValueError):
        load_config(write_config(tmp_path), ["no_equals_sign"])


def test_missing_key_raises(tmp_path):
    cfg = load_config(write_config(tmp_path))
    with pytest.raises(KeyError):
        cfg["no.such.key"]
