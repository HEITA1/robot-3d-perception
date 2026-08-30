# PROPOSAL: Phase 1 数据获取方案（等待批准，未执行任何下载）

- 日期：2026-08-30
- 状态：**APPROVED & EXECUTED**（2026-08-30；验证结果见 `docs/phase1_data_validation_report.md`——本地 GT 确认存在，决策树未触发）
- 结论：请求批准下载 **3 个官方文件，共 1.13 GB**（下载后磁盘峰值 ~3.4 GB，解压并删除压缩包后稳态 ~1.6–2.2 GB）。
  无法按"单个物体"裁剪下载（官方最小粒度是整个 split 包），1–2 个物体的控制在数据接口层实现，总体积仍在既定预算内。

---

## 1. 已核实事实（全部实测/官方来源，非假设）

### 1.1 官方包清单与体积（HuggingFace `bop-benchmark/ycbv`，经镜像 API 实测字节数）

| 包 | 体积 | 内容 | 我们的取舍 |
| --- | ---: | --- | --- |
| `ycbv_base.zip` | **15 KB** | camera.json（默认内参）、dataset_info、`test_targets_bop19.json`（评测帧列表） | **必选** |
| `ycbv_models.zip` | **500 MB** | 21 个物体模型（BOP 约定：毫米单位、原点=包围盒中心；含 models / models_eval / models_fine 三个变体） | **必选** |
| `ycbv_test_bop19.zip` | **630 MB** | BOP'19–24 评测用 test 图像子集（rgb + depth + 场景元数据；帧列表即原版数据集 `keyframe.txt` 子集，与 DenseFusion/FFB6D 文献评测帧同源） | **必选** |
| `ycbv_test_all.zip` | 15.0 GB | 全部 test 视频（45 个场景，所有帧） | 缓存备选，现在不下 |
| `ycbv_train_real.zip` + `.z01` | 27.4 + 48.3 GB | 训练真实帧（含公开 GT；Phase 3 训练才需要） | **超限，Phase 3 单独报批** |
| `ycbv_train_pbr.zip` | 21.0 GB | PBR 合成训练图（BOP 2020） | 缓存备选 |
| `ycbv_train_synt.zip` | 21.6 GB | 原版 80K 合成图；**官方提示勿用**（姿态与 test 重合） | 永不 |
- 全量 YCB-V（原版 PoseCNN 发布）为 **~265 GB 单包**（Box 托管）——确认不可行，排除。

### 1.2 本机连通性与磁盘（实测）
- `huggingface.co`：**本机直连超时（不可用）**；`hf-mirror.com`：HTTP 200，0.5 s。→ 下载走镜像（`curl -L -C -` 支持断点续传）。
- D 盘可用 **190 GB**；本次方案峰值占用 ~3.4 GB，无压力。

### 1.3 BOP 格式要点（来自 bop_toolkit 官方格式文档）
- 目录：`test/<scene_id>/{rgb,depth,mask,mask_visib}/` + `scene_gt.json` + `scene_gt_info.json` + `scene_camera.json`；图像按 `im_id` 对齐（`000001.png/jpg`）。
- **深度**：16-bit PNG；`深度(mm) = 原始值 × depth_scale`，`depth_scale` 逐图存于 `scene_camera.json`（ycbv 为 0.1，即原始值 ×10⁻⁴ = 米）。**代码必须从 scene_camera.json 读取，不许硬编码**。0 = 无效深度。
- **GT 位姿**：`scene_gt.json[im_id]` = 实例列表，每项 `{cam_R_m2c(9), cam_t_m2c(3), obj_id}`；**cam_t_m2c 单位是毫米**（×10⁻³ 转米）；列表顺序即 `gt_id`（对应 mask 文件名 `{im_id:06d}_{gt_id:06d}.png`）。
- **内参**：`scene_camera.json[im_id].cam_K`（行主序 9 元素），逐图可变（ycbv 场景内恒定）。
- `scene_gt_info.json`：`bbox_obj / bbox_visib / px_count_visib / visib_fract`——**visib_fract 可直接用于 Phase 5 按遮挡程度分层采样**（重要红利）。
- 模型：毫米单位、原点=包围盒中心、Z 轴向上；`models_info.json` 含每物体 diameter（Phase 2 的 0.1d 阈值需要）与（部分物体的）对称性标注。
- 相机系：OpenCV 约定（x 右、y 下、z 前向）。与原版 YCB-Video 约定不同，但 BOP 包内图像与 GT 自洽；实现后必须做"GT 模型投影叠加 RGB"的视觉自检一锤定音。
- ⚠ 待解压确认的小项：rgb 扩展名（.png/.jpg）、test 包是否含 `mask/mask_visib`（Phase 1 不需要 mask；若缺，可由 GT 位姿+模型渲染生成，不阻塞）。

## 2. 关键风险与裁决步骤：test 集是否含 GT 位姿？

- 证据 A（支持含 GT）：BOP 官网 **YCB-V 条目没有**"test GT 不公开"声明（对比 ITODD/HB 明确声明了）；legacy 数据集历来支持本地评测。
- 证据 B（存疑）：BOP 2024 起总体政策趋向服务器评测；近期部分工作（threednel、NCF）对 ycbv test 走在线服务器。
- **影响**：若 test 包无 GT，Phase 1（点云/变换正确性，roundtrip 自洽验证）不受影响；但 Phase 2–5 的本地评测与鲁棒性实验（核心研究）需要本地 GT。
- **裁决**：下载解压后 5 分钟内 `unzip -l | grep scene_gt` 一锤定音（见 §4 决策树）。在批准的包内验证，不产生新下载。

## 3. 关于"按 1–2 个物体裁剪下载"的诚实回答

- **官方不存在按物体拆分的包**。最小粒度 = 整个 `test_bop19`（全部物体、全部 test 场景，630 MB）。
- 物体级控制在**数据接口层**实现：`YcbvBopDataset(obj_ids=[...])` 只暴露选中物体（配置项，默认 **006_mustard_bottle（非对称）+ 024_bowl（旋转对称，强制 ADD-S）**，obj_id 以解压后 models_info.json 为准核对）。
- 体积天然落在预算内（下载 1.13 GB、稳态 ≤2.2 GB），故不值得为省几十 MB 做模型包的部分解压。

## 4. 下载执行方案（批准后执行）

```bash
mkdir -p data/_archives/ycbv data/ycbv
# 三个文件逐一下载（断点续传 + 重试），镜像直链：
curl -L -C - --retry 5 -o data/_archives/ycbv/ycbv_base.zip \
  "https://hf-mirror.com/datasets/bop-benchmark/ycbv/resolve/main/ycbv_base.zip"
# 同理 ycbv_models.zip (500MB)、ycbv_test_bop19.zip (630MB)
# 完整性：unzip -t 校验 → 解压到 data/ycbv/（BOP 约定三包同目录）→ unzip -t 通过后删除 zip
```

- 目录布局：`data/ycbv/{models/, test/, camera.json, test_targets_bop19.json}`（`data/` 已在 .gitignore，永不入库）。
- 磁盘曲线：下载完 1.13 GB → 解压中峰值 ~3.4 GB → 删 zip 后稳态 ~1.6–2.2 GB。

### 解压后 30 分钟验证清单（全本地）
1. `grep scene_gt` 裁决 test GT 存在性 → 触发 §5 决策树
2. 解析 `test_targets_bop19.json`：确认场景/帧数（文献值 ~2,952 帧）
3. 单帧验证：深度 PNG ×depth_scale → 米 → 反投影点云 → 重投影往返误差 ≈ 0
4. GT 模型投影叠加 RGB 可视化 → 坐标约定与内参一锤定音
5. models_info.json：obj_id ↔ 物体名映射、diameter、对称性标注

## 5. 决策树：若 test 包不含 GT（裁决后触发，届时停下请示）

| 备选 | 说明 | 评估 |
| --- | --- | --- |
| a. 第三方原版 keyframes 标注补齐 | 原版 `*-meta.mat` 对全部 keyframe 公开 GT；找可信镜像 | 来源可信度需单独评估，重新报批 |
| b. 特批更大官方包 | train_real 75.7 GB 含公开 GT | 超出你设定的数十 GB 红线，需你特批 |
| c. 改服务器评测协议 | 放弃本地 GT | **牺牲 Phase 5 鲁棒性实验，不推荐** |

## 6. Phase 1 必需 vs 可缓

- **必需（本次申请）**：base 15 KB + models 500 MB + test_bop19 630 MB = **1.13 GB 下载，~2.2 GB 稳态磁盘**。
- 可缓（后续单独报批）：test_all 15 GB（更多评测帧）、train_real 75.7 GB（Phase 3 训练）、train_pbr 21 GB（增强）。
- 永不：train_synt 21.6 GB、265 GB 原版全量。

## 7. 请求批准的边界

1. 下载 §4 三个文件（1.13 GB）至 `data/_archives/ycbv/`；
2. 校验、解压至 `data/ycbv/`、删除 zip；
3. 执行 §4 验证清单；若触发 §5 决策树则停下汇报，不自行补救。
