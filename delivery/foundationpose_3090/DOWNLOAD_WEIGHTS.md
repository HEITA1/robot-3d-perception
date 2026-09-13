# DOWNLOAD_WEIGHTS — 官方 checkpoint 清单（仅官方来源）

> 来源：`docs/PHASE4_PREFLIGHT.md` §1（对官方 README 的审计）。
> **禁止**：任何第三方镜像 / HuggingFace 转载 / 未验证 fork / 网盘转载。

## Checkpoints（2 个，均为官方 Google Drive）

| 角色 | 官方标识 | 目标目录（3090） | 文件名 | 大小 | sha256 |
| --- | --- | --- | --- | --- | --- |
| refiner | `2023-10-28-18-33-37` | `<FP_REPO_ROOT>/weights/` | ⏳ PENDING_3090（以官方 Drive 内实际文件名为准） | ⏳ PENDING_3090（GB 级，下载时实测） | ⏳ 官方未发布；下载后本机计算（命令见下） |
| scorer | `2024-01-11-20-02-45` | `<FP_REPO_ROOT>/weights/` | ⏳ PENDING_3090 | ⏳ PENDING_3090 | ⏳ 同上 |

- 来源页：官方 README 的 "Download checkpoints" 链接
  （仓库 <https://github.com/NVlabs/FoundationPose> → README）。
- 目录约定以 checkout 后的官方 README 现场说明为准（Preflight 审计为 `weights/`；
  若你 checkout 的 commit 指示不同目录，以官方为准并把实际路径记入 manifest）。
- Google Drive 在 3090 可能离线/受限 → **轻薄本下载 → U 盘/scp 中转**（项目既有决策）；
  下载清单（≈2 个文件，GB 级）按项目规则**先报批**。

## 下载后在本机记录（3090 上执行）

```bash
sha256sum <FP_REPO_ROOT>/weights/* | tee -a delivery_back/weights_sha256.txt
du -sh <FP_REPO_ROOT>/weights/* >> delivery_back/weights_sha256.txt
```

## 验证方式

- 无官方 checksum 可比对 → 验证手段 = **smoke gate**：`RUN_SMOKE_TEST.sh` 中
  estimater 加载 checkpoint 失败会显式报错（不做静默降级）。
- `CHECK_ENV.sh` 第 14 项检查两个 checkpoint 目录存在（PASS/FAIL）；
  完整性以 smoke 加载为准。
