"""Visualization helpers (CPU-friendly, headless-safe).

``save_pose_report_png`` builds a static matplotlib figure (depth image, scene
point cloud, model overlay GT vs estimate) and works without a display —
this is the default path for experiments. ``show_point_cloud_open3d`` is an
optional interactive viewer (requires open3d + a GUI); Phase 1 will use it
for manual point-cloud inspection.
"""

from __future__ import annotations

from pathlib import Path

import matplotlib

matplotlib.use("Agg")  # headless-safe; must run before pyplot import
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402

from ..geometry.camera import deproject  # noqa: E402
from ..geometry.se3 import apply as apply_T  # noqa: E402


def save_pose_report_png(path, obs: dict, T_est: np.ndarray | None = None, title: str = "") -> Path:
    """Static 3-panel report: depth image | scene point cloud | model GT vs estimate."""
    depth = np.asarray(obs["depth"])
    K = obs["K"]
    obj = next(iter(obs["gt_poses"]))
    T_gt = obs["gt_poses"][obj]
    model = obs["model_points"][obj]

    fig = plt.figure(figsize=(15, 5), dpi=150)
    if title:
        fig.suptitle(title)

    ax1 = fig.add_subplot(1, 3, 1)
    im = ax1.imshow(depth, cmap="viridis")
    ax1.set_title("depth (m)")
    fig.colorbar(im, ax=ax1, shrink=0.8)

    cloud = deproject(K, depth)
    if len(cloud) > 20000:  # keep plotting cheap
        sel = np.random.default_rng(0).choice(len(cloud), 20000, replace=False)
        cloud = cloud[sel]
    ax2 = fig.add_subplot(1, 3, 2, projection="3d")
    ax2.scatter(cloud[:, 0], cloud[:, 1], cloud[:, 2], s=1, c=cloud[:, 2], cmap="viridis")
    ax2.set_title(f"scene point cloud (n={len(cloud)})")

    ax3 = fig.add_subplot(1, 3, 3, projection="3d")
    p_gt = apply_T(T_gt, model)
    ax3.scatter(p_gt[:, 0], p_gt[:, 1], p_gt[:, 2], s=1, c="tab:green", label="GT")
    if T_est is not None:
        p_est = apply_T(T_est, model)
        ax3.scatter(p_est[:, 0], p_est[:, 1], p_est[:, 2], s=1, c="tab:red", label="estimate")
    ax3.legend(loc="upper left")
    ax3.set_title("model points: GT vs estimate")

    for ax in (ax2, ax3):
        ax.set_box_aspect((1, 1, 1))
    fig.tight_layout()

    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(path)
    plt.close(fig)
    return path


def show_point_cloud_open3d(clouds_with_colors) -> None:
    """Optional interactive viewer; requires open3d and a display.

    Args: iterable of (points (N, 3) meters, RGB color in [0, 1]).
    """
    import open3d as o3d  # optional dependency, imported lazily

    geoms = []
    for pts, color in clouds_with_colors:
        pcd = o3d.geometry.PointCloud()
        pcd.points = o3d.utility.Vector3dVector(np.asarray(pts, dtype=np.float64))
        pcd.paint_uniform_color(color)
        geoms.append(pcd)
    o3d.visualization.draw_geometries(geoms)
