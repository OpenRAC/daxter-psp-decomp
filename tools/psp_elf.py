#!/usr/bin/env python3
"""Read the structure of an Allegrex (PSP) ELF executable, and list its functions.

The tool reports structure only: the program headers, the sections, the entry
point, and the linked function symbols with their address and compiled size.
It never prints executable bytes, so its output can be published as research
metadata.

The reader accepts the two shapes a PSP executable comes in:

* a plain ELF (``\\x7fELF``), which is what a decrypted ``~PSP`` payload is;
* a ``~PSP`` encrypted wrapper, which is refused here with the pointer to
  the decryption step.

Usage:
    python3 tools/psp_elf.py <executable> [--json]
    python3 tools/psp_elf.py <executable> --functions [--tsv]
"""

from __future__ import annotations

import argparse
import hashlib
import json
import struct
from pathlib import Path

ELF_HEADER = struct.Struct("<HHIIIIIHHHHHH")
PROGRAM_HEADER = struct.Struct("<IIIIIIII")
SECTION_HEADER = struct.Struct("<IIIIIIIIII")
ELF_SYMBOL = struct.Struct("<IIIBBH")

ET_EXEC = 2
ET_DYN = 3
#: The type the PSP SDK gives to a PRX. The PSP loader does not care about
#: the ELF type, so a retail PRX does not claim to be an executable.
ET_SCE_PSP = 0xFFA0
EM_MIPS = 8
SHT_SYMTAB = 2
SHT_STRTAB = 3
SHT_NOBITS = 8
STT_FUNC = 2
PT_LOAD = 1

ELF_TYPES = {ET_EXEC: "EXEC", ET_DYN: "DYN", ET_SCE_PSP: "PSP-PRX"}


class ElfError(ValueError):
    """Raised when a file is not a usable PSP executable."""


def _headers(data: bytes):
    if len(data) < 52 or data[:6] != b"\x7fELF\x01\x01":
        raise ElfError("not a 32-bit little-endian ELF")
    (kind, machine, version, entry, phoff, shoff, flags, ehsize, phentsize,
     phnum, shentsize, shnum, shstrndx) = ELF_HEADER.unpack_from(data, 16)
    if machine != EM_MIPS:
        raise ElfError("not a MIPS executable")
    if kind not in ELF_TYPES:
        raise ElfError(f"not an executable, a shared object or a PSP PRX "
                       f"(type 0x{kind:04X})")
    if version != 1 or ehsize != 52:
        raise ElfError("unexpected ELF header version")
    if phnum and (phentsize != PROGRAM_HEADER.size or
                  phoff + phnum * phentsize > len(data)):
        raise ElfError("invalid ELF program-header table")
    if shnum and (shentsize != SECTION_HEADER.size or
                  shoff + shnum * shentsize > len(data)):
        raise ElfError("invalid ELF section-header table")
    programs = [PROGRAM_HEADER.unpack_from(data, phoff + index * phentsize)
                for index in range(phnum)]
    sections = [SECTION_HEADER.unpack_from(data, shoff + index * shentsize)
                for index in range(shnum)]
    return {
        "type": kind, "machine": machine, "version": version, "entry": entry,
        "flags": flags, "phnum": phnum, "shnum": shnum, "shstrndx": shstrndx,
    }, programs, sections


def _section_names(data: bytes, sections, shstrndx: int) -> list[str]:
    if shstrndx >= len(sections):
        return []
    _name, _type, _flags, _addr, offset, size, _link, _info, _align, _entsize = sections[shstrndx]
    blob = data[offset:offset + size]
    names = []
    for chunk in blob.split(b"\x00"):
        names.append(chunk.decode("utf-8", "replace"))
    return names


def inspect(path: Path) -> dict[str, object]:
    """Return the structure of a PSP ELF: programs, sections, entry, hashes."""
    data = Path(path).read_bytes()
    if data[:4] == b"~PSP":
        raise ElfError(
            "this is a ~PSP encrypted executable; decrypt it first "
            "(see docs/FORMATS.md)")
    header, programs, sections = _headers(data)
    names = _section_names(data, sections, header["shstrndx"])

    program_report = []
    for index, (ptype, offset, vaddr, paddr, file_size, mem_size, pflags,
                align) in enumerate(programs):
        if offset + file_size > len(data) or file_size > mem_size:
            raise ElfError(f"invalid ELF program header {index}")
        program_report.append({
            "index": index,
            "type": ptype,
            "file_offset": offset,
            "virtual_address": f"0x{vaddr:08X}",
            "physical_address": f"0x{paddr:08X}",
            "file_size": file_size,
            "memory_size": mem_size,
            "flags": pflags,
            "align": align,
        })

    section_report = []
    for index, section in enumerate(sections):
        (name_offset, stype, sflags, saddr, offset, size, link, info,
         align, entsize) = section
        section_report.append({
            "index": index,
            "name": names[name_offset] if name_offset < len(names) else "",
            "type": stype,
            "flags": sflags,
            "virtual_address": f"0x{saddr:08X}",
            "file_offset": offset,
            "size": size,
            "link": link,
            "info": info,
            "align": align,
            "entry_size": entsize,
        })

    return {
        "path": str(path),
        "size": len(data),
        "sha256": hashlib.sha256(data).hexdigest(),
        "sha1": hashlib.sha1(data).hexdigest(),
        "type": ELF_TYPES.get(header["type"], f"0x{header['type']:04X}"),
        "entry_point": f"0x{header['entry']:08X}",
        "flags": f"0x{header['flags']:08X}",
        "has_section_headers": bool(header["shnum"]),
        "programs": program_report,
        "sections": section_report,
    }


def functions(path: Path) -> list[dict[str, object]]:
    """Return the linked function symbols of a PSP ELF.

    Only the symbols that carry a size are reported: a function symbol
    without a size marks a label, not a function body.
    """
    data = Path(path).read_bytes()
    if data[:4] == b"~PSP":
        raise ElfError(
            "this is a ~PSP encrypted executable; decrypt it first "
            "(see docs/FORMATS.md)")
    header, _programs, sections = _headers(data)

    symbols: list[dict[str, object]] = []
    for section in sections:
        (name_offset, stype, _flags, _addr, offset, size, link, _info,
         _align, entsize) = section
        if stype != SHT_SYMTAB or not size:
            continue
        if link >= len(sections):
            continue
        str_section = sections[link]
        str_offset = str_section[4]
        str_size = str_section[5]
        strtab = data[str_offset:str_offset + str_size]
        entry_size = entsize or ELF_SYMBOL.size
        for index in range(size // entry_size):
            base = offset + index * entry_size
            st_name, st_value, st_size, st_info, _st_other, st_shndx = \
                ELF_SYMBOL.unpack_from(data, base)
            if (st_info & 0xF) != STT_FUNC or not st_size:
                continue
            end = strtab.find(b"\x00", st_name)
            name = strtab[st_name:end if end >= 0 else st_name].decode("utf-8", "replace")
            symbols.append({
                "name": name,
                "address": f"0x{st_value:08X}",
                "size": st_size,
                "section": st_shndx,
            })
    symbols.sort(key=lambda item: int(str(item["address"]), 16))
    return symbols


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("path", type=Path)
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--functions", action="store_true")
    parser.add_argument("--tsv", action="store_true")
    args = parser.parse_args(argv)

    if args.functions:
        rows = functions(args.path)
        if args.tsv:
            print("name\taddress\tsize")
            for row in rows:
                print(f"{row['name']}\t{row['address']}\t{row['size']}")
        elif args.json:
            print(json.dumps(rows, indent=2))
        else:
            for row in rows:
                print(f"{row['address']}  {row['size']:>8}  {row['name']}")
        return 0

    report = inspect(args.path)
    if args.json:
        print(json.dumps(report, indent=2))
        return 0
    print(f"{report['path']}")
    print(f"  size    : {report['size']}")
    print(f"  sha256  : {report['sha256']}")
    print(f"  entry   : {report['entry_point']}")
    print("  programs:")
    for program in report["programs"]:
        print(f"    [{program['index']}] type={program['type']} "
              f"vaddr={program['virtual_address']} "
              f"filesz={program['file_size']} memsz={program['memory_size']} "
              f"flags={program['flags']}")
    print("  sections:")
    for section in report["sections"]:
        print(f"    [{section['index']:>2}] {section['name']:<20} "
              f"type={section['type']} addr={section['virtual_address']} "
              f"size={section['size']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
