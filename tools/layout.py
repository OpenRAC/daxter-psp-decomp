#!/usr/bin/env python3
"""Establish the layout of the code: the call graph and the bounded bodies.

This is the **foundation lot** of the project, the piece the sibling
OpenRAC projects call *layout*.  Its job is to turn the raw frame-opening
candidates of ``tools/function_inventory.py`` into **bounded candidates**:
a start, an end, and the evidence that the range really is one body.

It writes three private artifacts, all of which stay out of the repository:

``work/E0/calls.tsv``     the call graph: every call site and its target
``work/E0/bounds.tsv``    the bounded candidates, with the proof of each bound
``work/lots/L*.tsv``      the lots, ranked by leverage

The method
----------

The retail executable is stripped, so the boundaries have to be recovered
from the code.  Four observations are used, and each of them is recorded
as the *evidence* of the candidate:

1. **A call names a function.**  Every ``jal`` target is the start of a
   function.  This is the strongest evidence there is.
2. **A return ends a body.**  A ``jr $ra`` is the end of a return path.
   The body of a function ends at its *last* return, not its first.
3. **A function often starts right after a return.**  In stripped code the
   next function usually follows the previous one's epilogue.
4. **A jump through a register can be read.**  The code of a switch
   computes the address of a **table** with ``lui``/``addu``/``lw``, masks
   the index with ``andi`` or checks it with ``sltiu``, and jumps through
   the register the table gave it.  The graph reads the table, so the
   cases of the switch belong to the body they are part of.

A candidate is therefore a function start that is a call target, or that
follows a return, or that opens a frame; and its body runs to the last
return before the next such start.

**Leverage** is the number of call sites that carry the same body.  It is
the ranking the shortlist uses: a body that many places call is worth more
than a rare large one, because one authored source can satisfy all of them.

Usage:
    python3 tools/layout.py --elf <decrypted.elf> [--work work] [--lots 6]
                            [--per-lot 40]
"""

from __future__ import annotations

import argparse
import csv
import struct
import sys
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import function_inventory  # noqa: E402

#: The instructions the sweep looks for.
OP_JAL = 0x0C000000          # jal target
OP_J = 0x08000000           # j target
OP_BEQ = 0x10000000         # beq rs, rt, offset
OP_BNE = 0x14000000         # bne rs, rt, offset
OP_SPECIAL = 0x00000000     # the SPECIAL opcode, which carries jr and jalr
FUNCT_JR = 0x08
FUNCT_JALR = 0x09
OP_ADDiu_SP = 0x27BD0000    # addiu $sp, $sp, imm

#: The conditional branches, and the *likely* forms of them.  The graph
#: absorbs the delay slot of a branch whatever the condition is: the
#: instruction belongs to the body either way.
CONDITIONAL = {0x04, 0x05, 0x06, 0x07, 0x14, 0x15, 0x16, 0x17}
#: The REGIMM family: bltz, bgez, and their likely forms.
REGIMM = {0x01}

REG_RA = 31
REG_T9 = 25
REG_ZERO = 0

#: The loadable segments of the executable, and their permissions.
PT_LOAD = 1
PF_X = 1
PF_W = 2

#: The instructions the resolver of the jump tables reads.
OP_ADDIU = 0x09
OP_SLTI = 0x0A
OP_SLTIU = 0x0B
OP_ANDI = 0x0C
OP_ORI = 0x0D
OP_LUI = 0x0F
OP_LW = 0x23

FUNCT_SLL = 0x00
FUNCT_ADDU = 0x21
FUNCT_SUBU = 0x23
FUNCT_OR = 0x25

#: How many instructions the resolver looks back for the definition of a
#: register.  The pattern of a switch is five instructions long; the
#: window is wide enough for the range check that gives the count.
RESOLVE_WINDOW = 64
#: How many instructions the resolver looks back for the range check of
#: the index.  The check sits before the branch that leaves the switch.
BOUND_WINDOW = 48
#: The largest table the resolver accepts.  A table of ten thousand cases
#: is not a switch, it is a mistake.
MAX_CASES = 4096


def _is_conditional(word: int) -> bool:
    if (word >> 26) in CONDITIONAL or (word >> 26) in REGIMM:
        return True
    # The floating-point branches: bc1f, bc1t, bc1fl and bc1tl.  A
    # disassembler that does not separate them from the other cop1
    # instructions makes a body look broken, and the bound explode.
    if (word >> 26) == 0x11 and (word & 0x3F) in (0x08, 0x09, 0x0E, 0x0F):
        return True
    return False


def _is_jump(word: int) -> bool:
    """Return True for the unconditional jumps and the returns.

    The main opcodes: 0x02 is ``j``, 0x03 is ``jal``.  Beware of the
    neighbours: 0x08 is ``addi`` and 0x0C is ``andi``, and a graph that
    mistakes them for a jump and for a call loses a great deal of the
    code.
    """
    opcode = word >> 26
    if opcode == 0x02:                    # j
        return True
    if (word & 0xFC000000) == OP_SPECIAL:
        funct = word & 0x3F
        if funct in (FUNCT_JR, FUNCT_JALR):
            return True
    return False


def _is_return(word: int) -> bool:
    """Return True for a return: a jump through a register."""
    if (word & 0xFC000000) != OP_SPECIAL:
        return False
    if (word & 0x3F) != FUNCT_JR:
        return False
    return ((word >> 21) & 0x1F) in (REG_RA, REG_T9)


def _is_call(word: int) -> bool:
    """Return True for a call: the control leaves and comes back.

    ``jal`` is the main opcode 0x03.  The opcode 0x0C is ``andi``, which
    is not a call, and the mask 0xFC000000 has to be applied to the whole
    word for the comparison to mean anything.
    """
    if (word >> 26) == 0x03:
        return True
    if (word & 0xFC000000) == OP_SPECIAL and (word & 0x3F) == FUNCT_JALR:
        return True
    return False


def _insn(data: bytes, offset: int) -> int:
    return struct.unpack_from("<I", data, offset)[0]


def _branch_target(word: int, pc: int) -> int | None:
    """Return the target of a branch, if the instruction is one."""
    opcode = word & 0xFC000000
    if opcode == OP_JAL or opcode == OP_J:
        return ((pc + 4) & 0xF0000000) | ((word & 0x03FFFFFF) << 2)
    if opcode == OP_BEQ or opcode == OP_BNE:
        return pc + 4 + ((word & 0xFFFF) << 2 if not (word & 0x8000)
                         else ((word & 0xFFFF) - 0x10000) << 2)
    return None


# --- the image ------------------------------------------------------------
#
# The tables of the switches live in the data of the executable, and the
# mapping between a virtual address and the file is read from the program
# headers of the executable, never from a table of our own.  On the
# pinned target the code segment is at the file offset 0x74 and the data
# segment at 0x363B08, so a data address is ``file offset - 0x70`` and a
# code address ``file offset - 0x74``.

def _loadable_segments(data: bytes) -> list[tuple[int, int, int, int]]:
    """Return the (file offset, size, virtual address, flags) of the segments."""
    if data[:4] != b"\x7fELF":
        raise ValueError("not an ELF")
    header = struct.unpack_from("<HHIIIIIHHHHHH", data, 16)
    phoff, phentsize, phnum = header[4], header[8], header[9]
    segments: list[tuple[int, int, int, int]] = []
    for index in range(phnum):
        base = phoff + index * phentsize
        ptype, offset, vaddr, _paddr, filesz, _memsz, flags, _align = \
            struct.unpack_from("<IIIIIIII", data, base)
        if ptype == PT_LOAD and filesz:
            segments.append((offset, filesz, vaddr, flags))
    return segments


class Image:
    """The segments of the executable, and the words they hold."""

    def __init__(self, data: bytes) -> None:
        self.data = data
        self.segments = _loadable_segments(data)
        self.code = next((seg for seg in self.segments if seg[3] & PF_X), None)

    def segment_of(self, va: int) -> tuple[int, int, int, int] | None:
        for segment in self.segments:
            _offset, size, vaddr, _flags = segment
            if vaddr <= va < vaddr + size:
                return segment
        return None

    def word(self, va: int) -> int | None:
        """Return the word at a virtual address, if the image holds one."""
        segment = self.segment_of(va)
        if segment is None:
            return None
        offset, _size, vaddr, _flags = segment
        return struct.unpack_from("<I", self.data, offset + (va - vaddr))[0]

    def is_code(self, va: int) -> bool:
        """Return True for an address that can hold an instruction."""
        if self.code is None or va == REG_ZERO:
            return False
        _offset, size, vaddr, _flags = self.code
        return vaddr <= va < vaddr + size and (va - vaddr) % 4 == 0


# --- the resolver of the jump tables --------------------------------------
#
# The abstract value of a register.  The graph does not need the value of
# a register, only the *shape* of the address it computes:
#
#   None                       the value is unknown
#   ("const", v)               the value is the constant v
#   ("plus", r, k, at)         the value is the value of register r, plus
#                              k, an adjustment made at `at`
#   ("and", r, m)              the value is the value of register r, masked
#   ("scaled", b, s, r, k, at) the value is b + s * (the value of r, plus k)
#   ("mem", inner)             the value is the word at the address `inner`
#
# A jump table is the shape that matters: an address made of a constant
# base plus four times an index, read from a word.

def _v_add(value, delta):
    if value is None:
        return None
    kind = value[0]
    if kind == "const":
        return ("const", (value[1] + delta) & 0xFFFFFFFF)
    if kind == "plus":
        return ("plus", value[1], value[2] + delta, value[3])
    if kind == "scaled":
        return ("scaled", (value[1] + delta) & 0xFFFFFFFF,
                value[2], value[3], value[4], value[5])
    if kind == "mem":
        return ("mem", _v_add(value[1], delta))
    return None


def _v_scale(value, shift):
    """The value of a register shifted left by `shift`."""
    if value is None:
        return None
    kind = value[0]
    if kind == "const":
        return ("const", (value[1] << shift) & 0xFFFFFFFF)
    if kind == "plus":
        return ("scaled", 0, 1 << shift, value[1], value[2], value[3])
    if kind == "and":
        return ("scaled", 0, 1 << shift, value[1], 0, 0)
    if kind == "scaled":
        base, scale, reg, adj, at = value[1], value[2], value[3], value[4], value[5]
        if base % (1 << shift):
            return None
        return ("scaled", base << shift, scale << shift, reg, adj, at)
    return None


def _v_plus(left, right):
    if left is None or right is None:
        return None
    lkind, rkind = left[0], right[0]
    if lkind == "const" and rkind == "const":
        return ("const", (left[1] + right[1]) & 0xFFFFFFFF)
    if lkind == "const":
        return _v_plus(right, left)
    if rkind == "const":
        if lkind == "plus":
            return ("plus", left[1], left[2] + right[1], left[3])
        if lkind == "scaled":
            return ("scaled", (left[1] + right[1]) & 0xFFFFFFFF,
                    left[2], left[3], left[4], left[5])
        return None
    if lkind == "plus" and rkind == "plus":
        if left[1] == right[1]:
            return ("plus", left[1], left[2] + right[2], left[3])
        return None
    if lkind == "scaled" and rkind == "scaled":
        if left[3] == right[3] and left[2] == right[2] and left[4] == right[4]:
            return ("scaled", (left[1] + right[1]) & 0xFFFFFFFF,
                    left[2], left[3], left[4], left[5])
        return None
    return None


def _v_minus(left, right):
    if left is None or right is None:
        return None
    lkind, rkind = left[0], right[0]
    if lkind == "const" and rkind == "const":
        return ("const", (left[1] - right[1]) & 0xFFFFFFFF)
    if rkind == "const":
        if lkind == "plus":
            return ("plus", left[1], left[2] - right[1], left[3])
        if lkind == "scaled":
            return ("scaled", (left[1] - right[1]) & 0xFFFFFFFF,
                    left[2], left[3], left[4], left[5])
    return None


class Dispatch:
    """A table of targets the code computes, and jumps through."""

    __slots__ = ("address", "table", "cases", "count", "source")

    def __init__(self, address: int, table: int, cases: list[int],
                 count: int, source: str) -> None:
        self.address = address      # the address of the jump itself
        self.table = table          # the address of the table
        self.cases = cases          # the address of every case
        self.count = count          # the number of cases
        self.source = source        # where the count was read


class Resolver:
    """The jump tables the code computes.

    The resolver reads a ``jr`` and the few instructions before it, and
    tells whether the jump goes through a **table** it can name.  When it
    cannot, it says so, and the graph keeps the old behaviour: the path
    ends at the jump, and the body stays provisional.
    """

    def __init__(self, image: Image, segment: bytes, vaddr: int) -> None:
        self.image = image
        self.segment = segment
        self.vaddr = vaddr
        self.cache: dict[int, Dispatch | None] = {}
        self.found = 0        # the jumps through a register the graph met
        self.resolved = 0     # the tables the resolver read
        self._values: dict[tuple[str, int, int], object] = {}
        self._runs: dict[int, int] = {}

    # --- the decoding ----------------------------------------------------

    def _word(self, va: int) -> int:
        return struct.unpack_from("<I", self.segment, va - self.vaddr)[0]

    @staticmethod
    def _rs(word: int) -> int:
        return (word >> 21) & 0x1F

    @staticmethod
    def _rt(word: int) -> int:
        return (word >> 16) & 0x1F

    @staticmethod
    def _sa(word: int) -> int:
        return (word >> 6) & 0x1F

    @staticmethod
    def _imm(word: int) -> int:
        value = word & 0xFFFF
        return value - 0x10000 if value & 0x8000 else value

    @staticmethod
    def _dest(word: int) -> int | None:
        """Return the register the instruction writes, if it writes one."""
        opcode = word >> 26
        if opcode == 0:
            funct = word & 0x3F
            if funct in (0x00, 0x02, 0x03, 0x04, 0x06, 0x07, 0x10, 0x12,
                         0x20, 0x21, 0x22, 0x23, 0x24, 0x25, 0x26, 0x27,
                         0x2A, 0x2B):
                return (word >> 11) & 0x1F
            if funct == FUNCT_JALR:
                return (word >> 11) & 0x1F or REG_RA
            return None
        if opcode in (OP_ADDIU, OP_SLTI, OP_SLTIU, OP_ANDI, OP_ORI, OP_LUI,
                      OP_LW, 0x20, 0x24, 0x21, 0x25, 0x10):
            return (word >> 16) & 0x1F
        return None

    @staticmethod
    def _is_branch(word: int) -> bool:
        opcode = word >> 26
        if opcode in CONDITIONAL or opcode in REGIMM:
            return True
        if opcode == 0x11 and (word & 0x3F) in (0x08, 0x09, 0x0E, 0x0F):
            return True
        return False

    @staticmethod
    def _is_unconditional(word: int) -> bool:
        opcode = word >> 26
        if opcode == 0x08:
            return True
        if opcode in (0x04, 0x05) and ((word >> 21) & 0x1F) == 0 \
                and ((word >> 16) & 0x1F) == 0:
            return True
        if opcode == 0x01 and ((word >> 16) & 0x1F) == 0:
            return True
        if opcode == 0 and (word & 0x3F) == FUNCT_JR:
            return True
        return False

    @staticmethod
    def _is_call(word: int) -> bool:
        opcode = word >> 26
        if opcode == 0x0C:
            return True
        return opcode == 0 and (word & 0x3F) == FUNCT_JALR

    @staticmethod
    def _is_likely(word: int) -> bool:
        """Return True for a branch whose delay slot is nullified.

        The *likely* branches of the Allegrex do not execute their delay
        slot when the branch is not taken: the slot belongs to the path
        the branch takes.  The code of the pinned target says so: the
        dispatch of ``0x001D7E08`` reads the byte it just compared, and
        the delay slot of the branch before it would have overwritten it.
        """
        opcode = word >> 26
        if opcode in (0x14, 0x15, 0x16, 0x17):
            return True
        if opcode == 0x01 and ((word >> 16) & 0x1F) in (0x10, 0x11):
            return True
        return False

    # --- the value of a register ----------------------------------------

    def _value_after(self, va: int, reg: int, budget: int = RESOLVE_WINDOW):
        """The value of a register after the instruction at `va`."""
        if budget <= 0:
            return ("plus", reg, 0, 0)
        key = ("after", va, reg)
        if key in self._values:
            return self._values[key]
        self._values[key] = None
        if va < self.vaddr:
            self._values[key] = ("plus", reg, 0, 0)
            return self._values[key]
        if reg == REG_ZERO:
            self._values[key] = ("const", 0)
            return self._values[key]
        word = self._word(va)
        nullified = False
        if va - 4 >= self.vaddr:
            nullified = self._is_likely(self._word(va - 4))
        if self._dest(word) == reg and not nullified:
            value = self._eval(va, word, reg, budget)
        elif self._is_branch(word) or self._is_unconditional(word) \
                or self._is_call(word):
            # The value of the register past a transfer of the control is
            # the value the register holds there: the shape is kept, the
            # number is not known.
            value = ("plus", reg, 0, 0)
        else:
            value = self._value_after(va - 4, reg, budget - 1)
        self._values[key] = value
        return value

    def _source(self, va: int, reg: int, budget: int):
        """The value of a register as the instruction at `va` reads it."""
        if reg == REG_ZERO:
            return ("const", 0)
        return self._value_after(va - 4, reg, budget - 1)

    def _eval(self, va: int, word: int, reg: int, budget: int):
        opcode = word >> 26
        if opcode == 0:
            funct = word & 0x3F
            if funct == FUNCT_SLL:
                return _v_scale(self._source(va, self._rt(word), budget - 1),
                                self._sa(word))
            if funct == FUNCT_ADDU:
                return _v_plus(self._source(va, self._rs(word), budget - 1),
                               self._source(va, self._rt(word), budget - 1))
            if funct == FUNCT_SUBU:
                return _v_minus(self._source(va, self._rs(word), budget - 1),
                                self._source(va, self._rt(word), budget - 1))
            if funct == FUNCT_OR:
                left = self._source(va, self._rs(word), budget - 1)
                right = self._source(va, self._rt(word), budget - 1)
                if right is not None and right[0] == "const" and right[1] == 0:
                    return left
                if left is not None and left[0] == "const" and left[1] == 0:
                    return right
                return None
            return None
        if opcode == OP_LUI:
            return ("const", (word & 0xFFFF) << 16)
        if opcode == OP_ADDIU:
            base = self._source(va, self._rs(word), budget - 1)
            if base is None:
                return ("plus", self._rs(word), self._imm(word), va)
            if base[0] == "plus" and base[2] == 0:
                return ("plus", self._rs(word), self._imm(word), va)
            return _v_add(base, self._imm(word))
        if opcode == OP_ANDI:
            base = self._source(va, self._rs(word), budget - 1)
            if base is None or base[0] == "plus":
                return ("and", self._rs(word), word & 0xFFFF)
            if base[0] == "const":
                return ("const", base[1] & (word & 0xFFFF))
            return None
        if opcode == OP_ORI:
            base = self._source(va, self._rs(word), budget - 1)
            if base is not None and base[0] == "const":
                return ("const", base[1] | (word & 0xFFFF))
            return None
        if opcode == OP_LW:
            return ("mem", _v_add(self._source(va, self._rs(word), budget - 1),
                                  self._imm(word)))
        return None

    def _counts(self, va: int, reg: int, adj: int) -> list[tuple[int, str]]:
        """The candidate counts of the table, in the order the code gives them.

        The count of the cases is in the code, not in the data: the
        compiler masks the index with ``andi`` or checks it with
        ``sltiu`` before the table is read.  Two tables of a switch often
        sit next to each other in the data, so the data alone cannot say
        where a table ends.

        The index the compiler uses is the raw value plus the adjustment
        it made to it, so a check on the raw value gives the count of
        the cases once the adjustment is added back.  Several checks can
        guard the same index - the low bound and the high bound of a
        range - so the candidates are given in the order the code reads
        them, and the first one the data confirms is the one the graph
        uses.
        """
        candidates: list[tuple[int, str]] = []
        place = va
        for _ in range(BOUND_WINDOW):
            if place - 4 < self.vaddr:
                break
            word = self._word(place)
            opcode = word >> 26
            if opcode == OP_ANDI and self._rs(word) == reg:
                candidates.append(((word & 0xFFFF) + 1 + adj, "andi"))
            elif opcode == OP_SLTIU and self._rs(word) == reg:
                candidates.append(((word & 0xFFFF) + adj, "sltiu"))
            elif opcode == OP_SLTI and self._rs(word) == reg:
                candidates.append((self._imm(word) + adj, "slti"))
            if self._is_call(word) or self._is_unconditional(word):
                break
            place -= 4
        return candidates

    def _run(self, base: int) -> int:
        """The number of code addresses the table holds, at least.

        The data holds the cases of a table one after the other, and the
        table of the next switch may follow immediately: the run of the
        code addresses is therefore an upper bound of the count, and
        never the count itself.
        """
        if base in self._runs:
            return self._runs[base]
        count = 0
        while count < MAX_CASES:
            word = self.image.word(base + 4 * count)
            if word is None or not self.image.is_code(word):
                break
            count += 1
        self._runs[base] = count
        return count

    # --- the dispatch ----------------------------------------------------

    def dispatch(self, va: int) -> Dispatch | None:
        """The table the jump at `va` computes, if it computes one."""
        if va in self.cache:
            return self.cache[va]
        self.found += 1
        result = self._resolve(va)
        if result is not None:
            self.resolved += 1
        self.cache[va] = result
        return result

    def _resolve(self, va: int) -> Dispatch | None:
        word = self._word(va)
        if (word & 0xFC000000) != OP_SPECIAL or (word & 0x3F) != FUNCT_JR:
            return None
        reg = self._rs(word)
        if reg in (REG_RA, REG_T9, REG_ZERO):
            return None
        value = self._value_after(va - 4, reg)
        if value is None or value[0] != "mem":
            return None
        inner = value[1]
        if inner is None or inner[0] != "scaled":
            return None
        base, scale, index, adj, _at = (inner[1], inner[2], inner[3],
                                        inner[4], inner[5])
        if scale != 4:
            # A table of words is indexed by four.
            return None
        candidates = self._counts(va - 4, index, adj)
        if not candidates:
            # No range check: the number of cases cannot be measured, and
            # the body stays provisional rather than guessed.
            return None
        run = self._run(base)
        for count, source in candidates:
            if not 1 <= count <= MAX_CASES or count > run:
                continue
            cases: list[int] = []
            for step in range(count):
                target = self.image.word(base + 4 * step)
                if target is None or not self.image.is_code(target):
                    # The table does not hold the address of a case: the
                    # reading is wrong, and the body stays provisional.
                    cases = []
                    break
                cases.append(target)
            if not cases:
                continue
            return Dispatch(va, base, cases, count, source)
        return None


def body_reachable(segment: bytes, start_index: int, limit_index: int,
                   resolver: Resolver | None = None,
                   vaddr: int = 0) -> tuple[set[int], int]:
    """Return the instructions a body reaches, and no other.

    This is the control-flow graph of the body, and it is what the review
    of wave 1 measured as the rule of the end:

        the body ends at the last instruction the graph reaches, plus four.

    Four rules make the graph right, and each of them was bought by a
    review:

    * the **delay slot** of a branch or a jump is executed.  The successor
      of a branch is at ``pc + 8``, not at ``pc + 4``.
    * a **call** does not transfer the control: the body continues after
      it, and the callee is not part of the body.
    * a **return** ends the path, and its delay slot is the last
      instruction of the body.
    * a **jump through a register** ends the path, unless the code
      computes a **table** of targets: then the cases of the table are
      part of the body, and the ones that fall outside it are counted and
      reported, never swallowed.
    """
    reachable: set[int] = set()
    outside = 0
    pending = [start_index]
    while pending:
        index = pending.pop()
        if index in reachable:
            continue
        if index < 0 or index + 4 > limit_index:
            continue
        reachable.add(index)
        word = struct.unpack_from("<I", segment, index)[0]

        if _is_return(word):
            # The delay slot of the return is executed, and then the
            # control leaves the body.
            if index + 8 <= limit_index:
                reachable.add(index + 4)
            continue

        if _is_call(word):
            # The delay slot is executed, and the body continues after
            # the call.  The callee is another body.
            if index + 8 <= limit_index:
                reachable.add(index + 4)
                pending.append(index + 8)
            continue

        if _is_conditional(word):
            # The delay slot is executed, and either branch is possible.
            if index + 8 <= limit_index:
                reachable.add(index + 4)
                pending.append(index + 8)
            target = _branch_target(word, index)
            if target is not None:
                pending.append(target)
            continue

        if _is_jump(word):
            # The delay slot is executed, and the control leaves.
            if index + 8 <= limit_index:
                reachable.add(index + 4)
            target = _branch_target(word, index)
            if target is not None:
                pending.append(target)
                continue
            # A jump through a register.  The code may compute the
            # address of a table and jump through what it reads there:
            # then the cases are part of the body.
            if resolver is None:
                continue
            dispatch = resolver.dispatch(vaddr + index)
            if dispatch is None:
                continue
            for case in dispatch.cases:
                case_index = case - vaddr
                if start_index <= case_index < limit_index:
                    pending.append(case_index)
                else:
                    # The table holds an address outside the body: the
                    # body is not what we think it is.  It is counted and
                    # reported, and the next function is not swallowed.
                    outside += 1
            continue

        pending.append(index + 4)
    return reachable, outside


def analyse(data: bytes) -> tuple[list[dict[str, object]],
                                  list[dict[str, object]], int,
                                  dict[str, int]]:
    """Return the call graph and the bounded candidates of the executable."""
    ranges = function_inventory.executable_ranges(data)
    if not ranges:
        raise ValueError("the executable has no executable segment")

    offset, size, vaddr = ranges[0]
    segment = data[offset:offset + size]
    image = Image(data)
    resolver = Resolver(image, segment, vaddr)

    # --- the call graph -------------------------------------------------
    call_sites: dict[int, int] = defaultdict(int)
    branch_targets: set[int] = set()
    returns: set[int] = set()
    virtual_calls = 0

    for index in range(0, max(0, len(segment) - 4), 4):
        word = _insn(segment, index)
        pc = vaddr + index
        if (word & 0xFC000000) == OP_JAL:
            target = _branch_target(word, pc)
            if target is not None:
                call_sites[target] += 1
        elif (word & 0xFC000000) == OP_SPECIAL and (word & 0x3F) == FUNCT_JALR:
            # A call through a register: a virtual call.  Its target is
            # not known statically, but the count says how much of the
            # code is reached that way.
            virtual_calls += 1
        elif (word & 0xFC000000) in (OP_J, OP_BEQ, OP_BNE):
            target = _branch_target(word, pc)
            if target is not None:
                branch_targets.add(target)
        if (word & 0xFC000000) == OP_SPECIAL and (word & 0x3F) == FUNCT_JR:
            register = (word >> 21) & 0x1F
            if register in (REG_RA, REG_T9):
                returns.add(index)

    # --- the function starts ---------------------------------------------
    # A **strong** start is a call target or a place that opens a frame.
    # Both of them begin a body, and a body runs from there to its last
    # return before the next strong start.
    #
    # A place that merely *follows* a return is a **weak** signal: a body
    # can have two epilogues, or a cold path after its epilogue, and the
    # instruction after a return is then still inside the body. Using it
    # as a start cuts those bodies at their first return, which is wrong.
    # It is kept as evidence, not as a boundary.
    after_return: set[int] = set()
    for index in sorted(returns):
        following = index + 8
        if following + 4 <= len(segment):
            after_return.add(following)

    frame_openers = set()
    for row in function_inventory.inventory(data):
        frame_openers.add(int(str(row["file_offset"]), 16) - offset)

    evidence: dict[int, set[str]] = defaultdict(set)
    strong: set[int] = set()
    for target in call_sites:
        evidence[target].add("call")
        strong.add(target)
    for index in after_return:
        evidence[vaddr + index].add("after_return")
    for index in frame_openers:
        evidence[vaddr + index].add("frame")
        strong.add(vaddr + index)

    # --- the bodies ------------------------------------------------------
    # The body of a function is the set of instructions its control-flow
    # graph reaches.  A call target is never part of it: a call does not
    # transfer the control.  The bound is the last instruction the graph
    # reaches, plus four - the rule the review of wave 1 measured.
    ordered = sorted(strong)
    bodies: list[dict[str, object]] = []
    outside_cases = 0
    bodies_outside = 0
    bodies_with_table = 0
    for position, start in enumerate(ordered):
        start_index = start - vaddr
        if start_index < 0 or start_index >= len(segment):
            continue
        # The graph is bounded by the next strong start.  A strong start
        # inside the body is a call target, which the graph does not
        # follow, so the bound holds; if the graph does reach it, the body
        # has no return, and the bound moves on.
        limit_index = len(segment)
        reachable: set[int] = set()
        outside = 0
        for attempt in range(4):
            if position + attempt + 1 < len(ordered):
                candidate = ordered[position + attempt + 1] - vaddr
            else:
                candidate = len(segment)
            reachable, outside = body_reachable(segment, start_index, candidate,
                                                resolver, vaddr)
            limit_index = candidate
            if candidate >= len(segment) or candidate not in reachable:
                break
        if not reachable:
            continue
        end_index = min(max(reachable) + 4, len(segment))
        if end_index <= start_index:
            continue
        if outside:
            outside_cases += outside
            bodies_outside += 1
        evidence_here = evidence.get(start, set())
        bodies.append({
            "start": start,
            "end": vaddr + end_index,
            "size": end_index - start_index,
            "bound_source": ("call" if "call" in evidence_here else
                             "after_return" if "after_return" in evidence_here
                             else "frame"),
            "evidence": ",".join(sorted(evidence_here)),
            "calls": call_sites.get(start, 0),
            "returns": sum(1 for index in returns
                           if start_index <= index < end_index),
        })

    calls = [
        {"address": target, "sites": count}
        for target, count in sorted(call_sites.items(), key=lambda kv: -kv[1])
    ]
    stats = {
        "computed_jumps": resolver.found,
        "tables_resolved": resolver.resolved,
        "cases_outside": outside_cases,
        "bodies_outside": bodies_outside,
    }
    return calls, bodies, virtual_calls, stats


def write_calls(path: Path, calls: list[dict[str, object]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle, delimiter="\t", lineterminator="\n")
        writer.writerow(["target", "sites"])
        for row in calls:
            writer.writerow([f"0x{int(row['address']):08X}", row["sites"]])


def write_bounds(path: Path, bodies: list[dict[str, object]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle, delimiter="\t", lineterminator="\n")
        writer.writerow(["start", "end", "size", "bound_source", "evidence",
                         "calls", "returns"])
        for row in bodies:
            writer.writerow([f"0x{int(row['start']):08X}",
                             f"0x{int(row['end']):08X}",
                             row["size"], row["bound_source"], row["evidence"],
                             row["calls"], row["returns"]])


#: The size buckets, so that a wave spans several body sizes instead of
#: filling up with stubs.
BUCKETS = [(16, 64), (64, 128), (128, 256), (256, 512), (512, 1024),
           (1024, 4096)]


def pick_stratified(rows: list[dict[str, object]], take: int) -> list[dict[str, object]]:
    """Round-robin over the size buckets, so a wave is not all stubs."""
    buckets = [[row for row in rows if low <= int(row["size"]) < high]
               for low, high in BUCKETS]
    chosen: list[dict[str, object]] = []
    cursors = [0] * len(buckets)
    while len(chosen) < take:
        progressed = False
        for index, bucket in enumerate(buckets):
            if len(chosen) >= take:
                break
            if cursors[index] < len(bucket):
                chosen.append(bucket[cursors[index]])
                cursors[index] += 1
                progressed = True
        if not progressed:
            break
    return sorted(chosen, key=lambda row: int(row["start"]))


def main(argv: list[str] | None = None) -> int:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--elf", type=Path, required=True)
    parser.add_argument("--work", type=Path, default=Path("work"))
    parser.add_argument("--lots", type=int, default=6)
    parser.add_argument("--per-lot", type=int, default=40)
    parser.add_argument("--skip", type=int, default=0,
                        help="skip the first N shortlist entries, to cut the "
                             "lots of the next wave without re-cutting the "
                             "ones already reviewed")
    parser.add_argument("--first-lot", type=int, default=1,
                        help="the number of the first lot to write")
    parser.add_argument("--exclude", type=Path, nargs="*", default=None,
                        help="layout tables of the lots already cut: their "
                             "targets are left out of the new ones, so that "
                             "two waves never review the same body")
    args = parser.parse_args(argv)

    data = args.elf.read_bytes()
    calls, bodies, virtual_calls, stats = analyse(data)

    write_calls(args.work / "E0" / "calls.tsv", calls)
    write_bounds(args.work / "E0" / "bounds.tsv", bodies)

    # The shortlist: the bounded candidates that a call reaches, ranked by
    # leverage, then stratified by size.
    eligible = [row for row in bodies if int(row["calls"]) > 0]
    eligible.sort(key=lambda row: (-int(row["calls"]), -int(row["size"])))

    # The bodies a previous wave already reviewed are left out.
    excluded: set[str] = set()
    for path in (args.exclude or []):
        if not path.is_file():
            continue
        with path.open(encoding="utf-8", newline="") as handle:
            for row in csv.DictReader(handle, delimiter="\t"):
                if row.get("start"):
                    excluded.add(row["start"])
    if excluded:
        eligible = [row for row in eligible
                    if f"0x{int(row['start']):08X}" not in excluded]

    shortlist = pick_stratified(eligible, args.skip + args.lots * args.per_lot)
    shortlist = shortlist[args.skip:]

    lots_dir = args.work / "lots"
    lots_dir.mkdir(parents=True, exist_ok=True)
    for index in range(args.lots):
        chunk = shortlist[index * args.per_lot:(index + 1) * args.per_lot]
        path = lots_dir / f"L{args.first_lot + index:02d}.tsv"
        with path.open("w", encoding="utf-8", newline="") as handle:
            writer = csv.writer(handle, delimiter="\t", lineterminator="\n")
            writer.writerow(["start", "end", "size", "bound_source", "evidence",
                             "calls", "returns"])
            for row in chunk:
                writer.writerow([f"0x{int(row['start']):08X}",
                                 f"0x{int(row['end']):08X}",
                                 row["size"], row["bound_source"], row["evidence"],
                                 row["calls"], row["returns"]])
        print(f"{path.name}: {len(chunk)} targets")

    print(f"call targets      : {len(calls)}")
    print(f"virtual calls     : {virtual_calls}")
    print(f"bounded candidates: {len(bodies)}")
    print(f"called candidates : {len(eligible)}")
    print(f"shortlist         : {len(shortlist)}")
    print(f"computed jumps    : {stats['computed_jumps']}")
    print(f"tables resolved   : {stats['tables_resolved']}")
    print(f"cases outside     : {stats['cases_outside']}")
    print(f"bodies outside    : {stats['bodies_outside']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
