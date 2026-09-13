"""W2-3 / EXP-014 unified cross-object baseline table builder.

Aggregates per-frame CSVs (produced by the frozen P2.3/P2.4 runner) into one
comparable table across the W2-2 7-object evaluation set:

- new objects  : per-frame CSVs from the W2-3 run        -> source = EXP-014 (W2-3)
- anchors      : per-frame CSVs from the historical P2.4 run -> source = historical (EXP-006)

Aggregation only — no metric is redefined (per-frame columns come from the
runner's compute_all output), no frame is dropped, failures are counted and
carried into the table. Error medians follow the EXP-006 convention: computed
over pose-successful frames, with N and success/N always shown so small-N
rows are never confused with historical full-coverage rows.

Usage::

    python scripts/w2_3_unified_table.py --run outputs/w2_3/<timestamp> \
        --historical outputs/p2_4/20260830-161911 \
        --output-dir outputs/w2_3
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
TABLE_COLUMNS = (
    "object", "name", "source", "N", "success", "success_rate",
    "median_ADD_mm", "median_ADD-S_mm", "median_trans_mm", "median_rot_deg",
    "failure_tags",
)


def load_rows(csv_path: Path) -> list[dict]:
    with open(csv_path, encoding="utf-8") as f:
        return list(csv.DictReader(f))


def _median(rows: list[dict], column: str) -> float | None:
    values = [float(r[column]) for r in rows if r.get(column) not in ("", None)]
    return round(statistics.median(values), 2) if values else None


def object_row(obj: dict, rows: list[dict], source: str) -> dict:
    success_rows = [r for r in rows if r.get("pose_success") == "1"]
    # Error medians follow the EXP-006 metrics.json convention exactly: over
    # every frame that produced a metric value (i.e. all frames except
    # insufficient_observation / runtime_error), INCLUDING solver-gate
    # failures (icp_no_converge keeps its pose metrics) — so anchor rows
    # reproduce the frozen headline numbers bit-exactly.
    tags: dict[str, int] = {}
    for r in rows:
        tag = r.get("failure_tag") or "unknown"
        tags[tag] = tags.get(tag, 0) + 1
    n = len(rows)
    return {
        "object": obj["id"],
        "name": obj["name"],
        "source": source,
        "N": n,
        "success": len(success_rows),
        "success_rate": round(len(success_rows) / n, 3) if n else None,
        "median_ADD_mm": _median(rows, "add_mm"),
        "median_ADD-S_mm": _median(rows, "adds_mm"),
        "median_trans_mm": _median(rows, "trans_mm"),
        "median_rot_deg": _median(rows, "rot_deg"),
        "diameter_mm": float(obj["diameter_mm"]),
        "eval_scene": obj.get("eval_scene"),
        "failure_tags": dict(sorted(tags.items())),
    }


def fmt(value, spec: str = ".2f") -> str:
    return "-" if value is None else format(value, spec)


def to_markdown(rows: list[dict]) -> str:
    header = (
        "| Obj | Name | Source | N | Success | Rate | med ADD (mm) | med ADD-S (mm) |"
        " med trans (mm) | med rot (deg) | Failure tags |\n"
        "| --- | --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | --- |\n"
    )
    lines = [header]
    for r in rows:
        tags = ", ".join(f"{k}×{v}" for k, v in r["failure_tags"].items())
        lines.append(
            f"| {r['object']} | {r['name']} | {r['source']} | {r['N']} | "
            f"{r['success']}/{r['N']} | {fmt(r['success_rate'], '.3f')} | "
            f"{fmt(r['median_ADD_mm'])} | {fmt(r['median_ADD-S_mm'])} | "
            f"{fmt(r['median_trans_mm'])} | {fmt(r['median_rot_deg'])} | {tags} |\n"
        )
    lines.append(
        "\nProtocol: frozen EXP-006 (P2.4) classical baseline, oracle `mask_visib`,"
        " ADD(-S) < 0.1×diameter, identical ICP/selection parameters.\n"
        "N = actually evaluated frames. Error medians are over every frame that produced"
        " a metric value (EXP-006 metrics.json convention; solver-gate failures included,"
        " insufficient-observation frames excluded); '-' when no frame produced a pose.\n"
        "source = historical (EXP-006, 75 frames/obj5+obj13) vs EXP-014 (W2-3, 10 frames"
        " deterministic even sampling) — coverage differs and is labeled per row.\n"
    )
    return "".join(lines)


def build(run_dir: Path, historical_dir: Path) -> list[dict]:
    with open(REGISTRY, encoding="utf-8") as f:
        registry = yaml.safe_load(f)
    rows = []
    for obj in registry["objects"]:
        if obj.get("eval_source") == "EXP-006":
            csv_path = historical_dir / f"per_frame_obj{obj['id']}.csv"
            source = "historical (EXP-006)"
        else:
            csv_path = run_dir / f"per_frame_obj{obj['id']}.csv"
            source = "EXP-014 (W2-3)"
        if not csv_path.is_file():
            raise FileNotFoundError(f"missing per-frame CSV for obj{obj['id']}: {csv_path}")
        rows.append(object_row(obj, load_rows(csv_path), source))
    return rows


def main(argv=None) -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run", required=True, help="W2-3 run directory (timestamped)")
    parser.add_argument("--historical", default="outputs/p2_4/20260830-161911",
                        help="historical EXP-006 (P2.4) run directory for the anchors")
    parser.add_argument("--output-dir", default="outputs/w2_3")
    args = parser.parse_args(argv)

    rows = build(Path(args.run), Path(args.historical))
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
