"""W2-1 demo artifact pipeline: presentation-layer composition over REAL
experiment outputs.

This module is a READ-ONLY consumer of experiment artifacts: it never
modifies poses, masks, intrinsics, or metrics, and it never recomputes or
interpolates poses. Pose rendering reuses the canonical experiment overlay
(:func:`r3p.experiments.run_p2_3.draw_quad_overlay` — GT=green, PCA init=blue,
ICP prediction=red, projected via ``r3p.geometry`` in meters); no pose or
coordinate convention is defined here.

Two artifact paths:

1. Composition from *stored* per-frame overlays. P2.3/P2.4 runs persist
   ``overlay_<scene>_<frame>.png`` + ``per_frame_obj<id>.csv`` but not the
   pose matrices, so the stored overlays ARE the authoritative rendering of
   the real predictions — they are annotated/assembled as-is.
2. Direct rendering from pose matrices through the reused canonical renderer
   (for future runs that store poses, and for tests).

Image arrays in this module are BGR (cv2-native, matching ``imread`` and
``VideoWriter``); the canonical renderer works in RGB and conversions happen
only at its boundary. All functions are deterministic — no clocks, no RNG.
"""

from __future__ import annotations

import csv
import math
from dataclasses import dataclass
from pathlib import Path

import cv2
import numpy as np

from ..experiments.run_p2_3 import draw_quad_overlay
from ..geometry.camera import project
from ..geometry.se3 import apply as apply_T

# Colors of the canonical overlay (RGB layout there), kept only for legend
# text and convention-verification tests — drawing itself is not redefined.
GT_RGB = (0, 200, 0)
INIT_RGB = (60, 60, 255)
PRED_RGB = (255, 60, 60)

_CAPTION_BG_BGR = (255, 255, 255)
_CAPTION_FG_BGR = (40, 40, 40)
_FILMSTRIP_BG_BGR = (70, 70, 70)
_FONT = cv2.FONT_HERSHEY_SIMPLEX


@dataclass(frozen=True)
class DemoFrame:
    """One experiment frame: stored metrics row + path of its stored overlay."""

    frame_id: str  # "<scene:06d>/<im_id:06d>", zero-padded so sort == time order
    obj_id: int
    overlay_path: Path | None  # None when the run stored no overlay for it
    row: dict  # raw per-frame CSV row (reference data, never mutated)


# --------------------------------------------------------------------------- #
# Artifact loading (read-only)
# --------------------------------------------------------------------------- #
def load_p2_3_run(run_dir: str | Path, obj_id: int) -> list[DemoFrame]:
    """Load per-frame records from a P2.3/P2.4 run directory.

    Reads ``per_frame_obj<obj_id>.csv`` and links each row to its stored
    ``overlay_<scene>_<frame>.png`` when present. Frames without a stored
    overlay (e.g. ``insufficient_observation``) are kept with
    ``overlay_path=None`` so the manifest can report them; visualization
    selection filters them out. Nothing is written.
    """
    run_dir = Path(run_dir)
    csv_path = run_dir / f"per_frame_obj{obj_id}.csv"
    if not csv_path.is_file():
        raise FileNotFoundError(f"per-frame CSV not found: {csv_path}")
    frames: list[DemoFrame] = []
    with open(csv_path, encoding="utf-8") as f:
        for row in csv.DictReader(f):
            fid = row["frame_id"]
            overlay = run_dir / f"overlay_{fid.replace('/', '_')}.png"
            frames.append(
                DemoFrame(fid, int(row["obj_id"]), overlay if overlay.is_file() else None, row)
            )
    frames.sort(key=lambda fr: fr.frame_id)
    return frames


def select_range(
    frames: list[DemoFrame],
    start: int | None = None,
    end: int | None = None,
    require_overlay: bool = True,
) -> list[DemoFrame]:
    """Frames whose 6-digit frame number lies in ``[start, end]`` (inclusive),
    in time order. ``require_overlay`` drops rows the run rendered no PNG for."""
    out = []
    for fr in frames:
        num = int(fr.frame_id.split("/")[-1])
        if start is not None and num < start:
            continue
        if end is not None and num > end:
            continue
        if require_overlay and fr.overlay_path is None:
            continue
        out.append(fr)
    return out


def read_overlay_bgr(frame: DemoFrame) -> np.ndarray:
    """Load a stored overlay PNG (BGR). Raises if absent — never substitutes."""
    if frame.overlay_path is None:
        raise FileNotFoundError(f"no stored overlay for frame {frame.frame_id}")
    img = cv2.imread(str(frame.overlay_path), cv2.IMREAD_COLOR)
    if img is None:
        raise FileNotFoundError(f"overlay image unreadable: {frame.overlay_path}")
    return img


# --------------------------------------------------------------------------- #
# Pose rendering (delegates to the canonical experiment overlay)
# --------------------------------------------------------------------------- #
def render_pose_overlay(rgb_bgr, K, model_pts, T_gt, T_init=None, T_icp=None, note="") -> np.ndarray:
    """Thin delegate to :func:`draw_quad_overlay` (GT green / init blue / ICP
    prediction red, meters, T_cam_model convention). Accepts and returns BGR
    to match this module's image convention."""
    rgb = cv2.cvtColor(np.ascontiguousarray(rgb_bgr), cv2.COLOR_BGR2RGB)
    out = draw_quad_overlay(rgb, K, np.asarray(model_pts), T_gt, T_init, T_icp, note)
    return cv2.cvtColor(out, cv2.COLOR_RGB2BGR)


# --------------------------------------------------------------------------- #
# Annotation & assembly
# --------------------------------------------------------------------------- #
def annotate_frame(img_bgr: np.ndarray, lines: list[str], font_scale: float = 0.46) -> np.ndarray:
    """Append a white caption strip with one line of text per entry.

    Lines longer than the image are auto-shrunk (deterministically) to fit.
    Output height = input height + strip height; width unchanged.
    """
    img = np.ascontiguousarray(img_bgr)
    h, w = img.shape[:2]
    thickness = 1
    fitted: list[tuple[str, float, int, int]] = []
    for line in lines:
        scale = font_scale
        (tw, th), _ = cv2.getTextSize(line, _FONT, scale, thickness)
        while tw > w - 16 and scale > 0.28:
            scale -= 0.02
            (tw, th), _ = cv2.getTextSize(line, _FONT, scale, thickness)
        fitted.append((line, scale, tw, th))
    line_h = max(th for _, _, _, th in fitted) + 9
    strip_h = line_h * len(fitted) + 12
    canvas = np.full((h + strip_h, w, 3), _CAPTION_BG_BGR, np.uint8)
    canvas[:h] = img
    baseline = h + 6 + line_h - 4
    for line, scale, tw, _ in fitted:
        x = max(8, (w - tw) // 2)
        cv2.putText(canvas, line, (x, baseline), _FONT, scale, _CAPTION_FG_BGR, thickness, cv2.LINE_AA)
        baseline += line_h
    return canvas


def build_filmstrip(
    frames_bgr: list[np.ndarray],
    labels: list[str] | None = None,
    cols: int = 4,
    pad: int = 6,
) -> np.ndarray:
    """Deterministic contact sheet (row-major, time order) for README preview."""
    if not frames_bgr:
        raise ValueError("no frames given")
    n = len(frames_bgr)
    rows = math.ceil(n / cols)
    h, w = frames_bgr[0].shape[:2]
    grid = np.full((rows * (h + pad) + pad, cols * (w + pad) + pad, 3), _FILMSTRIP_BG_BGR, np.uint8)
    for i, frame in enumerate(frames_bgr):
        if frame.shape[:2] != (h, w):
            raise ValueError(f"frame {i} size mismatch")
        r, c = divmod(i, cols)
        y, x = pad + r * (h + pad), pad + c * (w + pad)
        grid[y : y + h, x : x + w] = frame
        if labels is not None:
            pos = (x + 6, y + h - 10)  # bottom-left: the stored overlays carry
            # their own note text at the top-left — never overlap it
            cv2.putText(grid, labels[i], pos, _FONT, 0.5, (0, 0, 0), 3, cv2.LINE_AA)
            cv2.putText(grid, labels[i], pos, _FONT, 0.5, (255, 255, 255), 1, cv2.LINE_AA)
    return grid


def encode_video(frames_bgr: list[np.ndarray], out_path: str | Path, fps: float = 5.0) -> int:
    """Write frames (time order) to MP4 via cv2.VideoWriter (mp4v — no external
    ffmpeg needed). Returns the number of frames written. Deterministic: the
    encoded content depends only on the given frames."""
    if not frames_bgr:
        raise ValueError("no frames to encode")
    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    h, w = frames_bgr[0].shape[:2]
    writer = cv2.VideoWriter(str(out_path), cv2.VideoWriter_fourcc(*"mp4v"), float(fps), (w, h))
    if not writer.isOpened():
        raise RuntimeError("cv2.VideoWriter failed to open mp4v writer")
    for frame in frames_bgr:
        if frame.shape[:2] != (h, w):
            raise ValueError("frame size mismatch inside sequence")
        writer.write(np.ascontiguousarray(frame))
    writer.release()
    return len(frames_bgr)


# --------------------------------------------------------------------------- #
# Coordinate-convention sanity check (GT overlay vs evaluator convention)
# --------------------------------------------------------------------------- #
def dataset_index_for(dataset, frame_id: str) -> int:
    """Index into ``dataset`` whose observation frame_id equals ``frame_id``."""
    for i, (scene, im_id) in enumerate(dataset.frames):
        if f"{scene:06d}/{int(im_id):06d}" == frame_id:
            return i
    raise KeyError(f"frame {frame_id} not in dataset index")


def gt_overlay_in_mask_fraction(dataset, frame_index: int, obj_id: int) -> float:
    """Fraction of GT-projected model points landing inside the visible mask.

    Sanity check for the demo path: the dataset GT pose (meters, T_cam_model,
    the exact convention the experiment overlays were rendered with) pushed
    through the shared ``project(K, apply_T(T, pts))`` must fall on the
    object's ``mask_visib``. A low fraction means a units/coordinate bug —
    not a "visually close" demo. Requires ``load_masks=True``.
    """
    obs = dataset[frame_index]
    T_gt = obs["gt_poses"].get(obj_id)
    if T_gt is None:
        raise KeyError(f"object {obj_id} has no GT pose in frame {obs['frame_id']}")
    pts = np.asarray(obs["model_points"][obj_id])
    uv, _ = project(obs["K"], apply_T(T_gt, pts))
    mask = obs["masks"][obj_id]
    h, w = mask.shape[:2]
    u = np.round(uv[:, 0]).astype(int)
    v = np.round(uv[:, 1]).astype(int)
    inbounds = (u >= 0) & (u < w) & (v >= 0) & (v < h)
    inside = np.zeros(len(uv), dtype=bool)
    inside[inbounds] = mask[v[inbounds], u[inbounds]]
    if len(inside) == 0:
        return 0.0
    return float(inside.mean())
