"""P2.0 diagnosis control: intra-scene reference library (attribution experiment).

The approved P2.0 setup (reference = scene 52, evaluation = scene 50) yielded
0/10 solver success with only 0-6 in-mask matches per frame. This control
answers WHY, by swapping ONLY the reference library source:

  - library from 3 high-visibility frames of the SAME scene (scene 50),
    explicitly excluding the 10 evaluation frames (no leakage);
  - everything else identical (matching, PnP, metrics, 10 eval frames).

Interpretation:
  - control succeeds -> the failure of the cross-scene setup is a genuine
    algorithmic finding (limited SIFT viewpoint invariance), not a software bug;
  - control also fails -> the pipeline itself is broken, dig for bugs.

Run:  python scripts/p2_0_intra_scene_control.py [--data-root data/ycbv] [--out outputs/p2_0_control]
"""

from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path

import cv2
import numpy as np

from r3p.datasets.ycbv_bop import YcbvBopDataset
from r3p.evaluation.metrics import compute_all
from r3p.experiments.run_p2_0 import select_eval_frames
from r3p.geometry.camera import project
from r3p.geometry.se3 import apply as apply_T
from r3p.pose.sift_pnp import ReferenceLibrary, _lift_keypoints_to_model, match_query, solve_pnp

OBJ_ID = 5
DIAMETER_M = 0.1965  # models_info.json, obj 5


def build_intra_scene_library(dataset, exclude_im_ids: set[str], n_frames: int, sift):
    """Top-n frames by visib_fract among frames NOT in the evaluation set."""
    candidates = []
    for i in range(len(dataset)):
        obs = dataset[i]
        if obs["frame_id"].split("/")[1] in exclude_im_ids:
            continue
        candidates.append((float(obs["visib_fract"][OBJ_ID]), int(obs["im_id"]), obs))
    candidates.sort(key=lambda t: (-t[0], t[1]))
    chosen = candidates[:n_frames]
    assert len(chosen) > 0, "no reference candidates after excluding evaluation frames (anti-false-pass)"

    desc_parts, pt_parts, segments = [], [], {}
    row0 = 0
    for _, _, obs in chosen:
        desc, pts, kps, idx = _lift_keypoints_to_model(
            obs["rgb"], obs["depth"], obs["masks"][OBJ_ID], obs["K"], obs["gt_poses"][OBJ_ID], sift
        )
        desc_parts.append(desc)
        pt_parts.append(pts)
        segments[obs["frame_id"]] = {
            "rgb": obs["rgb"],
            "keypoints": [kps[j] for j in idx],
            "row_range": (row0, row0 + len(pts)),
            "visib_fract": float(obs["visib_fract"][OBJ_ID]),
        }
        row0 += len(pts)
    lib = ReferenceLibrary(
        obj_id=OBJ_ID,
        descriptors=np.concatenate(desc_parts, axis=0),
        points_model=np.concatenate(pt_parts, axis=0),
        frame_ids=[s for s in segments],
        per_frame_counts=[len(segments[s]["keypoints"]) for s in segments],
        segments=segments,
    )
    assert len(lib) > 0, "intra-scene library is empty (anti-false-pass)"
    return lib


def verify_library_self_consistency(dataset, lib) -> float:
    """Every lifted 3D point, transformed by its reference GT pose and projected,
    must land back on its own SIFT keypoint (catches lifting/convention bugs)."""
    errs = []
    obs_by_im = {int(dataset.frames[i][1]): dataset[i] for i in range(len(dataset))}
    for fid, seg in lib.segments.items():
        obs = obs_by_im[int(fid.split("/")[1])]
        r0, r1 = seg["row_range"]
        uv, _ = project(obs["K"], apply_T(obs["gt_poses"][OBJ_ID], lib.points_model[r0:r1]))
        kp_uv = np.array([k.pt for k in seg["keypoints"]])
        errs.append(np.linalg.norm(uv - kp_uv, axis=1))
    return float(np.concatenate(errs).max())


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data-root", default="data/ycbv")
    parser.add_argument("--out", default="outputs/p2_0_control")
    parser.add_argument("--scene", type=int, default=50)
    parser.add_argument("--n-frames", type=int, default=10)
    parser.add_argument("--n-ref", type=int, default=3)
    args = parser.parse_args()

    cv2.setRNGSeed(0)
    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)

    import cv2 as _cv2  # SIFT after seed
    sift = _cv2.SIFT_create()

    dataset = YcbvBopDataset(args.data_root, obj_ids=(OBJ_ID,), scene_ids=[args.scene],
                             load_masks=True, n_model_points=2000)
    eval_ids = select_eval_frames(dataset, args.n_frames)
    exclude = {dataset.frames[i][1] for i in eval_ids}
    assert len(exclude) == args.n_frames, "evaluation frame selection collided"

    lib = build_intra_scene_library(dataset, exclude, args.n_ref, sift)
    max_lift_err = verify_library_self_consistency(dataset, lib)

    rows = []
    n_solver = n_pose = 0
    threshold = 0.1 * DIAMETER_M
    for k, i in enumerate(eval_ids):
        obs = dataset[i]
        m = match_query(obs["rgb"], lib, mask_query=obs["masks"][OBJ_ID], ratio=0.75, sift=sift)
        if m.in_mask is not None and m.in_mask.sum() >= 6:
            pnp = solve_pnp(m.points_model[m.in_mask], m.points_image[m.in_mask], obs["K"])
        else:
            pnp = solve_pnp(np.zeros((0, 3)), np.zeros((0, 2)), obs["K"])
        met = compute_all(dataset._model_points[OBJ_ID], pnp.T, obs["gt_poses"][OBJ_ID]) if pnp.success else None
        pose_ok = bool(met and met["add"] < threshold)
        n_solver += int(pnp.success)
        n_pose += int(pose_ok)

        img = obs["rgb"].copy()
        uv_gt, _ = project(obs["K"], apply_T(obs["gt_poses"][OBJ_ID], dataset._model_points[OBJ_ID]))
        for u, v in uv_gt:
            _cv2.circle(img, (int(u), int(v)), 1, (0, 200, 0), -1)
        if pnp.success:
            uv_p, _ = project(obs["K"], apply_T(pnp.T, dataset._model_points[OBJ_ID]))
            for u, v in uv_p:
                _cv2.circle(img, (int(u), int(v)), 1, (255, 60, 60), -1)
        note = f"inl={pnp.n_inliers} add={'%.1fmm' % (met['add'] * 1e3) if met else 'NA'}"
        _cv2.putText(img, note, (10, 24), _cv2.FONT_HERSHEY_SIMPLEX, 0.55, (255, 255, 255), 2, _cv2.LINE_AA)
        _cv2.imwrite(str(out_dir / f"overlay_{obs['frame_id'].replace('/', '_')}.png"), _cv2.cvtColor(img, _cv2.COLOR_RGB2BGR))

        if k == 0 and m.matches:
            seg_frame, seg_first = next(iter(lib.segments.items()))
            r0, r1 = seg_first["row_range"]
            seg_matches = [
                cv2.DMatch(mt.queryIdx, mt.trainIdx - r0, mt.distance)
                for mt in m.matches
                if r0 <= mt.trainIdx < r1
            ]
            if seg_matches:
                _cv2.imwrite(str(out_dir / f"matches_{obs['frame_id'].replace('/', '_')}.png"),
                             _cv2.drawMatches(_cv2.cvtColor(obs["rgb"], _cv2.COLOR_RGB2BGR), m.query_keypoints,
                                              _cv2.cvtColor(seg_first["rgb"], _cv2.COLOR_RGB2BGR), seg_first["keypoints"],
                                              seg_matches[:120], None, flags=_cv2.DrawMatchesFlags_NOT_DRAW_SINGLE_POINTS))

        rows.append({
            "frame_id": obs["frame_id"], "query_kp": m.n_query_keypoints,
            "matches_good": m.n_matches_good, "matches_in_mask": m.n_matches_in_mask,
            "pnp_inliers": pnp.n_inliers if pnp.success else 0,
            "reproj_px": round(pnp.residual_px, 3) if pnp.success else "",
            "solver_success": int(pnp.success), "pose_success": int(pose_ok),
            "add_mm": round(met["add"] * 1e3, 2) if met else "",
            "adds_mm": round(met["adds"] * 1e3, 2) if met else "",
            "trans_mm": round(met["trans"] * 1e3, 2) if met else "",
            "rot_deg": round(met["rot_deg"], 2) if met else "",
        })
        print(f"{obs['frame_id']}: good={m.n_matches_good} in_mask={m.n_matches_in_mask} "
              f"inl={pnp.n_inliers} add={rows[-1]['add_mm']}mm pose_ok={pose_ok}")

    with open(out_dir / "per_frame.csv", "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)
    summary = {
        "purpose": "P2.0 attribution control: intra-scene reference library",
        "n_frames": len(rows), "solver_success": n_solver, "pose_success": n_pose,
        "add_threshold_m": threshold, "library_size": len(lib),
        "library_frames": lib.frame_ids, "max_lift_reprojection_err_px": max_lift_err,
        "rows": rows,
    }
    with open(out_dir / "metrics.json", "w", encoding="utf-8") as f:
        json.dump(summary, f, indent=2)
    print(f"\n[CONTROL] solver success {n_solver}/{len(rows)}, pose success {n_pose}/{len(rows)}, "
          f"library={len(lib)} desc, max lift reprojection err={max_lift_err:.3f}px")
    print(f"outputs: {out_dir}")


if __name__ == "__main__":
    main()
