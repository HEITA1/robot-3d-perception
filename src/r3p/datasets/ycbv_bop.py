"""YCB-V in BOP format (local subset: test_bop19), Phase 1.

Unit policy — BOP stores depth as uint16 scaled by a per-frame ``depth_scale``
(ycbv: 0.1, i.e. one raw unit = 0.1 mm) and translations in millimeters. All
conversion to meters happens exactly once, here, at the interface boundary:
everything leaving this module (depth, translations, model points) is meters.

Frame selection: by default only frames that contain at least one target
object are indexed (``require_objects=True``). The target objects default to
obj 5 (006_mustard_bottle, asymmetric) and obj 13 (024_bowl, rotationally
symmetric -> must be judged by ADD-S).

Observation dict (see r3p.datasets.base) extras beyond the base contract:
  scene_id / im_id  : ints identifying the frame
  depth_scale       : raw BOP scale (for debugging; depth is already meters)
  visib_fract       : per-object visible-silhouette fraction from scene_gt_info
  gt_instance_ids   : per-object gt_id, linking masks to scene_gt entries
"""

from __future__ import annotations

import json
import re
from pathlib import Path

import cv2
import numpy as np

from .base import PoseDataset
from ..geometry.se3 import make_T

MM_TO_M = 1e-3
DEFAULT_OBJ_IDS = (5, 13)


def load_obj_names(data_root: str | Path) -> dict[int, str]:
    """Parse the ``Object NN (ycb_name): [...]`` table from BOP dataset_info.md."""
    text = (Path(data_root) / "dataset_info.md").read_text(encoding="utf-8")
    names = {int(m.group(1)): m.group(2) for m in re.finditer(r"Object (\d+) \((.+?)\):", text)}
    if not names:
        raise ValueError(f"could not parse object names from {Path(data_root) / 'dataset_info.md'}")
    return names


class YcbvBopDataset(PoseDataset):
    """Local BOP-format YCB-V interface producing base-contract observations.

    Raises at __getitem__ time if a target object ever has multiple instances
    in one frame (the dict-per-object contract assumes at most one; the
    test_bop19 subset contains none).
    """

    def __init__(
        self,
        data_root: str | Path,
        split: str = "test",
        obj_ids=(5, 13),
        scene_ids=None,
        require_objects: bool = True,
        load_masks: bool = True,
        n_model_points: int | None = None,
        model_points_source: str = "vertices",
    ):
        self.data_root = Path(data_root)
        self.split = split
        self.obj_ids = tuple(int(o) for o in obj_ids)
        self.load_masks = load_masks
        self.n_model_points = n_model_points
        self.model_points_source = model_points_source

        self.obj_names = load_obj_names(self.data_root)
        unknown = [o for o in self.obj_ids if o not in self.obj_names]
        if unknown:
            raise KeyError(f"unknown obj_ids {unknown}; available: {sorted(self.obj_names)}")

        self.split_dir = self.data_root / split
        if not self.split_dir.is_dir():
            raise FileNotFoundError(f"split directory not found: {self.split_dir}")
        if scene_ids is None:
            self.scene_ids = sorted(int(p.name) for p in self.split_dir.iterdir() if p.is_dir())
        else:
            self.scene_ids = sorted(int(s) for s in scene_ids)

        self._scene_camera: dict[int, dict] = {}
        self._scene_gt: dict[int, dict] = {}
        self._scene_gt_info: dict[int, dict | None] = {}
        for scene in self.scene_ids:
            sdir = self.split_dir / f"{scene:06d}"
            self._scene_camera[scene] = json.loads((sdir / "scene_camera.json").read_text(encoding="utf-8"))
            self._scene_gt[scene] = json.loads((sdir / "scene_gt.json").read_text(encoding="utf-8"))
            info_path = sdir / "scene_gt_info.json"
            self._scene_gt_info[scene] = json.loads(info_path.read_text(encoding="utf-8")) if info_path.exists() else None

        self._index: list[tuple[int, str]] = []
        for scene in self.scene_ids:
            for im_id in sorted(self._scene_camera[scene], key=int):
                if require_objects:
                    present = {inst["obj_id"] for inst in self._scene_gt[scene][im_id]}
                    if not set(self.obj_ids) & present:
                        continue
                self._index.append((scene, im_id))
        if not self._index:
            raise RuntimeError(
                "empty frame index: no frames matched the filters "
                f"(obj_ids={self.obj_ids}, scene_ids={self.scene_ids})"
            )

        self._model_points: dict[int, np.ndarray] = {oid: self._load_model_points(oid) for oid in self.obj_ids}

    # ------------------------------------------------------------------ #
    def _load_model_points(self, obj_id: int) -> np.ndarray:
        """Model points in meters. 'vertices' = all mesh vertices (deterministic);
        'surface' = open3d uniform surface sampling to n_model_points."""
        import open3d as o3d  # lazy: not needed for json-only paths

        mesh = o3d.io.read_triangle_mesh(str(self.data_root / "models" / f"obj_{obj_id:06d}.ply"))
        if self.model_points_source == "vertices":
            pts = np.asarray(mesh.vertices, dtype=np.float64) * MM_TO_M
        elif self.model_points_source == "surface":
            n = self.n_model_points or 2000
            pcd = mesh.sample_points_uniformly(number_of_points=int(n))
            pts = np.asarray(pcd.points, dtype=np.float64) * MM_TO_M
        else:
            raise ValueError(f"unknown model_points_source: {self.model_points_source!r}")
        if self.n_model_points is not None and self.model_points_source == "vertices":
            rng = np.random.default_rng(0)  # fixed seed -> deterministic subsample
            pick = rng.choice(len(pts), size=int(self.n_model_points), replace=len(pts) < int(self.n_model_points))
            pts = pts[pick]
        return pts

    def _frame_paths(self, scene: int, im_id: str) -> tuple[Path, Path]:
        sdir = self.split_dir / f"{scene:06d}"
        return sdir / "rgb" / f"{int(im_id):06d}.png", sdir / "depth" / f"{int(im_id):06d}.png"

    # ------------------------------------------------------------------ #
    def __len__(self) -> int:
        return len(self._index)

    @property
    def frames(self) -> list[tuple[int, str]]:
        """The (scene_id, im_id) index (im_id is the string key used by the JSONs)."""
        return list(self._index)

    def __getitem__(self, index: int) -> dict:
        scene, im_id = self._index[index]
        sdir = self.split_dir / f"{scene:06d}"
        cam_entry = self._scene_camera[scene][im_id]
        K = np.array(cam_entry["cam_K"], dtype=np.float64).reshape(3, 3)
        depth_scale = float(cam_entry["depth_scale"])

        rgb_path, depth_path = self._frame_paths(scene, im_id)
        rgb = cv2.imread(str(rgb_path), cv2.IMREAD_COLOR)
        if rgb is None:
            raise FileNotFoundError(rgb_path)
        rgb = np.ascontiguousarray(rgb[:, :, ::-1])  # BGR -> RGB
        depth_raw = cv2.imread(str(depth_path), cv2.IMREAD_UNCHANGED)
        if depth_raw is None:
            raise FileNotFoundError(depth_path)
        depth = (depth_raw.astype(np.float32) * np.float32(depth_scale * 1e-3)).astype(np.float32)

        gt_poses: dict[int, np.ndarray] = {}
        masks: dict[int, np.ndarray] = {}
        visib: dict[int, float] = {}
        gt_instance_ids: dict[int, int] = {}
        instances = self._scene_gt[scene][im_id]
        for gid, inst in enumerate(instances):
            oid = int(inst["obj_id"])
            if oid not in self.obj_ids:
                continue
            if oid in gt_poses:
                raise ValueError(
                    f"multiple instances of object {oid} in frame {scene:06d}/{im_id}; "
                    "the dict-per-object contract supports at most one"
                )
            R = np.array(inst["cam_R_m2c"], dtype=np.float64).reshape(3, 3)
            t = np.array(inst["cam_t_m2c"], dtype=np.float64).reshape(3) * MM_TO_M
            gt_poses[oid] = make_T(R, t)
            gt_instance_ids[oid] = gid
            if self.load_masks:
                m = cv2.imread(str(sdir / "mask_visib" / f"{int(im_id):06d}_{gid:06d}.png"), cv2.IMREAD_UNCHANGED)
                if m is None:
                    raise FileNotFoundError(sdir / "mask_visib" / f"{int(im_id):06d}_{gid:06d}.png")
                masks[oid] = m > 0
            if self._scene_gt_info[scene] is not None:
                visib[oid] = float(self._scene_gt_info[scene][im_id][gid]["visib_fract"])

        return {
            "frame_id": f"{scene:06d}/{int(im_id):06d}",
            "scene_id": scene,
            "im_id": int(im_id),
            "rgb": rgb,
            "depth": depth,
            "depth_scale": depth_scale,
            "K": K,
            "masks": masks,
            "gt_poses": gt_poses,
            "model_points": {oid: pts.copy() for oid, pts in self._model_points.items()},
            "gt_instance_ids": gt_instance_ids,
            "visib_fract": visib,
        }
