#!/usr/bin/env python3
"""Check the structural invariants of the repository.

The check is structural, not semantic: it verifies that the published
metadata is consistent with itself, that the documented tables are present
and well formed, that the source layout is the one the method describes, and
that nothing that must never be committed has been committed.

It reads only the repository. It never needs the game.

Usage:
    python3 tools/check_repository.py
"""

from __future__ import annotations

import csv
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

#: Paths that must exist.
REQUIRED_PATHS = [
    "README.md",
    "AGENTS.md",
    "CONTRIBUTING.md",
    "LEGAL.md",
    "LICENSE",
    "THIRD_PARTY_NOTICES.md",
    "PROMPT.md",
    ".recomp.json",
    ".gitignore",
    "config/target.json",
    "config/toolchain.json",
    "config/boot/summary.json",
    "config/boot/functions.tsv",
    "config/disc/containers.tsv",
    "config/disc/pack_index.tsv",
    "config/levels/modules.tsv",
    "docs/METHOD.md",
    "docs/EVIDENCE.md",
    "docs/GATES.md",
    "docs/STATE.md",
    "docs/REUSE.md",
    "docs/FORMATS.md",
    "docs/LAYOUT.md",
    "config/boot/idioms.json",
    "config/boot/layout.tsv",
    "config/boot/layout_summary.json",
    "tools/psp_formats.py",
    "tools/psp_crypto.py",
    "tools/decrypt_psp.py",
    "tools/psp_elf.py",
    "tools/disc_inventory.py",
    "tools/boot_inventory.py",
    "tools/function_inventory.py",
    "tools/progress.py",
    "tests/test_tools.py",
]

#: Suffixes that must never appear in the repository.
FORBIDDEN_SUFFIXES = [
    ".iso", ".bin", ".elf", ".prx", ".psar", ".pack", ".pkg", ".cso",
    ".at3", ".pmf", ".png", ".pmf",
]

#: Directories where generated or private material belongs.
PRIVATE_DIRECTORIES = ["work"]

HEX40 = re.compile(r"^[0-9a-f]{40}$")
HEX64 = re.compile(r"^[0-9a-f]{64}$")


class Report:
    def __init__(self) -> None:
        self.failures: list[str] = []
        self.notes: list[str] = []

    def require(self, condition: bool, message: str) -> None:
        if not condition:
            self.failures.append(message)

    def note(self, message: str) -> None:
        self.notes.append(message)

    def report(self) -> int:
        for note in self.notes:
            print(f"note: {note}")
        for failure in self.failures:
            print(f"FAIL: {failure}", file=sys.stderr)
        if self.failures:
            print(f"\n{len(self.failures)} problem(s) found.", file=sys.stderr)
            return 1
        print("all structural checks passed.")
        return 0


def check_paths(report: Report) -> None:
    for relative in REQUIRED_PATHS:
        report.require((ROOT / relative).is_file(),
                       f"missing required path: {relative}")


def check_target(report: Report) -> dict:
    path = ROOT / "config" / "target.json"
    if not path.is_file():
        return {}
    target = json.loads(path.read_text(encoding="utf-8"))
    for key in ("game", "platform", "title_id", "disc_version",
                "disc_sha1", "disc_sha256", "disc_size", "executable"):
        report.require(key in target, f"config/target.json lacks '{key}'")
    for key in ("disc_sha1",):
        value = target.get(key, "")
        report.require(bool(HEX40.match(value)),
                       f"config/target.json {key} is not a SHA-1: {value!r}")
    for key in ("disc_sha256",):
        value = target.get(key, "")
        report.require(bool(HEX64.match(value)),
                       f"config/target.json {key} is not a SHA-256: {value!r}")
    executable = target.get("executable", {})
    report.require(executable.get("container") == "~PSP",
                   "the pinned executable is not a ~PSP container")
    report.require(executable.get("encrypted") is True,
                   "the pinned executable is not marked as encrypted")
    decrypted = executable.get("decrypted_sha256")
    if decrypted:
        report.require(bool(HEX64.match(decrypted)),
                       "the decrypted hash of the executable is malformed")
        report.require(executable.get("prx_type") in ("type0", "type1"),
                       "the PRX type of the executable is not recorded")
    else:
        report.require(executable.get("decrypted_sha256") in (None, ""),
                       "the decrypted hash of the executable is malformed")
    code = target.get("code", {})
    report.require(code.get("objects") == 1,
                   "the number of code objects is not recorded")
    report.note(f"target: {target.get('game')} ({target.get('title_id')}), "
                f"executable {executable.get('size')} bytes, "
                f"decrypted: {bool(decrypted)}")
    return target


def check_recomp_manifest(report: Report) -> None:
    path = ROOT / ".recomp.json"
    if not path.is_file():
        return
    manifest = json.loads(path.read_text(encoding="utf-8"))
    for key in ("game", "system", "type", "status"):
        report.require(key in manifest, f".recomp.json lacks '{key}'")
    original = manifest.get("original", {})
    if "sha1" in original:
        report.require(bool(HEX40.match(original["sha1"])),
                       ".recomp.json original.sha1 is not a SHA-1")


def check_tables(report: Report) -> None:
    expectations = {
        "config/disc/containers.tsv": ("path", "container", "size", "sha256"),
        "config/disc/pack_index.tsv": ("path", "size", "sha256", "version",
                                       "entries", "types", "magics"),
        "config/levels/modules.tsv": ("path", "version", "entries", "types"),
        "config/boot/functions.tsv": ("address", "file_offset", "frame",
                                      "saves_ra", "gp_setup"),
    }
    for relative, header in expectations.items():
        path = ROOT / relative
        if not path.is_file():
            continue
        with path.open(encoding="utf-8", newline="") as handle:
            rows = list(csv.reader(handle, delimiter="\t"))
        report.require(bool(rows), f"{relative} is empty")
        if not rows:
            continue
        report.require(tuple(rows[0]) == header,
                       f"{relative} header is {rows[0]}, expected {list(header)}")
        report.require(len(rows) > 1, f"{relative} has no data row")
        for row in rows[1:]:
            report.require(len(row) == len(header),
                           f"{relative} has a row with {len(row)} fields")


def check_source_layout(report: Report) -> None:
    """Every published C file must be one function definition, or a header."""
    src = ROOT / "src"
    if not src.is_dir():
        return
    for path in sorted(src.rglob("*.c")):
        text = path.read_text(encoding="utf-8", errors="replace")
        report.require("asm" not in text.lower(),
                       f"{path.relative_to(ROOT)} mentions assembly: the "
                       f"pure-C rule forbids it")
        report.require(".word" not in text,
                       f"{path.relative_to(ROOT)} contains a raw .word")
        report.require(".set" not in text,
                       f"{path.relative_to(ROOT)} contains a raw .set")
    bodies = list((src / "boot" / "bodies").glob("*.c")) + \
        list((src / "levels" / "bodies").glob("*.c"))
    report.note(f"published bodies: {len(bodies)}")


def check_nothing_forbidden(report: Report) -> None:
    """No game data may be tracked."""
    for path in sorted(ROOT.rglob("*")):
        if not path.is_file():
            continue
        relative = path.relative_to(ROOT)
        parts = relative.parts
        if ".git" in parts:
            continue
        if parts and parts[0] in PRIVATE_DIRECTORIES:
            continue
        if path.suffix.lower() in FORBIDDEN_SUFFIXES:
            report.failures.append(
                f"forbidden file committed: {relative.as_posix()}")
        if path.stat().st_size > 4 * 1024 * 1024:
            report.failures.append(
                f"suspiciously large file committed: {relative.as_posix()}")


def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    report = Report()
    check_paths(report)
    check_target(report)
    check_recomp_manifest(report)
    check_tables(report)
    check_source_layout(report)
    check_nothing_forbidden(report)
    return report.report()


if __name__ == "__main__":
    raise SystemExit(main())
