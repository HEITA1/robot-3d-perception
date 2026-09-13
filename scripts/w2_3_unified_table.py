"""W2-3 / EXP-014 unified cross-object baseline table builder.

Aggregates per-frame CSVs (produced by the frozen P2.3/P2.4 runner) into one
comparable table across the W2-2 7-object evaluation set:

- new objects  : per-frame CSVs from the W2-3 run          -> source = EXP-014 (W2-3)
- anchors      : per-frame CSVs from the historical P2.4 run -> source = historical (EXP-006)

W2-3.1 statistical semantics (derived from the runner code + real CSVs, see
docs/BASELINE_OPERATING_ENVELOPE.md):

  total      frames sampled by the frozen deterministic selection (CSV rows)
  valid      frames that passed input loading and entered processing; the
             dataset contract raises on missing RGB/depth/mask/GT, so an
             invalid input aborts the run loudly — valid == total in every
             observed run (input_invalid = 0)
  attempted  frames that entered the solver = total - insufficient_observation
             - runtime_error. `insufficient_observation` is a PRE-solver
             rejection (point-cloud floor): no pose, no metrics, NOT
             attempted. `icp_no_converge` frames DID run PCA+ICP (pose and
             metrics exist, fitness/rmse gates failed) and ARE attempted.
  success    frames with pose_success = 1, i.e. ADD(-S) < 0.1d AND solver
             gates passed (the runner's frozen definition)

  success_rate        = success / total   (project convention, = metrics.json)
  conditional_rate    = success / attempted, rendered "N/A (no solver
                        attempt)" when attempted = 0 — never 0/0 = 0%

Error medians follow the EXP-006 metrics.json convention exactly: over every
frame that produced a metric value (solver-gate failures INCLUDED,
insufficient-observation frames excluded) — anchor rows reproduce the frozen
headline numbers bit-exactly.

Aggregation only — no metric redefined, no frame dropped, raw failure tags
preserved; the state classification is an aggregate view on top of them.
"""

from __future__ import annotations

import argparse
import csv
import json
import statistics
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

import yaml  # noqa: E402

REGISTRY = Path("configs/evaluation_objects.yaml")

# Failure tags that never entered the solver (pre-solver rejections / errors).
PRE_SOLVER_TAGS = {"insufficient_observation", "runtime_error"}
# Solver ran but failed the frozen fitness/rmse gates (pose + metrics exist).
SOLVER_GATE_TAGS = {"icp_no_converge"}


def load_rows(csv_path: Path) -> list[dict]:
    with open(csv_path, encoding="utf-8") as f:
        return list(csv.DictReader(f))


def _median(rows: list[dict], column: str) -> float | None:
    values = [float(r[column]) for r in rows if r.get(column) not in ("", None)]
    return round(statistics.median(values), 2) if values else None


def object_row(obj: dict, rows: list[dict], source: str) -> dict:
    total = len(rows)
    success_rows = [r for r in rows if r.get("pose_success") == "1"]
    pre_solver = [r for r in rows if r.get("failure_tag") in PRE_SOLVER_TAGS]
    attempted_rows = [r for r in rows if r.get("failure_tag") not in PRE_SOLVER_TAGS]
    gate_failures = [r for r in attempted_rows if r.get("failure_tag") in SOLVER_GATE_TAGS]
    tags: dict[str, int] = {}
    for r in rows:
        tag = r.get("failure_tag") or "unknown"
        tags[tag] = tags.get(tag, 0) + 1

    attempted = len(attempted_rows)
    return {
        "object": obj["id"],
        "name": obj["name"],
        "source": source,
        "primary_metric": obj.get("primary_metric"),
        "total": total,
        "valid": total,  # input-invalid frames abort the run (dataset contract); none observed
        "attempted": attempted,
        "success": len(success_rows),
        "success_rate": round(len(success_rows) / total, 3) if total else None,
        "conditional_success_rate": (round(len(success_rows) / attempted, 3) if attempted else None),
        "median_ADD_mm": _median(rows, "add_mm"),
        "median_ADD-S_mm": _median(rows, "adds_mm"),
        "median_trans_mm": _median(rows, "trans_mm"),
        "median_rot_deg": _median(rows, "rot_deg"),
        "diameter_mm": float(obj["diameter_mm"]),
        "eval_scene": obj.get("eval_scene"),
        "failure_tags": dict(sorted(tags.items())),
        # aggregate state view (raw tags above stay authoritative)
        "state_counts": {
            "input_invalid": 0,
            "pre_solver_insufficient": sum(1 for r in pre_solver if r.get("failure_tag") == "insufficient_observation"),
            "runtime_error": sum(1 for r in pre_solver if r.get("failure_tag") == "runtime_error"),
            "solver_gate_failure": len(gate_failures),
            "pose_success": len(success_rows),
            "pose_metric_failure": attempted - len(gate_failures) - len(success_rows),
        },
    }


def fmt(value, spec: str = ".2f") -> str:
    return "-" if value is None else format(value, spec)


def _rate(r: dict) -> str:
    return "-" if r["success_rate"] is None else f"{r['success']}/{r['total']} ({r['success_rate']:.1%})"


def _conditional(r: dict) -> str:
    if r["attempted"] == 0:
        return "N/A (no solver attempt)"
    return f"{r['success']}/{r['attempted']} ({r['success'] / r['attempted']:.1%})"


def to_markdown(rows: list[dict]) -> str:
    header = (
        "| Obj | Name | Source | Metric | Total | Valid | Attempted | Success | succ/total | succ/attempted |"
        " med ADD (mm) | med ADD-S (mm) | med trans (mm) | med rot (deg) | Failure composition |\n"
        "| --- | --- | --- | --- | ---: | ---: | ---: | ---: | --- | --- |"
        " ---: | ---: | ---: | ---: | --- |\n"
    )
    lines = [header]
    for r in rows:
        metric = (r["primary_metric"] or "?").upper()
        tags = ", ".join(f"{k}×{v}" for k, v in r["failure_tags"].items())
        lines.append(
            f"| {r['object']} | {r['name']} | {r['source']} | {metric} | {r['total']} | {r['valid']} | "
            f"{r['attempted']} | {r['success']} | {_rate(r)} | {_conditional(r)} | "
            f"{fmt(r['median_ADD_mm'])} | {fmt(r['median_ADD-S_mm'])} | "
            f"{fmt(r['median_trans_mm'])} | {fmt(r['median_rot_deg'])} | {tags} |\n"
        )
    lines.append(
        "\nProtocol: frozen EXP-006 (P2.4) classical baseline, oracle `mask_visib`,"
        " ADD(-S) < 0.1×diameter, identical ICP/selection parameters.\n"
        "total = sampled frames · valid = frames that entered processing (invalid input"
        " aborts the run; none observed) · attempted = entered the solver (pre-solver"
        " `insufficient_observation`/`runtime_error` excluded; `icp_no_converge` ran"
        " PCA+ICP and IS attempted) · success = ADD(-S) < 0.1d with solver gates passed.\n"
        "succ/total is the project success rate (metrics.json convention); succ/attempted"
        " is the conditional pose success — the two are different metrics, and N/A means"
        " no solver attempt happened under the frozen protocol (never 0/0).\n"
        "Error medians: EXP-006 metrics.json convention (every frame that produced a"
        " pose, gate failures included) — anchor rows reproduce the frozen numbers.\n"
        "source = historical (EXP-006, 75 frames) vs EXP-014 (W2-3, 10-frame"
        " deterministic even sample) — coverage differs and is labeled per row.\n"
    )
    return "".join(lines)


def build(run_dir: Path, historical_dir: Path, new_source: str = "EXP-014 (W2-3)") -> list[dict]:
    with open(REGISTRY, encoding="utf-8") as f:
        registry = yaml.safe_load(f)
    rows = []
    for obj in registry["objects"]:
        if obj.get("eval_source") == "EXP-006":
            csv_path = historical_dir / f"per_frame_obj{obj['id']}.csv"
            source = "historical (EXP-006)"
        else:
            csv_path = run_dir / f"per_frame_obj{obj['id']}.csv"
            source = new_source
        if not csv_path.is_file():
            raise FileNotFoundError(f"missing per-frame CSV for obj{obj['id']}: {csv_path}")
        rows.append(object_row(obj, load_rows(csv_path), source))
    return rows


def main(argv=None) -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run", required=True, help="W2-3 run directory (timestamped)")
    parser.add_argument("--historical", default="outputs/p2_4/20260830-161911",
                        help="historical EXP-006 (P2.4) run directory for the anchors")
    parser.add_argument("--source-label", default="EXP-014 (W2-3)",
                        help="source label for the non-anchor objects (e.g. 'EXP-015 (W2-4)')")
    parser.add_argument("--output-dir", default="outputs/w2_3")
    args = parser.parse_args(argv)

    rows = build(Path(args.run), Path(args.historical), args.source_label)
    out_dir = Path(args.output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    table_md = out_dir / "unified_table.md"
    table_md.write_text(to_markdown(rows), encoding="utf-8")
    table_json = out_dir / "unified_table.json"
    table_json.write_text(json.dumps({"rows": rows}, indent=2) + "\n", encoding="utf-8")
    print(table_md.read_text(encoding="utf-8"))
    print(f"[written] {table_md}\n[written] {table_json}")


if __name__ == "__main__":
    main()
