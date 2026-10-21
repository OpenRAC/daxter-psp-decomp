# WAVE 3 — the toolchain, the last error class, and more layout (ROOT, 2026-10-21)

> Anchor of the wave. General state: `docs/STATE.md`. Start of the wave:
> `main` = `72c48cb`.

## Start

Already established, with its exact numbers:

* the disc is pinned; the `~PSP` executable is decrypted and measured; it
  is a **stripped PSP PRX** with 3 335 156 bytes of `.text`;
* **421 bodies** reviewed, 421 confirmed as functions, **48 named**; the
  sweep agrees with the review on **99,1 %** of them;
* the call graph holds 11 497 call targets and **6 070 virtual calls**;
* the toolchain is **measured**, not guessed: the retail prologue puts the
  saved `$ra` 1 to 4 slots below the top of the frame, 13 494 of 13 495
  frames are a multiple of 16, and the retail `strcmp` is the newlib 1.15
  *size* variant.

What is open, and what the queue of this wave comes from:

1. **H1 is untested.** The standing hypothesis is that the retail build is
   a **GCC of the 3.x line**, Allegrex target, not in the debug-C mode,
   with the library compiled for size. Three candidates were built and
   measured, and all three differ; the GCC 3.3 Allegrex was not obtained,
   because the community port does not carry the Allegrex machine
   description in an applicable form.
2. **The last error class of the sweep.** The four bodies the
   control-flow graph still gets wrong end at a **computed jump** through
   a register, whose targets are in a table the graph does not read.
3. **The rest of the layout.** 421 of the 11 452 called candidates have
   been reviewed.

## The lots of the wave

| lot | targets | kind |
|---|---|---|
| L15 … L20 | 40 each | layout review, 240 targets |
| H1 | — | the decisive test of the hypothesis |
| JUMP | — | the computed jumps of the control-flow graph |

Brief of the layout lots: `work/templates/BRIEF-COMMUN-2.md`, with the
addendum of this wave below. Lists: `work/lots/L*.tsv`. Report:
`work/templates/RAPPORT.md`.

## The addendum to the brief of the layout lots

The wave 2 lessons are in `BRIEF-COMMUN-2.md`. Three more, from wave 2
itself:

* the **delay slot of a jump** is executed without falling back, and a
  `jalr` is a **continuation** at `pc + 8`, not an exit;
* a `jr $ra` that the **data segment** references is a separate function
  — an entry of a virtual method table — and not the end of the body;
* an epilogue can be a **tail call** (`jr $a1`): the test "the word at
  `start - 4` is a `jr $ra`" has to accept it.

And the one rule that is now the rule:

> **`end` is the last instruction the control-flow graph reaches, plus
> four.**

## H1 — the decisive test

The lot is `work/TOOLCHAIN/`. The toolchain it measured is in
`work/TOOLCHAIN/shape.tsv`, and the recipe for the candidate that could
not be built is in `work/TOOLCHAIN/scratch/legacy33/RECIPE.md`.

**The idea that makes it cheap.** The retail prologue rule is a difference
of **compiler version**, not of ABI: the probe `ee-gcc 2.95.2` — a stock
PlayStation 2 configuration, 64-bit registers, o32 ABI — reproduces the
retail rule, and the modern Allegrex compilers do not. The PSP is a
64-bit-MIPS part with the o32 ABI, the same shape as the PS2 EE. So the
question *"does the 3.x line produce the retail prologue rule?"* can be
asked on a **stock 64-bit-MIPS o32 target**, which GCC 3.3 supports
natively, and does not need the Allegrex machine description at all.

The lot is to:

1. build a **GCC 3.3** (or 3.2, or 3.4) for a stock 64-bit-MIPS o32
   configuration, the way the PS2 SDK built its `ee-gcc` — and reuse the
   `ee-gcc` 2.95.2 the wave already has, as the control;
2. compile the **newlib 1.15 `strcmp`**, the same source, with the same
   flags, and compare the **shape** with the retail `0x00245504`: the
   number of slots, the signed comparison, the absence of masking, the
   branch that is used;
3. compile a small corpus of functions and compare the **prologue rule**:
   the number of slots below the saved `$ra`, and whether the frames are
   multiples of 16;
4. report whether the **debug-C idiom** is present in the compiler's
   output, since the retail code has none.

The lot may report **`not_built`** for what it could not build. A negative
result is a result.

## JUMP — the computed jumps

The control-flow graph of `tools/layout.py` stops at a jump through a
register, because it cannot know the target. The target is a **table**:
the code computes the address of the table with `lui`/`addu`/`lw`, and
indexes it with `andi`. The lot is to make the graph read the table, so
that the bodies it currently truncates are bounded correctly.

The lot may write `tools/layout.py` — it is the ROOT's file and the lot
is the one that owns it for the duration. The graph must keep the rules
that wave 2 established: the delay slot is absorbed, a call does not
transfer the control, a return closes the path.

## Integration (ROOT)

1. Merge the lots into `config/boot/layout.tsv`.
2. Merge the names, and record the corrections.
3. Recount, and publish the error rate of the sweep over what was
   reviewed.
4. Run the tests, then the repository guard.
5. One writer in the clone: the ROOT alone.
