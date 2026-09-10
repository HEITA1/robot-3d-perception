"""FoundationPose environment checker (run on the 3090 machine).

Prints a component table and exits non-zero if any REQUIRED component for
EXP-013 is missing. Never installs anything.

Usage:
  python scripts/foundationpose_env_check.py [--fp-repo /path/to/FoundationPose] \
      [--checkpoint-dir /path/to/weights] [--config configs/fp_exp013.yaml]
"""

from __future__ import annotations

import argparse
import importlib
import json
import os
import shutil
import sys
from pathlib import Path

ROWS: list[tuple[str, str, str, bool]] = []  # component, current, required, ok


def check(component: str, current: str, required: str, ok: bool) -> bool:
    ROWS.append((component, current, required, bool(ok)))
    return bool(ok)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--fp-repo", default=os.environ.get("FP_REPO_ROOT", ""),
                        help="path to the official NVlabs/FoundationPose checkout")
    parser.add_argument("--checkpoint-dir", default=os.environ.get("FP_CHECKPOINT_DIR", ""),
                        help="path to weights/ (refiner + scorer checkpoints)")
    parser.add_argument("--config", default="configs/fp_exp013.yaml")
    parser.add_argument("--json-out", default="")
    args = parser.parse_args()

    import platform
    check("OS", f"{platform.system()} {platform.release()}", "Linux (recommended)", platform.system() == "Linux")

    import shutil as sh
    gpu = sh.which("nvidia-smi")
    gpu_ok = gpu is not None
    driver = ""
    if gpu_ok:
        import subprocess
        out = subprocess.run(["nvidia-smi", "--query-gpu=name,driver_version,memory.total",
                              "--format=csv,noheader"], capture_output=True, text=True)
        driver = out.stdout.strip()
    check("GPU + driver", driver or "nvidia-smi not found", "NVIDIA GPU, driver >= CUDA build", gpu_ok)

    try:
        import torch
        tv = torch.__version__
        cuda_avail = torch.cuda.is_available()
        cuda_dev = torch.cuda.get_device_name(0) if cuda_avail else "n/a"
    except Exception as e:  # noqa: BLE001
        tv, cuda_avail, cuda_dev = f"import failed: {e}", False, "n/a"
    check("PyTorch", tv, "CUDA build", cuda_avail)
    check("torch.cuda", str(cuda_avail), "True", cuda_avail)
    if cuda_avail:
        check("GPU device", cuda_dev, "RTX 3090 class", True)

    for mod in ("nvdiffrast", "pytorch3d"):
        try:
            importlib.import_module(mod)
            check(f"python: {mod}", "importable", "importable", True)
        except Exception as e:  # noqa: BLE001
            check(f"python: {mod}", f"MISSING ({type(e).__name__})", "importable", False)

    nvcc = sh.which("nvcc")
    check("nvcc (CUDA toolkit)", nvcc or "not found",
          "needed for source builds (unless using docker image)", nvcc is not None)
    for tool in ("gcc", "cmake"):
        check(tool, sh.which(tool) or "not found", "needed for source builds", sh.which(tool) is not None)

    fp_ok = args.fp_repo and (Path(args.fp_repo) / "estimater.py").is_file()
    check("FoundationPose source", args.fp_repo or "not set",
          "official NVlabs/FoundationPose checkout (estimater.py)", bool(fp_ok))

    ckpt_ok = args.checkpoint_dir and Path(args.checkpoint_dir).is_dir()
    ckpt_files = sorted(p.name for p in Path(args.checkpoint_dir).glob("*")) if ckpt_ok else []
    check("checkpoints", args.checkpoint_dir or "not set",
          "weights/ with refiner (2023-10-28-18-33-37) + scorer (2024-01-11-20-02-45)",
          bool(ckpt_ok and ckpt_files))

    dataset_ok = Path("data/ycbv/test/000050").is_dir()
    check("dataset (BOP subset)", "data/ycbv", "test scenes + masks + models", dataset_ok)

    cfg_ok = Path(args.config).is_file()
    check("experiment config", args.config, "frozen EXP-013 config", cfg_ok)

    print(f"\n{'Component':<26}{'Current':<44}{'Required'}")
    print("-" * 100)
    for comp, cur, req, ok in ROWS:
        flag = "OK " if ok else "MISSING"
        print(f"[{flag}] {comp:<20} {cur:<44} {req}")

    required_ok = [r for *_, r in [(c, cu, rq, o) for c, cu, rq, o in ROWS]]
    all_ok = all(o for *_, o in ROWS)
    print(f"\nENV CHECK: {'PASS' if all_ok else 'FAIL'} "
          f"({sum(1 for *_, o in ROWS if o)}/{len(ROWS)} components)")
    if not all_ok:
        missing = [c for c, _, _, o in ROWS if not o]
        print("missing components:", ", ".join(missing))
        print("do NOT auto-install; resolve per docs/PHASE4_PREFLIGHT.md section 2/9.")

    if args.json_out:
        Path(args.json_out).write_text(json.dumps(
            {"rows": [{"component": c, "current": cu, "required": rq, "ok": o}
                      for c, cu, rq, o in ROWS], "all_ok": all_ok}, indent=2), encoding="utf-8")
    sys.exit(0 if all_ok else 1)


if __name__ == "__main__":
    main()
