#!/usr/bin/env python3
"""Merge the reviewed layout of the lots, and publish it.

This is the ROOT's integration step.  It reads the tables the lot agents
produced under ``work/L*/layout.tsv``, and writes:

``config/boot/layout.tsv``         the verified layout of the reviewed bodies
``config/boot/layout_summary.json`` the counts, and the error rate of the
                                    sweep that produced the hypotheses

The tool never reads an instruction byte: it merges metadata.

The error rate is the number the wave was for: the sweep guessed a bound
for every candidate, and the agents checked them.  The difference between
the sweep's end and the reviewed end is the measure of how much the sweep
can be trusted on the targets nobody reviewed.

Usage:
    python3 tools/merge_layout.py [--work work] [--out config]
"""

from __future__ import annotations

import argparse
import csv
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

FIELDS = ["start", "end", "size", "class", "name", "name_evidence",
          "confidence", "sweep_end", "sweep_size", "bound_agrees"]

VALID_CLASSES = {"function", "not_function", "unknown"}
VALID_CONFIDENCE = {"high", "medium", "low"}


def read_lot(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8", newline="") as handle:
        rows = list(csv.DictReader(handle, delimiter="\t"))
    return [row for row in rows if row.get("start")]


def read_sweep(path: Path) -> dict[str, dict[str, str]]:
    """Return the sweep's hypothesis, indexed by its start address."""
    if not path.is_file():
        return {}
    with path.open(encoding="utf-8", newline="") as handle:
        rows = list(csv.DictReader(handle, delimiter="\t"))
    return {row["start"]: row for row in rows if row.get("start")}


def build_identifiers() -> set[str]:
    """Return the strings of the build that are not function names.

    The version registration of the target passes the **branch** of the
    build where an assert would pass the name of the function.  A name that
    is a build identifier is therefore not a function name, whatever the
    evidence says.
    """
    path = ROOT / "config" / "target.json"
    if not path.is_file():
        return set()
    try:
        build = json.loads(path.read_text(encoding="utf-8")).get("build", {})
    except json.JSONDecodeError:
        return set()
    out = set()
    for key in ("branch", "engine", "port_developer", "object_layer"):
        value = build.get(key)
        if isinstance(value, str) and value:
            out.add(value)
            out.add(value.split(",")[0].strip())
    return out


def read_named(path: Path) -> list[dict[str, str]]:
    """Read a naming deliverable: start, name, evidence, confidence, corrects."""
    if not path.is_file():
        return []
    with path.open(encoding="utf-8", newline="") as handle:
        rows = list(csv.DictReader(handle, delimiter="\t"))
    return [row for row in rows if row.get("start") and row.get("name")]


def merge(work: Path, out: Path) -> dict[str, object]:
    lots = sorted(work.glob("L*/layout.tsv"))
    if not lots:
        raise SystemExit(f"no lot table found under {work}")

    sweep = read_sweep(work / "E0" / "bounds.tsv")
    merged: list[dict[str, str]] = []
    seen: dict[str, int] = {}
    duplicates = 0
    counts = {"function": 0, "not_function": 0, "unknown": 0}
    confidence = {"high": 0, "medium": 0, "low": 0}
    named = 0
    disagreements = 0
    checked = 0
    corrections = 0

    for lot in lots:
        for row in read_lot(lot):
            start = row["start"]
            if start in seen:
                # Two lots reviewed the same body.  The review is the
                # truth, and it is the same truth; keep the first and say
                # how many times it was seen.
                duplicates += 1
                continue
            seen[start] = 1
            end = row.get("end", "")
            size = row.get("size", "")
            klass = row.get("class", "unknown")
            name = row.get("name", "") or f"func_{start.replace('0x', '')}"
            evidence = row.get("name_evidence", "") or "-"
            conf = row.get("confidence", "low")

            if klass not in VALID_CLASSES:
                klass = "unknown"
            if conf not in VALID_CONFIDENCE:
                conf = "low"

            hypothesis = sweep.get(start, {})
            sweep_end = hypothesis.get("end", "")
            sweep_size = hypothesis.get("size", "")
            agrees = ""
            if sweep_end:
                checked += 1
                agrees = "yes" if sweep_end == end else "no"
                if agrees == "no":
                    disagreements += 1

            counts[klass] += 1
            confidence[conf] += 1
            if name and not name.startswith("func_"):
                named += 1

            merged.append({
                "start": start,
                "end": end,
                "size": size,
                "class": klass,
                "name": name,
                "name_evidence": evidence,
                "confidence": conf,
                "sweep_end": sweep_end,
                "sweep_size": sweep_size,
                "bound_agrees": agrees,
            })

    # The naming assignments: the assert mechanism and the naming pass.
    identifiers = build_identifiers()
    for source in (work / "ASSERT" / "names.tsv", work / "NAMES" / "names.tsv"):
        for row in read_named(source):
            start = row["start"]
            target = next((item for item in merged if item["start"] == start), None)
            if target is None:
                continue
            proposed = row["name"]
            if not proposed or proposed.startswith("func_"):
                continue
            if proposed in identifiers:
                # A build identifier, not the name of a function.
                continue
            if proposed == target["name"]:
                continue
            if not target["name"].startswith("func_"):
                corrections += 1
                target["name_evidence"] = (
                    f"corrects {target['name']}; {row.get('evidence', '-')}")
            else:
                target["name_evidence"] = row.get("evidence", "-")
            target["name"] = proposed
            candidate = row.get("confidence", "")
            if candidate in VALID_CONFIDENCE:
                target["confidence"] = candidate
            named = sum(1 for item in merged
                        if item["name"] and not item["name"].startswith("func_"))

    merged.sort(key=lambda row: int(row["start"], 16))

    out.joinpath("boot").mkdir(parents=True, exist_ok=True)
    with (out / "boot" / "layout.tsv").open("w", encoding="utf-8",
                                            newline="") as handle:
        writer = csv.writer(handle, delimiter="\t", lineterminator="\n")
        writer.writerow(FIELDS)
        for row in merged:
            writer.writerow([row[field] for field in FIELDS])

    summary = {
        "lots": [lot.parent.name for lot in lots],
        "reviewed": len(merged),
        "duplicates": duplicates,
        "class_counts": counts,
        "confidence_counts": confidence,
        "named": named,
        "name_corrections": corrections,
        "sweep_checked": checked,
        "sweep_disagreements": disagreements,
        "sweep_agreement_rate": (
            round((checked - disagreements) / checked, 4) if checked else None),
    }
    (out / "boot" / "layout_summary.json").write_text(
        json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return summary


def main(argv: list[str] | None = None) -> int:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--work", type=Path, default=Path("work"))
    parser.add_argument("--out", type=Path, default=Path("config"))
    args = parser.parse_args(argv)

    summary = merge(args.work, args.out)
    print(f"reviewed        : {summary['reviewed']}")
    if summary["duplicates"]:
        print(f"duplicates      : {summary['duplicates']}")
    for name, count in summary["class_counts"].items():
        print(f"  {name:<14}: {count}")
    print(f"named           : {summary['named']}")
    print(f"corrections     : {summary['name_corrections']}")
    print(f"sweep checked   : {summary['sweep_checked']}")
    print(f"sweep disagreed : {summary['sweep_disagreements']}")
    rate = summary["sweep_agreement_rate"]
    print(f"agreement rate  : {rate if rate is None else f'{rate:.1%}'}")
    print(f"tables          : {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
