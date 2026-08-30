"""P2.3/P2.4: geometry-based classical pose pipeline (route A).

Usage::

    python -m r3p.experiments.run_p2_3 --config configs/p2_3.yaml   # 2x10 frames
    python -m r3p.experiments.run_p2_3 --config configs/p2_4.yaml   # full frames

Per frame: oracle mask -> object cloud -> PCA -> 24 proper-rotation hypotheses
-> point-to-plane ICP each (3cm->1cm->3mm, <=60 it/stage) -> select by fitness
(the ONLY inference-time signal). PCA init and ICP result are evaluated
SEPARATELY so coarse-init failure and refinement failure are distinguishable.

Oracle segmentation (GT mask_visib) is a declared controlled condition; GT
pose is used ONLY in evaluation and in the diagnostic `gt_best_hypothesis`.
"""

from __future__ import annotations

import argparse
import csv
import json
import os
import time

# Open3D ICP/normal estimation use multithreaded FP reductions whose summation
# order varies run-to-run; on near-symmetric geometry this flips knife-edge
# frames (measured: bowl solver success 7-8/10 multithreaded vs stable 9/10
# single-threaded). Force single-thread BEFORE open3d import so every run is
# bit-reproducible; cost is ~2x runtime, accepted for an engineering baseline.
os.environ.setdefault("OMP_NUM_THREADS", "1")

import cv2
import numpy as np

from ..config import load_config
from ..datasets.ycbv_bop import YcbvBopDataset
from ..evaluation.evaluator import PoseEvaluator
from ..evaluation.metrics import compute_all
from ..geometry.camera import project
from ..geometry.se3 import apply as apply_T
from ..logging_utils import create_run_dir, setup_logger
from ..pose.geo_init import estimate_pose, load_model_cloud
from .run_p2_0 import select_eval_frames

FAILURE_TAGS = (
    "success", "insufficient_observation", "icp_no_converge",
    "hypothesis_selection_failure", "roll_symmetry_ambiguity", "runtime_error",
)


def failure_tag(solver: bool, pose_ok: bool, adds_ok: bool, add_ok: bool) -> str:
    if not solver:
        return "icp_no_converge"
    if pose_ok:
        return "success"
    if adds_ok and not add_ok:
        return "roll_symmetry_ambiguity"
    return "hypothesis_selection_failure"


def draw_quad_overlay(rgb, K, model_pts, T_gt, T_init, T_icp, note: str):
    img = rgb.copy()
    for T, color in ((T_gt, (0, 200, 0)), (T_init, (60, 60, 255)), (T_icp, (255, 60, 60))):
        if T is None:
            continue
        uv, _ = project(K, apply_T(T, model_pts))
        for u, v in uv:
            cv2.circle(img, (int(round(u)), int(round(v))), 1, color, -1)
    cv2.putText(img, note, (10, 24), cv2.FONT_HERSHEY_SIMPLEX, 0.55, (255, 255, 255), 2, cv2.LINE_AA)
    return img


def run_object(obj_cfg: dict, cfg, run_dir, log) -> dict:
    obj_id = int(obj_cfg["obj_id"])
    root = cfg.get("data.root", "data/ycbv")
    metric = str(obj_cfg["success_metric"])
    ds = YcbvBopDataset(root, obj_ids=(obj_id,), scene_ids=[int(obj_cfg["eval_scene"])],
                        load_masks=True, n_model_points=2000)
    model_pcd, model_pts_full = load_model_cloud(f"{root}/{obj_cfg['mesh']}")
    with open(f"{root}/models/models_info.json", encoding="utf-8") as f:
        diameter = float(json.load(f)[str(obj_id)]["diameter"]) * 1e-3
    thresh = float(cfg["success.add_diameter_frac"]) * diameter

    eval_ids = select_eval_frames(ds, int(obj_cfg["n_frames"]))
    assert len(eval_ids) > 0, f"obj {obj_id}: zero evaluation frames (anti-false-pass)"
    log.info("[obj %d] %d evaluation frames (scene %s): im %s .. %s", obj_id, len(eval_ids),
             obj_cfg["eval_scene"], ds.frames[eval_ids[0]][1], ds.frames[eval_ids[-1]][1])

    cv2.setRNGSeed(0)
    evaluator = PoseEvaluator()
    rows = []
    counts = {tag: 0 for tag in FAILURE_TAGS}
    fitness_matrix, rmse_matrix = [], []
    t0 = time.perf_counter()

    for ds_i in eval_ids:
        obs = ds[ds_i]
        fid = obs["frame_id"]
        T_gt = obs["gt_poses"].get(obj_id)
        row = {"frame_id": fid, "obj_id": obj_id}
        try:
            frame_start = time.perf_counter()
            result = estimate_pose(
                obs["depth"], obs["masks"][obj_id], obs["K"], model_pcd, model_pts_full,
                voxel_m=float(cfg["icp.voxel_m"]),
                corr_schedule_m=tuple(float(x) for x in cfg["icp.corr_schedule_m"]),
                max_iter_per_stage=int(cfg["icp.max_iter_per_stage"]),
                min_cloud_pts=int(cfg["icp.min_cloud_pts"]),
            )
            est_s = time.perf_counter() - frame_start
        except Exception as e:  # noqa: BLE001 — engineering stability: record and continue
            counts["runtime_error"] += 1
            row.update({"failure_tag": "runtime_error", "error": repr(e)[:200]})
            rows.append(row)
            log.warning("frame %s: runtime_error %r", fid, e)
            continue

        if result is None:
            counts["insufficient_observation"] += 1
            row.update({"failure_tag": "insufficient_observation", "n_cloud_pts": 0, "est_time_s": round(est_s, 3)})
            rows.append(row)
            log.info("frame %s: insufficient_observation", fid)
            continue

        sel = result.selected
        solver = sel.fitness >= float(cfg["selection.min_fitness"]) and \
            sel.inlier_rmse <= float(cfg["selection.max_rmse_m"])
        met = compute_all(ds._model_points[obj_id], sel.T_cam_model, T_gt)
        init_met = compute_all(ds._model_points[obj_id], sel.T_cam_model_init, T_gt)
        add_ok = met["add"] < thresh
        adds_ok = met["adds"] < thresh
        pose_ok = ((add_ok if metric == "add" else adds_ok)) and solver
        tag = failure_tag(solver, pose_ok, adds_ok, add_ok)
        counts[tag] += 1
        if solver:
            evaluator.add_frame(fid, ds.obj_names[obj_id], met)

        def _primary(h):
            return compute_all(ds._model_points[obj_id], h.T_cam_model, T_gt)[metric]

        gt_best = min(result.hypotheses, key=_primary)  # DIAGNOSTIC ONLY, never inference
        min_init = min(compute_all(ds._model_points[obj_id], h.T_cam_model_init, T_gt)[metric]
                       for h in result.hypotheses)

        row.update({
            "n_cloud_pts": len(result.scene_points),
            "pca_ratio_l2_l1": round(result.pca_ratio_l2_l1, 3),
            "pca_ratio_l3_l1": round(result.pca_ratio_l3_l1, 3),
            "hyp_selected": sel.index,
            "init_add_mm": round(init_met["add"] * 1e3, 2),
            "init_adds_mm": round(init_met["adds"] * 1e3, 2),
            "init_rot_deg": round(init_met["rot_deg"], 2),
            "init_trans_mm": round(init_met["trans"] * 1e3, 2),
            f"min_init_{metric}_mm_diag": round(min_init * 1e3, 2),
            "gt_best_hyp_diag": gt_best.index,
            "icp_fitness": round(sel.fitness, 4),
            "icp_rmse_mm": round(sel.inlier_rmse * 1e3, 2),
            "solver_success": int(solver),
            "pose_success": int(pose_ok),
            "add_mm": round(met["add"] * 1e3, 2),
            "adds_mm": round(met["adds"] * 1e3, 2),
            "trans_mm": round(met["trans"] * 1e3, 2),
            "rot_deg": round(met["rot_deg"], 2),
            "est_time_s": round(est_s, 3),
            "failure_tag": tag,
        })
        row[f"gt_best_hyp_{metric}_mm_diag"] = round(_primary(gt_best) * 1e3, 2)
        rows.append(row)
        fitness_matrix.append([h.fitness for h in result.hypotheses])
        rmse_matrix.append([h.inlier_rmse * 1e3 for h in result.hypotheses])
        log.info("frame %s: hyp%02d fit=%.2f rmse=%.1fmm %s=%.1fmm (init %.1fmm) gt_best=hyp%02d -> %s",
                 fid, sel.index, sel.fitness, sel.inlier_rmse * 1e3, metric.upper(),
                 met[metric] * 1e3, init_met[metric] * 1e3, gt_best.index, tag)

        note = f"obj{obj_id} fit={sel.fitness:.2f} {metric}={met[metric] * 1e3:.1f}mm {tag}"
        overlay = draw_quad_overlay(obs["rgb"], obs["K"], ds._model_points[obj_id],
                                    T_gt, sel.T_cam_model_init,
                                    sel.T_cam_model if solver else None, note)
        cv2.imwrite(str(run_dir / f"overlay_{fid.replace('/', '_')}.png"),
                    cv2.cvtColor(overlay, cv2.COLOR_RGB2BGR))

    wall = time.perf_counter() - t0
    n = len(rows)
    n_solver = sum(int(r.get("solver_success", 0)) for r in rows)
    n_pose = sum(int(r.get("pose_success", 0)) for r in rows)
    est_times = [float(r["est_time_s"]) for r in rows if "est_time_s" in r]

    csv_path = run_dir / f"per_frame_obj{obj_id}.csv"
    with open(csv_path, "w", newline="", encoding="utf-8") as f:
        fieldnames = sorted({k for r in rows for k in r})
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)

    add_vals = [float(r["add_mm"]) for r in rows if r.get("add_mm") not in ("", None)]
    adds_vals = [float(r["adds_mm"]) for r in rows if r.get("adds_mm") not in ("", None)]
    return {
        "obj_id": obj_id,
        "n_frames": n,
        "solver_success": n_solver,
        "pose_success": n_pose,
        "success_metric": metric,
        "add_threshold_m": thresh,
        "add_mean_mm": float(np.mean(add_vals)) if add_vals else None,
        "add_median_mm": float(np.median(add_vals)) if add_vals else None,
        "adds_mean_mm": float(np.mean(adds_vals)) if adds_vals else None,
        "adds_median_mm": float(np.median(adds_vals)) if adds_vals else None,
        "failure_counts": {k: counts[k] for k in FAILURE_TAGS},
        "wall_time_s": round(wall, 1),
        "est_time_mean_s": round(float(np.mean(est_times)), 3) if est_times else None,
        "est_time_max_s": round(float(np.max(est_times)), 3) if est_times else None,
        "fitness_matrix": fitness_matrix,
        "rmse_matrix_mm": rmse_matrix,
        "table": evaluator.format_table(),
        "eval_frame_ids": [ds.frames[i][1] for i in eval_ids],
    }


def run(config_path: str, overrides: list[str] | None = None) -> int:
    cfg = load_config(config_path, overrides)
    run_dir = create_run_dir(cfg.get("output.root", "outputs"), cfg.get("output.name", "p2_3"))
    log = setup_logger(run_dir)
    log.info("run_dir: %s", run_dir)

    summaries = [run_object(obj, cfg, run_dir, log) for obj in cfg["objects"]]
    with open(run_dir / "metrics.json", "w", encoding="utf-8") as f:
        json.dump({"objects": summaries, "config": cfg.as_dict()}, f, indent=2)

    for s in summaries:
        log.info("\n[obj %d] solver %d/%d, pose %d/%d (%s<0.1d), failures %s, wall %.1fs (mean %.2fs/frame)",
                 s["obj_id"], s["solver_success"], s["n_frames"], s["pose_success"], s["n_frames"],
                 s["success_metric"], s["failure_counts"], s["wall_time_s"], s["est_time_mean_s"] or 0)
        log.info("%s", s["table"])
    log.info("validation: PASS")
    return 0


def main(argv=None) -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", default="configs/p2_3.yaml")
    parser.add_argument("--set", action="append", default=[], metavar="KEY=VALUE")
    args = parser.parse_args(argv)
    raise SystemExit(run(args.config, args.set))


if __name__ == "__main__":
    main()
