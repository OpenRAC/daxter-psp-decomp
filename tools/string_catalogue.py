#!/usr/bin/env python3
"""Catalogue the strings of the executable, for the naming work.

The retail executable is stripped: its symbol table holds one null symbol.
The names of the functions therefore have to come from somewhere else, and
the strings of the data segment are one of the places they come from.

This tool writes a **private** catalogue — under ``work/``, never in the
repository — of the printable strings of the executable, with their
addresses, so that a lot agent can look up the string a body references.

Usage:
    python3 tools/string_catalogue.py --elf <decrypted.elf> --out work/E0
"""

from __future__ import annotations

import argparse
import csv
import re
import sys
from pathlib import Path

#: The minimum length of a string worth keeping.
MIN_LENGTH = 4


def catalogue(data: bytes, minimum: int = MIN_LENGTH) -> list[tuple[int, str]]:
    """Return the (address, text) of the printable strings of the file."""
    pattern = rb"[\x20-\x7e]{%d,}" % minimum
    return [(match.start(), match.group().decode("ascii"))
            for match in re.finditer(pattern, data)]


def main(argv: list[str] | None = None) -> int:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--elf", type=Path, required=True)
    parser.add_argument("--out", type=Path, default=Path("work/E0"))
    parser.add_argument("--min-length", type=int, default=MIN_LENGTH)
    args = parser.parse_args(argv)

    data = args.elf.read_bytes()
    strings = catalogue(data, args.min_length)

    args.out.mkdir(parents=True, exist_ok=True)
    path = args.out / "strings.tsv"
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle, delimiter="\t", lineterminator="\n")
        writer.writerow(["address", "length", "text"])
        for offset, text in strings:
            writer.writerow([f"0x{offset:08X}", len(text), text])

    print(f"strings   : {len(strings)}")
    print(f"catalogue : {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
