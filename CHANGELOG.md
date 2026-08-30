# CHANGELOG

> 重要实现变化（不是每个 commit 都记）。格式：日期 + Phase + 变更。

## 2026-08-30 — Phase 0 启动

- 初始化仓库：git（`main` 分支）+ 私有远程 `origin`（github.com/HEITA1/robot-3d-perception）。
- 建立研究记录五件套：PROJECT_CONTEXT / PROJECT_SPEC / EXPERIMENT_LOG / MODULE_MAP / CHANGELOG。
- 确定关键决策 D1–D7（见 PROJECT_CONTEXT.md §6）与环境约束：轻薄本 CPU-only，3090 另机待 Phase 3 迁移。
- 搭建 `src/r3p` 包骨架：config / logging / checkpoint / geometry(camera, se3) /
  datasets(base, synthetic, ycbv_bop 占位) / evaluation(metrics, evaluator) / visualization / experiments。
- 实现 ADD / ADD-S / 平移 / 旋转误差评测与合成数据 smoke 实验统一入口
  （`python -m r3p.experiments.run_smoke`），配套单元测试（se3/metrics/camera/synthetic/config）。
- 依赖版本在 pytest 全绿 + smoke 通过后冻结至 `requirements.txt`（决策 D5）。
