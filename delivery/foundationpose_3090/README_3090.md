# README_3090 — FoundationPose 3090 Execution Bundle (Stage A)

> 目标机器：RTX 3090 Ubuntu（**共用机**，另有他人使用）。本 Bundle 在轻薄本上准备（Stage A-LOCAL），
> 由用户手动拷贝到 3090。**本机（轻薄本）无 NVIDIA GPU：任何 GPU/CUDA/FP runtime 步骤
> 都只能在这台 3090 上发生**——标 `PENDING_3090` 的字段在 3090 执行时才获得真值。
> **隔离方案：Docker（默认）**——共用机避免依赖冲突，全部依赖固化在镜像内，宿主机零 Python 安装；
> conda 原生路线保留为 fallback（`USE_DOCKER=0`），详见 `DOCKER.md`。

## 0. 这是什么

为 **EXP-013（FoundationPose feasibility）** 准备的一键式执行包：

- 固定协议：obj5 `006_mustard_bottle` · scene 50 · frames **620, 653, 721, 1044, 1113** ·
  oracle `mask_visib` · register/estimation 路径（**无初始位姿、GT pose 零参与 inference**）·
  成功 = ADD < 0.1d = **19.65 mm**。协议来源：`configs/fp_exp013.yaml`（冻结，勿改）。
- Smoke gate：先跑 **1 帧**（frame 620）验证 runtime，通过后才允许正式 5 帧。
- 全部脚本 **safe-fail**：任何一步失败即停止并给出明确原因，不做版本乱试、不做 CPU/mock 回退。

## 1. 拷贝清单（用户手动执行）

1. **整个仓库**到 3090，例如 `/home/<user>/robot-3d-perception/`
   （推荐 `git clone`/拉取后把本 Bundle 目录覆盖过去；仓库在 GitHub，私有，需认证）。
   不要拷贝：`data/`、`outputs/`、`data_synth/`、任何权重/venv/conda 环境。
2. **最小 BOP 数据**（精确清单见 `DATA_MANIFEST.md`，约 30 个小文件 + 1 个 mesh），
   放到仓库同结构路径 `data/ycbv/...` 下。
3. 本 Bundle 已在仓库内 `delivery/foundationpose_3090/`，随仓库一起到位即可。

## 2. 执行顺序（每步都在 3090 上；每行 = 一条可整行复制的命令，说明在行尾 # 后）

```bash
cd /home/<user>/robot-3d-perception                                        # 1. 进入仓库根目录（U 盘的 robot-3d-perception 整体拷到 /home/<user>/）
ls data/ycbv/test/000050/rgb/000620.png                                    # 2. 确认最小数据就位（U 盘已带好 21 个文件；如有缺件对照 DATA_MANIFEST.md 补拷）
git clone https://github.com/NVlabs/FoundationPose.git                     # 3. 克隆官方 FoundationPose（仅官方源；不做任何修改）
mkdir -p outputs && git -C FoundationPose rev-parse HEAD | tee outputs/fp_commit.txt   # 4. 钉死并记录官方 commit（manifest 会引用该值）
bash delivery/foundationpose_3090/DOCKER_SETUP.sh                          # 5. Docker 隔离：拉官方基础镜像（10-20GB）+ 构建派生镜像 + 容器验证
bash delivery/foundationpose_3090/CHECK_ENV.sh                             # 6. 环境检查（自动进容器；checkpoint 未下载前该项 FAIL 属预期）
# 7. 下载官方 checkpoints（约 1-2GB，仅官方 Google Drive；⏳ 文件名/sha256 见 DOWNLOAD_WEIGHTS.md；>=1GB 记得先报批）
bash delivery/foundationpose_3090/CHECK_ENV.sh                             # 8. 环境复查（此次应全部 PASS，含 checkpoint 项）
bash delivery/foundationpose_3090/PREPARE_DATA.sh                          # 9. 数据完整性 + 米制单位守卫（CPU，自动进容器）
bash delivery/foundationpose_3090/RUN_SMOKE_TEST.sh                        # 10. 单帧 smoke gate（frame 620，GPU；打印 READY FOR EXP-013 才算通过）
ls outputs/phase4_foundationpose/smoke_test/                               # 11. 查看 smoke 产物（人工目检 overlay_000050_000620.png：GT 绿 / 预测红）
CONFIRM_EXP013=YES bash delivery/foundationpose_3090/RUN_EXP013.sh --unlock            # 12. EXP-013 正式 5 帧（Stage B，须用户明确授权）
bash delivery/foundationpose_3090/COLLECT_RESULTS.sh                       # 13. 汇集结果到 outputs/phase4_foundationpose/delivery_back/
# 14. 拷回轻薄本：outputs/phase4_foundationpose/delivery_back/ 整目录（环境/数据/权重不需要回传）
```

> fallback：若 Docker 路线不可用（无 docker 权限等），`USE_DOCKER=0 bash .../INSTALL.sh`
> 走 conda 原生路线（L1），其余步骤同名脚本照跑——两套脚本同一协议。

## 2b. 磁盘占用预估（3090）

| 项 | 预估 | 说明 |
| --- | --- | --- |
| 官方基础镜像 `wenbowen123/foundationpose` | **10–20 GB** | ⏳ 实际以拉取输出为准（Preflight 估算） |
| 派生镜像 `r3p-fp:exp013`（增量层） | 0.5–1 GB | 项目 + scipy/opencv/matplotlib/open3d 等轻量层 |
| checkpoints（refiner + scorer） | **1–2 GB** | ⏳ 下载时实测 |
| BOP 最小数据 | ~8 MB | DATA_MANIFEST 清单 |
| 仓库 + Bundle（不含数据/输出） | ~10 MB | |
| 运行输出（smoke + EXP-013 + delivery_back） | < 200 MB | manifest/overlay/日志 |
| docker 构建缓存（临时，可 `docker builder prune`） | 0–2 GB | |
| **合计** | **≈ 12–23 GB（典型 ~15–20 GB）** | **建议预留 25 GB**；`df -h` 确认 |

共享机礼仪：全部占用集中在 docker 镜像与 `<repo>/outputs/`，可整体删除回收
（`docker rmi r3p-fp:exp013` + 基础镜像视共用约定）；不写机器全局目录。

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

- GPU 型号 / driver 版本 / docker + nvidia-container-toolkit 可用性
- 官方基础镜像实际体积与 tag（DOCKER_SETUP 拉取时输出）
- conda 原生路线（fallback）的 nvcc / gcc 兼容性
- checkpoints 的实际文件名/大小/sha256（官方 Google Drive 未发布 checksum；
  下载后在本机计算 sha256 记录进 manifest）
- 官方 FoundationPose checkout 的确切 commit（克隆后立即记录）
- runtime smoke 的真实结果（`r3p.foundationpose.runtime` 的接线代码按
  PHASE4_PREFLIGHT §5 源码级审计实现，但**从未在本机执行过**——smoke gate 就是验证它的）

## 6. 红线（违反即停）

- 不修改 FoundationPose 官方算法；API 不匹配只允许改 `src/r3p/foundationpose/runtime.py`
  并记录新 commit。
- 不把 GT pose 传入 inference（runner 有 `assert_no_gt_pose` 结构守卫）。
- 不用 mock 冒充 FoundationPose 结果；mock 只做 plumbing（pytest）。
- 不动原始 BOP 数据（只读）；不动轻薄本的 `r3p` conda 环境；3090 上新建 `r3p-fp`。
- 任何 ≥1GB 下载（权重）按项目预算规则先报批清单。
