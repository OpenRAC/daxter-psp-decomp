#!/usr/bin/env python3
"""Print the progress snapshot of the project.

The snapshot reads the published tables and counts what is known. It never
reads the game, and it never claims a count that the gates have not
established.

Usage:
    python3 tools/progress.py
    python3 tools/progress.py --json
"""

from __future__ import annotations

import argparse
import csv
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def _rows(relative: str) -> list[dict[str, str]]:
    path = ROOT / relative
    if not path.is_file():
        return []
    with path.open(encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle, delimiter="\t"))


def snapshot() -> dict[str, object]:
    containers = _rows("config/disc/containers.tsv")
    packs = _rows("config/disc/pack_index.tsv")
    modules = _rows("config/levels/modules.tsv")

    blobs = 0
    for pack in packs:
        try:
            blobs += int(pack.get("entries", "0") or 0)
        except ValueError:
            pass

    bodies = list((ROOT / "src" / "boot" / "bodies").glob("*.c"))
    bodies += list((ROOT / "src" / "levels" / "bodies").glob("*.c"))
    parked = list((ROOT / "nonmatching").rglob("*.c"))

    target = {}
    target_path = ROOT / "config" / "target.json"
    if target_path.is_file():
        target = json.loads(target_path.read_text(encoding="utf-8"))

    executable = target.get("executable", {})
    decrypted = bool(executable.get("decrypted_sha256"))

    return {
        "target": target.get("game"),
        "title_id": target.get("title_id"),
        "disc_version": target.get("disc_version"),
        "disc_files": len(containers),
        "pack_containers": len(packs),
        "level_containers": len(modules),
        "blobs_in_packs": blobs,
        "code_objects": 1,
        "executable_decrypted": decrypted,
        "proved_bodies": len(bodies),
        "parked_attempts": len(parked),
        "functions_matched": 0,
        "gates_passed": 0,
    }


def main(argv: list[str] | None = None) -> int:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)

    state = snapshot()
    if args.json:
        print(json.dumps(state, indent=2))
        return 0

    width = max(len(key) for key in state)
    print(f"{state['target']} ({state['title_id']}) — {state['disc_version']}")
    print("-" * (width + 24))
    for key, value in state.items():
        if key in {"target", "title_id", "disc_version"}:
            continue
        print(f"{key:<{width}}  {value}")
    print()
    if not state["executable_decrypted"]:
        print("Next step: decrypt the ~PSP executable locally, measure it with")
        print("tools/psp_elf.py, and record its hash in config/target.json.")
        print("See docs/STATE.md.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
