#!/usr/bin/env python3
"""Compare a compiled body with the retail bytes, byte for byte.

This is the harness of the body gate.  It takes an object file, the symbol
that holds the body, and the address the body has in the retail executable;
it extracts the compiled bytes of that symbol and compares them with the
retail bytes at that address.

The result is the only thing that counts as a proof:

* ``exact`` — every byte of the range matches;
* ``mismatch`` — the bytes differ, and the tool says **where** and
  **how**;
* ``refused`` — the comparison cannot be made, and the tool says why.

A refusal is not an attempt.  It is reported as such, and it counts for
nothing.

Usage:
    python3 tools/harness.py --elf <retail.elf> --object <body.o> \\
        --symbol <name> --address 0x1234 [--size N] [--json]
"""

from __future__ import annotations

import argparse
import json
import struct
import sys
from pathlib import Path

ELF_HEADER = struct.Struct("<HHIIIIIHHHHHH")
SECTION_HEADER = struct.Struct("<IIIIIIIIII")
ELF_SYMBOL = struct.Struct("<IIIBBH")

SHT_SYMTAB = 2
STT_FUNC = 2


class Refusal(Exception):
    """Raised when the comparison cannot be made."""


def read_symbols(data: bytes) -> dict[str, dict[str, object]]:
    """Return the function symbols of an object, with their bytes."""
    if data[:4] != b"\x7fELF":
        raise Refusal("the object is not an ELF")
    (_kind, _machine, _version, _entry, _phoff, _shoff, _flags, _ehsize,
     _phentsize, _phnum, shentsize, shnum, shstrndx) = ELF_HEADER.unpack_from(
        data, 16)
    if shnum == 0:
        raise Refusal("the object has no section headers")

    sections = [SECTION_HEADER.unpack_from(data, _shoff + index * shentsize)
                for index in range(shnum)]
    out: dict[str, dict[str, object]] = {}
    for section in sections:
        (_name, stype, _flags, _addr, offset, size, link, _info, _align,
         entsize) = section
        if stype != SHT_SYMTAB or not size:
            continue
        if link >= len(sections):
            continue
        str_section = sections[link]
        strtab = data[str_section[4]:str_section[4] + str_section[5]]
        entry_size = entsize or ELF_SYMBOL.size
        for index in range(size // entry_size):
            base = offset + index * entry_size
            st_name, st_value, st_size, st_info, _other, st_shndx = \
                ELF_SYMBOL.unpack_from(data, base)
            if (st_info & 0xF) != STT_FUNC or not st_size:
                continue
            end = strtab.find(b"\x00", st_name)
            name = strtab[st_name:end if end >= 0 else st_name].decode(
                "utf-8", "replace")
            out[name] = {
                "value": st_value,
                "size": st_size,
                "section": st_shndx,
                "bytes": data[st_value:st_value + st_size],
            }
    return out


def retail_bytes(elf: bytes, address: int, size: int) -> bytes:
    """Return the retail bytes at an address, or refuse.

    The mapping comes from the program headers of the executable itself,
    not from a table: the target is a PSP PRX whose code segment is at
    file offset 0x74 for the virtual address zero, and whose data segment
    is at 0x00363B08 for 0x00363A98.
    """
    if elf[:4] != b"\x7fELF":
        raise Refusal("the retail executable is not an ELF")
    (_kind, _machine, _version, _entry, phoff, _shoff, _flags, _ehsize,
     phentsize, phnum, _shentsize, _shnum, _shstrndx) = ELF_HEADER.unpack_from(
        elf, 16)
    for index in range(phnum):
        base = phoff + index * phentsize
        ptype, offset, vaddr, _paddr, length, _memsz, _flags, _align = \
            struct.unpack_from("<IIIIIIII", elf, base)
        if ptype != 1:
            continue
        if not (vaddr <= address < vaddr + length):
            continue
        start = offset + (address - vaddr)
        if start + size > len(elf):
            raise Refusal("the retail range runs past the end of the file")
        return elf[start:start + size]
    raise Refusal(f"the address 0x{address:08X} is in no segment")


def compare(compiled: bytes, retail: bytes) -> dict[str, object]:
    """Compare the two byte strings and describe the difference."""
    if len(compiled) != len(retail):
        return {
            "result": "mismatch",
            "reason": "the sizes differ",
            "compiled_size": len(compiled),
            "retail_size": len(retail),
        }
    if compiled == retail:
        return {"result": "exact", "size": len(compiled)}
    for index, (left, right) in enumerate(zip(compiled, retail)):
        if left != right:
            start = max(0, index - 8)
            return {
                "result": "mismatch",
                "first_difference": index,
                "compiled": compiled[start:index + 8].hex(" "),
                "retail": retail[start:index + 8].hex(" "),
                "size": len(compiled),
            }
    return {"result": "exact", "size": len(compiled)}


def compare_symbols(elf_path: Path, object_path: Path, symbol: str,
                    address: int, size: int = 0) -> dict[str, object]:
    """Compare a compiled symbol with the retail bytes at an address.

    The report always has a ``result``: ``exact``, ``mismatch`` or
    ``refused``.  A refusal says why, and counts for nothing.
    """
    try:
        elf = Path(elf_path).read_bytes()
        symbols = read_symbols(Path(object_path).read_bytes())
        if symbol not in symbols:
            raise Refusal(f"the object has no function symbol {symbol!r}")
        entry = symbols[symbol]
        compiled_size = int(entry["size"])
        if compiled_size <= 0:
            raise Refusal("the body has no size")
        if size and size != compiled_size:
            # The caller knows the length of the retail body; a compiled
            # body of another length is a mismatch of the body itself, not
            # a comparison that can be made.
            return {
                "result": "mismatch",
                "reason": "the compiled body has another size",
                "compiled_size": compiled_size,
                "requested_size": size,
                "symbol": symbol,
                "address": f"0x{address:08X}",
            }
        length = size or compiled_size
        compiled = bytes(entry["bytes"])[:length]
        if len(compiled) < length:
            raise Refusal("the object holds fewer bytes than the body")
        retail = retail_bytes(elf, address, length)
        report = compare(compiled, retail)
        report["symbol"] = symbol
        report["address"] = f"0x{address:08X}"
        return report
    except Refusal as refusal:
        return {"result": "refused", "reason": str(refusal)}
    except OSError as error:
        return {"result": "refused", "reason": str(error)}


def main(argv: list[str] | None = None) -> int:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--elf", type=Path, required=True,
                        help="the decrypted retail executable")
    parser.add_argument("--object", type=Path, required=True)
    parser.add_argument("--symbol", required=True)
    parser.add_argument("--address", type=lambda v: int(v, 0), required=True,
                        help="the address of the body in the retail "
                             "executable")
    parser.add_argument("--size", type=int, default=0,
                        help="the size of the body; by default the size of "
                             "the compiled symbol")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)

    report = compare_symbols(args.elf, args.object, args.symbol, args.address,
                             args.size)
    if args.json:
        print(json.dumps(report, indent=2))
    else:
        for key, value in report.items():
            print(f"  {key}: {value}")
    return 0 if report["result"] == "exact" else 1


if __name__ == "__main__":
    raise SystemExit(main())
