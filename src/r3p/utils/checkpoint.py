"""Generic checkpoint save/load (pickle-based for Phase 0).

Phase 3 will switch model state dicts to torch.save/torch.load; the interface
(save a dict to a path, load it back) stays the same.
"""

from __future__ import annotations

import pickle
from pathlib import Path


def save_checkpoint(obj: dict, path: str | Path) -> Path:
    """Save a dict to ``path`` (parent dirs created)."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "wb") as f:
        pickle.dump(obj, f)
    return path


def load_checkpoint(path: str | Path) -> dict:
    """Load a dict previously written by :func:`save_checkpoint`."""
    with open(path, "rb") as f:
        return pickle.load(f)
