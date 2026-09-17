#!/usr/bin/env bash
# 诊断：打印 import estimater 的完整报错链（3090 离线环境）
set -uo pipefail
source ~/miniconda3/etc/profile.d/conda.sh
conda activate r3p-fp
cd /mnt/e/robot-3d-perception
python - <<'PYEOF'
import sys, traceback
sys.path.insert(0, '/mnt/e/FoundationPose')
print('python:', sys.version.split()[0])
print('--- imports one by one ---')
for mod in ('torch', 'pytorch3d', 'nvdiffrast', 'nvdiffrast.torch', 'trimesh', 'open3d', 'pandas', 'omegaconf', 'iopath'):
    try:
        __import__(mod)
        print('OK  ', mod)
    except Exception as e:
        print('FAIL', mod, '->', repr(e))
print('--- import estimater (full traceback) ---')
try:
    import estimater
    print('IMPORT OK')
except Exception:
    traceback.print_exc()
PYEOF
