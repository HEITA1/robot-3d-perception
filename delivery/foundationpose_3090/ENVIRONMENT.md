# ENVIRONMENT — 3090 环境要求（Stage A 审计版）

> 依据 `docs/PHASE4_PREFLIGHT.md`（对官方 README/requirements/environment.yml 的源码级审计）。
> 标 ⏳ 的字段只能在 3090 上实测（CHECK_ENV.sh 输出 `env_manifest.txt`）。

## Required

| 组件 | 要求 | 备注 |
| --- | --- | --- |
| OS | Linux（Ubuntu） | 官方开发/测试平台；Windows 仅社区 WSL workaround（issue #148），不采用 |
| GPU | NVIDIA，≥12–16GB 显存安全 | 3090 24GB 预期充裕（社区实证 16GB 可跑，issue #293）；⏳ 实际型号/driver |
| driver | ≥ CUDA 构建要求 | ⏳ `nvidia-smi` |
| CUDA | 与 PyTorch 构建匹配（官方建议 cu124 wheel） | 编译 pytorch3d/nvdiffrast 需 nvcc/CUDA_HOME；⏳ `nvcc --version` |
| Python | **3.11**（官方 environment.yml，conda-forge） | 独立 env `r3p-fp`；**不得动轻薄本的 `r3p` env（也不存在于 3090）** |
| PyTorch | CUDA 构建（cu124 index，官方 requirements 头注建议） | ⏳ 实装版本 |
| gcc/g++ | 源码编译 pytorch3d/nvdiffrast/mycpp 必需 | ⏳ 版本与 CUDA 匹配性 |
| cmake / ninja | 同上 | conda-forge 可提供 |
| nvdiffrast | CUDA 光栅化（`RasterizeCudaContext`，无头，无需 X/EGL） | 源码编译 |
| PyTorch3D | 源码编译（nvcc↔torch CUDA 必须匹配） | 失败→按 official README 排查，禁止乱试版本 |
| Kaolin / mycuda | **不需要**（仅 model-free 路线需要；本项目 model-based register） | |
| FoundationPose | 官方 `NVlabs/FoundationPose` checkout（commit 执行时钉死并记录） | 额外：trimesh 等 requirements.txt 依赖 |

## Isolation

- conda env：**`r3p-fp`**（新建；项目自身以 `pip install -e ".[dev]"` 装入该 env）。
- 不修改、不复用任何既有 conda 环境（轻薄本的 `r3p` 环境与此无关）。

## Version pinning policy

- Python 3.11 / torch cu124 index / 官方 requirements.txt 是唯一的版本来源；
  **INSTALL.sh 不做版本搜索或自动降级**——任何编译失败 = 停止并报告
  （⏳ 3090 上的真实组合以 CHECK_ENV 输出为准）。

## 已知风险（来自 Preflight §8）

- nvcc ↔ torch CUDA 不匹配是最高概率失败点 → 官方推荐 docker 备选
  （`wenbowen123/foundationpose`），如 conda 路线失败由用户决策切换（不在本 Bundle 自动切换）。
