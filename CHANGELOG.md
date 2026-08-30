# CHANGELOG

> 重要实现变化（不是每个 commit 都记）。格式：日期 + Phase + 变更。

## 2026-08-30 — Phase 2 / P2.2：真实参考库 3→75 帧（阴性结果，结论闭环）

- `run_p2_0` 增加只读验证日志：参考库自洽性（model 3D→GT→project 回到原关键点）
  与库统计（帧数/descriptor 数/每帧分布/重复计数）；`output.name` 可配置。
- 新增 `configs/p2_2.yaml`：唯一变量 reference.n_frames 3→75（scene 52 全部），其余参数冻结。
- 新增 `verify_reference_consistency` / `reference_statistics`（sift_pnp.py，只读诊断）。
- **结果（EXP-004）**：0/10；good 匹配反降（43→13 中位，ratio test 自相似压制）；in-mask 0–2。
  表观证据：scene 52 全程 bottle 背面躺放，scene 50 评测帧正面立姿——可见表面不相交。
- **SIFT+PnP 跨场景路线在 scene50↔52 上判定不可行（三变体归因链完整）；停止，后续路线待批。**

## 2026-08-30 — Phase 2 / P2.1：多视角渲染模板库（方案 B，阴性结果）

- 纹理核实：BOP PLY 原生带 texture_u/v + 4096² 纹理 PNG；Open3D 读取器不暴露 → 直接解析 ASCII PLY（模型自身数据，零新依赖）。
- 新增 `src/r3p/pose/render_templates.py`：RaycastingScene CPU 渲染（Fibonacci 确定性视角、每像素 UV 采样 + 模型帧 3D + z-depth、Lambert 头灯简单材质）。
- 新增 `run_p2_1.py` + `configs/p2_1.yaml`：除参考库来源外与 P2.0 严格可比。
- **结果（EXP-003）**：平铺 0/10、Lambert 0/10（in-mask 0–8）——视点覆盖未解决问题；诊断确认 **render→real 域差主导**（渲染↔渲染可匹配，渲染→照片 in-mask≈2 vs 真实参考 52）。
- 新增渲染一致性回归测试 4 项（已知视角重投影 3e-13 px、Fibonacci 确定性、单位、防零样本）；全套 42/42。
- 模板生成策略需变更：停止并汇报，P2.1 后续路线待批准。

## 2026-08-30 — Phase 2 / P2.0：SIFT + PnP-RANSAC feasibility spike

- 新增 `src/r3p/pose/sift_pnp.py`：深度提升 SIFT 参考库构建（GT 仅用于离线模板）、
  knn+Lowe-ratio 匹配（支持 GT mask 过滤）、solvePnPRansac（EPnP）+ 全内点精化。
  约定防线：残差一律用本项目 `project()` 计算，合成零噪声测试锁定 OpenCV↔SE(3) 约定。
- 新增 `run_p2_0.py` + `configs/p2_0.yaml`：10 固定帧统一入口，四级成功定义
  （feature/match/solver/pose ADD<0.1d），per-frame CSV + 全帧 overlay + matches 调试图。
- **主实验结果（跨场景，EXP-002）**：0/10 solver 成功，in-mask 匹配 0–6 个。
- **归因（三重诊断）**：提升自检 0.000px、同场景对照 8/10（ADD 1.1–16.6mm，纯 PnP）→
  管线正确，失败 = 3 帧参考库视点覆盖不足（SIFT 视点不变性边界）。
- 新增 `scripts/p2_0_intra_scene_control.py`（归因对照，排除评测帧，防泄漏）。
- 新增合成回归测试 3 项（精确恢复/退化输入/SIFT 冒烟）；全套 38/38 通过。
- 过程修复：knnMatch 解包、RANSAC 后精化、drawMatches 参数序/trainIdx 重映射、RGB/BGR 写图。

## 2026-08-30 — Phase 1 实现：YCB-V 真实数据接口与 demo

- 实现 `YcbvBopDataset`：接入本地 test_bop19 子集（默认 obj 5 mustard_bottle + obj 13 bowl，
  `require_objects` 过滤无目标帧）；单位转换集中在接口边界（depth raw×depth_scale×1e-3、
  cam_t_m2c mm→m、模型 ply mm→m），接口输出全为米；支持 mask_visib / gt_instance_ids / visib_fract。
- 实现 `run_ycbv_demo`：真实帧 RGB-D→点云→GT SE(3) 变换→投影叠加→三面板 PNG（Exit Criteria demo）。
- 新增 7 项真实数据测试（无数据环境自动跳过）：往返、单位（物理区间 + 官方 diameter 交叉验证）、
  GT 投影 vs mask_visib 一致性（recall>0.9）、obj 映射、索引非空显式断言、单实例假设、观测契约。
  全套 35/35 通过。所有抽样循环含 `checked > 0` 断言，防零样本假 PASS。
- **语义发现**：models_info `diameter` = 顶点最大点对距离（非 bbox 长边）——初版单测误用 bbox
  被当场抓住并修正；Phase 2 的 0.1d 阈值须按此语义（EXP-001）。
- 确认全子集无单帧多实例 → dict-per-object 接口安全（有回归测试防守）。

## 2026-08-30 — Phase 1 数据获取与验证（按批准范围执行）

- 按批准提案下载 3 个 BOP ycbv 文件（base 15KB / models 500MB / test_bop19 630MB，合计 1.13GB），
  unzip -t 校验通过后解压至 `data/ycbv/` 并删除压缩包；稳态占用 1.6GB，数据不入库。
- **首要裁决通过**：test_bop19 完整包含本地 GT（scene_gt / scene_gt_info / scene_camera / mask / mask_visib），
  Phase 2–5 本地评测路线无需变更。
- 数据验证全部通过（`scripts/verify_ycbv_data.py`，报告：`docs/phase1_data_validation_report.md`）：
  12 场景 × 75 帧、depth_scale=0.1、场景内 K 恒定、深度往返误差 1e-13 px、
  GT 模型投影与 RGB 像素级对齐（mustard_bottle；bowl 经最可见帧 + mask 包围盒双重确认）。
- 确认目标物体：obj5 mustard_bottle（非对称，d=196.5mm）、obj13 bowl（symmetries_continuous，d=161.9mm），
  各 150 个 GT 实例。
- 修复验证脚本"空转通过"缺陷（按物体独立采样替代"同帧双物体"条件）。

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
