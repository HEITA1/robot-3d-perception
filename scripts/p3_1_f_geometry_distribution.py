"""P3.1-F: synthetic vs real geometry distribution audit (read-only).

Question: how large is the geometric distribution gap between what CoordNet
saw in training/validation (synthetic renders) and what it receives on real
YCB-V frames -- and can that gap directly support the stable ~176 deg
canonical orientation bias?

Everything measured at the point the network actually consumes:
  real      : mask -> deproject -> (frame_seed) sample 1024 -> normalize -> XYZ
  synthetic : stored npz (2048 raycast hit points) -> normalize -> XYZ
              (superset of the 1024-point training subsets; noted as caveat)

Comparisons (per group; real groups: bottle clean x4 / bottle 721 / bowl x5):
  A. camera-frame normalized XYZ: per-axis mean/std, radius percentiles,
     pre-normalization scale
  B. canonical-frame visibility: GT-transformed (real) or label (synthetic)
     point directions binned on the canonical sphere (6 elevation x 12
     azimuth); per-axis mean/std/skew of canonical coords
  C. domain gap: mean NN distance of each real sample's canonical points to
     the pooled synthetic canonical cloud, vs the synthetic-held-out baseline
     (val -> train pool). GT poses are evaluation-side only.
  D. real depth-quality stats: valid-depth fraction inside mask, depth
     outliers beyond robust bounds (mask leakage indicator).

No training, no pipeline changes, no new data. Outputs: JSON + histograms PNG.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import cv2
import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np
import open3d as o3d  # noqa: F402

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import p3_0_gate3 as g3  # noqa: E402
import yaml  # noqa: E402

from r3p.learn.coord_net import normalize_points  # noqa: E402
from r3p.geometry.camera import deproject  # noqa: E402

N_BINS_PHI, N_BINS_AZ = 6, 12  # elevation bands x azimuth bins = 72


def sph_hist(points: np.ndarray) -> np.ndarray:
    """Visibility histogram: direction from canonical centroid, binned on the sphere."""
    c = points.mean(axis=0)
    v = points - c
    r = np.linalg.norm(v, axis=1)
    unit = v / np.clip(r[:, None], 1e-12, None)
    phi = np.arcsin(np.clip(unit[:, 2], -1, 1))  # elevation from xy-plane
    az = np.arctan2(unit[:, 1], unit[:, 0])
    phi_b = np.clip(((phi + np.pi / 2) / np.pi * N_BINS_PHI).astype(int), 0, N_BINS_PHI - 1)
    az_b = np.clip(((az + np.pi) / (2 * np.pi) * N_BINS_AZ).astype(int), 0, N_BINS_AZ - 1)
    h = np.zeros((N_BINS_PHI, N_BINS_AZ))
    np.add.at(h, (phi_b, az_b), 1)
    return (h / max(h.sum(), 1)).ravel()


def ax_stats(points: np.ndarray) -> dict:
    c = points - points.mean(axis=0)
    skw = []
    for a in range(3):
        sd = c[:, a].std()
        skw.append(0.0 if sd < 1e-12 else float((c[:, a] ** 3).mean() / sd ** 3))
    r = np.linalg.norm(c, axis=1)
    return {
        "axis_mean": points.mean(axis=0).round(5).tolist(),
        "axis_std": points.std(axis=0).round(5).tolist(),
        "axis_skew": [round(x, 3) for x in skw],
        "radius_mean_mm": round(float(r.mean()) * 1e3, 2),
        "radius_p95_mm": round(float(np.percentile(r, 95)) * 1e3, 2),
        "radius_max_mm": round(float(r.max()) * 1e3, 2),
    }


def sample_real_frame(frame: dict, frame_seed: int, n_pts: int) -> dict:
    """Replicates scripts/p3_0_gate3.py sampling exactly (what the network saw)."""
    cam_xyz = deproject(frame["K"], frame["depth"], mask=frame["mask"])
    mask_px = int(frame["mask"].sum())
    valid = cam_xyz[:, 2] > 0
    n_valid = int(valid.sum())
    outliers = 0
    if n_valid > 0:
        z = cam_xyz[valid, 2]
        med = np.median(z)
        outliers = int((np.abs(z - med) > 0.25).sum())  # robust outlier indicator
    rng = np.random.default_rng(frame_seed)
    idx = rng.choice(len(cam_xyz), size=min(n_pts, len(cam_xyz)), replace=False)
    cam_sampled = cam_xyz[idx]
    cam_norm, _, scale = normalize_points(cam_sampled)
    T_gt = frame["gt_pose"]
    canon = (cam_sampled - T_gt[:3, 3]) @ T_gt[:3, :3]  # eval-side GT canonical
    return {
        "cam_norm": cam_norm, "scale_m": float(scale),
        "canonical": canon,
        "valid_depth_frac": round(n_valid / max(mask_px, 1), 4),
        "n_depth_outliers": outliers, "n_mask_px": mask_px,
    }


def main():
    cfg = yaml.safe_load(Path("configs/p3_0_gate3.yaml").read_text("utf-8"))
    data_root = Path(cfg["data"]["root"])
    out_root = Path("outputs") / "p3_1_f_geo_stats"
    out_root.mkdir(parents=True, exist_ok=True)

    results: dict = {"bins": f"{N_BINS_PHI} elev x {N_BINS_AZ} az"}

    # ---------------- synthetic reference pools ----------------
    def load_pool(split_dir: Path, limit: int) -> list[dict]:
        out = []
        for f in sorted(Path(split_dir).glob("sample_*.npz"))[:limit]:
            d = np.load(f)
            out.append({"xyz": d["xyz"].astype(np.float64),
                        "coords": d["coords"].astype(np.float64),
                        "file": f.name})
        return out

    val50 = load_pool(Path("data_synth/bottle/val"), 50)
    train200 = load_pool(Path("data_synth/bottle/train"), 200)
    assert val50 and train200, "synthetic pools empty (anti-false-pass)"
    print(f"synthetic pools: val={len(val50)}, train={len(train200)} (bottle)")

    synth_stats = {
        "val": {"normalized_xyz_ax_std": np.round(np.std([normalize_points(s["xyz"])[0] for s in val50], axis=(0, 1)), 4).tolist(),
                "scale_m_mean": round(float(np.mean([normalize_points(s["xyz"])[2] for s in val50])), 4),
                "canonical": ax_stats(np.concatenate([s["coords"] for s in val50])),
                "sph_hist_mean": sph_hist(np.concatenate([s["coords"] for s in val50])).round(4).tolist()},
        "train": {"scale_m_mean": round(float(np.mean([normalize_points(s["xyz"])[2] for s in train200])), 4),
                  "canonical": ax_stats(np.concatenate([s["coords"] for s in train200]))},
    }
    # synthetic canonical pool for NN domain gap (subsample for KDTree size)
    rng = np.random.default_rng(0)
    synth_pool = np.concatenate([s["coords"] for s in train200])
    synth_pool = synth_pool[rng.choice(len(synth_pool), size=50000, replace=False)]
    from scipy.spatial import cKDTree
    synth_tree = cKDTree(synth_pool)  # bottle pool (formal Gate 2 data)

    # bowl reference pool: informal P3.0-S byproduct (200 samples, no EXP number)
    # -- used read-only so bowl frames get a same-object reference; caveat in report
    bowl_tree = None
    if Path("data_synth/bowl/train").is_dir():
        bowl_train = load_pool(Path("data_synth/bowl/train"), 200)
        bowl_pool = np.concatenate([s["coords"] for s in bowl_train])
        bowl_pool = bowl_pool[rng.choice(len(bowl_pool), size=50000, replace=False)]
        bowl_tree = cKDTree(bowl_pool)
        results["bowl_pool_provenance"] = "data_synth/bowl (informal P3.0-S byproduct, see EXP-008 note)"

    # synthetic held-out baseline: each val sample's NN distance to the train pool
    nn_synth_base = []
    for s in val50:
        d, _ = synth_tree.query(s["coords"], k=1)
        nn_synth_base.append(float(d.mean()))
    synth_nn_baseline_m = float(np.mean(nn_synth_base))
    results["synthetic"] = {
        "n_val": len(val50), "n_train": len(train200),
        "scale_m_mean_val": synth_stats["val"]["scale_m_mean"],
        "scale_m_mean_train": synth_stats["train"]["scale_m_mean"],
        "val_normalized_xyz_ax_std": synth_stats["val"]["normalized_xyz_ax_std"],
        "val_canonical": synth_stats["val"]["canonical"],
        "nn_to_train_pool_mean_m": round(synth_nn_baseline_m, 6),
        "nn_baseline_note": "val(2048 pts) -> train pool(50k subsample); sampling-density floor",
    }
    print(f"synthetic: scale={synth_stats['val']['scale_m_mean']}m, "
          f"nn baseline={synth_nn_baseline_m * 1e3:.3f}mm")

    # ---------------- real frames ----------------
    groups = {
        "bottle_clean": (5, 50, [620, 653, 1044, 1113]),
        "bottle_721": (5, 50, [721]),
        "bowl": (13, 53, [1, 93, 138, 162, 247]),
    }
    hist_data = {"synthetic_val": sph_hist(np.concatenate([s["coords"] for s in val50]))}
    for gname, (obj_id, scene, frames) in groups.items():
        rows = []
        for i, im_id in enumerate(frames):
            frame_seed = cfg["ransac_umeyama"]["seed"] + i * 1000 + obj_id * 10000
            # gate3 seed formula uses enumerate index over the SAME frame list
            if gname == "bottle_clean":
                j = [620, 653, 721, 1044, 1113].index(im_id)
                frame_seed = cfg["ransac_umeyama"]["seed"] + j * 1000 + obj_id * 10000
            elif gname == "bottle_721":
                frame_seed = cfg["ransac_umeyama"]["seed"] + 2 * 1000 + obj_id * 10000
            frame = g3.load_frame(data_root, scene, im_id, obj_id)
            s = sample_real_frame(frame, frame_seed, cfg["model"]["n_points"])
            hist = sph_hist(s["canonical"])
            canon_pts = s["canonical"].copy()  # keep the raw array for NN query
            same_object_tree = synth_tree if obj_id == 5 else bowl_tree
            ref_hist_key = "synthetic_val" if obj_id == 5 else "synthetic_val_bowl"
            if ref_hist_key not in hist_data:
                if obj_id == 5:
                    hist_data[ref_hist_key] = hist_data["synthetic_val"]
                else:
                    hist_data[ref_hist_key] = sph_hist(np.concatenate(
                        [np.load(f)["coords"].astype(np.float64)
                         for f in sorted(Path("data_synth/bowl/val").glob("sample_*.npz"))]))
            s.update({"frame_id": f"{scene:06d}/{im_id:06d}",
                      "cam_norm_ax_std": s["cam_norm"].std(axis=0).round(4).tolist(),
                      "canonical": ax_stats(s["canonical"]),
                      "sph_hist": hist,
                      "sph_hist_l1_to_synth_mean": round(float(np.abs(hist - hist_data[ref_hist_key]).sum()), 4)})
            # NN domain gap: real canonical points -> SAME-OBJECT synthetic canonical pool
            d, _ = same_object_tree.query(canon_pts, k=1)
            s["nn_to_synth_pool_mean_m"] = round(float(d.mean()), 6)
            s["nn_domain_gap_ratio"] = round(float(d.mean()) / max(synth_nn_baseline_m, 1e-12), 2)
            rows.append(s)
            print(f"  [{gname}] {s['frame_id']}: scale={s['scale_m']:.3f}m valid_depth={s['valid_depth_frac']:.3f} "
                  f"outliers={s['n_depth_outliers']} nn_gap={s['nn_domain_gap_ratio']}x "
                  f"histL1={s['sph_hist_l1_to_synth_mean']}")
        results[gname] = {
            "frames": [{k: v for k, v in r.items()
                        if k not in ("cam_norm", "canonical", "sph_hist")} for r in rows],
            "cam_norm_ax_std_mean": np.round(np.mean([r["cam_norm_ax_std"] for r in rows], axis=0), 4).tolist(),
            "canonical_ax_std_mean": np.round(np.mean([r["canonical"]["axis_std"] for r in rows], axis=0), 4).tolist(),
            "nn_domain_gap_ratio_mean": round(float(np.mean([r["nn_domain_gap_ratio"] for r in rows])), 2),
            "sph_hist_l1_mean": round(float(np.mean([r["sph_hist_l1_to_synth_mean"] for r in rows])), 4),
            "valid_depth_frac_mean": round(float(np.mean([r["valid_depth_frac"] for r in rows])), 4),
        }
        hist_data[gname] = np.mean([r["sph_hist"] for r in rows], axis=0)

    # ---------------- histograms PNG ----------------
    fig, axes = plt.subplots(2, 3, figsize=(16, 8), dpi=130)
    panels = [("synthetic_val", "synthetic val (bottle)"), ("bottle_clean", "real bottle clean"),
              ("bottle_721", "real bottle 721"), ("bowl", "real bowl"), ]
    for ax, (key, title) in zip(axes.ravel(), panels):
        if key in hist_data:
            im = ax.imshow(hist_data[key].reshape(N_BINS_PHI, N_BINS_AZ), cmap="viridis",
                           aspect="auto", vmin=0, vmax=0.08)
            ax.set_title(title)
            fig.colorbar(im, ax=ax, shrink=0.8)
    for ax in axes.ravel()[4:]:
        ax.axis("off")
    fig.suptitle("canonical-frame visibility histograms (6 elev x 12 az; real uses eval-side GT)")
    fig.tight_layout()
    fig.savefig(out_root / "coverage_histograms.png")
    plt.close(fig)

    with open(out_root / "p3_1_f_results.json", "w", encoding="utf-8") as f:
        json.dump(results, f, indent=2, ensure_ascii=False)
    print(f"\nsaved: {out_root / 'p3_1_f_results.json'} and coverage_histograms.png")


if __name__ == "__main__":
    main()
