#!/usr/bin/env python3
"""Recover the name of the functions that host an assert.

The engine carries its asserts through a helper at ``0x7035C`` that takes
the name of the enclosing function in ``$a3`` — the C ``__FUNCTION__``.
Every call site of that helper therefore names the function it sits in.
There are **344** such call sites in the target.

This is the largest naming source the project has: the executable is
stripped, and this is the code telling us its own names.

The resolver follows how the argument is actually built: a ``lui`` before
the call, and the ``addiu`` that completes it **in the delay slot of the
call itself**, which is where the compiler puts it.  A load of a pointer
is handled too, because the engine keeps its identifiers in a pool.

**Current coverage.** The direct pattern is resolved; the sites whose
argument comes from further away are not yet.  The catalogue is therefore
partial, and the tool says so rather than pretending otherwise: the count
it prints is the count that was *resolved*, not the count of the sites.
The names themselves live in a string pool that starts at ``0x00340000``;
see ``docs/STATE.md`` for the open item.

The catalogue it writes is **private**: it holds the text of the game.  The
repository publishes the names it recovers, and the counts.

Usage:
    python3 tools/assert_names.py --elf <decrypted.elf> \\
        --layout config/boot/layout.tsv --out work/E0
"""

from __future__ import annotations

import argparse
import csv
import struct
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import psp_elf  # noqa: E402

#: The address of the assert helper of the pinned target.  The register
#: that carries the function name is the third argument, ``$a3``.
ASSERT_HELPER = 0x0007035C
NAME_REGISTER = 7          # $a3

#: How far back the ``lui`` that loads the high half may be.
LOOK_BACK = 24


def _rs(word: int) -> int:
    return (word >> 21) & 0x1F


def _rt(word: int) -> int:
    return (word >> 16) & 0x1F


def _imm(word: int) -> int:
    return word & 0xFFFF


def _opcode(word: int) -> int:
    return word & 0xFC000000


def segments(data: bytes) -> list[tuple[int, int, int, int]]:
    _header, programs, _sections = psp_elf._headers(data)
    return [(offset, size, vaddr, flags)
            for ptype, offset, vaddr, _paddr, size, _memsz, flags, _align
            in programs if ptype == 1]


def to_file(loads, address: int) -> int | None:
    for offset, size, vaddr, _flags in loads:
        if vaddr <= address < vaddr + size:
            return offset + (address - vaddr)
    return None


def call_sites(data: bytes, loads, target: int) -> list[int]:
    """Return the addresses of the calls to ``target``."""
    sites = []
    for offset, size, vaddr, _flags in loads:
        for position in range(0, size - 3, 4):
            word = struct.unpack_from("<I", data, offset + position)[0]
            if (word & 0xFC000000) != 0x0C000000:
                continue
            reached = ((vaddr + position + 4) & 0xF0000000) | \
                      ((word & 0x03FFFFFF) << 2)
            if reached == target:
                sites.append(vaddr + position)
    return sites


def name_argument(data: bytes, loads, site: int) -> int | None:
    """Return the value the name argument holds at a call site.

    The high half is loaded before the call, and the low half is added
    **in the delay slot of the call**, which is where the compiler puts
    it.  The window therefore reaches one instruction past the call, and
    it is walked in program order: the last write of the register wins.
    """
    high: int | None = None
    low: int | None = None
    is_or = False
    materialised: int | None = None
    pointer: int | None = None

    first = site - LOOK_BACK * 4
    for address in range(first, site + 8, 4):
        offset = to_file(loads, address)
        if offset is None:
            continue
        word = struct.unpack_from("<I", data, offset)[0]
        opcode = _opcode(word)
        if opcode == 0x3C000000 and _rt(word) == NAME_REGISTER:
            high = _imm(word) << 16
            low = None
            is_or = False
            materialised = None
            pointer = None
        elif opcode == 0x24000000:
            source = _rs(word)
            target = _rt(word)
            if target != NAME_REGISTER:
                continue
            value = _imm(word)
            signed = value - 0x10000 if value & 0x8000 else value
            if source == NAME_REGISTER:
                low = signed
                is_or = False
                pointer = None
            elif source == 0:
                materialised = signed & 0xFFFFFFFF
                pointer = None
        elif opcode == 0x34000000 and _rt(word) == NAME_REGISTER:
            if _rs(word) == NAME_REGISTER:
                low = _imm(word)
                is_or = True
                pointer = None
        elif opcode == 0x8C000000 and _rt(word) == NAME_REGISTER:
            # A load of a pointer: the address of the pointer is built the
            # same way, and the word it holds is the value.
            source = _rs(word)
            if source == NAME_REGISTER and high is not None:
                slot = (high + _imm(word)) & 0xFFFFFFFF
                at = to_file(loads, slot)
                if at is not None and at + 4 <= len(data):
                    pointer = struct.unpack_from("<I", data, at)[0]
            elif source == 0:
                slot = _imm(word)
                at = to_file(loads, slot)
                if at is not None and at + 4 <= len(data):
                    pointer = struct.unpack_from("<I", data, at)[0]
        elif opcode == 0x00000000 and _rt(word) == NAME_REGISTER:
            # A move into the register: the value is not a literal.
            high = None
            low = None
            materialised = None
            pointer = None

    if pointer is not None:
        return pointer
    if materialised is not None:
        return materialised
    if high is None or low is None:
        return None
    if is_or:
        return (high | low) & 0xFFFFFFFF
    return (high + low) & 0xFFFFFFFF


def string_at(data: bytes, loads, address: int) -> str | None:
    offset = to_file(loads, address)
    if offset is None or offset + 1 > len(data):
        return None
    if not (0x20 <= data[offset] < 0x7F):
        return None
    end = data.find(b"\x00", offset, offset + 256)
    if end < 0:
        return None
    text = data[offset:end]
    if not all(0x20 <= byte < 0x7F for byte in text):
        return None
    return text.decode("ascii")


def read_layout(path: Path) -> list[tuple[int, int]]:
    if not path.is_file():
        return []
    out = []
    with path.open(encoding="utf-8", newline="") as handle:
        for row in csv.DictReader(handle, delimiter="\t"):
            if row.get("start"):
                out.append((int(row["start"], 16), int(row["end"], 16)))
    return out


def enclosing(layout: list[tuple[int, int]], address: int) -> int | None:
    """Return the start of the body that contains an address."""
    for start, end in layout:
        if start <= address < end:
            return start
    return None


def main(argv: list[str] | None = None) -> int:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--elf", type=Path, required=True)
    parser.add_argument("--layout", type=Path,
                        default=Path("config/boot/layout.tsv"))
    parser.add_argument("--out", type=Path, default=Path("work/E0"))
    parser.add_argument("--helper", type=lambda v: int(v, 0),
                        default=ASSERT_HELPER)
    args = parser.parse_args(argv)

    data = args.elf.read_bytes()
    loads = segments(data)
    layout = read_layout(args.layout)

    sites = call_sites(data, loads, args.helper)

    args.out.mkdir(parents=True, exist_ok=True)
    path = args.out / "assert_names.tsv"
    resolved = 0
    names: dict[str, set[int]] = {}
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle, delimiter="\t", lineterminator="\n")
        writer.writerow(["function", "name", "assert_site", "line"])
        for site in sites:
            address = name_argument(data, loads, site)
            if address is None:
                continue
            text = string_at(data, loads, address)
            if text is None:
                continue
            resolved += 1
            owner = enclosing(layout, site)
            if owner is not None:
                names.setdefault(text, set()).add(owner)
            writer.writerow([f"0x{owner:08X}" if owner is not None else "-",
                             text, f"0x{site:08X}", "-"])

    print(f"assert sites   : {len(sites)}")
    print(f"resolved       : {resolved}")
    print(f"distinct names : {len(names)}")
    print(f"catalogue      : {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
