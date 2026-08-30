# EXPERIMENT_LOG

> 记录规范：每个实验一条记录，必须包含 Question / Hypothesis / Setup / Result / Analysis / Decision。
> 原始数据（metrics.json、日志、可视化）存放在 `outputs/<exp_name>/<timestamp>/`，本文件记录要点与结论。

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





