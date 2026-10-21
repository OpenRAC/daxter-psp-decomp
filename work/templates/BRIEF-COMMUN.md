# COMMON BRIEF — wave 1, layout (2026-10-21)

> Read in full before any action. Common to every agent of the wave.

## 1. Context

What the wave must produce, in one sentence: **the verified layout of the
code** — for every target of your lot, the real boundary of the body,
whether it is a function at all, and a name if there is evidence for one.

Already established, and not to be redone: the disc is pinned; the `~PSP`
executable is decrypted and measured; it is a **stripped PSP PRX** with
3 335 156 bytes of `.text` in one segment; the call graph and the bounded
candidates are computed by `tools/layout.py`.

Open, and what this wave is for: **which of the bounded candidates are
functions, where their bodies really end, and what they are called.**

## 2. What is where

| Element | Path | Role |
|---|---|---|
| Target — the decrypted ELF | `C:\Users\GAMING\AppData\Local\Temp\opencode\work\decrypted.elf` | **READ ONLY** for a lot agent |
| Repository | `C:\Users\GAMING\AppData\Local\Temp\opencode\daxter-psp-decomp` | the tools and the method |
| Tools | `tools/layout.py`, `tools/function_inventory.py`, `tools/psp_elf.py` | the analysis |
| Your list | `work/lots/<LOT>.tsv` | your targets |
| **Your folder** | `work/<LOT>/` | **you write only here** |

## 3. The task, target by target

Each row of your list is a **hypothesis**, not a fact:

```
start  end  size  bound_source  evidence  calls  returns
```

For every row:

1. **Verify the bound.** Disassemble from `start` and check:
   * does the body really **start** there — a frame opening, or the first
     instruction of a leaf function?
   * does the body really **end** at `end` — is the last return
     (`jr $ra`, or `jr $t9`) at `end - 8`, with its delay slot?
   * is the bound **tight** — does the code just before `start` belong to
     the previous body, and does the code at `end` belong to the next one?
2. **Classify** the target:
   * `function` — it is entered by a call, it returns, and the bound is
     tight;
   * `not_function` — it is a label, a jump-table entry, a cold path, or a
     fragment of a bigger body;
   * `unknown` — you cannot tell. Say why.
3. **Look for a name.** Evidence, in this order:
   * a string of the data segment that the body references;
   * the catalogue of the sibling project `OpenRAC/rac-sac-decomp`: it
     already names the functions of the **same engine, on the same
     processor**, for *Secret Agent Clank*. It is a source of hypotheses,
     not of proof;
   * the NID of the stub the body calls (`sceCtrl`, `sceAudio`, ...);
   * otherwise: **no name**. `func_00001234` is a correct answer and is
     preferred over a guess.
4. **Record the evidence** for whatever you conclude.

## 4. Hard rules

1. **Never write outside `work/<LOT>/`.** The repository has one writer:
   the ROOT.
2. **Never publish an instruction listing.** A disassembly may be read
   locally; it must not appear in the deliverable. The deliverable is
   metadata: addresses, sizes, classes, names, evidence.
3. **No name without evidence.** `func_XXXXXXXX` is a valid answer, and is
   better than a plausible name with nothing behind it.
4. **The bound comes from the code.** The table is the hypothesis; you
   verify it.
5. **A disagreement with the table is a result, not a failure.** Report it
   plainly.
6. **Three attempts, then stop.** After three attempts on the same class
   of doubt, leave the target `unknown` with the reason, and move on.
7. **Only what you observed.** No promise, no extrapolation.

## 5. The deliverable of the lot

```
work/<LOT>/layout.tsv     one row per target
work/<LOT>/RAPPORT.md     20 lines maximum
```

`layout.tsv` has this header, tab separated:

```
start	end	size	class	name	name_evidence	confidence
```

* `class` is `function`, `not_function` or `unknown`;
* `name` is the proposed name, or `func_<address>` when there is none;
* `name_evidence` is `-` when there is none, otherwise where the name
  comes from;
* `confidence` is `high`, `medium` or `low`.

## 6. Final report to the ROOT

**French, 20 lines maximum**: the number of targets confirmed, the number
rejected, the number left unknown, the notable disagreements with the
table, and the paths of the deliverables.
