#!/usr/bin/env bash
# CHECK_ENV — 3090 环境检查（Stage A bundle）。只在 3090 上真实执行；
# 轻薄本上运行会得到 FAIL（无 NVIDIA GPU）——这不是错误，是事实。
# 输出：逐项 PASS / FAIL / UNKNOWN + env_manifest.txt（版本留档）。
# 退出码：0 = 全部必需项 PASS；非 0 = 有 FAIL（逐条列出，不做自动修复）。
set -uo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
ENV_NAME="${R3P_FP_ENV:-r3p-fp}"
FP_REPO_ROOT="${FP_REPO_ROOT:-$HOME/FoundationPose}"
FP_CHECKPOINT_DIR="${FP_CHECKPOINT_DIR:-$FP_REPO_ROOT/weights}"
PYTHON="${R3P_FP_PYTHON:-python}"   # README 步骤 10：conda activate r3p-fp 后运行
MANIFEST="$REPO_ROOT/outputs/phase4_foundationpose/env_manifest.txt"
mkdir -p "$(dirname "$MANIFEST")"

PASS=0; FAIL=0
declare -a FAILED
check() { # check <名称> <命令...>
  local name="$1"; shift
  if "$@" > /tmp/_check_out 2>&1; then
    echo "PASS  $name :: $(head -c 120 /tmp/_check_out | tr '\n' ' ')"
    echo "$name :: $(head -c 200 /tmp/_check_out | tr '\n' ' ')" >> "$MANIFEST"
    PASS=$((PASS+1)); return 0
  fi
  echo "FAIL  $name :: $(head -c 160 /tmp/_check_out | tr '\n' ' ')"
  echo "$name :: FAIL :: $(head -c 200 /tmp/_check_out | tr '\n' ' ')" >> "$MANIFEST"
  FAILED+=("$name"); FAIL=$((FAIL+1)); return 1
}
unknown() { # 已存在但无法验证版本的项
  echo "UNKNOWN $1 :: $2"
  echo "$1 :: UNKNOWN :: $2" >> "$MANIFEST"
}

echo "== CHECK_ENV @ $(date -u +%Y-%m-%dT%H:%M:%SZ) ==" | tee "$MANIFEST"
check "os-linux"            test "$(uname -s)" = "Linux"
check "gpu-nvidia-smi"      nvidia-smi
check "cuda-nvcc"           nvcc --version
check "compiler-gcc"        gcc --version
check "compiler-gxx"        g++ --version
check "cmake"               cmake --version
check "ninja"               ninja --version
check "conda"               conda --version
check "python"              "$PYTHON" --version
check "python-3.11"         "$PYTHON" -c "import sys; assert sys.version_info[:2] == (3, 11), sys.version"
check "torch"               "$PYTHON" -c "import torch; print(torch.__version__)"
check "torch-cuda"          "$PYTHON" -c "import torch; assert torch.cuda.is_available(); print(torch.cuda.get_device_name(0))"
check "nvdiffrast"          "$PYTHON" -c "import nvdiffrast; print('nvdiffrast ok')"
check "pytorch3d"           "$PYTHON" -c "import pytorch3d; print(pytorch3d.__version__)"
check "trimesh"             "$PYTHON" -c "import trimesh; print(trimesh.__version__)"
check "r3p-project"         "$PYTHON" -c "import r3p; print('r3p importable')"
check "foundationpose-import" "$PYTHON" -c "import sys; sys.path.insert(0, '$FP_REPO_ROOT'); import estimater; print('estimater importable')"
check "fp-checkpoint-dirs"  bash -c "test -d '$FP_CHECKPOINT_DIR' && ls '$FP_CHECKPOINT_DIR' | head -5"

# 数据存在性（最小 EXP-013 集合；见 DATA_MANIFEST.md）
DATA_OK=1
for f in \
  data/ycbv/dataset_info.md data/ycbv/models/obj_000005.ply data/ycbv/models/models_info.json \
  data/ycbv/test/000050/scene_camera.json data/ycbv/test/000050/scene_gt.json \
  data/ycbv/test/000050/rgb/000620.png data/ycbv/test/000050/rgb/000653.png \
  data/ycbv/test/000050/rgb/000721.png data/ycbv/test/000050/rgb/001044.png \
  data/ycbv/test/000050/rgb/001113.png \
  data/ycbv/test/000050/depth/000620.png data/ycbv/test/000050/depth/000653.png \
  data/ycbv/test/000050/depth/000721.png data/ycbv/test/000050/depth/001044.png \
  data/ycbv/test/000050/depth/001113.png \
  data/ycbv/test/000050/mask_visib/000620_000002.png data/ycbv/test/000050/mask_visib/000653_000002.png \
  data/ycbv/test/000050/mask_visib/000721_000002.png data/ycbv/test/000050/mask_visib/001044_000002.png \
  data/ycbv/test/000050/mask_visib/001113_000002.png ; do
  if [ ! -f "$REPO_ROOT/$f" ]; then echo "FAIL  data::$f (missing)"; DATA_OK=0; FAIL=$((FAIL+1)); FAILED+=("data::$f"); fi
done
[ "$DATA_OK" = "1" ] && { echo "PASS  data-minimal-EXP013 (20 files)"; PASS=$((PASS+1)); }

echo "==================================================="
echo "SUMMARY: PASS=$PASS FAIL=$FAIL (env manifest: $MANIFEST)"
if [ "$FAIL" -gt 0 ]; then
  echo "FAILED items: ${FAILED[*]}"
  echo "对照 ENVIRONMENT.md / DATA_MANIFEST.md / DOWNLOAD_WEIGHTS.md 处理后重跑；"
  echo "禁止自动安装/换版本重试——按报告逐项处理。"
  exit 1
fi
echo "ALL REQUIRED CHECKS PASSED — READY (smoke gate: RUN_SMOKE_TEST.sh)"
