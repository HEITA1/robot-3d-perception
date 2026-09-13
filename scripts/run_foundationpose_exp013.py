"""EXP-013 runner: FoundationPose feasibility on the 3090 machine.

Usage (on the GPU machine, inside the FoundationPose environment)::

    python scripts/run_foundationpose_exp013.py --check-only
    python scripts/run_foundationpose_exp013.py --backend mock      # laptop chain smoke
    python scripts/run_foundationpose_exp013.py --backend foundationpose \\
        --fp-repo /path/to/FoundationPose --checkpoint-dir /path/to/weights

Behavior:
  1. runs the full environment check (GPU/CUDA/runtime/checkpoints/config);
     exits with the missing-components list if anything is absent
  2. loads the frozen EXP-013 config (frames/object/threshold are immutable)
  3. per frame: BOP -> adapter (validated InferenceInput, zero GT in input)
     -> backend.run_register -> evaluator (unified metrics) -> overlay PNG
  4. writes manifest + per-frame results under
     outputs/phase4_foundationpose/fp_exp004_feasibility/

Anti-fooling guarantees:
  - mock results are flagged is_mock=true and only allowed with --backend mock
    (output folder suffixed _mock)
  - the foundationpose backend never falls back to CPU or to the mock
  - GT pose never enters the inference manifest (structural + recursive check)
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

import cv2  # noqa: E402
import numpy as np  # noqa: E402
import yaml  # noqa: E402

from r3p.datasets.ycbv_bop import YcbvBopDataset  # noqa: E402
from r3p.foundationpose import (  # noqa: E402
    AdapterConfig,
    FoundationPoseAdapter,
    FoundationPoseRuntimeUnavailable,
    MockFoundationPoseBackend,
    assert_no_gt_pose,
)
from r3p.foundationpose.runtime import FoundationPoseRuntime  # noqa: E402
from r3p.foundationpose.evaluator import evaluate_fp_result, save_gt_pred_overlay  # noqa: E402

SMOKE_FRAME = 620  # Stage A bundle: one-frame smoke gate (obj5 / scene 50)


def run_env_checks(args, backend: str) -> bool:
    """Reuse the standalone checker; return True iff everything required is OK."""
    import subprocess

    cmd = [sys.executable, str(Path(__file__).parent / "foundationpose_env_check.py"),
           "--config", args.config]
    if args.fp_repo:
        cmd += ["--fp-repo", args.fp_repo]
    if args.checkpoint_dir:
        cmd += ["--checkpoint-dir", args.checkpoint_dir]
    proc = subprocess.run(cmd, capture_output=True, text=True)
    print(proc.stdout)
    if proc.returncode != 0:
        print(proc.stderr)
        if backend == "foundationpose":
            print("\n[runner] environment check FAILED — resolve the missing components above.")
            print("[runner] no auto-install, no CPU fallback, no mock substitution.")
        else:
            print("[runner] env check FAILED as expected on a CPU laptop; "
                  "mock chain smoke proceeds (results flagged is_mock).")
    return proc.returncode == 0


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", default="configs/fp_exp013.yaml")
    parser.add_argument("--backend", choices=("foundationpose", "mock"), default=None,
                        help="override config backend; 'mock' is for laptop chain smoke only")
    parser.add_argument("--fp-repo", default=os.environ.get("FP_REPO_ROOT", ""))
    parser.add_argument("--checkpoint-dir", default=os.environ.get("FP_CHECKPOINT_DIR", ""))
    parser.add_argument("--check-only", action="store_true",
                        help="run environment checks and exit")
    parser.add_argument("--smoke", action="store_true",
                        help="one-frame smoke gate (frame %d only, outputs to "
                             "smoke_test/, is_smoke=true); requires the "
                             "foundationpose backend" % SMOKE_FRAME)
    args = parser.parse_args()

    cfg = yaml.safe_load(Path(args.config).read_text("utf-8"))
    backend = args.backend or cfg.get("backend", "foundationpose")
    if args.smoke and backend != "foundationpose":
        print("[runner] --smoke validates the REAL FoundationPose runtime; "
              "mock plumbing is covered by pytest, not by smoke. Refusing.")
        sys.exit(2)

    checks_ok = run_env_checks(args, backend)
    if args.check_only:
        sys.exit(0 if checks_ok else 1)
    if not checks_ok and backend == "foundationpose":
        print("[runner] refusing to run: environment incomplete.")
        sys.exit(2)

    out_root = Path(cfg["output"]["root"]) / cfg["output"]["name"]
    if backend == "mock":
        out_root = Path(str(out_root) + "_mock")  # mock never writes official results
    if args.smoke:
        out_root = out_root.parent / "smoke_test"
    out_root.mkdir(parents=True, exist_ok=True)

    frame_ids = [SMOKE_FRAME] if args.smoke else list(cfg["frame_ids"])
    manifest = {
        "experiment_id": cfg["experiment_id"],
        "method": cfg["method"],
        "mode": cfg["mode"],
        "backend": backend,
        "is_mock": backend == "mock",
        "is_smoke": bool(args.smoke),
        "object_id": cfg["object_id"],
        "scene_id": cfg["scene_id"],
        "frame_ids": frame_ids,
        "mask_source": "bop_gt_mask_visib",
        "initialization_mode": "none",
        "gt_pose_usage": "evaluation_only",
        "foundationpose_repo_commit": (cfg.get("foundationpose") or {}).get("repo_commit", "PENDING_3090"),
        "checkpoint_dir": (cfg.get("foundationpose") or {}).get("checkpoint_dir", "PENDING_3090"),
        "environment": "PENDING_3090",
        "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
    }
    assert_no_gt_pose(manifest)

    if backend == "foundationpose":
        # Real runtime wiring (implemented in r3p.foundationpose.runtime; the
        # official checkout is imported lazily and validated by the SMOKE gate
        # on the 3090 — never on this laptop). Records the exact repo commit.
        runtime = FoundationPoseRuntime(
            fp_repo_root=args.fp_repo, checkpoint_dir=args.checkpoint_dir,
        )
        runtime.load_object(cfg["object_id"], Path(cfg["data"]["root"]) / cfg["data"]["mesh"])
        manifest["foundationpose_repo_commit"] = runtime.repo_commit
        manifest["checkpoint_dir"] = str(runtime.checkpoint_dir)
        manifest["environment"] = {
            "python": sys.version.split()[0],
            "note": "full env manifest in env_manifest.txt (CHECK_ENV.sh)",
        }
        assert_no_gt_pose(manifest)

        adapter = FoundationPoseAdapter(AdapterConfig(
            data_root=cfg["data"]["root"],
            obj_id=cfg["object_id"],
            mesh_relpath=cfg["data"]["mesh"],
            depth_scale=cfg["data"]["depth_scale"],
            diameter_m=cfg["success"]["diameter_mm"] * 1e-3,
        ))
        ds = YcbvBopDataset(cfg["data"]["root"], obj_ids=(cfg["object_id"],),
                            scene_ids=[cfg["scene_id"]], load_masks=True)
        by_im = {int(ds.frames[i][1]): i for i in range(len(ds))}

        records, poses = [], {}
        for im in manifest["frame_ids"]:
            obs = ds[by_im[im]]
            inp = adapter.prepare_input(obs, obj_id=cfg["object_id"])
            problems = adapter.validate_input(inp)
            assert not problems, f"validation failed: {problems}"
            t0 = time.time()
            result = runtime.run_register(inp)
            dt = time.time() - t0
            ev = adapter.evaluation_data(obs, obj_id=cfg["object_id"])
            metrics = evaluate_fp_result(result["T_cam_model"], ev)
            save_gt_pred_overlay(inp.rgb, inp.K, ev.model_points_m, ev.gt_pose,
                                 result["T_cam_model"],
                                 out_root / f"overlay_{obs['frame_id'].replace('/', '_')}.png",
                                 title=f"FP {metrics['add_mm']:.2f}mm")
            poses[obs["frame_id"]] = np.asarray(result["T_cam_model"]).tolist()
            records.append({"frame_id": obs["frame_id"], "runtime_s": round(dt, 3), **metrics})
            print(f"  {obs['frame_id']}: FP add={metrics['add_mm']}mm "
                  f"success={metrics['success']} ({dt:.1f}s)")

        manifest["frames"] = records
        manifest["predicted_poses_T_cam_model"] = poses  # camera frame, meters
        n_ok = sum(1 for r in records if r["success"])
        manifest["summary"] = {
            "n_frames": len(records), "n_success": n_ok,
            "note": ("SMOKE gate result — NOT the EXP-013 benchmark"
                     if args.smoke else "EXP-013 frozen protocol result"),
        }
        (out_root / "manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
        if args.smoke:
            (out_root / "prediction_pose.json").write_text(
                json.dumps(poses, indent=2), encoding="utf-8")
            (out_root / "runtime_manifest.json").write_text(json.dumps({
                "foundationpose_repo_commit": manifest["foundationpose_repo_commit"],
                "checkpoint_dir": manifest["checkpoint_dir"],
                "python": manifest["environment"]["python"],
                "smoke_frame": SMOKE_FRAME,
                "gt_pose_used": False,
                "is_smoke": True,
            }, indent=2), encoding="utf-8")
        tag = "SMOKE" if args.smoke else "EXP-013"
        print(f"\n[runner] {tag} complete: {n_ok}/{len(records)} frames "
              f"({'threshold ' + str(cfg['success']['threshold_mm']) + 'mm'})")
        print(f"[runner] manifest: {out_root / 'manifest.json'}")
        if args.smoke:
            print("[runner] smoke != EXP-013: do not quote smoke metrics as benchmark results.")
        return

    # ---------------- mock chain smoke (laptop) ----------------
    adapter = FoundationPoseAdapter(AdapterConfig(
        data_root=cfg["data"]["root"],
        obj_id=cfg["object_id"],
        mesh_relpath=cfg["data"]["mesh"],
        depth_scale=cfg["data"]["depth_scale"],
        diameter_m=cfg["success"]["diameter_mm"] * 1e-3,
    ))
    ds = YcbvBopDataset(cfg["data"]["root"], obj_ids=(cfg["object_id"],),
                        scene_ids=[cfg["scene_id"]], load_masks=True)
    by_im = {int(ds.frames[i][1]): i for i in range(len(ds))}
    backend_obj = MockFoundationPoseBackend()

    records = []
    for im in manifest["frame_ids"]:
        obs = ds[by_im[im]]
        inp = adapter.prepare_input(obs, obj_id=cfg["object_id"])
        problems = adapter.validate_input(inp)
        assert not problems, f"validation failed: {problems}"
        t0 = time.time()
        result = backend_obj.run_register(inp)
        dt = time.time() - t0
        ev = adapter.evaluation_data(obs, obj_id=cfg["object_id"])
        metrics = evaluate_fp_result(result["T_cam_model"], ev)
        from r3p.foundationpose.evaluator import save_gt_pred_overlay as save_overlay
        save_overlay(inp.rgb, inp.K, ev.model_points_m, ev.gt_pose,
                     result["T_cam_model"], out_root / f"overlay_{obs['frame_id'].replace('/', '_')}.png",
                     title=f"MOCK {metrics['add_mm']:.2f}mm")
        records.append({"frame_id": obs["frame_id"], "runtime_s": round(dt, 3),
                        "is_mock": True, **metrics})
        print(f"  {obs['frame_id']}: MOCK add={metrics['add_mm']}mm success={metrics['success']}")

    manifest["frames"] = records
    n_ok = sum(1 for r in records if r["success"])
    manifest["summary"] = {"n_frames": len(records), "n_success": n_ok,
                           "note": "MOCK chain smoke — NOT a FoundationPose result"}
    (out_root / "manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    print(f"\n[runner] MOCK chain smoke complete: {n_ok}/{len(records)} (mock metrics are meaningless)")
    print(f"[runner] manifest: {out_root / 'manifest.json'}")
    print("[runner] mock results are flagged is_mock=true and never enter official results.")


if __name__ == "__main__":
    main()
