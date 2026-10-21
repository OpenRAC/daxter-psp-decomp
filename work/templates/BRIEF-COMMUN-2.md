# COMMON BRIEF — wave 2, layout (2026-10-21)

> Read in full before any action. Common to every layout agent of the wave.
> It supersedes `BRIEF-COMMUN.md` of wave 1, and adds what wave 1 learned.

## 1. Context

What the wave must produce, in one sentence: **the verified layout of the
code** — for every target of your lot, the real boundary of the body,
whether it is a function at all, and a name if there is evidence for one.

Already established, and not to be redone: the disc is pinned; the `~PSP`
executable is decrypted and measured; it is a **stripped PSP PRX** with
3 335 156 bytes of `.text` in one segment; the call graph and the bounded
candidates are computed by `tools/layout.py`.

Wave 1 reviewed 240 targets: **all 240 confirmed as functions**, 15 names
recovered, and the sweep got 93,3 % of the bounds right. This wave
continues the queue with the lots L07 to L14.

## 2. What is where

| Element | Path | Role |
|---|---|---|
| Target — the decrypted ELF | `C:\Users\GAMING\AppData\Local\Temp\opencode\work\decrypted.elf` | **READ ONLY** for a lot agent |
| Repository | `C:\Users\GAMING\AppData\Local\Temp\opencode\daxter-psp-decomp` | the tools and the method |
| Tools | `tools/layout.py`, `tools/function_inventory.py`, `tools/psp_elf.py`, `tools/function_strings.py`, `tools/assert_names.py` | the analysis |
| The string catalogue | `work/E0/strings.tsv` | the strings of the binary, with their addresses |
| The function-to-string catalogue | `work/E0/function_strings.tsv` | which strings a reviewed body reads |
| The module map | `config/boot/modules.tsv` | the source modules of the engine |
| The reviewed layout of wave 1 | `config/boot/layout.tsv` | the 240 bodies already confirmed, with their names |
| Your list | `work/lots/<LOT>.tsv` | your targets |
| **Your folder** | `work/<LOT>/` | **you write only here** |

## 3. What wave 1 learned — use this, do not rediscover it

**The mapping.** The file offset of a code address is `vaddr + 0x74`; the
file offset of a data address is `vaddr + 0x70`. Getting this wrong shifts
every disassembly by four bytes.

**A body.** From its entry point to its **single return** plus the delay
slot: the return is at `end - 8`, the slot at `end - 4`, the previous
body's return at `start - 8`, and the next body starts exactly at `end`.

**The control-flow graph must absorb the delay slot.** The successor of a
`jal` or a `j` is at `pc + 8`, not `pc + 4`. A graph that does not absorb
it breaks every body that contains a call, and the bound is then wrong on
both sides.

**The return address is not saved first.** The frame is opened, then the
callee-saved registers are pushed, and only then is `$ra` saved — the
measured distance goes up to fifteen instructions.

**The `after_return` evidence alone does not make a function.** A candidate
that only follows a return is a **return path**: wave 1's negative control
was `0x0024243C`, eight bytes, reached by a single conditional branch, no
call site and no frame.

**A body can have two epilogues, and a cold path after the epilogue.**
`0x00258524` runs a 64-bit multiplication to `0x258898`, well past its
return at `0x2585F4`. The bound is given by the control-flow graph, not by
the first return.

**A function is not always reached by a call.** It can be reached through a
pointer — a virtual method table, or a table of data. The sweep misses
those, and the review must notice it.

**Capstone does not decode every Allegrex encoding** — the FPU
instructions in particular. Make the controls on the **raw 32-bit words**.

**A body that opens no frame is normal** when it makes no call. It is a
leaf, and it is still a function.

## 4. The task, target by target

Each row of your list is a **hypothesis**:

```
start  end  size  bound_source  evidence  calls  returns
```

For every row:

1. **Verify the boundary from the code**, with the three proofs:
   * the body **starts** at `start` — a frame opening
     `addiu $sp, $sp, -N`, or the first instruction of a leaf;
   * the body **ends** at `end` — the return at `end - 8`, its delay slot
     at `end - 4`, and **nothing reachable from `end`** belongs to the
     body;
   * the bound is **tight** — the word at `start - 4` is the delay slot of
     the previous body's return, and no branch enters or leaves the body
     other than through a call.
2. **Classify**: `function`, `not_function` (a label, a jump-table entry,
   a cold path, a fragment) or `unknown` (say why).
3. **Look for a name**, with evidence only:
   * a string the body references — `work/E0/function_strings.tsv` gives
     the strings of the bodies already reviewed, and
     `tools/function_strings.py` resolves them for any body;
   * the source module it belongs to, from `config/boot/modules.tsv`;
   * the engine's **assert mechanism**: the helper at `0x7035C` takes the
     name of the enclosing function in `$a3` — the C `__FUNCTION__`. If
     the body hosts a call site of that helper, the name is in the
     argument;
   * a virtual method table entry in `.rodata`, a pair of a pointer and a
     zero;
   * the well-known algorithms;
   * otherwise: **no name**. `func_<8 hex digits of the address>` is a
     correct answer and is preferred over a guess.
4. **Record the evidence** for what you conclude.

## 5. Hard rules

1. **Write ONLY inside `work/<LOT>/`.** The repository has one writer:
   the ROOT.
2. **Never publish an instruction listing.** The deliverable is metadata:
   addresses, sizes, classes, names, evidence. You may disassemble
   locally to decide.
3. **No name without evidence.** `func_XXXXXXXX` is a valid answer.
4. **The bound comes from the code.** The table is the hypothesis.
5. **A disagreement with the table is a result, not a failure.**
6. **Three attempts, then stop.** After three attempts on the same class
   of doubt, leave the target `unknown` with the reason, and move on.
7. **Only what you observed.**

## 6. The deliverable of the lot

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

**All the targets of your list must be present**, in the order of the
list, including the ones you could not resolve.

## 7. Final report to the ROOT

**French, 20 lines maximum**: the number of targets confirmed, the number
rejected, the number left unknown, the notable disagreements with the
table, what the review learned that the other lots should know, and the
paths of the deliverables.
