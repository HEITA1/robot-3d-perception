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
        "DOWNLOAD_WEIGHTS.md", "DOCKER.md", "Dockerfile.r3p-fp")


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


def test_docker_isolation_is_default_path():
    """Shared 3090: every GPU-side script must default to docker re-exec
    (USE_DOCKER=1) with the official base image wired in the Dockerfile."""
    for name in ("CHECK_ENV.sh", "PREPARE_DATA.sh", "RUN_SMOKE_TEST.sh", "RUN_EXP013.sh"):
        text = (BUNDLE / name).read_text(encoding="utf-8")
        assert 'USE_DOCKER:-1' in text, f"{name} missing docker-default preamble"
        assert "INSIDE_CONTAINER" in text
    dockerfile = (BUNDLE / "Dockerfile.r3p-fp").read_text(encoding="utf-8")
    assert "FROM wenbowen123/foundationpose:" in dockerfile
    assert "--no-deps" in dockerfile  # never touch the base image's torch/CUDA tree


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
