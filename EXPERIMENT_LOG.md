# EXPERIMENT_LOG

> 记录规范：每个实验一条记录，必须包含 Question / Hypothesis / Setup / Result / Analysis / Decision。
> 原始数据（metrics.json、日志、可视化）存放在 `outputs/<exp_name>/<timestamp>/`，本文件记录要点与结论。

---

## EXP-000 — Phase 0 Smoke（pipeline 骨架验证）

- **日期**：2026-08-30
- **Phase**：0
- **Question**：Phase 0 搭建的骨架（配置 → 合成数据 → 几何 → 评测 → 可视化 → 日志）能否通过统一入口端到端运行，且数值行为正确？
- **Hypothesis**：
  1. GT 位姿自评估的 ADD / ADD-S / 平移 / 旋转误差 ≈ 0；
  2. 随扰动幅度增大（旋转 0→20°，平移 0→40 mm），ADD 单调非降；
  3. 纯旋转扰动的旋转误差应精确等于扰动角度；纯平移扰动的平移误差应精确等于扰动幅度。
- **Setup**：
  - 数据：合成立方体（0.10×0.07×0.05 m，表面结构化网格采样，保留精确对称性），
    640×480 合成深度图（散点 z-buffer 渲染），针孔内参 fx=fy=570, cx=320, cy=240
  - GT 位姿：axis-angle（axis=[1,2,3]/√14，30°），t=[0, 0, 0.8] m
  - 扰动（相机系左乘 ΔT，固定轴 [1,2,3]、固定方向 [1,−1,0.5]，确定性无随机）：
    - rot_only：0/2/5/10/20°（平移 0）
    - trans_only：0/5/10/20/40 mm（旋转 0）
    - combined：两者同级组合
  - 指标：ADD、ADD-S、平移误差、旋转误差；模型点 2000
  - 入口：`python -m r3p.experiments.run_smoke --config configs/smoke.yaml`
- **Result**：待填（运行后填写）
- **Analysis**：待填
- **Decision**：待填
