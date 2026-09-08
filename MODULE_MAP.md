# MODULE_MAP

> 当前代码模块及职责。随代码演进持续更新。
> 状态：`[x]` 已实现 / `[~]` 占位 / `[ ]` 计划中。

| 模块 | 职责 | 状态 |
| --- | --- | --- |
| `src/r3p/config.py` | YAML 配置加载/合并 + CLI `--set` 覆盖（点号键） | [x] |
| `src/r3p/logging_utils.py` | console+file logger；run 目录管理 `outputs/<exp>/<timestamp>/` | [x] |
| `src/r3p/utils/checkpoint.py` | 通用 dict checkpoint 保存/加载（Phase 3 接 torch） | [x] |
| `src/r3p/geometry/camera.py` | 针孔相机：project / deproject（RGB-D→点云）、make_K | [x] |
| `src/r3p/geometry/se3.py` | SE(3) 合成/求逆/apply；旋转矩阵/四元数/轴角；旋转角度误差 | [x] || `src/r3p/datasets/base.py` | 数据接口协议（rgb/depth/K/masks/gt_poses/model_points，单位：米） | [x] |
| `src/r3p/datasets/synthetic.py` | 合成 RGB-D 场景（box/cylinder，结构化采样保留精确对称性，零下载） | [x] |
| `src/r3p/datasets/ycbv_bop.py` | YCB-V BOP 格式数据集接口（单位转换集中边界：depth×depth_scale×1e-3、t mm→m、模型 mm→m；mask/gt_id/visib_fract） | [x] |
| `src/r3p/evaluation/metrics.py` | ADD / ADD-S / 平移误差 / 旋转误差（纯 numpy + scipy cdist） | [x] |
| `src/r3p/evaluation/evaluator.py` | 逐帧累积 → 按物体汇总表 | [x] |
| `src/r3p/pose/sift_pnp.py` | P2.0 经典基线构件：SIFT 参考库（深度提升）/ knn+ratio 匹配 / PnP-RANSAC+精化 | [x] |
| `src/r3p/learn/` | P3.0-S 学习 spike：umeyama/RANSAC、CoordNet（~59k 参数逐点 canonical 回归）、合成数据生成（渲染器直出标签） | [x] |
| `src/r3p/experiments/run_p3_0.py` | gen/train/gate1/sanity/gate2 子命令（sanity 为训练前强制门；train 支持 ADD/ADD-S loss） | [x] |
| `src/r3p/pose/geo_init.py` | P2.3 几何基线：mask→点云（确定性排序）→PCA→24 假设→point-to-plane ICP（推理零 GT pose）；`estimate_pose` = Phase 3 可替换推理接口 | [x] |
| `src/r3p/pose/render_templates.py` | P2.1 渲染模板：ASCII PLY(UV/法线) 解析 + RaycastingScene CPU 渲染 + Fibonacci 视角 + Lambert 材质 | [x] |
| `src/r3p/visualization/viz.py` | matplotlib 静态 PNG（headless 安全）+ Open3D 交互（可选） | [x] |
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
| `scripts/verify_ycbv_data.py` | 数据集下载后完整性验证（GT 存在性/文件配对/往返/GT 叠加） | [x] |
| `scripts/p2_0_intra_scene_control.py` | P2.0 归因对照实验（同场景参考库，排除评测帧） | [x] |
| `src/r3p/experiments/run_p2_1.py` | P2.1 统一入口（渲染模板库 → SIFT → PnP，与 P2.0 可比） | [x] |
| `src/r3p/experiments/run_p2_3.py` | P2.3 统一入口（两阶段评估/fitness 选择/失败 taxonomy/四重 overlay） | [x] |
| `tests/` | se3/metrics/camera/synthetic/config（28）+ 真实 YCB-V（7）+ pose 合成回归（3）+ learn（5）+ render_templates（4）+ geo_init（5），共 52 项（含点云确定性回归） | [x] |
| PnP / RANSAC（计划 `geometry/solver.py`） | 2D-3D 位姿求解 | [ ] Phase 2 |
| ICP（计划 `registration/icp.py`） | 点云配准 / 位姿精化 | [ ] Phase 2 |
| RGB/点云编码器 + 融合 + 位姿头（计划 `models/`） | 学习基线 | [ ] Phase 3 |
| FoundationPose 适配（计划 `external/`） | 推理适配 + 统一评测接入 | [ ] Phase 4 |
| 遮挡/深度噪声模拟（计划 `robustness/`） | 鲁棒性实验 | [ ] Phase 5 |
