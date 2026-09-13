#!/usr/bin/env bash
# INSTALL — 在 3090 上创建 FoundationPose 执行环境（Stage A bundle）。
# 原则：safe-fail。任何编译失败 = 停止并给出原因；**禁止自动尝试其他版本**。
# 不触碰任何名为 r3p 的既有 conda 环境。
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
ENV_NAME="${R3P_FP_ENV:-r3p-fp}"
FP_REPO_ROOT="${FP_REPO_ROOT:-$HOME/FoundationPose}"
die() { echo "[INSTALL][FATAL] $*" >&2; exit 1; }

echo "[1/7] OS check"
[ "$(uname -s)" = "Linux" ] || die "仅支持 Linux（3090 Ubuntu）。当前：$(uname -s)"
command -v conda >/dev/null || die "conda 不在 PATH（先安装 miniconda/anaconda）"

echo "[2/7] 创建 conda env: $ENV_NAME (python=3.11)"
if conda env list | grep -qE "^r3p( |$)"; then
  die "检测到既有环境 'r3p' —— 本脚本绝不修改它（红线）。请确认环境命名后重试。"
fi
if conda env list | grep -qE "^${ENV_NAME}( |$)"; then
  echo "  env '$ENV_NAME' 已存在——跳过创建（如需重建请手动删除后重跑）。"
else
  conda create -n "$ENV_NAME" python=3.11 -y || die "conda create 失败"
fi
CONDA_BASE="$(conda info --base)"
# shellcheck disable=SC1091
source "$CONDA_BASE/etc/profile.d/conda.sh"
conda activate "$ENV_NAME"
PYTHON="$(command -v python)"
echo "  python: $($PYTHON --version)"

echo "[3/7] PyTorch CUDA 构建（官方建议 cu124 index；单一来源，不做版本搜索）"
$PYTHON -c "import torch" 2>/dev/null || \
  pip install torch --index-url https://download.pytorch.org/whl/cu124 \
  || die "torch 安装失败——检查 driver/CUDA（nvidia-smi），不要换版本重试"

echo "[4/7] 官方 FoundationPose checkout"
if [ ! -f "$FP_REPO_ROOT/estimater.py" ]; then
  git clone https://github.com/NVlabs/FoundationPose.git "$FP_REPO_ROOT" \
    || die "官方仓库克隆失败（网络/认证）"
fi
git -C "$FP_REPO_ROOT" rev-parse HEAD | tee "$REPO_ROOT/outputs/fp_commit.txt"
echo "  commit 已记录（写入 outputs/fp_commit.txt；manifest 将引用该值）"

echo "[5/7] 官方 requirements"
pip install -r "$FP_REPO_ROOT/requirements.txt" || die "官方 requirements 安装失败——按报错处理，禁止乱试版本"

echo "[6/7] 编译型组件（nvdiffrast/pytorch3d/mycpp）"
if [ -f "$FP_REPO_ROOT/build_all_conda.sh" ]; then
  (cd "$FP_REPO_ROOT" && bash build_all_conda.sh) || die "官方 build_all_conda.sh 失败——检查 gcc/CUDA_HOME 匹配（ENVIRONMENT.md 风险表），不要自动换版本"
else
  echo "  checkout 中无 build_all_conda.sh——按官方 README 手动编译 nvdiffrast/pytorch3d 后重跑 CHECK_ENV.sh 验证"
fi

echo "[7/7] 安装本项目（r3p，含 adapter/runner/evaluator）"
(cd "$REPO_ROOT" && pip install -e ".[dev]") || die "项目安装失败"

echo "== INSTALL 完成。执行最终验证：bash delivery/foundationpose_3090/CHECK_ENV.sh =="
