#!/usr/bin/env python3
"""Measure the decrypted executable of the pinned target, and publish it.

The tool reads the decrypted Allegrex ELF — the file that
``tools/decrypt_psp.py`` produces on the contributor's machine — and writes
the research tables under ``config/boot/``:

``config/boot/summary.json``    the structure of the executable
``config/boot/functions.tsv``   the function candidates of the code segment

The decrypted ELF is **never committed**: only the structure it yields is.
The tool reports structure and counts, and never an instruction byte.

Usage:
    python3 tools/boot_inventory.py --elf <decrypted.elf> [--out config]
    python3 tools/boot_inventory.py --elf <decrypted.elf> --check
"""

from __future__ import annotations

import argparse
import hashlib
import json
import struct
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import function_inventory  # noqa: E402
import psp_elf  # noqa: E402

#: The offset of the module info in the ~PSP header, and the layout of the
#: PSP module info that follows it.
OFF_MODINFO = 0x34


def module_info(data: bytes) -> dict[str, object]:
    """Read the PSP module info of a PRX.

    The module info names the module and lists the libraries it imports.
    It is the only part of a retail PRX that carries names.  It is found by
    its own layout rather than by a fixed offset: the attribute word, the
    version word and the module name, which is followed by the pointers to
    the library table and by the library names themselves.
    """
    marker = b"\x00\x00\x01\x01dax\x00"
    index = data.find(marker)
    if index < 0 or index + 0x60 > len(data):
        return {}
    attribute = struct.unpack_from("<H", data, index)[0]
    version = struct.unpack_from("<H", data, index + 2)[0]
    name = data[index + 4:index + 4 + 28].split(b"\x00")[0].decode("utf-8", "replace")
    libraries: list[str] = []
    offset = index + 0x34
    # The library names follow the module info as NUL-terminated strings.
    # Their padding varies, because the table is a linked list of records
    # rather than an array of fixed-size slots.
    while offset < len(data):
        end = data.find(b"\x00", offset)
        if end < 0:
            break
        entry = data[offset:end]
        if not entry:
            offset = end + 1
            continue
        if not all(0x20 <= byte < 0x7F for byte in entry):
            break
        libraries.append(entry.decode("ascii"))
        offset = end + 1
        if len(libraries) > 64:
            break
    return {
        "offset": f"0x{index:08X}",
        "attribute": attribute,
        "version": f"0x{version:04X}",
        "name": name,
        "libraries": libraries,
    }


def render(elf_path: Path) -> dict[str, str]:
    """Return the text of every table, without writing anything."""
    data = elf_path.read_bytes()
    report = psp_elf.inspect(elf_path)
    candidates = function_inventory.inventory(data)

    # The path of the local file is never published: it is a personal path.
    report.pop("path", None)
    report["source"] = "the decrypted executable of the pinned disc"
    info = module_info(data)
    report["module_info"] = info
    report["function_candidates"] = len(candidates)
    report["functions_saving_ra"] = sum(1 for row in candidates if row["saves_ra"])

    lines = ["address\tfile_offset\tframe\tsaves_ra\tgp_setup"]
    for row in candidates:
        lines.append(f"{row['address']}\t{row['file_offset']}\t{row['frame']}\t"
                     f"{int(row['saves_ra'])}\t{int(row['gp_setup'])}")

    return {
        "boot/summary.json": json.dumps(report, indent=2, sort_keys=True) + "\n",
        "boot/functions.tsv": "\n".join(lines) + "\n",
    }


def build(elf_path: Path, out: Path) -> dict[str, object]:
    """Measure the executable and write the tables."""
    tables = render(elf_path)
    for relative, text in tables.items():
        path = out / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
    return json.loads(tables["boot/summary.json"])


def check(elf_path: Path, out: Path) -> int:
    """Compare the tables on disk with the executable. Never writes."""
    failures = 0
    for relative, expected in render(elf_path).items():
        path = out / relative
        if not path.is_file():
            print(f"missing table: {relative}", file=sys.stderr)
            failures += 1
            continue
        if path.read_text(encoding="utf-8") != expected:
            print(f"table is out of date: {relative}", file=sys.stderr)
            failures += 1
    return 1 if failures else 0


def main(argv: list[str] | None = None) -> int:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--elf", type=Path, required=True)
    parser.add_argument("--out", type=Path, default=Path("config"))
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args(argv)

    if not args.elf.is_file():
        print(f"not a file: {args.elf}", file=sys.stderr)
        return 2

    if args.check:
        return check(args.elf, args.out)

    report = build(args.elf, args.out)
    print(f"executable   : {report['size']} bytes")
    print(f"sha256       : {report['sha256']}")
    print(f"type         : {report['type']}")
    print(f"entry        : {report['entry_point']}")
    print(f"segments     : {len(report['programs'])}")
    print(f"sections     : {len(report['sections'])}")
    print(f"module       : {report['module_info'].get('name')}")
    print(f"libraries    : {len(report['module_info'].get('libraries', []))}")
    print(f"candidates   : {report['function_candidates']}")
    print(f"tables       : {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
