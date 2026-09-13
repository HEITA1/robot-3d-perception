#!/usr/bin/env bash
# RUN_SMOKE_TEST — 单帧 runtime gate（obj5 / scene 50 / frame 620）。
# 目的：验证 FoundationPose 真实 runtime 在 3090 上可用（imports/checkpoint/register）。
# 输出：outputs/phase4_foundationpose/smoke_test/（is_smoke=true，不是 benchmark）。
# Gate：全部通过才打印 READY FOR EXP-013。
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
FP_REPO_ROOT="${FP_REPO_ROOT:-$HOME/FoundationPose}"
FP_CHECKPOINT_DIR="${FP_CHECKPOINT_DIR:-$FP_REPO_ROOT/weights}"
export FP_REPO_ROOT FP_CHECKPOINT_DIR
PYTHON="${R3P_FP_PYTHON:-python}"

echo "[1/2] 环境门控（必须全 PASS——smoke 不接受降级）"
"$PYTHON" scripts/foundationpose_env_check.py --config configs/fp_exp013.yaml \
  --fp-repo "$FP_REPO_ROOT" --checkpoint-dir "$FP_CHECKPOINT_DIR"

echo "[2/2] 单帧 smoke（frame 620；GT pose 零参与 inference）"
cd "$REPO_ROOT"
"$PYTHON" scripts/run_foundationpose_exp013.py --backend foundationpose --smoke \
  --fp-repo "$FP_REPO_ROOT" --checkpoint-dir "$FP_CHECKPOINT_DIR"

SMOKE_DIR="$REPO_ROOT/outputs/phase4_foundationpose/smoke_test"
[ -f "$SMOKE_DIR/manifest.json" ] || { echo "[SMOKE][FATAL] 未生成 manifest.json"; exit 1; }
"$PYTHON" - "$SMOKE_DIR" <<'EOF'
import json, sys
m = json.load(open(sys.argv[1] + "/manifest.json", encoding="utf-8"))
assert m["is_smoke"] is True and m["gt_pose_usage"] == "evaluation_only"
ok = m["summary"]["n_success"] == m["summary"]["n_frames"] == 1
print("SMOKE RESULT:", "PASS — READY FOR EXP-013 (待用户授权 Stage B)"
      if ok else f"SMOKE REGISTERED but ADD 未达标: {m['summary']} "
      "(runtime 可用；是否继续由用户判断——不达标不是 bundle 故障)")
print(f"runtime_s={m['frames'][0]['runtime_s']} repo_commit={m['foundationpose_repo_commit']}")
EOF
echo "人工目检 overlay：$SMOKE_DIR/overlay_000050_000620.png（GT 绿 / 预测红）"
