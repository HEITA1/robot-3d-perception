"""Phase 1 minimal real-data demo: YCB-V frame -> point cloud -> GT overlay PNG.

Usage (from the repo root)::

    python -m r3p.experiments.run_ycbv_demo --scene 50 --frame 620

Pipeline: load one BOP YCB-V frame via YcbvBopDataset -> RGB-D -> point cloud
(pinhole deprojection) -> load GT poses -> transform model points into the
camera frame (SE(3)) -> project onto the image -> save a 3-panel PNG
(rgb + GT overlay | depth | 3D point cloud + transformed models).

This is the Phase 1 exit-criteria demonstration: real RGB-D in, correct point
cloud and coordinate transform out, visually verifiable.
"""

from __future__ import annotations

import argparse
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402

from ..datasets.ycbv_bop import YcbvBopDataset  # noqa: E402
from ..geometry.camera import deproject  # noqa: E402
from ..geometry.se3 import apply as apply_T  # noqa: E402

COLORS = {5: "tab:green", 13: "tab:orange"}


def run(data_root: str, scene_id: int, im_id: int, obj_ids, out_path: str) -> Path:
    dataset = YcbvBopDataset(
        data_root, obj_ids=obj_ids, scene_ids=[scene_id], require_objects=False, load_masks=False
    )
    matches = [i for i, (s, im) in enumerate(dataset.frames) if int(im) == int(im_id)]
    if not matches:
        available = sorted(int(im) for _, im in dataset.frames)
        raise SystemExit(f"frame {im_id} not in scene {scene_id} (available: {available[:5]}... {available[-5:]})")
    obs = dataset[matches[0]]

    cloud = deproject(obs["K"], obs["depth"])
    log_lines = [f"frame {obs['frame_id']}: scene={obs['scene_id']} im={obs['im_id']} "
                 f"valid_depth_px={len(cloud)} depth_scale={obs['depth_scale']}"]

    fig = plt.figure(figsize=(16, 5), dpi=150)

    ax1 = fig.add_subplot(1, 3, 1)
    ax1.imshow(obs["rgb"])
    for oid, T in obs["gt_poses"].items():
        P_cam = apply_T(T, obs["model_points"][oid])
        uv = obs["K"] @ P_cam.T
        u = uv[0] / uv[2]
        v = uv[1] / uv[2]
        ax1.scatter(u, v, s=0.5, c=COLORS.get(oid, "red"), label=f"obj {oid} ({dataset.obj_names[oid]})")
        log_lines.append(
            f"obj {oid:02d} ({dataset.obj_names[oid]}): t_cam = "
            f"[{T[0, 3]:+.3f}, {T[1, 3]:+.3f}, {T[2, 3]:+.3f}] m  "
            f"(model origin in camera frame)"
        )
    ax1.legend(loc="upper right", fontsize=8)
    ax1.set_title("RGB + GT model points (projected)")

    ax2 = fig.add_subplot(1, 3, 2)
    im2 = ax2.imshow(obs["depth"], cmap="viridis")
    fig.colorbar(im2, ax=ax2, shrink=0.8)
    ax2.set_title("depth (m)")

    ax3 = fig.add_subplot(1, 3, 3, projection="3d")
    sub = cloud[:: max(1, len(cloud) // 40000)]
    ax3.scatter(sub[:, 0], sub[:, 1], sub[:, 2], s=0.5, c=sub[:, 2], cmap="viridis")
    for oid, T in obs["gt_poses"].items():
        P_cam = apply_T(T, obs["model_points"][oid])
        ax3.scatter(P_cam[::4, 0], P_cam[::4, 1], P_cam[::4, 2], s=1, c=COLORS.get(oid, "red"))
    ax3.set_box_aspect((1, 1, 1))
    ax3.set_title("camera-frame point cloud + GT models")

    fig.suptitle(f"Phase 1 demo — YCB-V {obs['frame_id']}")
    fig.tight_layout()
    out = Path(out_path)
    out.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out)
    plt.close(fig)

    for line in log_lines:
        print(line, flush=True)
    print(f"saved: {out}")
    return out


def main(argv=None) -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data-root", default="data/ycbv")
    parser.add_argument("--scene", type=int, default=50)
    parser.add_argument("--frame", type=int, default=620)
    parser.add_argument("--obj-ids", type=int, nargs="+", default=[5, 13])
    parser.add_argument("--out", default="outputs/ycbv_demo/demo.png")
    args = parser.parse_args(argv)
    run(args.data_root, args.scene, args.frame, args.obj_ids, args.out)


if __name__ == "__main__":
    main()
