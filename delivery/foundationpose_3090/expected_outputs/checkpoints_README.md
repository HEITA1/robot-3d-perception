# checkpoints/ — 官方权重（✅ 已下载入包 2026-09-14，离线校验通过）

> 2026-09-14：用户手动经 Google Drive 下载并放入本目录；已离线校验（torch.load 通过：
> refiner=17M 参数 state_dict、scorer=含 model/optimizer 训练快照；文件名与 estimater
> 硬编码的 `weights/<run_name>/model_best.pth` + `config.yml` 完全一致）。sha256 见
> 本目录 `checkpoints_sha256.txt`。最终完整性以 3090 smoke gate 的 checkpoint 加载为准。

## 官方唯一来源（NVlabs/FoundationPose README 原文链接）

```text
https://drive.google.com/drive/folders/1DFezOAD0oD1BblsXVxqDsl8fj0qzB82i
```

需要的两个子目录（其余不用下）：

```text
2023-10-28-18-33-37/     # refiner
2024-01-11-20-02-45/     # scorer
```

## 已就位结构（3090 上由 RUN_ON_WINDOWS.ps1 install 自动复制到 E:\FoundationPose\weights\）

A. 在有网环境用 gdown 直接下到本目录（保留两个时间戳子目录结构）：

```bash
pip install gdown
python -m gdown --folder "https://drive.google.com/drive/folders/1DFezOAD0oD1BblsXVxqDsl8fj0qzB82i" -O offline_packages/checkpoints/
```


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
