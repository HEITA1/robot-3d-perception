# expected_outputs — 各步骤应产出什么（3090 上核对）

## CHECK_ENV.sh（步骤 5 / 8）
- 终端：逐项 PASS/FAIL/UNKNOWN + `SUMMARY: PASS=x FAIL=y`
- 文件：`outputs/phase4_foundationpose/env_manifest.txt`（版本留档）
- 步骤 5 预期：GPU/编译器 PASS、conda env 相关 FAIL（未安装）——正常
- 步骤 8 预期：**全部 PASS**（否则不得进入 smoke）

## INSTALL.sh（步骤 6）
- `outputs/fp_commit.txt`（官方 checkout 的 HEAD commit）
- conda env `r3p-fp` 可激活；`import estimater`（FP repo）与 `import r3p` 均可

## PREPARE_DATA.sh（步骤 9）
- 终端：5 帧逐帧 `units OK`（depth meter band / mask 像素数 / mesh 点数）
- 最后一行 `PREPARE_DATA PASS`

## RUN_SMOKE_TEST.sh（步骤 10）
- `outputs/phase4_foundationpose/smoke_test/`：
  - `manifest.json`（`is_smoke=true`、`foundationpose_repo_commit`、逐帧
    ADD/ADD-S/trans/rot、`predicted_poses_T_cam_model`）
  - `prediction_pose.json`、`runtime_manifest.json`
  - `overlay_000050_000620.png`（GT 绿 / 预测红——人工目检）
- 终端：`SMOKE RESULT: PASS — READY FOR EXP-013`（ADD<19.65mm 时）
- **smoke ≠ EXP-013**：不要引用 smoke 的 ADD 作为实验结果

## RUN_EXP013.sh（步骤 12，Stage B）
- `outputs/phase4_foundationpose/fp_exp004_feasibility/`：
  `manifest.json`（5 帧 + 预测位姿 + summary）+ 5 张 overlay
- 该目录 + manifest 即 EXP-013 正式记录（回传入档 EXPERIMENT_LOG）

## COLLECT_RESULTS.sh（步骤 13）
- `outputs/phase4_foundationpose/delivery_back/`：
  `smoke_test/`、`exp013_fp_exp004_feasibility/`、`env_manifest.txt`、
  `fp_commit.txt`、`SHA256SUMS`
