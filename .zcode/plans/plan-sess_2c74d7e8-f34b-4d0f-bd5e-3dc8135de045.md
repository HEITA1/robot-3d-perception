# Phase 0 计划：项目基础设施（已获批准内容 + 三条补充约束）

## 已确认决策（全部写入 PROJECT_CONTEXT / PROJECT_SPEC）
1. **数据**：YCB-V 未下载；Phase 1 采用 BOP 格式**最小子集（~1–2 GB，1–2 个物体）**；**未经批准不下载全量/数十 GB 级数据**。
2. **Git**：origin = `https://github.com/HEITA1/robot-3d-perception`（私有）；.gitignore 覆盖 `data/ datasets/ outputs/ checkpoints/ weights/ *.pt *.pth` 等；不推大文件；认证失败只报告，不擅动 SSH/gh 配置。
3. **版本策略**：requirements.txt 记录"实际安装成功 + pytest 全绿 + smoke 成功"后的实测版本；不追新、不为锁版本制造冲突。
4. **Scope 冻结**：Phase 0 不下载 YCB-V、不装 PyTorch、不动 3090 环境、不实现 PnP/ICP/训练/FoundationPose；YCB-V 下载须先报清单+空间、经批准后执行。
5. **计算环境（新增）**：当前开发机为**无 NVIDIA GPU 的轻薄本**，Phase 0 一切以 **CPU 环境**为目标，不假设 CUDA 存在；RTX 3090 在另一台机器且使用中，Phase 0 不访问/配置/迁移；Phase 3 需 GPU 时再单独规划迁移方案。此约束写入 PROJECT_CONTEXT.md 作为长期环境前提。

## Exit Criteria
一条命令完成最小端到端实验：
`python -m r3p.experiments.run_smoke --config configs/smoke.yaml`
→ 合成 RGB-D 场景 → 针孔模型生成点云 → SE(3) 变换 → ADD/ADD-S/平移/旋转误差评估（GT vs 多级扰动）→ 日志 + metrics.json + 可视化 PNG 落盘 `outputs/`。
同时：pytest 全绿、五份研究记录文档建立、git + origin 配置完成并推送。

## 执行步骤
- **P0.1 仓库与文档**：`git init -b main` → origin 配置 → `.gitignore` → 文档五件套（PROJECT_CONTEXT / PROJECT_SPEC / EXPERIMENT_LOG / MODULE_MAP / CHANGELOG，含实质初始内容与上述五条决策）+ README → 首次 commit + push（尽早验证认证；失败即报告）。
- **P0.2 Python 环境（纯 CPU）**：探测 conda（有则建独立 env `r3p`，Python 3.10/3.11；无则 venv）→ 安装 CPU 依赖（numpy/scipy/opencv-python/open3d/pyyaml/matplotlib/tqdm/pytest）→ `pyproject.toml`（editable install + pytest 配置）→ requirements.txt 记录实测版本。不装 PyTorch、不装任何 CUDA 组件。
- **P0.3 包骨架 `src/r3p/`**：config（YAML+CLI 覆盖）、logging_utils（run 目录）、utils/checkpoint、geometry/（camera: project/deproject；se3: 合成/求逆/旋转表示/角度误差）、datasets/（base 协议 + synthetic 合成场景 + ycbv_bop 占位）、evaluation/（metrics: ADD/ADD-S/平移/旋转；evaluator 汇总表）、visualization/viz.py（matplotlib PNG 兜底 + Open3D 交互可选）、experiments/run_smoke.py 统一入口。全 CPU 路径。
- **P0.4 单元测试**：test_se3（合成/求逆/往返/角度边界）、test_metrics（手算用例、对称物体 ADD-S 不变性）、test_camera（投影↔反投影往返）、test_synthetic（形状/单位/重投影一致性）、test_config。
- **P0.5 运行与汇报**：pytest 全绿 → smoke 单调性验证（GT ADD≈0，扰动越大误差越大）→ 结果写入 EXPERIMENT_LOG（EXP-000）→ 更新 MODULE_MAP/CHANGELOG → 最终 commit + push → **输出 Milestone Report 后停止，不进入 Phase 1**。

## 停止条件
遇到架构级重大决策、依赖无法解决、GitHub 认证问题、超出 Scope 事项 → 暂停汇报。Exit Criteria 全部验证后立即停止。