# CHANGELOG

> 重要实现变化（不是每个 commit 都记）。格式：日期 + Phase + 变更。

## 2026-08-30 — Phase 0 启动

- 初始化仓库：git（`main` 分支）+ 私有远程 `origin`（github.com/HEITA1/robot-3d-perception）。
- 建立研究记录五件套：PROJECT_CONTEXT / PROJECT_SPEC / EXPERIMENT_LOG / MODULE_MAP / CHANGELOG。
- 确定关键决策 D1–D7（见 PROJECT_CONTEXT.md §6）与环境约束：轻薄本 CPU-only，3090 另机待 Phase 3 迁移。
- 搭建 `src/r3p` 包骨架：config / logging / checkpoint / geometry(camera, se3) /
  datasets(base, synthetic, ycbv_bop 占位) / evaluation(metrics, evaluator) / visualization / experiments。
- 实现 ADD / ADD-S / 平移 / 旋转误差评测与合成数据 smoke 实验统一入口
  （`python -m r3p.experiments.run_smoke`），配套单元测试（se3/metrics/camera/synthetic/config，28 项全绿）。
- 修复 box 表面采样器总表面积公式（2·Σ → 8·Σ）：修复前 `n_model_points` 实际产出 4 倍点数，
  ADD-S 距离矩阵膨胀 ~500 MB；修复后按配置密度采样（详见 EXP-000）。
- smoke 验证 PASS（EXP-000）：GT 自评估全零、扰动单调性成立、纯旋转/纯平移解析特例精确复现。
- 依赖版本冻结至 `requirements.txt`（实测：numpy 2.4.6 / scipy 1.17.1 / open3d 0.19.0 /
  opencv-python 5.0.0.93 / matplotlib 3.11.1 / PyYAML 6.0.3 / tqdm 4.70.0 / pytest 9.1.1，Python 3.11.16）。

## 2026-08-30 — Phase 1 数据调查（未下载）

- 完成 BOP ycbv 数据包调查：官方包结构与实测体积（base 15KB / models 500MB / test_bop19 630MB；test_all 15GB、train_real 75.7GB 等缓置）。
- 确认官方无按物体拆分的包；最小粒度 test_bop19。1–2 个物体控制在数据接口层实现（拟选 mustard_bottle + bowl）。
- 实测本机 huggingface.co 不可达、hf-mirror.com 可用；D 盘 190GB 可用。
- 核实 BOP 格式细节（深度 16bit×depth_scale、cam_t_m2c 单位 mm、逐图 cam_K、visib_fract 可用于遮挡分层）。
- 识别关键不确定点：test 包是否含 GT 位姿（证据相抵），列为解压后首要裁决项（决策树见提案）。
- 提案文件：`docs/proposal_phase1_data.md`（等待批准，未执行任何下载）。
