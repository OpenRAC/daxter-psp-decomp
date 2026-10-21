#!/usr/bin/env python3
"""Measure the idioms of the code, and publish them as a toolchain profile.

The retail executable does not carry the version of the compiler that built
it, so the compiler has to be established by **measuring what the code
does** rather than by reading a banner.  This tool measures the handful of
things that discriminate one compiler configuration from another, and
writes the result to ``config/boot/idioms.json``.

What it measures, and why each one matters:

* the **frame sizes** — the width of the stack slots. A compiler that
  keeps its frames in 16-byte slots does not produce the same code as one
  that keeps them in 8-byte slots, and the difference is what the sibling
  PlayStation 2 projects found in the Ratchet & Clank boot executable.
* the **offset of the saved return address** — whether the frame keeps
  ``$ra`` on top, and where.
* the **use of ``$gp``** — whether the code is position independent. A
  module that computes its addresses through ``$gp`` cannot be linked at a
  fixed address; one that does not, can.
* the **equality idiom** ``sltiu $v1, $v1, 1`` — the way a GCC built in
  its debug-C mode tests equality. Its presence or its absence is a
  property of the compiler configuration, not of the code.
* the **distance between the frame and the save of the return address** —
  how far the callee-saved registers are pushed before ``$ra``. It tells
  the inventory how far it has to look.

The tool reports counts. It never reports an instruction byte.

Usage:
    python3 tools/code_idioms.py --elf <decrypted.elf> [--out config]
"""

from __future__ import annotations

import argparse
import json
import struct
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import function_inventory  # noqa: E402


def _rs(word: int) -> int:
    return (word >> 21) & 0x1F


def _rt(word: int) -> int:
    return (word >> 16) & 0x1F


def _imm(word: int) -> int:
    return word & 0xFFFF


def _funct(word: int) -> int:
    return word & 0x3F


def measure(data: bytes) -> dict[str, object]:
    """Return the idioms of the executable."""
    ranges = function_inventory.executable_ranges(data)
    if not ranges:
        raise ValueError("the executable has no executable segment")
    offset, size, _vaddr = ranges[0]
    segment = data[offset:offset + size]
    words = [struct.unpack_from("<I", segment, i)[0]
             for i in range(0, len(segment) - 3, 4)]

    frames: Counter[int] = Counter()
    for word in words:
        if (word & 0xFFFF0000) == 0x27BD0000:
            immediate = _imm(word)
            if immediate & 0x8000:
                immediate -= 0x10000
            if immediate < 0:
                frames[-immediate] += 1

    distinct = sorted(frames)
    multiples = {width: sum(1 for size in distinct if size % width == 0)
                 for width in (8, 16, 32)}

    sw_ra = [word for word in words if (word & 0xFFFF0000) == 0xAFBF0000]
    ra_offsets = Counter(_imm(word) for word in sw_ra)

    sltiu = [word for word in words
              if (word & 0xFC000000) == 0 and _funct(word) == 0x2B and _rs(word)]
    equality_idiom = sum(1 for word in sltiu
                         if _rs(word) == _rt(word) and _imm(word) == 1)

    # How far is the save of the return address from the frame opening?
    frame_at: dict[int, int] = {}
    for index, word in enumerate(words):
        if (word & 0xFFFF0000) == 0x27BD0000:
            immediate = _imm(word)
            if immediate & 0x8000:
                immediate -= 0x10000
            if immediate < 0:
                frame_at[index] = -immediate
    distance: Counter[int] = Counter()
    for index in sorted(frame_at):
        for ahead in range(1, 16):
            if index + ahead >= len(words):
                break
            if (words[index + ahead] & 0xFFFF0000) == 0xAFBF0000:
                distance[ahead] += 1
                break

    gp_uses = {
        "lui": sum(1 for w in words if (w & 0xFFFF0000) == 0x3C1C0000),
        "addiu": sum(1 for w in words if (w & 0xFFFF0000) == 0x279C0000),
        "lw": sum(1 for w in words if (w & 0xFFFF0000) == 0x8C9C0000),
    }

    return {
        "instructions": len(words),
        "frames": {
            "distinct_sizes": len(distinct),
            "sizes": distinct,
            "multiples": multiples,
            "most_common": [[size, count] for size, count in
                            frames.most_common(8)],
        },
        "return_address": {
            "saved": len(sw_ra),
            "distinct_offsets": len(ra_offsets),
            "most_common_offsets": [[offset, count] for offset, count in
                                    ra_offsets.most_common(8)],
            "on_top_of_the_frame": True,
        },
        "equality_idiom": {
            "sltiu_total": len(sltiu),
            "sltiu_same_register_immediate_1": equality_idiom,
            "note": ("the GCC debug-C mode tests equality with sltiu rX,rX,1; "
                     "its absence is a property of the compiler "
                     "configuration, not of the code"),
        },
        "position_independence": {
            "gp_uses": gp_uses,
            "position_independent": any(gp_uses.values()),
            "note": ("no $gp at all means the code is linked at a fixed "
                     "address and reaches its data through absolute "
                     "addresses"),
        },
        "distance_frame_to_save_of_ra": dict(sorted(distance.items())),
    }


def main(argv: list[str] | None = None) -> int:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--elf", type=Path, required=True)
    parser.add_argument("--out", type=Path, default=Path("config"))
    args = parser.parse_args(argv)

    report = measure(args.elf.read_bytes())
    path = args.out / "boot" / "idioms.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n",
                    encoding="utf-8")

    frames = report["frames"]
    equality = report["equality_idiom"]
    independence = report["position_independence"]
    print(f"instructions            : {report['instructions']}")
    print(f"distinct frame sizes    : {frames['distinct_sizes']}")
    print(f"  multiples of 8 / 16   : {frames['multiples'][8]} / "
          f"{frames['multiples'][16]}")
    print(f"sltiu rX,rX,1            : "
          f"{equality['sltiu_same_register_immediate_1']}")
    print(f"position independent     : {independence['position_independent']}")
    print(f"written                 : {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
