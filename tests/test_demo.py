"""W2-1 demo artifact pipeline tests.

Synthetic tests cover the presentation plumbing (overlay delegation,
annotation, filmstrip, MP4 assembly, artifact loading) with mock images and
mock run directories; real-data tests verify the GT overlay convention
against BOP data and the real frozen P2.4 artifacts, and skip automatically
when data/outputs are absent.
"""

from __future__ import annotations

import csv
import hashlib
from pathlib import Path

import cv2
import numpy as np
import pytest

from r3p.geometry.se3 import make_T
from r3p.visualization.demo import (
    DemoFrame,
    annotate_frame,
    build_filmstrip,
    dataset_index_for,
    encode_video,
    gt_overlay_in_mask_fraction,
    load_p2_3_run,
    render_pose_overlay,
    select_range,
)

DATA_ROOT = Path("data/ycbv")
P24_RUN = Path("outputs/p2_4/20260830-161911")

K = np.array([[500.0, 0.0, 320.0], [0.0, 500.0, 240.0], [0.0, 0.0, 1.0]])
# ~10 cm box one meter in front of the camera -> projects near image center.
MODEL_PTS = np.array(
    [[x, y, z] for x in (-0.05, 0.05) for y in (-0.035, 0.035) for z in (-0.025, 0.025)],
    dtype=np.float64,
)
T_GT = make_T(np.eye(3), np.array([0.0, 0.0, 1.0]))


def _count(img, bgr) -> int:
    return int(np.sum(np.all(img == np.array(bgr, np.uint8), axis=-1)))


# BGR tuples after the canonical RGB renderer's boundary conversion:
# GT green stays (0,200,0); pred red RGB (255,60,60) becomes BGR (60,60,255).
GT_BGR = (0, 200, 0)
PRED_BGR = (60, 60, 255)


def test_render_pose_overlay_gt_only_green():
    img = render_pose_overlay(np.zeros((480, 640, 3), np.uint8), K, MODEL_PTS, T_GT)
    assert _count(img, GT_BGR) > 0
    assert _count(img, PRED_BGR) == 0


def test_render_pose_overlay_identical_pose_covers_gt():
    """Delegation check: the prediction drawn at the GT pose must overwrite the
    GT dots exactly (same projection path, same convention — no redefinition)."""
    gt_only = render_pose_overlay(np.zeros((480, 640, 3), np.uint8), K, MODEL_PTS, T_GT)
    both = render_pose_overlay(np.zeros((480, 640, 3), np.uint8), K, MODEL_PTS, T_GT, T_icp=T_GT)
    assert _count(gt_only, GT_BGR) > 0
    assert _count(both, GT_BGR) == 0
    assert _count(both, PRED_BGR) == _count(gt_only, GT_BGR)


def test_annotate_frame_deterministic_and_dims():
    img = np.zeros((48, 64, 3), np.uint8)
    out1 = annotate_frame(img, ["method | object", "scene / frame | metric", "legend line"])
    out2 = annotate_frame(img, ["method | object", "scene / frame | metric", "legend line"])
    assert np.array_equal(out1, out2)
    assert out1.shape[0] > img.shape[0] and out1.shape[1] == img.shape[1]
    assert np.array_equal(out1[: img.shape[0]], img)  # content pixels untouched
    assert out1[img.shape[0] :].mean() > 200.0  # strip is white with dark text


def _write_mock_run(run_dir: Path, rows, overlay_ids) -> None:
    run_dir.mkdir(parents=True)
    with open(run_dir / "per_frame_obj5.csv", "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=["frame_id", "obj_id", "failure_tag", "add_mm"])
        writer.writeheader()
        writer.writerows(rows)
    for fid in overlay_ids:
        cv2.imwrite(str(run_dir / f"overlay_{fid.replace('/', '_')}.png"), np.full((6, 8, 3), 128, np.uint8))


def _dir_digest(root: Path) -> list[tuple[str, str]]:
    entries = []
    for p in sorted(root.rglob("*")):
        if p.is_file():
            entries.append((str(p.relative_to(root)), hashlib.sha256(p.read_bytes()).hexdigest()))
    return entries


def test_load_p2_3_run_sorted_readonly_missing_overlay(tmp_path):
    rows = [
        {"frame_id": "000050/000002", "obj_id": "5", "failure_tag": "success", "add_mm": "1.0"},
        {"frame_id": "000050/000001", "obj_id": "5", "failure_tag": "success", "add_mm": "1.1"},
        {"frame_id": "000050/000003", "obj_id": "5", "failure_tag": "success", "add_mm": "1.2"},
    ]
    _write_mock_run(tmp_path / "run", rows, overlay_ids={"000050/000001", "000050/000003"})
    before = _dir_digest(tmp_path / "run")
    frames = load_p2_3_run(tmp_path / "run", 5)
    assert _dir_digest(tmp_path / "run") == before  # read-only consumer
    assert [f.frame_id for f in frames] == ["000050/000001", "000050/000002", "000050/000003"]
    assert frames[0].overlay_path is not None
    assert frames[1].overlay_path is None  # no stored overlay -> kept, flagged
    assert frames[2].obj_id == 5


def test_load_p2_3_run_missing_csv_raises(tmp_path):
    with pytest.raises(FileNotFoundError):
        load_p2_3_run(tmp_path, 5)


def test_select_range_time_order_and_overlay_filter():
    frames = [
        DemoFrame(f"000050/{n:06d}", 5, Path("x") if n in (2, 4) else None, {})
        for n in (1, 2, 3, 4, 5)
    ]
    sel = select_range(frames, 2, 4)
    assert [f.frame_id for f in sel] == ["000050/000002", "000050/000004"]
    assert [f.frame_id for f in select_range(frames, 2, 4, require_overlay=False)] == [
        "000050/000002",
        "000050/000003",
        "000050/000004",
    ]
    assert [f.frame_id for f in select_range(frames)] == [
        "000050/000002",
        "000050/000004",
    ]


def test_encode_video_frame_count(tmp_path):
    frames = [np.full((48, 64, 3), 30 * i, np.uint8) for i in range(5)]
    out = tmp_path / "seq.mp4"
    n = encode_video(frames, out, fps=5.0)
    assert n == 5
    assert out.is_file() and out.stat().st_size > 0


def test_filmstrip_grid_shape():
    frames = [np.full((48, 64, 3), 128, np.uint8) for _ in range(5)]
    grid = build_filmstrip(frames, labels=[f"f{i}" for i in range(5)], cols=2)
    assert grid.shape == (3 * (48 + 6) + 6, 2 * (64 + 6) + 6, 3)


# --------------------------------------------------------------------------- #
# Real-data tests (skip when the local subset / outputs are absent)
# --------------------------------------------------------------------------- #
@pytest.mark.skipif(not (DATA_ROOT / "test").is_dir(), reason="local YCB-V subset not present")
def test_gt_overlay_in_mask_fraction_real():
    """The demo GT-convention sanity check on real data: GT model points (m)
    pushed through the shared project/apply path must land on mask_visib."""
    from r3p.datasets.ycbv_bop import YcbvBopDataset

    ds = YcbvBopDataset(DATA_ROOT, obj_ids=(5,), scene_ids=[50], load_masks=True, n_model_points=500)
    frac = gt_overlay_in_mask_fraction(ds, dataset_index_for(ds, "000050/000620"), 5)
    assert frac >= 0.8, f"GT overlay convention check failed: in-mask fraction {frac:.3f}"


@pytest.mark.skipif(not P24_RUN.is_dir(), reason="local P2.4 outputs not present")
def test_load_real_p2_4_run():
    frames = load_p2_3_run(P24_RUN, 5)
    assert len(frames) == 75
    assert frames[0].frame_id == "000050/000620"
    assert frames[-1].frame_id == "000050/001874"
    successes = [f for f in frames if f.row["failure_tag"] == "success"]
    assert len(successes) == 70
    assert all(f.overlay_path is not None for f in successes)
    window = select_range(frames, 620, 769)
    assert len(window) == 23
    assert all(f.row["failure_tag"] == "success" for f in window)
