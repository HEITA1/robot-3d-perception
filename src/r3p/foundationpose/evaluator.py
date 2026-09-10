"""Evaluation + visualization wrappers for the FoundationPose integration.

Evaluation delegates to the project's single metric implementation
(r3p.evaluation.metrics.compute_all) so FP numbers are directly comparable
with P2/P3. Visualization follows the project convention: GT = green,
prediction = red.
"""

from __future__ import annotations

from pathlib import Path

import cv2
import numpy as np

from ..evaluation.metrics import compute_all
from .schema import EvaluationData


def evaluate_fp_result(pred_pose: np.ndarray, evaluation: EvaluationData) -> dict:
    """Unified FP-style result -> project metrics + success flag.

    pred_pose: (4, 4) camera-frame SE(3) as returned by a backend.
    """
    metrics = compute_all(evaluation.model_points_m, pred_pose, evaluation.gt_pose)
    threshold_m = 0.1 * evaluation.diameter_m
    return {
        "pred_pose": pred_pose.tolist(),
        "gt_pose_present": True,
        "add_mm": round(metrics["add"] * 1e3, 3),
        "adds_mm": round(metrics["adds"] * 1e3, 3),
        "translation_error_mm": round(metrics["trans"] * 1e3, 3),
        "rotation_error_deg": round(metrics["rot_deg"], 3),
        "success": bool(metrics["add"] < threshold_m),
        "threshold_mm": round(threshold_m * 1e3, 3),
    }


def save_gt_pred_overlay(rgb: np.ndarray, K: np.ndarray, model_points_m: np.ndarray,
                         gt_pose: np.ndarray, pred_pose: np.ndarray | None,
                         out_path: str | Path, title: str = "") -> Path:
    """Project-convention overlay: GT points green, prediction points red."""
    img = rgb.copy()

    def project(T: np.ndarray) -> np.ndarray:
        p_cam = model_points_m @ T[:3, :3].T + T[:3, 3]
        uv = K @ p_cam.T
        return uv[0] / uv[2], uv[1] / uv[2]

    u, v = project(gt_pose)
    for uu, vv in zip(u, v):
        cv2.circle(img, (int(round(uu)), int(round(vv))), 1, (0, 200, 0), -1)
    if pred_pose is not None:
        u, v = project(pred_pose)
        for uu, vv in zip(u, v):
            cv2.circle(img, (int(round(uu)), int(round(vv))), 1, (255, 60, 60), -1)
    if title:
        cv2.putText(img, title, (10, 24), cv2.FONT_HERSHEY_SIMPLEX, 0.55,
                    (255, 255, 255), 2, cv2.LINE_AA)
    out = Path(out_path)
    out.parent.mkdir(parents=True, exist_ok=True)
    cv2.imwrite(str(out), cv2.cvtColor(img, cv2.COLOR_RGB2BGR))
    return out
