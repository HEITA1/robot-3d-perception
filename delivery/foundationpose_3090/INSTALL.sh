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
CONDA_BASE="$(conda info --base)"
ENV_PREFIX="$CONDA_BASE/envs/$ENV_NAME"

# 编译工具链：由离线 conda 闭包提供（gcc 13.4 / gxx / binutils / sysroot 2.17 /
# kernel-headers / make / boost 1.92 / zstd——3090 不联网方案），解包后自动就位

echo "[2/7] 创建 env: $ENV_NAME (python 3.11)"
if conda env list | grep -qE "^r3p( |$)"; then
  die "检测到既有环境 'r3p' —— 本脚本绝不修改它（红线）。请确认环境命名后重试。"
fi
if [ -x "$ENV_PREFIX/bin/python" ]; then
  echo "  env 已存在（$ENV_PREFIX）——跳过创建（如需重建请手动删除后重跑）。"
elif compgen -G "$OFFLINE_DIR/conda_pkgs/*.conda" > /dev/null; then
  # 离线终案：绕开 solver/ToS/repodata——把闭包 conda 包直接解入 env 前缀
  # （3090 实测三连坑后的定案：在线 ToS 门控、--offline ToS 门控、频道漂移致闭包不自洽）
  BPY="$CONDA_BASE/bin/python"   # miniconda base python（自带 pip；WSL 系统 python3 无 pip，incident #5）
  [ -x "$BPY" ] || die "miniconda base python 不存在（$BPY）"
  "$BPY" -m pip install --no-index --find-links "$OFFLINE_DIR/wheels_cu124" zstandard \
    || die "base python 安装 zstandard 失败（wheels_cu124 缺 cp313 wheel？）"
  "$BPY" "$REPO_ROOT/delivery/foundationpose_3090/scripts/extract_conda_pkgs.py" \
    --pkgs-dir "$OFFLINE_DIR/conda_pkgs" --dest "$ENV_PREFIX" \
    || die "conda 包解包失败"
  [ -x "$ENV_PREFIX/bin/python" ] || die "解包后 python 不存在——闭包不完整"
  "$ENV_PREFIX/bin/python" -m ensurepip --upgrade || die "ensurepip 失败（pip 引导）"
  echo "  env 前缀: $ENV_PREFIX（离线解包 + ensurepip 引导 pip）"
else
  # 在线路线（conda 求解；ToS 门控两连坑的修复保留在此）
  conda tos accept --override-channels --channel https://repo.anaconda.com/pkgs/main >/dev/null 2>&1 || true
  conda tos accept --override-channels --channel https://repo.anaconda.com/pkgs/r >/dev/null 2>&1 || true
  export CONDA_PLUGINS_AUTO_ACCEPT_TOS=yes
  conda create -n "$ENV_NAME" python=3.11 -y \
    || conda create -n "$ENV_NAME" python=3.11 -y -c conda-forge --override-channels \
    || die "conda create 失败（ToS 已尝试接受；conda-forge 兜底也失败——检查网络/磁盘）"
fi
# shellcheck disable=SC1091
source "$CONDA_BASE/etc/profile.d/conda.sh"
conda activate "$ENV_NAME"
PYTHON="$(command -v python)"
echo "  python: $($PYTHON --version)"
# conda 工具链（离线闭包：gcc 13.4/gxx/binutils/sysroot）——nvdiffrast JIT / pytorch3d / mycpp 的 CC/CXX
if [ -x "$ENV_PREFIX/bin/x86_64-conda-linux-gnu-gcc" ]; then
  export CC="$ENV_PREFIX/bin/x86_64-conda-linux-gnu-gcc"
  export CXX="$ENV_PREFIX/bin/x86_64-conda-linux-gnu-g++"
  export PATH="$ENV_PREFIX/bin:$PATH"
  "$CC" --version | head -1
elif ! command -v gcc >/dev/null 2>&1; then
  die "编译器缺失：离线工具链未解入且系统无 gcc——offline_packages/conda_pkgs 不完整"
fi

echo "[3/7] PyTorch CUDA 构建（cu124；单一来源，不做版本搜索）"
# 完整性健康检查：torch._C 是 torch 的核心编译模块——它的缺失说明存在崩溃残留的
# 部分安装（3090 实测：损坏 wheel 使 pip 在 torch 解包中途崩溃，元数据却已写入，
# 之后 pip 一直 "already satisfied" 跳过重装）。此时强制从好 wheel 重装。
if "$PYTHON" -c "import torch, torch._C" >/dev/null 2>&1; then
  echo "  torch 已安装且完整——跳过"
elif [ ${#PIP_OFFLINE[@]} -gt 0 ]; then
  echo "  torch 缺失或不完整——离线强制重装（约 3GB，无输出数分钟——不要中断）..."
  "$PYTHON" -m pip install "${PIP_OFFLINE[@]}" \
      --force-reinstall torch==2.6.0 torchvision==0.21.0 torchaudio==2.6.0 \
    || die "torch 强制重装失败——wheels_cu124 不完整？"
  "$PYTHON" -c "import torch, torch._C; print('  torch', torch.__version__, '| cuda:', torch.cuda.is_available())" \
    || die "重装后 import torch / torch._C 仍失败——torch 安装再次不完整，发回日志"
else
  $PYTHON -c "import torch" 2>/dev/null || \
    "$PYTHON" -m pip install torch torchvision torchaudio --index-url https://download.pytorch.org/whl/cu124 \
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
  echo "  正在安装官方 requirements（数分钟无输出属正常）..."
  "$PYTHON" -m pip install --no-build-isolation "${PIP_OFFLINE[@]}" -r "$FP_REPO_ROOT/requirements.txt" \
    || die "官方 requirements 安装失败——离线包缺件？按报错补 download，禁止乱试版本"
fi
if [ ${#PIP_OFFLINE[@]} -gt 0 ]; then
  "$PYTHON" -m pip install "${PIP_OFFLINE[@]}" cmake ninja || die "cmake/ninja wheel 安装失败"
fi

echo "[6/7] GPU 扩展编译（nvdiffrast / pytorch3d / mycpp）"
# 编译依赖前置检查（Boost/Eigen/pybind11 由离线 conda 包解入 env 前缀；放在 30-60 分钟
# 的 pytorch3d 编译之前，缺了立刻报而不是白等一小时）
BOOST_OK=$([ -f "$ENV_PREFIX/include/boost/version.hpp" ] && echo 1 || echo 0)
EIGEN_OK=$([ -d "$ENV_PREFIX/include/eigen3" ] && echo 1 || echo 0)
PYBIND11_DIR="$ENV_PREFIX/site-packages/pybind11/share/cmake/pybind11"
PYBIND_OK=$([ -f "$PYBIND11_DIR/pybind11Config.cmake" ] && echo 1 || echo 0)
if [ "$BOOST_OK" = "0" ] || [ "$EIGEN_OK" = "0" ] || [ "$PYBIND_OK" = "0" ]; then
  die "离线包缺件（boost=$BOOST_OK eigen3=$EIGEN_OK pybind11=$PYBIND_OK）——
  说明 offline_packages/conda_pkgs 与当前 INSTALL.sh 版本不配套：请用最新 U 盘整体重新覆盖"
fi
if [ -d "$OFFLINE_DIR/nvdiffrast-src/nvdiffrast" ]; then
  # JIT 模式安装：直接把 python 包复制进 site-packages（绕开 setup.py 在元数据阶段的
  # 试编译检查——其失败原因被 pip 吞掉无法远程诊断）。CUDA 部分在 smoke 首次渲染时
  # JIT 编译（届时 nvcc/gcc 齐备且日志完整可见）。
  SITE="$($PYTHON -c "import sysconfig; print(sysconfig.get_paths()['purelib'])")"
  rm -rf "$SITE/nvdiffrast"
  cp -r "$OFFLINE_DIR/nvdiffrast-src/nvdiffrast" "$SITE/nvdiffrast" || die "nvdiffrast 复制失败"
  # nvdiffrast/__init__.py 用 importlib.metadata 查询自身版本——裸复制没有元数据会
  # PackageNotFoundError，补一个最小 dist-info（已在笔记本验证该机制）
  DIST="$SITE/nvdiffrast-0.0.0.dist-info"
  mkdir -p "$DIST"
  printf 'Metadata-Version: 2.1\nName: nvdiffrast\nVersion: 0.0.0\n' > "$DIST/METADATA"
  printf 'pip\n' > "$DIST/INSTALLER"
  "$PYTHON" -c "import nvdiffrast; print('nvdiffrast (JIT mode):', nvdiffrast.__file__)" \
    || die "nvdiffrast 复制后 import 失败"
elif [ -f "$FP_REPO_ROOT/build_all_conda.sh" ]; then
  (cd "$FP_REPO_ROOT" && bash build_all_conda.sh) || die "官方 build_all_conda.sh 失败——检查 gcc/CUDA_HOME 匹配"
else
  "$PYTHON" -m pip install --no-build-isolation git+https://github.com/NVlabs/nvdiffrast.git \
    || die "nvdiffrast 安装失败"
fi
if [ -d "$OFFLINE_DIR/pytorch3d-src" ]; then
  echo "  编译 pytorch3d（源码编译，CPU 编译约 30–60 分钟，耐心等待；失败会停）"
  MAX_JOBS=4 "$PYTHON" -m pip install --no-build-isolation "$OFFLINE_DIR/pytorch3d-src" \
    || die "pytorch3d 编译失败（需 nvcc+gcc+CUDA_HOME 匹配；不要换版本乱试）"
else
  echo "  跳过 pytorch3d 离线源（未随包）——若 smoke 因缺 pytorch3d 失败，需补装"
fi

echo "[6c/7] mycpp 编译（estimater 的 cluster_poses 必需；pybind11/Eigen 由离线 conda 包提供）"
if [ ! -f "$ENV_PREFIX/mycpp_installed" ]; then
  cmake -S "$FP_REPO_ROOT/mycpp" -B "$FP_REPO_ROOT/mycpp/build" -G Ninja \
      -DCMAKE_BUILD_TYPE=Release \
      -DPython3_ROOT_DIR="$ENV_PREFIX" \
      -DPYBIND11_PYTHON_EXECUTABLE="$ENV_PREFIX/bin/python" \
      -DCMAKE_PREFIX_PATH="$ENV_PREFIX" \
      -Dpybind11_DIR="$PYBIND11_DIR" \
    || die "mycpp cmake 配置失败（需 gcc/g++/ninja/pybind11/Eigen/Boost——见上方前置检查）"
  cmake --build "$FP_REPO_ROOT/mycpp/build" -j 4 \
    || die "mycpp 编译失败（编译日志在上方；不要换版本乱试）"
  touch "$ENV_PREFIX/mycpp_installed"
  echo "  mycpp 编译完成"
else
  echo "  mycpp 已编译——跳过"
fi

echo "[7/7] 安装本项目（r3p adapter/runner/evaluator；运行时依赖已由 requirements 覆盖）"
(cd "$REPO_ROOT" && "$PYTHON" -m pip install "${PIP_OFFLINE[@]}" --no-deps -e .) || die "项目安装失败"

echo "== INSTALL 完成。最终验证：bash delivery/foundationpose_3090/CHECK_ENV.sh =="
