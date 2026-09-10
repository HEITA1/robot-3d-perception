"""P3.1-B: Canonical prediction failure analysis.

Pure diagnostic — no model changes, no retraining, no parameter tuning.
Uses the ORIGINAL Gate 3 baseline pipeline (max-radius normalization).

6-layer analysis per frame:
  1. Raw prediction error (mean/median/p90/max/RMSE, per-axis, centroid, radius)
  2. Translation-only alignment (centroid subtraction)
  3. Rigid alignment (Kabsch, no scale, det=+1)
  4. Similarity alignment (Umeyama, with scale)
  5. Reflection / axis flip / 180-degree rotation check
  6. Non-rigid / structural residual analysis
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import cv2
import numpy as np
import open3d as o3d
import torch

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from r3p.geometry.camera import deproject
from r3p.geometry.se3 import make_T, invert, apply as apply_T
from r3p.learn.coord_net import CoordNet, normalize_points
from r3p.learn.umeyama import umeyama_alignment

MM_TO_M = 1e-3


# ---------------------------------------------------------------------------
# Diagnostic alignment (not used for pose evaluation)
# ---------------------------------------------------------------------------

def similarity_alignment(src, dst):
    """Umeyama with scale: dst ~= s * R @ src + t. Returns (s, R, t)."""
    src_mean = src.mean(axis=0)
    dst_mean = dst.mean(axis=0)
    src_c = src - src_mean
    dst_c = dst - dst_mean
    n = len(src)
    H = (src_c.T @ dst_c) / n
    U, S, Vt = np.linalg.svd(H)
    d = np.sign(np.linalg.det(Vt.T @ U.T))
    D = np.diag([1.0, 1.0, d])
    R = Vt.T @ D @ U.T
    var_src = np.mean(np.sum(src_c ** 2, axis=1))
    s = float(np.sum(S * np.diag(D))) / var_src
    t = dst_mean - s * R @ src_mean
    return s, R, t


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def err_stats(e):
    return {
        "mean_mm": round(float(e.mean()) * 1e3, 3),
        "median_mm": round(float(np.median(e)) * 1e3, 3),
        "p90_mm": round(float(np.percentile(e, 90)) * 1e3, 3),
        "max_mm": round(float(e.max()) * 1e3, 3),
        "rmse_mm": round(float(np.sqrt(np.mean(e ** 2))) * 1e3, 3),
    }


def rot_deg(R):
    return float(np.degrees(np.arccos(np.clip((np.trace(R) - 1.0) / 2.0, -1.0, 1.0))))


# ---------------------------------------------------------------------------
# 6-layer analysis
# ---------------------------------------------------------------------------

def analyze_prediction(pred, gt, tag=""):
    """pred, gt: (N,3) canonical coords in meters. Returns (result, pred_rig, pred_sim)."""
    res = {"tag": tag, "n_points": len(pred)}

    # Layer 1: Raw
    raw_err = np.linalg.norm(pred - gt, axis=1)
    res["raw"] = err_stats(raw_err)
    pred_c = pred - pred.mean(axis=0)
    gt_c = gt - gt.mean(axis=0)
    for ax in range(3):
        d = pred[:, ax] - gt[:, ax]
        res["raw"][f"ax{ax}_mean_mm"] = round(float(d.mean()) * 1e3, 3)
        res["raw"][f"ax{ax}_std_mm"] = round(float(d.std()) * 1e3, 3)
        res["raw"][f"ax{ax}_corr"] = round(float(np.corrcoef(pred[:, ax], gt[:, ax])[0, 1]), 4)
    res["raw"]["centroid_shift_mm"] = round(
        float(np.linalg.norm(pred.mean(axis=0) - gt.mean(axis=0))) * 1e3, 3)
    res["raw"]["pred_radius_mean"] = round(float(np.linalg.norm(pred_c, axis=1).mean()), 6)
    res["raw"]["gt_radius_mean"] = round(float(np.linalg.norm(gt_c, axis=1).mean()), 6)
    res["raw"]["pred_std"] = [round(float(v), 6) for v in pred.std(axis=0)]
    res["raw"]["gt_std"] = [round(float(v), 6) for v in gt.std(axis=0)]

    # Layer 2: Translation-only
    res["translation_aligned"] = err_stats(np.linalg.norm(pred_c - gt_c, axis=1))

    # Layer 3: Rigid (Kabsch, det=+1)
    R_r, t_r = umeyama_alignment(pred, gt)
    pred_rig = pred @ R_r.T + t_r
    rig_err = np.linalg.norm(pred_rig - gt, axis=1)
    res["rigid_aligned"] = err_stats(rig_err)
    res["rigid_aligned"]["rot_deg"] = round(rot_deg(R_r), 3)
    res["rigid_aligned"]["trans_mm"] = round(float(np.linalg.norm(t_r)) * 1e3, 3)
    res["rigid_aligned"]["det_R"] = round(float(np.linalg.det(R_r)), 6)
    H = pred_c.T @ gt_c
    U, _, Vt = np.linalg.svd(H)
    R_unc = Vt.T @ U.T
    unc_err = np.linalg.norm(pred_c @ R_unc.T - gt_c, axis=1)
    res["rigid_aligned"]["det_R_unc"] = round(float(np.linalg.det(R_unc)), 6)
    res["rigid_aligned"]["unc_mean_mm"] = round(float(unc_err.mean()) * 1e3, 3)

    # Layer 4: Similarity (with scale)
    s_s, R_s, t_s = similarity_alignment(pred, gt)
    pred_sim = s_s * (pred @ R_s.T) + t_s
    sim_err = np.linalg.norm(pred_sim - gt, axis=1)
    res["similarity_aligned"] = err_stats(sim_err)
    res["similarity_aligned"]["scale"] = round(s_s, 6)
    res["similarity_aligned"]["rot_deg"] = round(rot_deg(R_s), 3)
    res["similarity_aligned"]["trans_mm"] = round(float(np.linalg.norm(t_s)) * 1e3, 3)
    res["similarity_aligned"]["det_R"] = round(float(np.linalg.det(R_s)), 6)

    # Layer 5: Reflection / flip / 180-degree rotation
    ref = {"rigid_baseline_mm": res["rigid_aligned"]["mean_mm"]}
    for ax in range(3):
        F = np.eye(3)
        F[ax, ax] = -1
        pf = pred @ F.T
        Rf, tf = umeyama_alignment(pf, gt)
        ef = np.linalg.norm(pf @ Rf.T + tf - gt, axis=1)
        ref[f"flip_ax{ax}_mm"] = round(float(ef.mean()) * 1e3, 3)
    for name, R180 in [("r180x", np.diag([1., -1., -1.])),
                        ("r180y", np.diag([-1., 1., -1.])),
                        ("r180z", np.diag([-1., -1., 1.]))]:
        pr = pred @ R180.T
        Rr, tr = umeyama_alignment(pr, gt)
        er = np.linalg.norm(pr @ Rr.T + tr - gt, axis=1)
        ref[f"{name}_mm"] = round(float(er.mean()) * 1e3, 3)
    res["reflection_check"] = ref

    # Layer 6: Structural (on similarity-aligned)
    st = {}
    resid = pred_sim - gt
    resid_mag = np.linalg.norm(resid, axis=1)
    for ax in range(3):
        st[f"resid_ax{ax}_mean_mm"] = round(float(np.abs(resid[:, ax]).mean()) * 1e3, 3)
        st[f"resid_ax{ax}_std_mm"] = round(float(resid[:, ax].std()) * 1e3, 3)
    gt_radii = np.linalg.norm(gt_c, axis=1)
    st["resid_vs_radius_corr"] = round(float(np.corrcoef(resid_mag, gt_radii)[0, 1]), 4)
    pe = np.sort(np.linalg.eigvalsh(np.cov(pred_sim.T)))[::-1]
    ge = np.sort(np.linalg.eigvalsh(np.cov(gt.T)))[::-1]
    st["pred_eigvals"] = [round(float(v), 8) for v in pe]
    st["gt_eigvals"] = [round(float(v), 8) for v in ge]
    st["eigval_ratio"] = [round(float(p / g), 4) if g > 1e-12 else 999.0
                           for p, g in zip(pe, ge)]
    res["structural"] = st

    return res, pred_rig, pred_sim


# ---------------------------------------------------------------------------
# Data loading (identical to Gate 3)
# ---------------------------------------------------------------------------

def load_frame(data_root, scene, im_id, obj_id):
    sdir = data_root / "test" / f"{scene:06d}"
    cam = json.loads((sdir / "scene_camera.json").read_text("utf-8"))
    gt_j = json.loads((sdir / "scene_gt.json").read_text("utf-8"))
    gt_info = json.loads((sdir / "scene_gt_info.json").read_text("utf-8"))
    im_key = str(im_id)
    K = np.array(cam[im_key]["cam_K"], dtype=np.float64).reshape(3, 3)
    ds = float(cam[im_key]["depth_scale"])
    rgb = cv2.imread(str(sdir / "rgb" / f"{im_id:06d}.png"), cv2.IMREAD_COLOR)
    rgb = cv2.cvtColor(rgb, cv2.COLOR_BGR2RGB)
    dep_raw = cv2.imread(str(sdir / "depth" / f"{im_id:06d}.png"), cv2.IMREAD_UNCHANGED)
    depth = (dep_raw.astype(np.float32) * np.float32(ds * 1e-3)).astype(np.float32)
    for gid, inst in enumerate(gt_j[im_key]):
        if int(inst["obj_id"]) == obj_id:
            R = np.array(inst["cam_R_m2c"], dtype=np.float64).reshape(3, 3)
            t = np.array(inst["cam_t_m2c"], dtype=np.float64).reshape(3) * MM_TO_M
            m = cv2.imread(str(sdir / "mask_visib" / f"{im_id:06d}_{gid:06d}.png"),
                           cv2.IMREAD_UNCHANGED)
            return {"rgb": rgb, "depth": depth, "K": K, "mask": m > 0,
                    "gt_pose": make_T(R, t),
                    "visib_fract": float(gt_info[im_key][gid]["visib_fract"])}
    raise ValueError(f"obj {obj_id} not found in {scene}/{im_id}")


# ---------------------------------------------------------------------------
# Visualization
# ---------------------------------------------------------------------------

def save_viz(pred, gt, pred_rig, pred_sim, tag, out_path):
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
    except ImportError:
        return

    fig, axes = plt.subplots(2, 2, figsize=(12, 10))
    fig.suptitle(tag, fontsize=10)

    panels = [
        (0, 0, pred, "Raw prediction"),
        (0, 1, pred_rig, "Rigid-aligned"),
        (1, 0, pred_sim, "Similarity-aligned"),
    ]
    for row, col, pts, title in panels:
        ax = axes[row, col]
        ax.scatter(gt[:, 0], gt[:, 1], s=0.5, c="blue", alpha=0.3, label="GT")
        ax.scatter(pts[:, 0], pts[:, 1], s=0.5, c="red", alpha=0.3, label="Pred")
        ax.set_title(title, fontsize=8)
        ax.set_xlabel("x (m)", fontsize=7)
        ax.set_ylabel("y (m)", fontsize=7)
        ax.set_aspect("equal")
        ax.legend(fontsize=6, markerscale=5)

    ax = axes[1, 1]
    resid = np.linalg.norm(pred_sim - gt, axis=1) * 1e3
    ax.hist(resid, bins=50, color="steelblue", edgecolor="none")
    ax.set_title("Similarity-aligned residual (mm)", fontsize=8)
    ax.set_xlabel("mm", fontsize=7)
    ax.axvline(np.median(resid), color="red", linestyle="--", linewidth=0.8,
               label=f"median={np.median(resid):.1f}")
    ax.legend(fontsize=6)

    plt.tight_layout()
    out_path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(str(out_path), dpi=150)
    plt.close(fig)


# ---------------------------------------------------------------------------
# MAIN
# ---------------------------------------------------------------------------

def main():
    import yaml
    cfg = yaml.safe_load(Path("configs/p3_0_gate3.yaml").read_text("utf-8"))
    data_root = Path(cfg["data"]["root"])
    n_pts = cfg["model"]["n_points"]

    out_dir = Path("outputs/p3_1_b_canonical_analysis")
    out_dir.mkdir(parents=True, exist_ok=True)

    net = CoordNet()
    net.load_state_dict(torch.load(cfg["model"]["checkpoint"], map_location="cpu",
                                   weights_only=True))
    net.eval()
    print(f"Checkpoint: {cfg['model']['checkpoint']}")

    results = {}

    # ========================================================================
    # Synthetic control (Gate 2 val split)
    # ========================================================================
    print("\n" + "=" * 70)
    print("SYNTHETIC CONTROL (Gate 2 val split, bottle)")
    print("=" * 70)

    synth_dir = Path("data_synth/bottle/val")
    synth_files = sorted(synth_dir.glob("*.npz"))[:10]
    synth_results = []

    for i, p in enumerate(synth_files):
        s = np.load(p)
        xyz = s["xyz"].astype(np.float64)
        gt_canonical = s["coords"].astype(np.float64)
        rgb = s["rgb"].astype(np.float64)

        xyz_norm, _, scale = normalize_points(xyz)
        features = np.concatenate([xyz_norm, rgb / 255.0], axis=1).astype(np.float32)
        with torch.no_grad():
            pred = net(torch.from_numpy(features)).numpy()

        tag = f"synth_{i:03d}"
        r, pred_rig, pred_sim = analyze_prediction(pred, gt_canonical, tag=tag)
        r["domain"] = "synthetic"
        r["object"] = "bottle"
        r["norm_scale"] = round(scale, 6)
        synth_results.append(r)

        print(f"  [{tag}] raw={r['raw']['mean_mm']:.2f} "
              f"trans={r['translation_aligned']['mean_mm']:.2f} "
              f"rigid={r['rigid_aligned']['mean_mm']:.2f} "
              f"sim={r['similarity_aligned']['mean_mm']:.2f} "
              f"scale={r['similarity_aligned']['scale']:.4f}")

        if i == 0:
            save_viz(pred, gt_canonical, pred_rig, pred_sim,
                     f"synthetic_val_{i:03d}", out_dir / f"viz_synth_{i:03d}.png")

    results["synthetic"] = synth_results

    # ========================================================================
    # Real frames
    # ========================================================================
    viz_frames = {("bottle", 0), ("bottle", 2), ("bowl", 0)}  # 620, 721, 001

    for obj_cfg in cfg["objects"]:
        obj_id = obj_cfg["obj_id"]
        scene = obj_cfg["scene"]
        frames = obj_cfg["test_frames"]
        obj_name = "bottle" if obj_id == 5 else "bowl"

        print(f"\n{'=' * 70}")
        print(f"REAL: obj{obj_id:02d} ({obj_name}) scene {scene}")
        print(f"{'=' * 70}")

        obj_results = []
        for fi, im_id in enumerate(frames):
            fseed = cfg["ransac_umeyama"]["seed"] + fi * 1000 + obj_id * 10000
            frame = load_frame(data_root, scene, im_id, obj_id)
            tag = f"obj{obj_id:02d}_{scene:06d}_{im_id:06d}"

            cam_xyz = deproject(frame["K"], frame["depth"], mask=frame["mask"])
            cam_rgb = frame["rgb"][frame["mask"]]

            rng = np.random.default_rng(fseed)
            idx = rng.choice(len(cam_xyz), size=n_pts, replace=False)
            cam_sampled = cam_xyz[idx]
            rgb_sampled = cam_rgb[idx]

            cam_norm, center, scale = normalize_points(cam_sampled)
            features = np.concatenate([cam_norm, rgb_sampled / 255.0],
                                      axis=1).astype(np.float32)

            with torch.no_grad():
                pred = net(torch.from_numpy(features)).numpy()

            gt_canonical = apply_T(invert(frame["gt_pose"]), cam_sampled)

            r, pred_rig, pred_sim = analyze_prediction(pred, gt_canonical, tag=tag)
            r["domain"] = "real"
            r["object"] = obj_name
            r["obj_id"] = obj_id
            r["scene"] = scene
            r["im_id"] = im_id
            r["visib_fract"] = frame["visib_fract"]
            r["norm_scale"] = round(scale, 6)
            obj_results.append(r)

            print(f"\n  [{tag}] visib={frame['visib_fract']:.3f} scale={scale:.4f}m")
            print(f"    raw: mean={r['raw']['mean_mm']:.2f} med={r['raw']['median_mm']:.2f} "
                  f"p90={r['raw']['p90_mm']:.2f} max={r['raw']['max_mm']:.2f} "
                  f"rmse={r['raw']['rmse_mm']:.2f}")
            print(f"    centroid_shift={r['raw']['centroid_shift_mm']:.2f}mm "
                  f"pred_r={r['raw']['pred_radius_mean']:.4f} "
                  f"gt_r={r['raw']['gt_radius_mean']:.4f}")
            for ax in range(3):
                print(f"    ax{ax}: corr={r['raw'][f'ax{ax}_corr']:+.4f} "
                      f"mean={r['raw'][f'ax{ax}_mean_mm']:+.2f}mm "
                      f"std={r['raw'][f'ax{ax}_std_mm']:.2f}mm")
            print(f"    trans: mean={r['translation_aligned']['mean_mm']:.2f}mm")
            ra = r["rigid_aligned"]
            print(f"    rigid: mean={ra['mean_mm']:.2f}mm rot={ra['rot_deg']:.1f}deg "
                  f"det={ra['det_R']:.4f} det_unc={ra['det_R_unc']:.4f} "
                  f"unc={ra['unc_mean_mm']:.2f}mm")
            sa = r["similarity_aligned"]
            print(f"    sim:   mean={sa['mean_mm']:.2f}mm scale={sa['scale']:.4f} "
                  f"rot={sa['rot_deg']:.1f}deg")
            rf = r["reflection_check"]
            print(f"    flips: ax0={rf['flip_ax0_mm']:.2f} ax1={rf['flip_ax1_mm']:.2f} "
                  f"ax2={rf['flip_ax2_mm']:.2f} | "
                  f"r180x={rf['r180x_mm']:.2f} r180y={rf['r180y_mm']:.2f} "
                  f"r180z={rf['r180z_mm']:.2f}")
            st = r["structural"]
            print(f"    struct: resid_vs_radius={st['resid_vs_radius_corr']:.4f} "
                  f"eigval_ratio={st['eigval_ratio']}")

            if (obj_name, fi) in viz_frames:
                save_viz(pred, gt_canonical, pred_rig, pred_sim, tag,
                         out_dir / f"viz_{tag}.png")

        results[obj_name] = obj_results

    # Save
    def _json_default(obj):
        if isinstance(obj, (np.floating, np.integer, np.bool_)):
            return obj.item()
        if isinstance(obj, np.ndarray):
            return obj.tolist()
        return str(obj)

    out_path = out_dir / "p3_1_b_results.json"
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(results, f, indent=2, ensure_ascii=False, default=_json_default)
    print(f"\nResults saved: {out_path}")

    # ========================================================================
    # Summary
    # ========================================================================
    print("\n" + "=" * 70)
    print("SUMMARY: Raw -> Translation -> Rigid -> Similarity (mean mm)")
    print("=" * 70)
    for domain_key in ["synthetic", "bottle", "bowl"]:
        entries = results[domain_key]
        raw_m = np.mean([r["raw"]["mean_mm"] for r in entries])
        t_m = np.mean([r["translation_aligned"]["mean_mm"] for r in entries])
        r_m = np.mean([r["rigid_aligned"]["mean_mm"] for r in entries])
        s_m = np.mean([r["similarity_aligned"]["mean_mm"] for r in entries])
        sc_m = np.mean([r["similarity_aligned"]["scale"] for r in entries])
        print(f"  {domain_key:12s}: raw={raw_m:7.2f} -> trans={t_m:7.2f} -> "
              f"rigid={r_m:7.2f} -> sim={s_m:7.2f} | scale={sc_m:.4f}")

    print("\nPer-frame rigid alignment rotation angles (deg):")
    for domain_key in ["synthetic", "bottle", "bowl"]:
        entries = results[domain_key]
        rots = [r["rigid_aligned"]["rot_deg"] for r in entries]
        dets_unc = [r["rigid_aligned"]["det_R_unc"] for r in entries]
        print(f"  {domain_key:12s}: rot={['%.1f' % v for v in rots]}")
        print(f"  {'':12s}  det_unc={['%.4f' % v for v in dets_unc]}")


if __name__ == "__main__":
    main()
