# The method

The method is the one of the sibling OpenRAC projects, adapted to a target
whose code is not readable on the disc.

## The wave protocol

1. **Foundation lot.** Extract the target locally, pin its identity
   (hashes, sizes, counts), compute the bounded candidate entries, and
   build a shortlist ranked by leverage — how many placements carry the same
   body.
2. **Lot.** The shortlist is cut into lots. One agent per lot writes one
   authored C source per target.
3. **Proof.** The body is proved by compiling it with the qualified
   toolchain, linking it at the measured offset, and comparing **every
   byte** with the retail bytes.
4. **Integration.** The root re-measures every claim, merges the bodies that
   compile to the same code, writes the placement table, runs the
   complete-program gate, regenerates the catalogues and the progress
   snapshot, runs the tests, and opens the pull request.
5. **Parking.** A body that will not match is parked in `nonmatching/` with
   its first difference and a concrete reopening condition. It is never
   counted.

## The phases of this target

### Phase 0 — visibility (not yet done)

The disc executable is encrypted. Until the decryption step runs on a
lawful local copy and `tools/psp_elf.py` has measured the structure, there
is nothing to match.

Deliverables of this phase:

| Deliverable | Where |
| --- | --- |
| the pinned target identity | `config/target.json` |
| the disc manifest | `config/disc/containers.tsv` |
| the asset container index | `config/disc/pack_index.tsv` |
| the container format readers | `tools/psp_formats.py` |
| the format research note | `docs/FORMATS.md` |

The decryption itself is **not** a deliverable of the repository: it is a
local step on a lawful copy, and its result is never committed. What the
repository gains from it is the structure, which is metadata.

### Phase 1 — layout

Establish the program layout of the decrypted executable: the sections, the
load addresses, the relocation model, the entry point, and the module
boundaries. This is the Allegrex counterpart of the "assembly baseline" the
PS2 projects had to build.

Deliverables: the layout note, the section table, the function inventory
(`tools/psp_elf.py --functions`).

### Phase 2 — toolchain qualification

Find a toolchain that can produce the retail bytes, and record it in
`config/toolchain.json` with the evidence each profile rests on. The PS2
siblings found that the modern GNU EE chain was *close but not equal*, and
that the difference was a register mode; the Allegrex equivalent has to be
**measured**, not assumed.

Deliverables: `config/toolchain.json` with at least one profile whose cause
is measured and whose regression control is stated.

### Phase 3 — bodies

The ordinary wave protocol: one lot, one agent, one body, one proof.

## What a body proof looks like

```
  authored C source  ──compile──►  object  ──link at 0xADDR──►  segment
                                                               │
                                                     compare every byte
                                                               │
                                                        equal? ── yes ──► proved
                                                               │
                                                                no
                                                               │
                                        park with the first difference
```

A body is *proved* only when:

* the toolchain profile is qualified and recorded;
* the body is linked at the measured offset;
* **every** byte of the body range matches;
* the boundary is reviewed: the byte before the range is a terminator of
  the previous body and the byte after is not part of this body.

A body that matches but whose boundary is guessed is **provisional** and is
not counted.

## What is not evidence

* compiling without error;
* a handful of matching instructions;
* comparing masked bytes;
* a screenshot of a disassembler;
* the existence of a plausible name.
