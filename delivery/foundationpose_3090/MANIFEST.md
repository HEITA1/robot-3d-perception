# MANIFEST — Bundle 文件索引（Stage A-LOCAL，2026-09-13）

| 文件 | 用途 | 在哪台机器执行/使用 |
| --- | --- | --- |
| `README_3090.md` | 总操作手册（顺序/门控/PENDING_3090/回传清单） | 3090（人读） |
| `ENVIRONMENT.md` | 环境要求与版本策略（含 ⏳ PENDING_3090 字段） | 3090（人读） |
| `DATA_MANIFEST.md` | 最小 BOP 数据搬运清单 + 单位契约红线 | 轻薄本（拷贝时）+ 3090（校验） |
| `DOWNLOAD_WEIGHTS.md` | 官方 checkpoint 清单（⏳ 文件名/大小/sha256） | 轻薄本下载 → 3090 |
| `CHECK_ENV.sh` | 环境检查（WSL2=原生；Linux 宿主=容器内；native 模式=全量 16+ 项；PASS/FAIL/UNKNOWN + env_manifest.txt） | 3090 机器 |
| `WINDOWS.md` / `RUN_ON_WINDOWS.ps1` | **Windows + WSL2 路线（当前主路径）**：PowerShell 引导器（doctor/install/check_env/prepare_data/smoke/exp013/collect）+ 方案与空间说明 | 3090 机器（Windows） |
| `DOCKER.md` / `DOCKER_SETUP.sh` / `Dockerfile.r3p-fp` | Linux Docker 路线（**已降为备选**——3090 Linux 空间不足） | 3090 机器（Linux，备选） |
| `INSTALL.sh` | conda env `r3p-fp` + torch cu124 + WSL 分支（conda nvcc）+ 官方 requirements + 编译（safe-fail） | 3090 机器 |
| `PREPARE_DATA.sh` | 数据齐全性 + 5 帧加载 + 米制单位守卫（CPU 即可） | 3090 机器 |
| `RUN_SMOKE_TEST.sh` | 单帧 620 runtime gate（is_smoke=true，非 benchmark） | 3090 机器 |
| `RUN_EXP013.sh` | 正式 5 帧实验（`EXECUTION_LOCKED=true`，需 `--unlock` + `CONFIRM_EXP013=YES`） | 3090 机器 |
| `COLLECT_RESULTS.sh` | 汇集 `delivery_back/`（结果 + SHA256；不含环境/数据/权重） | 3090 机器 |
| `configs/fp_exp013.yaml` | 冻结协议（与 `configs/fp_exp013.yaml` 逐字节一致，sha256 e51b9c45016d…） | 两端 |
| `expected_outputs/README.md` | 各步骤应产出什么 | 3090（人读） |
| `patches/README.md` | 说明：FP 核心不打补丁；接线在仓库 `src/r3p/foundationpose/runtime.py` | — |

## 磁盘占用（3090 机器）

当前主路径（Windows + WSL2）：合计 ≈ **10–15 GB（典型 ~12GB）**——WSL 1–2GB + conda env
6–8GB + nvcc 工具链 1–2GB + 权重 1–2GB + 数据/输出 <0.3GB；明细见 `WINDOWS.md`。
备选路线（Linux）：Docker ≈12–23GB / conda 原生 ≈8–12GB。

## Bundle 外部依赖（不在 Bundle 内、也不应拷入）

- 官方 FoundationPose checkout（3090 上克隆，commit 钉死记录）
- checkpoints（官方 Google Drive，见 DOWNLOAD_WEIGHTS.md）
- BOP 最小数据（见 DATA_MANIFEST.md）
- 仓库其余部分（runner/adapter/evaluator/dataset——随仓库整体到位）

## 配套仓库改动（随仓库推送，不在 Bundle 内重复）

- `src/r3p/foundationpose/runtime.py`：官方 estimater 的最小接线（惰性导入；
  轻薄本上仅可导入与单测，真实执行只在 3090 smoke 验证）
- `scripts/run_foundationpose_exp013.py`：新增 `--smoke`（单帧 gate）+
  foundationpose 后端接线调用 + manifest 记录 repo_commit/predicted poses
