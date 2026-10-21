# WAVE 1 — layout (ROOT, 2026-10-21)

> Anchor of the wave. General state: `docs/STATE.md`. Start of the wave:
> `main` = `c11bb00`.

## Start

Already established, with its exact numbers:

* the disc is pinned: 1 405 845 504 bytes, SHA-1 `6a54c86d…282cb`;
* the `~PSP` executable is decrypted: 4 949 041 bytes, SHA-256
  `df13fd9d…67d2`, a **type 1 PSP PRX**, tag `0xC0CB167C`, module `dax`;
* it is **stripped**: its symbol table holds one null symbol, so the
  functions have neither names nor sizes;
* it is **monolithic**: 3 335 156 bytes of `.text` in a single segment,
  against the forty-eight packed level overlays of the PlayStation 2 games
  of the same studio;
* the call graph holds **11 497** call targets, the top of them called
  1 718 times;
* the layout sweep yields **20 889** bounded candidates, of which
  **11 452** are reached by a call.

What is open, and what the queue of the wave comes from: **which of the
bounded candidates are functions, where their bodies really end, and what
they are called.**

## Foundation lot E0 — delivered

* `work/E0/calls.tsv` — the call graph: every target and its number of
  call sites.
* `work/E0/bounds.tsv` — the bounded candidates, with the evidence of each
  bound: `call`, `after_return` or `frame`, and the number of returns the
  body holds.
* `work/lots/L*.tsv` — the shortlist: the called candidates, ranked by
  **leverage** (how many call sites carry the same body) and then
  stratified by size, so that a wave spans several body sizes instead of
  filling up with stubs.

The tool is `tools/layout.py`. It is a heuristic, and the wave exists to
check it: **the table is the hypothesis, the code is the proof.**

## Layout review lots (6)

| lot | targets | what it covers |
|---|---|---|
| L01 | 40 | the highest-leverage bodies, smallest first |
| L02 | 40 | |
| L03 | 40 | |
| L04 | 40 | |
| L05 | 40 | |
| L06 | 40 | |

Brief: `work/templates/BRIEF-COMMUN.md`. Lists: `work/lots/L*.tsv`.
Report: `work/templates/RAPPORT.md`.

Each lot answers the same three questions for its own targets, and writes
one row per target:

```
start	end	size	class	name	name_evidence	confidence
```

## Integration (ROOT)

1. Merge the rows of the lots into `config/boot/layout.tsv`.
2. Recount: the number of functions, of rejected candidates, of unknowns.
3. Compare the reviewed bounds with the sweep's, and publish the
   disagreement: it measures the sweep's error rate.
4. Run the tests, then the repository guard.
5. One writer in the clone: the ROOT alone.

## Immediate resumption if interrupted

1. `cat work/*/RAPPORT.md`, `cat work/*/layout.tsv`.
2. Do not relaunch E0: the call graph, the bounds and the lots are
   delivered.
