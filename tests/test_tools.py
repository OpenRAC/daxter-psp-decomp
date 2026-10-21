#!/usr/bin/env python3
"""Unit tests of the integration tools, on synthetic data only.

No game data, no disc image and no retail byte appears in this file.  Every
fixture is built here, byte by byte, from the documented format of each
file.

Run:
    python3 -m unittest discover -s tests
"""

from __future__ import annotations

import csv
import struct
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))

import disc_inventory  # noqa: E402
import decrypt_psp  # noqa: E402
import function_inventory  # noqa: E402
import harness  # noqa: E402
import merge_layout  # noqa: E402
import psp_crypto  # noqa: E402
import psp_elf  # noqa: E402
import psp_formats as fmt  # noqa: E402

LOT_HEADER = ["start", "end", "size", "class", "name", "name_evidence",
               "confidence"]
NAMES_HEADER = ["start", "name", "evidence", "confidence", "corrects"]


def build_sfo(entries: list[tuple[str, str]]) -> bytes:
    """Build a PARAM.SFO file with the given key/value pairs."""
    key_table = bytearray()
    data_table = bytearray()
    index = bytearray()
    for key, value in entries:
        key_offset = len(key_table)
        key_table += key.encode("ascii") + b"\x00"
        if value.lstrip("-").isdigit() and len(value) <= 9:
            data = struct.pack("<i", int(value))
            fmt_code = fmt.SFO_FORMAT_INT32
            length = 4
        else:
            data = value.encode("utf-8") + b"\x00"
            fmt_code = fmt.SFO_FORMAT_UTF8
            length = len(value) + 1
        slot = len(data)
        if slot % 4:
            slot += 4 - slot % 4
        value_offset = len(data_table)
        data_table += data + b"\x00" * (slot - len(data))
        index += struct.pack("<HHHHII", key_offset, fmt_code, length, 0,
                             slot, value_offset)
    header_size = 0x14
    key_table_offset = header_size + len(entries) * 0x10
    data_table_offset = key_table_offset + len(key_table)
    while (data_table_offset + len(data_table)) % 4:
        data_table += b"\x00"
    header = struct.pack("<4sIIII", fmt.MAGIC_SFO, 0x00000101,
                         key_table_offset, data_table_offset, len(entries))
    return bytes(header) + bytes(index) + bytes(key_table) + bytes(data_table)


def build_pack(entries: list[tuple[int, bytes, int, int]]) -> bytes:
    """Build a Pack container with the given (type, payload, id) entries."""
    count = len(entries) + 1
    table_start = 0x24 + len(entries) * 0x10
    table = bytearray()
    blobs = bytearray()
    for entry_type, payload, identifier in entries:
        offset = table_start + len(blobs)
        table += struct.pack("<IIII", offset, len(payload), entry_type, identifier)
        blobs += payload
    header = bytearray(b"Pack")
    header += struct.pack("<HH", 3, 4)
    header += struct.pack("<II", table_start, count)
    header += struct.pack("<IIIII", 0, 0, 0, 0, 0)
    assert len(header) == 0x24
    return bytes(header) + bytes(table) + bytes(blobs)


def build_psar() -> bytes:
    return struct.pack("<4sIIII", fmt.MAGIC_PSAR, 3, 0x10, 1, 0) + b"\x00" * 16


def build_encrypted_psp(name: str, parameter: int = 0) -> bytes:
    body = name.encode("ascii") + b"\x00"
    return (fmt.MAGIC_PSP_ENC + struct.pack("<IH", parameter, 0x0101) +
            body + b"\x00" * 16)


def build_prx(code: bytes = b"") -> bytes:
    """Build a minimal Allegrex PRX: one program header, no sections."""
    header = bytearray(b"\x7fELF\x01\x01\x01\x00" + b"\x00" * 8)
    header += struct.pack("<HH", 0xFFA0, 8)
    header += struct.pack("<I", 1)
    header += struct.pack("<I", 0)
    header += struct.pack("<I", 52)
    header += struct.pack("<I", 0)
    header += struct.pack("<I", 0)
    header += struct.pack("<HHHHHH", 52, 32, 1, 0, 0, 0)
    program = struct.pack("<IIIIIIII", 1, 84, 0, 0, len(code), len(code), 5, 4)
    return bytes(header) + program + code


class SfoTests(unittest.TestCase):
    def test_reads_keys_and_values(self) -> None:
        blob = build_sfo([("TITLE", "Daxter"), ("DISC_NUMBER", "1")])
        sfo = fmt.read_sfo(blob)
        self.assertEqual(sfo.get("TITLE"), "Daxter")
        self.assertEqual(sfo.get("DISC_NUMBER"), 1)
        self.assertEqual(sfo.index_entries, 2)

    def test_rejects_a_foreign_file(self) -> None:
        with self.assertRaises(fmt.FormatError):
            fmt.read_sfo(b"not an sfo file at all, not even close!!")

    def test_padded_slots_are_honoured(self) -> None:
        blob = build_sfo([("A", "xy"), ("B", "z")])
        sfo = fmt.read_sfo(blob)
        self.assertEqual(sfo.get("A"), "xy")
        self.assertEqual(sfo.get("B"), "z")


class PackTests(unittest.TestCase):
    def test_reads_entries(self) -> None:
        blob = build_pack([(3, b"RADI" + b"\x00" * 12, 6),
                           (2, b"CfCm" + b"\x00" * 28, 7)])
        pack = fmt.read_pack(blob)
        self.assertEqual(pack.version_major, 3)
        self.assertEqual(pack.version_minor, 4)
        self.assertEqual(pack.count, 3)
        self.assertEqual(len(pack.entries), 2)
        self.assertEqual(pack.entries[0].magic, "RADI")
        self.assertEqual(pack.entries[1].magic, "CfCm")
        self.assertEqual(pack.entries[0].size, 16)

    def test_type_histogram(self) -> None:
        blob = build_pack([(3, b"RADI", 1), (3, b"RADI", 2), (2, b"CfCm", 3)])
        histogram = fmt.read_pack(blob).type_histogram()
        self.assertEqual(histogram["3:radi-or-mesh"], 2)
        self.assertEqual(histogram["2:cfcm-primary"], 1)

    def test_rejects_an_out_of_bounds_entry(self) -> None:
        blob = bytearray(build_pack([(3, b"RADI", 1)]))
        struct.pack_into("<I", blob, 0x24, 0xFFFFFF)
        with self.assertRaises(fmt.FormatError):
            fmt.read_pack(bytes(blob))

    def test_rejects_a_foreign_file(self) -> None:
        with self.assertRaises(fmt.FormatError):
            fmt.read_pack(b"Pack but truncated here")


class PsarTests(unittest.TestCase):
    def test_reads_the_header(self) -> None:
        archive = fmt.read_psar(build_psar())
        self.assertEqual(archive.version, 3)
        self.assertEqual(archive.member_count, 1)
        self.assertEqual(archive.files, [])

    def test_rejects_a_foreign_file(self) -> None:
        with self.assertRaises(fmt.FormatError):
            fmt.read_psar(b"PSAR but truncated here")


class EncryptedPspTests(unittest.TestCase):
    def test_reads_the_header(self) -> None:
        header = fmt.read_encrypted_psp(build_encrypted_psp("dax"))
        self.assertEqual(header.module_name, "dax")
        self.assertEqual(header.version, 0x0101)
        self.assertEqual(header.header_parameter, 0)

    def test_reads_the_update_header(self) -> None:
        header = fmt.read_encrypted_psp(build_encrypted_psp("update", 0x800))
        self.assertEqual(header.module_name, "update")
        self.assertEqual(header.header_parameter, 0x800)


class CryptoTests(unittest.TestCase):
    def test_aes_cmac_matches_rfc4493(self) -> None:
        key = bytes.fromhex("2b7e151628aed2a6abf7158809cf4f3c")
        vectors = [
            ("", "bb1d6929e95937287fa37d129b756746"),
            ("6bc1bee22e409f96e93d7e117393172a",
             "070a16b46b4d4144f79bdd9dd04a287c"),
            ("6bc1bee22e409f96e93d7e117393172aae2d8a571e03ac9c9eb76fac45af8e5"
             "130c81c46a35ce411",
             "dfa66747de9ae63030ca32611497c827"),
            ("6bc1bee22e409f96e93d7e117393172aae2d8a571e03ac9c9eb76fac45af8e5"
             "130c81c46a35ce411e5fbc1191a0a52eff69f2445df4f9b17ad2b417be66c3710",
             "51f0bebf7e3b9d92fc49741779363cfe"),
        ]
        for message, expected in vectors:
            self.assertEqual(psp_crypto.aes_cmac(key, bytes.fromhex(message)),
                             bytes.fromhex(expected))

    def test_the_key_vault_is_complete(self) -> None:
        self.assertEqual(len(psp_crypto.KEYVAULT), 128)
        for slot, key in enumerate(psp_crypto.KEYVAULT):
            self.assertEqual(len(key), 16, f"slot {slot}")

    def test_kirk7_refuses_an_unknown_slot(self) -> None:
        with self.assertRaises(ValueError):
            psp_crypto.kirk7(0x80, b"\x00" * 16)

    def test_aes_cbc_needs_whole_blocks(self) -> None:
        with self.assertRaises(ValueError):
            psp_crypto.aes_cbc_decrypt(b"\x00" * 16, b"\x00" * 17)


class DecryptTests(unittest.TestCase):
    def test_refuses_a_file_that_is_not_a_container(self) -> None:
        with self.assertRaises(decrypt_psp.DecryptError):
            decrypt_psp.decrypt_prx(b"not a ~PSP container at all, no")

    def test_refuses_a_truncated_container(self) -> None:
        with self.assertRaises(decrypt_psp.DecryptError):
            decrypt_psp.decrypt_prx(b"~PSP" + b"\x00" * 8)

    def test_reports_an_unknown_tag(self) -> None:
        blob = bytearray(build_encrypted_psp("dax").ljust(0x150, b"\x00"))
        struct.pack_into("<I", blob, 0xD0, 0xDEADBEEF)
        with self.assertRaises(decrypt_psp.DecryptError):
            decrypt_psp.decrypt_prx(bytes(blob))


class ElfTests(unittest.TestCase):
    def test_refuses_an_encrypted_executable(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "EBOOT.BIN"
            path.write_bytes(build_encrypted_psp("dax"))
            with self.assertRaises(psp_elf.ElfError):
                psp_elf.inspect(path)

    def test_refuses_a_foreign_file(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "junk.bin"
            path.write_bytes(b"junk" * 64)
            with self.assertRaises(psp_elf.ElfError):
                psp_elf.inspect(path)

    def test_accepts_the_psp_prx_type(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "prx.elf"
            path.write_bytes(build_prx())
            report = psp_elf.inspect(path)
            self.assertEqual(report["type"], "PSP-PRX")
            self.assertEqual(len(report["programs"]), 1)


class FunctionInventoryTests(unittest.TestCase):
    def test_finds_a_frame_opening(self) -> None:
        code = struct.pack("<I", 0x03E00008)          # jr $ra
        code += struct.pack("<I", 0x27BDFFE0)         # addiu $sp,$sp,-0x20
        code += struct.pack("<I", 0xAFBF001C)         # sw $ra,0x1C($sp)
        code += struct.pack("<I", 0x00000000)
        candidates = function_inventory.inventory(build_prx(code))
        self.assertEqual(len(candidates), 1)
        self.assertEqual(candidates[0]["frame"], 0x20)
        self.assertTrue(candidates[0]["saves_ra"])

    def test_ignores_a_frame_that_is_too_small(self) -> None:
        code = struct.pack("<I", 0x27BDFFF8)           # addiu $sp,$sp,-8
        candidates = function_inventory.inventory(build_prx(code))
        self.assertEqual(candidates, [])



def _read_layout(out: Path) -> list[dict[str, str]]:
    """Read the merged layout table of a synthetic wave."""
    with (out / "boot" / "layout.tsv").open(encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle, delimiter="\t"))

class MergeTests(unittest.TestCase):
    """The integration of the lots, on a synthetic wave."""

    def _make_wave(self, root: Path) -> Path:
        work = root / "work"
        (work / "E0").mkdir(parents=True)
        with (work / "E0" / "bounds.tsv").open("w", encoding="utf-8",
                                               newline="") as handle:
            writer = csv.writer(handle, delimiter="\t", lineterminator="\n")
            writer.writerow(["start", "end", "size", "bound_source", "evidence",
                             "calls", "returns"])
            writer.writerow(["0x00000100", "0x00000140", 64, "call", "call",
                             3, 1])
            writer.writerow(["0x00000200", "0x00000240", 64, "call", "call",
                             1, 1])
        (work / "L01").mkdir(parents=True)
        with (work / "L01" / "layout.tsv").open("w", encoding="utf-8",
                                                newline="") as handle:
            writer = csv.writer(handle, delimiter="\t", lineterminator="\n")
            writer.writerow(LOT_HEADER)
            writer.writerow(["0x00000100", "0x00000140", 64, "function",
                             "func_00000100", "-", "high"])
            writer.writerow(["0x00000200", "0x00000230", 48, "function",
                             "func_00000200", "-", "medium"])
        return work

    def test_merges_the_lots(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            work = self._make_wave(root)
            out = root / "config"
            summary = merge_layout.merge(work, out)
            self.assertEqual(summary["reviewed"], 2)
            self.assertEqual(summary["class_counts"]["function"], 2)
            self.assertEqual(summary["named"], 0)
            self.assertEqual(summary["sweep_checked"], 2)
            # the second body disagrees with the sweep
            self.assertEqual(summary["sweep_disagreements"], 1)
            rows = _read_layout(out)
            self.assertEqual(len(rows), 2)
            self.assertEqual(rows[1]["bound_agrees"], "no")

    def test_applies_the_naming_deliverable(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            work = self._make_wave(root)
            (work / "ASSERT").mkdir()
            with (work / "ASSERT" / "names.tsv").open("w", encoding="utf-8",
                                                      newline="") as handle:
                writer = csv.writer(handle, delimiter="\t", lineterminator="\n")
                writer.writerow(NAMES_HEADER)
                writer.writerow(["0x00000100", "CFile_Open", "assert $a3", "high",
                                 "-"])
            out = root / "config"
            summary = merge_layout.merge(work, out)
            self.assertEqual(summary["named"], 1)
            rows = _read_layout(out)
            self.assertEqual(rows[0]["name"], "CFile_Open")

    def test_records_a_correction(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            work = self._make_wave(root)
            (work / "NAMES").mkdir()
            with (work / "NAMES" / "names.tsv").open("w", encoding="utf-8",
                                                    newline="") as handle:
                writer = csv.writer(handle, delimiter="\t", lineterminator="\n")
                writer.writerow(NAMES_HEADER)
                writer.writerow(["0x00000100", "CFile_Open", "the string ~CFile",
                                 "high", "-"])
            (work / "L01" / "layout.tsv").write_text(
                "start\tend\tsize\tclass\tname\tname_evidence\tconfidence\n"
                "0x00000100\t0x00000140\t64\tfunction\tCFile_Close\t-\thigh\n",
                encoding="utf-8")
            out = root / "config"
            summary = merge_layout.merge(work, out)
            self.assertEqual(summary["name_corrections"], 1)
            rows = _read_layout(out)
            self.assertEqual(rows[0]["name"], "CFile_Open")
            self.assertIn("corrects CFile_Close", rows[0]["name_evidence"])


def build_object(text: bytes, name: str = "body") -> bytes:
    """Build a relocatable object with one function symbol.

    The layout is the minimum an ELF reader needs: a null section, a
    .text, a .symtab and a .strtab.
    """
    strtab = b"\x00" + name.encode("ascii") + b"\x00"
    shstrtab = b"\x00.text\x00.symtab\x00.strtab\x00"
    shstr_names = {".text": 1, ".symtab": 7, ".strtab": 13}

    header_size = 52
    text_offset = header_size
    symtab_offset = text_offset + len(text)
    # one null symbol, then the function.  In a relocatable object the
    # value of a symbol is the offset of the byte inside its section,
    # which here is the file offset of the text.
    symtab = struct.pack("<IIIBBH", 0, 0, 0, 0, 0, 0)
    symtab += struct.pack("<IIIBBH", 1, text_offset, len(text), 0x12, 0, 1)
    strtab_offset = symtab_offset + len(symtab)
    shstrtab_offset = strtab_offset + len(strtab)
    shoff = shstrtab_offset + len(shstrtab)

    header = bytearray(b"\x7fELF\x01\x01\x01\x00" + b"\x00" * 8)
    header += struct.pack("<HH", 1, 8)              # ET_REL, EM_MIPS
    header += struct.pack("<I", 1)
    header += struct.pack("<I", 0)
    header += struct.pack("<I", 0)                  # e_phoff
    header += struct.pack("<I", shoff)              # e_shoff
    header += struct.pack("<I", 0)
    header += struct.pack("<HHHHHH", header_size, 0, 0, 40, 5, 4)

    sections = [
        (0, 0, 0, 0, 0, 0, 0, 0, 0, 0),             # the null section
        (shstr_names[".text"], 1, 0x6, 0, text_offset, len(text), 0, 0, 4, 0),
        (shstr_names[".symtab"], 2, 0, 0, symtab_offset, len(symtab), 3, 1, 4, 16),
        (shstr_names[".strtab"], 3, 0, 0, strtab_offset, len(strtab), 0, 0, 1, 0),
        (0, 3, 0, 0, shstrtab_offset, len(shstrtab), 0, 0, 1, 0),
    ]
    table = b"".join(struct.pack("<IIIIIIIIII", *section) for section in sections)
    return (bytes(header) + text + symtab + strtab + shstrtab + table)


class HarnessTests(unittest.TestCase):
    def test_refuses_a_missing_symbol(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            elf = root / "retail.elf"
            elf.write_bytes(build_prx(b"\x00" * 64))
            obj = root / "body.o"
            obj.write_bytes(build_object(b"\x00" * 8))
            report = harness.compare_symbols(elf, obj, "nope", 0x100)
            self.assertEqual(report["result"], "refused")

    def test_compares_and_finds_the_first_difference(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            body = b"\x01\x02\x03\x04\x05\x06\x07\x08"
            elf = root / "retail.elf"
            elf.write_bytes(build_prx(body))
            obj = root / "body.o"
            obj.write_bytes(build_object(body))
            report = harness.compare_symbols(elf, obj, "body", 0)
            self.assertEqual(report["result"], "exact")
            self.assertEqual(report["size"], len(body))

            obj2 = root / "other.o"
            other = bytearray(body)
            other[5] = 0xFF
            obj2.write_bytes(build_object(bytes(other)))
            report = harness.compare_symbols(elf, obj2, "body", 0)
            self.assertEqual(report["result"], "mismatch")
            self.assertEqual(report["first_difference"], 5)

    def test_reports_a_size_difference(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            elf = root / "retail.elf"
            elf.write_bytes(build_prx(b"\x00" * 8))
            obj = root / "body.o"
            obj.write_bytes(build_object(b"\x00" * 4))
            # the caller knows the retail body is 8 bytes long
            report = harness.compare_symbols(elf, obj, "body", 0, size=8)
            self.assertEqual(report["result"], "mismatch")
            self.assertEqual(report["reason"], "the compiled body has another size")
            self.assertEqual(report["compiled_size"], 4)


class InventoryTests(unittest.TestCase):
    def test_builds_the_tables(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "disc"
            data = root / "PSP_GAME" / "USRDIR" / "data"
            data.mkdir(parents=True)
            (root / "PSP_GAME" / "SYSDIR").mkdir(parents=True)
            (root / "PSP_GAME" / "SYSDIR" / "EBOOT.BIN").write_bytes(
                build_encrypted_psp("dax"))
            (data / "level.bin").write_bytes(
                build_pack([(3, b"RADI" + b"\x00" * 12, 6)]))
            out = Path(directory) / "config"
            counts = disc_inventory.build(root, out)
            self.assertEqual(counts["packs"], 1)
            self.assertTrue((out / "disc" / "pack_index.tsv").is_file())
            self.assertTrue((out / "levels" / "modules.tsv").is_file())
            rows = (out / "disc" / "pack_index.tsv").read_text(
                encoding="utf-8").splitlines()
            self.assertIn("level.bin", rows[1])
            self.assertEqual(len(rows), 2)

    def test_check_reports_a_stale_table(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "disc"
            data = root / "PSP_GAME" / "USRDIR" / "data"
            data.mkdir(parents=True)
            (data / "level.bin").write_bytes(
                build_pack([(3, b"RADI" + b"\x00" * 12, 6)]))
            out = Path(directory) / "config"
            disc_inventory.build(root, out)
            self.assertEqual(disc_inventory.check(root, out), 0)
            (out / "disc" / "pack_index.tsv").write_text("stale\n", encoding="utf-8")
            self.assertEqual(disc_inventory.check(root, out), 1)


if __name__ == "__main__":
    unittest.main()
