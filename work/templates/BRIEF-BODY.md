# BRIEF — body lots, wave 5 phase B (2026-10-21)

> Read in full before any action. This brief supersedes the layout brief
> for the body lots: a body lot is a different kind of work.

## 1. Context

What the wave must produce, in one sentence: **bodies written in C that
compile to the retail bytes, byte for byte, with the proof attached.**

Everything the method needs is in place. The disc is pinned, the
executable is decrypted and measured, the layout of 661 bodies is
reviewed, the configuration of the retail build is named, and the pipeline
that compiles, links at the retail address and compares is built.

What is open: the bodies themselves. **This is the first time the
project writes code.**

## 2. What is where

| Element | Path | Role |
|---|---|---|
| Target — the decrypted ELF | `C:\Users\GAMING\AppData\Local\Temp\opencode\work\decrypted.elf` | **READ ONLY** |
| The reviewed layout | `config\boot\layout.tsv` | the bounds and the names of the 661 bodies |
| The placement table | `config\boot\placements.tsv` | the bodies that are the same body |
| The idioms of the code | `config\boot\idioms.json` | the frame rule, the save width, the branches |
| The strings a body reads | `work\E0\function_strings.tsv` | the naming evidence |
| The module map | `config\boot\modules.tsv` | the source files of the engine |
| The candidates | `work\BODIES\candidates.tsv` | the bodies the wave chose, best first |
| The compiler | `work\TOOLCHAIN\toolchain.json` | the image, the invocation, the pinned hashes |
| The pipeline | `tools\harness.py` | compile, link at the address, compare |
| **Your folder** | `work\BODIES\B<NN>/` | **you write only here** |

## 3. The task, body by body

For every body of your list:

1. **Reconstruct the source.** From the code, not from the name. Say what
   forces it: the constant, the idiom, the string, the module.
2. **Write the C.** Plain C, the way the surrounding code would be
   written. No comments that are not true, no assertions the retail code
   does not have, no clean-ups. The retail code is what it is, bugs
   included.
3. **Compile it** with the identified profile, **link it at the retail
   address**, and compare **every byte**.
4. **Report the result**: `exact`, or the first difference.

If the bytes do not match, the answer is the **source**, not a trick.
The method refuses:

* inline or global assembly, `.word`, fixed register bindings, edits of
  the compiler output;
* a construct whose only purpose is to move a value into another
  register — that is steering the code generator, not authoring the
  routine;
* a body that does not return the same value, or has a different
  behaviour, however many bytes match.

After three attempts on the same body, park it: the source, the first
difference, and a concrete condition of reopening. Never count it.

## 4. The deliverable of the lot

```
work/BODIES/B<NN>/bodies/<NAME>.c    the authored source, one file per body
work/BODIES/B<NN>/results.tsv        start  size  status  first_difference
work/BODIES/B<NN>/RAPPORT.md         the report
```

`results.tsv` has this header, tab separated:

```
start	size	status	first_difference
```

`status` is `exact`, `mismatch` or `parked`. `first_difference` is the
offset of the first differing byte, or `-`.

For a body that matches, the authored source goes to `src/` **through the
ROOT**, not by you. Write it in your lot, and the ROOT integrates it.

## 5. Hard rules

1. **Write ONLY inside `work\BODIES\B<NN>\`.** One writer in the clone:
   the ROOT integrates.
2. **Never publish an instruction listing.** The deliverable is the
   source, the result and the reason.
3. **Pure C.** No inline assembly, no raw instruction words, no fixed
   register bindings, no barrier, no edit of the compiler output.
4. **The source must be forced.** A body whose source is a matter of taste
   is a body that must not be written yet.
5. **The original behaviour** is preserved, bugs included.
6. **A negative control is expected**: check that the pipeline reports a
   difference when the address or the flags are wrong, and say so.
7. Report only what you measured.

## 6. Final report to the ROOT

**French, 20 lines maximum**: the number of bodies proved exact, the
number mismatched, the number parked, the first difference of each
mismatch, what the compilation taught that the other lots should know,
and the paths.
