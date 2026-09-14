# WINDOWS — Windows 机器执行路线（WSL2 主路径，Stage A）

> 背景：3090 所在机器 **Linux 侧磁盘不足**，Docker 基础镜像（10–20GB）放不下 →
> 执行路线改为 **Windows + WSL2**。WSL2 是 FoundationPose 在 Windows 上唯一的
> 成熟路线（官方仅支持 Linux；社区验证 workaround = issue #148）；Windows 原生
> 路线（VS 编译 pytorch3d/nvdiffrast/mycpp，无官方 wheel）**不采用**——脆弱且无先例。
>
> 诚实声明：WSL2 = 社区验证路线，非官方支持；**smoke gate 是最终裁决**——
> RUN_SMOKE_TEST.sh 全绿才允许进入 EXP-013。

## 方案

```text
Windows（3090 机器的 Windows 系统）
  ├── NVIDIA Windows 驱动（WSL CUDA 直通——不需要在 WSL 装显卡驱动）
  ├── WSL2 Ubuntu（用户级隔离：与 Windows 及其他用户的依赖天然隔离，替代 Docker 的隔离作用）
  │     ├── miniconda + conda env r3p-fp（python 3.11 + torch cu124 + conda nvcc 12.4）
  │     ├── 本仓库（含 delivery/foundationpose_3090/，.sh 脚本在 WSL 内原样运行）
  │     └── 官方 FoundationPose checkout（commit 钉死）+ checkpoints
  └── RUN_ON_WINDOWS.ps1（PowerShell 引导器：doctor/install/check_env/prepare_data/smoke/exp013/collect）
```

- 相比 Docker 路线**去掉 10–20GB 基础镜像**；脚本不重写（WSL 内就是 Ubuntu）。
- 4 个 GPU 侧脚本已内置 WSL 识别（`WSL_DISTRO_NAME` → 自动走原生，跳过 Docker re-exec）。

## 空间预估（落在本仓库所在盘的 WSL VHDX 内）

| 项 | 预估 |
| --- | --- |
| WSL2 Ubuntu 发行版（VHDX） | 1–2 GB |
| conda env `r3p-fp`（torch cu124 安装后含自带 CUDA 库） | 6–8 GB |
| conda nvcc 12.4 最小工具链（编译 + nvdiffrast 运行期 JIT） | 1–2 GB |
| checkpoints（refiner + scorer） | 1–2 GB |
| 本仓库 + 最小数据 + 输出 | < 0.3 GB |
| **合计** | **≈ 10–15 GB（典型 ~12 GB）** |

第一步 `doctor` 会检查所在盘可用空间（建议 ≥25GB）；空间不足时把 WSL 发行版
迁移到大盘（`wsl --export` / `wsl --import`，或安装时指定位置）。

## 前置条件

- Windows 10 22H2 / Windows 11；**NVIDIA Windows 驱动**为较新版本（支持 WSL CUDA）
- 管理员权限（首次安装 WSL 需要，可能要求重启）

## 执行顺序（PowerShell，逐行复制；说明在行尾 # 后）

```powershell
cd $HOME\robot-3d-perception                                                          # 1. 进入仓库根（U 盘整体拷到 Windows 用户目录）
wsl --install -d Ubuntu                                                              # 2. 仅首次：装 WSL2 Ubuntu（管理员；可能要求重启）
powershell -ExecutionPolicy Bypass -File delivery\foundationpose_3090\RUN_ON_WINDOWS.ps1 doctor        # 3. 体检：驱动/WSL/CUDA 直通/磁盘空间
git clone https://github.com/NVlabs/FoundationPose.git $HOME\FoundationPose          # 4. 克隆官方 FP（仅官方源）
powershell -ExecutionPolicy Bypass -File delivery\foundationpose_3090\RUN_ON_WINDOWS.ps1 install       # 5. WSL 内装 miniconda + r3p-fp 环境（含 conda nvcc；safe-fail）
# 6. 下载官方 checkpoints（1-2GB，仅官方 Google Drive，⏳ 文件名见 DOWNLOAD_WEIGHTS.md；>=1GB 先报批）放到 $HOME\FoundationPose\weights\
powershell -ExecutionPolicy Bypass -File delivery\foundationpose_3090\RUN_ON_WINDOWS.ps1 check_env     # 7. 环境复查（应全部 PASS）
powershell -ExecutionPolicy Bypass -File delivery\foundationpose_3090\RUN_ON_WINDOWS.ps1 prepare_data  # 8. 数据完整性 + 单位守卫
powershell -ExecutionPolicy Bypass -File delivery\foundationpose_3090\RUN_ON_WINDOWS.ps1 smoke         # 9. 单帧 smoke gate（frame 620）
# 10. 目检 outputs\phase4_foundationpose\smoke_test\overlay_000050_000620.png（GT 绿 / 预测红）；PASS → 等待 Stage B 授权
powershell -ExecutionPolicy Bypass -File delivery\foundationpose_3090\RUN_ON_WINDOWS.ps1 exp013 -Unlock  # 11. EXP-013 正式 5 帧（Stage B，须 $env:CONFIRM_EXP013='YES'）
powershell -ExecutionPolicy Bypass -File delivery\foundationpose_3090\RUN_ON_WINDOWS.ps1 collect       # 12. 汇集 delivery_back/ 拷回轻薄本
```

## 路线对照

| 路线 | 空间 | 状态 |
| --- | --- | --- |
| **Windows + WSL2（本文件）** | ≈10–15 GB | **主路径**（3090 Linux 空间不足后的替换方案） |
| Linux + Docker（DOCKER.md） | ≈12–23 GB | 备选（Linux 空间恢复时可回退；脚本仍支持） |
| Linux conda 原生（INSTALL.sh, USE_DOCKER=0） | ≈8–12 GB | 备选 |
| Windows 原生（无 WSL） | – | **不采用**（无官方支持，编译链无先例） |

## 红线（与 README_3090.md §6 相同）

不修改 FP 算法（API 不匹配只改 `src/r3p/foundationpose/runtime.py`）；GT 零参与
inference；不用 mock 冒充真实结果；原始 BOP 数据只读；权重仅官方源；≥1GB 下载先报批。
