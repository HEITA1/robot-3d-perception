#!/usr/bin/env bash
# DOCKER_SETUP — 在 3090 上建立 Docker 隔离执行环境（共用机首选路线）。
# 前置：docker + nvidia-container-toolkit（本脚本检查）；官方基础镜像自动拉取。
# 产出：派生镜像 r3p-fp:exp013（基础镜像 + r3p 项目 + 轻量依赖）+ 容器内验证。
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
BASE_IMAGE="${R3P_FP_BASE_IMAGE:-wenbowen123/foundationpose:latest}"
IMAGE="${R3P_FP_IMAGE:-r3p-fp:exp013}"
die() { echo "[DOCKER_SETUP][FATAL] $*" >&2; exit 1; }

echo "[1/5] 宿主机前置检查"
command -v docker >/dev/null || die "docker 不在 PATH——先安装 docker（共用机上若无权限，联系管理员）"
docker info 2>/dev/null | grep -qi nvidia || die "nvidia-container-toolkit 未生效（docker info 无 NVIDIA runtime）——先装 toolkit"
nvidia-smi >/dev/null || die "nvidia-smi 不可用（driver 问题）"
echo "  docker + NVIDIA runtime OK"

echo "[2/5] 拉取官方基础镜像：$BASE_IMAGE（⏳ 实际体积以拉取输出为准，预估 10–20GB）"
docker pull "$BASE_IMAGE" || die "基础镜像拉取失败——检查网络/磁盘（df -h），不要换非官方镜像"

echo "[3/5] 写白名单式 .dockerignore（上下文排除 data/outputs/data_synth/.git）"
if [ ! -f "$REPO_ROOT/.dockerignore" ]; then
  cat > "$REPO_ROOT/.dockerignore" <<'EOF'
/*
!pyproject.toml
!README.md
!src/
!delivery/foundationpose_3090/Dockerfile.r3p-fp
EOF
  echo "  .dockerignore 已创建（构建上下文 MB 级；文件保留，对后续构建同样生效）"
else
  echo "  .dockerignore 已存在——保留现状"
fi

echo "[4/5] 构建派生镜像：$IMAGE"
docker build -f "$REPO_ROOT/delivery/foundationpose_3090/Dockerfile.r3p-fp" \
  -t "$IMAGE" "$REPO_ROOT" || die "派生镜像构建失败——按报错处理（多为轻量依赖缺漏，补进 Dockerfile 依赖行重建）；禁止更换 torch/CUDA 版本"

echo "[5/5] 容器内验证（GPU + 项目 + 官方 checkout 挂载）"
HOST_FP_ROOT="${FP_REPO_ROOT:-$HOME/FoundationPose}"
HOST_CKPT="${FP_CHECKPOINT_DIR:-$HOST_FP_ROOT/weights}"
docker run --rm --gpus all \
  -v "$REPO_ROOT":/work -w /work \
  -v "$HOST_FP_ROOT":/fp/FoundationPose -v "$HOST_CKPT":/fp/weights \
  -e FP_REPO_ROOT=/fp/FoundationPose -e FP_CHECKPOINT_DIR=/fp/weights \
  "$IMAGE" bash -c 'python -c "import torch; assert torch.cuda.is_available(); print(\"torch CUDA:\", torch.__version__, torch.cuda.get_device_name(0))" \
                    && python -c "import r3p, r3p.foundationpose.runtime; print(\"r3p + runtime importable\")" \
                    && ls /fp/FoundationPose/estimater.py >/dev/null && echo "FP checkout mounted"'

echo "== 镜像与磁盘占用 =="
docker images | grep -E "foundationpose|r3p-fp" || true
docker system df || true
df -h "$REPO_ROOT" | tail -1
echo "== DOCKER_SETUP 完成。后续脚本默认 USE_DOCKER=1 自动进容器；CHECK_ENV 应全 PASS =="
