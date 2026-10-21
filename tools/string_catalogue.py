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
import struct
import sys
from pathlib import Path

#: The minimum length of a string worth keeping.
MIN_LENGTH = 4


def catalogue(data: bytes, minimum: int = MIN_LENGTH) -> list[tuple[int, str]]:
    """Return the (address, text) of the printable strings of the file.

    The addresses are **virtual** addresses, the ones the code uses, not
    file offsets.  The two are not the same, and mixing them is a trap:
    the code segment is at file offset 0x74 for the virtual address zero,
    and the data segment is at 0x00363B08 for 0x00363A98.
    """
    pattern = rb"[\x20-\x7e]{%d,}" % minimum
    segments = _segments(data)
    out: list[tuple[int, str]] = []
    for match in re.finditer(pattern, data):
        address = _to_virtual(segments, match.start())
        if address is None:
            continue
        out.append((address, match.group().decode("ascii")))
    return out


def _segments(data: bytes) -> list[tuple[int, int, int, int]]:
    """Return the (file offset, file size, virtual address, flags) of the loads."""
    if data[:4] != b"\x7fELF":
        return []
    _kind, _machine, _version, _entry, phoff, _shoff, _flags, _ehsize, \
        phentsize, phnum, _shentsize, _shnum, _shstrndx = struct.unpack_from(
            "<HHIIIIIHHHHHH", data, 16)
    out = []
    for index in range(phnum):
        ptype, offset, vaddr, _paddr, size, _memsz, flags, _align = \
            struct.unpack_from("<IIIIIIII", data, phoff + index * phentsize)
        if ptype == 1:
            out.append((offset, size, vaddr, flags))
    return out


def _to_virtual(segments: list[tuple[int, int, int, int]],
                offset: int) -> int | None:
    for file_offset, size, vaddr, _flags in segments:
        if file_offset <= offset < file_offset + size:
            return vaddr + (offset - file_offset)
    return None


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
