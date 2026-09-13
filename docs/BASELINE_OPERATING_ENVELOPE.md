# BASELINE OPERATING ENVELOPE — 冻结 Classical Baseline（P2.3-S/P2.4 谱系）

> 日期：2026-09-13 ｜ 依据：EXP-006（历史 75 帧全量）+ EXP-014（W2-3 统一 10 帧子集）+
> **EXP-015（W2-4 全 scene 75 帧扩评测）** 的真实结果与只读数据探针。
> **本文档是观察记录，不是参数优化结果**（§5 non-goals）。
> 数据表：`outputs/w2_4/unified_table.md`（冻结版）｜ 对照：`outputs/w2_4/w2_3_vs_w2_4_comparison.md`
> ｜ 实验记录：`EXPERIMENT_LOG.md` EXP-014 / EXP-015

---

## 1. Scope

冻结的 classical 6D pose baseline：oracle `mask_visib` → 物体点云（确定性排序）→
PCA/OBB 24 假设 → point-to-plane ICP（3cm→1cm→3mm，≤60 it/段）→ fitness/rmse 选择。
参数自 EXP-005 起冻结：`voxel_m=0.005`、`min_cloud_pts=500`、
`corr_schedule_m=[0.03,0.01,0.003]`、`min_fitness=0.5`、`max_rmse_m=0.004`、
成功判据 ADD(-S) < 0.1×diameter。适用物体集：W2-2 7 物体评测集
（`configs/evaluation_objects.yaml`）。

## 2. Input assumptions

- RGB / depth（米制，BOP `raw×depth_scale×1e-3`）/ `mask_visib` / GT pose（仅评测）/
  CAD mesh（米制）齐备——任何缺失会由数据接口显式报错中止（无静默降级）；
- 点云分辨率：5mm 体素下**可见表面 ≥500 点**（`min_cloud_pts`）——这是硬性进入门槛；
- 针孔相机 K（逐帧来自 scene_camera.json）；
- oracle mask（声明性受控条件：分割质量不是本 baseline 的变量）。

## 3. Observed envelope（EXP-006 + EXP-014 + EXP-015 全量实测）

| 区域 | 表现 | 证据（EXP-015 全 scene 覆盖后） |
| --- | --- | --- |
| 复杂机构 + 强纹理 + 非凸 | **强**（接近完美） | obj15 drill **75/75**（med ADD 1.15mm）——W2-3 的 10/10 在扩评测下完全稳定 |
| 细长弯曲完全非对称 | **强**（条件口径 95.2%） | obj10 banana 59/75（13 帧点数不足为 pre-solver 拒绝；条件成功率 59/62） |
| 旋转对称 + 开曲面 | 中（遮挡敏感） | obj13 bowl 77.3%（16 帧 no-converge 集中于重遮挡；EXP-006） |
| 近对称盒/瓶（roll 歧义主导） | **弱——成功率被翻面支配** | obj2 box **33/75=44%**（roll×42，ADD-S med 4.18mm 但 ADD med 120mm）；obj5 bottle 93.3%（roll×5，近对称程度远弱于盒） |
| 小型扁平物体（d≲100mm） | **不进入 solver** | obj6 tuna：**75/75 全部 `insufficient_observation`（attempted=0）**——10 帧与 75 帧结论完全一致 |
| 低纹理 + 凹面 | **ICP 不收敛为主** | obj14 mug：**0/75 pose**（attempted=62：no_converge×47 + roll×15；insufficient×13） |

**EXP-015 对 W2-3 观察的修正与确认**（详见 `outputs/w2_4/w2_3_vs_w2_4_comparison.md`）：

- **确认**：obj6 点数地板（attempted 0→0）、obj14 低纹理不收敛主导（0% pose 稳定）、
  obj15 复杂几何优势（100% 稳定）、obj10 细长非对称优势（78.7%）；**5 个物体的 failure
  tag 集合在扩评测后全部不变**；
- **修正**：obj2 cracker_box 的 roll 歧义在 10 帧采样中被低估（70% → 全量 44%）——
  「大尺寸/强纹理 ⇒ 强」的早期表述被修正为上表的「近对称 ⇒ roll 歧义支配」；
  对称性（而非尺寸/纹理）是决定性变量。

## 4. Failure regimes（聚合状态视图；原始 failure tag 不变）

| 状态 | 原始 tag | 进 solver？ | 位姿/指标？ | 计入 attempted？ |
| --- | --- | --- | --- | --- |
| INPUT_INVALID | —（数据接口 raise，run 中止） | – | – | –（实测 0 例） |
| PRE_SOLVER_INSUFFICIENT | `insufficient_observation` | **否** | 无 | **否** |
| RUNTIME_ERROR | `runtime_error` | 异常 | 无 | 否（实测 0 例） |
| SOLVER_GATE_FAILURE | `icp_no_converge` | **是**（PCA+ICP 已跑） | **有** | **是** |
| POSE_SUCCESS | `success` | 是 | 有 | 是 |
| POSE_METRIC_FAILURE | `roll_symmetry_ambiguity` / `hypothesis_selection_failure` | 是 | 有 | 是 |

四层统计语义：

- **total** = 冻结确定性采样选中的帧数（CSV 行数）；
- **valid** = 通过输入加载、进入处理的帧数（无效输入会中止运行，故实测 valid=total）；
- **attempted** = 进入 solver 的帧数 = total − PRE_SOLVER_INSUFFICIENT − RUNTIME_ERROR；
- **success** = `ADD(-S) < 0.1d` 且过 solver 门（runner 冻结定义）；
- **success_rate = success / total**（项目 metrics.json 口径）；**conditional pose
  success = success / attempted** 是另一个指标——attempted=0 时显示 N/A（从不写 0/0=0%）；
- 误差中位数 = EXP-006 metrics.json 口径：所有产出指标值的帧（含 gate failures，
  不含 insufficient）——anchor 行逐位复现冻结值（obj5 1.30mm / obj13 2.67mm）。

**关键判读（防误读）**：

- obj6 的 `0/10` **不是** "ICP 失败 10 次"，而是**冻结分辨率/点数门槛下观测不足、
  无法进入 solver**（attempted=0）——Operating Envelope Finding；
- obj14 的 `0/10` 是 attempted=9 上的真实求解失败，其构成为
  7 no-converge + 2 roll + 1 insufficient，非单一模式。

## 5. Current non-goals

- 本文档**不代表参数优化结果**：voxel/`min_cloud_pts`/ICP 调度/选择门限/成功阈值
  全部保持 EXP-006 冻结值，EXP-014 零调参；
- 包络边界的"修复"（如小物体点数协议、低纹理 ICP 策略）属于**协议变体候选**，
  仅记录为 future work（见 `EXPERIMENT_LOG.md` EXP-014 Decision），未经单独提案
  不得执行、不得混入本口径；
- 不覆盖 FoundationPose（EXP-013，runtime 待 3090）——模型-based 路线在同一物体集上
  的对照正是本包络的后续验证。

---

## 6. Baseline Freeze（2026-09-13，W2-4 / EXP-015 达成 DoD 后生效）

自本节起，以下评测口径**冻结**；任何参数/协议/物体集/帧覆盖变化 = 新实验
（EXP-016+，需单独提案），不得改动或混入本口径：

| 冻结项 | 内容 |
| --- | --- |
| evaluation object set | 7 objects（`configs/evaluation_objects.yaml` registry；不再扩到 21 物体） |
| scenes | obj5→scene 50（EXP-006 historical）、obj13→scene 53（EXP-006 historical）、obj2/obj10/obj15→scene 50、obj6/obj14→scene 48 |
| frame coverage | anchors 75 frames（EXP-006 historical）；5 新物体各 75 frames（EXP-015 full-scene，全部帧，无采样丢弃） |
| baseline parameters | 指纹 `584da3b46fa28ed4`（icp/selection/success 三段 canonical JSON sha256[:16]，`tests/test_w2_4.py` 守护——改动即测试失败） |
| metric policy | registry `metric_policy`（逐物体 ADD/ADD-S，pre-registered geometry policy；anchors 沿用 EXP-006 口径） |
| success threshold | ADD(-S) < 0.1×官方 diameter |
| mask condition | oracle `mask_visib`（声明性受控条件） |
| 统计语义 | total/valid/attempted/success 四层 + 双成功率（§4）；误差中位数=EXP-006 metrics.json 约定 |
| known envelope | §3（三个 failure regimes：A 对称歧义 / B 前置观测不足 / C 低纹理 ICP 不收敛） |
| known limitations | 无 21 物体、无多场景、无 robustness 扰动（Phase 5）、FoundationPose 未执行（EXP-013 待 3090）；失败未通过调参修复（红线） |
