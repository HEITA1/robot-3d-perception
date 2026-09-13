#!/usr/bin/env bash
# PREPARE_DATA — 在 3090 上验证 EXP-013 最小数据（CPU 即可，无需 GPU）。
# 只读校验：不修改任何 BOP 原始文件；不做单位换算产物落盘（adapter 运行时处理）。
# 校验内容：文件齐全 + 数据集可加载 5 帧 + 深度/网格单位守卫（米制 meter band）。
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
# Docker 隔离（默认）：re-exec 进容器（数据通过 /work 挂载可见；本步骤纯 CPU）
if [ "${USE_DOCKER:-1}" = "1" ] && [ "${INSIDE_CONTAINER:-0}" != "1" ]; then
  IMAGE="${R3P_FP_IMAGE:-r3p-fp:exp013}"
  exec docker run --rm -e INSIDE_CONTAINER=1 -v "$REPO_ROOT":/work -w /work \
    "$IMAGE" bash "delivery/foundationpose_3090/$(basename "${BASH_SOURCE[0]}")"
fi
PYTHON="${R3P_FP_PYTHON:-python}"

echo "[1/2] 文件齐全性（DATA_MANIFEST.md 必须项）"
missing=0
while IFS= read -r f; do
  if [ ! -f "$REPO_ROOT/$f" ]; then echo "MISSING: $f"; missing=1; fi
done <<'EOF'
data/ycbv/dataset_info.md
data/ycbv/models/obj_000005.ply
data/ycbv/models/models_info.json
data/ycbv/test/000050/scene_camera.json
data/ycbv/test/000050/scene_gt.json
data/ycbv/test/000050/rgb/000620.png
data/ycbv/test/000050/rgb/000653.png
data/ycbv/test/000050/rgb/000721.png
data/ycbv/test/000050/rgb/001044.png
data/ycbv/test/000050/rgb/001113.png
data/ycbv/test/000050/depth/000620.png
data/ycbv/test/000050/depth/000653.png
data/ycbv/test/000050/depth/000721.png
data/ycbv/test/000050/depth/001044.png
data/ycbv/test/000050/depth/001113.png
data/ycbv/test/000050/mask_visib/000620_000002.png
data/ycbv/test/000050/mask_visib/000653_000002.png
data/ycbv/test/000050/mask_visib/000721_000002.png
data/ycbv/test/000050/mask_visib/001044_000002.png
data/ycbv/test/000050/mask_visib/001113_000002.png
EOF
[ "$missing" = "0" ] || { echo "[PREPARE_DATA][FATAL] 数据不齐——对照 DATA_MANIFEST.md 补拷。"; exit 1; }

echo "[2/2] 数据集加载 + 单位守卫（5 帧；米制 meter band 断言）"
cd "$REPO_ROOT"
"$PYTHON" - <<'EOF'
import sys
from pathlib import Path
sys.path.insert(0, str(Path("src").resolve()))
from r3p.datasets.ycbv_bop import YcbvBopDataset
from r3p.foundationpose import AdapterConfig, FoundationPoseAdapter

ds = YcbvBopDataset("data/ycbv", obj_ids=(5,), scene_ids=[50], load_masks=True)
by_im = {int(ds.frames[i][1]): i for i in range(len(ds))}
adapter = FoundationPoseAdapter(AdapterConfig(
    data_root="data/ycbv", obj_id=5, mesh_relpath="models/obj_000005.ply",
    depth_scale=0.1, diameter_m=0.196463,
))
for im in (620, 653, 721, 1044, 1113):
    obs = ds[by_im[im]]
    inp = adapter.prepare_input(obs, obj_id=5)
    problems = adapter.validate_input(inp)
    assert not problems, f"frame {im}: {problems}"
    print(f"frame {im}: RGB{inp.rgb.shape} depth[m] p50={float(inp.depth_m[inp.depth_m>0].mean()):.3f} "
          f"mask_px={int(inp.mask.sum())} mesh_m pts={inp.mesh_m.shape[0]} — units OK")
print("PREPARE_DATA PASS: 5/5 frames load, unit guards green (no conversion written).")
EOF
echo "== 数据就绪。下一步：RUN_SMOKE_TEST.sh（需要 GPU + checkpoints）=="
