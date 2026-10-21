#!/usr/bin/env python3
"""Decrypt a ``~PSP`` executable into the Allegrex ELF it carries.

A PSP executable that ships on a UMD disc is stored in a ``~PSP`` container:
a ``PSP_Header`` whose fields the PSP firmware uses to find and unlock the
payload, followed by the encrypted program.  The tool reproduces that
unlocking, and writes the ELF it recovers.

The tool is this project's own implementation, written from the published
description of the format; the key material it uses lives in
``tools/psp_crypto.py``.  See ``docs/FORMATS.md`` for the container, and
``THIRD_PARTY_NOTICES.md`` for the provenance of the keys.

**The decrypted executable is never committed.**  What the repository
publishes is the *structure* the ELF yields, read by ``tools/psp_elf.py``.

Usage:
    python3 tools/decrypt_psp.py <encrypted> <output.elf> [--json]
"""

from __future__ import annotations

import argparse
import hashlib
import json
import struct
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import psp_crypto as crypto  # noqa: E402

PSP_HEADER_SIZE = 0x150
KIRK_CMD1_HEADER_SIZE = 0x90

#: The offsets of the fields of the ``PSP_Header`` the decrypter reads.
OFF_TAG = 0xD0
OFF_COMP_SIZE = 0xB0
OFF_KEY_DATA0 = 0x80
OFF_KEY_DATA1 = 0x110
OFF_SCHECK = 0xD4


class DecryptError(ValueError):
    """Raised when a container cannot be decrypted."""


def _u16(data: bytes, offset: int) -> int:
    return struct.unpack_from("<H", data, offset)[0]


def _u32(data: bytes, offset: int) -> int:
    return struct.unpack_from("<I", data, offset)[0]


def _xor(left: bytes, right: bytes) -> bytes:
    return bytes(a ^ b for a, b in zip(left, right))


def _expand_seed(seed: bytes, key_slot: int) -> bytes:
    """Expand a 144-byte tag seed into the 144-byte xor buffer.

    Each 16-byte block of the seed is copied, with its first byte replaced
    by the block index; the whole thing is then decrypted with the key of
    the slot, which is what the PSP does to turn a stored seed into a
    per-module xor buffer.
    """
    expanded = bytearray()
    for index in range(9):
        block = bytearray(seed[index * 0x10:index * 0x10 + 0x10])
        block[0] = index
        expanded += block
    return crypto.kirk7(key_slot, bytes(expanded))


def _decrypt_kirk_header_type0(header: bytes, source: bytes,
                                xorbuf: bytes, key_slot: int) -> bytes:
    """Unlock the 0x70-byte KIRK command 1 header of a type 0 PRX."""
    out = bytearray(header)
    for index in range(0x70):
        out[index] = source[index] ^ xorbuf[index + 0x14]
    out[0:0x70] = crypto.kirk7(key_slot, bytes(out[0:0x70]))
    for index in range(0x70):
        out[index] ^= xorbuf[index + 0x20]
    return bytes(out)


def _decrypt_kirk_header(header: bytes, source: bytes, xorbuf: bytes,
                         key_slot: int) -> bytes:
    """Unlock the 0x40-byte KIRK command 1 header of a type 2/5/6/9 PRX."""
    out = bytearray(header)
    for index in range(0x40):
        out[index] = source[index] ^ xorbuf[index]
    out[0:0x40] = crypto.kirk7(key_slot, bytes(out[0:0x40]))
    for index in range(0x40):
        out[index] ^= xorbuf[index]
    return bytes(out)


def _kirk_cmd1(buffer: bytes, offset: int) -> bytes:
    """Run the KIRK command 1 over a prepared buffer, and return the payload.

    The command operates on the buffer from ``offset`` onwards: the KIRK
    header sits at its start, and the encrypted program follows it.  The
    header carries the per-module AES and CMAC keys, wrapped by the KIRK1
    key.  The command unwraps them, checks the CMAC hashes over the header
    and over the payload, and decrypts the payload with the per-module AES
    key.

    The two CMAC hashes are what tell a correct decryption from a wrong
    one, so they are checked rather than assumed.
    """
    inbuf = buffer[offset:]
    if len(inbuf) < KIRK_CMD1_HEADER_SIZE:
        raise DecryptError("the KIRK header is too small")
    mode = _u32(inbuf, 0x60)
    if mode != 1:
        raise DecryptError(f"unexpected KIRK header mode: {mode}")

    keys = crypto.aes_cbc_decrypt(crypto.KIRK1_KEY, inbuf[0:32])
    aes_key = keys[0:16]
    cmac_key = keys[16:32]

    data_size = _u32(inbuf, 0x70)
    data_offset = _u32(inbuf, 0x74)
    if data_size == 0:
        raise DecryptError("the KIRK header declares no data")
    if KIRK_CMD1_HEADER_SIZE + data_offset + data_size > len(inbuf):
        raise DecryptError("the KIRK header points outside the buffer")

    checked_size = data_size + (16 - data_size % 16) % 16
    header_hash = crypto.aes_cmac(cmac_key, inbuf[0x60:0x60 + 0x30])
    if header_hash != inbuf[0x20:0x30]:
        raise DecryptError("the KIRK header hash does not match")
    data_hash = crypto.aes_cmac(cmac_key, inbuf[0x60:0x60 + 0x30 + checked_size + data_offset])
    if data_hash != inbuf[0x30:0x40]:
        raise DecryptError("the KIRK data hash does not match")

    payload = inbuf[KIRK_CMD1_HEADER_SIZE + data_offset:
                     KIRK_CMD1_HEADER_SIZE + data_offset + checked_size]
    plain = crypto.aes_cbc_decrypt(aes_key, payload)
    return plain[:data_size]


def _prepare_output(data: bytes, kirk_block: bytes, prx_header: bytes,
                    xorbuf: bytes, key_slot: int) -> tuple[bytes, int]:
    """Build the buffer the KIRK command 1 runs on, and return its offset.

    The command runs on the whole container, with the KIRK header written
    over the first 0x110 bytes of the region it starts at.  The bytes that
    follow the header in that region are the encrypted program, and the
    CMAC of the payload covers them, so the buffer has to be complete
    before the command runs.
    """
    offset = PSP_HEADER_SIZE - KIRK_CMD1_HEADER_SIZE - len(prx_header)
    out = bytearray(data)
    header = bytearray(kirk_block + prx_header)
    header = bytearray(_decrypt_kirk_header_type0(
        bytes(header), kirk_block, xorbuf, key_slot))
    out[offset:offset + len(header)] = header
    return bytes(out), offset


def _type0_parts(data: bytes) -> dict[str, bytes]:
    """Split a type 0 PRX into the parts its hash covers."""
    return {
        "sha1": data[OFF_SCHECK:OFF_SCHECK + 0x14],
        "unused": data[0xE8:0xE8 + 0x28],
        # The kirk block is split in the file: 0x40 bytes at 0x110, and the
        # 0x50 bytes at 0x80.
        "kirk_block": data[OFF_KEY_DATA1:OFF_KEY_DATA1 + 0x40] +
                      data[OFF_KEY_DATA0:OFF_KEY_DATA0 + 0x50],
        "prx_header": data[0x00:0x80],
    }


def decrypt_type0(data: bytes) -> bytes | None:
    """Decrypt a type 0 PRX. Returns ``None`` when the hash does not match."""
    tag = _u32(data, OFF_TAG)
    if tag not in crypto.TAG_KEYS:
        return None
    seed, key_slot, scramble = crypto.TAG_KEYS[tag]

    xorbuf = bytearray(seed)
    if scramble:
        xorbuf = bytearray(crypto.kirk7(key_slot, bytes(xorbuf)))

    parts = _type0_parts(data)
    digest = hashlib.sha1()
    digest.update(bytes(xorbuf[0:0x14]))
    digest.update(parts["unused"])
    digest.update(parts["kirk_block"])
    digest.update(parts["prx_header"])
    if digest.digest() != parts["sha1"]:
        return None

    out, offset = _prepare_output(data, parts["kirk_block"], parts["prx_header"],
                                  xorbuf, key_slot)
    return _kirk_cmd1(out, offset)


def decrypt_type1(data: bytes) -> bytes | None:
    """Decrypt a type 1 PRX. Returns ``None`` when the hash does not match.

    A type 1 PRX differs from a type 0 one in that its sha1, its unused
    block and the first 0x70 bytes of its kirk block are encrypted as one
    run, over the *rearranged* header: the sha1 and the unused block are
    adjacent in the file but are not adjacent in the rearranged one, so the
    0xA0 bytes that the kirk7 covers have to be assembled before they can
    be decrypted.
    """
    tag = _u32(data, OFF_TAG)
    if tag not in crypto.TAG_KEYS:
        return None
    seed, key_slot, _scramble = crypto.TAG_KEYS[tag]

    # The rearranged header: sha1, unused, kirk block, PRX header.
    rearranged = bytearray(
        data[OFF_SCHECK:OFF_SCHECK + 0x14] +
        data[0xE8:0xE8 + 0x28] +
        data[OFF_KEY_DATA1:OFF_KEY_DATA1 + 0x40] +
        data[OFF_KEY_DATA0:OFF_KEY_DATA0 + 0x50] +
        data[0x00:0x80])

    # The kirk7 covers 0xA0 bytes from the 0x0C of the sha1.
    rearranged[0x0C:0x0C + 0xA0] = crypto.kirk7(
        key_slot, bytes(rearranged[0x0C:0x0C + 0xA0]))

    sha1 = bytes(rearranged[0x00:0x14])
    unused = bytes(rearranged[0x14:0x3C])
    kirk_block = bytes(rearranged[0x3C:0xCC])
    prx_header = bytes(rearranged[0xCC:0x14C])

    xorbuf = seed
    digest = hashlib.sha1()
    digest.update(xorbuf[0:0x14])
    digest.update(unused)
    digest.update(kirk_block)
    digest.update(prx_header)
    if digest.digest() != sha1:
        return None

    out, offset = _prepare_output(data, kirk_block, prx_header, xorbuf, key_slot)
    return _kirk_cmd1(out, offset)


def decrypt_prx(data: bytes) -> tuple[bytes, str]:
    """Decrypt a ``~PSP`` container, and return the ELF and the type used."""
    if len(data) < PSP_HEADER_SIZE:
        raise DecryptError("the container is too small")
    if data[:4] != b"~PSP":
        raise DecryptError("not a ~PSP container")

    tag = _u32(data, OFF_TAG)
    for name, decrypter in (("type0", decrypt_type0), ("type1", decrypt_type1)):
        result = decrypter(data)
        if result is not None:
            return result, name
    raise DecryptError(
        f"no decryption matched: tag 0x{tag:08X} is not in the tag table")


def main(argv: list[str] | None = None) -> int:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("source", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)

    data = args.source.read_bytes()
    elf, kind = decrypt_prx(data)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_bytes(elf)

    report = {
        "source": str(args.source),
        "output": str(args.output),
        "container": "~PSP",
        "module_name": data[0x0A:0x0A + 28].split(b"\x00")[0].decode("utf-8", "replace"),
        "tag": f"0x{_u32(data, OFF_TAG):08X}",
        "decrypt_mode": _u32(data, 0x7C),
        "prx_type": kind,
        "encrypted_size": len(data),
        "elf_size": len(elf),
        "elf_sha1": hashlib.sha1(elf).hexdigest(),
        "elf_sha256": hashlib.sha256(elf).hexdigest(),
    }
    if args.json:
        print(json.dumps(report, indent=2))
    else:
        for key, value in report.items():
            print(f"  {key}: {value}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
