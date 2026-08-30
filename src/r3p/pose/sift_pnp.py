"""SIFT + PnP-RANSAC: the P2.0 classical baseline building blocks.

Reference construction (offline, one-time): SIFT keypoints detected inside the
GT visible mask of a few reference frames are lifted to the MODEL frame via
depth back-projection and the inverse GT pose. At inference, query SIFT
keypoints are matched against this library, yielding 2D(image, px) <->
3D(model, m) correspondences for cv2.solvePnPRansac.

Units & conventions (the whole pipeline speaks one language):
  - model points, translations: METERS (model frame origin = bbox center)
  - image points: PIXELS; K from scene_camera.json, no distortion (BOP ycbv)
  - T_cam_model = [R | t] maps model -> camera, identical to the GT convention.
    cv2.solvePnP returns exactly this decomposition (p_cam = R @ p_obj + t).
"""

from __future__ import annotations

from dataclasses import dataclass, field

import cv2
import numpy as np

from ..geometry.camera import project
from ..geometry.se3 import apply as apply_T
from ..geometry.se3 import invert, make_T


# --------------------------------------------------------------------------- #
# Reference library (offline construction from GT-annotated frames)
# --------------------------------------------------------------------------- #
@dataclass
class ReferenceLibrary:
    """SIFT descriptors with model-frame 3D points lifted from reference frames."""

    obj_id: int
    descriptors: np.ndarray  # (N, 128) float32
    points_model: np.ndarray  # (N, 3) meters, model frame
    frame_ids: list[str] = field(default_factory=list)
    per_frame_counts: list[int] = field(default_factory=list)
    # per-frame debug payload for drawMatches (frame_id -> (rgb, keypoints, row_range))
    segments: dict = field(default_factory=dict)

    def __len__(self) -> int:
        return len(self.descriptors)


def _lift_keypoints_to_model(rgb, depth, mask, K, T_cam_model, sift):
    """SIFT on the full image; keep keypoints inside the visible mask whose depth
    is valid; back-project them to the camera frame and map to the model frame.
    Depth is read at the rounded pixel (sensor resolution); projection uses the
    exact float keypoint location."""
    keypoints, descriptors = sift.detectAndCompute(rgb, None)
    if descriptors is None or len(keypoints) == 0:
        return np.zeros((0, 128), np.float32), np.zeros((0, 3)), [], []

    u = np.array([kp.pt[0] for kp in keypoints])
    v = np.array([kp.pt[1] for kp in keypoints])
    ui = np.rint(u).astype(int)
    vi = np.rint(v).astype(int)
    H, W = depth.shape
    in_bounds = (ui >= 0) & (ui < W) & (vi >= 0) & (vi < H)
    z = np.zeros(len(keypoints))
    z[in_bounds] = depth[vi[in_bounds], ui[in_bounds]]
    keep = in_bounds & (z > 0) & mask[vi.clip(0, H - 1), ui.clip(0, W - 1)]

    idx = np.nonzero(keep)[0]
    x = (u[idx] - K[0, 2]) * z[idx] / K[0, 0]
    y = (v[idx] - K[1, 2]) * z[idx] / K[1, 1]
    p_cam = np.stack([x, y, z[idx]], axis=1)
    T_model_cam = invert(T_cam_model)
    p_model = p_cam @ T_model_cam[:3, :3].T + T_model_cam[:3, 3]
    return descriptors[idx], p_model, keypoints, idx


def build_reference(dataset, ref_scene: int, obj_id: int, n_ref_frames: int = 3, sift=None) -> ReferenceLibrary:
    """Build the SIFT<->model-frame library from the top-`n_ref_frames` frames of
    `ref_scene`, ranked by visib_fract (tie-break: smaller im_id). Deterministic."""
    sift = sift or cv2.SIFT_create()
    candidates = []
    for i in range(len(dataset)):
        obs = dataset[i]
        visib = obs["visib_fract"].get(obj_id)
        if visib is not None:
            candidates.append((float(visib), int(obs["im_id"]), obs))
    if not candidates:
        raise RuntimeError(f"scene {ref_scene} contains no frames with object {obj_id}")
    candidates.sort(key=lambda t: (-t[0], t[1]))
    chosen = candidates[:n_ref_frames]

    all_desc, all_pts = [], []
    lib = ReferenceLibrary(obj_id=obj_id, descriptors=np.zeros((0, 128), np.float32), points_model=np.zeros((0, 3)))
    row0 = 0
    for visib, im_id, obs in chosen:
        desc, pts, kps, idx = _lift_keypoints_to_model(
            obs["rgb"], obs["depth"], obs["masks"][obj_id], obs["K"], obs["gt_poses"][obj_id], sift
        )
        all_desc.append(desc)
        all_pts.append(pts)
        lib.frame_ids.append(obs["frame_id"])
        lib.per_frame_counts.append(len(pts))
        ref_kps = [kps[j] for j in idx]
        lib.segments[obs["frame_id"]] = {
            "rgb": obs["rgb"],
            "keypoints": ref_kps,
            "row_range": (row0, row0 + len(pts)),
            "visib_fract": visib,
        }
        row0 += len(pts)
    lib.descriptors = np.concatenate(all_desc, axis=0)
    lib.points_model = np.concatenate(all_pts, axis=0)
    return lib


# --------------------------------------------------------------------------- #
# Query matching
# --------------------------------------------------------------------------- #
@dataclass
class MatchResult:
    points_model: np.ndarray  # (M, 3) meters, model frame (after ratio test)
    points_image: np.ndarray  # (M, 2) px, query image
    n_query_keypoints: int
    n_library: int
    n_matches_good: int  # after Lowe ratio test
    n_matches_in_mask: int  # good matches whose query keypoint is inside the GT mask
    matches: list = field(default_factory=list)  # cv2.DMatch list (good, not only in-mask)
    query_keypoints: list = field(default_factory=list)
    in_mask: np.ndarray | None = None  # (M,) bool aligned with points_model/points_image


def match_query(rgb_query, library: ReferenceLibrary, mask_query=None, ratio: float = 0.75, sift=None) -> MatchResult:
    """Match query SIFT against the library; Lowe ratio test; optional GT-mask
    filtering of the query keypoints (D2: segmentation may be assumed)."""
    sift = sift or cv2.SIFT_create()
    query_kp, query_desc = sift.detectAndCompute(rgb_query, None)
    n_query = 0 if query_kp is None else len(query_kp)
    empty = MatchResult(
        points_model=np.zeros((0, 3)), points_image=np.zeros((0, 2)),
        n_query_keypoints=n_query, n_library=len(library), n_matches_good=0, n_matches_in_mask=0,
        query_keypoints=[] if query_kp is None else list(query_kp),
    )
    if n_query == 0 or len(library) < 2:
        return empty

    matcher = cv2.BFMatcher()
    knn = matcher.knnMatch(query_desc, library.descriptors, k=2)
    good = []
    for pair in knn:
        if len(pair) == 2 and pair[0].distance < ratio * pair[1].distance:
            good.append(pair[0])
    if not good:
        return empty

    pts2d = np.array([query_kp[m.queryIdx].pt for m in good], dtype=np.float64)
    pts3d = library.points_model[np.array([m.trainIdx for m in good])]

    in_mask = None
    if mask_query is not None:
        ui = np.rint(pts2d[:, 0]).astype(int)
        vi = np.rint(pts2d[:, 1]).astype(int)
        H, W = mask_query.shape
        inb = (ui >= 0) & (ui < W) & (vi >= 0) & (vi < H)
        in_mask = np.zeros(len(good), dtype=bool)
        in_mask[inb] = mask_query[vi[inb], ui[inb]]

    return MatchResult(
        points_model=pts3d,
        points_image=pts2d,
        n_query_keypoints=n_query,
        n_library=len(library),
        n_matches_good=len(good),
        n_matches_in_mask=int(in_mask.sum()) if in_mask is not None else len(good),
        matches=good,
        query_keypoints=list(query_kp),
        in_mask=in_mask,
    )


# --------------------------------------------------------------------------- #
# PnP-RANSAC
# --------------------------------------------------------------------------- #
@dataclass
class PnpResult:
    success: bool  # solver success (returned a pose with enough inliers)
    T: np.ndarray | None  # (4, 4) T_cam_model, meters
    inlier_indices: np.ndarray  # indices into the input correspondence arrays
    n_inliers: int
    residual_px: float  # mean reprojection residual over inliers (inf if failed)

    @classmethod
    def failed(cls) -> "PnpResult":
        return cls(success=False, T=None, inlier_indices=np.zeros(0, dtype=int), n_inliers=0, residual_px=float("inf"))


def solve_pnp(
    points_model: np.ndarray,
    points_image: np.ndarray,
    K: np.ndarray,
    min_inliers: int = 6,
    reproj_error_px: float = 3.0,
    iterations: int = 10000,
    confidence: float = 0.99,
) -> PnpResult:
    """solvePnPRansac on model-frame 3D (m) <-> image 2D (px) correspondences.

    The reprojection residual is computed by OUR project() on purpose: if the
    OpenCV convention and our SE(3) convention ever diverge, this number
    explodes and the synthetic regression test fails.
    """
    if len(points_model) < max(4, min_inliers):
        return PnpResult.failed()

    ok, rvec, tvec, inliers = cv2.solvePnPRansac(
        objectPoints=points_model.astype(np.float64),
        imagePoints=points_image.astype(np.float64),
        cameraMatrix=K,
        distCoeffs=None,
        flags=cv2.SOLVEPNP_EPNP,
        reprojectionError=reproj_error_px,
        iterationsCount=iterations,
        confidence=confidence,
    )
    if not ok or inliers is None or len(inliers) < min_inliers:
        return PnpResult.failed()

    R = cv2.Rodrigues(rvec)[0]
    T = make_T(R, tvec.reshape(3))
    inliers = np.asarray(inliers).reshape(-1)

    # Refine on all RANSAC inliers (warm start from the RANSAC solution); without
    # this the returned pose is a minimal-subset estimate with ~1e-6-level error.
    try:
        ok2, rvec2, tvec2 = cv2.solvePnP(
            objectPoints=points_model[inliers].astype(np.float64),
            imagePoints=points_image[inliers].astype(np.float64),
            cameraMatrix=K,
            distCoeffs=None,
            rvec=rvec,
            tvec=tvec,
            useExtrinsicGuess=True,
            flags=cv2.SOLVEPNP_ITERATIVE,
        )
        if ok2:
            R = cv2.Rodrigues(rvec2)[0]
            T = make_T(R, tvec2.reshape(3))
    except cv2.error:
        pass  # keep the RANSAC pose

    uv_proj, _ = project(K, points_model[inliers] @ R.T + T[:3, 3])
    residual = float(np.linalg.norm(uv_proj - points_image[inliers], axis=1).mean())
    return PnpResult(success=True, T=T, inlier_indices=inliers, n_inliers=len(inliers), residual_px=residual)


# --------------------------------------------------------------------------- #
# Reference library verification (read-only diagnostics; do not affect results)
# --------------------------------------------------------------------------- #
def verify_reference_consistency(dataset, library: ReferenceLibrary, max_frames: int | None = None) -> dict:
    """Roundtrip check on (a subset of) the reference frames:
    model 3D -> GT -> camera 3D -> project must land back on the source SIFT
    keypoint pixels. Catches lifting/convention bugs. Read-only diagnostics."""
    rng = np.random.default_rng(0)
    frame_ids = list(library.frame_ids)
    if max_frames is not None and len(frame_ids) > max_frames:
        frame_ids = sorted(rng.choice(frame_ids, size=max_frames, replace=False).tolist())
    errs = []
    checked = 0
    for frame_id in frame_ids:
        scene, im = frame_id.split("/")
        cam_entry = dataset._scene_camera[int(scene)][str(int(im))]
        K = np.array(cam_entry["cam_K"], dtype=np.float64).reshape(3, 3)
        inst = next(i for i in dataset._scene_gt[int(scene)][str(int(im))] if i["obj_id"] == library.obj_id)
        T = make_T(np.array(inst["cam_R_m2c"]).reshape(3, 3),
                   np.array(inst["cam_t_m2c"]).reshape(3) * 1e-3)
        seg = library.segments[frame_id]
        r0, r1 = seg["row_range"]
        uv, _ = project(K, apply_T(T, library.points_model[r0:r1]))
        kp_uv = np.array([k.pt for k in seg["keypoints"]])
        errs.append(np.linalg.norm(uv - kp_uv, axis=1))
        checked += 1
    assert checked > 0, "consistency check sampled zero frames (anti-false-pass)"
    errs = np.concatenate(errs)
    assert len(errs) > 0, "consistency check sampled zero points (anti-false-pass)"
    return {"n_frames_checked": checked, "n_points": int(len(errs)),
            "max_err_px": float(errs.max()), "mean_err_px": float(errs.mean())}


def reference_statistics(library: ReferenceLibrary) -> dict:
    """Library composition stats. Exact-duplicate descriptor count is reported
    as-is (no dedup logic exists by design)."""
    counts = np.array(library.per_frame_counts, dtype=np.int64)
    uniq = np.unique(library.descriptors, axis=0).shape[0] if len(library) else 0
    return {
        "n_frames": len(library.frame_ids),
        "n_descriptors": int(len(library)),
        "per_frame_min": int(counts.min()) if len(counts) else 0,
        "per_frame_median": float(np.median(counts)) if len(counts) else 0.0,
        "per_frame_max": int(counts.max()) if len(counts) else 0,
        "duplicate_descriptors": int(len(library) - uniq),
    }
