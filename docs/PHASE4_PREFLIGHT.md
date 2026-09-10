# Phase 4 Preflight Report — FoundationPose Environment Audit & Minimal Baseline Design

> 日期：2026-09-11
> 性质：环境审计 + 可行性调查 + 实验设计。**未实现、未训练、未大下载、未 push。**
> 调查方式：官方 README / requirements.txt / environment.yml / run_ycb_video.py / estimater.py /
> datareader.py 源码级核对（GitHub API 拉取官方 main 分支），+ 本机实测。

---

## 1. Official implementation

| 项 | 值 | 证据 |
| --- | --- | --- |
| 官方仓库 | `NVlabs/FoundationPose`（CVPR 2024 Highlight，BOP leaderboard #1 model-based 2024/03） | README |
| License | **NVIDIA Source Code License — non-commercial**，仅限研究/评测用途（对本项目合规；不可商用声明需保留） | LICENSE |
| 版本 | main 分支（无 tag 发布惯例；EXP 记录 commit hash 于执行时固定） | repo |
| Python | **3.11**（environment.yml，conda-forge） | environment.yml |
| PyTorch | CUDA 构建，官方建议 cu124 index（匹配驱动） | requirements.txt 头注 |
| 编译依赖 | **nvdiffrast + PyTorch3D 源码编译（需 nvcc/CUDA_HOME）**；`build_all_conda.sh` 构建 mycpp 扩展；conda-forge 提供 cmake/ninja/eigen/boost-cpp/pybind11/cxx-compiler | README + environment.yml |
| 可选 | Kaolin（**仅 model-free** 需要——本项目 model-based 路线不需要）；mycuda（仅 model-free/NeRF） | README |
| 权重 | 两个 checkpoint：refiner `2023-10-28-18-33-37`、scorer `2024-01-11-20-02-45`，Google Drive → `weights/`（大小待下载时实测，预估 GB 级） | README |
| 额外数据 | demo data（可选）；大规模训练数据（**不需要**——我们只推理） | README |
| Docker | 官方推荐路径：`wenbowen123/foundationpose` 镜像；4090 级 GPU 用 `shingarey/foundationpose_custom_cuda121`（issue #27） | README |

## 2. Environment compatibility

| Component | Current（轻薄本 / 实测） | Required | Status |
| --- | --- | --- | --- |
| OS | Windows 11（MINGW64 bash） | Linux（官方开发/测试平台；Windows 仅社区 WSL workaround issue #148） | ❌ 本机不可运行 |
| GPU | **无 NVIDIA GPU**（`nvidia-smi` 不存在，实测） | CUDA GPU（社区实证 16GB 可跑；issue #293） | ❌ 本机 BLOCKED |
| VRAM | — | ≥12–16GB 安全（3090 24GB 充裕） | 执行机满足 |
| Python | 3.11.16（r3p env）/ 3.13 base | 3.11 | ✅ 版本可得（须独立 env） |
| PyTorch | 2.13.0+cpu（r3p，Phase 3 用） | CUDA 构建（cu124/cu121） | ❌ 需独立 env + CUDA wheel |
| CUDA / nvcc | 本机无 | 编译 pytorch3d/nvdiffrast 必需（或用官方 docker 免编译） | ❌ 本机无；3090 机待审计 |
| gcc/g++/cmake | 本机 Git Bash 环境无 | 源码编译扩展必需（docker 镜像内置） | ❌ 本机无；3090 机待审计 |
| EGL/渲染 | — | nvdiffrast CUDA rasterization（`RasterizeCudaContext`，无需显示服务） | 随 CUDA 环境解决 |
| 磁盘 | D: 210GB 空闲 | 权重 1–2GB + env ~8–10GB（或 docker 镜像 10–20GB） | ✅ 充足 |
| **3090 Ubuntu 机（执行目标）** | 已知 RTX 3090 24GB + Ubuntu；**driver/CUDA/nvcc/docker 状态未知** | driver ≥ CUDA 构建要求；nvcc 或 docker | ⚠ **待审计（见 §9）** |

隔离策略（§5）：新建独立 conda env（如 `r3p-fp`），**不动 `r3p`**；优先级按 §15：
L1 官方 native conda 路线（README 现已提供完整 conda-forge 配方）→ L2 独立机器环境 →
L3 官方 docker（`wenbowen123/foundationpose`，需 3090 机有 docker+nvidia-container-toolkit）→ L4 停止上报。

## 3. Resource requirement

| 资源 | 估算 | 位置 |
| --- | --- | --- |
| 磁盘 | 权重 ~1–2GB + 独立 conda env ~8–10GB（或 docker 镜像 10–20GB）+ 输出 <1GB | 3090 机 ~10–25GB；轻薄本仅适配器代码 |
| VRAM | 社区实证 16GB 可运行（issue #293）；**3090 24GB 预期充足**（EXP-013 实测记录） | 3090 |
| RAM | 官方未注明；预期 ≤32GB | 3090 |
| Runtime | register 首跑含 JIT 编译较慢；之后每帧秒级~ tens of seconds（EXP-013 实测记录） | 3090 |
| 下载 | 权重（Google Drive，需 gdown 或手动 U 盘中转——3090 离线约束）+ repo + 依赖 wheels | 下载量 ~3–12GB，**需按预算规则报批清单** |

## 4. Dataset compatibility（BOP → FoundationPose，代码级核对）

| BOP 子集（只读） | FoundationPose 需要的形态 | 适配（官方 `datareader.py` 同款约定） |
| --- | --- | --- |
| `rgb/*.png` | color (H,W,3) RGB | 直接读取 |
| `depth/*.png` + `depth_scale=0.1` | depth (H,W) **米** | `raw × 1e-3 × 0.1`（官方 ycbv reader 同款；内部再做 erode+bilateral） |
| `scene_camera.json → cam_K` | K (3,3) | 直接读取（downscale=1） |
| `mask_visib/*.png` | ob_mask（detect_type='mask' 官方支持） | 直接读取（oracle mask，声明为受控条件，与 P2/P3 一致） |
| `models/obj_000005.ply`（mm） | mesh **米**（官方 reader `mesh.vertices *= 1e-3`） | 适配器转换后存 `outputs/phase4_foundationpose/cache/`，原始数据只读 |
| `scene_gt.json` | **estimation 不需要**（见 §5）；仅评测端 | 不进入 adapter 推理路径 |

转换产物全部写入 `outputs/phase4_foundationpose/`（gitignored），不覆盖原始数据。

## 5. Input assumptions（源码级核实，防止"偷换外部信息"）

| 输入 | 是否必需 | 模式 | 证据 |
| --- | --- | --- | --- |
| RGB | ✅ | register | `run_ycb_video.py`: `est.register(K, rgb, depth, ob_mask, ob_id, iteration=5)` |
| Depth | ✅ | register | 同上；内部 `erode_depth` + `bilateral_filter_depth` |
| 相机 K | ✅ | register | 同上 |
| **Object mesh（CAD）** | ✅（model-based） | register | `FoundationPose(model_pts, model_normals, mesh=…)`；model-free 替代需参考视图+Kaolin（不在本路线） |
| **Mask** | ✅（或 bbox / cnos 检测，官方三选一：`detect_type='box'/'mask'/'cnos'`） | register | `get_mask(..., type='mask_visib')` → **我们的 oracle mask 直接对应官方 'mask' 模式** |
| **Initial pose** | ❌ estimation 不需要 | register | `register` 从 pose 假设网格出发（`generate_random_pose_hypo` + 平移由深度质心猜测）；**需要初始位姿的是 `track_one`（tracking/refinement 模式）**，与 estimation 是两条路径 |
| Detection | mask 模式下不需要独立检测器；box/cnos 模式才需要 | register | `get_mask` 三分支 |
| GT pose | ❌ **inference 零参与（源码级证实）** | — | 公开版 `estimater.py` 中 `compute_add_err_to_gt_pose` 为**桩函数**（直接返回 −1，不读 `self.gt_pose`）；`self.gt_pose` 仅外部赋值、从未被算法读取；register 内 `set_seed(0)` 固定随机性 |

**结论**：EXP-004 采用官方 model-based register 路线 = **GT-free pose estimation**（oracle mask 为声明性受控条件，与 P2/P3 完全一致的协议口径）；"GT-initialized refinement"（`track_one`）若未来使用，必须单独立项并明确标注。

## 6. Evaluation protocol（沿用已有协议，零修改）

- Frames：obj5 / scene 50 / **620, 653, 721, 1044, 1113**（与 P2.4、P3.1-B/C/E 完全相同的子集，保证同帧可比）
- Metrics：ADD、ADD-S、trans (mm)、rot (°)——复用 `r3p.evaluation.metrics.compute_all`
- Success：obj5 `ADD < 0.1d = 19.65mm`
- Overlays：GT 绿 / prediction 红（沿用约定）；另存 RGB、depth 可视化
- 对照：同帧 P2.3-S/P2.4 Classical 数字（已有）与 P3.1-B/C 诊断（已有）

## 7. Proposed experiment（EXP-013，输出目录沿用用户命名惯例）

`outputs/phase4_foundationpose/fp_exp004_feasibility/`

- 物体：obj5 mustard_bottle（scene 50 上 5 帧）——与 P2/P3 诊断史形成 before/after 对比
- 输入条件：model-based register + oracle mask（官方 'mask' 模式）+ depth(m) + mesh(m) + K；零初始位姿、零 GT
- 记录：checkpoint hash、repo commit、env freeze（pip freeze）、逐帧 runtime、VRAM（`torch.cuda.max_memory_allocated`）、metrics、失败帧
- ⚠ **EXP 编号冲突说明**：项目日志已用至 EXP-012；用户建议的 "EXP-004" 沿用为**输出目录名**，
  `EXPERIMENT_LOG.md` 中登记为 **EXP-013**（待你确认）
- 后续（**仅设计，未获授权不执行**）：EXP-014 normal inference（更多帧/bowl）、EXP-015 initialization
  sensitivity（register vs track_one）、EXP-016 与 P2/P3 统一比较表

## 8. Risks

| 风险 | 等级 | 缓解 |
| --- | --- | --- |
| **执行机无 GPU（轻薄本）** | 确定事实 | 全部执行移至 3090 Ubuntu 机；轻薄本只写代码/适配器/报告 |
| 3090 机 driver/CUDA/nvcc/docker 未知 | 高 | §9 审计命令清单先行；按结果选 L1 conda 或 L3 docker |
| 权重在 Google Drive（3090 离线约束） | 中 | 轻薄本下载（gdown/浏览器）→ U 盘/scp 中转；清单先报批 |
| nvdiffrast/pytorch3d 源码编译失败（nvcc↔torch CUDA 不匹配） | 中 | docker 路线内置工具链（官方推荐）；或 conda-forge `cxx-compiler`+系统 CUDA |
| EGL/渲染初始化 | 低 | 官方默认 `RasterizeCudaContext`（无头 CUDA 光栅化，无需 X/EGL 显示服务） |
| mesh 单位（mm vs m） | 低 | 官方 reader 同款 `×1e-3`；适配器内断言 bbox≈[0.097,0.067,0.191]m |
| 4090+ 新架构编译问题（issue #27） | 不适用 | 3090 为 Ampere，官方主线路径覆盖 |
| 许可 | 低 | NC research-only，本项目合规；保留 LICENSE 归属声明 |
| 可复现性 | 低 | register 内 `set_seed(0)`；EXP 记录 repo commit + env freeze + 种子 |

## 9. Proposed next action

**状态：READY（有条件）**——条件是完成 3090 机审计。当前轻薄本对该路线为硬件 BLOCKED（无 GPU），
这本身就是 Preflight 的结论之一，不是阻塞项（执行机本就规划为 3090）。

**下一步（等待你的授权与 3090 机审计结果）**：

1. 在 3090 Ubuntu 机上执行并回传以下命令输出（决定 conda-native vs docker 路线）：
   ```bash
   nvidia-smi                                   # driver 版本 + CUDA capability
   nvcc --version || ls /usr/local/ | grep cuda # CUDA toolkit
   which docker && docker info | grep -i nvidia # docker + nvidia-container-toolkit
   conda --version; python --version
   df -h /home                                  # 磁盘
   free -g                                      # RAM
   ```
2. 依结果确定路线（L1 conda-native / L3 docker），我提交 **Commit B（adapter）** 与
   **Commit C（评测+可视化，CPU 可测部分）**；
3. 权重+依赖下载清单报批后，3090 机执行 **EXP-013 feasibility**（Commit D），回传结果江南评测入档。

---

## 附：EXP-013 预计记录字段（占位，执行时填写）

repo commit / env pip freeze / checkpoint 文件名+hash / object=5 scene=50 frames=5 /
mode=register(mask) / 逐帧 ADD·ADD-S·trans·rot·runtime·VRAM / success n/5 / 失败帧归因 /
与 P2.3-S 同 5 帧对照（Classical 5/5 solver、5/5 pose——同帧数字已有）
