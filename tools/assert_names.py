#!/usr/bin/env python3
"""Recover the name of the functions that host an assert.

The engine carries its asserts through a helper at ``0x7035C`` that takes
the name of the enclosing function in ``$a3`` — the C ``__FUNCTION__``.
Every call site of that helper therefore names the function it sits in.
There are **344** such call sites in the target.

This is the largest naming source the project has: the executable is
stripped, and this is the code telling us its own names.

How the argument is built
-------------------------

The compiler does not always materialise the name where the call is.  It
uses several shapes, and the resolver has to follow all of them:

``direct``
    The address of the name is built in place: a ``lui`` that loads the
    high half and an ``addiu`` that completes it, often **in the delay
    slot of the call itself**.

``register``
    The address is built once, kept in a callee-saved register for the
    whole body, and only moved into ``$a3`` at the call.  A linear walk
    of the whole body finds it; a window does not.

``copy``
    The engine copies the name into a scratch buffer of the data segment
    with a byte loop, and passes the *address of the buffer*.  The bytes
    of the buffer only exist at run time, so the resolver has to run the
    loop: a backward branch is replayed until the memory stops moving.

``pool``
    The address is loaded as a pointer out of the identifier pool, which
    starts at ``0x00340000``.

``carry``
    The site does not set ``$a3`` at all: the call is a plain error
    print, and the register still holds what the body built earlier.
    The name is then the name of the body, but the site does not pass
    it; the evidence column says so.

**Current coverage.**  The resolver walks every body that holds a call
site, so the catalogue has one row per site and the count it prints is
the count of the sites.  On the pinned target **339 of the 344** sites
are resolved, into **73** distinct names over **82** bodies.  The five
that resist are the calls that pass no name at all: their ``$a3`` holds
a constant of the comparison, or the argument of the caller.

A site is *resolved* when the abstract value of ``$a3`` points at a
printable string that has the shape of a C identifier; a site whose
argument is a format string, a source path or a message is reported as
such rather than dressed up as a name.  The catalogue is therefore
partial, and the tool says so rather than pretending otherwise: it
prints both the count of the sites and the count of the ones that were
resolved.  The names themselves live in a string pool of the game; see
``docs/STATE.md`` for the open item.

The catalogue it writes is **private**: it holds the text of the game.
The repository publishes the names it recovers, and the counts.

Usage:
    python3 tools/assert_names.py --elf <decrypted.elf> \\
        --layout config/boot/layout.tsv --out work/ASSERT
"""

from __future__ import annotations

import argparse
import csv
import re
import struct
import sys
from bisect import bisect_right
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import psp_elf  # noqa: E402

#: The address of the assert helper of the pinned target.  The register
#: that carries the function name is the third argument, ``$a3``.
ASSERT_HELPER = 0x0007035C
NAME_REGISTER = 7          # $a3

#: The identifier pool of the engine starts here, in the data segment,
#: and runs to the end of the writable segment.
POOL_START = 0x00340000
POOL_END = 0x00363A98

#: The instruction forms the walk understands.
OP_LUI = 0x3C000000
OP_ADDIU = 0x24000000
OP_ADDI = 0x20000000
OP_ORI = 0x34000000
OP_ANDI = 0x30000000
OP_XORI = 0x38000000
OP_SLTI = 0x28000000
OP_SLTIU = 0x2C000000
OP_LW = 0x8C000000
OP_LB = 0x80000000
OP_LBU = 0x90000000
OP_LH = 0x84000000
OP_LHU = 0x94000000
OP_SW = 0xAC000000
OP_SB = 0xA0000000
OP_SH = 0xA4000000
OP_JAL = 0x0C000000
OP_J = 0x08000000
OP_BEQ = 0x10000000
OP_BNE = 0x14000000
OP_BLEZ = 0x18000000
OP_BGTZ = 0x1C000000
OP_REGIMM = 0x00000000
OP_SPECIAL = 0x00000000

FUNCT_SLL = 0x00
FUNCT_SRL = 0x02
FUNCT_SRA = 0x03
FUNCT_SLLV = 0x04
FUNCT_SRLV = 0x06
FUNCT_SRAV = 0x07
FUNCT_JR = 0x08
FUNCT_JALR = 0x09
FUNCT_ADD = 0x20
FUNCT_ADDU = 0x21
FUNCT_SUB = 0x22
FUNCT_SUBU = 0x23
FUNCT_AND = 0x24
FUNCT_OR = 0x25
FUNCT_XOR = 0x26
FUNCT_NOR = 0x27
FUNCT_SLT = 0x2A
FUNCT_SLTU = 0x2B

#: The registers a call destroys: the ABI makes them caller-saved.
CALLER_SAVED = (2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15, 24, 25)

#: How many times a backward branch is replayed before the walk gives up.
MAX_ROUNDS = 64

#: The longest string the resolver reads.
MAX_STRING = 256

#: The shape of a C identifier.  A destructor carries a tilde, a method
#: carries the scope operator; anything else is a message, a format or
#: a path, and is reported as such.
IDENTIFIER = re.compile(r"^[A-Za-z_~][A-Za-z0-9_]*(::[A-Za-z_~][A-Za-z0-9_]*)*$")


def _rs(word: int) -> int:
    return (word >> 21) & 0x1F


def _rt(word: int) -> int:
    return (word >> 16) & 0x1F


def _rd(word: int) -> int:
    return (word >> 11) & 0x1F


def _imm(word: int) -> int:
    return word & 0xFFFF


def _opcode(word: int) -> int:
    return word & 0xFC000000


def is_regimm(word: int) -> bool:
    """Say whether the word is a REGIMM branch and not a SPECIAL one.

    Both share the opcode ``000000``: REGIMM puts the condition in the
    field that SPECIAL uses for its second operand.  The all-zero word
    is the ``nop``, and the two are told apart the way the assembler
    does it: a REGIMM has its condition in that field, a ``sll`` has
    none.
    """
    if word == 0:
        return False
    if _opcode(word) != OP_REGIMM:
        return False
    if (word & 0x3F) != 0:            # only the shift shares the opcode
        return False
    return _rt(word) in (0, 1, 16, 17)


def _signed(imm: int) -> int:
    return imm - 0x10000 if imm & 0x8000 else imm


def segments(data: bytes) -> list[tuple[int, int, int, int]]:
    _header, programs, _sections = psp_elf._headers(data)
    return [(offset, size, vaddr, flags)
            for ptype, offset, vaddr, _paddr, size, _memsz, flags, _align
            in programs if ptype == 1]


def to_file(loads, address: int) -> int | None:
    for offset, size, vaddr, _flags in loads:
        if vaddr <= address < vaddr + size:
            return offset + (address - vaddr)
    return None


def call_sites(data: bytes, loads, target: int) -> list[int]:
    """Return the addresses of the calls to ``target``."""
    sites = []
    for offset, size, vaddr, _flags in loads:
        for position in range(0, size - 3, 4):
            word = struct.unpack_from("<I", data, offset + position)[0]
            if (word & 0xFC000000) != 0x0C000000:
                continue
            reached = ((vaddr + position + 4) & 0xF0000000) | \
                      ((word & 0x03FFFFFF) << 2)
            if reached == target:
                sites.append(vaddr + position)
    return sites


class Value:
    """One abstract register value: a known word, with its origin."""

    __slots__ = ("bits", "where", "kind", "src")

    def __init__(self, bits: int, where: int, kind: str,
                 src: "Value | None" = None):
        self.bits = bits
        self.where = where
        self.kind = kind
        self.src = src

    def root(self) -> "Value":
        """Follow the moves back to the value that was really built."""
        value = self
        while value.kind == "move" and value.src is not None:
            value = value.src
        return value


class Walker:
    """The abstract state of one body: registers and a memory map."""

    def __init__(self, data: bytes, loads):
        self.data = data
        self.loads = loads
        self.regs: list[Value | None] = [None] * 32
        self.mem: dict[int, int] = {}      # address -> byte
        self.written: set[int] = set()     # addresses the body wrote
        self.stale: bool = True            # is $a3 a leftover of a call?

    # --- the memory ----------------------------------------------------
    def byte(self, address: int) -> int | None:
        if address in self.mem:
            return self.mem[address]
        offset = to_file(self.loads, address)
        if offset is None or offset >= len(self.data):
            return None
        return self.data[offset]

    def load_word(self, address: int) -> int | None:
        parts = [self.byte(address + index) for index in range(4)]
        if any(part is None for part in parts):
            return None
        return (parts[0] | (parts[1] << 8) | (parts[2] << 16) |
                (parts[3] << 24))

    def store(self, address: int, payload: bytes) -> None:
        for index, byte in enumerate(payload):
            self.mem[address + index] = byte
            self.written.add(address + index)

    # --- the registers -------------------------------------------------
    def value(self, register: int) -> int | None:
        if register == 0:
            return 0
        entry = self.regs[register]
        return None if entry is None else entry.bits

    def set(self, register: int, bits: int | None, where: int, kind: str,
            src: Value | None = None) -> None:
        if register == 0:
            return
        if register == NAME_REGISTER:
            self.stale = False
        self.regs[register] = None if bits is None else Value(bits, where,
                                                               kind, src)

    def clobber(self) -> None:
        """A call destroys the caller-saved registers.

        ``$a3`` is kept, and marked stale: the body built it, and the
        value is what the site hands over.  A site that never sets it
        is therefore reported apart from a site that does.
        """
        for register in CALLER_SAVED:
            if register == NAME_REGISTER:
                continue
            self.regs[register] = None
        self.stale = True

    # --- the instructions -----------------------------------------------
    def step(self, address: int) -> None:
        word = self.word(address)
        if word is None:
            return
        op = _opcode(word)
        rs = _rs(word)
        rt = _rt(word)
        rd = _rd(word)
        sa = (word >> 6) & 0x1F
        funct = word & 0x3F
        imm = _imm(word)
        simm = _signed(imm)

        if op == OP_LUI:
            self.set(rt, (imm << 16) & 0xFFFFFFFF, address, "imm")
        elif op == OP_ADDIU:
            base = self.value(rs)
            if base is None:
                self.set(rt, None, address, "imm")
            else:
                self.set(rt, (base + simm) & 0xFFFFFFFF, address, "imm")
        elif op == OP_ADDI:
            base = self.value(rs)
            if base is None:
                self.set(rt, None, address, "imm")
            else:
                self.set(rt, (base + simm) & 0xFFFFFFFF, address, "imm")
        elif op == OP_ORI:
            base = self.value(rs)
            if base is None:
                self.set(rt, None, address, "imm")
            else:
                self.set(rt, (base | imm) & 0xFFFFFFFF, address, "imm")
        elif op == OP_ANDI:
            base = self.value(rs)
            if base is None:
                self.set(rt, None, address, "imm")
            else:
                self.set(rt, (base & imm) & 0xFFFFFFFF, address, "imm")
        elif op == OP_XORI:
            base = self.value(rs)
            if base is None:
                self.set(rt, None, address, "imm")
            else:
                self.set(rt, (base ^ imm) & 0xFFFFFFFF, address, "imm")
        elif op == OP_SLTI:
            base = self.value(rs)
            self.set(rt, None if base is None else
                     (1 if base < simm else 0), address, "imm")
        elif op == OP_SLTIU:
            base = self.value(rs)
            self.set(rt, None if base is None else
                     (1 if (base & 0xFFFFFFFF) < (simm & 0xFFFFFFFF) else 0),
                     address, "imm")
        elif op == OP_LW:
            base = self.value(rs)
            if base is None:
                self.set(rt, None, address, "load")
            else:
                self.set(rt, self.load_word((base + simm) & 0xFFFFFFFF),
                         address, "load")
        elif op == OP_LB or op == OP_LBU:
            base = self.value(rs)
            if base is None:
                self.set(rt, None, address, "load")
            else:
                byte = self.byte((base + simm) & 0xFFFFFFFF)
                if byte is None:
                    self.set(rt, None, address, "load")
                elif op == OP_LB:
                    self.set(rt, byte - 0x100 if byte & 0x80 else byte,
                             address, "load")
                else:
                    self.set(rt, byte, address, "load")
        elif op == OP_LH or op == OP_LHU:
            base = self.value(rs)
            if base is None:
                self.set(rt, None, address, "load")
            else:
                low = self.byte((base + simm) & 0xFFFFFFFF)
                high = self.byte((base + simm + 1) & 0xFFFFFFFF)
                if low is None or high is None:
                    self.set(rt, None, address, "load")
                else:
                    word = low | (high << 8)
                    if op == OP_LH and word & 0x8000:
                        word -= 0x10000
                    self.set(rt, word & 0xFFFFFFFF, address, "load")
        elif op == OP_SW:
            base = self.value(rs)
            payload = self.value(rt)
            if base is not None and payload is not None:
                self.store((base + simm) & 0xFFFFFFFF,
                           (payload & 0xFFFFFFFF).to_bytes(4, "little"))
        elif op == OP_SB:
            base = self.value(rs)
            payload = self.value(rt)
            if base is not None and payload is not None:
                self.store((base + simm) & 0xFFFFFFFF,
                           bytes([payload & 0xFF]))
        elif op == OP_SH:
            base = self.value(rs)
            payload = self.value(rt)
            if base is not None and payload is not None:
                self.store((base + simm) & 0xFFFFFFFF,
                           (payload & 0xFFFF).to_bytes(2, "little"))
        elif op == OP_JAL:
            self.set(31, (address + 8) & 0xFFFFFFFF, address, "imm")
        elif op in (OP_J, OP_BEQ, OP_BNE, OP_BLEZ, OP_BGTZ):
            pass                      # a branch writes no register
        elif op == OP_SPECIAL and is_regimm(word):
            # A REGIMM branch: the two linking forms also write $ra.
            if rt in (16, 17):
                self.set(31, (address + 8) & 0xFFFFFFFF, address, "imm")
        elif op == OP_SPECIAL:
            self.step_special(address, word, rs, rt, rd, sa, funct)
        else:
            # Any other write to a register makes it unknown.
            self.set(rt, None, address, "imm")

    def step_special(self, address: int, word: int, rs: int, rt: int,
                     rd: int, sa: int, funct: int) -> None:
        left = self.value(rs)
        right = self.value(rt)
        if funct == FUNCT_JR:
            return
        if funct == FUNCT_JALR:
            self.set(rd if rd else 31, (address + 8) & 0xFFFFFFFF, address,
                     "imm")
            return
        if funct == FUNCT_SLL:
            if rt == 0 or rd == 0:
                return
            self.set(rd, None if right is None else
                     (right << sa) & 0xFFFFFFFF, address, "imm")
            return
        if funct == FUNCT_SRL:
            if rt == 0 or rd == 0:
                return
            self.set(rd, None if right is None else
                     (right & 0xFFFFFFFF) >> sa, address, "imm")
            return
        if funct == FUNCT_SRA:
            if rt == 0 or rd == 0:
                return
            self.set(rd, None if right is None else
                     (right - 0x100000000) >> sa & 0xFFFFFFFF, address, "imm")
            return
        if funct == FUNCT_SLLV:
            self.set(rd, None if left is None or right is None else
                     (right << (left & 0x1F)) & 0xFFFFFFFF, address, "imm")
            return
        if funct == FUNCT_SRLV:
            self.set(rd, None if left is None or right is None else
                     (right & 0xFFFFFFFF) >> (left & 0x1F), address, "imm")
            return
        if funct == FUNCT_SRAV:
            self.set(rd, None if left is None or right is None else
                     ((right - 0x100000000) >> (left & 0x1F)) & 0xFFFFFFFF,
                     address, "imm")
            return
        if funct in (FUNCT_ADD, FUNCT_ADDU):
            self.set(rd, None if left is None or right is None else
                     (left + right) & 0xFFFFFFFF, address, "imm")
            return
        if funct in (FUNCT_SUB, FUNCT_SUBU):
            self.set(rd, None if left is None or right is None else
                     (left - right) & 0xFFFFFFFF, address, "imm")
            return
        if funct == FUNCT_AND:
            self.set(rd, None if left is None or right is None else
                     left & right, address, "imm")
            return
        if funct == FUNCT_OR:
            if rt == 0:                       # a move
                self.set(rd, left, address, "move", self.regs[rs])
            elif rs == 0:                     # a move the other way
                self.set(rd, right, address, "move", self.regs[rt])
            else:
                self.set(rd, None if left is None or right is None else
                         left | right, address, "imm")
            return
        if funct == FUNCT_XOR:
            self.set(rd, None if left is None or right is None else
                     left ^ right, address, "imm")
            return
        if funct == FUNCT_NOR:
            self.set(rd, None if left is None or right is None else
                     ~(left | right) & 0xFFFFFFFF, address, "imm")
            return
        if funct == FUNCT_SLT:
            self.set(rd, None if left is None or right is None else
                     (1 if left < right else 0), address, "imm")
            return
        if funct == FUNCT_SLTU:
            self.set(rd, None if left is None or right is None else
                     (1 if (left & 0xFFFFFFFF) < (right & 0xFFFFFFFF) else 0),
                     address, "imm")
            return
        # mult, div, mfhi, mflo, and the rest: the register is unknown.
        self.set(rd, None, address, "imm")

    # --- the control flow -----------------------------------------------
    def word(self, address: int) -> int | None:
        offset = to_file(self.loads, address)
        if offset is None or offset + 4 > len(self.data):
            return None
        return struct.unpack_from("<I", self.data, offset)[0]

    def branch_target(self, address: int) -> int | None:
        word = self.word(address)
        if word is None:
            return None
        op = _opcode(word)
        if op == OP_JAL or op == OP_J:
            return ((address + 4) & 0xF0000000) | ((word & 0x03FFFFFF) << 2)
        if op in (OP_BEQ, OP_BNE, OP_BLEZ, OP_BGTZ):
            return address + 4 + (_signed(_imm(word)) << 2)
        if is_regimm(word):
            return address + 4 + (_signed(_imm(word)) << 2)
        return None

    def branch_taken(self, address: int) -> bool:
        """Say whether the branch at ``address`` is taken.

        An unknown operand is read as "taken": the walk then replays the
        loop until the memory stops moving, which is what the engine's
        copy loop needs.
        """
        word = self.word(address)
        if word is None:
            return False
        op = _opcode(word)
        rs = _rs(word)
        rt = _rt(word)
        left = self.value(rs)
        right = self.value(rt)
        if op == OP_BEQ:
            if left is None or right is None:
                return True
            return left == right
        if op == OP_BNE:
            if left is None or right is None:
                return True
            return left != right
        if op == OP_BLEZ:
            return True if left is None else left <= 0
        if op == OP_BGTZ:
            return True if left is None else left > 0
        if op == OP_REGIMM and is_regimm(word):
            kind = rt
            if kind in (0, 16):
                return True if left is None else left < 0
            if kind in (1, 17):
                return True if left is None else left >= 0
        return False


def has_delay_slot(word: int) -> bool:
    op = _opcode(word)
    if op in (OP_JAL, OP_J, OP_BEQ, OP_BNE, OP_BLEZ, OP_BGTZ):
        return True
    if is_regimm(word):
        return True
    if op == OP_SPECIAL and (word & 0x3F) in (FUNCT_JR, FUNCT_JALR):
        return True
    return False


def is_call(word: int) -> bool:
    op = _opcode(word)
    if op == OP_JAL:
        return True
    if op == OP_SPECIAL and (word & 0x3F) == FUNCT_JALR:
        return True
    return False


def backward_branches(data: bytes, loads, start: int, end: int) -> dict[int, int]:
    """Return the backward branches of a body, and where they go."""
    out = {}
    for address in range(start, end, 4):
        offset = to_file(loads, address)
        if offset is None or offset + 4 > len(data):
            continue
        word = struct.unpack_from("<I", data, offset)[0]
        if not has_delay_slot(word):
            continue
        op = _opcode(word)
        if op in (OP_JAL, OP_J):
            continue
        target = None
        if op in (OP_BEQ, OP_BNE, OP_BLEZ, OP_BGTZ):
            target = address + 4 + (_signed(_imm(word)) << 2)
        elif is_regimm(word):
            target = address + 4 + (_signed(_imm(word)) << 2)
        if target is not None and target < address:
            out[address] = target
    return out


def walk(data: bytes, loads, start: int, end: int,
         sites: dict[int, tuple[Value | None, bool]]) -> Walker:
    """Walk a body in program order and record ``$a3`` at each site.

    The walk is linear: every instruction of the body is applied once, in
    the order it stands.  The two places where the program order and the
    linear order differ are handled explicitly:

    * the **delay slot** of a call or a branch runs before the callee
      sees the arguments, so it is applied before the arguments are
      read;
    * a **backward branch** is a loop: it is replayed from its target
      until the memory stops moving, which is how the engine's copy
      loop fills a scratch buffer with a name.

    The walker is returned: the memory it built is the only place where
    a copied name exists.
    """
    walker = Walker(data, loads)
    loops = backward_branches(data, loads, start, end)
    heads = set(loops.values())
    snapshots: dict[int, tuple[list, dict]] = {}
    address = start
    while address < end:
        word = walker.word(address)
        if word is None:
            address += 4
            continue
        if address in heads:
            snapshots[address] = (list(walker.regs), dict(walker.mem))
        if address in loops:
            target = loops[address]
            snapshot = snapshots.get(target)
            if snapshot is not None:
                walker.regs = list(snapshot[0])
                walker.mem = dict(snapshot[1])
                replay(walker, target, address)
            else:
                walker.step(address + 4)    # the slot of the branch
            address += 8
            continue
        walker.step(address)
        if has_delay_slot(word):
            walker.step(address + 4)
        if address in sites:
            sites[address] = (walker.regs[NAME_REGISTER], walker.stale)
        if is_call(word):
            walker.clobber()
        address += 8 if has_delay_slot(word) else 4
    return walker


def replay(walker: Walker, target: int, branch: int) -> None:
    """Run the loop at ``branch`` until its memory stops moving."""
    for _ in range(MAX_ROUNDS):
        for address in range(target, branch, 4):
            walker.step(address)
        taken = walker.branch_taken(branch)
        walker.step(branch + 4)          # the slot of the loop branch
        if not taken:
            return


def string_at(walker: Walker | None, address: int | None) -> str | None:
    """Return the printable string at ``address``, or ``None``.

    The string is read from the memory the body built first: a name that
    the engine copies into a scratch buffer only exists there.
    """
    if walker is None or address is None:
        return None
    out = bytearray()
    for index in range(MAX_STRING):
        byte = walker.byte(address + index)
        if byte is None or byte == 0:
            break
        out.append(byte)
    else:
        return None
    if not out:
        return None
    if not all(0x20 <= byte < 0x7F for byte in out):
        return None
    return out.decode("ascii")


def read_layout(path: Path) -> list[tuple[int, int]]:
    """Return the (start, end) of the reviewed bodies."""
    if not path.is_file():
        return []
    out = []
    with path.open(encoding="utf-8", newline="") as handle:
        for row in csv.DictReader(handle, delimiter="\t"):
            if row.get("start"):
                out.append((int(row["start"], 16), int(row["end"], 16)))
    out.sort()
    return out


class Bodies:
    """The bodies of the target: the reviewed ones first, then the sweep."""

    def __init__(self, reviewed: list[tuple[int, int]],
                 sweep: list[tuple[int, int]]):
        self.reviewed = reviewed
        self.sweep = sweep
        self.starts = [start for start, _ in sweep]

    def owner(self, address: int) -> tuple[int, int] | None:
        for start, end in self.reviewed:
            if start <= address < end:
                return (start, end)
        index = bisect_right(self.starts, address) - 1
        for step in range(8):
            if index - step < 0:
                break
            start, end = self.sweep[index - step]
            if start <= address < end:
                return (start, end)
        return None


def evidence_of(walker: Walker, entry: Value | None, site: int,
                address: int | None, text: str | None,
                stale: bool) -> str:
    """Say how the name was obtained, or what the argument really is."""
    if entry is None:
        return "-"
    root = entry.root()
    if text is None:
        return "not-a-string"
    if address is not None and address in walker.written:
        return "copy"
    if stale:
        # the site did not set $a3: it hands over what the body built
        return "carry"
    if root.kind == "load":
        return "pool" if POOL_START <= (entry.bits or 0) < POOL_END \
            else "load"
    if root.kind == "imm" and root.where >= site - 16:
        return "direct"
    return "register"


def what_it_is(text: str | None) -> str:
    """Describe a string that is not a function name."""
    if text is None:
        return "not-a-string"
    if "%" in text:
        return "format"
    if "\\" in text or ("/" in text and " " not in text):
        return "path"
    return "message"


def main(argv: list[str] | None = None) -> int:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--elf", type=Path, required=True)
    parser.add_argument("--layout", type=Path,
                        default=Path("config/boot/layout.tsv"))
    parser.add_argument("--bounds", type=Path,
                        default=Path("work/E0/bounds.tsv"),
                        help="the bodies of the sweep, used for the sites "
                             "the reviewed layout does not cover")
    parser.add_argument("--out", type=Path, default=Path("work/ASSERT"))
    parser.add_argument("--helper", type=lambda v: int(v, 0),
                        default=ASSERT_HELPER)
    args = parser.parse_args(argv)

    data = args.elf.read_bytes()
    loads = segments(data)

    reviewed = read_layout(args.layout)
    sweep = read_layout(args.bounds)
    bodies = Bodies(reviewed, sweep)

    sites = call_sites(data, loads, args.helper)

    # --- the walk --------------------------------------------------------
    found: dict[int, tuple[Value | None, bool]] = {}
    walkers: dict[tuple[int, int], Walker] = {}
    by_body: dict[tuple[int, int], list[int]] = {}
    owners: dict[int, tuple[int, int] | None] = {}
    for site in sites:
        owner = bodies.owner(site)
        owners[site] = owner
        if owner is None:
            found[site] = (None, True)
        else:
            by_body.setdefault(owner, []).append(site)
            found.setdefault(site, (None, True))

    for (start, end), members in sorted(by_body.items()):
        collected: dict[int, tuple[Value | None, bool]] = {
            site: (None, True) for site in members}
        walkers[(start, end)] = walk(data, loads, start, end, collected)
        for site, value in collected.items():
            found[site] = value

    # --- the reading -----------------------------------------------------
    rows = []
    for site in sites:
        owner = owners[site]
        entry, stale = found.get(site, (None, True))
        address = None if entry is None else entry.bits
        walker = walkers.get(owner) if owner else None
        if walker is None:
            walker = Walker(data, loads)
        text = string_at(walker, address)
        if text is not None and IDENTIFIER.match(text):
            name = text
            evidence = evidence_of(walker, entry, site, address, text, stale)
        else:
            name = "-"
            evidence = "-" if entry is None else what_it_is(text)
        rows.append((owner, name, site, evidence))

    # --- the catalogue ---------------------------------------------------
    args.out.mkdir(parents=True, exist_ok=True)
    path = args.out / "assert_names.tsv"
    resolved = 0
    names: dict[str, set[int]] = {}
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle, delimiter="\t", lineterminator="\n")
        writer.writerow(["function", "name", "assert_site", "evidence"])
        for owner, name, site, evidence in rows:
            if name != "-":
                resolved += 1
                if owner is not None:
                    names.setdefault(name, set()).add(owner[0])
            writer.writerow([f"0x{owner[0]:08X}" if owner else "-",
                             name, f"0x{site:08X}", evidence])

    # --- the per-body names ---------------------------------------------
    # A body of the sweep may cover several functions: the engine
    # inlines a destructor in the body of its caller, and the two then
    # carry two names.  The name that most of the sites support wins;
    # a tie goes to the name the earliest site carries, which is the
    # function the body starts in.
    by_body_name: dict[int, dict[str, int]] = {}
    first_site: dict[int, tuple[int, str]] = {}
    for owner, name, site, evidence in rows:
        if owner is None or name == "-":
            continue
        start = owner[0]
        by_body_name.setdefault(start, {})
        by_body_name[start][name] = by_body_name[start].get(name, 0) + 1
        if start not in first_site or site < first_site[start][0]:
            first_site[start] = (site, name)

    names_path = args.out / "names.tsv"
    named = 0
    conflicting = 0
    with names_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle, delimiter="\t", lineterminator="\n")
        writer.writerow(["function", "name", "confidence", "source"])
        for start in sorted(by_body_name):
            tally = by_body_name[start]
            best = max(tally.items(),
                       key=lambda item: (item[1],
                                         item[0] == first_site[start][1]))
            count = best[1]
            if len(tally) == 1:
                confidence = "high" if count > 1 else "medium"
                source = "assert"
            else:
                confidence = "low"
                source = f"assert+conflict({len(tally)})"
                conflicting += 1
            writer.writerow([f"0x{start:08X}", best[0], confidence, source])
            named += 1

    print(f"assert sites   : {len(sites)}")
    print(f"resolved       : {resolved}")
    print(f"distinct names : {len(names)}")
    print(f"bodies named   : {named}")
    print(f"bodies in doubt: {conflicting}")
    print(f"catalogue      : {path}")
    print(f"body names     : {names_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
