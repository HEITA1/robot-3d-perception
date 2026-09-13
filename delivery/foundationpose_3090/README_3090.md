# README_3090 — FoundationPose 3090 Execution Bundle (Stage A)

> 目标机器：RTX 3090 Ubuntu（本项目从未使用过）。本 Bundle 在轻薄本上准备（Stage A-LOCAL），
> 由用户手动拷贝到 3090。**本机（轻薄本）无 NVIDIA GPU：任何 GPU/CUDA/FP runtime 步骤
> 都只能在这台 3090 上发生**——标 `PENDING_3090` 的字段在 3090 执行时才获得真值。

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

## 2. 执行顺序（每步都在 3090 上）

```text
 1. cd /home/<user>/robot-3d-perception
 2. 把 BOP 最小数据放到 data/ycbv/...            （DATA_MANIFEST.md）
 3. git clone https://github.com/NVlabs/FoundationPose.git   # 官方仓库
 4. 记录 commit：git -C FoundationPose rev-parse HEAD        # 写入 fp_commit.txt
 5. bash delivery/foundationpose_3090/CHECK_ENV.sh            # 预期：GPU/编译器 PASS，conda env 部分 FAIL（未装）
 6. bash delivery/foundationpose_3090/INSTALL.sh              # 建 r3p-fp env + 依赖 + 编译（safe-fail）
 7. 下载官方 checkpoints（DOWNLOAD_WEIGHTS.md；仅官方 Google Drive）
 8. bash delivery/foundationpose_3090/CHECK_ENV.sh            # 预期：全部 PASS
 9. bash delivery/foundationpose_3090/PREPARE_DATA.sh         # 数据完整性 + 单位守卫（CPU 可跑）
10. conda activate r3p-fp
    bash delivery/foundationpose_3090/RUN_SMOKE_TEST.sh       # 单帧 620 runtime gate
11. 检查 outputs/phase4_foundationpose/smoke_test/（manifest + overlay 人工目检）
12. 仅在用户明确授权后（Stage B）：
    CONFIRM_EXP013=YES bash delivery/foundationpose_3090/RUN_EXP013.sh --unlock
13. bash delivery/foundationpose_3090/COLLECT_RESULTS.sh      # 汇集 delivery_back/
14. 把 delivery_back/ 拷回轻薄本（结果回传清单见 §4）
```

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

- GPU 型号 / driver 版本 / CUDA toolkit / nvcc / gcc 兼容性
- conda env `r3p-fp` 的实际安装结果与版本组合
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
