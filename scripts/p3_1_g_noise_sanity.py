"""P3.1-G phase 1: depth noise-scale sanity check (read-only).

Question: does the existing real YCB-V depth data support "millimeter-level
depth noise" as a reasonable synthetic augmentation magnitude (~1 mm)?

Estimator (deliberately simple, per approved scope):
  - 3x3 box high-pass residual  r = z - blur_3x3(z)  on valid pixels
    (box filter preserves linear slopes, so tilt does not contaminate;
     curvature contribution at these kernel sizes is ~0.03 mm, negligible)
  - smooth-pixel gate: local 3x3 range < 3 mm (excludes silhouette edges and
    depth discontinuities so the bulk statistic reflects sensor noise)
  - implied pixel-noise sigma = std(r_smooth) * sqrt(9/10)
    (for iid pixel noise, Var(r) = sigma^2 * (1 + 1/9))

Frames: the 10 frozen Gate 3 frames (bottle clean x4, 721, bowl x5).
No data modification, no model involvement, GT not needed.
"""

from __future__ import annotations

import json
from pathlib import Path

import cv2
import numpy as np
import yaml

MM_TO_M = 1e-3


def depth_stats(depth_m: np.ndarray, mask: np.ndarray) -> dict:
    z = np.where(mask & (depth_m > 0), depth_m, np.nan).astype(np.float64)
    valid = np.isfinite(z)
    frac_valid = float(valid.mean())

    # 3x3 nan-aware box mean
    m = np.where(valid, z, 0.0)
    w = valid.astype(np.float64)
    k = np.ones((3, 3))
    from cv2 import filter2D
    cnt = filter2D(w, -1, k)
    mean = filter2D(m, -1, k) / np.maximum(cnt, 1)
    resid = np.where(valid & (cnt >= 6), z - mean, np.nan)

    # local range for the smooth gate
    zmin = filter2D(m, -1, k) / np.maximum(cnt, 1)  # rough; use min/max via dilate instead
    zmin = cv2.erode(z, np.ones((3, 3)), borderType=cv2.BORDER_CONSTANT)
    zmax = cv2.dilate(z, np.ones((3, 3)), borderType=cv2.BORDER_CONSTANT)
    local_range = zmax - zmin
    smooth = valid & np.isfinite(resid) & (local_range < 3e-3)

    r_abs = np.abs(resid[smooth])
    sigma_iid = float(np.nanstd(resid[smooth]) * np.sqrt(9 / 10))
    return {
        "n_smooth_px": int(smooth.sum()),
        "valid_depth_frac": round(frac_valid, 4),
        "resid_abs_median_mm": round(float(np.median(r_abs)) * 1e3, 3),
        "resid_abs_iqr_mm": round(float(np.percentile(r_abs, 75) - np.percentile(r_abs, 25)) * 1e3, 3),
        "resid_abs_p90_mm": round(float(np.percentile(r_abs, 90)) * 1e3, 3),
        "resid_abs_p95_mm": round(float(np.percentile(r_abs, 95)) * 1e3, 3),
        "implied_sigma_mm": round(sigma_iid * 1e3, 3),
        "depth_range_m": [round(float(np.nanmin(z)), 3), round(float(np.nanmax(z)), 3)],
    }


def main():
    cfg = yaml.safe_load(Path("configs/p3_0_gate3.yaml").read_text("utf-8"))
    data_root = Path(cfg["data"]["root"])
    out_root = Path("outputs") / "p3_1_g_noise_sanity"
    out_root.mkdir(parents=True, exist_ok=True)

    per_frame = {}
    for obj_cfg in cfg["objects"]:
        obj_id, scene = obj_cfg["obj_id"], obj_cfg["scene"]
        for im_id in obj_cfg["test_frames"]:
            sdir = data_root / "test" / f"{scene:06d}"
            cam = json.loads((sdir / "scene_camera.json").read_text("utf-8"))[str(im_id)]
            depth_scale = float(cam["depth_scale"])
            gt = json.loads((sdir / "scene_gt.json").read_text("utf-8"))[str(im_id)]
            gid = next(i for i, inst in enumerate(gt) if int(inst["obj_id"]) == obj_id)
            mask = cv2.imread(str(sdir / "mask_visib" / f"{im_id:06d}_{gid:06d}.png"),
                              cv2.IMREAD_UNCHANGED) > 0
            depth = cv2.imread(str(sdir / "depth" / f"{im_id:06d}.png"),
                               cv2.IMREAD_UNCHANGED).astype(np.float32) * np.float32(depth_scale * 1e-3)
            key = f"obj{obj_id:02d}_{scene:06d}_{im_id:06d}"
            per_frame[key] = depth_stats(depth, mask)
            print(f"{key}: smooth_px={per_frame[key]['n_smooth_px']:6d} "
                  f"median|r|={per_frame[key]['resid_abs_median_mm']:.3f}mm "
                  f"p90={per_frame[key]['resid_abs_p90_mm']:.3f}mm "
                  f"implied_sigma={per_frame[key]['implied_sigma_mm']:.3f}mm")

    sigmas = [v["implied_sigma_mm"] for v in per_frame.values()]
    medians = [v["resid_abs_median_mm"] for v in per_frame.values()]
    summary = {
        "per_frame": per_frame,
        "implied_sigma_mm": {"min": round(min(sigmas), 3), "median": round(float(np.median(sigmas)), 3),
                             "max": round(max(sigmas), 3)},
        "resid_abs_median_mm": {"min": round(min(medians), 3), "median": round(float(np.median(medians)), 3),
                                "max": round(max(medians), 3)},
    }
    print(f"\nimplied sigma across frames: {summary['implied_sigma_mm']}")
    print(f"local residual |r| median across frames: {summary['resid_abs_median_mm']}")

    # verdict per approved decision rule
    med_sigma = summary["implied_sigma_mm"]["median"]
    if 0.5 <= med_sigma <= 3.0:
        verdict = "SUPPORTS ~1mm (millimeter-level noise present; proceed with sigma=1mm as pre-registered)"
    elif med_sigma < 0.5:
        verdict = ("DOES NOT SUPPORT 1mm: measured noise is sub-millimeter; "
                   "stop and report the suggested magnitude instead of training")
    else:
        verdict = ("1mm UNDERESTIMATES: measured noise is several mm; "
                   "stop and report the suggested magnitude range instead of training")
    results = {"summary": summary, "verdict": verdict,
               "preregistered_next_step_if_supported": "retrain bottle CoordNet with depth sigma = 1 mm "
                                                        "(i.i.d. per-pixel Gaussian on the rendered depth map), "
                                                        "everything else frozen; evaluate bias on the 5 real bottle frames"}
    print(f"\nVERDICT: {verdict}")
    with open(out_root / "noise_sanity_results.json", "w", encoding="utf-8") as f:
        json.dump(results, f, indent=2)
    print(f"saved: {out_root / 'noise_sanity_results.json'}")


if __name__ == "__main__":
    main()
