# patches/ — 说明

**本目录有意为空（无补丁）。**

- FoundationPose 官方仓库**不做任何修改**（不 fork 核心算法、不打 patch）；
  3090 上按官方 commit 原样使用。
- 与本项目的全部接线下沉在仓库内：`src/r3p/foundationpose/runtime.py`
  （官方 estimater 的最小包装：惰性导入 + mesh 一次性 mm→m + register 调用）。
  若官方 API 与审计 commit 不一致，**只允许改这一个文件**并记录新 commit。
- 如未来确需补丁（例如官方 bug 修复），必须：单独提案 → 记录 diff 与理由 →
  放入本目录并更新 MANIFEST.md。
