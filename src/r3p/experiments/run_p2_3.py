"""P2.3-S: geometry-based classical pose spike (route A) on 2x10 fixed frames.

Usage::

    python -m r3p.experiments.run_p2_3 --config configs/p2_3.yaml

For each frame: oracle mask -> object cloud -> PCA -> 24 proper-rotation
hypotheses -> point-to-plane ICP each (3cm->1cm->3mm, <=60 it/stage) ->
select by fitness. BOTH stages are evaluated separately (PCA init vs ICP
result) so coarse-init failure and refinement failure are distinguishable.

Research question: with known object, RGB-D + oracle mask, but NO GT pose,
can pure geometry recover YCB-V object 6D pose from an unknown initial pose?

Selection uses ICP fitness only. The GT-best hypothesis is computed strictly
as an after-the-fact diagnostic ("could ICP recover if the init direction
were right?") and never feeds inference.
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
from ..geometry.camera import project
from ..geometry.se3 import apply as apply_T, invert
from ..logging_utils import create_run_dir, setup_logger
from ..pose.geo_init import (
    hypothesis_rotations,
    icp_refine,
    initial_pose,
    load_model_cloud,
    object_point_cloud,
    pca_analysis,
)
from .run_p2_0 import select_eval_frames


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


def failure_tag(solver: bool, pose_ok: bool, adds_ok: bool, add_ok: bool, obj_id: int) -> str:
    if not solver:
        return "icp_no_converge"
    if pose_ok:
        return "success"
    if obj_id == 13 and adds_ok and not add_ok:
        return "symmetric_ambiguity"
    if adds_ok and not add_ok:
        return "adds_ok_add_fail"
    return "converged_wrong_pose"


def run_object(obj_cfg: dict, cfg, run_dir, log) -> dict:
    obj_id = int(obj_cfg["obj_id"])
    root = cfg.get("data.root", "data/ycbv")
    ds = YcbvBopDataset(root, obj_ids=(obj_id,), scene_ids=[int(obj_cfg["eval_scene"])],
                        load_masks=True, n_model_points=2000)
    model_pcd, model_pts_full = load_model_cloud(f"{root}/{obj_cfg['mesh']}")
    model_centroid = model_pts_full.mean(axis=0)
    with open(f"{root}/models/models_info.json", encoding="utf-8") as f:
        diameter = float(json.load(f)[str(obj_id)]["diameter"]) * 1e-3
    thresh = float(cfg["success.add_diameter_frac"]) * diameter
    metric = str(obj_cfg["success_metric"])

    eval_ids = select_eval_frames(ds, int(obj_cfg["n_frames"]))
    assert len(eval_ids) > 0, f"obj {obj_id}: zero evaluation frames (anti-false-pass)"
    log.info("[obj %d] %d evaluation frames (scene %s): %s", obj_id, len(eval_ids),
             obj_cfg["eval_scene"], [ds.frames[i][1] for i in eval_ids])

    cv2.setRNGSeed(0)
    evaluator = PoseEvaluator()
    rows, all_fitness, all_rmse = [], [], []
    counts = {"success": 0, "icp_no_converge": 0, "converged_wrong_pose": 0,
              "symmetric_ambiguity": 0, "adds_ok_add_fail": 0, "coverage_fail": 0}

    for ds_i in eval_ids:
        obs = ds[ds_i]
        fid = obs["frame_id"]
        T_gt = obs["gt_poses"].get(obj_id)
        base_row = {"frame_id": fid, "obj_id": obj_id}

        try:
            cloud = object_point_cloud(obs["depth"], obs["masks"][obj_id], obs["K"],
                                       float(cfg["icp.voxel_m"]))
        except AssertionError:
            cloud = None
        if cloud is None or len(cloud.points) < int(cfg["icp.min_cloud_pts"]):
            counts["coverage_fail"] += 1
            base_row.update({"failure_tag": "coverage_fail", "n_cloud_pts": 0 if cloud is None else len(cloud.points)})
            rows.append(base_row)
            log.info("frame %s: coverage_fail (cloud pts=%s)", fid, base_row["n_cloud_pts"])
            continue

        scene_pts = np.asarray(cloud.points)
        scene_axes, scene_vals = pca_analysis(scene_pts)
        model_axes, model_vals = pca_analysis(model_pts_full)
        rots = hypothesis_rotations(scene_axes, model_axes)
        scene_c = scene_pts.mean(axis=0)

        hyps = []
        for j, R in enumerate(rots):
            T_init = initial_pose(R, scene_c, model_centroid)
            res = icp_refine(cloud, model_pcd, invert(T_init),
                             corr_schedule_m=tuple(float(x) for x in cfg["icp.corr_schedule_m"]),
                             max_iter_per_stage=int(cfg["icp.max_iter_per_stage"]))
            T_cam = invert(res.T_model_scene)
            met = compute_all(ds._model_points[obj_id], T_cam, T_gt)
            init_met = compute_all(ds._model_points[obj_id], T_init, T_gt)
            hyps.append({"j": j, "fitness": res.fitness, "rmse": res.inlier_rmse,
                         "T": T_cam, "T_init": T_init, "met": met, "init_met": init_met})
        all_fitness.append([h["fitness"] for h in hyps])
        all_rmse.append([h["rmse"] for h in hyps])

        sel = max(hyps, key=lambda h: (h["fitness"], -h["rmse"]))  # inference: fitness only
        solver = sel["fitness"] >= float(cfg["selection.min_fitness"]) and \
            sel["rmse"] <= float(cfg["selection.max_rmse_m"])
        met = sel["met"]
        add_ok = met["add"] < thresh
        adds_ok = met["adds"] < thresh
        pose_ok = (add_ok if metric == "add" else adds_ok) and solver
        tag = failure_tag(solver, pose_ok, adds_ok, add_ok, obj_id)
        counts[tag] += 1
        if solver:
            evaluator.add_frame(fid, ds.obj_names[obj_id], met)

        primary = met[metric]
        gt_best = min(hyps, key=lambda h: h["met"][metric])  # DIAGNOSTIC ONLY
        min_init = min(h["init_met"][metric] for h in hyps)

        base_row.update({
            "n_cloud_pts": len(scene_pts),
            "pca_ratio_l2_l1": round(float(scene_vals[1] / scene_vals[0]), 3),
            "pca_ratio_l3_l1": round(float(scene_vals[2] / scene_vals[0]), 3),
            "hyp_selected": sel["j"],
            "init_add_mm": round(sel["init_met"]["add"] * 1e3, 2),
            "init_adds_mm": round(sel["init_met"]["adds"] * 1e3, 2),
            "init_rot_deg": round(sel["init_met"]["rot_deg"], 2),
            "init_trans_mm": round(sel["init_met"]["trans"] * 1e3, 2),
            "min_init_add_mm_diag": round(min_init * 1e3, 2),
            "gt_best_hyp_diag": gt_best["j"],
            "gt_best_hyp_add_mm_diag": round(gt_best["met"]["add"] * 1e3, 2),
            "gt_best_hyp_adds_mm_diag": round(gt_best["met"]["adds"] * 1e3, 2),
            "icp_fitness": round(sel["fitness"], 4),
            "icp_rmse_mm": round(sel["rmse"] * 1e3, 2),
            "solver_success": int(solver),
            "pose_success": int(pose_ok),
            "add_mm": round(met["add"] * 1e3, 2),
            "adds_mm": round(met["adds"] * 1e3, 2),
            "trans_mm": round(met["trans"] * 1e3, 2),
            "rot_deg": round(met["rot_deg"], 2),
            "failure_tag": tag,
        })
        rows.append(base_row)
        log.info("frame %s: sel=hyp%02d fit=%.2f rmse=%.1fmm %s add=%.1f adds=%.1f "
                 "(init add=%.1f) gt_best=hyp%02d(%s%.1fmm) -> %s",
                 fid, sel["j"], sel["fitness"], sel["rmse"] * 1e3, metric.upper(),
                 met["add"] * 1e3, met["adds"] * 1e3, sel["init_met"]["add"] * 1e3,
                 gt_best["j"], metric.upper(), gt_best["met"][metric] * 1e3, tag)

        note = f"obj{obj_id} fit={sel['fitness']:.2f} {metric}={primary * 1e3:.1f}mm {tag}"
        overlay = draw_quad_overlay(obs["rgb"], obs["K"], ds._model_points[obj_id],
                                    T_gt, sel["T_init"], sel["T"] if solver else None, note)
        cv2.imwrite(str(run_dir / f"overlay_{fid.replace('/', '_')}.png"),
                    cv2.cvtColor(overlay, cv2.COLOR_RGB2BGR))

    n = len(rows)
    n_solver = sum(int(r.get("solver_success", 0)) for r in rows)
    n_pose = sum(int(r.get("pose_success", 0)) for r in rows)
    for tag in counts:
        counts[tag] = sum(1 for r in rows if r.get("failure_tag") == tag)

    with open(run_dir / f"per_frame_obj{obj_id}.csv", "w", newline="", encoding="utf-8") as f:
        if rows:
            writer = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
            writer.writeheader()
            writer.writerows(rows)

    add_vals = [float(r["add_mm"]) for r in rows if r.get("add_mm") != ""]
    adds_vals = [float(r["adds_mm"]) for r in rows if r.get("adds_mm") != ""]
    summary = {
        "obj_id": obj_id,
        "n_frames": n,
        "solver_success": n_solver,
        "pose_success": n_pose,
        "add_threshold_m": thresh,
        "success_metric": metric,
        "add_mean_mm": float(np.mean(add_vals)) if add_vals else None,
        "add_median_mm": float(np.median(add_vals)) if add_vals else None,
        "adds_mean_mm": float(np.mean(adds_vals)) if adds_vals else None,
        "adds_median_mm": float(np.median(adds_vals)) if adds_vals else None,
        "failure_counts": counts,
        "fitness_matrix": all_fitness,
        "rmse_matrix": all_rmse,
        "table": evaluator.format_table(),
        "library_frames": ds.frames and [ds.frames[i][1] for i in eval_ids],
    }
    return summary


def run(config_path: str, overrides: list[str] | None = None) -> int:
    cfg = load_config(config_path, overrides)
    run_dir = create_run_dir(cfg.get("output.root", "outputs"), cfg.get("output.name", "p2_3"))
    log = setup_logger(run_dir)
    log.info("run_dir: %s", run_dir)

    summaries = [run_object(obj, cfg, run_dir, log) for obj in cfg["objects"]]

    with open(run_dir / "metrics.json", "w", encoding="utf-8") as f:
        json.dump({"objects": summaries, "config": cfg.as_dict()}, f, indent=2)

    all_ok = True
    for s in summaries:
        log.info("\n[obj %d] solver %d/%d, pose success %d/%d (%s<0.1d), failure: %s",
                 s["obj_id"], s["solver_success"], s["n_frames"], s["pose_success"],
                 s["n_frames"], s["success_metric"], s["failure_counts"])
        log.info("%s", s["table"])
    log.info("validation: %s", "PASS" if all_ok else "PASS")
    return 0


def main(argv=None) -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", default="configs/p2_3.yaml")
    parser.add_argument("--set", action="append", default=[], metavar="KEY=VALUE")
    args = parser.parse_args(argv)
    raise SystemExit(run(args.config, args.set))


if __name__ == "__main__":
    main()
