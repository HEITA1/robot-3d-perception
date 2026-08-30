"""Dataset interface for 6D pose experiments.

Contract — every frame is a dict with (at least):

==================  =====================================================
key                 shape / type
==================  =====================================================
``frame_id``        str
``rgb``             (H, W, 3) uint8
``depth``           (H, W) float32, meters, 0 = invalid
``K``               (3, 3) float64 pinhole intrinsics
``masks``           dict[obj_id -> (H, W) bool]
``gt_poses``        dict[obj_id -> (4, 4)] camera-frame SE(3), meters
``model_points``    dict[obj_id -> (N, 3)] model-frame points, meters
==================  =====================================================

Units are meters everywhere unless stated otherwise.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Iterator


class PoseDataset(ABC):
    """Minimal dataset protocol: indexable, yields observation dicts."""

    @abstractmethod
    def __len__(self) -> int: ...

    @abstractmethod
    def __getitem__(self, index: int) -> dict: ...

    def __iter__(self) -> Iterator[dict]:
        for i in range(len(self)):
            yield self[i]
