#!/usr/bin/env bash
# COLLECT_RESULTS — 把需要拷回轻薄本的结果集中到 delivery_back/（不打包环境/数据/权重）。
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
FP4="$REPO_ROOT/outputs/phase4_foundationpose"
BACK="$REPO_ROOT/outputs/phase4_foundationpose/delivery_back"

rm -rf "$BACK"; mkdir -p "$BACK/overlays" "$BACK/logs"

copy_if_exists() { # copy_if_exists <src> <dest-name>
  if [ -e "$1" ]; then cp -r "$1" "$BACK/$2"; else echo "  (skip, 不存在: $1)"; fi
}

echo "== 收集结果 =="
copy_if_exists "$FP4/smoke_test"                          "smoke_test"
copy_if_exists "$FP4/fp_exp004_feasibility"               "exp013_fp_exp004_feasibility"
copy_if_exists "$FP4/env_manifest.txt"                    "env_manifest.txt"
copy_if_exists "$REPO_ROOT/outputs/fp_commit.txt"         "fp_commit.txt"

# 只拷 manifest/指标/overlay/日志，环境目录本身不拷（copy_if_exists 对目录取整体，
# smoke_test 与 exp013 目录内天然只含这些产物；如混入异常大文件，下面会列出）
echo "== 体积审计（>20MB 的文件会列出，不应出现）=="
find "$BACK" -type f -size +20M -print || true

echo "== SHA256 清单 =="
( cd "$BACK" && find . -type f -print0 | sort -z | xargs -0 sha256sum ) > "$BACK/SHA256SUMS"

echo "== 完成。把整个 delivery_back/ 拷回轻薄本 =="
find "$BACK" -type f | sort
