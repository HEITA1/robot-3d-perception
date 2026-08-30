# PROJECT_CONTEXT

> 本文档回答：为什么做这个项目、项目定位是什么、技术路线如何、关键长期决策有哪些。
> 重大决策发生变化时必须更新此文件并注明日期。
> 最后更新：2026-08-30（Phase 0 启动）

## 1. 项目动机

面向 **2027 秋招**的 3D Vision / Robot Perception 核心项目。目标不是发论文、不是刷 SOTA，而是：

> 构建一个**真正理解、能够复现、能够实验、能够解释、最终能够工程化交付**的
> RGB-D 6D Object Pose Estimation 项目。

衡量一切技术选择的三问：

1. 它是否提升我的真实能力？
2. 它是否能形成可验证的实验？
3. 它是否能成为秋招面试中可以讲清楚的成果？

答案是否定的，即使技术再热门也不加入。

## 2. 项目定位

- **秋招导向的高质量算法项目**，目标 80–85 分档（核心秋招项目），不是 100 分。
- 不追求：SOTA、A 会论文、大规模训练、多个创新点、完整机器人系统。
- 毕业标准：RGB-D→点云、坐标变换、SE(3)、PnP/ICP、RGB-D 学习基线、FoundationPose、
  标准 6D 评测、遮挡/深度噪声实验、Failure Analysis、一个针对性改进 + Ablation、可视化 Demo。

## 3. 核心任务

从 RGB-D 输入估计目标物体的 6D Pose，并转换到机器人坐标系：

```text
T = [ R  t ]    R: 3D 旋转    t: 3D 平移    T ∈ SE(3)
    [ 0  1 ]
```

必须能回答："这个物体在相机坐标系中的位姿是什么？转换到机器人坐标系后在哪里？"

## 4. 技术路线

```text
RGB-D
  ├── RGB ────► 2D 特征 / 物体信息（Phase 0–3 使用 GT mask：分割不是变量）
  └── Depth ──► 点云（针孔反投影，几何代码自实现）
        ▼
   3D 表征（RGB 外观特征 ⊕ 几何特征融合）
        ▼
   6D Pose 估计（学习基线：DenseFusion 思想的现代重实现）
        ▼
   Pose Refinement（ICP / 迭代精化）
        ▼
   SE(3) ──► 相机系 ──► 机器人系（hand-eye 外参，可配置；无真实机器人用占位值）
```

方法层次：L1 3D Geometry（自实现）→ L2 Classical（PnP/RANSAC/ICP）→ L3 Learning RGB-D Pose
→ L4 FoundationPose（强参照，纯推理）→ L5 Robustness（遮挡/深度噪声）→ L6 工程与秋招包装。

对照系统锁定为三个（不囤积基线）：

| 系统 | 角色 |
| --- | --- |
| PnP + ICP | 经典几何基线 |
| RGB-D 学习基线（DenseFusion 思想现代重实现） | 学习基线；FFB6D 式融合作为升级路径 |
| FoundationPose | 强参照系统 |

新增基线的唯一理由：它能回答一个明确的问题。

## 5. 鲁棒性研究（研究灵魂）

核心研究问题：**RGB-D Noise and Occlusion 下的 6D Pose Robustness**。

- 遮挡分级：Clean / 20% / 40% / 60%；深度噪声分级：Clean / Mild / Medium / Severe。
- 所有方法在同一评测协议下跑同一组退化实验 → Failure Analysis → 唯一改进点 → Ablation。
- 改进点必须由实验驱动（Baseline → Experiment → Failure Analysis → Bottleneck → Design →
  Ablation），不得提前决定。若 FoundationPose 已足够强，不强行制造创新，
  转为 Robustness Analysis + Failure Analysis + Engineering Insight。

## 6. 关键决策记录

| # | 日期 | 决策 | 理由 |
| --- | --- | --- | --- |
| D1 | 2026-08-30 | 数据集主线 YCB-V，采用 **BOP 格式**；Phase 1 只下最小子集（~1–2 GB，1–2 个物体） | BOP 格式规整、体积小、评测生态统一；磁盘受限 |
| D2 | 2026-08-30 | Phase 0–3 的分割使用 **GT mask** | 分割不是研究变量，控制变量；检测/分割不在 Scope 内 |
| D3 | 2026-08-30 | 学习基线走**现代重实现**（DenseFusion 思想，现代 PyTorch），不复活老仓库 | 老仓库依赖地狱不值得；原则：Modernize / Reimplement / Replace |
| D4 | 2026-08-30 | Git 私有远程 `github.com/HEITA1/robot-3d-perception`，每阶段推送；展示前再决定是否公开 | 一年期项目的云端备份 |
| D5 | 2026-08-30 | 依赖版本以"实际安装成功 + 测试全绿 + smoke 成功"为准记录；不追新、不为锁版本制造冲突 | 可复现 > 新版本 |
| D6 | 2026-08-30 | 相机系→机器人系用**可配置 hand-eye 外参（占位值）**实现 | 无真实机器人；重点是变换的正确实现 |
| D7 | 2026-08-30 | 机器人系变换作为普通 SE(3) 变换放在 geometry 层，不引入 ROS | Scope Freeze |

## 7. 环境约束（长期有效）

- **当前开发机：轻薄本，无 NVIDIA GPU。** Phase 0 一切以 **CPU 环境**为目标，
  代码与依赖不得假设 CUDA 存在。
- **RTX 3090 位于另一台机器**，目前正在使用中。Phase 0 不访问、不配置、不迁移。
- 进入 Phase 3（训练）时，再单独规划"轻薄本 → 3090"的环境与代码迁移方案。
- 不为了老仓库的依赖问题牺牲项目进度（Modernize / Reimplement / Replace 三选一）。

## 8. 角色与流程

- **Zcode（当前）**：Research + Algorithm + Experiment——资料/论文理解、方法设计、算法实现、
  实验、Debug、Failure Analysis、研究决策。算法未稳定前不追求生产级工程架构。
- **Codex（Algorithm Freeze 后）**：工程重构、Test、CI、CLI、Documentation、Demo、
  可复现性、仓库清理、秋招包装。
- 重大决策（换核心任务 / 删核心模块 / 加大型模块 / 换主要数据集 / 换研究问题 / 进新方向）
  必须先说明理由并等待批准。
- 每完成一个 Milestone 按固定格式汇报；未达 Exit Criteria 不得假装完成。

## 9. 风险登记（Phase 0 认知）

1. **评测协议错误**（最致命且最隐蔽）：模型点单位（mm/m）、DenseFusion 0.1d 阈值 vs BOP 协议、
   对称物体处理、聚合方式。对策：metrics 在 Phase 0 实现 + 手算用例单测 + Phase 2 与已发表数字交叉校验。
2. **FoundationPose 环境**：老依赖 + Windows 不友好。对策：Phase 4 独立锁定环境（必要时 WSL2）；
   兜底社区现代化 fork；不阻塞主线。
3. **学习基线收敛**：现代重实现无现成权重。对策：Phase 3 先单物体小序列过拟合验证再扩量。
4. **数据细节坑**：YCB-V 深度单位（原版与 BOP 不同，极易误判）、逐场景内参。
   对策：数据接口"深度→点云→重投影"往返单测 + 可视化人工复核。
5. **实验管理失控**：鲁棒性阶段是 4×4×N 方法矩阵。对策：统一入口 + config + 结果目录约定
   （Phase 0 建立）+ EXPERIMENT_LOG 纪律。
