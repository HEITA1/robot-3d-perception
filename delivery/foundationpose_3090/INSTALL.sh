#!/usr/bin/env bash
# INSTALL — 在 3090 机器上创建 FoundationPose 执行环境（Stage A bundle）。
# 双模式：repo 旁存在 offline_packages/ 时自动全离线安装（网络不稳机器的预设）；
# 否则在线安装。安全失败：任何一步失败即停；禁止自动尝试其他版本。
# 不触碰任何名为 r3p 的既有 conda 环境。
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
ENV_NAME="${R3P_FP_ENV:-r3p-fp}"
FP_REPO_ROOT="${FP_REPO_ROOT:-$HOME/FoundationPose}"
OFFLINE_DIR="${R3P_FP_OFFLINE:-$REPO_ROOT/offline_packages}"
die() { echo "[INSTALL][FATAL] $*" >&2; exit 1; }

PIP_OFFLINE=()
if [ -d "$OFFLINE_DIR/wheels_cu124" ] && compgen -G "$OFFLINE_DIR/wheels_cu124/*.whl" > /dev/null; then
  PIP_OFFLINE=(--no-index --find-links "$OFFLINE_DIR/wheels_cu124")
  echo "离线模式: wheels = $OFFLINE_DIR/wheels_cu124"
fi
HAVE_OFFLINE_FP=0
[ -f "$OFFLINE_DIR/fp_repo/estimater.py" ] && HAVE_OFFLINE_FP=1

echo "[1/7] OS check"
[ "$(uname -s)" = "Linux" ] || die "仅支持 Linux / WSL2（3090 Windows 路线在 WSL 内运行本脚本）。当前：$(uname -s)"
command -v conda >/dev/null || die "conda 不在 PATH（WSL 内先装 miniconda，见 RUN_ON_WINDOWS.ps1 install）"

echo "[2/7] 创建 conda env: $ENV_NAME (python=3.11)"
if conda env list | grep -qE "^r3p( |$)"; then
  die "检测到既有环境 'r3p' —— 本脚本绝不修改它（红线）。请确认环境命名后重试。"
fi
if conda env list | grep -qE "^${ENV_NAME}( |$)"; then
  echo "  env '$ENV_NAME' 已存在——跳过创建（如需重建请手动删除后重跑）。"
else
  # ToS 门控（3090 实测两次踩坑：在线与 --offline create 都会被拦）——必须先接受；
  # accept 本地写记录，失败不阻断；CONDA_PLUGINS_AUTO_ACCEPT_TOS 做无网兜底。
  conda tos accept --override-channels --channel https://repo.anaconda.com/pkgs/main >/dev/null 2>&1 || true
  conda tos accept --override-channels --channel https://repo.anaconda.com/pkgs/r >/dev/null 2>&1 || true
  export CONDA_PLUGINS_AUTO_ACCEPT_TOS=yes
  if compgen -G "$OFFLINE_DIR/conda_pkgs/*.conda" > /dev/null; then
    echo "  离线模式: 预下 conda 包注入 pkgs 缓存后 --offline 创建"
    mkdir -p ~/miniconda3/pkgs
    cp "$OFFLINE_DIR"/conda_pkgs/*.conda ~/miniconda3/pkgs/ || die "conda 包注入失败"
    conda create -n "$ENV_NAME" python=3.11 -y --offline \
      || die "离线 conda create 失败——确认 WSL 发行版 glibc >= 2.17（Ubuntu 20.04+）"
  else
    conda create -n "$ENV_NAME" python=3.11 -y \
      || conda create -n "$ENV_NAME" python=3.11 -y -c conda-forge --override-channels \
      || die "conda create 失败（ToS 已尝试接受；conda-forge 兜底也失败——检查网络/磁盘）"
  fi
fi
CONDA_BASE="$(conda info --base)"
# shellcheck disable=SC1091
source "$CONDA_BASE/etc/profile.d/conda.sh"
conda activate "$ENV_NAME"
PYTHON="$(command -v python)"
echo "  python: $($PYTHON --version)"

echo "[3/7] PyTorch CUDA 构建（cu124；单一来源，不做版本搜索）"
if [ ${#PIP_OFFLINE[@]} -gt 0 ]; then
  pip install "${PIP_OFFLINE[@]}" torch==2.6.0 torchvision==0.21.0 torchaudio==2.6.0 \
    || die "离线 torch 安装失败——wheels_cu124 不完整？"
else
  $PYTHON -c "import torch" 2>/dev/null || \
    pip install torch torchvision torchaudio --index-url https://download.pytorch.org/whl/cu124 \
    || die "torch 安装失败——检查 driver/CUDA（nvidia-smi），不要换版本重试"
fi

echo "[3b/7] nvcc 工具链（编译 pytorch3d/nvdiffrast + nvdiffrast 运行期 JIT 必需）"
if compgen -G "$OFFLINE_DIR/conda_pkgs/nvcc_pkgs/cuda-nvcc-*.tar.bz2" > /dev/null; then
  echo "  离线模式：conda nvcc 包直接解入 $CONDA_PREFIX（nvcc 12.4.131 + cudart 12.4.127 头文件）"
  for p in "$OFFLINE_DIR"/conda_pkgs/nvcc_pkgs/*.tar.bz2; do
    tar -xjf "$p" -C "$CONDA_PREFIX" || die "nvcc conda 包解包失败: $p"
  done
  export CUDA_HOME="$CONDA_PREFIX"
  export PATH="$CUDA_HOME/bin:$PATH"
  hash -r
  nvcc --version | tail -1 || die "解包后 nvcc 不可执行"
  [ -f "$CUDA_HOME/include/cuda_runtime.h" ] || die "cuda_runtime.h 缺失（cudart-dev 未解入？）"
elif [ -n "${WSL_DISTRO_NAME:-}" ]; then
  echo "  WSL2 + 在线：conda 安装最小工具链（cuda-nvcc 12.4）"
  conda install -y -c nvidia cuda-nvcc=12.4 cuda-cudart-dev=12.4 \
    || die "conda 安装 cuda-nvcc 失败（磁盘/网络）；不要换版本乱试"
  export CUDA_HOME="$CONDA_PREFIX"
else
  echo "  原生 Linux：使用系统 nvcc（CHECK_ENV 会验证）"
fi

echo "[4/7] 官方 FoundationPose checkout"
if [ ! -f "$FP_REPO_ROOT/estimater.py" ]; then
  if [ "$HAVE_OFFLINE_FP" = "1" ]; then
    mkdir -p "$FP_REPO_ROOT"
    cp -r "$OFFLINE_DIR/fp_repo/." "$FP_REPO_ROOT/" || die "离线 fp_repo 拷贝失败"
    echo "  离线 fp_repo 已就位"
  else
    git clone https://github.com/NVlabs/FoundationPose.git "$FP_REPO_ROOT" \
      || die "官方仓库克隆失败（网络/认证）"
  fi
else
  echo "  $FP_REPO_ROOT 已有 checkout——跳过（保留其 weights/）"
fi
mkdir -p "$REPO_ROOT/outputs"
if [ -f "$OFFLINE_DIR/fp_repo_commit.txt" ]; then
  cp "$OFFLINE_DIR/fp_repo_commit.txt" "$REPO_ROOT/outputs/fp_commit.txt"
else
  git -C "$FP_REPO_ROOT" rev-parse HEAD | tee "$REPO_ROOT/outputs/fp_commit.txt"
fi
echo "  commit: $(cat "$REPO_ROOT/outputs/fp_commit.txt")"

echo "[5/7] 官方 requirements + 构建工具（cmake/ninja 经 wheel）"
if [ -f "$FP_REPO_ROOT/requirements.txt" ]; then
  pip install "${PIP_OFFLINE[@]}" -r "$FP_REPO_ROOT/requirements.txt" \
    || die "官方 requirements 安装失败——离线包缺件？按报错补 download，禁止乱试版本"
fi
if [ ${#PIP_OFFLINE[@]} -gt 0 ]; then
  pip install "${PIP_OFFLINE[@]}" cmake ninja || die "cmake/ninja wheel 安装失败"
fi

echo "[6/7] GPU 扩展编译（nvdiffrast / pytorch3d）"
if [ -d "$OFFLINE_DIR/nvdiffrast-src" ]; then
  pip install --no-build-isolation "$OFFLINE_DIR/nvdiffrast-src" \
    || die "nvdiffrast 安装失败（需 nvcc+gcc；WSL 下确认 apt build-essential 已装）"
elif [ -f "$FP_REPO_ROOT/build_all_conda.sh" ]; then
  (cd "$FP_REPO_ROOT" && bash build_all_conda.sh) || die "官方 build_all_conda.sh 失败——检查 gcc/CUDA_HOME 匹配"
else
  pip install --no-build-isolation git+https://github.com/NVlabs/nvdiffrast.git \
    || die "nvdiffrast 安装失败"
fi
if [ -d "$OFFLINE_DIR/pytorch3d-src" ]; then
  echo "  编译 pytorch3d（源码编译，CPU 编译约 30–60 分钟，耐心等待；失败会停）"
  MAX_JOBS=4 pip install --no-build-isolation "$OFFLINE_DIR/pytorch3d-src" \
    || die "pytorch3d 编译失败（需 nvcc+gcc+CUDA_HOME 匹配；不要换版本乱试）"
else
  echo "  跳过 pytorch3d 离线源（未随包）——若 smoke 因缺 pytorch3d 失败，需补装"
fi

echo "[7/7] 安装本项目（r3p adapter/runner/evaluator；运行时依赖已由 requirements 覆盖）"
(cd "$REPO_ROOT" && pip install "${PIP_OFFLINE[@]}" --no-deps -e .) || die "项目安装失败"

echo "== INSTALL 完成。最终验证：bash delivery/foundationpose_3090/CHECK_ENV.sh =="
