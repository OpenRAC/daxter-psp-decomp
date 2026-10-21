#!/usr/bin/env python3
"""Inventory the containers of a PSP UMD disc, and publish the tables.

The tool walks an extracted disc (or a mounted ISO), classifies every file by
the container it uses, and writes the research tables under ``config/``:

``config/disc/pack_index.tsv``   one row per Pack container of the disc
``config/disc/containers.tsv``   one row per container of any kind
``config/levels/modules.tsv``    one row per level container, with its census

Only structure is published: names, sizes, counts, hashes, type codes and
payload magics.  No payload byte is written to the repository.

Usage:
    python3 tools/disc_inventory.py --disc <path> [--out config] [--check]

``--check`` verifies that the tables on disk still match the disc, without
writing anything.  It is the check the continuous integration runs.
"""

from __future__ import annotations

import argparse
import hashlib
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import psp_formats as fmt  # noqa: E402

#: The disc layout of the pinned target, as a path prefix -> role.
DISC_ROLES = {
    "PSP_GAME/SYSDIR/EBOOT.BIN": "executable",
    "PSP_GAME/SYSDIR/BOOT.BIN": "boot-blob",
    "PSP_GAME/SYSDIR/UPDATE/EBOOT.BIN": "executable-update",
    "PSP_GAME/SYSDIR/UPDATE/DATA.BIN": "update-archive",
    "PSP_GAME/PARAM.SFO": "disc-parameters",
    "PSP_GAME/SYSDIR/UPDATE/PARAM.SFO": "update-parameters",
}

DATA_PREFIX = "PSP_GAME/USRDIR/data/"


def _relative(root: Path, path: Path) -> str:
    return path.relative_to(root).as_posix()


def classify(root: Path) -> list[tuple[str, str, int, str]]:
    """Return (relative path, container name, size, sha256) of every file."""
    rows = []
    for path in sorted(root.rglob("*")):
        if not path.is_file():
            continue
        data = path.read_bytes()
        name = fmt.identify(data) or "raw"
        rows.append((_relative(root, path), name, len(data),
                     hashlib.sha256(data).hexdigest()))
    return rows


def pack_rows(root: Path) -> list[dict[str, object]]:
    """Return one record per Pack container found under the data directory."""
    data_root = root / DATA_PREFIX
    records = []
    if not data_root.is_dir():
        return records
    for path in sorted(data_root.rglob("*.bin")):
        blob = path.read_bytes()
        if blob[:4] != fmt.MAGIC_PACK:
            continue
        pack = fmt.read_pack(blob)
        histogram = pack.type_histogram()
        magics = Counter(entry.magic for entry in pack.entries if entry.magic)
        records.append({
            "path": _relative(root, path),
            "size": len(blob),
            "sha256": hashlib.sha256(blob).hexdigest(),
            "version": f"{pack.version_major}.{pack.version_minor}",
            "entries": len(pack.entries),
            "types": ",".join(f"{key}={value}" for key, value in sorted(histogram.items())),
            "magics": ",".join(f"{key}={value}" for key, value in sorted(magics.items())),
        })
    return records


def render_tsv(header: list[str], rows: list[list[object]]) -> str:
    """Return the text of a TSV table."""
    lines = ["\t".join(header)]
    for row in rows:
        lines.append("\t".join(str(cell) for cell in row))
    return "\n".join(lines) + "\n"


def render(root: Path) -> dict[str, str]:
    """Return the text of every table, without writing anything."""
    containers = classify(root)
    packs = pack_rows(root)
    return {
        "disc/containers.tsv": render_tsv(
            ["path", "container", "size", "sha256"],
            [[row[0], row[1], row[2], row[3]] for row in containers]),
        "disc/pack_index.tsv": render_tsv(
            ["path", "size", "sha256", "version", "entries", "types", "magics"],
            [[pack["path"], pack["size"], pack["sha256"], pack["version"],
              pack["entries"], pack["types"], pack["magics"]] for pack in packs]),
        "levels/modules.tsv": render_tsv(
            ["path", "version", "entries", "types"],
            [[pack["path"], pack["version"], pack["entries"], pack["types"]]
             for pack in packs]),
    }


def build(root: Path, out: Path) -> dict[str, int]:
    containers = classify(root)
    packs = pack_rows(root)
    for relative, text in render(root).items():
        path = out / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
    return {"containers": len(containers), "packs": len(packs)}


def check(root: Path, out: Path) -> int:
    """Compare the tables on disk with the disc. Returns a process exit code.

    The check never writes: it renders the tables in memory and compares
    them with what is on disk.
    """
    failures = 0
    for relative, expected in render(root).items():
        path = out / relative
        if not path.is_file():
            print(f"missing table: {relative}", file=sys.stderr)
            failures += 1
            continue
        before = path.read_text(encoding="utf-8")
        if before != expected:
            print(f"table is out of date: {relative}", file=sys.stderr)
            failures += 1
    return 1 if failures else 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--disc", type=Path, required=True,
                        help="root of the extracted disc")
    parser.add_argument("--out", type=Path, default=Path("config"))
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args(argv)

    root = args.disc
    if not root.is_dir():
        print(f"not a directory: {root}", file=sys.stderr)
        return 2
    if args.check:
        return check(root, args.out)
    counts = build(root, args.out)
    print(f"containers: {counts['containers']}  packs: {counts['packs']}")
    print(f"tables written under {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
