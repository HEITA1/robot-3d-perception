"""Minimal canonical-coordinate network (P3.0-S).

A ~50k-parameter per-point MLP: input is 6 features per point
(XYZ normalized to the unit ball around the cloud centroid + RGB),
output is the predicted canonical (model-frame) XYZ of that point.
Deliberately tiny: easy to debug, trains on CPU in minutes.
"""

from __future__ import annotations

import numpy as np
import torch
from torch import nn


class CoordNet(nn.Module):
    """PointNet-style per-point regression.

    Per-point local features are combined with a GLOBAL max-pool descriptor so
    each point's prediction can depend on the whole cloud — without global
    context, the per-point camera-frame -> canonical mapping is multivalued
    across poses and the network can only fit the conditional mean (observed in
    Gate 1 attempt 1: loss plateaued at ~550mm). Still a tiny PointNet-style
    MLP: no conv patch encoder, no attention, no pretrained backbone.
    """

    def __init__(self, in_dim: int = 6, local_widths: tuple[int, ...] = (64, 128), out_dim: int = 3):
        super().__init__()
        layers = []
        prev = in_dim
        for w in local_widths:
            layers += [nn.Linear(prev, w), nn.ReLU()]
            prev = w
        self.local = nn.Sequential(*layers)
        self.global_head = nn.Sequential(nn.Linear(128, 128), nn.ReLU())
        self.head = nn.Sequential(nn.Linear(128 + 128, 128), nn.ReLU(), nn.Linear(128, out_dim))

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        """x: (B, N, 6) or (N, 6) -> predicted canonical XYZ, same leading shape."""
        single = x.dim() == 2
        if single:
            x = x[None]
        local = self.local(x)                      # (B, N, 128)
        glob = self.global_head(local.max(dim=1).values)  # (B, 128) global shape descriptor
        glob = glob[:, None, :].expand_as(local)
        out = self.head(torch.cat([local, glob], dim=-1))
        return out[0] if single else out


def normalize_points(xyz: np.ndarray) -> tuple[np.ndarray, np.ndarray, float]:
    """Center at centroid + scale to unit max-radius. Returns (xyz_norm, center, scale)."""
    center = xyz.mean(axis=0)
    scale = float(np.linalg.norm(xyz - center, axis=1).max())
    if scale < 1e-9:
        scale = 1.0
    return (xyz - center) / scale, center, scale


def count_parameters(module: nn.Module) -> int:
    return sum(p.numel() for p in module.parameters() if p.requires_grad)
