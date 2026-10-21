#!/usr/bin/env python3
"""Inventory the functions of an Allegrex executable.

The retail executable of a PSP game carries no symbol table: its ELF has a
symbol table section with nothing but the null symbol.  The functions have
therefore to be found in the code itself.

This tool reports the **candidates**: the places where the code opens a
stack frame the way the Allegrex compiler does.  It does not claim they are
functions, does not name them, and does not print any instruction bytes:
its output is research metadata, and it is what the first wave of the
project starts from.

The pattern the tool looks for is the one the PSP toolchain emits for a
function with a frame:

    addiu $sp, $sp, -N      the frame, N bytes
    sw    $ra, M($sp)       the return address is saved

A frame alone is not enough to call a place a function: a function that
never returns, a jump table, or a hand-written assembly block can open a
frame too.  The candidates are the *input* of the review, not its result.

Usage:
    python3 tools/function_inventory.py <executable> [--tsv] [--json]
"""

from __future__ import annotations

import argparse
import json
import struct
import sys
from pathlib import Path

#: The Allegrex instructions the scan looks for, as (mask, value).
INSN_ADDIU_SP = (0xFFFF0000, 0x27BD0000)   # addiu $sp, $sp, imm
INSN_ADDIU_GP = (0xFFFF0000, 0x279C0000)   # addiu $gp, $gp, imm
INSN_LUI_GP = (0xFFFF0000, 0x3C1C0000)     # lui   $gp, imm
INSN_SW_RA = (0xFFFF0000, 0xAFBF0000)      # sw    $ra, off($sp)

#: The frame sizes the scan accepts. 0x10 is the smallest useful frame on
#: the Allegrex: the saved return address and one register.
MIN_FRAME = 0x10
MAX_FRAME = 0x8000

#: How far the scan looks for the save of the return address after the
#: frame is opened.  The measured distance on the pinned target reaches
#: fifteen instructions, when the callee-saved registers are pushed first.
SAVE_WINDOW = 16

PF_X = 1
PF_W = 2
PF_R = 4


def _insn(data: bytes, offset: int) -> int:
    return struct.unpack_from("<I", data, offset)[0]


def _matches(word: int, mask: int, value: int) -> bool:
    return (word & mask) == value


def executable_ranges(data: bytes) -> list[tuple[int, int, int]]:
    """Return the (file offset, size, virtual address) of the code segments."""
    if data[:4] != b"\x7fELF":
        raise ValueError("not an ELF")
    (_kind, _machine, _version, _entry, phoff, _shoff, _flags, _ehsize,
     phentsize, phnum) = struct.unpack_from("<HHIIIIIHHH", data, 16)
    ranges = []
    for index in range(phnum):
        base = phoff + index * phentsize
        ptype, offset, vaddr, _paddr, filesz, _memsz, flags, _align = \
            struct.unpack_from("<IIIIIIII", data, base)
        if ptype == 1 and (flags & PF_X) and filesz:
            ranges.append((offset, filesz, vaddr))
    return ranges


def inventory(data: bytes) -> list[dict[str, object]]:
    """Return the frame-opening candidates of an Allegrex executable."""
    candidates: list[dict[str, object]] = []
    for offset, size, vaddr in executable_ranges(data):
        segment = data[offset:offset + size]
        for index in range(0, max(0, len(segment) - 4), 4):
            word = _insn(segment, index)
            if not _matches(word, *INSN_ADDIU_SP):
                continue
            # The frame is opened downwards, so the immediate is negative.
            immediate = word & 0xFFFF
            if immediate & 0x8000:
                immediate -= 0x10000
            frame = -immediate
            if not MIN_FRAME <= frame <= MAX_FRAME:
                continue
            # A function saves the return address after it opens the frame,
            # but not necessarily on the very next instruction: the
            # callee-saved registers are usually pushed first.  The
            # measured distance between the frame and the save of $ra goes
            # up to fifteen instructions, so the window has to be wide.
            saved = False
            for ahead in range(1, SAVE_WINDOW):
                if index + ahead * 4 >= len(segment) - 4:
                    break
                if _matches(_insn(segment, index + ahead * 4), *INSN_SW_RA):
                    saved = True
                    break
            gp_setup = False
            if index >= 4:
                gp_setup = _matches(_insn(segment, index - 4), *INSN_LUI_GP)
            candidates.append({
                "address": f"0x{vaddr + index:08X}",
                "file_offset": f"0x{offset + index:08X}",
                "frame": frame,
                "saves_ra": bool(saved),
                "gp_setup": bool(gp_setup),
            })
    return candidates


def main(argv: list[str] | None = None) -> int:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("path", type=Path)
    parser.add_argument("--tsv", action="store_true")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)

    data = args.path.read_bytes()
    candidates = inventory(data)
    if args.json:
        print(json.dumps(candidates, indent=2))
        return 0
    if args.tsv:
        print("address\tframe\tsaves_ra\tgp_setup")
        for row in candidates:
            print(f"{row['address']}\t{row['frame']}\t"
                  f"{int(row['saves_ra'])}\t{int(row['gp_setup'])}")
        return 0

    print(f"{args.path}")
    print(f"  candidates: {len(candidates)}")
    with_ra = sum(1 for row in candidates if row["saves_ra"])
    with_gp = sum(1 for row in candidates if row["gp_setup"])
    print(f"  saving $ra: {with_ra}")
    print(f"  with a $gp setup: {with_gp}")
    for row in candidates[:20]:
        print(f"    {row['address']}  frame={row['frame']:#06x} "
              f"ra={int(row['saves_ra'])} gp={int(row['gp_setup'])}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
