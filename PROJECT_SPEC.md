# PROJECT_SPEC

> 当前正式项目规格与验收标准。PROJECT_CONTEXT 回答"为什么"，本文档回答"做什么、做到什么程度算完成"。
> 最后更新：2026-08-30（Phase 0 启动）

## 1. 任务定义

- 输入：RGB 图像 + 深度图 + 相机内参 K（+ 目标物体 mask 与模型点云）
- 输出：目标物体 6D 位姿 T ∈ SE(3)（相机系），及机器人系位姿 `T_robot = E_cam2robot · T`
- 主数据集：YCB-V（BOP 格式，21 个物体；含 bowl/mug/can 等对称物体）

## 2. 数据策略

| 项 | 规定 |
| --- | --- |
| 主数据集 | YCB-V（BOP 格式） |
| 下载原则 | **先报下载清单 + 预计占用空间，经批准后执行**；Phase 1 只下最小子集（~1–2 GB，1–2 个物体） |
| 扩充条件 | YCB-V 主线稳定后，经批准再考虑 HOPEv2 / T-LESS 或扩充 YCB-V |
| 分割来源 | GT mask（Phase 0–3） |

## 3. 评价指标

- 平移误差：`e_t = ||t − t̂||`
- 旋转误差：`e_R = arccos((tr(R̂ᵀR) − 1)/2)`（度）
- ADD / ADD-S（对称物体以 ADD-S 为准；主表同时报告）
- 汇总主表（Phase 5 结束时填写完整）：

| Method（Phase 2 Classical，oracle mask，scene 50/53 各 75 帧） | ADD (mm) mean/med | ADD-S (mm) mean/med | Pose Success |
| ----------------------------------------------------------- | ----------------- | ------------------ | -----------: |
| Classical init（PCA/OBB，obj5 bottle，判据 ADD）            | 73.4 / 84.3       | 25.3 / 24.9        | —（仅初值）  |
| **Classical + ICP（obj5 bottle，判据 ADD<0.1d）**           | 5.27 / 1.30       | 1.22 / 1.21        | **70/75 = 93.3%** |
| Classical init（PCA/OBB，obj13 bowl，判据 ADD-S）           | 140.6 / 149.1     | 68.9 / 73.8        | —（仅初值）  |
| **Classical + ICP（obj13 bowl，判据 ADD-S<0.1d）**          | 90.2 / 2.67（ADD-S median） | 10.3 / 2.67 | **58/75 = 77.3%** |
| Learning Baseline（Phase 3）                                 |                   |                    |              |
| FoundationPose（Phase 4）                                    |                   |                    |              |
| Ours（Phase 5）                                              |                   |                    |              |

注：bowl 的 ADD 高值是旋转对称性的必然结果（判据为 ADD-S）；失败模式：bottle 5 帧 roll 歧义、bowl 16 帧重遮挡 no-converge + 1 帧选择失败（EXP-006）。

- 评测协议细节（阈值、模型点单位、聚合方式）在 Phase 2 实现时确定并记录于此。

## 4. 阶段与 Exit Criteria

| Phase | 内容 | Exit Criteria | 状态 |
| --- | --- | --- | --- |
| 0 基础设施 | 仓库/数据接口/配置/日志/评测/可视化/测试/文档 | 统一入口完成一次最小实验（smoke） | **进行中** |
| 1 3D Geometry | 相机模型/RGB-D/点云/坐标变换/SE(3)/旋转表示 | 输入 RGB-D 正确生成点云并完成坐标系转换与可视化 | 未开始 |
| 2 Classical Pose | 几何路线：mask→PCA/OBB 24 假设→point-to-plane ICP（SIFT+PnP 路线已证伪，见 EXP-002/003/004） | ≥1 个 YCB-V 物体跑通完整 pipeline 并获得标准评价结果 | **完成（P2.4，oracle mask 受控条件）** |
| 3 Learning Pose | RGB/点云编码器/融合/位姿头/loss/训练 | 学习基线稳定训练并在测试数据输出合理 6D 位姿 | 未开始 |
| 4 FoundationPose | 安装/推理/评测适配/对比 | FoundationPose 进入统一实验体系 | 未开始 |
| 5 鲁棒性研究 | 遮挡/噪声实验/失败分析/一个改进/Ablation | 得到有明确实验依据的改进并验证有效 | 未开始 |
| 6 工程包装 | 重构/测试/CLI/文档/Demo/报告 | 别人能理解、运行、展示；本人能讲清楚 | 未开始 |

## 5. Scope Freeze（未经明确批准不得加入）

SLAM / VLA / VLM 训练 / NeRF / 3DGS / RL / 抓取规划 / 运动规划 / 大规模 Foundation Model 训练 /
多传感器融合 / 完整 ROS2 系统 / 目标检测与分割网络训练。

补充冻结条款：

- **数据下载批准制**：任何 ≥1 GB 的新数据下载必须先报告清单与预计占用空间。
- **基线冻结**：锁定 PnP/ICP、1 个学习基线、FoundationPose 三个系统。
- **改进冻结**：全项目只允许 1 个核心改进 + Ablation。
- **Phase 0 冻结**：不下载 YCB-V、不装 PyTorch、不动 3090 环境。

## 6. 实验纪律

每个实验必须记录：Question → Hypothesis → Setup（变量控制）→ Result → Analysis → Decision。
禁止"跑一下看看"。记录位置：`EXPERIMENT_LOG.md`。

## 7. 质量目标

80–85 分档：核心秋招项目。60 分=完成；75 分=可写简历；90+ 有额外时间再说，不作默认目标。
