"""W2-1 demo artifact builder — read-only consumer of experiment outputs.

Composes presentation-layer artifacts from stored P2.3/P2.4 run outputs:
annotated static demo images, an MP4 sequence (cv2 mp4v — no external ffmpeg),
and a filmstrip preview. The pipeline never modifies poses, masks,
intrinsics, or metrics, never recomputes or interpolates poses, and never
writes into experiment run directories.

The sequence uses the per-frame overlay PNGs rendered by the experiment run
itself (the runs store metrics + overlays, not pose matrices), so every
visualized pose is the real frozen experiment output in time order.

Usage::

    python scripts/build_demo.py --experiment p2_4 --object 5 --mode static --pick success
    python scripts/build_demo.py --experiment p2_4 --object 5 --mode static --pick failure
    python scripts/build_demo.py --experiment p2_4 --object 5 --mode sequence \
        --start-frame 620 --end-frame 769
    python scripts/build_demo.py --experiment p2_4 --object 5 --mode all \
        --start-frame 620 --end-frame 769 --output outputs/demo

A GT-convention sanity check (GT pose projected through the shared
project/apply path must land inside mask_visib) gates every build and its
fraction is recorded in the manifest.
"""

from __future__ import annotations

import argparse
import json
import statistics
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

import cv2  # noqa: E402

from r3p.datasets.ycbv_bop import YcbvBopDataset, load_obj_names  # noqa: E402
from r3p.visualization import demo as D  # noqa: E402

LEGEND_LINE = "GT green | PCA init blue | ICP prediction red"
PREFERRED_FAILURE_TAG = "roll_symmetry_ambiguity"  # most visually explainable


def resolve_run_dir(experiment: str) -> Path:
    """Direct run-dir path, or latest (name-sorted) run under outputs/<name>."""
    direct = Path(experiment)
    if direct.is_dir():
        return direct
    base = Path("outputs") / experiment
    runs = sorted(d for d in base.iterdir() if d.is_dir()) if base.is_dir() else []
    if not runs:
        raise FileNotFoundError(f"no run directory found for experiment {experiment!r}")
    return runs[-1]


def load_run_summary(run_dir: Path, obj_id: int) -> dict:
    """Per-object entry from the run's metrics.json (threshold, metric key)."""
    with open(run_dir / "metrics.json", encoding="utf-8") as f:
        metrics = json.load(f)
    for entry in metrics["objects"]:
        if int(entry["obj_id"]) == obj_id:
            return entry
    raise KeyError(f"object {obj_id} not in {run_dir / 'metrics.json'}")


def pick_static_frame(frames: list[D.DemoFrame], pick: str, frame_num: int | None) -> D.DemoFrame:
    """Deterministic single-frame selection for the static demo.

    ``--frame`` wins; ``success`` picks the successful frame whose ADD is
    closest to the successful-frame median (a typical case, not the best);
    ``failure`` prefers the explainable roll-symmetry tag, then frame order.
    """
    usable = [f for f in frames if f.overlay_path is not None]
    if frame_num is not None:
        for f in usable:
            if int(f.frame_id.split("/")[-1]) == frame_num:
                return f
        raise ValueError(f"frame {frame_num} has no stored overlay")
    if pick == "success":
        cands = [f for f in usable if f.row.get("pose_success") == "1" and f.row.get("add_mm")]
        if not cands:
            raise ValueError("no successful frames with overlays")
        med = statistics.median(float(f.row["add_mm"]) for f in cands)
        return min(cands, key=lambda f: (abs(float(f.row["add_mm"]) - med), f.frame_id))
    cands = [f for f in usable if f.row.get("failure_tag", "success") != "success"]
    if not cands:
        raise ValueError("no failure frames with overlays")
    cands.sort(key=lambda f: (f.row["failure_tag"] != PREFERRED_FAILURE_TAG, f.frame_id))
    return cands[0]


def caption_lines(
    frame: D.DemoFrame, obj_name: str, method_label: str, summary: dict, run_label: str
) -> list[str]:
    row = frame.row
    scene, num = frame.frame_id.split("/")
    metric_key = str(summary["success_metric"])  # "add" or "adds"
    value_mm = float(row[f"{metric_key}_mm"])
    thresh_mm = float(summary["add_threshold_m"]) * 1e3
    if row.get("pose_success") == "1":
        status = f"{metric_key.upper()} {value_mm:.2f} mm < {thresh_mm:.2f} mm | SUCCESS"
    else:
        extra = f" (ADD-S {float(row['adds_mm']):.2f} mm)" if metric_key == "add" else ""
        status = f"{metric_key.upper()} {value_mm:.2f} mm >= {thresh_mm:.2f} mm | FAIL: {row['failure_tag']}{extra}"
    return [
        f"{method_label} | obj{frame.obj_id} {obj_name}",
        f"run {run_label} | scene {int(scene)} / frame {int(num)}",
        status,
        LEGEND_LINE,
    ]


def run_gt_sanity_check(data_root: Path, frame_id: str, obj_id: int, scene: int, gt_min: float) -> float:
    """GT-overlay convention check (units/pose convention guard). Mandatory."""
    ds = YcbvBopDataset(data_root, obj_ids=(obj_id,), scene_ids=[scene], load_masks=True, n_model_points=1000)
    frac = D.gt_overlay_in_mask_fraction(ds, D.dataset_index_for(ds, frame_id), obj_id)
    if frac < gt_min:
        raise RuntimeError(
            f"GT overlay convention check FAILED: in-mask fraction {frac:.3f} < {gt_min} "
            f"for {frame_id} obj{obj_id} — a units/coordinate bug would make the demo lie"
        )
    return frac


def merge_manifest(out_dir: Path, update: dict) -> Path:
    """Merge-update demo_manifest.json so separate builds accumulate."""
    path = out_dir / "demo_manifest.json"
    current: dict = {}
    if path.is_file():
        current = json.loads(path.read_text(encoding="utf-8"))
    for key, value in update.items():
        if isinstance(value, dict) and isinstance(current.get(key), dict):
            current[key].update(value)
        else:
            current[key] = value
    path.write_text(json.dumps(current, indent=2) + "\n", encoding="utf-8")
    return path


def build(args: argparse.Namespace) -> int:
    run_dir = resolve_run_dir(args.experiment)
    summary = load_run_summary(run_dir, args.object)
    obj_name = load_obj_names(args.data_root)[args.object]
    run_label = f"{run_dir.parent.name}/{run_dir.name}"
    frames = D.load_p2_3_run(run_dir, args.object)
    if args.scene is not None:
        prefix = f"{args.scene:06d}/"
        frames = [f for f in frames if f.frame_id.startswith(prefix)]
        if not frames:
            raise ValueError(f"no frames for scene {args.scene} obj{args.object}")
    out_dir = Path(args.output)
    out_dir.mkdir(parents=True, exist_ok=True)
    manifest: dict = {
        "experiment": args.experiment,
        "run_dir": str(run_dir),
        "object": args.object,
        "obj_name": obj_name,
        "success_metric": summary["success_metric"],
        "threshold_mm": round(float(summary["add_threshold_m"]) * 1e3, 2),
        "method_label": args.method_label,
        "fps": args.fps,
        "outputs": {},
    }
    produced = 0

    if args.mode in ("static", "all"):
        frame = pick_static_frame(frames, args.pick, args.frame)
        scene = int(frame.frame_id.split("/")[0])
        frac = run_gt_sanity_check(Path(args.data_root), frame.frame_id, args.object, scene, args.gt_min)
        img = D.annotate_frame(
            D.read_overlay_bgr(frame),
            caption_lines(frame, obj_name, args.method_label, summary, run_label),
        )
        num = int(frame.frame_id.split("/")[-1])
        out_path = out_dir / f"static_{args.pick}_frame{num:06d}.png"
        cv2.imwrite(str(out_path), img)
        manifest["gt_check_frame"] = frame.frame_id
        manifest.setdefault("static", {})[args.pick] = {
            "frame_id": frame.frame_id,
            "failure_tag": frame.row.get("failure_tag"),
            "gt_in_mask_fraction": round(frac, 4),
            "output": str(out_path),
        }
        manifest["outputs"][f"static_{args.pick}"] = str(out_path)
        produced += 1
        print(f"[static] {frame.frame_id} ({frame.row.get('failure_tag')}) -> {out_path}  gt_in_mask={frac:.3f}")

    if args.mode in ("sequence", "all"):
        window = D.select_range(frames, args.start_frame, args.end_frame)
        if not window:
            raise ValueError("empty frame window (no stored overlays in range)")
        scene = int(window[0].frame_id.split("/")[0])
        frac = run_gt_sanity_check(Path(args.data_root), window[0].frame_id, args.object, scene, args.gt_min)
        annotated = [
            D.annotate_frame(
                D.read_overlay_bgr(f),
                caption_lines(f, obj_name, args.method_label, summary, run_label),
            )
            for f in window
        ]
        start_num = int(window[0].frame_id.split("/")[-1])
        end_num = int(window[-1].frame_id.split("/")[-1])
        mp4_path = out_dir / f"sequence_frame{start_num:06d}-{end_num:06d}.mp4"
        n_written = D.encode_video(annotated, mp4_path, fps=args.fps)
        n_success = sum(1 for f in window if f.row.get("failure_tag") == "success")
        manifest["outputs"]["sequence_mp4"] = str(mp4_path)
        manifest["sequence"] = {
            "frames": [f.frame_id for f in window],
            "n_frames": len(window),
            "n_success": n_success,
            "gt_in_mask_fraction": round(frac, 4),
            "gt_check_frame": window[0].frame_id,
            "failure_tags_in_window": sorted({f.row["failure_tag"] for f in window if f.row["failure_tag"] != "success"}),
        }
        produced += 1
        print(
            f"[sequence] {len(window)} frames ({start_num}..{end_num}, {n_success} success) "
            f"-> {mp4_path}  gt_in_mask={frac:.3f}"
        )

        # README-friendly preview: evenly spaced raw overlays, time order.
        k = min(args.filmstrip_frames, len(window))
        idx = sorted({round(i * (len(window) - 1) / (k - 1)) for i in range(k)}) if k > 1 else [0]
        strip_frames = [D.read_overlay_bgr(window[i]) for i in idx]
        strip_labels = [f"frame {int(window[i].frame_id.split('/')[-1])}" for i in idx]
        preview = D.build_filmstrip(strip_frames, labels=strip_labels, cols=args.filmstrip_cols)
        preview_path = out_dir / "sequence_preview.jpg"
        cv2.imwrite(str(preview_path), preview, [int(cv2.IMWRITE_JPEG_QUALITY), 88])
        manifest["outputs"]["sequence_preview"] = str(preview_path)
        produced += 1
        print(f"[filmstrip] {len(idx)} frames -> {preview_path}")

    manifest_path = merge_manifest(out_dir, manifest)
    print(f"[manifest] {manifest_path} ({produced} artifact(s) this run)")
    return 0


def main(argv=None) -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--experiment", required=True, help="run dir path, or experiment name under outputs/")
    parser.add_argument("--object", type=int, required=True, help="BOP object id (e.g. 5 bottle, 13 bowl)")
    parser.add_argument("--scene", type=int, default=None, help="restrict to one scene id")
    parser.add_argument("--mode", choices=("static", "sequence", "all"), default="all")
    parser.add_argument("--pick", choices=("success", "failure"), default="success", help="static auto-pick rule")
    parser.add_argument("--frame", type=int, default=None, help="explicit frame number for static (overrides --pick)")
    parser.add_argument("--start-frame", type=int, default=None, help="sequence window start (frame number)")
    parser.add_argument("--end-frame", type=int, default=None, help="sequence window end (inclusive)")
    parser.add_argument("--fps", type=float, default=5.0, help="MP4 playback rate")
    parser.add_argument("--filmstrip-frames", type=int, default=8, help="frames in the filmstrip preview")
    parser.add_argument("--filmstrip-cols", type=int, default=4, help="filmstrip columns")
    parser.add_argument("--output", default="outputs/demo", help="demo artifact output directory")
    parser.add_argument("--method-label", default="Classical baseline: PCA/OBB 24-hyp + point-to-plane ICP")
    parser.add_argument("--data-root", default="data/ycbv", help="BOP data root for the GT sanity check")
    parser.add_argument("--gt-min", type=float, default=0.8, help="minimum GT in-mask fraction (convention guard)")
    args = parser.parse_args(argv)
    raise SystemExit(build(args))


if __name__ == "__main__":
    main()
