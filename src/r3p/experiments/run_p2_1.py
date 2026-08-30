"""P2.1 feasibility: multi-view rendered template library -> SIFT -> PnP-RANSAC.

Usage::

    python -m r3p.experiments.run_p2_1 --config configs/p2_1.yaml

Held identical to P2.0 (same obj 5, same 10 evaluation frames of scene 50,
same SIFT/ratio/PnP parameters, same ADD<0.1d pose-success definition) so the
only changed variable is the reference library:
  P2.0: 3 real-image frames of scene 52  -> 0/10 solver success
  P2.1: N rendered views of the textured model -> ?

Validation vs research results, same split as P2.0:
  - validation (exit code): all frames processed; template self-consistency
    (3D points reproject onto their own pixels); per-frame residual sanity
  - research output: match/inlier counts, solver & pose success rates.
"""

from __future__ import annotations

import argparse
import csv
import json

import cv2
import numpy as np

from ..config import load_config
from ..datasets.ycbv_bop import YcbvBopDataset
from ..evaluation.evaluator import PoseEvaluator
from ..evaluation.metrics import compute_all
from ..geometry.se3 import apply as apply_T
from ..logging_utils import create_run_dir, setup_logger
from ..pose.render_templates import ReferenceLibraryLite, TexturedModel, build_rendered_library, render_view
from ..pose.sift_pnp import match_query, solve_pnp
from .run_p2_0 import apply_T_and_project, draw_overlay, select_eval_frames


def run(config_path: str, overrides: list[str] | None = None) -> int:
    cfg = load_config(config_path, overrides)
    run_dir = create_run_dir(cfg.get("output.root", "outputs"), "p2_1")
    log = setup_logger(run_dir)
    log.info("run_dir: %s", run_dir)

    obj_id = int(cfg["evaluation.obj_id"])
    root = cfg.get("data.root", "data/ycbv")
    model = TexturedModel.from_ply(f"{root}/{cfg['data.model_ply']}")

    K = None
    eval_ds = YcbvBopDataset(
        root, obj_ids=(obj_id,), scene_ids=[int(cfg["evaluation.scene"])],
        require_objects=True, load_masks=True, n_model_points=2000,
    )
    K = eval_ds[0]["K"]
    image_size = (eval_ds[0]["depth"].shape[0], eval_ds[0]["depth"].shape[1])

    with open(f"{root}/models/models_info.json", encoding="utf-8") as f:
        diameter = float(json.load(f)[str(obj_id)]["diameter"]) * 1e-3
    add_thresh = float(cfg["success.add_diameter_frac"]) * diameter

    # ---- reference: rendered multi-view library --------------------------
    templates, library = build_rendered_library(
        model, K, image_size,
        n_views=int(cfg["reference.n_views"]),
        radius=float(cfg["reference.radius_m"]),
    )
    per_view_kp = [len(t.keypoints or []) for t in templates]
    log.info("rendered library: %d views, %d/%d/%s descriptors=%d, per-view kp=%s",
             len(templates), len(library), len(library), "views", len(library), per_view_kp)
    assert len(library) > 0, "rendered library is empty (anti-false-pass guard)"

    # template self-consistency: stored 3D points must reproject onto their own
    # pixels through the recorded render camera (catches any convention bug)
    max_err = 0.0
    for tpl in templates[:3]:
        if len(tpl.points_model) == 0:
            continue
        uv, _ = apply_T_and_project(K, tpl.points_model, tpl.T_cam_model)
        max_err = max(max_err, float(np.abs(uv - tpl.pixels).max()))
    log.info("template self-consistency: max |reprojection - pixel| = %.2e px (3 views)", max_err)
    consistency_ok = max_err < 1e-2
    # also save one rendered view for the record
    cv2.imwrite(str(run_dir / "template_view0.png"), cv2.cvtColor(templates[0].rgb, cv2.COLOR_RGB2BGR))

    eval_ids = select_eval_frames(eval_ds, int(cfg["evaluation.n_frames"]))
    log.info("evaluation frames (%d/%d, scene %s): %s", len(eval_ids), len(eval_ds),
             cfg["evaluation.scene"], [eval_ds.frames[i][1] for i in eval_ids])
    assert len(eval_ids) > 0, "zero evaluation frames selected (anti-false-pass guard)"

    cv2.setRNGSeed(int(cfg["pnp.rng_seed"]))
    import cv2 as _cv

    sift = _cv.SIFT_create()
    evaluator = PoseEvaluator()
    rows = []
    sanity_ok = True
    lib = ReferenceLibraryLite(descriptors=library.descriptors, points_model=library.points_model)

    for k, ds_i in enumerate(eval_ids):
        obs = eval_ds[ds_i]
        m = match_query(obs["rgb"], lib, mask_query=obs["masks"].get(obj_id),
                        ratio=float(cfg["sift.ratio"]), sift=sift)
        if m.in_mask is not None and m.in_mask.sum() >= 4:
            pnp = solve_pnp(
                m.points_model[m.in_mask], m.points_image[m.in_mask], obs["K"],
                min_inliers=int(cfg["pnp.min_inliers"]),
                reproj_error_px=float(cfg["pnp.reproj_error_px"]),
                iterations=int(cfg["pnp.iterations"]),
                confidence=float(cfg["pnp.confidence"]),
            )
        else:
            pnp = solve_pnp(np.zeros((0, 3)), np.zeros((0, 2)), obs["K"])

        T_gt = obs["gt_poses"].get(obj_id)
        metrics = compute_all(eval_ds._model_points[obj_id], pnp.T, T_gt) if (pnp.success and T_gt is not None) else None
        pose_success = bool(metrics and metrics["add"] < add_thresh)
        if metrics:
            evaluator.add_frame(obs["frame_id"], eval_ds.obj_names[obj_id], metrics)

        row = {
            "frame_id": obs["frame_id"],
            "query_kp": m.n_query_keypoints,
            "lib_size": len(lib),
            "matches_good": m.n_matches_good,
            "matches_in_mask": m.n_matches_in_mask,
            "pnp_inliers": pnp.n_inliers if pnp.success else 0,
            "reproj_px": round(pnp.residual_px, 4) if pnp.success else "",
            "solver_success": int(pnp.success),
            "pose_success": int(pose_success),
            "add_mm": round(metrics["add"] * 1e3, 2) if metrics else "",
            "adds_mm": round(metrics["adds"] * 1e3, 2) if metrics else "",
            "trans_mm": round(metrics["trans"] * 1e3, 2) if metrics else "",
            "rot_deg": round(metrics["rot_deg"], 2) if metrics else "",
        }
        rows.append(row)
        log.info(
            "frame %s: kp=%d good=%d in_mask=%d inliers=%d res=%s solver=%s pose=%s "
            + ("add=%.1fmm" % (metrics["add"] * 1e3) if metrics else "add=n/a"),
            row["frame_id"], row["query_kp"], row["matches_good"], row["matches_in_mask"],
            row["pnp_inliers"], f"{pnp.residual_px:.2f}" if pnp.success else "nan",
            row["solver_success"], row["pose_success"],
        )

        note = f"obj{obj_id} inl={row['pnp_inliers']} add={'%.1fmm' % (metrics['add'] * 1e3) if metrics else 'NA'}"
        overlay = draw_overlay(obs["rgb"], obs["K"], eval_ds._model_points[obj_id], T_gt, pnp.T, note)
        _cv.imwrite(str(run_dir / f"overlay_{obs['frame_id'].replace('/', '_')}.png"),
                    _cv.cvtColor(overlay, _cv.COLOR_RGB2BGR))

        if k < int(cfg["output.n_draw_matches"]) and m.matches:
            # per-template debug matches are skipped in P2.1: trainIdx maps into
            # the concatenated synthetic library, not to a single template frame
            pass
        if pnp.success and pnp.residual_px > 3 * float(cfg["pnp.reproj_error_px"]):
            log.warning("SANITY: frame %s residual %.2f px >> threshold", obs["frame_id"], pnp.residual_px)
            sanity_ok = False

    with open(run_dir / "per_frame.csv", "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)

    n_solver = sum(r["solver_success"] for r in rows)
    n_pose = sum(r["pose_success"] for r in rows)
    summary = {
        "n_frames": len(rows),
        "solver_success_rate": n_solver / len(rows),
        "pose_success_rate": n_pose / len(rows),
        "add_threshold_m": add_thresh,
        "library_descriptors": len(lib),
        "n_views": int(cfg["reference.n_views"]),
        "template_selfconsistency_max_px": max_err,
        "table": evaluator.format_table(),
        "config": cfg.as_dict(),
        "validation": {
            "all_frames_processed": len(rows) == len(eval_ids),
            "residual_sanity": sanity_ok,
            "template_consistency": consistency_ok,
        },
    }
    with open(run_dir / "metrics.json", "w", encoding="utf-8") as f:
        json.dump(summary, f, indent=2)

    log.info("\n%s", evaluator.format_table())
    log.info("solver success: %d/%d (%.0f%%) | pose success (ADD<%.1fmm): %d/%d (%.0f%%)",
             n_solver, len(rows), 100 * summary["solver_success_rate"], add_thresh * 1e3,
             n_pose, len(rows), 100 * summary["pose_success_rate"])
    all_ok = sanity_ok and summary["validation"]["all_frames_processed"] and consistency_ok
    log.info("validation: %s", "PASS" if all_ok else "FAIL")
    return 0 if all_ok else 1


def main(argv=None) -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", default="configs/p2_1.yaml")
    parser.add_argument("--set", action="append", default=[], metavar="KEY=VALUE")
    args = parser.parse_args(argv)
    raise SystemExit(run(args.config, args.set))


if __name__ == "__main__":
    main()
