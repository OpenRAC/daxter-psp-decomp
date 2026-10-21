#!/usr/bin/env python3
"""Establish the layout of the code: the call graph and the bounded bodies.

This is the **foundation lot** of the project, the piece the sibling
OpenRAC projects call *layout*.  Its job is to turn the raw frame-opening
candidates of ``tools/function_inventory.py`` into **bounded candidates**:
a start, an end, and the evidence that the range really is one body.

It writes three private artifacts, all of which stay out of the repository:

``work/E0/calls.tsv``     the call graph: every call site and its target
``work/E0/bounds.tsv``    the bounded candidates, with the proof of each bound
``work/lots/L*.tsv``      the lots, ranked by leverage

The method
----------

The retail executable is stripped, so the boundaries have to be recovered
from the code.  Three observations are used, and each of them is recorded
as the *evidence* of the candidate:

1. **A call names a function.**  Every ``jal`` target is the start of a
   function.  This is the strongest evidence there is.
2. **A return ends a body.**  A ``jr $ra`` is the end of a return path.
   The body of a function ends at its *last* return, not its first.
3. **A function often starts right after a return.**  In stripped code the
   next function usually follows the previous one's epilogue.

A candidate is therefore a function start that is a call target, or that
follows a return, or that opens a frame; and its body runs to the last
return before the next such start.

**Leverage** is the number of call sites that carry the same body.  It is
the ranking the shortlist uses: a body that many places call is worth more
than a rare large one, because one authored source can satisfy all of them.

Usage:
    python3 tools/layout.py --elf <decrypted.elf> [--work work] [--lots 6]
                            [--per-lot 40]
"""

from __future__ import annotations

import argparse
import csv
import struct
import sys
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import function_inventory  # noqa: E402

#: The instructions the sweep looks for.
OP_JAL = 0x0C000000          # jal target
OP_J = 0x08000000           # j target
OP_BEQ = 0x10000000         # beq rs, rt, offset
OP_BNE = 0x14000000         # bne rs, rt, offset
OP_SPECIAL = 0x00000000     # the SPECIAL opcode, which carries jr and jalr
FUNCT_JR = 0x08
FUNCT_JALR = 0x09
OP_ADDiu_SP = 0x27BD0000    # addiu $sp, $sp, imm

REG_RA = 31
REG_T9 = 25


def _insn(data: bytes, offset: int) -> int:
    return struct.unpack_from("<I", data, offset)[0]


def _branch_target(word: int, pc: int) -> int | None:
    """Return the target of a branch, if the instruction is one."""
    opcode = word & 0xFC000000
    if opcode == OP_JAL or opcode == OP_J:
        return ((pc + 4) & 0xF0000000) | ((word & 0x03FFFFFF) << 2)
    if opcode == OP_BEQ or opcode == OP_BNE:
        return pc + 4 + ((word & 0xFFFF) << 2 if not (word & 0x8000)
                         else ((word & 0xFFFF) - 0x10000) << 2)
    return None


def analyse(data: bytes) -> tuple[list[dict[str, object]], list[dict[str, object]]]:
    """Return the call graph and the bounded candidates of the executable."""
    ranges = function_inventory.executable_ranges(data)
    if not ranges:
        raise ValueError("the executable has no executable segment")

    offset, size, vaddr = ranges[0]
    segment = data[offset:offset + size]

    # --- the call graph -------------------------------------------------
    call_sites: dict[int, int] = defaultdict(int)
    branch_targets: set[int] = set()
    returns: set[int] = set()

    for index in range(0, max(0, len(segment) - 4), 4):
        word = _insn(segment, index)
        pc = vaddr + index
        if (word & 0xFC000000) == OP_JAL:
            target = _branch_target(word, pc)
            if target is not None:
                call_sites[target] += 1
        elif (word & 0xFC000000) in (OP_J, OP_BEQ, OP_BNE):
            target = _branch_target(word, pc)
            if target is not None:
                branch_targets.add(target)
        if (word & 0xFC000000) == OP_SPECIAL and (word & 0x3F) == FUNCT_JR:
            register = (word >> 21) & 0x1F
            if register in (REG_RA, REG_T9):
                returns.add(index)

    # --- the function starts ---------------------------------------------
    # A start is a call target, the instruction that follows a return, or
    # a place that opens a frame.  A branch target on its own is not: a
    # loop header is not a function.
    after_return: set[int] = set()
    for index in sorted(returns):
        following = index + 8
        if following + 4 <= len(segment):
            after_return.add(following)

    frame_openers = set()
    for row in function_inventory.inventory(data):
        frame_openers.add(int(str(row["file_offset"]), 16) - offset)

    evidence: dict[int, set[str]] = defaultdict(set)
    for target in call_sites:
        evidence[target].add("call")
    for index in after_return:
        evidence[vaddr + index].add("after_return")
    for index in frame_openers:
        evidence[vaddr + index].add("frame")

    # --- the bodies ------------------------------------------------------
    # A call target *inside* a body that has not returned yet does not
    # split it: it is a call, not a new function.  A body therefore runs to
    # its last return before the next start that follows a return.
    ordered = sorted(evidence)
    bodies: list[dict[str, object]] = []
    body_start: int | None = None
    body_evidence: set[str] = set()

    def close_body(last_return_index: int) -> None:
        nonlocal body_start, body_evidence
        if body_start is None:
            return
        start_index = body_start - vaddr
        end_index = min(last_return_index + 8, len(segment))
        bodies.append({
            "start": body_start,
            "end": vaddr + end_index,
            "size": end_index - start_index,
            "bound_source": ("call" if "call" in body_evidence else
                             "after_return" if "after_return" in body_evidence
                             else "frame"),
            "evidence": ",".join(sorted(body_evidence)),
            "calls": call_sites.get(body_start, 0),
            "returns": sum(1 for index in returns
                           if start_index <= index < end_index),
        })
        body_start = None
        body_evidence = set()

    returns_sorted = sorted(returns)
    for position in ordered:
        position_index = position - vaddr
        if position_index < 0 or position_index >= len(segment):
            continue
        last_return = None
        for index in returns_sorted:
            if index < position_index:
                last_return = index
            else:
                break
        if body_start is None:
            body_start = position
            body_evidence = set(evidence[position])
            continue
        if last_return is None:
            # The open body has not returned yet: this start is a call
            # inside it, and does not split it.
            body_evidence |= evidence[position]
            continue
        close_body(last_return)
        body_start = position
        body_evidence = set(evidence[position])

    if body_start is not None:
        last_return = None
        for index in returns_sorted:
            if index < len(segment):
                last_return = index
        if last_return is not None:
            close_body(last_return)

    calls = [
        {"address": target, "sites": count}
        for target, count in sorted(call_sites.items(), key=lambda kv: -kv[1])
    ]
    return calls, bodies


def write_calls(path: Path, calls: list[dict[str, object]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle, delimiter="\t", lineterminator="\n")
        writer.writerow(["target", "sites"])
        for row in calls:
            writer.writerow([f"0x{int(row['address']):08X}", row["sites"]])


def write_bounds(path: Path, bodies: list[dict[str, object]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle, delimiter="\t", lineterminator="\n")
        writer.writerow(["start", "end", "size", "bound_source", "evidence",
                         "calls", "returns"])
        for row in bodies:
            writer.writerow([f"0x{int(row['start']):08X}",
                             f"0x{int(row['end']):08X}",
                             row["size"], row["bound_source"], row["evidence"],
                             row["calls"], row["returns"]])


#: The size buckets, so that a wave spans several body sizes instead of
#: filling up with stubs.
BUCKETS = [(16, 64), (64, 128), (128, 256), (256, 512), (512, 1024),
           (1024, 4096)]


def pick_stratified(rows: list[dict[str, object]], take: int) -> list[dict[str, object]]:
    """Round-robin over the size buckets, so a wave is not all stubs."""
    buckets = [[row for row in rows if low <= int(row["size"]) < high]
               for low, high in BUCKETS]
    chosen: list[dict[str, object]] = []
    cursors = [0] * len(buckets)
    while len(chosen) < take:
        progressed = False
        for index, bucket in enumerate(buckets):
            if len(chosen) >= take:
                break
            if cursors[index] < len(bucket):
                chosen.append(bucket[cursors[index]])
                cursors[index] += 1
                progressed = True
        if not progressed:
            break
    return sorted(chosen, key=lambda row: int(row["start"]))


def main(argv: list[str] | None = None) -> int:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--elf", type=Path, required=True)
    parser.add_argument("--work", type=Path, default=Path("work"))
    parser.add_argument("--lots", type=int, default=6)
    parser.add_argument("--per-lot", type=int, default=40)
    args = parser.parse_args(argv)

    data = args.elf.read_bytes()
    calls, bodies = analyse(data)

    write_calls(args.work / "E0" / "calls.tsv", calls)
    write_bounds(args.work / "E0" / "bounds.tsv", bodies)

    # The shortlist: the bounded candidates that a call reaches, ranked by
    # leverage, then stratified by size.
    eligible = [row for row in bodies if int(row["calls"]) > 0]
    eligible.sort(key=lambda row: (-int(row["calls"]), -int(row["size"])))
    shortlist = pick_stratified(eligible, args.lots * args.per_lot)

    lots_dir = args.work / "lots"
    lots_dir.mkdir(parents=True, exist_ok=True)
    for index in range(args.lots):
        chunk = shortlist[index * args.per_lot:(index + 1) * args.per_lot]
        path = lots_dir / f"L{index + 1:02d}.tsv"
        with path.open("w", encoding="utf-8", newline="") as handle:
            writer = csv.writer(handle, delimiter="\t", lineterminator="\n")
            writer.writerow(["start", "end", "size", "bound_source", "evidence",
                             "calls", "returns"])
            for row in chunk:
                writer.writerow([f"0x{int(row['start']):08X}",
                                 f"0x{int(row['end']):08X}",
                                 row["size"], row["bound_source"], row["evidence"],
                                 row["calls"], row["returns"]])
        print(f"{path.name}: {len(chunk)} targets")

    print(f"call targets      : {len(calls)}")
    print(f"bounded candidates: {len(bodies)}")
    print(f"called candidates : {len(eligible)}")
    print(f"shortlist         : {len(shortlist)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
