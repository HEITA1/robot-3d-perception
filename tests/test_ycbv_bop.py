"""Real-data tests for the BOP YCB-V interface (Phase 1).

Skipped automatically when the local subset is absent, so the suite stays
green on machines without data. Every sampling loop asserts an explicit
``checked > 0`` — a loop that silently runs zero iterations must fail, not pass.
"""

from pathlib import Path

import cv2
import numpy as np
import pytest

from r3p.datasets.ycbv_bop import DEFAULT_OBJ_IDS, YcbvBopDataset, load_obj_names
from r3p.geometry.camera import deproject, project
from r3p.geometry.se3 import apply as apply_T

DATA_ROOT = Path("data/ycbv")
pytestmark = pytest.mark.skipif(not (DATA_ROOT / "test").is_dir(), reason="local YCB-V subset not present")


@pytest.fixture(scope="module")
def dataset():
    return YcbvBopDataset(DATA_ROOT, obj_ids=DEFAULT_OBJ_IDS)


def test_obj_id_mapping(dataset):
    names = load_obj_names(DATA_ROOT)
    assert len(names) == 21
    assert names[5] == "006_mustard_bottle"
    assert names[13] == "024_bowl"
    assert dataset.obj_names[5] == "006_mustard_bottle"
    assert set(dataset._model_points) == set(DEFAULT_OBJ_IDS)


def test_index_nonempty_and_counts(dataset):
    """Explicit guard: the index must be non-empty and match the verified counts."""
    assert len(dataset) > 0
    frames_with = {5: 0, 13: 0}
    for scene in dataset.scene_ids:
        for insts in dataset._scene_gt[scene].values():
            for oid in frames_with:
                if any(i["obj_id"] == oid for i in insts):
                    frames_with[oid] += 1
    assert frames_with == {5: 150, 13: 150}


def test_single_instance_per_target_object(dataset):
    """The dict-per-object contract requires <=1 instance per object per frame."""
    for scene in dataset.scene_ids:
        for im_id, insts in dataset._scene_gt[scene].items():
            for oid in DEFAULT_OBJ_IDS:
                n = sum(1 for x in insts if x["obj_id"] == oid)
                assert n <= 1, f"object {oid} has {n} instances in {scene:06d}/{im_id}"


def test_observation_contract(dataset):
    obs = dataset[0]
    H, W = obs["depth"].shape
    assert (H, W) == (480, 640)
    assert obs["rgb"].shape == (H, W, 3) and obs["rgb"].dtype == np.uint8
    assert obs["depth"].dtype == np.float32 and obs["depth_scale"] == 0.1
    assert obs["K"].shape == (3, 3)
    assert set(obs["gt_poses"]) and set(obs["gt_poses"]) <= set(DEFAULT_OBJ_IDS)
    for oid, T in obs["gt_poses"].items():
        assert T.shape == (4, 4) and np.allclose(T[3], [0, 0, 0, 1])
        P = obs["model_points"][oid]
        assert P.shape[1] == 3 and len(P) > 0
        assert 0 < obs["visib_fract"][oid] <= 1.0
        assert obs["gt_instance_ids"][oid] >= 0


def test_depth_roundtrip_real_data(dataset):
    """depth -> point cloud -> reproject must recover pixels and depths exactly."""
    checked = 0
    step = max(1, len(dataset) // 6)
    for i in range(0, len(dataset), step):
        obs = dataset[i]
        K, depth = obs["K"], obs["depth"]
        mask = depth > 0
        if mask.sum() < 1000:
            continue
        pts = deproject(K, depth)
        uv, z = project(K, pts)
        v_idx, u_idx = np.nonzero(mask)
        assert np.abs(uv[:, 0] - u_idx).max() < 1e-6
        assert np.abs(uv[:, 1] - v_idx).max() < 1e-6
        assert np.abs(z - depth[v_idx, u_idx]).max() < 1e-9
        checked += 1
    assert checked > 0, "roundtrip check ran on zero frames"


def test_units_are_meters_not_millimeters(dataset):
    """Physical-plausibility guards against depth/translation/model unit mixing."""
    checked = 0
    for i in range(min(10, len(dataset))):
        obs = dataset[i]
        valid = obs["depth"][obs["depth"] > 0]
        if valid.size:
            near, far = np.percentile(valid, 1), np.percentile(valid, 99)
            assert 0.2 < near and far < 3.0, f"depth range [{near}, {far}] m looks wrong"
        for T in obs["gt_poses"].values():
            t_norm = float(np.linalg.norm(T[:3, 3]))
            assert 0.2 < t_norm < 3.0, f"translation norm {t_norm} looks like millimeters"
        checked += 1
    assert checked > 0, "unit check ran on zero frames"
    # model points must be in meters: cross-check against the official
    # models_info.json diameters (BOP defines diameter as the max pairwise
    # vertex distance, computed in mm). A mm/m mixing would blow this up 1000x.
    import json

    from scipy.spatial import ConvexHull
    from scipy.spatial.distance import cdist

    info = json.loads((DATA_ROOT / "models" / "models_info.json").read_text(encoding="utf-8"))

    def max_pairwise_distance(P: np.ndarray) -> float:
        hull_vertices = P[ConvexHull(P).vertices]
        return float(cdist(hull_vertices, hull_vertices).max())

    for oid, key in ((5, "5"), (13, "13")):
        expected = float(info[key]["diameter"]) * 1e-3
        got = max_pairwise_distance(dataset._model_points[oid])
        assert abs(got - expected) < 2e-3, f"obj {oid}: max pairwise distance {got:.4f} m != diameter {expected:.4f} m"


def test_gt_projection_matches_mask_visib(dataset):
    """GT pose + model points projected into the image must explain mask_visib."""
    checked = 0
    for i in range(len(dataset)):
        obs = dataset[i]
        if not obs["gt_poses"]:
            continue
        H, W = obs["depth"].shape
        for oid, T in obs["gt_poses"].items():
            mask = obs["masks"][oid]
            if mask.sum() < 100:
                continue
            P_cam = apply_T(T, obs["model_points"][oid])
            keep = P_cam[:, 2] > 1e-6
            uv, _ = project(obs["K"], P_cam[keep])
            uu = np.rint(uv[:, 0]).astype(int)
            vv = np.rint(uv[:, 1]).astype(int)
            inb = (uu >= 0) & (uu < W) & (vv >= 0) & (vv < H)
            assert inb.mean() > 0.95, (
                f"frame {obs['frame_id']} obj {oid}: only {inb.mean():.2%} of GT model in frame"
            )
            proj = np.zeros((H, W), dtype=np.uint8)
            proj[vv[inb], uu[inb]] = 1
            proj_d = cv2.dilate(proj, np.ones((5, 5), np.uint8)) > 0
            recall = float((mask & proj_d).sum()) / float(mask.sum())
            assert recall > 0.9, (
                f"frame {obs['frame_id']} obj {oid}: visible mask not explained by GT projection (recall={recall:.3f})"
            )
            checked += 1
        if checked >= 6:
            break
    assert checked > 0, "GT/mask consistency check ran on zero samples"
