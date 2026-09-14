# README_3090 — FoundationPose 3090 Execution Bundle (Stage A)

> 目标机器：RTX 3090。**当前执行路线 = Windows + WSL2（主路径）**——3090 机器 Linux 侧
> 磁盘不足，Docker 方案（需 10–20GB 基础镜像）弃用；详见 `WINDOWS.md`。
> 本 Bundle 在轻薄本上准备（Stage A-LOCAL），由用户手动拷贝到 3090 机器。
> **轻薄本无 NVIDIA GPU：任何 GPU/CUDA/FP runtime 步骤只能在 3090 机器上发生**——
> 标 `PENDING_3090` 的字段在执行时才获得真值。
> 固定协议：obj5 `006_mustard_bottle` · scene 50 · frames **620, 653, 721, 1044, 1113** ·
> oracle `mask_visib` · register/estimation 路径（**无初始位姿、GT pose 零参与 inference**）·
> 成功 = ADD < 0.1d = **19.65 mm**（`configs/fp_exp013.yaml` 冻结，勿改）。
> Smoke gate：先跑 **1 帧**（frame 620）验证 runtime，通过后才允许正式 5 帧。
> 全部脚本 **safe-fail**：失败即停并给出明确原因，不做版本乱试、不做 CPU/mock 回退。

## 0. 这是什么

为 **EXP-013（FoundationPose feasibility）** 准备的一键式执行包：

- 固定协议：obj5 `006_mustard_bottle` · scene 50 · frames **620, 653, 721, 1044, 1113** ·
  oracle `mask_visib` · register/estimation 路径（**无初始位姿、GT pose 零参与 inference**）·
  成功 = ADD < 0.1d = **19.65 mm**。协议来源：`configs/fp_exp013.yaml`（冻结，勿改）。
- Smoke gate：先跑 **1 帧**（frame 620）验证 runtime，通过后才允许正式 5 帧。
- 全部脚本 **safe-fail**：任何一步失败即停止并给出明确原因，不做版本乱试、不做 CPU/mock 回退。

## 1. 拷贝清单（用户手动执行）

1. **整个仓库**（剔除 `data\`全量、`data_synth\`、`outputs\`）到 3090 机器的
   Windows 用户目录，例如 `C:\Users\<user>\robot-3d-perception\`。
2. **最小 BOP 数据**（`DATA_MANIFEST.md` 精确清单，21 个小文件 + mesh ≈8MB）——
   若 U 盘组装时已放入仓库同结构路径 `data/ycbv/...` 则无需重复操作。
3. 权重（官方 Google Drive，1–2GB）单独下载（先报批），放 `$HOME\FoundationPose\weights\`。

## 2. 执行顺序（Windows 主路径；PowerShell 逐行复制，说明在行尾 # 后）

> 部署假设：仓库放 **`E:\robot-3d-perception`**（`RUN_ON_WINDOWS.ps1` 自动定位仓库根，
> 放任何盘都零参数）。完整版与前置条件见 `WINDOWS.md`；速查版：

```powershell
cd E:\robot-3d-perception                                                            # 1. 进入仓库根（U 盘整体拷到 E 盘）
wsl --install -d Ubuntu                                                              # 2. 仅首次：装 WSL2 Ubuntu（管理员，可能重启）
powershell -ExecutionPolicy Bypass -File delivery\foundationpose_3090\RUN_ON_WINDOWS.ps1 doctor        # 3. 体检（驱动/WSL/CUDA 直通/磁盘空间）
git clone https://github.com/NVlabs/FoundationPose.git E:\FoundationPose             # 4. 克隆官方 FP（仅官方源）
powershell -ExecutionPolicy Bypass -File delivery\foundationpose_3090\RUN_ON_WINDOWS.ps1 install       # 5. WSL 内建 conda r3p-fp 环境（含 nvcc 工具链；safe-fail）
# 6. 下载官方 checkpoints（1-2GB，仅官方 Google Drive）→ 放 E:\FoundationPose\weights\
powershell -ExecutionPolicy Bypass -File delivery\foundationpose_3090\RUN_ON_WINDOWS.ps1 check_env     # 7. 环境复查（应全 PASS）
powershell -ExecutionPolicy Bypass -File delivery\foundationpose_3090\RUN_ON_WINDOWS.ps1 prepare_data  # 8. 数据完整性 + 米制单位守卫
powershell -ExecutionPolicy Bypass -File delivery\foundationpose_3090\RUN_ON_WINDOWS.ps1 smoke         # 9. 单帧 smoke gate（frame 620，GPU）
# 10. 目检 outputs\phase4_foundationpose\smoke_test\overlay_000050_000620.png（GT 绿/预测红）；PASS 才算 READY
powershell -ExecutionPolicy Bypass -File delivery\foundationpose_3090\RUN_ON_WINDOWS.ps1 exp013 -Unlock  # 11. EXP-013 正式 5 帧（Stage B，须授权 + $env:CONFIRM_EXP013='YES'）
powershell -ExecutionPolicy Bypass -File delivery\foundationpose_3090\RUN_ON_WINDOWS.ps1 collect       # 12. 汇集 delivery_back/ → 拷回轻薄本
```

## 2b. Linux 机器（备选路线，Docker）

若回退到 Linux 机器执行，runbook 见 `DOCKER.md`（Docker 主）/ `INSTALL.sh`（conda fallback），
脚本同名同协议（`USE_DOCKER=0/1`）。磁盘预估：Docker ≈12–23GB / conda 原生 ≈8–12GB。

## 2c. 磁盘占用预估（Windows 主路径）

| 项 | 预估 | 说明 |
| --- | --- | --- |
| WSL2 Ubuntu 发行版（VHDX） | 1–2 GB | 落在仓库所在盘 |
| conda env `r3p-fp`（torch cu124 含自带 CUDA 库） | 6–8 GB | |
| conda nvcc 12.4 最小工具链（编译 + nvdiffrast 运行期 JIT） | 1–2 GB | |
| checkpoints（refiner + scorer） | **1–2 GB** | ⏳ 下载时实测 |
| BOP 最小数据 + 仓库 + 运行输出 | < 0.3 GB | |
| **合计** | **≈ 10–15 GB（典型 ~12 GB）** | **建议预留 25 GB**；`doctor` 步骤自动检查 |

（Linux 备选路线：Docker ≈12–23GB、conda 原生 ≈8–12GB——见 `DOCKER.md`。）

## 3. Gates

- **Smoke gate**（步骤 10-11）必须全部满足才算 `READY FOR EXP-013`：
  GPU 可用 ✓ FoundationPose 可导入 ✓ checkpoint 加载 ✓ obj5 输入加载 ✓
  `register()` 返回 4×4 位姿 ✓ GT pose 未参与 ✓
- **EXP-013 gate**（步骤 12）：`RUN_EXP013.sh` 内置 `EXECUTION_LOCKED=true`——
  需要 `--unlock` 且 `CONFIRM_EXP013=YES` 双确认；运行前再次检查环境/权重/数据/config。
- Smoke 结果标 `is_smoke=true`，**不得当作 EXP-013 benchmark 引用**。

## 4. 执行完成后拷回轻薄本

运行 `COLLECT_RESULTS.sh` 后，把 `delivery_back/` 整目录拷回。内含：
`manifest.json`（含逐帧预测位姿）、`prediction_pose.json`、`runtime_manifest.json`、
overlays、env_manifest、FP commit 记录、SHA256SUMS、日志。
**原始 dataset、conda 环境、FoundationPose 源码、权重一律不需要回传。**

## 5. PENDING_3090（本 Bundle 无法在轻薄本获得的真值）

- GPU 型号 / Windows driver 版本 / WSL2 CUDA 直通可用性（`doctor` 步骤实测）
- WSL 内 conda 环境的实际安装结果与版本组合（INSTALL 输出）
- checkpoints 的实际文件名/大小/sha256（官方 Google Drive 未发布 checksum；
  下载后在本机计算 sha256 记录进 manifest）
- 官方 FoundationPose checkout 的确切 commit（克隆后立即记录）
- runtime smoke 的真实结果（`r3p.foundationpose.runtime` 的接线代码按
  PHASE4_PREFLIGHT §5 源码级审计实现，但**从未在本机执行过**——smoke gate 就是验证它，
  尤其在 WSL2 这一社区验证路线下）

## 6. 红线（违反即停）

- 不修改 FoundationPose 官方算法；API 不匹配只允许改 `src/r3p/foundationpose/runtime.py`
  并记录新 commit。
- 不把 GT pose 传入 inference（runner 有 `assert_no_gt_pose` 结构守卫）。
- 不用 mock 冒充 FoundationPose 结果；mock 只做 plumbing（pytest）。
- 不动原始 BOP 数据（只读）；不动轻薄本的 `r3p` conda 环境；3090 上新建 `r3p-fp`。
- 任何 ≥1GB 下载（权重）按项目预算规则先报批清单。
