# The gates

Three gates, in order. A body is not *counted* until it has passed them all.

---

## Gate 0 — the visibility gate

**A gate this project has, and the PS2 siblings do not.**

> The decrypted executable must exist locally, its structure must have been
> measured with `tools/psp_elf.py`, and its hashes must be recorded in
> `config/target.json`.

Until this gate is passed, the repository may publish:

* the disc identity, the container formats, the asset inventory;
* the readers and their tests;
* the research notes.

It may **not** publish, and may not claim:

* function names, addresses, sizes or boundaries;
* instruction listings or disassembly;
* any extracted module.

The gate is passed per contributor, and its evidence is the pinned hashes
of the decrypted executable written into `config/target.json` — never the
file itself.

---

## Gate 1 — the body gate

> One authored C/C++ definition compiles, links at the measured offset, and
> produces **every byte** of the retail body range, identically.

Requirements:

| Requirement | Test |
| --- | --- |
| the toolchain profile is qualified | the profile exists in `config/toolchain.json` with a measured cause and a regression control |
| the body range is known | the start and the end are both justified, not guessed |
| the bytes match | a full-range comparison, unmasked |
| the boundary is reviewed | the byte before the range closes the previous body; the byte after is not part of this body |
| the source is pure C | no inline assembly, no raw instruction words, no register bindings, no edits to compiler output |

A body that passes the byte comparison but not the boundary review is
**provisional**: it is published, it is not counted.

---

## Gate 2 — the placement gate

> The same body is linked at **every** placement the inventory attributes to
> it, and each placement reproduces the retail bytes.

This is the gate that separates "a function that happens to match somewhere"
from "a function of the program". A body that matches at one address and
differs at another address attributed to the same body is **not** proved:
either the boundary is wrong, or the body is not one body.

---

## Gate 3 — the complete-program gate

> The complete linked program equals the retail program, byte for byte,
> and hashes to the pinned retail hash.

This is the only gate that promotes. Until it passes, the project holds
**no** count of matched functions; it holds a set of proved bodies, each
proved against the retail bytes at its own placement.

The PS2 projects call this the gate that is "still missing" for most of
their history. It is the last gate, not the first one, and it is the one
that decides whether the project is a decompilation or a pile of
coincidences.

---

## Where the project stands

```
   Gate 0            Gate 1             Gate 2             Gate 3
 visibility  ──►  the body      ──►  every placement  ──►  the program
   (local)          (one body)        (all of them)        (the hash)
      │                │                   │                   │
      │ PASSED         │ IN PROGRESS       │                   │
      │                └── provisional ─────┘                   │
      │                                                            │
      └───────────── nothing is counted before this ─────────────┘
```

**Gate 0 is passed.** The executable is decrypted, measured, and its
structure published: 661 bodies reviewed and confirmed as functions, 84
named, and the sweep agreeing with the review on 99,4 per cent of them.
The layout the body gate needs is therefore in place.

**Gate 1 is the frontier.** The configuration of the retail build is named
and reproducible, and the pipeline that compiles, links at the retail
address and compares the bytes is built. What is missing is a body written
in C that compiles to the retail bytes.

Two things are worth saying about the order, because they are what the
sibling projects learned the hard way:

* **Gate 1 is the gate that decides everything.** A body that matches at
  one address and differs at another is not a body. The project would hold
  a pile of coincidences, and the sibling PS2 projects held exactly that
  for most of their history.
* **Gate 2 is where the leverage is.** When two bodies hold the same
  bytes, one authored source satisfies both — the placement table of this
  project already holds eight such groups over 661 bodies. A body proved
  at one place and then found at another is a body that paid for itself
  twice.
