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

### The rule of the end, once the wave was over

Lot L07 measured the rule that reproduces **every** bound of wave 1 and
every correction of lot L06:

> **`end` is the last instruction reachable from `start` in the
> control-flow graph, plus four.**

Not the first return, and not the return of the epilogue. Two cases make
the difference, and both were found in the wave:

* a body with **two epilogues** — `0x0024F8BC`, `0x0024FC90`,
  `0x00266FF0`: the second return is the one that ends the body;
* a body with a **cold path after its epilogue** — `0x00258524` runs a
  64-bit multiplication to `0x258898`, well past the return at
  `0x2585F4`.

And the converse, which is the negative control of lot L07: a block that
the graph **does not** reach is not part of the body, even when it sits
between the body and the next one. `0x000DE350` is 28 bytes of epilogue
that no branch of the binary reaches and whose address appears nowhere in
the file; the body of `0x000DDFF8` ends before it.

> **A body ends where the graph ends, not where a return is.**

### A function is not always called

A function can be reached only through a **pointer**: a virtual method
table, or a table of data. `0x000EF2C8` has **no** call site at all, and
is referenced from `.data` — the sweep never proposed it, and a review that
trusted the sweep alone would have missed it.

The virtual method tables sit in `.rodata` as pairs of a **pointer and a
zero**, and a body address found in one of them corroborates the function.

---

## 2. The traps

All were found by the wave, and all would have produced a wrong answer if
the review had not been done.

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

### A third trap, found by lot L07: the registers have to be followed

To resolve what a body *reads*, the registers have to be followed, not
guessed. The first resolver paired a `lui` with whatever came later, and
made a body read `Korean`: the `lui` had been superseded by a write to
its register, and the high half it held was dead.

`tools/regflow.py` kills a register when an instruction writes it, and the
string resolver uses it. The false positive is gone, and the true count
went **up**: 28 bodies and 132 references, against 24 and 124 before —
the flow now continues past the interference instead of being thrown off
by it.

The same rule applies to the assert resolver, where the argument of the
helper is built the same way.

---

## 3. The false-positive class, and the error of the sweep

The sweep produces bounded candidates from three kinds of evidence:

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

### The error the wave found in the sweep itself

The sweep is a heuristic, and the review measured it. Two of its errors
are now known:

**The first return is not the last return.** The sweep originally closed a
body at the return that came *before* the next start, and it treated the
instruction after a return as a start. A body with **two epilogues** was
therefore cut at its first one. Lot L06 found six such bodies — among them
`0x0024F8BC`, `0x0024FC90` and `0x00266FF0`, each with a second return.
The sweep now closes a body at its last return before the next **strong**
start, where a strong start is a call target or a frame opening; the
instruction after a return is kept as evidence, not as a boundary. That
removes the error, and it removes 1 827 candidates of the suspect class
from the sweep as well.

**A cold path after the epilogue is still the body.** The sweep is a
linear sweep, and it cannot see that a block placed *after* the epilogue
is still reachable from the body: `0x00258524` runs a 64-bit
multiplication to `0x258898`, well past the return at `0x2585F4`, and
`0x00258BA4` returns through a jump to `0x258BFC`. Those bounds need the
control-flow graph, not a linear pass.

> **The sweep proposes; the review proves.** The residual error rate is
> the price of the method, and it is measured and published rather than
> hidden: `config/boot/layout_summary.json` reports how many reviewed
> bounds the sweep got right.

The bounds that the review corrected are the ones the next wave's sweep
has to get right from the start, so the sweep was fixed and the lots of
the next wave — L07 to L12 — were cut with the corrected rule.

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

The executable is stripped, so the names have to be earned. Five sources
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
4. **The engine's own assert mechanism.** The helper at `0x7035C` takes
   the name of the enclosing function in `$a3` — the C `__FUNCTION__` —
   and the target has **344** call sites of it. This is the largest
   naming source there is: the code is telling us its own names. The
   argument is built by a `lui` before the call and an `addiu` **in the
   delay slot of the call**, and the identifiers live in a string pool
   that starts at `0x00340000`. `tools/assert_names.py` resolves the
   direct form of that pattern; the rest is an open item.
5. **The sibling projects.** `OpenRAC/rac-sac-decomp` has already named
   137 bodies of a Ratchet & Clank title. On the two hundred and forty
   targets of wave 1, **none** of them matched, and lot L01 established
   why: the catalogue is of a different build, of a different engine
   generation. It is a source of *hypotheses*, not of proof, and it has
   to be checked against this target.

The names found in wave 1:

| Address | Name | Confidence |
| --- | --- | --- |
| `0x00070A04` | `memcpy` | high |
| `0x0007044C` | `Aurora_GetErrorMessage` | high |
| `0x0008DFB8` | `mt19937_genrand` | high |
| `0x00245504` | `strcmp` | high |
| `0x0005D884` | `CNodeXD_CFileCm` | medium |
| `0x00097A34` | `CFile_ResolvePath` | medium |
| `0x000981C0` | `CFile_GetPath` | medium |
| `0x00099010` | `CFile_Close` | medium |
| `0x0013C1C4` | `timeline_update` | medium |
| `0x00168028` | `format_indexed_name` | medium |
| `0x001995A0` | `vehicle_mount_update` | medium |
| `0x00199B54` | `vehicle_motion_update` | medium |
| `0x001A06C8` | `enemy_ai_update` | medium |
| `0x0024F8BC` | `Math_RegisterAcosf` | medium |
| `0x0024FC90` | `Math_RegisterFmodf` | medium |

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
