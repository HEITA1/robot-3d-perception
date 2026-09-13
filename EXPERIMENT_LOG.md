# EXPERIMENT_LOG

> 记录规范：每个实验一条记录，必须包含 Question / Hypothesis / Setup / Result / Analysis / Decision。
> 原始数据（metrics.json、日志、可视化）存放在 `outputs/<exp_name>/<timestamp>/`，本文件记录要点与结论。

---

## Experiment Index（canonical IDs & cross-references）

**编号规则**：EXP 编号授予"在冻结协议下产出新数值结果"的实验；只读审计/对既有产物的分析
以 `docs/` 报告形式归档（有独立文档，无 EXP 编号）。历史编号保留不重排；顺序异常处已加注。

| ID | 名称 | 状态/位置 |
| --- | --- | --- |
| EXP-000 | Phase 0 smoke | 本文件 |
| EXP-001 | Phase 1 数据接口验证 | 本文件 |
| EXP-002 | P2.0 SIFT+PnP spike | 本文件 |
| EXP-003 | P2.1 渲染模板库 | 本文件 |
| EXP-004 | P2.2 参考库 3→75 | 本文件 |
| EXP-005 | P2.3-S 几何路线 GO | 本文件 |
| EXP-006 | P2.4 工程验证（Phase 2 Complete） | 本文件（文件内位于 EXP-007 之后——插入顺序所致，内容完整） |
| EXP-007 | P3.0-S Gate 1（首跑 VOID → 修正后 PASS） | 本文件 |
| EXP-008 | P3.0-S Gate 3 NO-GO + 审计 | 本文件 |
| **EXP-009**（追溯编号） | **P3.1-C** post-hoc 旋转诊断（0/10→10/10） | 本节尾注 + `outputs/p3_1_c_posthoc_rotation/` + `scripts/p3_1_c_posthoc_rotation.py` |
| EXP-010 | P3.1-E 输入敏感性（几何通路归因） | 本文件 |
| EXP-011 | P3.1-F 几何分布审计（两 regime） | 本文件 |
| EXP-012 | P3.1-G depth noise sanity（1mm 不支持，训练前停止） | 本文件 |
| EXP-013 | FoundationPose feasibility（obj5×5 帧） | **已注册，runtime 待 3090**；目录别名 `fp_exp004_feasibility`（Phase 4 命名惯例，见 `configs/fp_exp013.yaml`） |
| EXP-014 | W2-3 跨物体统一 baseline（7 物体集，5 新物体 ×10 帧） | 本文件 + `outputs/w2_3/`；registry `configs/evaluation_objects.yaml` |

**编号说明**：`docs/PHASE4_PREFLIGHT.md` §7 曾把 "EXP-014" **预留**给未执行的 FoundationPose
扩帧提案（仅设计、从未注册/运行）；按编号规则（授予实际产出数值结果的实验），EXP-014 归属
W2-3 跨物体统一 baseline。该 FP 提案若将来执行，将顺延使用下一个可用编号。

**无 EXP 编号的诊断文档**（只读审计/分析既有产物，按上述规则不编号）：
P3.1-A → `docs/P3_1_A_ROBUST_NORMALIZATION.md`（单变量消融，Outcome D）；
P3.1-B → `docs/P3_1_B_CANONICAL_FAILURE_ANALYSIS.md`（预测误差分层分解，~176.5° 发现）；
P3.1-D → `docs/P3_1_D_CANONICAL_FRAME_AUDIT.md`（frame 同一性审计，Case B）。
Gate 3 逐层定位 → `docs/P3_0_GATE3_DEBUG.md`（D1–D6）。

---

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
- **Result**（run: `outputs/smoke/20260830-114734/`，exit code 0，validation PASS）：
  - GT 自评估：ADD = ADD-S = trans = 0.0，rot = 0.0°（全部精确为零）✔
  - rot_only（0/2/5/10/20°）：ADD = 0 / 16.7 / 41.8 / 83.5 / 166.4 mm，单调 ✔；
    旋转误差精确等于扰动角（最大偏差 < 1e-12°）✔
  - trans_only（0/5/10/20/40 mm）：ADD == trans == 扰动量（精确）✔，rot ≡ 0 ✔；
    ADD-S ≈ trans 的 0.5–0.6 倍（最近邻匹配软化了平移误差，符合预期）
  - combined：ADD = 0 / 21.3 / 50.7 / 101.1 / 199.9 mm，单调 ✔
  - 可视化 `pose_report.png`：深度图物体居中 ~0.8 m；点云透视正确；GT vs 扰动位姿偏移清晰
  - pytest：28/28 通过（se3/metrics/camera/synthetic/config）
- **Analysis**：
  - 骨架五环节（config → 合成数据 → 几何 → 评测 → 可视化/日志）行为全部符合解析预期，
    metrics 的解析特例（纯平移 ADD=|Δt|、纯旋转 rot_err=θ）被精确复现，说明指标实现无误。
  - rot_only 下 trans 误差非零：扰动按相机系左乘 ΔT 定义，ΔR 会带动原平移（t_est = ΔR·t_gt），
    这是定义使然而非 bug；Phase 5 鲁棒性实验沿用此定义并写入协议。
  - 过程中发现并修复 box 采样器总表面积公式错误（2·Σ → 8·Σ），修复前 n_model_points 实际产出
    4 倍点数（8022 vs 2000），导致 ADD-S 的 O(N²) 距离矩阵无谓膨胀 ~500 MB；修复后 2018 点、
    单次运行 ~1 s。
- **Decision**：
  1. Phase 0 Exit Criteria 满足：统一入口一条命令端到端出结果（metrics.json + log + PNG）。
  2. 评测协议基线确定：相机系位姿、单位米、扰动为相机系左乘；阈值协议留待 Phase 2 对齐
     DenseFusion/BOP 时冻结。
  3. Phase 1 可以开始（数据下载清单需先行报批）。

---

## EXP-001 — Phase 1 真实数据接口验证（YCB-V BOP → r3p）

- **日期**：2026-08-30
- **Phase**：1
- **Question**：真实 YCB-V 数据经 `YcbvBopDataset` 接口后，几何、单位与标注语义是否与 BOP 官方定义完全一致（无单位混用、无坐标约定错误）？
- **Hypothesis**：
  1. 深度 → 点云 → 重投影往返误差 ≈ 0（真实深度图含传感器噪声与空洞，不影响往返一致性）；
  2. GT 位姿 + 模型点投影能解释 `mask_visib`（可见区域 recall > 0.9）；
  3. 接口边界处深度/平移/模型点全部为米：以物理合理性区间 + 官方 diameter 交叉验证捕获任何 mm/m 混用。
- **Setup**：
  - 接口：`YcbvBopDataset(data_root="data/ycbv", obj_ids=(5, 13))`，单位转换集中在接口边界
    （depth: raw × depth_scale × 1e-3；cam_t_m2c × 1e-3；模型 ply 毫米 → 米）；
  - 测试 7 项（`tests/test_ycbv_bop.py`）：往返（6 帧抽样）、单位（10 帧 + 两物体直径交叉验证）、
    GT 投影 vs mask_visib（6 实例，膨胀 5×5 后 recall > 0.9）、obj 映射（21 物体名解析）、
    索引非空显式断言（150+150 帧）、单实例假设扫描（全子集）、观测契约（形状/键/visib_fract）；
  - demo：`run_ycbv_demo`（scene 50/im 620 mustard_bottle；scene 53/im 33 bowl）。
- **Result**：
  - pytest **35/35 通过**（28 合成 + 7 真实数据）；
  - 往返：像素误差 < 1e-6（断言阈值），深度误差 < 1e-9 m；
  - GT 投影 vs mask_visib：6/6 实例 recall > 0.9；模型点 100% 在帧内；
  - 单位：深度 1%–99% 分位在 [0.2, 3.0] m；平移范数同区间；模型点最大点对距离与官方 diameter
    精确吻合（obj5: 0.1965 m，obj13: 0.1619 m）；
  - demo 两帧 GT 模型点与 RGB 实物像素级贴合（人工确认）。
- **Analysis**：
  - 接口无单位混用、无约定错误；真实深度图空洞/噪声不影响往返一致性（往返只依赖投影模型）。
  - **语义发现**：models_info.json 的 `diameter` = 模型顶点间最大两两距离（非包围盒最长边）。
    Phase 2 的 ADD-0.1d 阈值必须按此语义使用（初版单测曾误用 bbox 长边而被测试当场抓住）。
  - 目标物体在整个 test_bop19 子集中无单帧多实例 → dict 接口安全（测试固化为回归防线）。
- **Decision**：
  1. **Phase 1 Exit Criteria 满足**：RGB-D → 点云 → 坐标变换 → 可视化全链路在真实数据上验证通过。
  2. 评测协议备忘：ADD(-S) 阈值用 models_info diameter（最大点对距离）；模型点默认用 models/ 顶点
    （确定性），Phase 2 冻结协议时复核是否改用表面均匀采样。
  3. 可进入 Phase 2（PnP/ICP），等待指令。

---

## EXP-002 — P2.0 Feasibility Spike：SIFT + PnP-RANSAC（方案 A）

- **日期**：2026-08-30
- **Phase**：2（P2.0）
- **Question**：方案 A（深度提升参考帧模板）下，SIFT 能否建立稳定的 2D-3D 对应支撑 PnP-RANSAC？10 个固定帧的成功率如何？
- **Hypothesis**：若参考库覆盖目标表观，ratio test 后应有大量匹配落在目标 mask 内（≥15），PnP inlier 重投影残差 < 3 px，部分帧 ADD < 0.1d。
- **Setup**：
  - 参考：scene 52 visib_fract top-3（im 561/516/575），SIFT@mask 内深度提升 → **645 descriptors**
  - 评测：scene 50 等间隔 10 帧（im 620…1874）；场景不相交，无泄漏
  - PnP：solvePnPRansac（EPnP，3px，10k iter，conf 0.99，min_inliers 6，cv2 种子 0）+ 全内点精化
  - pose success：ADD < 0.1d = 19.65 mm（diameter=最大点对距离语义）
  - 入口：`python -m r3p.experiments.run_p2_0 --config configs/p2_0.yaml`（run: `outputs/p2_0/20260830-142053`）
- **Result（主实验：跨场景）**：**0/10 solver 成功**。每帧 query kp ~2200–2360，ratio 后 good 28–78，但**落在 bottle mask 内仅 0–6 个** → PnP 无可用对应。validation PASS（管线端到端正确、无崩溃）。
- **Failure → Diagnosis**（按链条记录）：
  1. **Failure**：0/10，in-mask 匹配趋零。
  2. **诊断 1（可视化）**：drawMatches 显示参考帧 bottle 为**躺放、露出侧面标签**，评测帧为**立姿正面**——视点/姿态大幅差异；匹配集中在瓶盖/瓶颈等近视点不变区域。
  3. **诊断 2（提升自检）**：库内 3D 点经参考帧 GT 投影回自身关键点，误差 **0.000 px** → 深度提升与 convention 无 bug。
  4. **诊断 3（同场景对照，`scripts/p2_0_intra_scene_control.py`）**：参考库改由 scene 50 自身 3 帧（visib top-3，**显式排除 10 个评测帧**，run: `outputs/p2_0_control`）→ **8/10 solver、8/10 pose success**，ADD **1.1–16.6 mm**（多数 1–3 mm，纯 PnP 无 ICP），残差 0.6–1.3 px；失败 2 帧（im 620/653）in-mask 仅 4–6。
- **Attribution**：主实验失败**不是软件 bug**（诊断 2、3 排除），而是真实的算法发现：**3 帧参考库视点覆盖不足，SIFT 跨大幅视点/姿态变化无法建立对应**（SIFT 视点不变性有限，符合预期理论边界）。
- **Fix**：无软件缺陷需修。算法层面的修复路径（P2.1 提案，待批准）：方案 B（CPU RaycastingScene 渲染多视角模板库，覆盖视点空间）。
- **Conclusion**（区分三层）：
  - **软件正确性**：✅ 通过——合成零噪声回归精确恢复（<1e-6）、提升自检 0px、对照实验 8/10 且残差亚像素。
  - **算法成功**：方案 A 跨场景 **0/10（不足）**；同场景 **8/10**（PnP 单独即达 mm 级，说明"深度提升 3D 点 + SIFT 匹配 + PnP"路线本身精度潜力很好）。
  - **研究结论**：SIFT+PnP 的可行性边界 = **参考库的视点覆盖**，而非特征/求解器本身。该结论直接约束 P2.1 设计。
- **过程软件修复记录**（不影响结论）：knnMatch 解包错误、RANSAC 后补全内点精化、drawMatches 参数序与 trainIdx 重映射、RGB/BGR 写图修正。
- **Decision**：P2.0 Exit Criteria 满足。**P2.1 需要你批准方案 B 升级**（跨场景评测要求视点覆盖的模板库；同场景对照不构成合格 baseline——参考与评测同分布，会高估性能）。

---

## EXP-003 — P2.1：多视角渲染模板库（方案 B）

- **日期**：2026-08-30
- **Phase**：2（P2.1）
- **Question**：增加 reference viewpoint coverage（16 视角渲染模板库）后，P2.0 暴露的跨场景视点覆盖问题是否得到改善？
- **Hypothesis**：视点覆盖补齐后，in-mask 匹配显著增加，solver success > 0。
- **Setup**（除参考库来源外与 P2.0 严格一致：同 obj5、同 10 评测帧、同 SIFT/ratio/PnP 参数、同 ADD<0.1d）：
  - **纹理核实**：BOP PLY 原生自带 `texture_u/v` 属性 + `TextureFile obj_000005.png`（4096²），Open3D 标准读取器不暴露 → 直接解析 ASCII PLY（模型自身数据，无新依赖、无纹理重建）
  - 渲染：Open3D `RaycastingScene` CPU 光线投射（无 GPU/OpenGL），Fibonacci 确定性 16 视角，radius 0.9 m，K 与数据集一致
  - 材质两版：①平铺纹理 ②Lambert 头灯明暗（约束 1 预批的"简单可视化材质"）
  - 库规模：595 descriptors / 16 视角（每视角 25–157 kp）
  - 入口：`python -m r3p.experiments.run_p2_1 --config configs/p2_1.yaml`（runs: `outputs/p2_1/20260830-144219`、`-144843`）
- **Result**：
  | 材质 | solver success | pose success | good 匹配 | in-mask 匹配 |
  | --- | ---: | ---: | ---: | ---: |
  | 平铺纹理 | **0/10** | 0/10 | 23–46 | 0–5 |
  | Lambert 明暗 | **0/10** | 0/10 | 29–70 | 0–8 |
- **Diagnosis**：
  1. 模板自一致性 3.13e-13 px（渲染 3D/相机位姿/pixel 完全自洽）→ 非 geometry bug；
  2. 渲染↔渲染：view0 自匹配 59 good、相邻视角 27 good → 模板库内部可匹配；
  3. **渲染→照片**（frame 1044，P2.0 对照中最易帧）：good=28 / **in-mask=2**，而真实参考同帧 94/52 →
     **render→real 域差主导**：光照复杂性、镜面高光、传感器噪声、色彩响应——平铺与 Lambert 均无法弥合。
- **Conclusion**（三层）：
  - 软件正确性：✅（42/42 测试；模板重投影 3e-13 px；z-depth 语义修正）
  - 算法结果：**视点覆盖单独不解决问题**——P2.1 = 0/10（两版材质）；域差是比视点覆盖更强的瓶颈
  - 研究结论：SIFT 描述子在 render→real 域间本质上脆弱；用简单材质渲染模板**不是**可行的跨场景参考来源
- **Decision**：按约束"需改变模板生成策略时先汇报"——**停止，P2.1 后续路线待批准**（见 Milestone Report 选项）。已知最有希望的廉价选项：**真实参考库扩充**（scene 52 全部 75 帧 ≈ 15k descriptors，跨场景零帧重叠、零新依赖、与 P2.0/P2.1 完全可比）；架构级备选：深度/几何初值路线（需批准）。
- **过程软件修复**：z-depth vs 光线距离语义、下标赋值 RHS 先求值导致 walrus 未绑定、材质法线插值。

---

## EXP-004 — P2.2：真实参考库扩充（scene 52 全 75 帧，唯一变量 3→75）

- **日期**：2026-08-30
- **Phase**：2（P2.2）
- **Question**：把 P2.0 的真实参考库从 scene 52 的 3 帧扩到全部 75 帧，能否解决 scene 50 跨场景评测的 SIFT 2D-3D 对应不足？
- **Hypothesis**：视点/表观覆盖扩大 20 倍后，in-mask 匹配显著增加，solver success > 0。
- **Setup**：**唯一变量 = reference.n_frames: 3 → 75**（`configs/p2_2.yaml`，其余全部冻结：
  同 SIFT/ratio=0.75/同 PnP 参数与精化/同 10 评测帧/同 ADD<0.1d）。复用 `run_p2_0` 入口
  （run: `outputs/p2_2/`），新增只读验证（不影响结果）：
  - **A. Reference self-consistency**：12,670 个库点全量做 `model 3D → GT → project → 原关键点`，
    **max 8.94e-04 px / mean 6.38e-05 px**（≈0，float 精度级），anti-zero guard 生效（75 帧/12670 点）
  - **B. Library statistics**：75 帧、**12,670 descriptors**（P2.0 的 19.6 倍）、
    每帧 min/median/max = 84/192/252、**重复 descriptors = 0**（无去重逻辑，如实报告）
  - **C. 10 帧全记录**：见 `outputs/p2_2/*/per_frame.csv`（无一帧省略）
- **Result**：
  | 指标 | P2.0（3 帧，645 desc） | P2.2（75 帧，12,670 desc） |
  | --- | --- | --- |
  | good 匹配 min/med/max | 28 / 43 / 78 | **7 / 13 / 19（下降）** |
  | in-mask 匹配 min/med/max | 0 / 2 / 6 | 0 / 1 / 2 |
  | solver success | 0/10 | **0/10** |
  | pose success (ADD<0.1d) | 0/10 | 0/10 |
  | ADD / ADD-S mean·median | n/a（无成功帧） | n/a（无成功帧） |
- **Diagnosis**：
  1. **表观状态证据（`outputs/p2_2/aspect_grid.png`）**：scene 52 全程（采样 im 1/116/520/593/886 + P2.0 的 516/561/575）
     中 bottle 均为**背面朝上（蓝色标签侧）躺放**；scene 50 评测帧为**正面（红色 French's 标签）立姿**——
     **两场景可见表面几乎不相交**。75 帧里不存在查询帧所需的外观状态。
  2. **ratio test 压制效应**：库扩大 19.6 倍后 good 反而下降（中位 43→13）——同物体 75 视角的自相似描述子
     使第二近邻不再"足够远"，Lowe ratio 通过率下降（SIFT ratio test 的已知机制）。
- **Conclusion**（按结果解释纪律）：
  - **如实报告：扩大真实视点覆盖仍不足以解决问题（0/10）。** 且本数据对上的更尖锐结论是：
    瓶颈不是覆盖**密度**，而是参考场景中**根本不存在**查询所需外观（可见表面不相交）。
  - 参考库依赖是 SIFT+PnP 路线的本质约束：真实参考库只有包含查询外观时才可能工作
    （intra-scene 对照 8/10、ADD 1–3mm 证明了上限）。
  - 至此三个变体（3 帧真实 / 75 帧真实 / 16 视角渲染±明暗）全部失败，
    SIFT+PnP 跨场景路线在 YCB-V scene50↔52 上判定为不可行（有完整归因链）。
- **Decision**：按指令停止，不进入 ICP 或其他方案。SIFT 跨场景结论已闭环；
  后续 P2.3+ 的路线选择（同场景参考定义 baseline + 局限声明 / 深度几何初值 / 进入 ICP 等）
  等待批准，本实验不做任何延伸。

---

## EXP-005 — P2.3-S：几何路线（mask → PCA/OBB 24 假设 → point-to-plane ICP）✅ GO

- **日期**：2026-08-30
- **Phase**：2（P2.3-S）
- **Question**：已知物体类别、拥有 RGB-D + oracle mask、**无 GT pose** 的条件下，纯几何方法能否从未知初始姿态恢复 YCB-V 物体 6D pose？
- **Hypothesis**：几何信号绕开外观重叠与域差（EXP-002/003/004 的三条失败原因全部不适用）；多假设 + ICP 达到 GO 判据（bottle ADD<0.1d ≥5/10，bowl ADD-S<0.1d ≥5/10）。
- **Setup**（参数跑前冻结于 `configs/p2_3.yaml`，未因结果调整）：
  - 推理链：oracle mask（受控条件，显式标注）→ 物体点云（5mm voxel）→ PCA → **24 个 proper rotation 假设**（6 置换 × 4 符号，det=+1）→ 质心平移对齐 → 逐假设 point-to-plane ICP（scene→model 方向，3cm→1cm→3mm，每级 ≤60 iter）→ **仅以 fitness 选择**（并列取低 RMSE）
  - GT 仅用于评测与事后诊断 `gt_best_hypothesis`（不进推理）；两阶段（PCA init / ICP）分别评测
  - 数据：obj5 scene 50 固定 10 帧 + obj13 scene 53 固定 10 帧；入口 `run_p2_3`（run: `outputs/p2_3/20260830-155355`）
- **Result**：
  | 物体 | solver success | pose success | 主指标 | PCA init（被选假设） | ICP 结果 |
  | --- | ---: | ---: | --- | --- | --- |
  | obj5 mustard_bottle | **10/10**（fitness 0.88–0.97，RMSE 1.4–1.6mm） | **9/10**（ADD<0.1d） | ADD **0.7–2.0mm**（9 帧） | ADD 32.9–131.8mm | ADD 0.7–2.0mm |
  | obj13 bowl | **8/10** | **8/10**（ADD-S<0.1d） | ADD-S **2.4–3.2mm** | init 77–181mm | ADD-S 2.4–3.2mm |
  - **failure taxonomy**：bottle：9 success + 1 `adds_ok_add_fail`（im 1718，ADD 62mm / ADD-S 2.7mm / fitness **0.97**——几何收敛到错误 roll 的近圆柱歧义）；bowl：8 success + 2 `icp_no_converge`（im 533/551，fitness 0.13–0.14，碗被罐头重遮挡、可见表面不足；GT-best 诊断亦仅 27.9–28.2mm → 深度/覆盖极限而非选择失败）
  - **fitness 选择 vs GT-best**：20 帧中被 fitness 选中且非 GT-best 的帧里，除 bottle 1718 外全部落在对称等价位形（ bowl）或同等精度（bottle 1113：hyp17 vs hyp15 均 0.7mm）→ **fitness 选择仅 1 帧真实失误**
- **Analysis**：
  1. **两阶段分工清晰**：PCA init 普遍偏离 33–181mm（单视角半壳 PCA 的必然粗糙度），但 24 假设几乎总有一个落在正确朝向盆地内，ICP 一律收敛到 ~1–3mm——"粗初始化失败"与"精化失败"被干净地区分开：粗初始化靠假设集兜底，精化失败仅 2 帧且归因遮挡。
  2. **问题 D 的量化答案**：bowl 的 ADD（均值 96.8mm）与 ADD-S（均值 2.65mm）巨大分裂正是旋转对称性的正确表现——算法没有失败，是 ADD 对对称物体不可判别。
  3. **fitness≠pose 的实例**（1718）：fitness 0.97 + RMSE 1.5mm 但 ADD 62mm——"几何配准收敛，但收敛到错误 roll"，正是预判的高价值失败模式；也标出了未来改进点（roll 歧义的消解），但本轮不改。
  4. 与 SIFT 路线对照：同一批 scene 50 评测帧上，SIFT 全变体 0/10，几何路线 9/10 + 8/10——失败原因（外观）被换信号彻底绕开。
- **Conclusion**：
  - **GO 判据达成**（9/10 ≥ 5，8/10 ≥ 5）。纯几何 classical 方法在 oracle mask + 无 GT pose 条件下**成立**。
  - Phase 2 baseline 候选正式产生：Baseline-A = PCA/OBB init（粗糙），**Baseline-B = PCA/OBB + ICP（主 baseline）**；后续学习方法的对照组即此。
  - 已知局限（诚实声明）：oracle mask；roll 歧义影响非对称指标（bottle 1/10）；重遮挡下失败（bowl 2/10）；单帧未批处理。
- **Decision**：P2.3-S 完成。规模放大（全场景/全帧）、遮挡失败改进、与 Phase 3 的衔接——等待批准，本轮不延伸。

---

## EXP-007 — P3.0-S Gate 1（第一次结果 VOID；修正后 PASS）

- **日期**：2026-08-30
- **Phase**：3（P3.0-S）

### 第一次 Gate 1：**INVALID / VOID — caused by confirmed synthetic-data coordinate-frame bug**

- 数据生成实现错误：`synth_data.py` 将 `xyz` 字段误存为**模型系**点（与 canonical 标签同源），
  正确值应为**相机系**（`xyz = T_cam_model @ points_model`）。
- 证据：npz 中 `xyz` 与 `coords` 最大差 3.0e-05（同一数组）；`T @ coords` 与存档 `xyz` 相差 0.87m
  （= 相机距离量级）；`ADD(GT pose, GT labels) = 624.9mm`（应 ~0）。
- 因此训练目标为逐点不可学的伪任务，下列数字**全部作废、不得引用**：
  train ADD 86mm / 0/200 达标 / aligned residual 10.9mm / 损失平台 90mm /
  “roll 歧义签名”假设 / “欠拟合”判断。诊断时另一 ADD-S 代理脚本亦有误，已弃用。

### 修正后 Gate 1（数据 sanity PASS 后，同冻结配置、同种子重跑）：**PASS**

- **Data sanity（250/250 样本）**：frame consistency max 3.5e-05 m；ADD(GT pose, GT labels)
  mean 0.012 / max 0.015 mm；Umeyama(GT correspondence) max 0.037 mm —— 全部为 float16 舍入级。
- 三项冻结判据：
  1. train per-point ADD mean = **4.824 mm ≤ 5mm** ✅（max 8.6mm）
  2. Umeyama 对齐残差 mean = **2.749 mm ≤ 3mm** ✅（max 4.8mm）
  3. final/initial loss = **0.0809 ≤ 0.2** ✅（57.9mm → 4.7mm）
- 训练：CoordNet 58,563 参数，CPU 213s。产物：`outputs/p3_0/gate1/`。
- 含义：最小学习模型**能够在合成数据上学会 canonical correspondence**（Gate 1 回答"能不能学"= 能）。
  sim-to-real（Gate 3）是下一个、也是真正的不确定性问题。

### Gate 2 — Synthetic Validation（50 未见姿态，同一 checkpoint，零重训）：**PASS**

- 验证集 sanity：50/50 样本 frame/ADD/Umeyama 检查全部 float16 舍入级 ✅
- **三项冻结判据全部通过**：
  1. val ADD mean = **5.824 mm ≤ 10mm** ✅（min 3.09 / median 5.47 / p90 7.07 / max 20.51）
  2. val Umeyama 对齐残差 mean = **3.167 mm ≤ 5mm** ✅（median 2.75 / p90 4.50 / max 7.08）
  3. val/train ratio = **1.207 ≤ 3** ✅（train ADD 4.824 / aligned 2.749 —— 与 Gate 1 完全复现）
- 姿态相关性：按视点仰角分桶（<45°/45–90°/90–135°/≥135°）均值 5.6–6.7mm，
  **无强姿态相关失败**；最差帧（val_0042，20.5mm）出现在近轴视角（elev 83°，沿轴向观察几何辨识度最低），符合几何直觉。
- 判读：val/train 差距 1.21 倍属健康泛化间隙——**模型学到的是 canonical correspondence，不是对 200 样本的记忆**。
- 产物：`outputs/p3_0/gate2/gate2_metrics.json`。下一步 Gate 3（真实 YCB-V smoke，10 帧）等待批准。
- 工程记录：`run_p3_0` 新增强制 `sanity` 子命令（训练前必过）；渲染标签管线经此 Gate 后确认健康。
---

## EXP-006 — P2.4：Classical baseline 工程验证（75+75 帧全量）—— **Phase 2 Complete**

- **日期**：2026-08-30
- **Phase**：2（P2.4，工程收尾）
- **Question**：P2.3-S 的成功是否偶然？几何 Classical pipeline 能否作为后续系统的稳定 baseline？
- **Setup**：参数与 P2.3-S **完全冻结一致**（24 假设 / ICP 3cm→1cm→3mm / fitness 选择 / 同 metrics / 同成功判据），唯一变化 = 帧数 10 → **75+75 全量**（obj5 scene 50、obj13 scene 53 全部含目标帧）。oracle mask（受控条件）；推理零 GT pose。
- **Result**：
  | 物体 | solver | pose success | 成功帧主指标 | 失败分布 |
  | --- | ---: | ---: | --- | --- |
  | obj5 bottle | **75/75 (100%)** | **70/75 (93.3%)** | ADD median **1.30mm** / p90 1.74 / max 2.01 | roll 歧义 ×5 |
  | obj13 bowl | **59/75 (78.7%)** | **58/75 (77.3%)** | ADD-S median **2.67mm** / p90 2.83 / max 3.19 | no-converge ×16 + 选择失败 ×1 |
  - 稳定性：150 帧零崩溃、零 NaN、零 insufficient_observation、零 runtime_error；单帧推理 0.8s（bottle）/ 3.1s（bowl），总 wall ~6.6 min（CPU）。
- **工程发现与修复（本轮最有价值的产出）**：
  1. **运行间非确定性**：初版 20 帧回归发现 bowl solver 8→7 翻转；逐帧 diff 定位到全管线第 3 位小数级抖动。
     两个来源：Open3D `voxel_down_sample` 输出顺序不保证 + ICP/法线估计的**多线程 FP 归约顺序**。
     修复：点云字典序规范化 + `OMP_NUM_THREADS=1`（~2× 耗时）。验证：单线程下两次运行**逐位一致**（回归测试固化）。
     影响：多线程下 bowl solver 在 7–9/10 间波动；单线程 canonical = 9/10。决策 D9。
  2. taxonomy 对齐为五类：success / insufficient_observation / icp_no_converge / hypothesis_selection_failure / roll_symmetry_ambiguity。
  3. 推理接口固化为 `geo_init.estimate_pose`（Phase 3 学习方法按同签名替换）。
- **与 P2.3-S 一致性**：bottle 90%→93.3%、bowl 80%→77.3%——小幅波动，**结论一致**；失败模式完全相同且更系统化：
  bottle 5 帧 roll 歧义呈同一签名（ADD≈62mm / fitness≈0.95，即几何正确但绕轴错位一个标签宽度）；
  bowl 16 帧 no-converge 聚集在 im 479–687（视频中碗被罐头重遮挡的区段）+ 1 帧选择失败（fitness 0.58 / ADD-S 36.6mm）。
- **Conclusion**：**Phase 2 Classical Baseline Complete**。基线能力：bottle 93.3% @ ADD median 1.3mm；
  bowl 77.3% @ ADD-S median 2.7mm；失败可解释、可分类、集中且非偶然。局限（诚实声明）：
  oracle mask（非端到端）；bowl 对称性使 ADD 不可用；重遮挡段与 roll 歧义是已知弱点。
- **Decision**：Phase 2 收官。Phase 3（Learning-based）的动机由此完全成立：Classical 几何方法的失败模式
  （roll 歧义、遮挡脆弱）与外观路线的失败（域差）都是学习方法的靶点。等待批准后规划 3090 迁移。

---

## EXP-009（追溯编号）— P3.1-C：Post-hoc Canonical Rotation Diagnostic

- **日期**：2026-09-10（追溯编号于 2026-09-11 文档整合时补记；原始记录见
  `docs/` 各 P3.1 报告的引用与 `outputs/p3_1_c_posthoc_rotation/`）
- **一句话**：预注册单一固定旋转（canonical Y 轴 −176.5°）使 Gate 3 从 0/10 恢复 10/10
  （bottle ADD 0.73–1.75mm、bowl ADD-S 1.35–1.51mm）——Gate 3 失败被单一固定 canonical
  frame 偏移完全解释。完整分析见 `docs/P3_1_E_INPUT_SENSITIVITY.md` 之前的
  P3.1 报告链与 CHANGELOG 2026-09-10 条目。

---

## EXP-008 — P3.0-S Gate 3：真实 YCB-V smoke test（定义冻结）

- **日期**：2026-09-08（定义冻结 + 执行完成）
- **Phase**：3（P3.0-S）
- **Question**：CoordNet 在合成数据上学到的 canonical correspondence（Gate 1/2 PASS），能否直接迁移到真实 YCB-V 图像并产出合理的 6D pose？
- **Hypothesis**：sim-to-real 域差存在但不至致命——RANSAC-Umeyama 的鲁棒性 + ICP 精化可以吸收中等程度的对应噪声，至少部分帧 ADD < 0.1d。
- **Setup**：
  - 配置：`configs/p3_0_gate3.yaml`
  - **Pipeline**（推理零 GT pose）：
    1. oracle mask（`mask_visib`，受控条件，与 Phase 2 一致）
    2. masked depth → 相机系点云（5mm voxel downsample，与 P2.3 一致）
    3. 随机采样 1024 点 → normalize → concat RGB/255 → CoordNet forward → 预测 canonical coords
    4. RANSAC-Umeyama（predicted canonical = src, camera-frame xyz = dst；threshold=10mm, 200 iter）→ 鲁棒初始位姿
    5. ICP 精化（scene→model，P2.3 冻结 schedule：3cm→1cm→3mm，≤60 iter/stage）
    6. 最终 pose = ICP result 取逆（camera-frame）
  - **测试帧**（每物体 5 帧，高 visib_fract，全部位于 test_bop19 子集）：
    - obj5 mustard_bottle：scene 50, im [620, 653, 721, 1044, 1113]
    - obj13 bowl：scene 53, im [1, 93, 138, 162, 247]
  - **Checkpoint**：Gate 1 产出 `outputs/p3_0/gate1/coord_net_bottle.pt`（与 Gate 2 使用的相同；Gate 2 未重训）
  - **Correspondence quality metrics**（逐帧记录）：
    - RANSAC inlier count / ratio / mean residual (m)
    - Post-ICP fitness / RMSE (m)
  - **Pose metrics**（逐帧 + 汇总）：
    - ADD (mm) / ADD-S (mm) / 平移误差 (mm) / 旋转误差 (°)
    - 成功判据：ADD < 0.1d = 19.65mm（bottle）/ ADD-S < 0.1d = 16.19mm（bowl）
  - **GO / WEAK / NO-GO 判定**（⚠ 阈值待用户确认，非自行冻结）：
    - GO：每物体 ≥ 3/5 帧 success
    - WEAK：每物体 ≥ 2/5 帧 success
    - NO-GO：任一物体 < 2/5 帧 success
- **Analysis**（设计理由）：
  1. 5 帧/物体 = smoke test 规模（非全 benchmark），目的是快速判定 sim-to-real 迁移可行性
  2. 帧选择偏向高 visib_fract（0.88–1.00）——有意降低遮挡难度，先验证干净场景的迁移能力
  3. RANSAC-Umeyama → ICP 的两阶段结构与 Phase 2 一致（粗初始化 + 精化），可直接对比
  4. ICP 参数复用 P2.3 冻结 schedule，不引入新变量
  5. 已知风险：合成数据无深度噪声/无 RGB 抖动、viewpoint roll 受固定 up-vector 约束——域差可能比预期更大
- **Result**（run: `outputs/p3_0_gate3/`，exit code 0）：

  **obj5 mustard_bottle（scene 50，metric=ADD，threshold=19.65mm）：0/5 success**

  | Frame | visib | ADD(mm) | ADD-S(mm) | trans(mm) | rot(°) | RANSAC inliers | RANSAC ratio | ICP fitness | ICP RMSE(mm) |
  |-------|-------|---------|-----------|-----------|--------|----------------|--------------|-------------|--------------|
  | 620 | 0.998 | 117.45 | 12.60 | 30.3 | 172.4 | 750 | 0.732 | 0.426 | 1.83 |
  | 653 | 0.992 | 118.01 | 13.00 | 39.1 | 178.0 | 697 | 0.681 | 0.447 | 1.79 |
  | 721 | 0.990 | 116.56 | 11.87 | 35.6 | 179.8 | 58 | 0.057 | 0.406 | 1.70 |
  | 1044 | 1.000 | 117.68 | 8.08 | 40.8 | 179.3 | 316 | 0.309 | 0.560 | 1.49 |
  | 1113 | 1.000 | 117.40 | 7.24 | 51.1 | 179.8 | 436 | 0.426 | 0.742 | 1.55 |

  ADD: mean 117.42 / median 117.45 / max 118.01 mm
  ADD-S: mean 10.56 / median 11.87 / max 13.00 mm

  **obj13 bowl（scene 53，metric=ADD-S，threshold=16.19mm）：0/5 success**

  | Frame | visib | ADD(mm) | ADD-S(mm) | trans(mm) | rot(°) | RANSAC inliers | RANSAC ratio | ICP fitness | ICP RMSE(mm) |
  |-------|-------|---------|-----------|-----------|--------|----------------|--------------|-------------|--------------|
  | 1 | 0.981 | 154.52 | 59.35 | 129.6 | 171.6 | 34 | 0.033 | 0.092 | 1.72 |
  | 93 | 0.984 | 157.39 | 62.05 | 133.6 | 170.1 | 32 | 0.031 | 0.084 | 1.65 |
  | 138 | 0.990 | 106.59 | 34.42 | 64.4 | 177.1 | 26 | 0.025 | 0.141 | 1.71 |
  | 162 | 0.997 | 108.62 | 38.23 | 87.1 | 179.7 | 34 | 0.033 | 0.089 | 1.71 |
  | 247 | 1.000 | 104.83 | 34.98 | 73.8 | 174.7 | 36 | 0.035 | 0.083 | 1.82 |

  ADD: mean 126.39 / median 108.62 / max 157.39 mm
  ADD-S: mean 45.80 / median 38.23 / max 62.05 mm

- **Analysis**（failure layer analysis + coordinate/transform audit）：

  **初始 failure layer analysis（Gate 3 执行时）**：
  所有 10 帧旋转误差均为 170°–180°，初步归因为 "canonical-frame ambiguity"——声称训练 loss 对 canonical frame 的全局旋转不变，网络收敛到与 BOP model frame 相差 ~180° 的解。

  **⚠ 撤回：上述 root cause 分析存在技术性错误**
  "per-point L2 loss is invariant under global rotations of the predicted canonical frame" 这一表述**不成立**。训练 loss 为 `||T_cam_model @ pred_canonical - xyz_cam||²`（camera-frame L2），对 pred_canonical 的全局旋转**不是**不变的。用户正确指出了这一错误，要求重新做 failure localization。

  **Coordinate / Transform Audit（failure localization，纯分析，不改代码/不重训/不调参）**：
  1. **合成数据内部一致性 — PASS**：`xyz_cam = T_cam_model @ coords` 最大误差 3.13e-05 m（float16 精度）
  2. **闭环测试 — PASS**：用合成数据做输入，CoordNet + RANSAC-Umeyama 恢复位姿：旋转误差 **4.05°**，平移误差 **4.1 mm**，内点率 **97.2%**，平均残差 **3.8 mm**
  3. **坐标链一致性 — 确认**：合成数据 → CoordNet 训练 → RANSAC → ICP 的整条变换链方向正确，无帧混淆
  4. **合成 coords vs BOP model points**：最大距离 2.85 mm（float16 精度 + raycasting 采样差异，不影响闭环）

  **闭环测试通过的含义**：坐标变换链在数学上正确，不存在变换方向 bug、不存在帧混淆、不存在 Umeyama src/dst 颠倒。Gate 3 失败**不是** pipeline 实现错误。

  **修正后的 root cause**：
  The primary observed failure is **poor real-data generalization of the learned canonical correspondence**; the specific source of the sim-to-real gap is not fully isolated.

  证据：
  - CoordNet 在合成数据上可以学到有意义的 correspondence（Gate 1/2 PASS，闭环 4°/4mm）
  - 但在真实 YCB-V 深度图上完全失败（0/10 帧），呈现系统性 ~180° 旋转
  - 唯一解释：网络从合成渲染域到真实深度图域的**泛化失败**
  - ~180° 旋转可能是 bottle/bowl 的近似旋转对称性 + 网络噪声导致的 RANSAC 系统性偏差，而非 "canonical frame 模糊性"

  **Failure layer breakdown（修正后）**：
  - **Layer 1 — CoordNet sim-to-real generalization（ROOT CAUSE）**：网络在真实数据上的 per-point 预测质量不足
  - **Layer 2 — RANSAC**：继承 Layer 1 的错误预测；bowl 的 inlier ratio 极低（2.5%–3.5%）表明网络对未见物体泛化更差
  - **Layer 3 — ICP**：功能正常（低 RMSE），但无法从大角度初始误差恢复

  **Bottle vs Bowl 差异**：
  - Bottle RANSAC inlier ratio 5.7%–73.2%（训练物体，有一定泛化）
  - Bowl RANSAC inlier ratio 2.5%–3.5%（未见物体，近似随机）
  - CoordNet 学到的是 bottle-specific 特征，非通用 canonical correspondence

- **Conclusion**：
  - **Gate 3 判定：NO-GO**（bottle 0/5, bowl 0/5）
  - ⚠ **GO/WEAK/NO-GO 阈值（3/5, 2/5）为提案，未经用户冻结**
  - Coordinate / Transform Audit 通过，排除 pipeline 实现错误
  - Synthetic learning：successful（Gate 1/2 PASS）
  - Synthetic closed-loop：successful（4°/4mm）
  - Real-data transfer：failed（0/10）
  - Root cause：sim-to-real domain gap（具体来源未完全隔离）

- **Decision**：Gate 3 NO-GO。sim-to-real 迁移在当前配置下不可行。
  Coordinate / transform chain validated；失败源于学习方法的泛化能力不足，非实现错误。
  修复路径存在但需要新实验（domain randomization / real fine-tuning / 更大网络 / 更多数据等），全部留到下一阶段规划。

  本轮不改冻结参数，不自动修复，不进入新的学习改进实验。产物：`outputs/p3_0_gate3/gate3_results.json` + 10 overlay PNGs + `scripts/_audit_coordinate_transform.py`。

---

---

## EXP-009 — P3.1-C：Post-hoc Canonical Rotation Diagnostic —— **固定旋转完全解释 Gate 3 失败（0/10 → 10/10）**

- **日期**：2026-09-10
- **Phase**：3（P3.1-C，诊断/定位实验，非正式 baseline）
- **Question**：P3.1-B 发现的 ~176.5° 系统性 canonical 旋转，是否足以解释原 Gate 3 的 pose failure？
- **Setup**（全部冻结，仅插入一个固定旋转）：
  - 预注册修正旋转：**绕 canonical Y 轴 −176.5°**（右手法则）。
    轴来自 P3.1-B 逐轴相关签名（−,+,−，clean bottle：X −0.84 / Y +0.57 / Z −0.997）；
    角度来自 P3.1-B rigid alignment 均值（clean bottle 176.6° / bowl 176.5° / 全体 175.1–179.0°）。
    **预注册 caveat**：符号不可从已发布证据恢复（±176.5° 的一阶相关签名相同）；错误符号的期望残差仅 ~7°
    （物半径处 ~10mm），诊断在两种符号下均有效。
  - 其余与 Gate 3 逐位同构（同 checkpoint/预处理/max-radius 归一化/sampling seeds/RANSAC/ICP/metrics）；
    baseline 数字直接读取 `gate3_results.json`，**不重跑 baseline**。
  - 入口：`scripts/p3_1_c_posthoc_rotation.py`（run: `outputs/p3_1_c_posthoc_rotation/`）。
- **Result**：
  | 物体 | Baseline | + 固定旋转修正 | 修正后主指标 | 修正后 ICP fitness |
  | --- | ---: | ---: | --- | --- |
  | obj5 bottle (ADD<19.65mm) | 0/5 | **5/5** | ADD **0.73–1.75mm**（mean 1.13），rot 0.9–2.4° | 0.88–0.96 |
  | obj13 bowl (ADD-S<16.19mm) | 0/5 | **5/5** | ADD-S **1.35–1.51mm**（mean 1.46）；ADD 12.3–109.4mm（对称等价类内） | 0.78–0.90 |
  - 预注册符号校验：bottle 修正后 rot 仅 0.9–2.4°，远小于错误符号预期的 ~7° 额外残差 → 所选符号与真实失配一致。
- **Analysis**：
  1. **判定性回答：是。** 单一固定 canonical 旋转把 Gate 3 从 0/10 翻正到 10/10，且 bottle 修正后精度
    （ADD ~1mm，rot ~1–2°）与合成域能力（Gate 2 val ADD 5.8mm）同量级甚至更好（ICP 精化功劳）。
  2. **失败模型精化（修正 P3.1-B 的部分判断）**：frame 721（归一化污染、预测"坍缩 18×"）修正后 ADD 1.75mm——
    均匀尺度坍缩**不破坏** Kabsch/Procrustes 的旋转估计（尺度作为正标量因子从正交 argmax 中消去），平移被
    Umeyama 吸收，度量级残差由 ICP 用完整模型清理。**对 pose 而言，逐点坍缩不是致命的；致命的只有 fixed frame offset。**
  3. bowl 的 rot 11.6–133.6° 但 ADD-S ~1.5mm：位姿落在旋转对称等价类内，指标行为与 Phase 2 的对称性结论一致。
- **边界与诚实声明**：
  - 原 **Gate 3 NO-GO 结论不变**：本实验是诊断，不是可部署 pipeline——修正旋转依赖 P3.1-B 的 GT 诊断知识，
    推理系统无法获得；"P3.0-S 已经成功"的说法不成立。
  - **~176.5° 偏移的来源仍未证明**（hypothesis）：合成/真实 canonical frame 约定差异、外观线索（标签正反）在两域
    反转、或网络在真实域收敛到不同 frame mapping——均在候选列表，未被隔离。
  - 符号/轴的预注册选择如上；错误符号的预期行为已量化，实测与正确符号一致。
- **Decision**：P3.0-S 的失败归因由"泛化失败（来源不明）"精化为"**单一低维缺陷：固定 canonical frame 偏移**
  （外加 bowl 的逐点坍缩——被证明对 pose 无害）"。Phase 3 的续/停决策现在有明确的证据基础，等待用户批准：
  (a) 定位 176.5° 偏移来源的定向实验（候选：纯几何输入消融/外观消融/训练数据 frame 约定复查）；
  (b) 按原纪律关闭自研路线（Classical 保持 baseline，Phase 4 FoundationPose 作为 learning 对照）。

---

## EXP-010 — P3.1-E：Input Sensitivity Diagnostic——偏置由几何通路驱动，外观假设被否定

- **日期**：2026-09-10
- **Phase**：3（P3.1-E，输入敏感性诊断；**注**：审批消息在 Condition A 后截断，B/C/D 条件为
  标准敏感性集合预注册，脚本注释已标注，可与原稿比对后廉价重跑）
- **Question**：~176.5° real-domain orientation bias 由 RGB、XYZ 还是二者逐点关联驱动？
- **Setup**：frozen checkpoint + Gate 3 全部冻结参数；四条件（full / rgb_mean / xyz_zero / rgb_shuffle）
  × 10 真实帧 + 10 合成对照（Gate 2 val）；GT 仅评测端。**Input Sensitivity Diagnostic，
  非模态 ablation**（checkpoint 从未单模态训练）。
- **Result**（详见 `docs/P3_1_E_INPUT_SENSITIVITY.md`）：
  - real bottle：full 176.1° / rgb_mean **173.4°** / rgb_shuffle **175.8°** / xyz_zero 165.4°（坍缩 r=2.2mm，证据弱）
  - real bowl：full 175.6° / rgb_mean 175.2° / rgb_shuffle 176.8° / xyz_zero 82.9°（坍缩）
  - **合成对照**：full 3.2° / rgb_mean 49.7° / xyz_zero 105.8°（坍缩）/ rgb_shuffle 13.4°
- **Analysis**：
  1. 两种破坏逐点外观-几何关联的方式（均值/打乱）均不改变偏置（176.1→173.4/175.8）→
     **逐点 RGB 内容不是偏置载体**，P3.1-D H-b（标签外观反转）强形式被否定。
  2. rgb_mean（仅几何有信息、非坍缩）偏置仍 173.4° → **纯几何输入足以触发翻转——几何通路驱动**。
  3. 合成对照：full 合成 3.2° vs real full 176.1°——翻转确为 real 触发，非消融伪影；
     且合成 rgb_mean 恶化至 49.7° 说明逐点外观在合成域是承重的——real 下被几何翻转淹没。
  4. xyz_zero 两域坍缩（1.3–2.4mm），其偏置数不具解释力（H-e 类条件局限，如实记录）。
- **Conclusion / Decision**：
  - 失败定位进一步收窄：**几何通路的 real-domain 响应**是 ~176.5° 偏置的载体；
    RGB 侧 domain randomization 对该失败无效（对后续迭代的重要工程结论）。
  - 候选机制（H-e1 覆盖模式/H-e2 深度噪声/H-e3 容量）未隔离，需新实验，等待批准。
  - Gate 3 NO-GO、P2.4 Classical 基线均不变。

---

## EXP-011 — P3.1-F：Synthetic vs Real Geometry Distribution Audit——两个 failure regime 的划分

- **日期**：2026-09-10
- **Phase**：3（P3.1-F，只读分布审计）
- **Question**：真实输入给 CoordNet 的几何分布与训练/验证 synthetic 几何分布差多少？
  该差异能否为 ~176° orientation bias 提供直接证据？
- **Setup**：测量网络真正收到的归一化 XYZ（复现 Gate 3 frame_seed 采样）+ canonical 系可见性覆盖
  （real 用评测端 GT 反算；synth 用标签）；NN 域差对同物体合成池；深度质量统计（空洞/离群点）。
  零模型/管线改动。入口：`scripts/p3_1_f_geometry_distribution.py`。
- **Result**（`outputs/p3_1_f_geo_stats/`）：
  | 组 | cam_norm 轴 std vs synthetic | NN 域差（基线 0.475mm） | 深度离群点 | 覆盖 L1 |
  | --- | --- | ---: | ---: | --- |
  | bottle clean | 同量级（差 21–33%） | **2.43–3.27×**（≈1mm 噪声级） | 0 | 0.72–0.99（合成单 view 自然波动 0.47–0.84） |
  | bottle 721 | 压缩 4–18× | 12.68× | **66**（mask 泄漏确认） | 0.83 |
  | bowl | 压缩 4–16× | **5.7–33.3×** | **42–316/帧** | 0.40–0.60 |
- **Analysis（核心产出：两个 failure regime 的划分）**：
  1. **Regime 1 — clean bottle**：几何近 in-distribution（NN 差 ≈1mm 噪声级）却发生确定性 176.5° 翻转
     → 不是分布问题，是**朝向决策零裕度/朝向锚点缺失**（网络在真实几何扰动下无稳定朝向解）。
  2. **Regime 2 — 721 + bowl**：严重几何 OOD（尺度污染 10–20×、离群点 42–316/帧、NN 域差 12–87×）
     → 预测坍缩的直接原因之一；但 P3.1-C 证明即使此类帧，固定旋转+ICP 仍恢复 ~1–2mm pose。
  3. 合成对照基线补齐：单合成 view 对 50-view 均值的 L1 自然波动 0.47–0.84——real clean 的 0.72–0.99
     仅略超，覆盖缺失不构成翻转的直接解释（H-f3 部分削弱）。
- **Conclusion / Decision**：
  - 对用户问题的回答：**分布差异对 Regime 2 是直接证据；对 Regime 1（clean bottle）不是**——
    clean bottle 的翻转需要"朝向裕度/锚点"层面的解释（H-f1），分布审计无法提供。
  - 若重启学习路线的杠杆分化：Regime 1 → 朝向等变性/锚点设计；Regime 2 → 几何域对齐
    （深度噪声/泄漏/遮挡模拟）。等待批准，本轮不延伸。
  - 审计脚本自身的 3 处实现问题（键序/数组覆盖/跨物体参考池）已修正并记录，早期跨物体 bowl NN 值作废。

---

## EXP-012 — P3.1-G Phase 1：Depth Noise-Scale Sanity Check——**1mm 不被支持，训练前停止**

- **日期**：2026-09-10
- **Phase**：3（P3.1-G 第一阶段；按批准的决策树在训练前停止）
- **Question**：已有 real depth 数据是否支持"毫米级（~1mm）深度噪声"作为合理的 synthetic augmentation 量级？
- **Setup**（只读，简单统计量，无 GT 需求）：3×3 box 高通残差 r = z − blur(z)（box 保线性、倾斜不污染；
  曲率贡献 ~0.03mm 可忽略）；平滑像素门控（局部 3×3 range < 3mm，排除轮廓/不连续）；
  隐含 σ = std(r_smooth)·√(9/10)（i.i.d. 像素噪声下 Var(r) = σ²(1+1/9)）。
  帧 = Gate 3 固定 10 帧。入口：`scripts/p3_1_g_noise_sanity.py`。
- **Result**：
  | 帧 | median\|r\| | p90\|r\| | 隐含 σ |
  | --- | ---: | ---: | ---: |
  | bottle clean ×4 | 0.111–0.222mm | 0.444mm | **0.263–0.297mm** |
  | bottle 721 | 0.111mm | 0.444mm | 2.516mm（污染帧） |
  | bowl ×5 | 0.111mm | 0.500–0.556mm | 0.357–3.356mm（部分污染） |
  - 跨帧汇总：隐含 σ median **0.372mm**、max 3.356mm；median\|r\| 全部 0.111–0.222mm（≈深度量化步长 0.1mm 量级）。
- **Analysis**：
  1. 平滑表面的高频深度噪声为**亚毫米**（隐含 σ ≈ 0.26–0.40mm；clean bottle 稳定在 0.26–0.30mm），
     局部残差中位数已接近深度量化步长（0.1mm/单位）。
  2. 1mm i.i.d. 像素噪声 ≈ 实测高频噪声的 ~3×——**"训练缺少真实 ~1mm 深度噪声"的假设失去量级依据**。
  3. 污染帧（721/bowl 部分）的 1.8–3.4mm 局部 σ 来自泄漏/多次反射——属 P3.1-F Regime 2 的结构伪影，
     不是基础传感器噪声，不应作为高斯增广的量级依据。
  4. 方法局限（如实声明）：3×3 高通只测高频噪声，低频/相关深度误差对本估计不可见；
     若要表达此类误差，增广模型需另行设计（低频偏置场等），超出本轮范围。
- **Decision（按预批准决策树）**：**停止，不训练，不自行选择新 σ。**
  建议量级（如未来重启该方向）：高频噪声增广 σ ∈ [0.25, 0.5]mm；
  或改用结构化深度伪影建模（泄漏/低频偏置），需另行提案。
- **对假设链条的影响**：P3.1-F Regime 1（clean bottle 近 in-distribution 仍翻转）进一步巩固——
  真实高频噪声比亚干净 3×，"噪声缺失"更不可能是 clean bottle 翻转的原因。
  P3.0-S/Phase 3 自研路线的证据链至此完整闭合于：**朝向锚点缺失（Regime 1）+ 结构性几何伪影（Regime 2）**。

### 非正式记录：bowl 训练产物（无 EXP 编号，待决策）

以下产物存在于仓库中但无对应实验记录：

- `data_synth/bowl/`：200 train + 50 val 合成样本（obj_id=13，mtime 2026-08-31 13:23）
- `outputs/p3_0/bowl_train/coord_net.pt`：ADD loss checkpoint（mtime 2026-08-31 13:35:29）
- `outputs/p3_0/bowl_train/coord_net_adds.pt`：ADD-S loss checkpoint（mtime 2026-08-31 13:35:29）

**证据**：
- 数据完整性 PASS（frame consistency 3.1e-5 m，obj_id=13 确认）
- Checkpoint 与 Gate 1 bottle checkpoint 结构相同（58563 params）但权重不同
- 时间线与 `cmd_train` 子命令（未提交代码）一致——数据生成后 ~12 分钟训练完成
- 无任何评估指标、无 log、无 EXP 记录

**性质判断**：临时探索性训练运行，验证 `cmd_train`（ADD-S loss 变体）能否在 bowl 上运行。
不属于正式实验（无 Question/Hypothesis/Result），不满足实验纪律要求。

**建议**（待用户确认）：
1. 保留产物，在 EXPERIMENT_LOG 中标注为"非正式运行，不承认正式结论"
2. 不将其纳入项目正式实验序列
3. Gate 3 不使用 bowl checkpoint（使用 Gate 1 bottle checkpoint）
4. 若后续需要正式 bowl 实验，需新分配 EXP 编号并包含完整评估





---

## EXP-014 — W2-3 跨物体统一 baseline（7 物体评测集）

- **日期**：2026-09-13
- **Phase**：W2-3（Phase 2 baseline 的跨物体统一评测，非新方法）
- **Question**：冻结的 P2.4 classical baseline（EXP-005/006 全套冻结参数）在 W2-2 选定的
  7 物体评测集上，以统一协议最小子集运行时表现如何？它的有效包络（envelope）边界在哪里？
- **Hypothesis**：
  1. 同一冻结 pipeline 无需任何算法/参数改动即可在全部 7 物体上运行并产出可比较结果；
  2. 强纹理/复杂几何物体预期表现好，纯对称/低纹理物体按 EXP-006 已知失败模式
     （roll 歧义、遮挡不收敛）退化；
  3. 若某物体系统性失败，归因为 baseline 包络而非数据/评测错误（预注册归因规则，
     禁止为提升分数调参）。
- **Setup**：
  - **Baseline**：`r3p.experiments.run_p2_3` 全链复用（零算法改动，配置
    `configs/w2_3_multibaseline.yaml` 与 `configs/p2_4.yaml` 的 icp/selection/success
    参数逐项相同，有测试守护）；oracle `mask_visib`（声明性受控条件）；
  - **物体与 metric（跑前预注册）**：obj2 cracker_box→ADD、obj6 tuna_fish_can→ADD-S
    （扁圆柱=旋转对称，与 bowl 同判据）、obj10 banana→ADD、obj14 mug→ADD（手柄打破
    对称）、obj15 power_drill→ADD；阈值 ADD(-S)<0.1×官方 diameter；
  - **帧采样**：每新物体 10 帧，`select_eval_frames` linspace 确定性均匀采样。
    scene 50：obj2/obj10/obj15（采样帧 620,653,721,1044,1113,1209,1324,1658,1718,1874，
    其中 5 帧与 anchors/EXP-013 冻结帧同帧）；scene 48：obj6/obj14（obj6/14 不在
    scene 50 出现，取其首个可用场景，两物体同场景可互照）；
  - **Anchors 处理**：obj5/obj13 **不重跑**，引用 EXP-006 历史逐帧结果
    （source=historical，75 帧），与新评测（source=EXP-014，10 帧）在统一表中分列标注；
  - **入口**：`python -m r3p.experiments.run_p2_3 --config configs/w2_3_multibaseline.yaml`；
    汇总 `scripts/w2_3_unified_table.py`（中位数口径=EXP-006 metrics.json 约定：
    所有产出指标值的帧，anchor 行逐位复现 1.30/2.67 冻结值）。
- **Run**：`outputs/w2_3/20260913-094927/`（CPU，~66s 全部；逐帧 overlay + per_frame CSV + manifest）
- **Result**（Unified Object Baseline Table，完整口径见 `outputs/w2_3/unified_table.md`）：

| Obj | Name | Source | N | Success | med ADD | med ADD-S | 失败 |
| --- | --- | --- | ---: | ---: | ---: | ---: | --- |
| 5 | mustard_bottle | historical (EXP-006) | 75 | 70/75=93.3% | 1.30mm | 1.21mm | roll×5 |
| 13 | bowl | historical (EXP-006) | 75 | 58/75=77.3% | 94.57mm | **2.67mm** | no_converge×16, sel×1 |
| 2 | cracker_box | EXP-014 | 10 | **7/10** | 3.19mm | 2.76mm | roll×3 |
| 6 | tuna_fish_can | EXP-014 | 10 | **0/10** | – | – | insufficient×10 |
| 10 | banana | EXP-014 | 10 | **7/10** | 3.48mm | 1.71mm | insufficient×2, roll×1 |
| 14 | mug | EXP-014 | 10 | **0/10** | 190.82mm | 149.71mm | no_converge×7, roll×2, insufficient×1 |
| 15 | power_drill | EXP-014 | 10 | **10/10** | 1.21mm | 1.17mm | 无 |

  （med = 该物体成功判据列的中位数；bowl 行 med ADD 高是旋转对称的必然，判据为 ADD-S。）
- **Analysis**：
  1. **包络上界**：大尺寸/强纹理/复杂几何物体上冻结基线依然强——drill 10/10（med 1.21mm）、
     box 7/10、banana 7/10（成功帧 ~1.7–3.5mm）；obj15 证明「mask 给定 + 几何丰富」时
     PCA/OBB+ICP 接近完美；
  2. **失败模式 A——点数地板（obj6 全灭）**：10/10 帧 `insufficient_observation`。探针实测：
     mask 健康（5–8k px），但 tuna_can 整只网格在 5mm 体素下仅 **990 点**（可见子集必然
     < 冻结 `min_cloud_pts=500`）。归因：**冻结参数的尺度下限**（d≈90mm 扁物体），
     非 adapter/评测 bug；按纪律**不调参**；
  3. **失败模式 B——低纹理凹面不收敛（obj14 全灭）**：7/10 帧 ICP 未过 solver 门
     （fitness/rmse），2 帧 roll 翻转（rot med 179.6°）；低纹理 + 凹面杯体是纯几何 ICP 的
     已知弱点，与 EXP-006 bowl 遮挡不收敛同族但更严重；
  4. **失败模式 C——近对称翻面（obj2×3、obj10×1）**：与 bottle roll 歧义同族
     （ADD-S 好、ADD 差），cracker box 俯视近方对称所致；
  5. 无 runtime_error、无数据适配错误；失败帧全部保留在 CSV 中（未删除任何帧）。
- **Decision**：
  1. 结果冻结入档（EXP-014）；`configs/evaluation_objects.yaml` registry 将 5 新物体标记
     evaluated（source EXP-014），anchors 保持 EXP-006；
  2. **不调参**：min_cloud_pts/voxel/ICP 调度均不动——任何放宽都是协议变体，需单独提案
     并与本 baseline 分列，不得混入 EXP-014 口径；
  3. obj6/obj14 的包络边界直接支撑 FoundationPose 强基线对照（EXP-013，待 3090）的必要性；
  4. 10 帧 ≠ 75 帧：跨物体比较仅在同一 N 口径内进行，README 引用时强制标注 N 与 source。

### EXP-014 Addendum（2026-09-13，W2-3.1 协议收口——结果解释正式化，非算法改动）

- **四层统计语义**（从 runner 代码 + 真实 CSV 推导，权威表述见
  `docs/BASELINE_OPERATING_ENVELOPE.md` §4）：total=采样帧数；valid=进入处理的帧数
  （无效输入会中止运行，实测 valid=total）；**attempted=进入 solver 的帧数
  = total − insufficient_observation − runtime_error**（`icp_no_converge` 已跑
  PCA+ICP 且有位姿/指标 → 计 attempted；`insufficient_observation` 是 solver 前
  点数地板拒绝 → 不计）；success = ADD(-S)<0.1d 且过 solver 门（runner 冻结定义）。
- **双成功率**：success_rate = success/total（项目 metrics.json 口径）；
  conditional pose success = success/attempted（attempted=0 → N/A，禁止 0/0=0%）。
- **obj6 Operating Envelope Finding（正式化）**：attempted=0——不是 "ICP 失败 10 次"，
  而是冻结分辨率/点数门槛（5mm 体素、`min_cloud_pts=500`）下观测不足、无法进入
  solver；探针证据：mask 健康 5–8k px、整只网格 @体素仅 990 点。
- **obj14 failure composition（正式化）**：total=10, valid=10, attempted=9, success=0
  = icp_no_converge×7（gate failure，有位姿有指标）+ roll_symmetry_ambiguity×2
  + insufficient_observation×1。
- **Symmetry metric policy 显式注册**：`configs/evaluation_objects.yaml` 的
  `metric_policy`（pre_registered_geometry_policy，跑前预注册；anchors 沿用 EXP-006
  口径永不重判；YCB-V models_info.json 无 symmetry 标注——不得表述为官方标签）。
- **统一表升级**：Total/Valid/Attempted/Success 四层列 + 双成功率 + failure
  composition（`scripts/w2_3_unified_table.py` v2）；误差中位数口径不变
  （anchor 行逐位复现 1.30 / 2.67 冻结值）。
- 本 addendum **不改变 EXP-014 的任何数字、算法或参数**；失败语义的权威表述以
  `docs/BASELINE_OPERATING_ENVELOPE.md` 为准。
