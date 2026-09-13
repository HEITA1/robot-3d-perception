# MODULE_MAP

> 当前代码模块及职责。随代码演进持续更新。
> 状态：`[x]` 已实现 / `[~]` 占位 / `[ ]` 计划中。

| 模块 | 职责 | 状态 |
| --- | --- | --- |
| `src/r3p/config.py` | YAML 配置加载/合并 + CLI `--set` 覆盖（点号键） | [x] |
| `src/r3p/logging_utils.py` | console+file logger；run 目录管理 `outputs/<exp>/<timestamp>/` | [x] |
| `src/r3p/utils/checkpoint.py` | 通用 dict checkpoint 保存/加载（Phase 3 接 torch） | [x] |
| `src/r3p/geometry/camera.py` | 针孔相机：project / deproject（RGB-D→点云）、make_K | [x] |
| `src/r3p/geometry/se3.py` | SE(3) 合成/求逆/apply；旋转矩阵/四元数/轴角；旋转角度误差 | [x] |
| `src/r3p/datasets/base.py` | 数据接口协议（rgb/depth/K/masks/gt_poses/model_points，单位：米） | [x] |
| `src/r3p/datasets/synthetic.py` | 合成 RGB-D 场景（box/cylinder，结构化采样保留精确对称性，零下载） | [x] |
| `src/r3p/datasets/ycbv_bop.py` | YCB-V BOP 格式数据集接口（单位转换集中边界：depth×depth_scale×1e-3、t mm→m、模型 mm→m；mask/gt_id/visib_fract） | [x] |
| `src/r3p/evaluation/metrics.py` | ADD / ADD-S / 平移误差 / 旋转误差（纯 numpy + scipy cdist） | [x] |
| `src/r3p/evaluation/evaluator.py` | 逐帧累积 → 按物体汇总表 | [x] |
| `src/r3p/pose/sift_pnp.py` | P2.0 经典基线构件：SIFT 参考库（深度提升）/ knn+ratio 匹配 / PnP-RANSAC+精化 | [x] |
| `src/r3p/learn/` | P3.0-S 学习 spike：umeyama/RANSAC、CoordNet（~59k 参数逐点 canonical 回归）、合成数据生成（渲染器直出标签） | [x] |
| `src/r3p/experiments/run_p3_0.py` | gen/gate1/sanity/gate2 子命令（sanity 为训练前强制门）。注：曾有的 train 子命令（ADD-S loss 变体）随 P3.0-S closeout 回退，未入 git 历史；bowl checkpoint 为其非正式产物 | [x] |
| `src/r3p/pose/geo_init.py` | P2.3 几何基线：mask→点云（确定性排序）→PCA→24 假设→point-to-plane ICP（推理零 GT pose）；`estimate_pose` = Phase 3 可替换推理接口 | [x] |
| `src/r3p/pose/render_templates.py` | P2.1 渲染模板：ASCII PLY(UV/法线) 解析 + RaycastingScene CPU 渲染 + Fibonacci 视角 + Lambert 材质 | [x] |
| `src/r3p/visualization/viz.py` | matplotlib 静态 PNG（headless 安全）+ Open3D 交互（可选） | [x] |
| `src/r3p/visualization/demo.py` | W2-1 demo 工件流水线：read-only 合成 P2.3/P2.4 stored overlay/CSV → 标注静态图 / MP4 序列 / filmstrip；pose 渲染复用 `draw_quad_overlay`（零 convention 重定义）+ GT convention 检查 | [x] |
| `scripts/build_demo.py` | demo 工件 CLI（--experiment/--scene/--object/--start-frame/--end-frame/--output/--mode；累积 manifest；构建前强制 GT 检查） | [x] |
| `src/r3p/experiments/run_smoke.py` | Phase 0 统一入口 smoke 实验 | [x] |
| `src/r3p/experiments/run_ycbv_demo.py` | Phase 1 真实数据 demo：RGB-D→点云→GT 投影→PNG | [x] |
| `src/r3p/experiments/run_p2_0.py` | P2.0 spike 统一入口（10 帧 SIFT+PnP，per-frame CSV + overlay + metrics.json） | [x] |
| `configs/smoke.yaml` | smoke 实验配置 | [x] |
| `configs/p2_0.yaml` | P2.0 spike 配置（参考/评测场景、PnP/成功阈值参数） | [x] |
| `configs/p2_1.yaml` | P2.1 渲染模板配置（16 视角/radius，其余与 P2.0 一致） | [x] |
| `configs/p2_2.yaml` | P2.2 配置（唯一变量：reference.n_frames 3→75，其余冻结） | [x] |
| `configs/p2_3.yaml` | P2.3 几何基线配置（ICP schedule/选择阈值/成功判据，跑前冻结） | [x] |
| `configs/p2_4.yaml` | P2.4 全量工程验证配置（75+75 帧，参数与 P2.3-S 冻结一致） | [x] |
| `configs/p3_0_gate3.yaml` | P3.0-S Gate 3 真实 YCB-V smoke test 配置（测试帧/pipeline/判定标准） | [x] |
| `configs/evaluation_objects.yaml` | W2-2 评测物体集 registry（7 物体选择记录；`evaluated` 仅标记有真实实验的 anchors，非结果文件） | [x] |
| `scripts/p3_0_gate3.py` | Gate 3 执行脚本（独立入口，oracle mask→CoordNet→RANSAC→ICP→评测） | [x] |
| `scripts/_audit_coordinate_transform.py` / `_debug_gate3.py` | 变换链审计（合成闭环 4°/4mm）/ D1–D6 逐层故障定位 | [x] |
| `scripts/p3_1_a_robust_norm.py` | P3.1-A 单变量消融（max→p95 归一化，Outcome D） | [x] |
| `scripts/p3_1_b_canonical_analysis.py` | P3.1-B 分层分解（raw/trans/rigid/sim，发现 ~176.5° 系统旋转） | [x] |
| `scripts/p3_1_c_posthoc_rotation.py` | P3.1-C 判定性诊断（预注册固定旋转 −176.5°，0/10→10/10） | [x] |
| `scripts/p3_1_d_canonical_frame_audit.py` | P3.1-D canonical frame 约定审计（读取器等价性/Kabsch 恒等/判别器，Case B） | [x] |
| `scripts/p3_1_e_input_sensitivity.py` | P3.1-E 输入敏感性诊断（四条件 × 10 帧 + 合成对照，几何通路归因） | [x] |
| `scripts/p3_1_f_geometry_distribution.py` | P3.1-F 几何分布审计（网络真实输入 vs 合成的分布/覆盖/域差量化，两 regime 划分） | [x] |
| `scripts/p3_1_g_noise_sanity.py` | P3.1-G Phase 1 深度噪声量级 sanity check（3×3 高通残差 + 平滑门控；1mm 不被支持） | [x] |
| `src/r3p/foundationpose/` | Phase 4 项目侧集成：InferenceInput/EvaluationData（GT 结构性隔离）、单位规则与断言、adapter、mock backend、evaluator/viz wrapper、EXP-013 冻结配置 | [x] |
| `scripts/run_foundationpose_exp013.py` | 3090 runner（环境门控→adapter→backend→evaluator→manifest；mock 仅 _mock 目录） | [x] |
| `scripts/foundationpose_env_check.py` | 13 组件环境检查器（GPU/CUDA/torch-cuda/nvdiffrast/pytorch3d/FP source/checkpoint/dataset/config） | [x] |
| `scripts/verify_ycbv_data.py` | 数据集下载后完整性验证（GT 存在性/文件配对/往返/GT 叠加） | [x] |
| `scripts/p2_0_intra_scene_control.py` | P2.0 归因对照实验（同场景参考库，排除评测帧） | [x] |
| `src/r3p/experiments/run_p2_1.py` | P2.1 统一入口（渲染模板库 → SIFT → PnP，与 P2.0 可比） | [x] |
| `src/r3p/experiments/run_p2_3.py` | P2.3 统一入口（两阶段评估/fitness 选择/失败 taxonomy/四重 overlay） | [x] |
| `tests/` | se3/metrics/camera/synthetic/config（28）+ 真实 YCB-V（7）+ pose 合成回归（3）+ learn（5）+ render_templates（4）+ geo_init（5）+ foundationpose（11）+ demo（10）+ evaluation_objects registry（9），共 82 项（本地全量；CI 上数据相关测试自动跳过） | [x] |
| PnP / RANSAC（`pose/sift_pnp.py` 内，cv2.solvePnPRansac） | 2D-3D 位姿求解（P2.0 路线，已证伪并关闭） | [x]（路线关闭） |
| ICP（`pose/geo_init.py::icp_refine`，Open3D point-to-plane） | 点云配准 / 位姿精化（P2 Classical 基线核心） | [x] |
| RGB/点云编码器 + 融合 + 位姿头（计划 `models/`） | 学习基线 | [ ] Phase 3 |
| FoundationPose 集成（`src/r3p/foundationpose/` + scripts） | adapter/schema/单位断言/mock backend/evaluator/EXP-013 runner/env checker；runtime 接线待 3090 | [x]（runtime ⏳） |
| 遮挡/深度噪声模拟（计划 `robustness/`） | 鲁棒性实验 | [ ] Phase 5 |
