# checkpoints/ — 官方权重（⏳ PENDING：本网络无法访问 Google Drive）

> 2026-09-14 实测：本轻薄本网络连不上 `drive.google.com`（连接超时），gdown 失败。
> 权重（约 1–2GB）需要你在**能访问 Google Drive 的网络**（或代理）下下载后放进本目录。

## 官方唯一来源（NVlabs/FoundationPose README 原文链接）

```text
https://drive.google.com/drive/folders/1DFezOAD0oD1BblsXVxqDsl8fj0qzB82i
```

需要的两个子目录（其余不用下）：

```text
2023-10-28-18-33-37/     # refiner
2024-01-11-20-02-45/     # scorer
```

## 放置方式（二选一）

A. 在有网环境用 gdown 直接下到本目录（保留两个时间戳子目录结构）：

```bash
pip install gdown
python -m gdown --folder "https://drive.google.com/drive/folders/1DFezOAD0oD1BblsXVxqDsl8fj0qzB82i" -O offline_packages/checkpoints/
```

B. 浏览器手动下载后，把两个时间戳文件夹拖进本目录。

## 3090 上的最终位置（INSTALL / RUN 脚本按此约定）

```text
E:\FoundationPose\weights\2023-10-28-18-33-37\...
E:\FoundationPose\weights\2024-01-11-20-02-45\...
```

（即 FP checkout 根下的 `weights/`；`RUN_ON_WINDOWS.ps1 -CheckpointDir` 可覆盖。）

## 校验

官方未发布 checksum → 下载完成后在本目录记录：

```bash
find . -type f -exec sha256sum {} \; > checkpoints_sha256.txt
```

完整性最终以 smoke gate 的 checkpoint 加载为准。
