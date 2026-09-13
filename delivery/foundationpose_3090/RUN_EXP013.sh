#!/usr/bin/env bash
# RUN_EXP013 — 正式 EXP-013（5 帧，冻结协议）。默认 EXECUTION_LOCKED=true。
# 仅在用户明确进入 Stage B 时运行：需要 --unlock 且环境变量 CONFIRM_EXP013=YES。
# 参数唯一来源 = configs/fp_exp013.yaml（本脚本不重复任何协议参数）。
set -euo pipefail

EXECUTION_LOCKED=true   # Stage B 解锁时由用户改/传参；不要悄悄改掉

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
FP_REPO_ROOT="${FP_REPO_ROOT:-$HOME/FoundationPose}"
FP_CHECKPOINT_DIR="${FP_CHECKPOINT_DIR:-$FP_REPO_ROOT/weights}"
export FP_REPO_ROOT FP_CHECKPOINT_DIR
PYTHON="${R3P_FP_PYTHON:-python}"

if [ "$EXECUTION_LOCKED" = "true" ]; then
  if [ "${1:-}" != "--unlock" ] || [ "${CONFIRM_EXP013:-}" != "YES" ]; then
    echo "[EXP013] LOCKED — 正式执行需同时满足：--unlock 且 CONFIRM_EXP013=YES"
    echo "  （EXP-013 是冻结协议实验；先通过 RUN_SMOKE_TEST.sh gate 并获用户授权）"
    exit 3
  fi
fi

echo "[1/2] 环境门控（foundationpose 后端，FAIL 即停止，无回退）"
"$PYTHON" scripts/foundationpose_env_check.py --config configs/fp_exp013.yaml \
  --fp-repo "$FP_REPO_ROOT" --checkpoint-dir "$FP_CHECKPOINT_DIR"

echo "[2/2] EXP-013 正式运行（5 帧；协议全部来自 configs/fp_exp013.yaml）"
cd "$REPO_ROOT"
"$PYTHON" scripts/run_foundationpose_exp013.py --backend foundationpose \
  --fp-repo "$FP_REPO_ROOT" --checkpoint-dir "$FP_CHECKPOINT_DIR"

echo "== 完成。执行 COLLECT_RESULTS.sh 汇集回传包 =="
