# WAVE 2 — layout and naming (ROOT, 2026-10-21)

> Anchor of the wave. General state: `docs/STATE.md`. Start of the wave:
> `main` = `fcfb6a8`.

## Start

Already established, with its exact numbers:

* the disc is pinned; the `~PSP` executable is decrypted: 4 949 041 bytes,
  SHA-256 `df13fd9d…67d2`, a **type 1 PSP PRX**, module `dax`;
* it is **stripped**: one null symbol; 3 335 156 bytes of `.text` in a
  single segment; no `$gp` anywhere, so the code is linked at a fixed
  address;
* the call graph holds **11 497** call targets; the sweep yields
  **19 062** bounded candidates, of which **11 452** are called;
* **wave 1** reviewed 240 targets: 240 confirmed as functions, 15 names,
  and **93,3 %** agreement with the sweep on the bounds. The sweep was
  corrected — a body now closes at its last return before the next
  *strong* start — and the lots of this wave were cut with the corrected
  rule.

What is open, and what the queue of this wave comes from: **which of the
bounded candidates are functions, where their bodies really end, what they
are called, and which toolchain can reproduce the retail bytes.**

## The lots of the wave

| lot | targets | kind |
|---|---|---|
| L07 … L14 | 40 each | layout review, 320 targets |
| NAMES | 240 | naming pass over the bodies wave 1 confirmed |
| ASSERT | 344 sites | the engine's own naming mechanism |
| TOOLCHAIN | — | the compiler that built the retail bytes |

Brief of the layout lots: `work/templates/BRIEF-COMMUN-2.md`. Lists:
`work/lots/L*.tsv`. Report: `work/templates/RAPPORT.md`.

## The three special assignments

**NAMES** takes the 240 bodies wave 1 confirmed, and names the ones that
kept `func_XXXXXXXX`. Its sources are the strings the body reads, the
module map, the virtual method tables, the assert mechanism, and the
well-known algorithms. It may also **correct** a name wave 1 proposed, if
it finds better evidence — and it must say so when it does.

**ASSERT** resolves the 344 call sites of the engine's assert helper at
`0x7035C`, which takes the name of the enclosing function in `$a3`. The
argument is built by a `lui` before the call and an `addiu` **in the delay
slot of the call**; the identifiers live in a string pool that starts at
`0x00340000`. Wave 1 resolved 158 of the 344 by hand and got 63 distinct
names. The assignment is to resolve **all** of them, with a dataflow
analysis over each function, and to publish the catalogue.

**TOOLCHAIN** establishes which compiler can reproduce the retail bytes.
What is measured already: 16-byte stack slots with the return address on
top of the frame, no `$gp`, and **no** GCC debug-C equality idiom — the
last being a measured difference from the PlayStation 2 Ratchet & Clank
boot build, which does carry it. The PSPSDK Allegrex toolchain is a GCC
3.3 lineage; the community port of it says so. The assignment is to
**obtain** a toolchain, compile a body, and compare the bytes.

## Integration (ROOT)

1. Merge the lots into `config/boot/layout.tsv`.
2. Merge the names into the same table, and record the corrections.
3. Recount, and publish the error rate of the sweep over what was
   reviewed.
4. Run the tests, then the repository guard.
5. One writer in the clone: the ROOT alone.

## Immediate resumption if interrupted

1. `cat work/*/RAPPORT.md`, `cat work/*/layout.tsv`.
2. Do not relaunch the foundation: the call graph, the bounds, the lots,
   the string catalogue and the module map are delivered.
