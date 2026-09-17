# DATA_MANIFEST — 需要手动拷贝到 3090 的最小 BOP 数据（EXP-013）

> 原始 BOP 数据**只读**。放到 3090 仓库同结构路径（`<repo>/data/ycbv/...`）。
> 除下表外**什么都不需要**（其余 11 个 scene、其余 20 个模型、outputs、data_synth 均不需要）。

## 必须拷贝（约 32 个小文件 + 1 个 mesh ≈ 8MB）

相对 `<repo>/data/ycbv/`：

```text
dataset_info.md                                  # 物体名称表——数据集接口必需（缺它 YcbvBopDataset 直接报错）

models/obj_000005.ply                            # obj5 mesh（mm；adapter 在运行时 ×1e-3 转米，恰好一次）
models/obj_000005.png                            # obj5 纹理（6.7MB）——FP 加载 mesh 时必需，缺它 FileNotFoundError
models/models_info.json                          # 官方 diameter（196.463mm → 阈值 19.65mm）

test/000050/scene_camera.json                    # 逐帧内参 K + depth_scale=0.1
test/000050/scene_gt.json                        # GT pose——仅评测端 + mask gid 解析；绝不进入 inference
test/000050/rgb/000620.png                       # ┐
test/000050/rgb/000653.png                       # │
test/000050/rgb/000721.png                       # ├ 5 帧冻结帧（EXP-013 协议）
test/000050/rgb/001044.png                       # │
test/000050/rgb/001113.png                       # ┘
test/000050/depth/000620.png                     # ┐
test/000050/depth/000653.png                     # │
test/000050/depth/000721.png                     # ├ raw uint16（米制换算：raw×0.1×1e-3，在数据集边界一次完成）
test/000050/depth/001044.png                     # │
test/000050/depth/001113.png                     # ┘
test/000050/mask_visib/000620_000002.png         # ┐ obj5 的实例 gid=2（scene 50 全 5 帧一致，已实测）
test/000050/mask_visib/000653_000002.png         # │ oracle mask_visib（声明性受控条件）
test/000050/mask_visib/000721_000002.png         # │
test/000050/mask_visib/001044_000002.png         # │
test/000050/mask_visib/001113_000002.png         # ┘
```

## 可选（建议但非必需）

```text
test/000050/mask_visib/000620_*.png  等其余实例 mask   # 很小；拷整帧的 mask 免去按 gid 挑选
test/000050/scene_gt_info.json                        # visib_fract 元数据（数据集接口兼容读取）
```

## 不需要拷贝

- 其余 11 个 scene / 其余 20 个模型 / 训练集
- `outputs/`、`data_synth/`、任何实验产物
- conda env、venv、任何权重（权重单独按 DOWNLOAD_WEIGHTS.md 在 3090 下载）
- FoundationPose 源码（在 3090 上按 README 步骤 3 官方克隆）

## 单位契约（⚠️ 历史 bug 防线，勿破坏）

- **depth**：BOP raw(uint16) × depth_scale(0.1) × 1e-3 = 米——在 `YcbvBopDataset`
  数据边界**恰好一次**；项目字段到达 adapter 时**已经是米**，禁止二次转换
  （Phase 4-B 曾实抓 double-conversion bug：0.8m → 8e-5m，meter-band 断言当场拦截）。
- **mesh**：PLY 文件为 mm；运行时 `FoundationPoseRuntime` 加载后 **×1e-3 恰好一次**
  并断言 meter band（`assert_mesh_units_plausible`）。
- `PREPARE_DATA.sh` 会在 3090 上对 5 帧执行上述单位断言（CPU 即可）。
