"""Minimal synthetic data generation for P3.0-S (renderer-derived labels).

Each sample stores a fixed set of 2048 surface points of the textured model
rendered from one random view:

    xyz     : (P, 3) camera-frame points (meters)
    rgb     : (P, 3) uint8 surface colors at those points
    coords  : (P, 3) canonical (model-frame) XYZ — exact labels from the renderer
    T       : (4, 4) render camera pose T_cam_model (training loss only)

No YCB-V ground truth is involved anywhere.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np

from ..pose.render_templates import TexturedModel, render_view


def generate_samples(model: TexturedModel, K: np.ndarray, image_size, out_dir: Path,
                     split: str, n_samples: int, seed: int, obj_id: int,
                     n_points: int = 2048, radius_range: tuple[float, float] = (0.7, 1.1)) -> Path:
    rng = np.random.default_rng(seed)
    out = Path(out_dir) / split
    out.mkdir(parents=True, exist_ok=True)
    generated = 0
    attempts = 0
    while generated < n_samples:
        attempts += 1
        assert attempts < n_samples * 20, "too many render attempts without usable views"
        direction = rng.normal(size=3)
        direction /= np.linalg.norm(direction)
        radius = float(rng.uniform(*radius_range))
        tpl = render_view(model, K, image_size, direction, radius=radius, shading=True)
        if len(tpl.points_model) < n_points:
            continue
        choose = rng.choice(len(tpl.points_model), size=n_points, replace=False)
        rgb = tpl.rgb[tpl.pixels[choose][:, 1].astype(int), tpl.pixels[choose][:, 0].astype(int)]
        np.savez_compressed(
            out / f"sample_{generated:04d}.npz",
            xyz=tpl.points_model[choose].astype(np.float32),
            rgb=rgb.astype(np.uint8),
            coords=tpl.points_model[choose].astype(np.float16),  # canonical labels (model frame)
            T=tpl.T_cam_model.astype(np.float64),
            obj_id=obj_id,
        )
        generated += 1
    print(f"[{split}] wrote {generated} samples to {out} (attempts={attempts})")
    return out
