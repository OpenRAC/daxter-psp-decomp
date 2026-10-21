#!/usr/bin/env python3
"""Map the source modules of the target, from the paths the binary carries.

The executable holds the path of the source file every assert and every
error message comes from.  Those paths are the **module map** of the
program: which engine library each part of the code belongs to, and where
the platform-specific variants live.

This is the same thing the sibling projects publish as their module
catalogue, and it is what the decompilation is split along.

The tool writes ``config/boot/modules.tsv``: the path, the address it was
found at, and the library it belongs to.  It publishes the **structure**,
not the text of the game: it extracts the path tokens and nothing else.

Usage:
    python3 tools/module_map.py --strings <work/E0/strings.tsv> --out config
"""

from __future__ import annotations

import argparse
import csv
import re
import sys
from pathlib import Path

#: A source path: a directory, a file name, and an extension.
PATH_RE = re.compile(r"[A-Za-z0-9_./\\-]+\.(?:cpp|c|h|hpp|inl|s|S)", re.ASCII)

#: The sections of the ELF that hold the paths, so that a section name is
#: not mistaken for one.
def is_path(token: str) -> bool:
    if token.startswith("."):
        return False
    if "/" not in token and "\\" not in token:
        return False
    return True


def library_of(path: str) -> str:
    """Return the library a source path belongs to."""
    normalised = path.replace("\\", "/")
    parts = normalised.split("/")
    if len(parts) >= 2 and parts[0] == "libs":
        return parts[1]
    if len(parts) >= 2:
        return parts[0]
    return normalised


def extract(rows: list[tuple[str, str]]) -> list[tuple[str, str, str]]:
    """Return the (path, address, library) of the source paths of the file."""
    found: dict[str, str] = {}
    for address, text in rows:
        for match in PATH_RE.finditer(text):
            token = match.group()
            if not is_path(token):
                continue
            found.setdefault(token, address)
    return [(path, address, library_of(path))
            for path, address in sorted(found.items())]


def main(argv: list[str] | None = None) -> int:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--strings", type=Path, required=True)
    parser.add_argument("--out", type=Path, default=Path("config"))
    args = parser.parse_args(argv)

    with args.strings.open(encoding="utf-8", newline="") as handle:
        rows = [(row[0], row[2]) for row in
                csv.reader(handle, delimiter="\t")][1:]

    modules = extract(rows)
    path = args.out / "boot" / "modules.tsv"
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle, delimiter="\t", lineterminator="\n")
        writer.writerow(["source", "address", "library"])
        for source, address, library in modules:
            writer.writerow([source, address, library])

    libraries: dict[str, int] = {}
    for _source, _address, library in modules:
        libraries[library] = libraries.get(library, 0) + 1
    print(f"source paths : {len(modules)}")
    print(f"libraries    : {len(libraries)}")
    for library, count in sorted(libraries.items(), key=lambda kv: (-kv[1], kv[0])):
        print(f"  {library:<16} {count}")
    print(f"written      : {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
