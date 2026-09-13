# robot-3d-perception

**A reproducible robot 3D perception research project for 6D object pose estimation —
with controlled baselines, systematic failure analysis, and a FoundationPose integration path.**

Given an RGB-D frame, estimate the SE(3) pose (rotation `R` + translation `t`) of a target
object and transform it into the robot coordinate frame. The project pairs a validated
classical geometry baseline with a *failure-driven* diagnosis of a self-developed learning
route, and is integrating FoundationPose as a strong model-based reference baseline.

## Current Status

| Phase | Scope | Status |
| --- | --- | --- |
| Phase 0 | Infrastructure (data interface, config, logging, evaluation, tests) | ✅ complete |
| Phase 1 | BOP YCB-V data subset (validated GT / masks / depth / models) | ✅ complete |
| Phase 2 | Classical geometry baseline (PCA/OBB + point-to-plane ICP) | ✅ complete |
| Phase 3 | Self-developed learning route | ✅ **closed after Gate 3 NO-GO + full diagnosis chain (P3.1-C/D/E/F/G)** |
| Phase 4 | FoundationPose integration | ✅ local integration complete · ⏳ runtime waiting for GPU machine |
| Phase 5 | Robustness / failure analysis | ⏳ planned |
| Phase 6 | Engineering packaging | ⏳ planned |

## Why This Project

Not "train a bigger model" — the project is built around **route decisions driven by
experimental evidence**. Every baseline runs under the same frozen evaluation protocol
(same frames, same metrics, same thresholds, oracle mask as a *declared controlled
condition*), and every failure gets a diagnosis before the route moves on.

## Pipeline

```mermaid
flowchart TD
    A["BOP YCB-V subset<br/>RGB-D · masks · GT poses · CAD meshes"] --> B["Classical baseline<br/>mask → point cloud → PCA/OBB 24 hypotheses<br/>→ point-to-plane ICP"]
    B --> C["93.3% bottle / 77.3% bowl<br/>failures: roll ambiguity, occlusion"]
    A --> D["Self-developed learning route<br/>CoordNet 58.6k params, synthetic-only training"]
    D --> E["Gate 1 ✓ · Gate 2 ✓ · Gate 3 ✗ 0/10 real frames"]
    E --> F["Diagnosis chain P3.1-C/D/E/F/G<br/>single fixed ~176.5° canonical rotation explains<br/>all failures · frames identical · geometry-driven ·<br/>1 mm noise augmentation not supported"]
    F --> G["Route closed (decision D10)"]
    A --> H["FoundationPose baseline<br/>model-based register (GT-free), EXP-013"]
    H --> I["⏳ pending GPU execution"]
```

## Key Results

All numbers come from the frozen evaluation protocol: BOP YCB-V `test_bop19` subset,
scenes 50/53, 75 frames per object, **oracle `mask_visib`** (declared controlled condition),
success = `ADD(-S) < 0.1 × diameter`.

### Classical / Geometry Baseline (PCA/OBB + point-to-plane ICP)

| Object | Metric | Solver | Pose Success | Error (successful frames) |
| --- | --- | ---: | ---: | --- |
| 006_mustard_bottle (asymmetric) | ADD < 0.1d = 19.65 mm | 75/75 | **70/75 = 93.3%** | ADD median **1.30 mm**, max 2.01 mm |
| 024_bowl (rotationally symmetric) | ADD-S < 0.1d = 16.19 mm | 59/75 | **58/75 = 77.3%** | ADD-S median **2.67 mm**, max 3.19 mm |

Known failure modes: bottle **roll ambiguity** (5 frames — geometrically valid fit rotated
along the near-symmetric axis); bowl **heavy occlusion** (16 frames — insufficient visible
surface for ICP convergence). Full record: `EXPERIMENT_LOG.md` EXP-005/006.

![Classical baseline success](docs/assets/classical_pipeline_success.jpg)

### Phase 3 Diagnostic Results (self-developed learning route — closed)

A minimal PointNet-style canonical-correspondence network (58.6k params) trained purely on
synthetic renders:

| Gate | Result |
| --- | --- |
| Gate 1 — overfit sanity (synthetic) | ✅ PASS (train ADD 4.8 mm) |
| Gate 2 — synthetic validation (50 unseen poses) | ✅ PASS (val ADD 5.8 mm, train/val ratio 1.21) |
| Gate 3 — real YCB-V smoke (10 frames) | ❌ **0/10** |

The diagnosis chain that followed localized the failure precisely
(`EXPERIMENT_LOG.md` EXP-008–012, reports in `docs/`):

- **P3.1-C**: one fixed canonical rotation (−176.5° about the model Y axis) restores
  **10/10 poses to ~1–2 mm** — the failure is a single low-dimensional defect.
- **P3.1-D**: synthetic canonical frame and BOP model frame are **identical** (Kabsch ≈
  identity) — not a data convention bug.
- **P3.1-E**: destroying point-wise RGB does not remove the bias — it is
  **geometry-pathway-driven**; appearance explanations refuted.
- **P3.1-F**: clean real frames are *near-in-distribution* (NN domain gap ≈ 1 mm noise
  level) yet still flip — an **orientation-margin failure**, distinct from the
  severe-OOD collapse seen on the untrained bowl object.
- **P3.1-G**: real high-frequency depth noise is σ ≈ 0.26–0.40 mm, so "1 mm augmentation"
  is not supported; the route was closed **before** training (pre-registered stop).

![Learning route diagnosis](docs/assets/learning_route_diagnosis.jpg)

### FoundationPose (model-based reference baseline)

Local integration complete (adapter, evaluation wrapper, frozen EXP-013 config, mock
pipeline verified end-to-end, 3090 runner with environment gating). Runtime execution is
**pending GPU machine availability** — no results exist yet and none are claimed.

![Geometry distribution audit](docs/assets/geometry_distribution_audit.png)

## Demo Artifacts

Presentation-layer demos composed **read-only** from the frozen EXP-006 (P2.4)
per-frame outputs — no poses recomputed, no metrics touched
(`python scripts/build_demo.py --experiment p2_4 --object 5 ...`):

| Success (frame 1209, ADD 1.27 mm) | Failure (frame 1052, roll ambiguity) |
| --- | --- |
| ![Success demo](docs/assets/success_pose_demo.jpg) | ![Failure demo](docs/assets/failure_pose_demo.jpg) |

![Sequence preview](docs/assets/pose_sequence_preview.jpg)

GT = green, PCA init = blue, ICP prediction = red. The 23-frame sequence
(scene 50, frames 620–769, all successful) is assembled into an MP4 from the
stored per-frame overlays (local artifact under `outputs/demo/`, gitignored).
Every build is gated by a GT-overlay convention check: the projected GT pose
must land on `mask_visib` (measured 0.92–0.95), guarding units and coordinate
conventions. The failure case shows the declared `roll_symmetry_ambiguity`
mode — ADD-S 2.52 mm (surface fits) but ADD 61.85 mm (flipped about the
bottle's near-symmetric axis) — failure analysis on display, not hidden error.

## Dataset & Evaluation

- **Data**: BOP YCB-V `test_bop19` minimal subset (12 scenes, 900 RGB-D frames, 21 textured
  models) — local, validated, read-only. Details: `docs/phase1_data_validation_report.md`.
- **Metrics**: ADD / ADD-S / translation / rotation error via one shared implementation
  (`r3p.evaluation.metrics.compute_all`) used by *every* method.
- **Evaluation object set (W2-2)**: 7 objects selected for geometry / appearance / symmetry
  coverage — anchors obj5 `006_mustard_bottle` (asymmetric → ADD) and obj13 `024_bowl`
  (rotationally symmetric → ADD-S), both evaluated in EXP-006, plus obj2 / obj6 / obj10 /
  obj14 / obj15 (**registered for upcoming experiments, not yet evaluated**).
  Rationale: `docs/EVALUATION_OBJECT_SET.md` · registry: `configs/evaluation_objects.yaml`.
- **Controlled condition**: ground-truth `mask_visib` segmentation is used by all methods
  (oracle mask) — this isolates pose estimation from detection and is stated on every
  experiment record.

## Reproducibility

- Frozen per-experiment configs (`configs/`), fixed seeds, deterministic point-cloud
  ordering, single-thread ICP for bit-reproducible runs (decision D9).
- One-shot evaluation script per experiment; results (JSON/CSV/overlays) under
  `outputs/` (gitignored), summarized in `EXPERIMENT_LOG.md`.
- 82 tests (`pytest`), including synthetic regression tests, real-data contract tests,
  unit-conversion guards, and a structural GT-anti-leakage guard for the FoundationPose
  input manifest.

## Project Structure

```text
src/r3p/
  geometry/        pinhole model, SE(3), rotation representations
  datasets/        BOP YCB-V interface + synthetic scene generator
  pose/            classical baseline (PCA/OBB + ICP), SIFT+PnP (closed route),
                   rendered templates, learned CoordNet (closed route)
  evaluation/      ADD / ADD-S / translation / rotation + summary tables
  foundationpose/  project-side adapter, schemas, mock backend, EXP-013 config
  experiments/     one entry point per experiment
configs/           frozen per-experiment configs
docs/              per-experiment reports and audits
scripts/           dataset verification, diagnosis and FP runner scripts
tests/             82 tests (regression + real-data contracts)
```

## Current Scope & Limitations

Stated as current controlled scope and planned work — not as defects:

- **2 evaluated objects** (bottle, bowl); a 7-object evaluation set is **selected** for
  upcoming experiments (`docs/EVALUATION_OBJECT_SET.md`) — broader expansion stays gated on
  storage/execution budget.
- **Oracle mask** for all pose methods: detection/segmentation is intentionally excluded
  to isolate the pose variable.
- **Controlled experiments** dominate so far: robustness perturbation studies
  (occlusion / depth noise) are Phase 5, not yet executed.
- FoundationPose runtime execution is **pending a GPU machine**; no FP numbers exist yet.
- The self-developed learning route is **closed** with a complete attribution chain; any
  restart would require a new approved design (orientation-anchor / equivariance work).

## 3-Minute Tour

1. This page — overview, status, pipeline.
2. [`docs/PROJECT_OVERVIEW.md`](docs/PROJECT_OVERVIEW.md) — the 2-screen version.
3. Key results above + `EXPERIMENT_LOG.md` (every experiment: question → hypothesis →
   setup → result → analysis → decision).
4. Decision **D10** in `PROJECT_CONTEXT.md` — why the self-developed route was closed and
   what replaced it.
5. `MODULE_MAP.md` — what every module does.

## Documentation Map

| File | Content |
| --- | --- |
| `PROJECT_OVERVIEW.md` | 2-screen overview for reviewers |
| `PROJECT_CONTEXT.md` | motivation, decisions (D1–D10), constraints |
| `PROJECT_SPEC.md` | phase plan, exit criteria, scope freeze |
| `EXPERIMENT_LOG.md` | EXP-000…012 records + experiment index |
| `MODULE_MAP.md` | module responsibilities |
| `CHANGELOG.md` | implementation history |
| `docs/PHASE4_PREFLIGHT.md` | FoundationPose audit & integration plan |
| `docs/P3_1_*.md`, `docs/P3_0_GATE3_DEBUG.md` | Phase 3 diagnosis reports |

## Next Step

Run **EXP-013** (FoundationPose feasibility, obj5 × 5 frozen frames) on the GPU machine —
project-side integration is complete and gated by
`scripts/foundationpose_env_check.py`; then Phase 5 robustness studies.

## License

Project license decision pending before any public release.
[FoundationPose](https://github.com/NVlabs/FoundationPose) is an **external dependency**
with its own license terms (NVIDIA Source Code License, non-commercial research use) and
is not redistributed from this repository.
