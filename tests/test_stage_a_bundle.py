"""Stage A-LOCAL bundle guards (delivery/foundationpose_3090).

Validates what CAN be validated on the CPU laptop: bundle completeness, the
copied frozen config is byte-identical, shell scripts parse (bash -n), the
real-runtime module stays lazy (no FoundationPose import, laptop-safe), and
the runner refuses a mock smoke. Nothing here pretends to execute
FoundationPose — that is the 3090 smoke gate's job.
"""

from __future__ import annotations

import hashlib
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

BASH_AVAILABLE = shutil.which("bash") is not None

BUNDLE = Path("delivery/foundationpose_3090")
SCRIPTS = ("CHECK_ENV.sh", "INSTALL.sh", "PREPARE_DATA.sh", "RUN_SMOKE_TEST.sh",
           "RUN_EXP013.sh", "COLLECT_RESULTS.sh", "DOCKER_SETUP.sh")
DOCS = ("README_3090.md", "MANIFEST.md", "ENVIRONMENT.md", "DATA_MANIFEST.md",
        "DOWNLOAD_WEIGHTS.md", "DOCKER.md", "Dockerfile.r3p-fp",
        "WINDOWS.md", "RUN_ON_WINDOWS.ps1")
GPU_SIDED_SCRIPTS = ("CHECK_ENV.sh", "PREPARE_DATA.sh", "RUN_SMOKE_TEST.sh", "RUN_EXP013.sh")


def test_bundle_completeness():
    for name in SCRIPTS + DOCS:
        assert (BUNDLE / name).is_file(), f"bundle missing {name}"
    assert (BUNDLE / "configs" / "fp_exp013.yaml").is_file()
    assert (BUNDLE / "expected_outputs" / "README.md").is_file()
    assert (BUNDLE / "patches" / "README.md").is_file()


def test_bundle_config_is_byte_identical_to_frozen():
    frozen = Path("configs/fp_exp013.yaml").read_bytes()
    copied = (BUNDLE / "configs" / "fp_exp013.yaml").read_bytes()
    assert hashlib.sha256(frozen).hexdigest() == hashlib.sha256(copied).hexdigest()


def test_locked_execution_script_states_lock():
    text = (BUNDLE / "RUN_EXP013.sh").read_text(encoding="utf-8")
    assert "EXECUTION_LOCKED=true" in text
    assert "CONFIRM_EXP013=YES" in text


def test_install_handles_conda_tos_and_offline():
    """Locked-in fixes from three 3090 field incidents:
    #1 new conda's ToS gate (online fallback keeps the accept + conda-forge
    fallback); #2 ToS also blocks --offline; #3 channel drift made packaged
    closures unsolvable — final design extracts packages directly into the
    env prefix (no solver) and bootstraps pip via ensurepip."""
    text = (BUNDLE / "INSTALL.sh").read_text(encoding="utf-8")
    assert "extract_conda_pkgs.py" in text, "offline extraction path missing"
    assert "ensurepip" in text, "pip bootstrap missing"
    # incident #5: bare `python` does not exist in WSL Ubuntu (and system
    # python3 has no pip) — BPY must be the miniconda base python, with an
    # explicit existence check (silent set -e death otherwise).
    assert 'BPY="$CONDA_BASE/bin/python"' in text
    assert '[ -x "$BPY" ] || die' in text
    assert 'conda tos accept' in text, "online-fallback ToS fix missing"
    assert "conda-forge --override-channels" in text
    assert "--no-index --find-links" in text
    assert "nvcc_pkgs" in text and "tar -xjf" in text  # offline nvcc via conda pkg extraction
    assert "cuda_runtime.h" in text  # cudart-dev header guard
    assert "cccl_include" in text  # CCCL headers (nv/target, thrust, cub, cuda) shipped offline
    assert '"$PYTHON" -m pip install' in text  # no reliance on env pip script
    # incident #7/#8: partial torch install (crashed wheel) was masked by pip's
    # "already satisfied" — INSTALL must health-check torch._C and force-reinstall
    # WITH dependencies (incident #8: --no-deps skipped typing_extensions etc.,
    # all of which ARE in the offline wheels).
    assert "import torch, torch._C" in text
    assert "--force-reinstall torch==2.6.0 torchvision==0.21.0 torchaudio==2.6.0" in text
    assert "--force-reinstall --no-deps" not in text
    # full-review fixes: conda toolchain shipped offline (3090 has NO network —
    # apt route retired), mycpp compiled via Ninja, compiler gate checks prefix
    assert "mycpp" in text and "-G Ninja" in text  # estimater's cluster_poses needs mycpp
    assert "ln -sf x86_64-conda-linux-gnu-gcc" in text  # bare gcc/g++ symlinks (env_check + JIT look them up by bare name)
    assert "CPATH" in text  # nvidia wheel headers (cusparse.h etc.) fed to gcc/nvcc
    assert "pybind11_DIR" in text  # noarch pybind11 cmake config lives under site-packages
    assert "x86_64-conda-linux-gnu-gcc" in text  # conda toolchain exported as CC/CXX
    ps1 = (BUNDLE / "RUN_ON_WINDOWS.ps1").read_text(encoding="utf-8")
    assert "Miniconda3-latest-Linux-x86_64.sh" in ps1  # offline installer support
    assert 'FP_REPO_ROOT="' in ps1  # install passes the FP location (install/smoke consistency)


def test_bundle_scripts_are_lf_only():
    """CRLF breaks bash on Linux/WSL ('pipefail\\r: invalid option name' —
    3090 field incident #4, introduced by a Windows text-mode rewrite). MSYS
    bash -n tolerates CRLF, so this byte-level check is the reliable guard."""
    for name in SCRIPTS:
        data = (BUNDLE / name).read_bytes()
        assert b"\r" not in data, f"{name} contains CR bytes (must be LF only)"


def test_offline_package_manifest_present():
    """offline_packages contents are carried by USB (gitignored) — the docs
    must describe them and the weights must be present + hash-recorded."""
    windows = (BUNDLE / "WINDOWS.md").read_text(encoding="utf-8")
    assert "offline_packages/" in windows
    ckpt = (BUNDLE / "expected_outputs" / "checkpoints_README.md").read_text(encoding="utf-8")
    assert "1DFezOAD0oD1BblsXVxqDsl8fj0qzB82i" in ckpt  # official Google Drive folder id
    assert "已下载入包" in ckpt  # weights received (2026-09-14), no longer PENDING
    sha_path = Path("offline_packages/checkpoints/checkpoints_sha256.txt")
    if sha_path.is_file():  # on the USB copy
        content = sha_path.read_text(encoding="utf-8")
        assert "model_best.pth" in content  # both checkpoints hash-recorded
        assert len(content.strip().splitlines()) >= 4


def test_docker_isolation_is_default_path():
    """Shared 3090 (Linux): every GPU-side script defaults to docker re-exec
    (USE_DOCKER=1) with the official base image wired in the Dockerfile —
    except under WSL2, where the Windows route runs natively."""
    for name in GPU_SIDED_SCRIPTS:
        text = (BUNDLE / name).read_text(encoding="utf-8")
        assert 'USE_DOCKER:-1' in text, f"{name} missing docker-default preamble"
        assert "INSIDE_CONTAINER" in text
        assert 'WSL_DISTRO_NAME:-' in text, f"{name} must force native under WSL2 (Windows route)"
    dockerfile = (BUNDLE / "Dockerfile.r3p-fp").read_text(encoding="utf-8")
    assert "FROM wenbowen123/foundationpose:" in dockerfile
    assert "--no-deps" in dockerfile  # never touch the base image's torch/CUDA tree


def test_windows_route_bundle():
    """Windows/WSL2 is the primary path: bootstrap wrapper + route doc exist,
    the wrapper stays native (USE_DOCKER=0) and gated for EXP-013."""
    windows = (BUNDLE / "WINDOWS.md").read_text(encoding="utf-8")
    assert "WSL2" in windows and "10–15 GB" in windows
    assert "smoke gate" in windows.lower()
    ps1 = (BUNDLE / "RUN_ON_WINDOWS.ps1").read_text(encoding="utf-8")
    for step in ("doctor", "install", "check_env", "prepare_data", "smoke", "exp013", "collect"):
        assert f'"{step}"' in ps1, f"ps1 missing step {step}"
    assert "USE_DOCKER=0" in ps1
    assert "CONFIRM_EXP013" in ps1  # exp013 stays double-gated on Windows too
    assert "$PSScriptRoot" in ps1  # repo root auto-detected from the script location
    assert "offline_packages\\checkpoints" in ps1  # weights auto-placed during install
    assert "E:\\robot-3d-perception" in (BUNDLE / "WINDOWS.md").read_text(encoding="utf-8")


@pytest.mark.skipif(not BASH_AVAILABLE, reason="bash not available")
def test_bundle_scripts_pass_bash_n():
    for name in SCRIPTS:
        proc = subprocess.run(["bash", "-n", str(BUNDLE / name)],
                              capture_output=True, text=True)
        assert proc.returncode == 0, f"{name}: {proc.stderr}"


def test_runtime_module_is_lazy_and_laptop_safe():
    """Importing/constructing the real runtime on the laptop must fail with
    FoundationPoseRuntimeUnavailable — and must NOT import the official
    checkout (which does not exist here)."""
    import sys

    sys.path.insert(0, str(Path("src").resolve()))
    from r3p.foundationpose.adapter import FoundationPoseRuntimeUnavailable
    from r3p.foundationpose.runtime import FoundationPoseRuntime

    assert "estimater" not in sys.modules, "official checkout must not be imported on the laptop"
    with pytest.raises(FoundationPoseRuntimeUnavailable):
        FoundationPoseRuntime(fp_repo_root="nonexistent", checkpoint_dir="nonexistent")


def test_runner_refuses_mock_smoke():
    """--smoke exists to validate the REAL runtime; mock is pytest-only."""
    proc = subprocess.run(
        [sys.executable, str(Path("scripts/run_foundationpose_exp013.py").resolve()),
         "--smoke", "--backend", "mock"],
        capture_output=True, text=True,
    )
    assert proc.returncode == 2
    assert "smoke" in (proc.stdout + proc.stderr).lower()
