"""Phase 0 unified entry: minimal end-to-end smoke experiment (CPU, synthetic).

Usage::

    python -m r3p.experiments.run_smoke --config configs/smoke.yaml [--set key=value ...]

Pipeline: config -> synthetic RGB-D scene -> depth -> point cloud (pinhole) ->
SE(3) perturbations -> ADD / ADD-S / translation / rotation metrics ->
``metrics.json`` + PNG + log under ``outputs/<exp>/<timestamp>/``.

Built-in validation (exit code 0 only if all pass):
1. GT pose self-evaluation is ~zero for all metrics.
2. ADD is non-decreasing across perturbation levels within each set.
3. rot_only: rotation error equals the perturbation angle.
4. trans_only: translation error equals the perturbation magnitude.
"""

from __future__ import annotations

import argparse
import json

import numpy as np

from ..config import load_config
from ..datasets.synthetic import SyntheticSceneDataset
from ..evaluation.evaluator import PoseEvaluator
from ..evaluation.metrics import compute_all
from ..geometry.se3 import compose, make_T, matrix_from_axis_angle
from ..logging_utils import create_run_dir, setup_logger
from ..visualization.viz import save_pose_report_png


def parse_args(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", default="configs/smoke.yaml", help="YAML config path")
    parser.add_argument(
        "--set",
        action="append",
        default=[],
        metavar="KEY=VALUE",
        help="config override, e.g. --set scene.model=cylinder",
    )
    return parser.parse_args(argv)


def perturbed_pose(T_gt, axis, direction, rot_deg: float, trans_m: float):
    """Camera-frame perturbation: ``T_est = DeltaT @ T_gt`` with fixed axis/direction."""
    dR = matrix_from_axis_angle(axis, np.radians(rot_deg))
    d = np.asarray(direction, dtype=np.float64)
    d = d / np.linalg.norm(d)
    return compose(make_T(dR, d * trans_m), T_gt)


def run(config_path: str, overrides: list[str] | None = None) -> int:
    cfg = load_config(config_path, overrides)
    run_dir = create_run_dir(cfg.get("output.root", "outputs"), cfg["experiment.name"])
    log = setup_logger(run_dir)
    log.info("run_dir: %s", run_dir)

    scene = cfg["scene"]
    dataset = SyntheticSceneDataset(
        image_size=tuple(scene["image_size"]),
        intrinsics=scene["intrinsics"],
        model=scene["model"],
        model_size=scene["model_size"],
        gt_rotation_axis=scene["gt_pose"]["rotation"]["axis"],
        gt_rotation_angle_deg=float(scene["gt_pose"]["rotation"]["angle_deg"]),
        gt_translation=scene["gt_pose"]["translation"],
        n_model_points=int(scene["n_model_points"]),
        n_render_points=int(scene["n_render_points"]),
    )
    obs = dataset[0]
    obj = dataset.obj_id
    T_gt = obs["gt_poses"][obj]
    model_pts = obs["model_points"][obj]
    log.info(
        "scene: %s size=%s image=%s model_points=%d render_points=%d",
        scene["model"],
        scene["model_size"],
        tuple(scene["image_size"]),
        len(model_pts),
        dataset.n_render_points,
    )

    # --- check 1: GT pose self-evaluation must be ~zero -------------------
    m_gt = compute_all(model_pts, T_gt, T_gt)
    log.info(
        "GT self-check: add=%.3e adds=%.3e trans=%.3e rot=%.3e deg",
        m_gt["add"], m_gt["adds"], m_gt["trans"], m_gt["rot_deg"],
    )
    gt_ok = (
        m_gt["add"] < 1e-9
        and m_gt["adds"] < 1e-9
        and m_gt["trans"] < 1e-9
        and m_gt["rot_deg"] < 1e-6
    )

    # --- perturbation sweeps ----------------------------------------------
    pert = cfg["perturbation"]
    axis, direction = pert["axis"], pert["direction"]
    results: dict = {"gt_self": m_gt, "sets": {}, "checks": {}}
    evaluator = PoseEvaluator()
    T_worst = None

    for set_name, spec in pert["sets"].items():
        rots = [float(x) for x in spec["rotation_deg"]]
        trans = [float(x) for x in spec["translation_m"]]
        rows = []
        for rot_deg, trans_m in zip(rots, trans):
            T_est = perturbed_pose(T_gt, axis, direction, rot_deg, trans_m)
            m = compute_all(model_pts, T_est, T_gt)
            evaluator.add_frame(f"{set_name}@{rot_deg:.0f}deg/{trans_m * 1e3:.0f}mm", obj, m)
            rows.append(m)
            T_worst = T_est
        results["sets"][set_name] = rows

        add_seq = [r["add"] for r in rows]
        checks = {
            "add_monotonic": bool(all(b >= a - 1e-9 for a, b in zip(add_seq, add_seq[1:]))),
            "rot_exact_max_err": None,
            "trans_exact_max_err": None,
        }
        if set_name == "rot_only":
            checks["rot_exact_max_err"] = max(abs(r["rot_deg"] - rt) for r, rt in zip(rows, rots))
        if set_name == "trans_only":
            checks["trans_exact_max_err"] = max(abs(r["trans"] - tm) for r, tm in zip(rows, trans))
        results["checks"][set_name] = checks

    table = evaluator.format_table()
    log.info("\n%s", table)

    checks_ok = all(c["add_monotonic"] for c in results["checks"].values())
    rot_err = results["checks"]["rot_only"]["rot_exact_max_err"]
    trans_err = results["checks"]["trans_only"]["trans_exact_max_err"]
    if rot_err is not None:
        checks_ok = checks_ok and rot_err < 1e-6
    if trans_err is not None:
        checks_ok = checks_ok and trans_err < 1e-9

    all_ok = bool(gt_ok and checks_ok)
    results["summary"] = evaluator.summary()
    results["config"] = cfg.as_dict()
    results["validation"] = {"gt_self_ok": bool(gt_ok), "checks_ok": bool(checks_ok), "passed": all_ok}

    if cfg.get("output.save_visualization", True):
        viz_path = save_pose_report_png(run_dir / "pose_report.png", obs, T_est=T_worst, title="Phase 0 smoke")
        log.info("visualization: %s", viz_path)

    with open(run_dir / "metrics.json", "w", encoding="utf-8") as f:
        json.dump(results, f, indent=2)

    log.info("validation: %s", "PASS" if all_ok else "FAIL")
    return 0 if all_ok else 1


def main(argv=None) -> None:
    args = parse_args(argv)
    raise SystemExit(run(args.config, args.set))


if __name__ == "__main__":
    main()
