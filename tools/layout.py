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

#: The conditional branches, and the *likely* forms of them.  The likely
#: branches execute their delay slot whatever the condition is.
CONDITIONAL = {0x04, 0x05, 0x06, 0x07, 0x14, 0x15, 0x16, 0x17}
#: The REGIMM family: bltz, bgez, and their likely forms.
REGIMM = {0x01}

REG_RA = 31
REG_T9 = 25


def _is_conditional(word: int) -> bool:
    return (word >> 26) in CONDITIONAL or (word >> 26) in REGIMM


def _is_jump(word: int) -> bool:
    """Return True for the unconditional jumps and the returns."""
    opcode = word >> 26
    if opcode == 0x08:                    # j
        return True
    if opcode == 0x0C:                    # jal target
        return True
    if (word & 0xFC000000) == OP_SPECIAL:
        funct = word & 0x3F
        if funct in (FUNCT_JR, FUNCT_JALR):
            return True
    return False


def _is_return(word: int) -> bool:
    """Return True for a return: a jump through a register."""
    if (word & 0xFC000000) != OP_SPECIAL:
        return False
    if (word & 0x3F) != FUNCT_JR:
        return False
    return ((word >> 21) & 0x1F) in (REG_RA, REG_T9)


def _is_call(word: int) -> bool:
    """Return True for a call: the control leaves and comes back."""
    if (word >> 26) == 0x0C:
        return True
    if (word & 0xFC000000) == OP_SPECIAL and (word & 0x3F) == FUNCT_JALR:
        return True
    return False


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


def body_reachable(segment: bytes, start_index: int, limit_index: int) -> set[int]:
    """Return the instructions a body reaches, and no other.

    This is the control-flow graph of the body, and it is what the review
    of wave 1 measured as the rule of the end:

        the body ends at the last instruction the graph reaches, plus four.

    Three rules make the graph right, and each of them was bought by a
    review:

    * the **delay slot** of a branch or a jump is executed.  The successor
      of a branch is at ``pc + 8``, not at ``pc + 4``.
    * a **call** does not transfer the control: the body continues after
      it, and the callee is not part of the body.
    * a **return** ends the path, and its delay slot is the last
      instruction of the body.
    """
    reachable: set[int] = set()
    pending = [start_index]
    while pending:
        index = pending.pop()
        if index in reachable:
            continue
        if index < 0 or index + 4 > limit_index:
            continue
        reachable.add(index)
        word = struct.unpack_from("<I", segment, index)[0]

        if _is_return(word):
            # The delay slot of the return is executed, and then the
            # control leaves the body.
            if index + 8 <= limit_index:
                reachable.add(index + 4)
            continue

        if _is_call(word):
            # The delay slot is executed, and the body continues after
            # the call.  The callee is another body.
            if index + 8 <= limit_index:
                reachable.add(index + 4)
                pending.append(index + 8)
            continue

        if _is_conditional(word):
            # The delay slot is executed, and either branch is possible.
            if index + 8 <= limit_index:
                reachable.add(index + 4)
                pending.append(index + 8)
            target = _branch_target(word, index)
            if target is not None:
                pending.append(target)
            continue

        if _is_jump(word):
            # The delay slot is executed, and the control leaves.
            if index + 8 <= limit_index:
                reachable.add(index + 4)
            target = _branch_target(word, index)
            if target is not None:
                pending.append(target)
            continue

        pending.append(index + 4)
    return reachable


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
    # A **strong** start is a call target or a place that opens a frame.
    # Both of them begin a body, and a body runs from there to its last
    # return before the next strong start.
    #
    # A place that merely *follows* a return is a **weak** signal: a body
    # can have two epilogues, or a cold path after its epilogue, and the
    # instruction after a return is then still inside the body. Using it
    # as a start cuts those bodies at their first return, which is wrong.
    # It is kept as evidence, not as a boundary.
    after_return: set[int] = set()
    for index in sorted(returns):
        following = index + 8
        if following + 4 <= len(segment):
            after_return.add(following)

    frame_openers = set()
    for row in function_inventory.inventory(data):
        frame_openers.add(int(str(row["file_offset"]), 16) - offset)

    evidence: dict[int, set[str]] = defaultdict(set)
    strong: set[int] = set()
    for target in call_sites:
        evidence[target].add("call")
        strong.add(target)
    for index in after_return:
        evidence[vaddr + index].add("after_return")
    for index in frame_openers:
        evidence[vaddr + index].add("frame")
        strong.add(vaddr + index)

    # --- the bodies ------------------------------------------------------
    # The body of a function is the set of instructions its control-flow
    # graph reaches.  A call target is never part of it: a call does not
    # transfer the control.  The bound is the last instruction the graph
    # reaches, plus four - the rule the review of wave 1 measured.
    ordered = sorted(strong)
    bodies: list[dict[str, object]] = []
    for position, start in enumerate(ordered):
        start_index = start - vaddr
        if start_index < 0 or start_index >= len(segment):
            continue
        # The graph is bounded by the next strong start.  A strong start
        # inside the body is a call target, which the graph does not
        # follow, so the bound holds; if the graph does reach it, the body
        # has no return, and the bound moves on.
        limit_index = len(segment)
        reachable: set[int] = set()
        for attempt in range(4):
            if position + attempt + 1 < len(ordered):
                candidate = ordered[position + attempt + 1] - vaddr
            else:
                candidate = len(segment)
            reachable = body_reachable(segment, start_index, candidate)
            limit_index = candidate
            if candidate >= len(segment) or candidate not in reachable:
                break
        if not reachable:
            continue
        end_index = min(max(reachable) + 4, len(segment))
        if end_index <= start_index:
            continue
        evidence_here = evidence.get(start, set())
        bodies.append({
            "start": start,
            "end": vaddr + end_index,
            "size": end_index - start_index,
            "bound_source": ("call" if "call" in evidence_here else
                             "after_return" if "after_return" in evidence_here
                             else "frame"),
            "evidence": ",".join(sorted(evidence_here)),
            "calls": call_sites.get(start, 0),
            "returns": sum(1 for index in returns
                           if start_index <= index < end_index),
        })

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
    parser.add_argument("--skip", type=int, default=0,
                        help="skip the first N shortlist entries, to cut the "
                             "lots of the next wave without re-cutting the "
                             "ones already reviewed")
    parser.add_argument("--first-lot", type=int, default=1,
                        help="the number of the first lot to write")
    args = parser.parse_args(argv)

    data = args.elf.read_bytes()
    calls, bodies = analyse(data)

    write_calls(args.work / "E0" / "calls.tsv", calls)
    write_bounds(args.work / "E0" / "bounds.tsv", bodies)

    # The shortlist: the bounded candidates that a call reaches, ranked by
    # leverage, then stratified by size.
    eligible = [row for row in bodies if int(row["calls"]) > 0]
    eligible.sort(key=lambda row: (-int(row["calls"]), -int(row["size"])))
    shortlist = pick_stratified(eligible, args.skip + args.lots * args.per_lot)
    shortlist = shortlist[args.skip:]

    lots_dir = args.work / "lots"
    lots_dir.mkdir(parents=True, exist_ok=True)
    for index in range(args.lots):
        chunk = shortlist[index * args.per_lot:(index + 1) * args.per_lot]
        path = lots_dir / f"L{args.first_lot + index:02d}.tsv"
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
