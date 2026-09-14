# DOCKER — Linux Docker 路线（**备选**；当前主路径 = WINDOWS.md 的 WSL2）

> 2026-09-13 降级说明：3090 机器 Linux 侧磁盘不足（Docker 基础镜像需 10–20GB），
> 主路径改为 Windows + WSL2（`WINDOWS.md` / `RUN_ON_WINDOWS.ps1`）。本路线保留为
> Linux 空间恢复后的备选；4 个 GPU 侧脚本仍支持 `USE_DOCKER=1`（Linux 宿主机上）。
> 共用机隔离初衷（防依赖冲突）在 WSL2 路线下由 WSL 发行版的用户级隔离天然满足。

## 方案

```text
宿主机（3090 Ubuntu）
  ├── docker + nvidia-container-toolkit        （DOCKER_SETUP.sh 前置检查）
  ├── 官方基础镜像  wenbowen123/foundationpose  （Preflight §1 官方推荐；含 CUDA/torch/编译链）
  ├── 派生镜像      r3p-fp:exp013               （= 基础镜像 + r3p 项目与轻量依赖；Dockerfile.r3p-fp）
  └── 运行时挂载（容器内外同名效果）：
        <repo>            → /work               （代码 + configs + data + outputs 全在这里）
        ~/FoundationPose  → /fp/FoundationPose   （官方 checkout，commit 钉死）
        ~/FoundationPose/weights → /fp/weights   （checkpoints）
```

- 宿主机上**零 Python 依赖安装**——所有依赖固化在镜像层里，与机器上其他用户的
  conda/venv 完全隔离；`--rm` 容器用完即弃，不留半截状态（符合共享机生存法则）。
- 所有 `CHECK_ENV / PREPARE_DATA / RUN_SMOKE_TEST / RUN_EXP013` 脚本
  **默认自动在容器内 re-exec**（`USE_DOCKER=1` 默认值）；设 `USE_DOCKER=0` 走原生路线。

## 步骤（替代 conda 路线的步骤 5–6）

```bash
# 前置：docker 已装且 nvidia-container-toolkit 可用（DOCKER_SETUP 会检查）
bash delivery/foundationpose_3090/DOCKER_SETUP.sh      # 拉基础镜像 → 构建派生镜像 → 容器内验证
bash delivery/foundationpose_3090/CHECK_ENV.sh         # 自动进容器，应全 PASS
bash delivery/foundationpose_3090/PREPARE_DATA.sh      # 自动进容器（CPU 部分）
bash delivery/foundationpose_3090/RUN_SMOKE_TEST.sh    # 自动进容器（GPU）
```

## 常用命令（3090 上）

```bash
docker images | grep -E "foundationpose|r3p-fp"     # 查看镜像与体积
docker run --rm -it --gpus all -v "$PWD":/work -w /work \
  r3p-fp:exp013 bash                                 # 手动进入容器排查
docker system df                                     # docker 磁盘占用总览
```

## 注意

- 基础镜像 tag 以执行时官方 README 为准（本 Bundle 按 Preflight 审计用
  `wenbowen123/foundationpose:latest`）；若 tag/目录不同，只改 `DOCKER_SETUP.sh`
  一处并记录。
- 派生镜像内**不做任何 GPU 相关的版本搜索**；缺轻量依赖 → 补进
  `Dockerfile.r3p-fp` 的依赖行并重建（幂等），CUDA/torch 永远以基础镜像为准。
- 拉取/构建产生的构建缓存可用 `docker builder prune` 清理（不影响已建镜像）。
