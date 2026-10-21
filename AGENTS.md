# Instructions for contributors and AI agents

Read `README.md`, `PROMPT.md`, `docs/METHOD.md`, `docs/EVIDENCE.md` and
`docs/STATE.md` before changing this project.

This repository adopts the **evidence standard and source layout** of the
sibling OpenRAC projects (`rac1-decomp`, `rac2-gc-decomp`, `rac3-uya-decomp`,
`rac-deadlocked-decomp`, and above all the PSP project `rac-sac-decomp`).
It does **not** adopt their compilers, their formats or their boundaries.

## Ten working rules

1. **Bounds and ownership.** Each replacement range has one owner, no
   overlaps or duplicate names. A compiled prefix or a next-label interval
   is not proof of a complete function. Unknown extents remain provisional
   and uncounted.
2. **Explicit promotion.** Count C only when the claimed body is actually
   linked at every reviewed placement and the complete-program gates pass.
   An assembly fallback preserves the baseline but earns no C credit. One
   proven zero word of linker alignment may follow a complete body, but
   count only compiled body bytes after boundary and semantic review;
   promote separately.
3. **Evidence-based profiles.** Compiler routes, options and patches require
   a measured cause, known provenance and regression controls. Do not select
   a compiler just because one sample matches. Requalify affected accepted
   bodies.
4. **Proven names and types.** Keep reference symbols stable. Descriptive
   aliases, prototypes, field sizes, offsets and signedness need evidence
   from symbols, code, callers or data. Share definitions rather than
   inventing layouts.
5. **Bounded experiments.** Change one hypothesis at a time. After three
   attempts with the same mismatch class, recover context, change approach
   or park the best source with its first difference and a concrete
   reopening condition.
6. **Original behavior.** Preserve original behavior, including bugs, in
   matching work. Do not add purposeless C tricks to steer code generation.
   Bug fixes and PC platform adaptations belong in explicitly separate work
   and earn no matching credit. This does not relax the strict
   no-instruction-assembly rule.
7. **Public hygiene.** Keep scratch directories, probes, generated lists and
   raw reports private. Index useful alternatives by function in
   `nonmatching/`. Reusable tools belong in `tools/` with tests; public text
   is English.
8. **Pure C evidence.** C/C++ evidence must come from compiler-generated
   instructions: no inline or global assembly, no fixed-register bindings,
   no raw instruction words, no artificial assembly barriers, and no edits to
   compiler output. A file-scope assembler-name label on a declaration is
   allowed solely to name a reference symbol; it must emit no instructions.
9. **Authored form, not steered codegen.** When the compiled bytes do not
   match, the answer is the *source*, not the compiler's mood. Recover the
   authentic form of the routine: where the values live, how many are live
   at once, in which order they are produced. A construct whose only purpose
   is to move a value into a different register is not accepted.
10. **One writer in the clone.** Only the root integrates. Agents write in
    their own lot directory under `work/`.

## What counts as a match

After the applicable program layout, assembly baseline, function boundary and
compiler profile have been qualified, keep one authored C/C++ definition per
function in `src/`. A useful but nonmatching attempt belongs in
`nonmatching/`. Only a qualified toolchain reproducing the **complete retail
program bytes at every applicable placement** can establish a match.
Compiling successfully, matching a few instructions, or comparing masked
bytes cannot.

## The gate this project has and the PS2 siblings do not

The PS2 siblings could open the retail executable on day one. This project
could not: the executable on the disc is encrypted behind the `~PSP`
container.

The gate is now **passed**, and its evidence is published: the decrypted
ELF's SHA-256 is in `config/target.json`, and its structure is in
`config/boot/summary.json`. The decrypted ELF itself is never committed.

So the rules for the work that follows are the ordinary ones:

* the **function inventory** is `config/boot/functions.tsv`: 14 655
  frame-opening candidates. A candidate is **not** a function. Before a
  candidate is used as the target of a body, its boundary has to be
  established: that it is entered from a call, that it returns through
  `$ra`, and where it ends. A candidate with an unestablished boundary is
  provisional and is not counted.
* the **names** have to be proved. The symbol table of the retail
  executable is empty. A name may come from a string, from a caller, from
  the sibling projects, or from nowhere — and "nowhere" is an acceptable
  answer: the reference name may be `func_00001234`. What is not
  acceptable is a plausible name with no evidence behind it.
* the **decrypted executable** stays local. So does every module, listing
  and report derived from it.

## Never commit

Disc images, retail executables, decrypted executables, extracted modules,
instruction listings, disassembly, assets, proprietary tools, build output,
SDK sources or headers, leaked or NDA source, and personal paths. The
`.gitignore` covers the common local locations, but review your own diff: the
guard is structural, not a substitute for reading the diff.

## Checks

Run the repository's own checks before a commit, and describe in the pull
request what was verified and what remains provisional. Checks enforce
structural invariants, not semantic truth: names, types, patch justification,
intent and original behavior still require evidence and review.

```
python3 tools/check_repository.py
python3 -m unittest discover -s tests
python3 tools/progress.py
```

The first two need nothing but the repository. The third reads the tables
under `config/` and prints the state of the project.
