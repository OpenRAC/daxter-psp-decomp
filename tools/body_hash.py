#!/usr/bin/env python3
"""Find the bodies that are the same body.

Two functions of a program often hold the same code: the compiler inlined
a helper, or the source was written twice.  When the bytes of two bodies
are identical, the second one is a **placement** of the first, and one
authored source satisfies both.

This is the cheapest help there is for the naming work, and the cheapest
one for the compiler work too: a body that appears twice in the retail
code has been produced by the same source twice, so the source has to
explain both.

The tool reads the reviewed layout, hashes the body of each of them, and
groups the bodies that share a hash.

Usage:
    python3 tools/body_hash.py --elf <decrypted.elf> \\
        --layout config/boot/layout.tsv [--tsv] [--json]
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import sys
from pathlib import Path


def segments(data: bytes) -> list[tuple[int, int, int]]:
    """Return the (file offset, file size, virtual address) of the loads."""
    if data[:4] != b"\x7fELF":
        return []
    _kind, _machine, _version, _entry, phoff, _shoff, _flags, _ehsize, \
        phentsize, phnum, _shentsize, _shnum, _shstrndx = struct.unpack_from(
            "<HHIIIIIHHHHHH", data, 16)
    out = []
    for index in range(phnum):
        ptype, offset, vaddr, _paddr, size, _memsz, _flags, _align = \
            struct.unpack_from("<IIIIIIII", data, phoff + index * phentsize)
        if ptype == 1:
            out.append((offset, size, vaddr))
    return out


def body_bytes(data: bytes, loads, start: int, end: int) -> bytes | None:
    """Return the bytes of a body, or ``None`` when it is not readable."""
    for offset, size, vaddr in loads:
        if vaddr <= start and end <= vaddr + size:
            begin = offset + (start - vaddr)
            return data[begin:begin + (end - start)]
    return None


def main(argv: list[str] | None = None) -> int:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--elf", type=Path, required=True)
    parser.add_argument("--layout", type=Path,
                        default=Path("config/boot/layout.tsv"))
    parser.add_argument("--tsv", action="store_true")
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--write", type=Path, default=None,
                        help="write the placement table to this path")
    args = parser.parse_args(argv)

    data = args.elf.read_bytes()
    loads = segments(data)

    with args.layout.open(encoding="utf-8", newline="") as handle:
        rows = list(csv.DictReader(handle, delimiter="\t"))

    groups: dict[str, list[dict[str, str]]] = {}
    hashed = 0
    for row in rows:
        if not row.get("start") or not row.get("end"):
            continue
        start = int(row["start"], 16)
        end = int(row["end"], 16)
        blob = body_bytes(data, loads, start, end)
        if not blob:
            continue
        hashed += 1
        digest = hashlib.sha256(blob).hexdigest()
        groups.setdefault(digest, []).append(row)

    shared = {digest: members for digest, members in groups.items()
              if len(members) > 1}
    placements = sum(len(members) for members in shared.values())
    distinct = len(groups)

    if args.write:
        args.write.parent.mkdir(parents=True, exist_ok=True)
        with args.write.open("w", encoding="utf-8", newline="") as handle:
            writer = csv.writer(handle, delimiter="\t", lineterminator="\n")
            writer.writerow(["sha256", "placements", "starts", "size", "name"])
            for digest, members in sorted(shared.items(),
                                          key=lambda kv: -len(kv[1])):
                writer.writerow([
                    digest, len(members),
                    ",".join(member["start"] for member in members),
                    members[0].get("size", ""),
                    members[0].get("name", ""),
                ])

    if args.json:
        print(json.dumps({
            "hashed": hashed,
            "distinct_bodies": distinct,
            "shared_groups": len(shared),
            "shared_bodies": placements,
        }, indent=2))
        return 0

    if args.tsv:
        print("sha256\tcount\tstarts")
        for digest, members in sorted(shared.items(),
                                      key=lambda kv: -len(kv[1])):
            print("%s\t%d\t%s" % (digest, len(members),
                                  ",".join(m["start"] for m in members)))
        return 0

    print(f"bodies hashed       : {hashed}")
    print(f"distinct bodies     : {distinct}")
    print(f"shared groups       : {len(shared)}")
    print(f"bodies that share   : {placements}")
    if shared:
        print()
        for digest, members in sorted(shared.items(),
                                      key=lambda kv: -len(kv[1]))[:16]:
            names = sorted({m["name"] for m in members})
            print(f"  {len(members)} bodies  {digest[:16]}  "
                  f"{', '.join(m['start'] for m in members)}")
            if len(names) > 1:
                print(f"      names: {', '.join(names)}")
    return 0


if __name__ == "__main__":
    import struct  # noqa: E402  (used by segments)
    raise SystemExit(main())
