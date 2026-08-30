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


