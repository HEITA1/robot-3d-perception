"""P3.0-S: learning feasibility spike (minimal canonical-coordinate model).

Subcommands:
  gen    --obj-id 5 --mesh models/obj_000005.ply --n-train 200 --n-val 50
  gate1  --data data_synth/bottle   (train on 200 synthetic samples, frozen
          config, objective pass criteria: train ADD <= 5mm, aligned residual
          <= 3mm, final loss <= 20% of initial)

Frozen by approval: CoordNet 6-64-128-256-3 (~50k params), Adam lr=1e-3,
batch=16, <=500 epochs, per-point ADD loss with the render GT pose, fixed
seeds. No hyperparameter search, no extra DR, no test-frame information.
"""

from __future__ import annotations

import argparse
import json
import time
from pathlib import Path

import numpy as np

from ..learn.coord_net import CoordNet, normalize_points
from ..learn.synth_data import generate_samples
from ..learn.umeyama import umeyama_alignment
from ..pose.render_templates import TexturedModel

FROZEN = {"lr": 1e-3, "batch": 16, "epochs": 500, "points_per_sample": 1024,
          "gate1_add_mm": 5.0, "gate1_aligned_mm": 3.0, "gate1_loss_ratio": 0.2}


def cmd_gen(args) -> None:
    model = TexturedModel.from_ply(f"{args.data_root}/{args.mesh}")
    K = np.array([[570.0, 0, 319.5], [0, 570.0, 239.5], [0, 0, 1]])
    generate_samples(model, K, (480, 640), Path(args.out), "train",
                     args.n_train, seed=args.seed, obj_id=args.obj_id)
    generate_samples(model, K, (480, 640), Path(args.out), "val",
                     args.n_val, seed=args.seed + 1, obj_id=args.obj_id)


def _load_split(split_dir: Path) -> list[dict]:
    samples = []
    for f in sorted(Path(split_dir).glob("sample_*.npz")):
        d = np.load(f)
        samples.append({"xyz": d["xyz"].astype(np.float64), "rgb": d["rgb"],
                        "coords": d["coords"].astype(np.float64), "T": d["T"]})
    assert samples, f"no samples in {split_dir} (anti-false-pass)"
    return samples


def _batch_tensors(samples, rng, batch, n_points):
    """Sample a batch: per sample, n_points random surface points, normalized."""
    xs, cs, raws, Ts = [], [], [], []
    for s in rng.choice(len(samples), size=batch, replace=True):
        d = samples[s]
        idx = rng.choice(len(d["xyz"]), size=n_points, replace=len(d["xyz"]) < n_points)
        xyz = d["xyz"][idx]
        xn, _, _ = normalize_points(xyz)
        xs.append(np.concatenate([xn, d["rgb"][idx] / 255.0], axis=1))
        cs.append(d["coords"][idx])
        raws.append(xyz)
        Ts.append(d["T"])
    return (np.stack(xs).astype(np.float32), np.stack(cs).astype(np.float32),
            np.stack(raws).astype(np.float32), np.stack(Ts))


def _add_loss(pred, coords, raw_xyz, Ts):
    """Per-point ADD distance with the render GT pose (training/eval signal)."""
    R = Ts[:, :3, :3]
    t = Ts[:, :3, 3]
    p_cam = np.einsum("bij,bnj->bni", R, pred) + t[:, None, :]
    return np.linalg.norm(p_cam - raw_xyz, axis=2).mean()


def cmd_gate1(args) -> None:
    import torch

    torch.manual_seed(args.seed)
    rng = np.random.default_rng(args.seed)
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    log_lines = []

    def log(msg):
        print(msg, flush=True)
        log_lines.append(msg)

    train_samples = _load_split(Path(args.data) / "train")
    log(f"train samples: {len(train_samples)}")

    net = CoordNet()
    n_params = sum(p.numel() for p in net.parameters() if p.requires_grad)
    log(f"CoordNet params: {n_params}")
    opt = torch.optim.Adam(net.parameters(), lr=FROZEN["lr"])

    first_loss = last_loss = None
    started = time.time()
    for epoch in range(1, FROZEN["epochs"] + 1):
        order = rng.permutation(len(train_samples))
        epoch_loss, n_batches = 0.0, 0
        for b in range(0, len(order), FROZEN["batch"]):
            x, c, raw, T = _batch_tensors([train_samples[i] for i in order[b:b + FROZEN["batch"]]],
                                          rng, FROZEN["batch"], FROZEN["points_per_sample"])
            opt.zero_grad()
            pred = net(torch.from_numpy(x))
            p_cam = torch.einsum("bij,bnj->bni", torch.from_numpy(T[:, :3, :3]).float(), pred) \
                + torch.from_numpy(T[:, :3, 3]).float()[:, None, :]
            loss = ((p_cam - torch.from_numpy(raw).float()) ** 2).sum(dim=2).sqrt().mean()
            loss.backward()
            opt.step()
            epoch_loss += float(loss.detach())
            n_batches += 1
        epoch_loss /= max(n_batches, 1)
        if first_loss is None:
            first_loss = epoch_loss
        last_loss = epoch_loss
        if epoch == 1 or epoch % 50 == 0:
            log(f"epoch {epoch:4d}: train ADD loss = {epoch_loss*1e3:.2f} mm")
    log(f"training wall: {time.time() - started:.1f}s")

    # --- frozen Gate 1 evaluation on the training set ----------------------
    net.eval()
    eval_rng = np.random.default_rng(123)
    add_mm, aligned_mm = [], []
    for s in train_samples:
        idx = eval_rng.choice(len(s["xyz"]), size=FROZEN["points_per_sample"], replace=False)
        xyz = s["xyz"][idx]
        xn, _, _ = normalize_points(xyz)
        with torch.no_grad():
            pred = net(torch.from_numpy(np.concatenate([xn, s["rgb"][idx] / 255.0],
                                                       axis=1)[None].astype(np.float32)))[0].numpy()
        add_mm.append(float(_add_loss(pred[None], s["coords"][idx][None], xyz[None], s["T"][None])) * 1e3)
        R_a, t_a = umeyama_alignment(xyz, pred)
        aligned_mm.append(float(np.linalg.norm(xyz @ R_a.T + t_a - pred, axis=1).mean()) * 1e3)

    results = {
        "n_params": n_params,
        "train_loss_initial_mm": round(first_loss * 1e3, 3),
        "train_loss_final_mm": round(last_loss * 1e3, 3),
        "loss_ratio": round(last_loss / max(first_loss, 1e-12), 4),
        "train_add_mean_mm": round(float(np.mean(add_mm)), 3),
        "train_add_max_mm": round(float(np.max(add_mm)), 3),
        "aligned_residual_mean_mm": round(float(np.mean(aligned_mm)), 3),
        "aligned_residual_max_mm": round(float(np.max(aligned_mm)), 3),
        "criteria": {
            "train_add_le_5mm": bool(np.mean(add_mm) <= FROZEN["gate1_add_mm"]),
            "aligned_le_3mm": bool(np.mean(aligned_mm) <= FROZEN["gate1_aligned_mm"]),
            "loss_ratio_le_0p2": bool(last_loss <= FROZEN["gate1_loss_ratio"] * max(first_loss, 1e-12)),
        },
    }
    results["passed"] = all(results["criteria"].values())
    log(json.dumps(results, indent=2))
    torch.save(net.state_dict(), out / "coord_net_bottle.pt")
    with open(out / "gate1_metrics.json", "w", encoding="utf-8") as f:
        json.dump(results, f, indent=2)
    with open(out / "log.txt", "w", encoding="utf-8") as f:
        f.write("\n".join(log_lines) + "\n")
    log(f"GATE1: {'PASS' if results['passed'] else 'FAIL'}")


def cmd_sanity(args) -> None:
    """Mandatory data integrity gate before any training (added after the
    P3.0-S coordinate-frame bug): frame consistency + metric sanity on ALL
    samples of a split set."""
    from ..learn.umeyama import umeyama_alignment
    samples = _load_split(Path(args.data) / args.split)
    assert len(samples) > 0, "no samples (anti-false-pass)"
    frame_err, add_err, umey_err = [], [], []
    for s in samples:
        T, coords, xyz = s["T"], s["coords"], s["xyz"]
        frame_err.append(float(np.abs(xyz - (coords @ T[:3, :3].T + T[:3, 3])).max()))
        add_err.append(float(_add_loss(coords[None], coords[None], xyz[None], T[None])) * 1e3)
        R, t = umeyama_alignment(xyz, coords)  # perfect correspondence given
        umey_err.append(float(np.linalg.norm(xyz @ R.T + t - coords, axis=1).max()) * 1e3)
    res = {
        "n_samples": len(samples),
        "frame_consistency_max_err_m": float(np.max(frame_err)),
        "add_gt_pose_mean_mm": float(np.mean(add_err)),
        "add_gt_pose_max_mm": float(np.max(add_err)),
        "umeyama_gt_corr_max_err_mm": float(np.max(umey_err)),
    }
    # tolerances absorb float16 label rounding (~0.01-0.04mm); the coordinate-
    # frame bug this gate guards against produces errors of ~600-870mm
    res["passed"] = bool(res["frame_consistency_max_err_m"] < 1e-3
                         and res["add_gt_pose_max_mm"] < 0.1
                         and res["umeyama_gt_corr_max_err_mm"] < 0.1)
    print(json.dumps(res, indent=2))
    print(f"DATA SANITY: {'PASS' if res['passed'] else 'FAIL'}")
    assert res["passed"], "data sanity check FAILED — training must not start"


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="cmd", required=True)
    g = sub.add_parser("gen")
    g.add_argument("--data-root", default="data/ycbv")
    g.add_argument("--mesh", default="models/obj_000005.ply")
    g.add_argument("--obj-id", type=int, default=5)
    g.add_argument("--n-train", type=int, default=200)
    g.add_argument("--n-val", type=int, default=50)
    g.add_argument("--seed", type=int, default=0)
    g.add_argument("--out", default="data_synth/bottle")
    t = sub.add_parser("gate1")
    t.add_argument("--data", default="data_synth/bottle")
    t.add_argument("--seed", type=int, default=0)
    t.add_argument("--out", default="outputs/p3_0/gate1")
    y = sub.add_parser("sanity")
    y.add_argument("--data", default="data_synth/bottle")
    y.add_argument("--split", default="train")
    args = parser.parse_args()
    {"gen": cmd_gen, "gate1": cmd_gate1, "sanity": cmd_sanity}[args.cmd](args)


if __name__ == "__main__":
    main()
