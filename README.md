# Robot 3D Perception

RGB-D 3D scene understanding and **6D object pose estimation**: estimate the SE(3) pose
(rotation `R` + translation `t`) of a target object from RGB-D input, and transform it into
the robot coordinate frame.

A career-oriented, research-grade project — the goal is not SOTA but *understanding,
reproducibility, experiments, and a defensible engineering story*.

## Status

**Phase 0 — project infrastructure.** Skeleton with config / logging / evaluation metrics /
synthetic-data smoke experiment. See `PROJECT_SPEC.md` for the full phase plan and exit criteria.

## Quick start (CPU-only, no downloads needed)

```bash
# 1. Create an isolated environment (conda recommended; venv works too)
conda create -n r3p python=3.11 -y
conda run -n r3p python -m pip install -e ".[dev]"

# 2. Run unit tests
conda run -n r3p python -m pytest

# 3. Run the minimal end-to-end smoke experiment
conda run -n r3p python -m r3p.experiments.run_smoke --config configs/smoke.yaml
```

Outputs (log, `metrics.json`, visualization PNG) land in `outputs/smoke/<timestamp>/`.

## Repository map

| Path | Purpose |
| --- | --- |
| `src/r3p/` | Main package: geometry, datasets, evaluation, visualization, experiments |
| `configs/` | Experiment configs (YAML, CLI-overridable via `--set key=value`) |
| `tests/` | Unit tests |
| `outputs/` | Run outputs (gitignored; results are recorded in `EXPERIMENT_LOG.md`) |

## Documentation

| File | Content |
| --- | --- |
| `PROJECT_CONTEXT.md` | Motivation, positioning, technical route, key decisions |
| `PROJECT_SPEC.md` | Formal spec, phase plan, scope freeze |
| `EXPERIMENT_LOG.md` | Experiment records (Question/Hypothesis/Setup/Result/Analysis/Decision) |
| `MODULE_MAP.md` | Code module responsibilities |
| `CHANGELOG.md` | Important implementation changes |
