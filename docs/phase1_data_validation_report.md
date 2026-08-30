# Phase 1 数据验证报告 — BOP YCB-V test_bop19

- 日期：2026-08-30
- 依据：已批准的 `docs/proposal_phase1_data.md`（仅 3 个文件，1.13 GB）
- 结论：**全部验证通过，本地 GT 确认存在，数据就绪**。压缩包已按批准删除。
- 验证脚本：`scripts/verify_ycbv_data.py`（可重复执行）；产物在 `outputs/verification/`（gitignored）

## 1. 下载与解压（按批准范围，无超界）

| 文件 | 体积（字节） | unzip -t | 解压目标 |
| --- | ---: | --- | --- |
| `ycbv_base.zip` | 15,805 | 通过 | `data/ycbv/`（camera_uw/cmu.json、dataset_info.md、test_targets_bop19.json） |
| `ycbv_models.zip` | 524,634,729 | 通过 | `data/ycbv/models{,_eval,_fine}/` |
| `ycbv_test_bop19.zip` | 660,198,701 | 通过 | `data/ycbv/test/` |

下载源：`hf-mirror.com`（本机直连 huggingface.co 不可达，实测镜像可用）；断点续传模式 `curl -L -C -`。
**稳态磁盘占用 1.6 GB**（models 164M + models_eval 4.8M + models_fine 781M + test 672M），压缩包删除后 D 盘余 188 GB。`data/` 已被 .gitignore 覆盖，未入库任何数据。

## 2. 首要裁决：本地 GT 存在 ✅（决策树未触发）

`test/<scene>/scene_gt.json`、`scene_gt_info.json`、`scene_camera.json`、`mask/`、`mask_visib/` **全部存在且可解析**。
→ Phase 2–5 的本地评测与鲁棒性实验路线保持不变，无需任何补救方案。

## 3. 验证结果明细（脚本自动检查，OVERALL: PASS）

| # | 检查 | 结果 |
| --- | --- | --- |
| 1 | GT/元数据可解析（12 场景） | ✅ 12/12 |
| 2 | 每帧 rgb+depth 文件配对 | ✅ 900/900 帧（12 场景 × 75 帧） |
| 3 | `depth_scale` 全部 = 0.1；场景内 K 恒定 | ✅（fx=1066.778, fy=1067.487, cx=312.987, cy=241.311，640×480） |
| 4 | models_info.json：21 物体、diameter | ✅ obj5 mustard_bottle d=196.5mm；obj13 bowl d=161.9mm **含 symmetries_continuous** |
| 5 | 深度→点云→重投影往返 | ✅ 最大误差 1.14e-13 px / 0.0 m |
| 6 | GT 模型投影叠加 RGB | ✅ 像素级对齐（见 §4） |

目标物体在 test 集中的 GT 实例数：**obj5 = 150，obj13 = 150**（评测目标总数 4,123，场景 000048–000059）。

## 4. 人工视觉确认（关键：坐标约定一锤定音）

- `overlay_000050_000620.png`：mustard_bottle GT 模型点（10,983 顶点全部在界内）与 RGB 中瓶子**像素级重合** → BOP 约定（OpenCV y 向下）、行主序 R、t 毫米转米、K 全部正确。
- `bowl_check_000053_000033.png`：bowl 最可见帧上，投影模型点与 mask_visib 轮廓**包围盒 1 px 内吻合**（三帧一致）；GT 点精确贴合碗沿。
  （注：scene 49 frame 1 的碗为玻璃材质难以目视辨认，曾引起怀疑，经最可见帧+mask 双重验证排除疑虑。）

## 5. 格式确认（写入 ycbv_bop.py 实现依据）

- 深度：16-bit PNG，`米 = 原始值 × 0.1 × 1e-3`；0 = 无效。**从 scene_camera.json 逐帧读取 depth_scale**。
- GT：`cam_R_m2c` 行主序 9 元素；`cam_t_m2c` 毫米；实例顺序 = gt_id（mask 文件名 `{im_id:06d}_{gt_id:06d}.png`）。
- 图像扩展名：rgb 与 depth 均为 **.png**。
- models_fine（高精度网格，781M）将用于 Phase 2 ICP；models（简化）用于对应点/评测采样。
- `visib_fract` 字段可用 → Phase 5 遮挡分层采样的现成依据。

## 6. 过程记录与修正

- 验证脚本初版存在"空转通过"缺陷（要求单帧同时含两个目标物体，实际不存在此类帧，roundtrip/overlay 被静默跳过却报 PASS）——已修复为按物体独立采样后重跑。教训：**验证逻辑本身必须防"零样本通过"**。
- 过程中 2 处小 bug（WindowsPath 误包 list、JSON 字符串键格式化）已修复，最终脚本入库可复现。

## 7. 状态

- Phase 1 数据获取与验证：**完成**。
- 未进入 Phase 1 的接口实现（`ycbv_bop.py`），未进入 Phase 2；未安装 PyTorch/CUDA；未触碰 3090。
