"""Accumulate per-frame, per-object metrics and produce summary tables."""

from __future__ import annotations

import numpy as np


class PoseEvaluator:
    """Collects one metric dict per (frame, object); summarizes by object.

    Metric keys follow :func:`r3p.evaluation.metrics.compute_all`:
    ``add``, ``adds``, ``trans`` (meters) and ``rot_deg`` (degrees).
    """

    METRICS = ("add", "adds", "trans", "rot_deg")

    def __init__(self) -> None:
        self._rows: list[dict] = []

    def add_frame(self, frame_id: str, obj_id: str, metrics: dict) -> None:
        row = {"frame_id": frame_id, "obj_id": obj_id}
        for key in self.METRICS:
            row[key] = float(metrics.get(key, float("nan")))
        self._rows.append(row)

    def summary(self) -> dict:
        """Per-object mean metrics (plus ``n_frames``)."""
        out: dict = {}
        for obj in sorted({r["obj_id"] for r in self._rows}):
            rows = [r for r in self._rows if r["obj_id"] == obj]
            out[obj] = {k: float(np.nanmean([r[k] for r in rows])) for k in self.METRICS}
            out[obj]["n_frames"] = len(rows)
        return out

    def format_table(self) -> str:
        """Fixed-width human-readable table (mm / deg)."""
        header = (
            f"{'object':<14}{'n':>5}{'ADD(mm)':>10}{'ADD-S(mm)':>11}{'trans(mm)':>11}{'rot(deg)':>10}"
        )
        lines = [header, "-" * len(header)]
        for obj, m in self.summary().items():
            lines.append(
                f"{obj:<14}{m['n_frames']:>5}{m['add'] * 1e3:>10.2f}{m['adds'] * 1e3:>11.2f}"
                f"{m['trans'] * 1e3:>11.2f}{m['rot_deg']:>10.2f}"
            )
        return "\n".join(lines)
