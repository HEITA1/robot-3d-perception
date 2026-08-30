"""Configuration loading and merging.

Configs are plain YAML files. :func:`load_config` returns a :class:`Config`
wrapper with dotted-key access (``cfg["scene.image_size"]``). CLI overrides use
``--set key=value`` with dotted keys; values are parsed as YAML scalars/lists.
"""

from __future__ import annotations

import copy
from typing import Any

import yaml


class Config:
    """Thin wrapper around a nested dict with dotted-key access."""

    def __init__(self, data: dict[str, Any] | None = None):
        self._data = data if data is not None else {}

    def __getitem__(self, key: str) -> Any:
        return self._get(key)

    def get(self, key: str, default: Any = None) -> Any:
        try:
            return self._get(key)
        except KeyError:
            return default

    def __contains__(self, key: str) -> bool:
        try:
            self._get(key)
            return True
        except KeyError:
            return False

    def _get(self, key: str) -> Any:
        node: Any = self._data
        for part in key.split("."):
            if not isinstance(node, dict) or part not in node:
                raise KeyError(key)
            node = node[part]
        return node

    def as_dict(self) -> dict[str, Any]:
        """Deep copy of the underlying dict (safe for JSON dumping)."""
        return copy.deepcopy(self._data)


def _deep_merge(base: dict, extra: dict) -> dict:
    out = copy.deepcopy(base)
    for k, v in extra.items():
        if isinstance(v, dict) and isinstance(out.get(k), dict):
            out[k] = _deep_merge(out[k], v)
        else:
            out[k] = copy.deepcopy(v)
    return out


def _nested_dict(dotted_key: str, value: Any) -> dict:
    out: dict = {}
    node = out
    parts = dotted_key.split(".")
    for part in parts[:-1]:
        node[part] = {}
        node = node[part]
    node[parts[-1]] = value
    return out


def load_config(path: str, overrides: list[str] | None = None) -> Config:
    """Load a YAML config and apply ``key=value`` overrides (dotted keys).

    Override values are parsed with YAML, so ``seed=7``, ``flag=true`` and
    ``image_size=[256, 256]`` all work.
    """
    with open(path, "r", encoding="utf-8") as f:
        data = yaml.safe_load(f) or {}
    if not isinstance(data, dict):
        raise ValueError(f"config root must be a mapping: {path}")

    for item in overrides or []:
        key, sep, raw = item.partition("=")
        if not key or not sep:
            raise ValueError(f"invalid override, expected key=value: {item!r}")
        data = _deep_merge(data, _nested_dict(key, yaml.safe_load(raw)))
    return Config(data)
