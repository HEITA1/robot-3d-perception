"""W2-4 / EXP-015 comparison: W2-3 10-frame initial subset vs expanded coverage.

Loads the per-frame CSVs of the same five non-anchor objects from two runs of
the frozen P2.3/P2.4 baseline (the W2-3 initial run and the W2-4 expanded
full-scene run) and reports side-by-side four-layer statistics, success rates
and failure compositions — so the 10-frame observations can be checked for
stability without any significance testing (sample sizes do not warrant it).

Aggregation only: reuses :func:`w2_3_unified_table.object_row` (EXP-006
median convention, four-layer semantics); no metric redefined, no frame
dropped, raw failure tags preserved.

Usage::

    python scripts/w2_4_compare.py --initial-run outputs/w2_3/<ts> \
        --expanded-run outputs/w2_4/<ts> --output-dir outputs/w2_4
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import yaml  # noqa: E402

from w2_3_unified_table import load_rows, object_row  # noqa: E402

REGISTRY = Path("configs/evaluation_objects.yaml")
INITIAL_SOURCE = "EXP-014 (W2-3)"
EXPANDED_SOURCE = "EXP-015 (W2-4)"


def _composition(tags: dict[str, int]) -> str:
    return ", ".join(f"{k}×{v}" for k, v in tags.items()) or "-"


def _tag_changes(initial: dict[str, int], expanded: dict[str, int]) -> str:
    added = sorted(set(expanded) - set(initial))
    removed = sorted(set(initial) - set(expanded))
    parts = []
    if added:
        parts.append("+" + ",".join(added))
    if removed:
        parts.append("-" + ",".join(removed))
    return " ".join(parts) if parts else "tag set unchanged"


def compare_object(obj: dict, initial_csv: Path, expanded_csv: Path) -> dict:
    r0 = object_row(obj, load_rows(initial_csv), INITIAL_SOURCE)
    r1 = object_row(obj, load_rows(expanded_csv), EXPANDED_SOURCE)
    metric = (obj.get("primary_metric") or "?").upper()
    med_key = "median_ADD-S_mm" if metric == "ADDS" else "median_ADD_mm"
    return {
        "object": obj["id"],
        "name": obj["name"],
        "metric": metric,
        "n": f"{r0['total']} → {r1['total']}",
        "attempted": f"{r0['attempted']} → {r1['attempted']}",
        "success": f"{r0['success']} → {r1['success']}",
        "success_rate": f"{r0['success_rate']:.1%} → {r1['success_rate']:.1%}",
        "median_mm": f"{r0[med_key]} → {r1[med_key]}",
        "composition_initial": r0["failure_tags"],
        "composition_expanded": r1["failure_tags"],
        "tag_changes": _tag_changes(r0["failure_tags"], r1["failure_tags"]),
        "initial": r0,
        "expanded": r1,
    }


def to_markdown(rows: list[dict]) -> str:
    lines = [
        "| Obj | Name | Metric | N (init→exp) | Attempted | Success | Success rate |"
        " Median (mm) | Failure composition (init → exp) | Tag changes |\n"
        "| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |\n",
    ]
    for r in rows:
        comp = (f"{_composition(r['composition_initial'])} → {_composition(r['composition_expanded'])}")
        lines.append(
            f"| {r['object']} | {r['name']} | {r['metric']} | {r['n']} | {r['attempted']} | "
            f"{r['success']} | {r['success_rate']} | {r['median_mm']} | {comp} | {r['tag_changes']} |\n"
        )
    lines.append(
        "\nSame frozen baseline in both runs (identical parameters; oracle mask;"
        " ADD(-S) < 0.1d). Median = EXP-006 metrics.json convention (all frames that"
        " produced a pose, gate failures included); '-' when none.\n"
        "No significance testing — sample sizes do not warrant it; the comparison"
        " checks whether the W2-3 10-frame observations are directionally stable.\n"
    )
    return "".join(lines)


def main(argv=None) -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--initial-run", required=True, help="W2-3 (EXP-014) run directory")
    parser.add_argument("--expanded-run", required=True, help="W2-4 (EXP-015) run directory")
    parser.add_argument("--output-dir", default="outputs/w2_4")
    args = parser.parse_args(argv)

    with open(REGISTRY, encoding="utf-8") as f:
        registry = yaml.safe_load(f)
    out_dir = Path(args.output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    rows = []
    for obj in registry["objects"]:
        if obj.get("eval_source") == "EXP-006":
            continue  # anchors: historical full coverage, nothing to expand
        rows.append(compare_object(
            obj,
            Path(args.initial_run) / f"per_frame_obj{obj['id']}.csv",
            Path(args.expanded_run) / f"per_frame_obj{obj['id']}.csv",
        ))

    table_md = out_dir / "w2_3_vs_w2_4_comparison.md"
    table_md.write_text(to_markdown(rows), encoding="utf-8")
    table_json = out_dir / "w2_3_vs_w2_4_comparison.json"
    table_json.write_text(json.dumps({"rows": rows}, indent=2) + "\n", encoding="utf-8")
    print(table_md.read_text(encoding="utf-8"))
    print(f"[written] {table_md}\n[written] {table_json}")


if __name__ == "__main__":
    main()
