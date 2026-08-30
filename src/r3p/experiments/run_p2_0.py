"""P2.0 feasibility spike: SIFT + PnP-RANSAC on 10 fixed YCB-V frames (CPU).

Usage::

    python -m r3p.experiments.run_p2_0 --config configs/p2_0.yaml

Answers feasibility question A (can SIFT features establish stable 2D-3D
correspondences to the object model?) and produces the first PnP baseline
numbers on real data. Validation vs research results, explicitly:

  - validation (exit code): pipeline ran end-to-end, every frame processed,
    per-frame sanity (solver-success frames must have small reprojection
    residuals — a convention/units bug indicator)
  - research output (NOT an exit criterion): match counts, inlier counts,
    pose success rate at ADD < 0.1*d — reported as measured.
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
from ..pose.sift_pnp import build_reference, match_query, solve_pnp


def parse_args(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", default="configs/p2_0.yaml")
    parser.add_argument("--set", action="append", default=[], metavar="KEY=VALUE")
    return parser.parse_args(argv)


def select_eval_frames(dataset, n_frames: int) -> list[int]:
    """Evenly spaced indices over the im_id-sorted frame list (deterministic)."""
    n = len(dataset)
    if n == 0:
        raise RuntimeError("empty evaluation index")
    if n <= n_frames:
        return list(range(n))
    idx = np.linspace(0, n - 1, n_frames).round().astype(int)
    idx = sorted(set(idx.tolist()))
    while len(idx) < n_frames:  # rounding may collide; fill from unused tail
        extra = next(j for j in range(n) if j not in idx)
        idx = sorted(idx + [extra])
    return idx


def draw_overlay(rgb, K, model_points, T_gt, T_est, note: str):
    img = rgb.copy()
    if T_gt is not None:
        uv, _ = apply_T_and_project(K, model_points, T_gt)
        for u, v in uv:
            cv2.circle(img, (int(round(u)), int(round(v))), 1, (0, 200, 0), -1)
    if T_est is not None:
        uv, _ = apply_T_and_project(K, model_points, T_est)
        for u, v in uv:
            cv2.circle(img, (int(round(u)), int(round(v))), 1, (255, 60, 60), -1)
    cv2.putText(img, note, (10, 24), cv2.FONT_HERSHEY_SIMPLEX, 0.55, (255, 255, 255), 2, cv2.LINE_AA)
    return img


def apply_T_and_project(K, points, T):
    from ..geometry.camera import project

    P_cam = apply_T(T, points)
    return project(K, P_cam)


def run(config_path: str, overrides: list[str] | None = None) -> int:
    cfg = load_config(config_path, overrides)
    run_dir = create_run_dir(cfg.get("output.root", "outputs"), "p2_0")
    log = setup_logger(run_dir)
    log.info("run_dir: %s", run_dir)

    obj_id = int(cfg["evaluation.obj_id"])
    diameter = None
    eval_ds = YcbvBopDataset(
        cfg.get("data.root", "data/ycbv"),
        obj_ids=(obj_id,),
        scene_ids=[int(cfg["evaluation.scene"])],
        require_objects=True,
        load_masks=True,
        n_model_points=2000,
    )
    import json as _json

    info = _json.loads((eval_ds.data_root / "models" / "models_info.json").read_text(encoding="utf-8"))
    diameter = float(info[str(obj_id)]["diameter"]) * 1e-3
    add_thresh = float(cfg["success.add_diameter_frac"]) * diameter

    eval_ids = select_eval_frames(eval_ds, int(cfg["evaluation.n_frames"]))
    log.info("evaluation frames (%d/%d selected, scene %s): %s",
             len(eval_ids), len(eval_ds), cfg["evaluation.scene"],
             [eval_ds.frames[i][1] for i in eval_ids])
    assert len(eval_ids) > 0, "zero evaluation frames selected (anti-false-pass guard)"

    ref_scene = int(cfg["reference.scene"])
    ref_ds = YcbvBopDataset(
        cfg.get("data.root", "data/ycbv"), obj_ids=(obj_id,), scene_ids=[ref_scene],
        require_objects=True, load_masks=True,
    )
    library = build_reference(ref_ds, ref_scene, obj_id, n_ref_frames=int(cfg["reference.n_frames"]))
    log.info(
        "reference library: obj %d, %d descriptors from %d frames %s (per-frame %s)",
        obj_id, len(library), len(library.frame_ids), library.frame_ids, library.per_frame_counts,
    )

    cv2.setRNGSeed(int(cfg["pnp.rng_seed"]))
    sift = cv2.SIFT_create()
    evaluator = PoseEvaluator()
    rows = []
    sanity_ok = True

    for k, ds_i in enumerate(eval_ids):
        obs = eval_ds[ds_i]
        m = match_query(obs["rgb"], library, mask_query=obs["masks"].get(obj_id),
                        ratio=float(cfg["sift.ratio"]), sift=sift)
        # PnP uses in-mask matches only (GT segmentation is an allowed input, D2)
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
            "lib_size": m.n_library,
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
            "frame %s: kp=%d good=%d in_mask=%d inliers=%d res=%.2fpx solver=%s pose=%s "
            + ("add=%.1fmm" % (metrics["add"] * 1e3) if metrics else "add=n/a"),
            row["frame_id"], row["query_kp"], row["matches_good"], row["matches_in_mask"],
            row["pnp_inliers"], pnp.residual_px if pnp.success else float("nan"),
            row["solver_success"], row["pose_success"],
        )

        note = f"obj{obj_id} inl={row['pnp_inliers']} add={'%.1fmm' % (metrics['add'] * 1e3) if metrics else 'NA'}"
        overlay = draw_overlay(obs["rgb"], obs["K"], eval_ds._model_points[obj_id], T_gt, pnp.T, note)
        cv2.imwrite(str(run_dir / f"overlay_{obs['frame_id'].replace('/', '_')}.png"), cv2.cvtColor(overlay, cv2.COLOR_RGB2BGR))
        if k < int(cfg["output.n_draw_matches"]) and m.matches:
            # trainIdx indexes the CONCATENATED library; remap to the first
            # reference segment so drawMatches gets consistent keypoint lists
            seg_frame, seg = next(iter(library.segments.items()))
            r0, r1 = seg["row_range"]
            seg_matches = [
                cv2.DMatch(mt.queryIdx, mt.trainIdx - r0, mt.distance)
                for mt in m.matches
                if r0 <= mt.trainIdx < r1
            ]
            if seg_matches:
                # drawMatches expects queryIdx -> image1, trainIdx -> image2;
                # our DMatch queryIdx points at the query frame
                dbg = cv2.drawMatches(
                    cv2.cvtColor(obs["rgb"], cv2.COLOR_RGB2BGR), m.query_keypoints,
                    cv2.cvtColor(seg["rgb"], cv2.COLOR_RGB2BGR), seg["keypoints"],
                    seg_matches[:120], None, flags=cv2.DrawMatchesFlags_NOT_DRAW_SINGLE_POINTS,
                )
                cv2.imwrite(str(run_dir / f"matches_{obs['frame_id'].replace('/', '_')}.png"), dbg)

        # sanity: a solver-success frame with a huge residual means a convention bug
        if pnp.success and pnp.residual_px > 3 * float(cfg["pnp.reproj_error_px"]):
            log.warning("SANITY: frame %s residual %.2f px >> reproj threshold", obs["frame_id"], pnp.residual_px)
            sanity_ok = False

    # ------------------------------------------------------------------ #
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
        "table": evaluator.format_table(),
        "config": cfg.as_dict(),
        "validation": {"all_frames_processed": len(rows) == len(eval_ids), "residual_sanity": sanity_ok},
    }
    with open(run_dir / "metrics.json", "w", encoding="utf-8") as f:
        json.dump(summary, f, indent=2)

    log.info("\n%s", evaluator.format_table())
    log.info(
        "solver success: %d/%d (%.0f%%) | pose success (ADD<%.1fmm): %d/%d (%.0f%%)",
        n_solver, len(rows), 100 * summary["solver_success_rate"],
        add_thresh * 1e3, n_pose, len(rows), 100 * summary["pose_success_rate"],
    )
    log.info("validation: %s", "PASS" if (sanity_ok and summary["validation"]["all_frames_processed"]) else "FAIL")
    return 0 if (sanity_ok and summary["validation"]["all_frames_processed"]) else 1


def main(argv=None) -> None:
    args = parse_args(argv)
    raise SystemExit(run(args.config, args.set))


if __name__ == "__main__":
    main()
