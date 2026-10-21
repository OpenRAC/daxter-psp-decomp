#!/usr/bin/env python3
"""Map the functions of the target to the strings they reference.

The executable is stripped, so a function has no name.  But the code
reaches its data through absolute addresses, and the strings it reads are
often the assert messages of the engine: a body that reads
``CFile::Open(%s)`` belongs to ``CFile``, and a body that reads the path
of a source file belongs to that file.

This tool resolves, for every function of the reviewed layout, the strings
it references.  It is the naming aid of the next wave.

The catalogue it writes is **private**: it holds the text of the game.  It
goes under ``work/``, never in the repository.  What the repository
publishes is the count of the functions that carry a string, and the
addresses of the strings themselves.

Usage:
    python3 tools/function_strings.py --elf <decrypted.elf> \\
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
import regflow  # noqa: E402

#: The offsets of the two program headers, and the data segment's.
CODE_SEGMENT = 0
DATA_SEGMENT = 1

#: The code segment of the target: it starts at the virtual address zero,
#: and its file offset is 0x74.
CODE_VADDR = 0x00000000
CODE_SIZE = 3553940
CODE_FILE_OFFSET = 0x74

#: The instruction forms that complete an absolute address.
COMPLETIONS = {
    # addiu rt, rs, imm   -> rt = rs + imm
    0x24000000: "addiu",
    # ori rt, rs, imm    -> rt = rs | imm
    0x34000000: "ori",
    # lw rt, off(rs)     -> rt = mem[rs + off]
    0x8C000000: "lw",
}


def _rs(word: int) -> int:
    return (word >> 21) & 0x1F


def _rt(word: int) -> int:
    return (word >> 16) & 0x1F


def _imm(word: int) -> int:
    return word & 0xFFFF


def _opcode(word: int) -> int:
    return word & 0xFC000000


def read_layout(path: Path) -> list[tuple[int, int]]:
    """Return the (start, end) of the reviewed functions."""
    if not path.is_file():
        return []
    out = []
    with path.open(encoding="utf-8", newline="") as handle:
        for row in csv.DictReader(handle, delimiter="\t"):
            if not row.get("start"):
                continue
            out.append((int(row["start"], 16), int(row["end"], 16)))
    return out


def segments(data: bytes) -> list[tuple[int, int, int, int]]:
    """Return the (file offset, size, virtual address, flags) of the loads."""
    header, programs, _sections = psp_elf._headers(data)
    out = []
    for ptype, offset, vaddr, _paddr, filesz, _memsz, flags, _align in programs:
        if ptype == 1:
            out.append((offset, filesz, vaddr, flags))
    return out


def addresses_of(data: bytes, start: int, end: int,
                 loads: list[tuple[int, int, int, int]]) -> list[int]:
    """Return the absolute addresses the body builds.

    The code is not position independent: an address is built in two steps,
    a ``lui`` that loads the high half and an ``addiu``, an ``ori`` or a
    ``lw`` that completes it.  The pair is recognised by the register they
    share — and a register that is written in between **kills** the high
    half, which is what keeps a superseded ``lui`` from pairing with a
    later completion.
    """
    segment = data[CODE_FILE_OFFSET:CODE_FILE_OFFSET + CODE_SIZE]

    def load_word(address: int) -> int | None:
        offset = to_file(loads, address)
        if offset is None or offset + 4 > len(data):
            return None
        return struct.unpack_from("<I", data, offset)[0]

    return regflow.addresses(segment, start - CODE_VADDR, end - CODE_VADDR,
                             load_word)


def to_file(loads: list[tuple[int, int, int, int]], address: int) -> int | None:
    """Return the file offset of a virtual address, or ``None``."""
    for offset, size, vaddr, _flags in loads:
        if vaddr <= address < vaddr + size:
            return offset + (address - vaddr)
    return None


def data_ranges(data: bytes) -> list[tuple[int, int]]:
    """Return the (virtual address, end) of the allocatable data sections.

    A section is data when it is allocated, is not executable, and holds
    something.  The code is excluded, and so is the zero-filled bss.
    """
    if data[:4] != b"\x7fELF":
        return []
    (_kind, _machine, _version, _entry, _phoff, _shoff, _flags, _ehsize,
     _phentsize, _phnum, _shentsize, _shnum, _shstrndx) = struct.unpack_from(
        "<HHIIIIIHHHHHH", data, 16)
    out = []
    for index in range(_shnum):
        _name, stype, sflags, saddr, _offset, ssize, _link, _info, \
            _align, _entsize = struct.unpack_from(
                "<IIIIIIIIII", data, _shoff + index * _shentsize)
        if not (sflags & 0x2) or (sflags & 0x4) or stype == 8 or not ssize:
            continue
        out.append((saddr, saddr + ssize))
    return out


def string_at(data: bytes, loads: list[tuple[int, int, int, int]],
              address: int, ranges: list[tuple[int, int]]) -> str | None:
    """Return the string a virtual address points at, or ``None``.

    The address has to be in a **data** section.  A code address can hold
    printable bytes, and a run of them can look exactly like a string: the
    review of wave 3 found a body that "read" a comma and a body that
    "read" the digit four, and both of them were code.
    """
    if not any(low <= address < high for low, high in ranges):
        return None
    offset = to_file(loads, address)
    if offset is None or offset + 1 > len(data):
        return None
    if not (0x20 <= data[offset] < 0x7F):
        return None
    end = data.find(b"\x00", offset, offset + 512)
    if end < 0:
        return None
    text = data[offset:end]
    if not all(0x20 <= byte < 0x7F for byte in text):
        return None
    return text.decode("ascii")


def main(argv: list[str] | None = None) -> int:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--elf", type=Path, required=True)
    parser.add_argument("--layout", type=Path,
                        default=Path("config/boot/layout.tsv"))
    parser.add_argument("--out", type=Path, default=Path("work/E0"))
    args = parser.parse_args(argv)

    data = args.elf.read_bytes()
    loads = segments(data)
    if len(loads) < 2:
        raise SystemExit("the executable has no data segment")

    ranges = data_ranges(data)
    layout = read_layout(args.layout)
    if not layout:
        raise SystemExit(f"no reviewed layout in {args.layout}")

    args.out.mkdir(parents=True, exist_ok=True)
    path = args.out / "function_strings.tsv"
    named = 0
    rows = 0
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle, delimiter="\t", lineterminator="\n")
        writer.writerow(["start", "end", "string_address", "string"])
        for start, end in layout:
            found = []
            for address in addresses_of(data, start, end, loads):
                text = string_at(data, loads, address, ranges)
                if text is None:
                    continue
                found.append((address, text))
            if found:
                named += 1
            for address, text in found:
                writer.writerow([f"0x{start:08X}", f"0x{end:08X}",
                                 f"0x{address:08X}", text])
                rows += 1

    print(f"functions      : {len(layout)}")
    print(f"with a string  : {named}")
    print(f"references     : {rows}")
    print(f"catalogue      : {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
