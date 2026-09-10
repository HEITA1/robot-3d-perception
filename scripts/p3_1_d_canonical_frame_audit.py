"""P3.1-D: canonical frame convention audit (read-only).

Question: is the canonical frame of the synthetic training labels (renderer
output, parsed by TexturedModel's manual ASCII PLY reader) IDENTICAL to the
BOP model frame (Open3D reader, used by evaluation)?

Checks:
  1. Model source: sha256, headers, vertex counts, bboxes, diameters for
     obj_000005 / obj_000013 via BOTH readers (manual vs Open3D).
  2. Reader equivalence: max |manual_vertices - open3d_vertices|.
  3. Training-label correspondence: for K stored .npz samples per object,
     nearest-neighbor distance from label points (coords) to the BOP vertex
     cloud, then Kabsch(pred-frame -> BOP-frame) on NN-matched pairs:
     R should be ~identity if frames are identical. Report rot_deg, |t|,
     scale, det(R) -- and explicitly compare R against the P3.1-C rotation.
  4. Discriminator: NN distance from label points to BOP vertices with and
     without applying the P3.1-C correction rotation R_y(-176.5 deg).
     If the frames were mismatched by that rotation, applying it would shrink
     distances; if identical, it inflates them.

No model/checkpoint/training/pipeline changes. GT poses are not used at all
(BOP model frame is defined by the mesh file, not by per-frame poses).
"""

from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

import numpy as np
import open3d as o3d
from scipy.spatial import cKDTree

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from r3p.learn.coord_net import normalize_points  # noqa: F401  (documented convention)
from r3p.learn.umeyama import umeyama_alignment
from r3p.pose.render_templates import TexturedModel

MM_TO_M = 1e-3
OBJECTS = {5: "obj_000005.ply", 13: "obj_000013.ply"}
DATA_SYNTH = {"5": Path("data_synth/bottle/train"), "13": Path("data_synth/bowl/train")}
P31C_ANGLE_DEG = -176.5  # the P3.1-C pre-registered correction (comparison only)


def rot_y_deg(angle_deg: float) -> np.ndarray:
    th = np.deg2rad(angle_deg)
    c, s = np.cos(th), np.sin(th)
    return np.array([[c, 0.0, s], [0.0, 1.0, 0.0], [-s, 0.0, c]])


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def manual_parse_vertices(path: Path) -> tuple[np.ndarray, dict]:
    """The EXACT parser TexturedModel.from_ply uses (duplicated here so the
    audit is independent of importing the class)."""
    with open(path, "rb") as f:
        raw = f.read()
    header_end = raw.index(b"end_header") + len(b"end_header\n")
    header = raw[:header_end].decode("ascii")
    n_vertex = int(next(l for l in header.splitlines() if l.startswith("element vertex")).split()[2])
    n_face = int(next(l for l in header.splitlines() if l.startswith("element face")).split()[2])
    props = [l.split()[-1] for l in header.splitlines() if l.strip().startswith("property")]
    lines = raw[header_end:].decode("ascii").splitlines()
    vuv = np.loadtxt(lines[:n_vertex], dtype=np.float64)
    meta = {"n_vertex": n_vertex, "n_face": n_face, "vertex_properties": props,
            "ascii": "format ascii" in header,
            "texture_comment": next((l for l in header.splitlines() if "TextureFile" in l), "").strip()}
    return vuv[:, 0:3] * MM_TO_M, meta


def diameter(points: np.ndarray) -> float:
    from scipy.spatial import ConvexHull
    from scipy.spatial.distance import cdist
    hull = points[ConvexHull(points).vertices]
    return float(cdist(hull, hull).max())


def bbox(points: np.ndarray) -> dict:
    return {"min": points.min(axis=0).round(6).tolist(),
            "max": points.max(axis=0).round(6).tolist(),
            "extent": (points.max(axis=0) - points.min(axis=0)).round(6).tolist()}


def audit_object(obj_id: int, ply_name: str, results: dict) -> None:
    ply_path = Path("data/ycbv/models") / ply_name
    print(f"\n{'=' * 66}\nCHECK 1 — model source: obj {obj_id:02d} ({ply_name})\n{'=' * 66}")

    manual_v, meta = manual_parse_vertices(ply_path)
    o3d_mesh = o3d.io.read_triangle_mesh(str(ply_path))
    o3d_v = np.asarray(o3d_mesh.vertices) * MM_TO_M  # o3d returns file units (mm)

    check1 = {
        "ply_sha256": sha256(ply_path),
        "manual_parse": {"vertex_count": meta["n_vertex"], "face_count": meta["n_face"],
                         "vertex_properties_in_file_order": meta["vertex_properties"],
                         "ascii_format": meta["ascii"], "texture_comment": meta["texture_comment"],
                         "bbox_m": bbox(manual_v), "diameter_m": round(diameter(manual_v), 6)},
        "open3d_read": {"vertex_count": len(o3d_v),
                        "bbox_m": bbox(o3d_v), "diameter_m": round(diameter(o3d_v), 6)},
        "reader_equivalence_max_abs_diff_m": float(np.abs(manual_v - o3d_v).max()),
    }
    check1["readers_identical"] = bool(check1["reader_equivalence_max_abs_diff_m"] < 1e-9
                                       and manual_v.shape == o3d_v.shape)
    print(f"  sha256: {check1['ply_sha256'][:16]}...")
    print(f"  vertex properties (file order): {meta['vertex_properties']}")
    print(f"  manual vs open3d: n={meta['n_vertex']}/{len(o3d_v)}, "
          f"max|diff|={check1['reader_equivalence_max_abs_diff_m']:.3e} m -> "
          f"{'IDENTICAL' if check1['readers_identical'] else 'MISMATCH'}")
    print(f"  bbox extent (m): {check1['manual_parse']['bbox_m']['extent']}")
    print(f"  diameter (m): {check1['manual_parse']['diameter_m']}")
    results[f"obj_{obj_id:02d}_check1_model_source"] = check1

    # ------------------------------------------------------------------
    print(f"\nCHECK 4 — training labels vs BOP model frame: obj {obj_id:02d}")
    tree = cKDTree(o3d_v)
    k_samples = 12
    files = sorted(DATA_SYNTH[str(obj_id)].glob("sample_*.npz"))[:k_samples]
    assert files, f"no synthetic samples for obj {obj_id} (anti-false-pass)"

    nn_ident, nn_rotfix = [], []
    R_list, t_list = [], []
    for f in files:
        d = np.load(f)
        coords = d["coords"].astype(np.float64)  # the ACTUAL training labels
        dist_ident = tree.query(coords, k=1)[0]  # label -> nearest BOP vertex
        nn_ident.append(dist_ident)

        # Kabsch(label -> BOP vertex of nearest neighbor) on matched pairs
        nn_idx = tree.query(coords, k=1)[1]
        R, t = umeyama_alignment(coords, o3d_v[nn_idx])
        R_list.append(R)
        t_list.append(t)

        # discriminator: same labels under the P3.1-C rotation
        coords_rot = (rot_y_deg(P31C_ANGLE_DEG) @ coords.T).T
        nn_rotfix.append(tree.query(coords_rot, k=1)[0])

    nn_ident = np.concatenate(nn_ident)
    nn_rotfix = np.concatenate(nn_rotfix)

    # per-sample Kabsch rotations vs identity
    rots_deg = []
    for R in R_list:
        cos = np.clip((np.trace(R) - 1) / 2, -1, 1)
        rots_deg.append(float(np.degrees(np.arccos(cos))))
    t_norms = [float(np.linalg.norm(t)) for t in t_list]
    dets = [float(np.linalg.det(R)) for R in R_list]
    scales = []
    for f, R, t in zip(files, R_list, t_list):
        d = np.load(f)
        coords = d["coords"].astype(np.float64)
        nn_idx = tree.query(coords, k=1)[1]
        src_c = coords - coords.mean(axis=0)
        dst_c = o3d_v[nn_idx] - o3d_v[nn_idx].mean(axis=0)
        var_src = float((src_c ** 2).sum())
        var_dst = float((dst_c ** 2).sum())
        scales.append(round(np.sqrt(var_dst / max(var_src, 1e-18)), 6))

    # explicit comparison against the P3.1-C rotation
    R_p31c = rot_y_deg(P31C_ANGLE_DEG)
    dev_from_p31c = [float(np.degrees(np.arccos(np.clip((np.trace(R_p31c.T @ R) - 1) / 2, -1, 1))))
                     for R in R_list]

    check4 = {
        "n_samples_checked": len(files),
        "nn_dist_label_to_bop_identity_m": {
            "mean": round(float(nn_ident.mean()), 9), "median": round(float(np.median(nn_ident)), 9),
            "p99": round(float(np.percentile(nn_ident, 99)), 6), "max": round(float(nn_ident.max()), 6),
        },
        "nn_dist_label_to_bop_under_p31c_rotation_m": {
            "mean": round(float(nn_rotfix.mean()), 6), "min": round(float(nn_rotfix.min()), 6),
        },
        "kabsch_label_to_bop": {
            "rot_deg_min": round(min(rots_deg), 4), "rot_deg_max": round(max(rots_deg), 4),
            "trans_norm_max_m": round(max(t_norms), 9),
            "det_R_min": round(min(dets), 6), "det_R_max": round(max(dets), 6),
            "scale_min": min(scales), "scale_max": max(scales),
        },
        "kabsch_rotation_distance_from_p31c_rotation_deg": {
            "min": round(min(dev_from_p31c), 3), "max": round(max(dev_from_p31c), 3),
        },
    }
    # "worse" = the P3.1-C rotation inflates NN distances by >=5x over identity
    # (identity distances are set by surface sampling density, ~1mm here)
    check4["p31c_rotation_inflates_nn"] = bool(
        nn_rotfix.mean() > 5 * max(nn_ident.mean(), 1e-12))
    check4["nn_inflation_factor"] = round(float(nn_rotfix.mean() / max(nn_ident.mean(), 1e-12)), 2)
    # verdict rests on the Kabsch fit (rotation/translation/scale/reflection)
    # plus the P3.1-C inflation discriminator. NN-identity distances are NOT
    # part of the verdict: 2048 samples vs ~10k vertices put the sampling-
    # density floor at ~1mm regardless of frame agreement.
    check4["verdict_frames_identical"] = bool(
        check4["kabsch_label_to_bop"]["rot_deg_max"] < 1.0            # R ~ I
        and check4["kabsch_label_to_bop"]["trans_norm_max_m"] < 1e-3  # |t| < 1mm
        and abs(check4["kabsch_label_to_bop"]["scale_max"] - 1.0) < 1e-2
        and check4["kabsch_label_to_bop"]["det_R_min"] > 0.999        # no reflection
        and check4["p31c_rotation_inflates_nn"])                      # wrong rotation inflates

    print(f"  samples checked: {len(files)} x {coords.shape[0]} label points")
    print(f"  NN(label -> BOP vertex), identity frame: mean={nn_ident.mean():.3e} m, "
          f"max={nn_ident.max():.3e} m")
    print(f"  NN(label -> BOP vertex), after P3.1-C rotation: mean={nn_rotfix.mean():.4f} m "
          f"(x{check4['nn_inflation_factor']} vs identity -> "
          f"{'INFLATED: frames identical' if check4['p31c_rotation_inflates_nn'] else 'REDUCED: frames mismatched'})")
    print(f"  Kabsch(label->BOP): rot {min(rots_deg):.4f}-{max(rots_deg):.4f} deg, "
          f"|t| <= {max(t_norms):.2e} m, det(R) {min(dets):.3f}-{max(dets):.3f}, "
          f"scale {min(scales)}-{max(scales)}")
    print(f"  Kabsch R distance from P3.1-C rotation: {min(dev_from_p31c):.1f}-{max(dev_from_p31c):.1f} deg")
    results[f"obj_{obj_id:02d}_check4_labels_vs_bop"] = check4


def main():
    print(__doc__)
    results = {
        "p31c_correction_used_for_comparison_only": {
            "angle_deg": P31C_ANGLE_DEG, "axis": "canonical Y",
            "note": "used ONLY as a discriminator in check 4; never as a correction",
        },
    }
    for obj_id, ply in OBJECTS.items():
        audit_object(obj_id, ply, results)

    # ------------------------------------------------------------------
    # Check 2/3 are code-path documentation; asserted here so the report
    # quotes live code, not memory.
    print(f"\n{'=' * 66}\nCHECK 2/3 — coordinate source & transform chain (code assertions)\n{'=' * 66}")
    import inspect
    from r3p.learn import synth_data
    from r3p.pose import render_templates
    src_gen = inspect.getsource(synth_data.generate_samples)
    assert "apply_T(tpl.T_cam_model, tpl.points_model[choose])" in src_gen
    assert "coords=tpl.points_model[choose]" in src_gen
    src_render = inspect.getsource(render_templates.render_view)
    assert "points = (np.broadcast_to(eye, dirs.shape) + dirs * t_hit[..., None])" in src_render
    src_from_ply = inspect.getsource(render_templates.TexturedModel.from_ply)
    assert "vertices_m = vuv[:, 0:3] * MM_TO_M" in src_from_ply
    assert "tm.vertex.positions = o3d.core.Tensor(vertices_m.astype(np.float32))" in src_from_ply
    print("  synth label formula : coords = raycast hit point in MODEL frame "
          "(= eye + t_hit * dir, mesh loaded mm->m, no other transform)")
    print("  synth input formula : xyz_cam = T_cam_model @ coords (T from _camera_pose, world->cam)")
    print("  BOP evaluation      : model_points = o3d(obj_*.ply) * 1e-3; "
          "p_cam = cam_R_m2c @ p_model + cam_t_m2c (row-major 9 -> 3x3, t mm->m)")
    print("  assertions on live code passed (see source refs in report)")

    results["check2_coordinate_source"] = {
        "labels": "raycast hit positions in the model/world frame "
                  "(points = eye + t_hit * dir_world); mesh vertices loaded mm->m, "
                  "no other transform applied -> label frame == parsed-PLY frame",
        "inputs": "xyz_cam = T_cam_model @ coords, T_cam_model from _camera_pose (world->cam)",
        "bop_evaluation": "model_points = Open3D(obj_*.ply) * 1e-3 (same file); "
                          "GT: p_cam = R_m2c @ p_model + t_m2c (row-major, mm->m)",
    }
    results["overall_verdict"] = {
        "case_a_frame_mismatch": any(not v.get("verdict_frames_identical", True)
                                     for k, v in results.items() if "check4" in k),
        "case_b_frames_identical": all(v.get("verdict_frames_identical", False)
                                       for k, v in results.items() if "check4" in k),
    }

    out = Path("outputs/p3_1_d_canonical_frame_audit")
    out.mkdir(parents=True, exist_ok=True)
    with open(out / "p3_1_d_results.json", "w", encoding="utf-8") as f:
        json.dump(results, f, indent=2)
    print(f"\nsaved: {out / 'p3_1_d_results.json'}")
    print(f"OVERALL: Case A (mismatch) = {results['overall_verdict']['case_a_frame_mismatch']} | "
          f"Case B (identical) = {results['overall_verdict']['case_b_frames_identical']}")


if __name__ == "__main__":
    main()
