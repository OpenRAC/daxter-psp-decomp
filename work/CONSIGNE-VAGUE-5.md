# WAVE 5 — the first bodies (ROOT, 2026-10-21)

> Anchor of the wave. General state: `docs/STATE.md`. Start of the wave:
> `main` = `da9e557`.

## Start

Everything that could be measured has been measured.

* the target is decrypted and measured: 4 949 041 bytes, a stripped PSP PRX;
* **661 bodies** reviewed, 661 confirmed as functions, **84 named**, and the
  sweep agrees with the review on **99,4 %** of them;
* the **configuration of the retail build is named**: GCC 3.3.6, o32, stack
  aligned on sixteen bytes, frame rounded to sixteen as a whole. The recipe
  is in `work/H3/build.md`, and it reproduces the prologue rule of the retail
  code on 157 of 157 bodies;
* the **library** of the retail build is still open, H4: its `strcmp` has 13
  slots and no public newlib source gives that shape.

What is open, and what the queue of this wave comes from: **the first
matched body.** Everything the method needs is in place — the layout, the
harness, and a named compiler configuration. What is missing is a body
written in C that compiles to the retail bytes.

## Phase A — three assignments

### TOOLCHAIN — build the identified compiler

Build the configuration named above, from the recipe of `work/H3/build.md`,
into a location every later assignment can use. Verify it on the retail
prologue rule, and pin it by hash.

### HARNESS — the proof pipeline

`tools/harness.py` compares a compiled symbol with the retail bytes. It
does not yet *produce* the object: there is no recipe that compiles a C
file with the identified profile, links it at the retail address, and hands
the bytes over. That is this assignment.

The links matter: the retail code is not position independent, so a body
that calls another function has a relative call offset that depends on
where it is linked. The body has to be linked at its retail address, or
the comparison is meaningless.

### BODIES — choose the first bodies

The reviewed layout holds 661 bodies, and the question is which of them can
be **written in C and proved** first. The criteria are narrow and harsh: the
source has to be recoverable from the code with confidence, and the body
has to be small.

## Phase B — write and prove

Six to eight lots, one body each to begin with. For every body:

1. reconstruct the source from the code, and say why it is right;
2. compile it with the identified profile;
3. link it at the retail address;
4. compare **every byte** with the retail.

`exact` is the only result that counts. A mismatch is reported with its
first difference, and the body is parked in `nonmatching/` with the
difference and a condition of reopening — never counted.

## The rules that do not change

The rules of `AGENTS.md` hold, and so do the two the method adds here:

* **pure C**: no inline assembly, no raw instruction words, no fixed
  register bindings, no edit of the compiler output;
* **authored form, not steered codegen**: when the bytes do not match, the
  answer is the *source*, not a trick that moves a value into another
  register. A construct whose only purpose is to steer the code generator
  is refused;
* the **original behaviour** is preserved, bugs included.

## The public boundary

No disc image, no executable, no decrypted executable, no instruction
listing and no asset is ever committed. The bodies that are proved go into
`src/`, one file per function, and the placement table records where each
one sits.
