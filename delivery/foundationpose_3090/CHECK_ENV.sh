#!/usr/bin/env bash
# CHECK_ENV — 3090 环境检查（Stage A bundle，Docker 隔离优先）。
# 默认 USE_DOCKER=1：本脚本在宿主机上自动 re-exec 进容器（仅容器内相关项）。
# USE_DOCKER=0：原生 conda 路线全量检查。
# 轻薄本上运行会 FAIL（无 NVIDIA GPU）——这是事实，不是错误。
# 输出：逐项 PASS / FAIL / UNKNOWN + env_manifest.txt；退出码 0 = 全部必需项 PASS。
set -uo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
MANIFEST="$REPO_ROOT/outputs/phase4_foundationpose/env_manifest.txt"
mkdir -p "$(dirname "$MANIFEST")"

# ---- Docker 隔离：仅 Linux 宿主机使用；WSL2（Windows 路线）原生运行，跳过 ----
if [ "${USE_DOCKER:-1}" = "1" ] && [ "${INSIDE_CONTAINER:-0}" != "1" ] && [ -z "${WSL_DISTRO_NAME:-}" ]; then
  IMAGE="${R3P_FP_IMAGE:-r3p-fp:exp013}"
  HOST_FP_ROOT="${FP_REPO_ROOT:-$HOME/FoundationPose}"
  HOST_CKPT="${FP_CHECKPOINT_DIR:-$HOST_FP_ROOT/weights}"
  exec docker run --rm --gpus all -e INSIDE_CONTAINER=1 \
    -v "$REPO_ROOT":/work -w /work \
    -v "$HOST_FP_ROOT":/fp/FoundationPose -v "$HOST_CKPT":/fp/weights \
    -e FP_REPO_ROOT=/fp/FoundationPose -e FP_CHECKPOINT_DIR=/fp/weights \
    "$IMAGE" bash "delivery/foundationpose_3090/$(basename "${BASH_SOURCE[0]}")"
fi

PYTHON="${R3P_FP_PYTHON:-python}"
IN_CONTAINER="${INSIDE_CONTAINER:-0}"

PASS=0; FAIL=0
declare -a FAILED
check() {
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

echo "== CHECK_ENV @ $(date -u +%Y-%m-%dT%H:%M:%SZ) mode=$([ "$IN_CONTAINER" = "1" ] && echo docker || echo native) ==" | tee "$MANIFEST"

check "os-linux" test "$(uname -s)" = "Linux"
check "gpu-nvidia-smi" nvidia-smi
check "torch" "$PYTHON" -c "import torch; print(torch.__version__)"
check "torch-cuda" "$PYTHON" -c "import torch; assert torch.cuda.is_available(); print(torch.cuda.get_device_name(0))"
check "nvdiffrast" "$PYTHON" -c "import nvdiffrast; print('nvdiffrast ok')"
check "pytorch3d" "$PYTHON" -c "import pytorch3d; print(pytorch3d.__version__)"
check "trimesh" "$PYTHON" -c "import trimesh; print(trimesh.__version__)"
check "r3p-project" "$PYTHON" -c "import r3p; print('r3p importable')"

if [ "$IN_CONTAINER" = "1" ]; then
  echo "-- docker 模式：镜像内已固化构建链/conda（跳过宿主机构建工具项）--"
else
  check "cuda-nvcc" nvcc --version
  check "compiler-gcc" gcc --version
  check "compiler-gxx" g++ --version
  check "cmake" cmake --version
  check "ninja" ninja --version
  check "conda" conda --version
  check "python" "$PYTHON" --version
  check "python-3.11" "$PYTHON" -c "import sys; assert sys.version_info[:2] == (3, 11), sys.version"
fi

FP_REPO_ROOT="${FP_REPO_ROOT:-$HOME/FoundationPose}"
FP_CHECKPOINT_DIR="${FP_CHECKPOINT_DIR:-$FP_REPO_ROOT/weights}"
check "foundationpose-import" "$PYTHON" -c "import sys; sys.path.insert(0, '$FP_REPO_ROOT'); import estimater; print('estimater importable')"
check "fp-checkpoint-dirs" bash -c "test -d '$FP_CHECKPOINT_DIR' && ls '$FP_CHECKPOINT_DIR' | head -5"

# 数据存在性（最小 EXP-013 集合；见 DATA_MANIFEST.md）——两种模式都必须过
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
  echo "对照 DOCKER.md / ENVIRONMENT.md / DATA_MANIFEST.md / DOWNLOAD_WEIGHTS.md 处理后重跑；"
  echo "禁止自动安装/换版本重试——按报告逐项处理。"
  exit 1
fi
echo "ALL REQUIRED CHECKS PASSED — READY (smoke gate: RUN_SMOKE_TEST.sh)"
