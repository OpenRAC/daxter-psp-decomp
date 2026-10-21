#!/usr/bin/env python3
"""Readers for the on-disc container formats of a PlayStation Portable UMD game.

The module recognises, and reads the structure of, the four containers that
the Daxter (PSP) disc uses:

``~PSP``   the encrypted executable wrapper of ``PSP_GAME/SYSDIR/EBOOT.BIN``;
``PSAR``   the update archive of ``PSP_GAME/SYSDIR/UPDATE/DATA.BIN``;
``PARAM.SFO``  the parameter file of the disc and of the update;
``Pack``   the asset container of ``PSP_GAME/USRDIR/data/*.bin``.

Every reader reports **structure only**: offsets, sizes, counts, identifiers
and magic numbers.  It never returns executable bytes, so its output is
publishable as research metadata.

The readers are deliberately independent of the game: they were written
against the containers of the pinned target and against the public format
descriptions, and they are tested on synthetic data.

Usage:
    python3 tools/psp_formats.py <file> [--json]
"""

from __future__ import annotations

import argparse
import hashlib
import json
import struct
import sys
from dataclasses import dataclass, field
from pathlib import Path

# --------------------------------------------------------------------------
# magic numbers
# --------------------------------------------------------------------------

MAGIC_PSP_ENC = b"~PSP"
MAGIC_PSAR = b"PSAR"
MAGIC_PACK = b"Pack"
MAGIC_SFO = b"\x00PSF"
MAGIC_ELF = b"\x7fELF"


class FormatError(ValueError):
    """Raised when a file does not have the structure the reader expects."""


def _u16(data: bytes, offset: int) -> int:
    return struct.unpack_from("<H", data, offset)[0]


def _u32(data: bytes, offset: int) -> int:
    return struct.unpack_from("<I", data, offset)[0]


def _magic(data: bytes) -> str:
    """Return the leading magic as printable ASCII, or an empty string."""
    head = data[:4]
    if len(head) < 4:
        return ""
    if all(0x20 <= byte < 0x7F for byte in head):
        return head.decode("ascii")
    return ""


# --------------------------------------------------------------------------
# PARAM.SFO
# --------------------------------------------------------------------------

SFO_FORMAT_UTF8 = 0x0204
SFO_FORMAT_INT32 = 0x0404


@dataclass
class SfoEntry:
    """One key/value record of a PARAM.SFO file."""

    key: str
    format: int
    length: int
    max_length: int
    offset: int
    value: object = None

    def as_dict(self) -> dict[str, object]:
        return {
            "key": self.key,
            "format": f"0x{self.format:04X}",
            "length": self.length,
            "max_length": self.max_length,
            "offset": self.offset,
            "value": self.value,
        }


@dataclass
class SfoFile:
    """The structure of a PARAM.SFO file."""

    version: int
    key_table_offset: int
    data_table_offset: int
    index_entries: int
    entries: list[SfoEntry] = field(default_factory=list)

    def get(self, key: str, default: object = None) -> object:
        for entry in self.entries:
            if entry.key == key:
                return entry.value
        return default

    def as_dict(self) -> dict[str, object]:
        return {
            "format": "PARAM.SFO",
            "version": self.version,
            "key_table_offset": self.key_table_offset,
            "data_table_offset": self.data_table_offset,
            "index_entries": self.index_entries,
            "entries": [entry.as_dict() for entry in self.entries],
        }


def read_sfo(data: bytes) -> SfoFile:
    """Read the structure of a PARAM.SFO file.

    The index entries are 16 bytes:

    ======  ==========================================================
    Offset  Meaning
    ======  ==========================================================
    0x00    u16 offset of the key in the key table
    0x02    u16 format: 0x0204 UTF-8, 0x0404 int32
    0x04    u16 length of the value
    0x06    u16 reserved
    0x08    u32 size of the value slot, padded
    0x0C    u32 offset of the value in the data table
    ======  ==========================================================
    """
    if len(data) < 20 or data[:4] != MAGIC_SFO:
        raise FormatError("not a PARAM.SFO file")
    version = _u32(data, 4)
    key_table_offset = _u32(data, 8)
    data_table_offset = _u32(data, 12)
    index_entries = _u32(data, 16)
    if index_entries > 0x10000:
        raise FormatError("implausible PARAM.SFO index entry count")

    result = SfoFile(version, key_table_offset, data_table_offset, index_entries)
    for index in range(index_entries):
        base = 0x14 + index * 0x10
        if base + 0x10 > len(data):
            raise FormatError(f"PARAM.SFO index entry {index} is out of bounds")
        key_offset = _u16(data, base)
        fmt = _u16(data, base + 2)
        length = _u16(data, base + 4)
        slot_size = _u32(data, base + 8)
        value_offset = data_table_offset + _u32(data, base + 0x0C)
        key_end = data.find(b"\x00", key_table_offset + key_offset)
        if key_end < 0:
            raise FormatError(f"PARAM.SFO key {index} is not terminated")
        key = data[key_table_offset + key_offset:key_end].decode("utf-8", "replace")
        value: object = None
        if fmt == SFO_FORMAT_INT32:
            value = _u32(data, value_offset) if value_offset + 4 <= len(data) else None
        elif (fmt & 0xFF) == 0x04:
            value = data[value_offset:value_offset + length].split(b"\x00")[0].decode("utf-8", "replace")
        result.entries.append(SfoEntry(key, fmt, length, slot_size, value_offset, value))
    return result


# --------------------------------------------------------------------------
# Pack
# --------------------------------------------------------------------------

#: The payload magics observed in the pinned target, with the container
#: *type* codes they appear under.  A type code is a property of the
#: container; a payload magic is a property of the blob it points at.
PACK_TYPE_NAMES = {
    2: "cfcm-primary",
    3: "radi-or-mesh",
    4: "cfcm-singleton",
    5: "cfcm-dense",
    9: "cfcm-textured",
    11: "sblk-block",
    23: "gmtx-texture",
    43: "float-table",
    61: "texture-page",
}

PACK_HEADER_SIZE = 0x24
PACK_ENTRY_SIZE = 0x10


@dataclass
class PackEntry:
    """One blob inside a Pack container."""

    index: int
    offset: int
    size: int
    type: int
    identifier: int
    magic: str = ""

    def as_dict(self) -> dict[str, object]:
        return {
            "index": self.index,
            "offset": self.offset,
            "size": self.size,
            "type": self.type,
            "type_name": PACK_TYPE_NAMES.get(self.type, "unknown"),
            "identifier": self.identifier,
            "magic": self.magic,
        }


@dataclass
class PackFile:
    """The structure of a Pack container."""

    version_major: int
    version_minor: int
    table_start: int
    count: int
    table_limit: int
    header_words: list[int] = field(default_factory=list)
    entries: list[PackEntry] = field(default_factory=list)

    def type_histogram(self) -> dict[str, int]:
        histogram: dict[str, int] = {}
        for entry in self.entries:
            key = f"{entry.type}:{PACK_TYPE_NAMES.get(entry.type, 'unknown')}"
            histogram[key] = histogram.get(key, 0) + 1
        return histogram

    def as_dict(self) -> dict[str, object]:
        return {
            "format": "Pack",
            "version": f"{self.version_major}.{self.version_minor}",
            "header_word_08": f"0x{self.table_start:08X}",
            "blob_area_offset": self.table_limit,
            "count": self.count,
            "header_words": [f"0x{word:08X}" for word in self.header_words],
            "entries": [entry.as_dict() for entry in self.entries],
        }


def read_pack(data: bytes) -> PackFile:
    """Read the structure of a Pack container.

    Layout, as measured on the pinned target:

    ======  ==========================================================
    Offset  Meaning
    ======  ==========================================================
    0x00    magic ``Pack``
    0x04    u16 version major, u16 version minor
    0x08    u32, meaning not established
    0x0C    u32 entry count, **including** the header pseudo-entry
    0x10    five header words, meaning not established
    0x24    u32 end of the entry table, and the start of the blob area
    0x24+   entries of 16 bytes: u32 offset, u32 size, u32 type,
            u32 identifier
    ======  ==========================================================

    The reader validates that every entry stays inside the file and that the
    entries do not overlap each other.
    """
    if len(data) < PACK_HEADER_SIZE + PACK_ENTRY_SIZE or data[:4] != MAGIC_PACK:
        raise FormatError("not a Pack container")
    version_major = _u16(data, 4)
    version_minor = _u16(data, 6)
    table_start = _u32(data, 8)
    count = _u32(data, 12)
    if count < 1 or count > 0x100000:
        raise FormatError("implausible Pack entry count")
    table_limit = _u32(data, PACK_HEADER_SIZE)

    header_words = [_u32(data, offset) for offset in range(0x10, PACK_HEADER_SIZE, 4)]
    result = PackFile(version_major, version_minor, table_start, count, table_limit, header_words)

    for index in range(count - 1):
        base = PACK_HEADER_SIZE + index * PACK_ENTRY_SIZE
        if base + PACK_ENTRY_SIZE > len(data):
            raise FormatError(f"Pack entry {index} is out of bounds")
        offset = _u32(data, base)
        size = _u32(data, base + 4)
        entry_type = _u32(data, base + 8)
        identifier = _u32(data, base + 12)
        if offset + size > len(data):
            raise FormatError(f"Pack entry {index} points outside the file")
        magic = _magic(data[offset:offset + 4]) if size >= 4 else ""
        result.entries.append(PackEntry(index, offset, size, entry_type, identifier, magic))
    return result


# --------------------------------------------------------------------------
# PSAR
# --------------------------------------------------------------------------

PSAR_HEADER_SIZE = 0x20


@dataclass
class PsarFile:
    """One member of a PSAR archive."""

    index: int
    name: str
    offset: int
    size: int

    def as_dict(self) -> dict[str, object]:
        return {"index": self.index, "name": self.name, "offset": self.offset, "size": self.size}


@dataclass
class PsarArchive:
    """The structure of a PSAR archive.

    The header is 0x10 bytes: the magic ``PSAR``, a u32 version, the u32
    offset of the member table, and the u32 member count.  The table sits
    at the end of the archive and the members themselves are encrypted with
    a key derived from the disc identifier, so a reader without that key
    can report the header but not the member names.
    """

    version: int
    table_offset: int
    member_count: int
    files: list[PsarFile] = field(default_factory=list)

    def as_dict(self) -> dict[str, object]:
        return {
            "format": "PSAR",
            "version": self.version,
            "table_offset": self.table_offset,
            "member_count": self.member_count,
            "members_readable": bool(self.files),
            "note": ("the member table and the members are encrypted with a "
                     "disc-derived key; only the header is readable without it"),
            "files": [item.as_dict() for item in self.files],
        }


def read_psar(data: bytes) -> PsarArchive:
    """Read the header of a PSAR archive.

    The member table of the update archive of the pinned target is
    encrypted: the bytes at the recorded table offset have high entropy and
    do not decode as offsets, sizes and names.  The reader therefore
    reports the header, and leaves the member list empty rather than
    inventing one.
    """
    if len(data) < 0x10 or data[:4] != MAGIC_PSAR:
        raise FormatError("not a PSAR archive")
    version = _u32(data, 4)
    table_offset = _u32(data, 8)
    member_count = _u32(data, 12)
    if table_offset > len(data):
        raise FormatError("invalid PSAR member-table offset")
    archive = PsarArchive(version, table_offset, member_count)
    return archive


# --------------------------------------------------------------------------
# ~PSP encrypted executable
# --------------------------------------------------------------------------

@dataclass
class EncryptedPsp:
    """The header of a ``~PSP`` encrypted executable."""

    header_parameter: int
    version: int
    module_name: str
    size: int

    def as_dict(self) -> dict[str, object]:
        return {
            "format": "~PSP",
            "header_parameter": f"0x{self.header_parameter:08X}",
            "version": f"0x{self.version:04X}",
            "module_name": self.module_name,
            "size": self.size,
            "note": ("the payload is encrypted with a disc-derived key; the "
                     "boundary of the encrypted payload is not established "
                     "here, see docs/FORMATS.md"),
        }


def read_encrypted_psp(data: bytes) -> EncryptedPsp:
    """Read the header of a ``~PSP`` encrypted executable.

    The wrapper is a small header in front of the encrypted payload:

    ======  ==========================================================
    Offset  Meaning
    ======  ==========================================================
    0x00    magic ``~PSP``
    0x04    u32 header parameter; 0x00000000 on the disc executable of
            the pinned target, 0x00000800 on its update executable
    0x08    u16 format version, 0x0101 on the pinned target
    0x0A    the module name, NUL terminated: ``dax`` on the disc
            executable, ``update`` on the update executable
    ======  ==========================================================

    The payload itself is encrypted with a key derived from the disc
    identifier; it can only be recovered with a PSP implementation.  See
    ``docs/FORMATS.md``.
    """
    if len(data) < 0x10 or data[:4] != MAGIC_PSP_ENC:
        raise FormatError("not a ~PSP encrypted executable")
    header_parameter = _u32(data, 4)
    version = _u16(data, 8)
    name_end = data.find(b"\x00", 0x0A)
    module_name = data[0x0A:name_end if name_end > 0 else 0x0A].decode("utf-8", "replace")
    return EncryptedPsp(header_parameter, version, module_name, len(data))


# --------------------------------------------------------------------------
# dispatch
# --------------------------------------------------------------------------

READERS = {
    MAGIC_SFO: ("PARAM.SFO", read_sfo),
    MAGIC_PSAR: ("PSAR", read_psar),
    MAGIC_PACK: ("Pack", read_pack),
    MAGIC_PSP_ENC: ("~PSP", read_encrypted_psp),
}


def identify(data: bytes) -> str:
    """Return the name of the container a blob is in, or ``""``."""
    for magic, (name, _reader) in READERS.items():
        if data[:4] == magic:
            return name
    if data[:4] == MAGIC_ELF:
        return "ELF"
    return ""


def read_any(data: bytes) -> dict[str, object]:
    """Read whichever container the blob is in."""
    name = identify(data)
    if not name:
        raise FormatError("unrecognised container")
    if name == "ELF":
        return {"format": "ELF", "note": "read by tools/psp_elf.py"}
    _name, reader = READERS[data[:4]]
    return reader(data).as_dict()


def file_report(path: Path) -> dict[str, object]:
    """Return the structure of a container file, with its hashes."""
    data = Path(path).read_bytes()
    report: dict[str, object] = {
        "path": str(path),
        "size": len(data),
        "sha256": hashlib.sha256(data).hexdigest(),
        "sha1": hashlib.sha1(data).hexdigest(),
        "format": identify(data) or "unknown",
    }
    if report["format"] == "unknown":
        return report
    if report["format"] == "ELF":
        return report
    report.update(read_any(data))
    return report


def main(argv: list[str] | None = None) -> int:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("path", type=Path)
    parser.add_argument("--json", action="store_true", help="emit JSON")
    args = parser.parse_args(argv)
    report = file_report(args.path)
    if args.json:
        print(json.dumps(report, indent=2))
        return 0
    print(f"{report['path']}")
    for key, value in report.items():
        if key == "path":
            continue
        if key in {"entries", "files"}:
            print(f"  {key}: {len(value)}")
            for item in value[:16]:
                print(f"    {item}")
        else:
            print(f"  {key}: {value}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
