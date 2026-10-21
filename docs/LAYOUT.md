# The layout of the code

The **assembly baseline** of the project: what a function of the target
looks like, and how a body is bounded.

The executable is stripped, so none of this could be read off the binary.
It was established by the review of **wave 1** — six lots of forty targets
each — and it is what the next waves build on.

The numbers below are the review's; the method is the sibling OpenRAC
projects'.

---

## 1. What a body is

> A body runs from its entry point to its **single return**, plus the
> return's delay slot.

| Property | Measurement |
| --- | --- |
| returns per body | exactly one |
| the return | `jr $ra` at `end - 8` |
| the delay slot | at `end - 4` |
| the previous body's return | at `start - 8` |
| the next body | starts exactly at `end` |

`jr $t9` was looked for and **not found**: the target returns through
`$ra`.

Two returns inside one range mean **two bodies welded together**, not one
body with two exits. That is what the sweep's rule of "the last return
before the next start" is for.

### The three proofs a bound must satisfy

Every lot applied the same three checks, and a target is a function only
when all three hold:

1. the body **starts** at `start` — a frame opening
   `addiu $sp, $sp, -N`, or the first instruction of a leaf;
2. the body **ends** at `end` — the single return at `end - 8` with its
   delay slot at `end - 4`, and **nothing reachable from `end`** belongs to
   the body;
3. the bound is **tight** — the word at `start - 4` is the delay slot of
   the previous body's return, and no branch enters or leaves the body
   other than through a call.

The third check is the one that separates a function from a fragment, and
it is the one that needs the control-flow graph.

---

## 2. The two traps

Both were found by the wave, and both would have produced a wrong answer
if the review had not been done.

### The delay slot must be absorbed

The control-flow graph has to treat the instruction after a `jal` or a `j`
as the successor of the **delay slot**, at `pc + 8`, not at `pc + 4`.
A graph that does not absorb it breaks every body that contains a call,
and the bound is then wrong on both sides.

### The return address is not saved first

The frame is opened, then the callee-saved registers are pushed, and only
then is the return address saved. The measured distance between the frame
and the save of `$ra` goes from **1 to 15 instructions**, with a mode at 1:

| distance | 1 | 2 | 3 | 4 | 5 | 6 | 7 | 8 | 9 | 10 | 11 | 12 | 13 | 14 | 15 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| bodies | 4322 | 835 | 1469 | 2169 | 664 | 878 | 596 | 371 | 490 | 471 | 393 | 273 | 265 | 177 | 122 |

A scan that looks five instructions ahead misses 4 700 of the 14 655
candidates. The inventory now looks sixteen.

---

## 3. The false-positive class

The sweep produces 20 889 candidates from three kinds of evidence:

| Evidence | Bodies | What it is |
| --- | --- | --- |
| `after_return,frame` | 7 576 | a frame right after a return: a function, reached by something other than a call |
| `after_return,call,frame` | 7 020 | a function, called and framed |
| `after_return,call` | 4 391 | a leaf function, called, without a frame |
| `after_return` | **1 827** | **the suspect class** |
| `frame` | 34 | a frame that nothing reaches |
| `call,frame` | 25 | a function called in one place |
| `call` | 16 | a leaf called in one place |

The **1 827** candidates of the `after_return` class are neither called
nor do they open a frame. The negative control of lot L04 is one of them:
`0x0024243C`, eight bytes, reached by a single conditional branch, no call
site, no frame — a **return path**, not a function.

> **The `after_return` evidence alone does not make a function.**

That is the one lesson the wave had to buy, and it is what the 1 827
candidates of that class are worth.

---

## 4. The mapping of the file

| Segment | Virtual address | File offset |
| --- | --- | --- |
| `PT_LOAD[0]`, the code | `0x00000000` | `+ 0x74` |
| `PT_LOAD[1]`, the data | `0x00363A98` | `+ 0x70` |

The code segment runs to virtual address `0x00363A94`.

The strings live in `.sdata` and `.rodata`, from `0x0032F268` to
`0x00335F0B0`. `.data`, from `0x00363A98` to `0x003AE11C`, holds **no
printable string of four characters or more**.

---

## 5. What the code is made of

| Property | Measurement |
| --- | --- |
| instructions | 888 485 |
| stack slots | 16 bytes wide: 93 of the 93 frame sizes are multiples of 16 |
| the return address | on top of the frame, at `frame_size - 4` |
| position independence | **none**: no `lui $gp`, no `addiu $gp`, no load from `$gp` |
| equality | the GCC debug-C idiom `sltiu rX,rX,1` is **absent** |
| the engine | SCREAM, the Ratchet & Clank engine of the studio |
| the object layer | Aurora |

The absence of `$gp` means every global is reached through an absolute
address, built in two steps (`lui` then `addiu`/`ori`/`lw`). The module is
linked at a fixed address and `.text` starts at `0x00000000`.

The absence of the debug-C idiom is a **measured difference** between this
build and the PlayStation 2 Ratchet & Clank boot build, which the sibling
projects found to carry it. Two builds of the same engine, two compiler
configurations: that is what the toolchain phase has to explain.

---

## 6. Where the names come from

The executable is stripped, so the names have to be earned. Four sources
produced names in the first wave:

1. **The strings the body references.** 438 functions of the binary
   reference an engine assert string — `CFile::Open(%s)` and its
   relatives. The module `libs\core\cfile.cpp` gives the class `CFile` its
   name.
2. **The library tables.** The virtual method tables sit in `.rodata` as
   pairs of a pointer and a zero; a body address found there corroborates
   the function.
3. **The well-known algorithms.** A body that twists 227 and 623 elements
   over a state of 624 words, with the constants `0x9908B0DF`,
   `0x9D2C5680` and `0xEFC60000`, is `mt19937_genrand` and nothing else.
4. **The sibling projects.** `OpenRAC/rac-sac-decomp` has already named
   137 bodies of the **same engine on the same processor**. On the
   hundred and sixty targets of wave 1, **none** of them matched: the
   catalogue is a source of *hypotheses*, not of proof, and it has to be
   checked against this target.

The names found in wave 1:

| Address | Name | Confidence |
| --- | --- | --- |
| `0x0007044C` | `Aurora_GetErrorMessage` | high |
| `0x00070A04` | `memcpy` | high |
| `0x0008DFB8` | `mt19937_genrand` | high |
| `0x0005D884` | `CNodeXD_CFileCm` | medium |
| `0x00097A34` | `CFile_ResolvePath` | medium |
| `0x000981C0` | `CFile_GetPath` | medium |
| `0x00099010` | `CFile_Close` | medium |
| `0x0013C1C4` | `timeline_update` | medium |
| `0x00168028` | `format_indexed_name` | medium |
| `0x001995A0` | `vehicle_mount_update` | medium |
| `0x00199B54` | `vehicle_motion_update` | medium |
| `0x001A06C8` | `enemy_ai_update` | medium |

Everything else kept `func_<address>`. That is not a failure: it is the
answer the evidence gives.

---

## 7. A note on the disassembler

Capstone does not decode every encoding the Allegrex uses — the FPU
instructions in particular. The controls of the wave were therefore made
on the **raw 32-bit words**, not on a disassembly. This is not a detail:
a body boundary is a claim about words.

---

## 8. See also

* `docs/METHOD.md` — the wave protocol.
* `docs/EVIDENCE.md` — what counts as a proof.
* `docs/GATES.md` — the gates, and where this layout stands.
* `config/boot/layout.tsv` — the reviewed layout of the wave.
* `config/boot/idioms.json` — the measurements of §5.
