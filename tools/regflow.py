#!/usr/bin/env python3
"""Track the values of the registers over a straight run of instructions.

The retail code of the target is not position independent: an address is
built in two steps, a ``lui`` that loads the high half and an ``addiu``, an
``ori`` or a ``lw`` that completes it.  Recovering the addresses a body
touches is therefore a small dataflow problem — and it goes wrong if the
``lui`` is not **killed** when its register is written again.

The first version of the resolver paired a ``lui`` with whatever came
later, and read the string ``Korean`` at an address that had nothing to do
with the body.  A register that is written is dead: this module kills it.

The module reports **structure**: the set of registers an instruction
writes, and the absolute addresses a body builds.  It never reports an
instruction byte.
"""

from __future__ import annotations

import struct
from typing import Iterable

#: The SPECIAL opcodes that write nothing.
SPECIAL_NO_WRITE = {
    0x00,  # sll
    0x08,  # jr
    0x0C,  # syscall
    0x0D,  # break
    0x0F,  # sync
    0x11,  # mthi
    0x13,  # mtlo
    0x18,  # mult
    0x19,  # multu
    0x1A,  # div
    0x1B,  # divu
}

#: The SPECIAL opcodes that write $ra as well.
SPECIAL_WRITES_RA = {0x09}   # jalr

#: The main opcodes that write $rt.
LOAD_OPCODES = {0x20, 0x21, 0x22, 0x23, 0x24, 0x25, 0x26}

#: The main opcodes that write nothing.
STORE_OPCODES = {0x28, 0x29, 0x2A, 0x2B, 0x2C, 0x2E}

#: The main opcodes of the branches, including the *likely* ones.
#:
#: 0x01 is the REGIMM family (bltz, bgez, and their likely forms), 0x04 to
#: 0x09 are beq, bne, blez, bgtz, j and jal, and 0x14 to 0x17 are beql,
#: bnel, blezl and bgtzl.  The likely branches execute their delay slot
#: whatever the condition is, and a control-flow graph that does not know
#: about them makes 112 bodies look broken.
BRANCH_OPCODES = {0x01, 0x04, 0x05, 0x06, 0x07, 0x08, 0x09,
                  0x14, 0x15, 0x16, 0x17}


def _rs(word: int) -> int:
    return (word >> 21) & 0x1F


def _rt(word: int) -> int:
    return (word >> 16) & 0x1F


def _rd(word: int) -> int:
    return (word >> 11) & 0x1F


def _opcode(word: int) -> int:
    return word & 0xFC000000


def written_registers(word: int) -> set[int]:
    """Return the registers an instruction may write.

    The answer is conservative: when the encoding is not one the module
    knows, it assumes the destination register is written, because a
    register wrongly killed costs a name, while a register wrongly kept
    costs a false one.
    """
    opcode = word & 0xFC000000
    if opcode == 0x00000000:                 # SPECIAL
        funct = word & 0x3F
        if funct in SPECIAL_NO_WRITE:
            if funct == 0x00:                # sll writes rd
                return {_rd(word)}
            return set()
        if funct in SPECIAL_WRITES_RA:
            return {_rd(word), 31}
        return {_rd(word)}
    if opcode >> 26 in LOAD_OPCODES:
        return {_rt(word)}
    if opcode >> 26 in STORE_OPCODES:
        return set()
    if opcode >> 26 in BRANCH_OPCODES:
        if opcode >> 26 == 0x09:             # jal
            return {31}
        return set()
    if opcode >> 26 == 0x0C:                 # jal target
        return {31}
    if opcode >> 26 == 0x0D:                 # jalr
        return {31, _rd(word)}
    if opcode >> 26 == 0x0F:                 # lui
        return {_rt(word)}
    if opcode >> 26 == 0x10:                 # cop0
        return {_rt(word)}
    if opcode >> 26 == 0x11:                 # cop1
        return {_rt(word)}
    if opcode >> 26 == 0x13:                 # SPECIAL2
        return {_rd(word)}
    return {_rd(word)}


class AddressFlow:
    """Follow the absolute addresses a straight run of instructions builds.

    The flow keeps, for each register, the high half of an address that was
    loaded into it.  A register that is written is killed, so a ``lui`` that
    has been superseded never pairs with a later completion.
    """

    def __init__(self) -> None:
        self._high: dict[int, int] = {}

    def kill(self, registers: Iterable[int]) -> None:
        for register in registers:
            self._high.pop(register, None)

    def step(self, word: int) -> None:
        """Feed one instruction to the flow."""
        opcode = _opcode(word)
        self.kill(written_registers(word))
        if opcode == 0x3C000000:              # lui rt, imm
            self._high[_rt(word)] = (word & 0xFFFF) << 16

    def high_of(self, register: int) -> int | None:
        """Return the high half held by a register, if it holds one."""
        return self._high.get(register)


def _signed16(value: int) -> int:
    """Return a 16-bit immediate, sign extended.

    The immediate of ``addiu`` is signed: ``addiu $a3, $a3, -0xca8`` adds
    negative 0xca8, not positive 0xff58.  Completing an address with the
    unsigned value puts it in the wrong page, and the string that is read
    there is a different one.
    """
    return value - 0x10000 if value & 0x8000 else value


def addresses(segment: bytes, start: int, end: int,
              load_word) -> list[int]:
    """Return the absolute addresses the body builds.

    ``load_word`` is called with an absolute address and returns the 32-bit
    word stored there, or ``None`` when the address is not readable.  It is
    what turns a load of a pointer into the pointer.
    """
    flow = AddressFlow()
    found: list[int] = []
    for offset in range(start, end - 3, 4):
        word = struct.unpack_from("<I", segment, offset)[0]
        flow.step(word)
        opcode = _opcode(word)
        if opcode == 0x24000000:              # addiu rt, rs, imm
            high = flow.high_of(_rs(word))
            if high is not None:
                found.append((high + _signed16(word & 0xFFFF)) & 0xFFFFFFFF)
        elif opcode == 0x34000000:            # ori rt, rs, imm
            high = flow.high_of(_rs(word))
            if high is not None:
                found.append((high | (word & 0xFFFF)) & 0xFFFFFFFF)
        elif opcode == 0x8C000000:            # lw rt, off(rs)
            high = flow.high_of(_rs(word))
            if high is not None:
                slot = (high + _signed16(word & 0xFFFF)) & 0xFFFFFFFF
                value = load_word(slot)
                if value is not None:
                    found.append(value)
    return found
