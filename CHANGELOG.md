# CHANGELOG

> 重要实现变化（不是每个 commit 都记）。格式：日期 + Phase + 变更。

## 2026-09-10 — Phase 3 / P3.1-F：几何分布审计（两个 failure regime）

- 新增 `scripts/p3_1_f_geometry_distribution.py` + `docs/P3_1_F_GEOMETRY_DISTRIBUTION_AUDIT.md`
  + `outputs/p3_1_f_geo_stats/`（JSON + 覆盖直方图 PNG）。
- 测量网络真实输入（Gate 3 同种子采样 → max-radius 归一化）的分布 vs 合成（Gate 1/2 npz）：
  bottle clean 轴 std 同量级、NN 域差 2.75×（≈1mm 噪声级）；721 压缩 4–18×/66 离群点；
  bowl 压缩 4–16×/离群点 42–316 每帧/NN 域差 5.7–33×（对同物体非正式合成池）。
- **结论**：real-domain 失败分两个 regime——clean bottle 近 in-distribution 仍翻转（朝向裕度问题）；
  721/bowl 严重 OOD 致坍缩（分布问题）。分布差异只能直接解释后者。

## 2026-09-10 — Phase 3 / P3.1-E：输入敏感性诊断（几何通路驱动；外观假设否定）

- 新增 `scripts/p3_1_e_input_sensitivity.py` + `docs/P3_1_E_INPUT_SENSITIVITY.md`。
- 四条件（full/rgb_mean/xyz_zero/rgb_shuffle）× 10 真实帧 × 2 物体 + 10 合成对照，frozen checkpoint 零改动。
- **结论**：~176.5° 偏置与逐点 RGB 无关（均值/打乱均不改变），纯几何输入（rgb_mean，非坍缩）即触发
  173.4°；合成对照确认 real 触发（合成 full 仅 3.2°）。外观线索反转假设否定；RGB 侧 DR 对该失败无效。
- xyz_zero 条件两域坍缩，数值不具解释力（如实记录）。

## 2026-09-10 — Phase 3 / P3.1-D：Canonical Frame Convention Audit（Case B：frame 同一）

- 新增 `scripts/p3_1_d_canonical_frame_audit.py` + `docs/P3_1_D_CANONICAL_FRAME_AUDIT.md`。
- 审计结论：渲染器（手写 ASCII 解析）与评测（Open3D）读取同一 PLY 文件且输出逐位一致；
  训练标签（coords）与 BOP model frame 的 Kabsch 变换 = 恒等（rot ≤0.096°，|t| ≤0.26mm，scale≈1，det=+1）；
  施加 P3.1-C 旋转使 label→BOP 距离膨胀 10.7×/15.5×。**Case A（frame mismatch）排除，Case B 成立。**
- 176.5° 现象的定位由此收窄：非数据/约定 bug，而是 CoordNet 在真实输入分布上的 frame 歧义选择。

## 2026-09-10 — Phase 3 / P3.1-C：固定旋转诊断（Gate 3 失败完全归因）

- 新增 `scripts/p3_1_c_posthoc_rotation.py`：与 Gate 3 逐位同构的管线 + 单一预注册修正
  （canonical Y 轴 −176.5°，来源 P3.1-B）；baseline 读已有 JSON 不重跑。
- **结果：0/10 → 10/10**（bottle ADD 0.73–1.75mm rot 0.9–2.4°；bowl ADD-S 1.35–1.51mm）。
  Gate 3 失败被完全解释：唯一致命缺陷 = 固定 canonical frame 偏移；逐点坍缩/尺度污染对 pose 无害
  （Procrustes 旋转对均匀尺度不变 + ICP 清理）。Gate 3 NO-GO 维持（诊断性质）。
- 一并入库前任 Agent 遗留的 P3.1-B 未提交文件（`scripts/p3_1_b_canonical_analysis.py` +
  `docs/P3_1_B_CANONICAL_FAILURE_ANALYSIS.md`）；修正 MODULE_MAP 中对不存在子命令的错误记载。

## 2026-09-08 — Phase 3 / P3.0-S：Closeout（feasibility spike 封存）

- **P3.0-S 最终结论**：Gate 1 PASS + Gate 2 PASS + Gate 3 NO-GO = sim-to-real 迁移在当前配置下不可行。
- **Coordinate / Transform Audit**（`scripts/_audit_coordinate_transform.py`）：
  合成数据内部一致性 PASS；闭环测试 PASS（4.05° / 4.1mm / 97.2% inliers）；
  坐标变换链方向正确，排除 pipeline 实现错误。
- **Root cause 修正**：撤回此前 "canonical-frame ambiguity / L2 loss 对 global rotation invariant" 的
  确定性表述（该表述技术上不成立）。修正后的 root cause：
  "The primary observed failure is poor real-data generalization of the learned canonical correspondence;
  the specific source of the sim-to-real gap is not fully isolated."
- **EXP-008 更新**：failure layer analysis 重写，保留审计轨迹（初始错误分析 → 用户质疑 → audit → 修正）；
  GO/WEAK/NO-GO 阈值（3/5, 2/5）明确标注为提案，未经用户冻结。
- Bowl 训练产物（`data_synth/bowl/`, `outputs/p3_0/bowl_train/`）保持非正式记录，不纳入正式实验序列。
- 不修改任何实验代码、不重训、不调参、不重新执行 Gate 3。

## 2026-09-08 — Phase 3 / P3.0-S：Gate 3 前置整理（实验定义入仓 + 文档修正）

- 新增 `configs/p3_0_gate3.yaml`：Gate 3 真实 YCB-V smoke test 完整定义
  （测试帧/pipeline/correspondence quality metrics/GO·WEAK·NO-GO 判定标准）。
- EXPERIMENT_LOG 新增 EXP-008（Gate 3 定义冻结）+ bowl 非正式训练产物记录。
- `run_p3_0.py`：修正模块 docstring 中网络结构描述（"6-64-128-256-3" →
  "local 6→64→128, global max-pool → 128→128, head 256→128→3"，256 是拼接维度非隐藏层宽）；
  清理未使用的 Gate 3 预添加导入（cv2/glob/csv/YcbvBopDataset 等 11 项）；
  docstring 补充 train 子命令。
- MODULE_MAP.md：测试数 47 → 52（补列 learn/render_templates/geo_init 分项）；
  新增 p3_0_gate3.yaml 条目；run_p3_0.py 描述更新为完整子命令列表。
- requirements.txt：补充 torch 2.13.0+cpu 注释（Phase 3 可选，lazy-import）。
- pyproject.toml：新增 `[learning]` optional dependency（torch>=2.12）。

## 2026-08-30 — Phase 3 / P3.0-S：最小学习对应 spike（Gate 1 PASS；首跑 VOID）

- 新增 `src/r3p/learn/`（umeyama+RANSAC、CoordNet ~59k 参数、合成数据生成）与 `run_p3_0` 入口
  （gen/sanity/gate1）；新增 torch 2.13.0+cpu 依赖（已批准）。
- **数据 bug 与修复**：`synth_data.py` 曾将 xyz 误存模型系点（与标签同数组）→ 第一次 Gate 1
  判定 **VOID**（训练目标不可学，全部数字作废）。修复为相机系 xyz + 每样本完整性断言
  + `sanity` 子命令（250 样本三项检查全部 ~0.01–0.04mm）。
- 修正后 **Gate 1 PASS**：train ADD 4.8mm（≤5）、对齐残差 2.7mm（≤3）、loss 比 0.081（≤0.2）。
- 新增 5 项测试（umeyama 恢复/RANSAC 外点/网络形状与规模/过拟合烟雾/归一化往返）；52/52 全绿。
- **Gate 2 PASS**（50 未见合成姿态）：val ADD 5.82mm ≤10、对齐残差 3.17mm ≤5、val/train 比 1.21 ≤3——泛化成立，非记忆。

## 2026-08-30 — Phase 2 / P2.4：Classical baseline 工程收尾 —— **Phase 2 Complete**

- 全量工程验证：obj5 scene 50 全 75 帧 + obj13 scene 53 全 75 帧（参数与 P2.3-S 完全冻结一致）。
  bottle solver 75/75、pose 70/75（93.3%，成功帧 ADD median 1.3mm / max 2.0mm）；bowl solver 59/75、
  pose 58/75（77.3%，成功帧 ADD-S median 2.67mm / max 3.2mm）；零崩溃/零 NaN/runtime_error。
- **工程发现与修复：运行间非确定性**——Open3D voxel_down_sample 输出顺序不保证 + ICP/法线估计
  多线程 FP 归约顺序抖动，近对称刀刃帧逐位翻转（实测 bowl solver 7–9/10 波动）。修复：点云字典序
  规范化 + OMP 单线程（OMP_NUM_THREADS=1），两次运行逐位一致（回归测试固化）；~2× 耗时（决策 D9）。
- 推理接口固化：`geo_init.estimate_pose`（Phase 3 学习方法按同签名替换）。
- 失败模式与 P2.3-S 一致且系统化：bottle 5 帧 roll 歧义（ADD≈62mm / fitness≈0.95 同签名）、
  bowl 16 帧重遮挡段 no-converge（im 479–687 聚集）+ 1 帧选择失败（fitness 0.58 / ADD-S 36.6mm）。
- **Phase 2 Classical Baseline Complete**（oracle mask 受控条件）；PROJECT_SPEC 基线表已填入；
  决策 D8/D9 记录于 PROJECT_CONTEXT；EXP-006。

## 2026-08-30 — Phase 2 / P2.3-S：几何路线（route A）—— GO

- 新增 `src/r3p/pose/geo_init.py`：oracle mask→物体点云→PCA→24 proper-rotation 假设→
  质心对齐→point-to-plane ICP（scene→model 方向，3cm→1cm→3mm）；推理路径零 GT pose，
  假设选择仅用 fitness；新增 `run_p2_3.py` + `configs/p2_3.yaml`（两物体、两阶段评估、
  失败 taxonomy、GT-best 仅诊断、四重 overlay）。
- **结果（EXP-005，GO）**：bottle solver 10/10、pose 9/10（ADD 0.7–2.0mm）；bowl solver 8/10、
  pose 8/10（ADD-S 2.4–3.2mm）。失败 3 帧全部归因：1×近圆柱 roll 歧义（fitness 0.97 但 ADD 62mm）、
  2×重遮挡（fitness 0.13）。PCA init 偏差 33–181mm 由 ICP 收敛至 1–3mm——两阶段分工被干净证明。
- Phase 2 baseline 候选产生：PCA/OBB init（A）与 PCA/OBB+ICP（B，主）。
- 新增合成回归测试 4 项（24 假设正交性/合成恢复/ICP 改善量/点云过滤防零样本）；全套 46/46。

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
