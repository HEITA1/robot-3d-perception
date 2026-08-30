"""Verify the downloaded BOP YCB-V test_bop19 subset (Phase 1 data validation).

Checks (docs/proposal_phase1_data.md section 4, verification checklist):
  1. scene_gt.json / scene_gt_info.json / scene_camera.json exist and parse for all scenes
  2. every frame listed in scene_camera.json has rgb + depth files on disk
  3. depth_scale == 0.1 for all frames; intrinsics constant within each scene
  4. models_info.json parses; per-object diameters present; obj_id <-> name mapping
  5. round-trip on sample frames: depth -> point cloud -> reproject (pixel + depth error)
  6. GT overlay: project model points with GT pose onto RGB, save PNG for visual check

Usage:
  python scripts/verify_ycbv_data.py --data-root data/ycbv [--out outputs/verification]

Exit code 0 iff all checks pass.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import cv2
import numpy as np
import open3d as o3d

SCENES = list(range(48, 60))  # test_bop19: scenes 000048..000059
TARGET_OBJECTS = {5: "006_mustard_bottle", 13: "024_bowl"}  # from dataset_info.md
MM_TO_M = 1e-3


def load_json(path: Path):
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def check_gt_and_frames(data_root: Path, log) -> bool:
    ok = True
    total_frames = 0
    obj_scene_count = {k: 0 for k in TARGET_OBJECTS}
    for scene in SCENES:
        sdir = data_root / "test" / f"{scene:06d}"
        try:
            gt = load_json(sdir / "scene_gt.json")
            gt_info = load_json(sdir / "scene_gt_info.json")
            cam = load_json(sdir / "scene_camera.json")
        except Exception as e:  # noqa: BLE001
            log(f"FAIL scene {scene}: JSON parse error: {e}")
            ok = False
            continue
        missing = [
            f"{key}/{im_id:06d}.*"
            for im_id in cam
            for key in ("rgb", "depth")
            if not list((sdir / key).glob(f"{int(im_id):06d}.*"))
        ]
        if missing:
            log(f"FAIL scene {scene}: {len(missing)} missing rgb/depth files, e.g. {missing[:3]}")
            ok = False
        for im_id, instances in gt.items():
            for inst in instances:
                if inst["obj_id"] in obj_scene_count and im_id in cam:
                    obj_scene_count[inst["obj_id"]] += 1
        total_frames += len(cam)
        log(
            f"scene {scene:06d}: frames={len(cam):4d} gt_ok=True rgb/depth_ok={not missing} "
            f"masks(mask_visib)={len(list((sdir / 'mask_visib').glob('*.png')))}"
        )
    log(f"total frames across scenes: {total_frames}")
    for obj_id, name in TARGET_OBJECTS.items():
        log(f"target object {obj_id:02d} ({name}): instances with GT in test set = {obj_scene_count[obj_id]}")
    return ok


def check_camera_params(data_root: Path, log) -> bool:
    ok = True
    for scene in SCENES:
        cam = load_json(data_root / "test" / f"{scene:06d}" / "scene_camera.json")
        scales = {entry["depth_scale"] for entry in cam.values()}
        if scales != {0.1}:
            log(f"FAIL scene {scene}: unexpected depth_scale values {scales}")
            ok = False
        Ks = {tuple(np.round(entry["cam_K"], 3)) for entry in cam.values()}
        if len(Ks) != 1:
            log(f"FAIL scene {scene}: intrinsics vary within scene: {len(Ks)} distinct K")
            ok = False
    log("depth_scale == 0.1 and per-scene constant K: verified for all scenes" if ok else "camera param check FAILED")
    return ok


def check_models(data_root: Path, log) -> bool:
    info = load_json(data_root / "models" / "models_info.json")
    log(f"models_info.json: {len(info)} objects")
    for obj_id, name in TARGET_OBJECTS.items():
        entry = info.get(str(obj_id))
        if entry is None:
            log(f"FAIL: models_info.json missing object {obj_id}")
            return False
        log(f"obj {obj_id:02d} ({name}): diameter = {entry['diameter']:.1f} mm, "
            f"keys = {sorted(entry.keys())}")
    mesh = o3d.io.read_triangle_mesh(str(data_root / "models" / "obj_000005.ply"))
    log(f"obj 05 mesh: {len(mesh.vertices)} vertices, {len(mesh.triangles)} triangles")
    return True


def depth_to_meters(raw: np.ndarray, depth_scale: float) -> np.ndarray:
    return raw.astype(np.float64) * depth_scale * 1e-3


def check_roundtrip_and_overlay(data_root: Path, out_dir: Path, log) -> bool:
    """Sample one frame per target object (objects may never co-occur in a frame),
    run a depth round-trip on each, and project the GT models onto RGB for visual check."""
    ok = True
    samples = []  # (scene, frame_str, [obj_ids present in frame])
    for obj_id in TARGET_OBJECTS:
        found = False
        for scene in SCENES:
            sdir = data_root / "test" / f"{scene:06d}"
            gt = load_json(sdir / "scene_gt.json")
            frame = next(
                (im for im, insts in gt.items() if any(i["obj_id"] == obj_id for i in insts)),
                None,
            )
            if frame is not None:
                present = [i["obj_id"] for i in gt[frame] if i["obj_id"] in TARGET_OBJECTS]
                samples.append((scene, frame, present, sdir))
                found = True
                break
        if not found:
            log(f"FAIL: object {obj_id} not found in any sampled scene")
            ok = False
    if not samples:
        log("FAIL: no sample frames collected")
        return False

    for scene, frame, present, sdir in samples:
        cam = load_json(sdir / "scene_camera.json")
        K = np.array(cam[frame]["cam_K"]).reshape(3, 3)
        depth = depth_to_meters(
            cv2.imread(str(sdir / "depth" / f"{int(frame):06d}.png"), cv2.IMREAD_UNCHANGED),
            cam[frame]["depth_scale"],
        )
        mask = depth > 0
        v, u = np.nonzero(mask)
        z = depth[v, u]
        x = (u - K[0, 2]) * z / K[0, 0]
        y = (v - K[1, 2]) * z / K[1, 1]
        pts = np.stack([x, y, z], axis=1)
        u2 = K[0, 0] * pts[:, 0] / pts[:, 2] + K[0, 2]
        v2 = K[1, 1] * pts[:, 1] / pts[:, 2] + K[1, 2]
        px_err = max(float(np.abs(u2 - u).max()), float(np.abs(v2 - v).max()))
        depth_err = float(np.abs(pts[:, 2] - z).max())

        rgb = cv2.imread(str(sdir / "rgb" / f"{int(frame):06d}.png"), cv2.IMREAD_COLOR)
        gt = load_json(sdir / "scene_gt.json")
        for obj_id, color in zip(present, ((0, 255, 0), (255, 128, 0))):
            inst = next(i for i in gt[frame] if i["obj_id"] == obj_id)
            R = np.array(inst["cam_R_m2c"]).reshape(3, 3)
            t = np.array(inst["cam_t_m2c"]).reshape(3) * MM_TO_M
            mesh = o3d.io.read_triangle_mesh(str(data_root / "models" / f"obj_{obj_id:06d}.ply"))
            P = np.asarray(mesh.vertices) * MM_TO_M
            P_cam = P @ R.T + t
            uv = K @ P_cam.T
            uu = np.rint(uv[0] / uv[2]).astype(int)
            vv = np.rint(uv[1] / uv[2]).astype(int)
            inb = (uu >= 0) & (uu < rgb.shape[1]) & (vv >= 0) & (vv < rgb.shape[0])
            for pu, pv in zip(uu[inb], vv[inb]):
                cv2.circle(rgb, (int(pu), int(pv)), 1, color, -1)
            log(f"scene {scene} frame {frame}: obj {obj_id:02d} GT projected {int(inb.sum())}/{len(P)} points in bounds")
        out_dir.mkdir(parents=True, exist_ok=True)
        out_path = out_dir / f"overlay_{scene:06d}_{int(frame):06d}.png"
        cv2.imwrite(str(out_path), rgb)
        log(f"  frame {scene}/{frame}: roundtrip max err = {px_err:.2e} px, {depth_err:.2e} m; overlay: {out_path.name}")
        if px_err > 1e-3 or depth_err > 1e-9:
            ok = False
    return ok


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data-root", default="data/ycbv")
    parser.add_argument("--out", default="outputs/verification")
    args = parser.parse_args()

    log_lines: list[str] = []

    def log(msg: str) -> None:
        print(msg, flush=True)
        log_lines.append(msg)

    data_root = Path(args.data_root)
    results = {}
    results["gt_and_frames"] = check_gt_and_frames(data_root, log)
    results["camera_params"] = check_camera_params(data_root, log)
    results["models"] = check_models(data_root, log)
    results["roundtrip_overlay"] = check_roundtrip_and_overlay(data_root, Path(args.out), log)

    log("\n=== SUMMARY ===")
    for name, passed in results.items():
        log(f"{name}: {'PASS' if passed else 'FAIL'}")
    all_ok = all(results.values())
    log(f"OVERALL: {'PASS' if all_ok else 'FAIL'}")

    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    with open(out / "verification_log.txt", "w", encoding="utf-8") as f:
        f.write("\n".join(log_lines) + "\n")
    raise SystemExit(0 if all_ok else 1)


if __name__ == "__main__":
    main()
