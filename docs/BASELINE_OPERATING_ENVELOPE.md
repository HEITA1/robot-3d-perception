# BASELINE OPERATING ENVELOPE — 冻结 Classical Baseline（P2.3-S/P2.4 谱系）

> 日期：2026-09-13 ｜ 依据：EXP-006（历史 75 帧全量）+ EXP-014（W2-3 统一 10 帧子集）
> 的真实结果与只读数据探针。**本文档是观察记录，不是参数优化结果**（§5 non-goals）。
> 数据表：`outputs/w2_3/unified_table.md` ｜ 实验记录：`EXPERIMENT_LOG.md` EXP-014

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

## 3. Observed envelope（EXP-006 + EXP-014 实测）

| 区域 | 表现 | 证据 |
| --- | --- | --- |
| 大尺寸 / 复杂几何 / 强纹理 | **强**（成功帧 ~1–3.5mm） | obj15 drill 10/10（med 1.21mm）；obj2 box 7/10；obj10 banana 7/10；obj5 bottle 93.3%（med 1.30mm） |
| 旋转对称 + 开曲面 | 中（遮挡敏感） | obj13 bowl 77.3%（16 帧 no-converge 集中于重遮挡） |
| 小型扁平物体（d≲100mm） | **不进入 solver** | obj6 tuna：mask 健康（5–8k px）但整只网格 @5mm 体素仅 990 点，可见子集 < 500 下限 → 10/10 `insufficient_observation`（attempted=0） |
| 低纹理 + 凹面 | **ICP 不收敛为主** | obj14 mug：7/10 未过 fitness/rmse 门 + 2 帧 roll 翻转 → 0/10 pose（attempted=9） |
| 近对称物体 | roll/翻面歧义 | obj5 roll×5、obj2 roll×3、obj10 roll×1、obj14 roll×2——ADD-S 好、ADD 差的统一签名 |

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
