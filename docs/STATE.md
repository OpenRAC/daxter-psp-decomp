# State

The anchor: where the project stands, and what to do next.

**Target:** *Daxter* (USA), PSP, title id `UCUS98618`, disc version 1.00.
**Status:** `in-progress`. The visibility gate is passed, and the layout of
the code is established for the two hundred and forty targets of wave 1.
No function has been matched.

---

## What is done

| Item | Evidence | Where |
| --- | --- | --- |
| the disc is pinned | SHA-1 `6a54c86d…282cb`, SHA-256 `648e237a…59f4`, 1 405 845 504 bytes | `config/target.json` |
| the disc is inventoried | 1 104 files, 342 Pack containers, 19 255 blobs | `config/disc/containers.tsv`, `config/disc/pack_index.tsv` |
| the target identity is read from the disc itself | `UCUS98618`, `UG`, `1.00`, region `0x8000`, firmware `2.60` | `tools/psp_formats.py` |
| four container formats are read and documented | `PARAM.SFO`, `~PSP`, `PSAR`, `Pack` | `docs/FORMATS.md` |
| the binary layout is settled | the code is one monolithic executable, not a loader plus overlays | `docs/FORMATS.md` §5 |
| **the executable is decrypted** | the ELF is 4 949 041 bytes, SHA-256 `df13fd9d…67d2` | `tools/decrypt_psp.py`, `config/target.json` |
| **the executable is measured** | 2 segments, 60 sections, module `dax`, 25 imported libraries | `config/boot/summary.json` |
| **the build is identified** | engine SCREAM, object layer Aurora, port by Ready At Dawn, built `Mar 28 2005` | `config/target.json` |
| **the module map is published** | 25 source paths in 11 libraries | `config/boot/modules.tsv` |
| **the code's idioms are measured** | 888 485 instructions, 16-byte stack slots, no `$gp`, no debug-C idiom | `config/boot/idioms.json` |
| **the layout is established** | 661 targets reviewed, 661 confirmed as functions, 84 named | `config/boot/layout.tsv` |
| **the shared bodies are known** | 652 distinct bodies, 8 groups of two or more | `config/boot/placements.tsv` |
| the readers are tested | synthetic fixtures, no game data in the tests | `tests/test_tools.py` |

### The decryption

The executable is a **type 1 PSP PRX** behind the `~PSP` container, tag
`0xC0CB167C`, decrypt mode 9. The decryption is implemented in this
repository, in Python, from the published description of the format:

```sh
python3 tools/decrypt_psp.py <EBOOT.BIN> <decrypted.elf>
python3 tools/boot_inventory.py --elf <decrypted.elf> --out config
```

Two independent things confirm that the decryption is right, and neither of
them is "it looks like code":

* the **SHA-1 of the header** matches the one in the file, and so do the
  **two CMAC hashes** of the KIRK command — the header hash and the hash
  over the payload. A wrong key fails both.
* the same implementation decrypts the **PSP firmware updater** that ships
  on the same disc — a type 0 PRX with a different tag and a different key
  slot — and gets its SHA-1 right too. The algorithm is not tuned to one
  file.

### What the executable turned out to be

* a **PSP PRX**, not an ELF executable: its type is `0xFFA0`;
* **stripped**: the symbol table holds one null symbol, so the functions
  have no names and no sizes;
* **one monolithic object**: 3 335 156 bytes of `.text` in a single
  segment, against the forty-eight packed level overlays of the PlayStation
  2 games of the same studio;
* **not position independent**: no `$gp` at all, every global reached
  through an absolute address, `.text` linked at `0x00000000`;
* `BOOT.BIN` is **entirely zeroed** and exactly the size of the decrypted
  ELF: it is the buffer the firmware decrypts into, not another version of
  the program.

### What wave 2 established

The compiler that built the retail bytes is not guessed, it is **measured**,
and the measurement **discriminates**:

| Property | Retail | GCC 8.2 / 15.2 (Allegrex) | GCC 2.95.2 (EE probe) |
| --- | --- | --- | --- |
| `$ra` inside the frame | 1 to 4 slots below the top — 1524, 3033, 2133, 6798 | always on top, 15/15 and 16/16 | at frame − 16, 26/28 |
| frames a multiple of 16 | 13 494 of 13 495 | 15/20 and 13/20 | 28/28 |
| the `strcmp` at `0x00245504` | 13 slots, `lb`, `lbu`−`lbu`, no masking | 11 or 19 slots, masks with `andi` | 13 slots, same form, `beql` where the retail has `bnel` |

The rule of the retail code is the rule of an **old 64-bit MIPS GCC**: the
callee-saved registers are pushed first, at the bottom of a save area
aligned on sixteen bytes, and `$ra` is pushed last, just above them. A
modern GCC does not produce that, and the probe that reproduces it is the
Sony `ee-gcc` of the sibling PlayStation 2 projects.

The library is the **newlib 1.15 size variant**, the one selected by
`PREFER_SIZE_OVER_SPEED` — so it was built with `-Os`.

The standing hypothesis, **H1**: the retail build is a **GCC of the 3.x
line**, Allegrex target, **not** in the debug-C mode, with the library
compiled for size. It is falsifiable: the GCC 3.3 Allegrex is not built
yet, and if it replays neither the prologue rule nor the form of the
`strcmp`, H1 is false. The build recipe is written down, in
`work/TOOLCHAIN/scratch/legacy33/`.

**Hypothesis H1 is open, not proved.** The measurement is the advance; the
qualification is not.

### What wave 3 established

**Twenty lots of forty targets, each verified against the code**, and the
sweep corrected to follow the control-flow graph.

**661 distinct bodies reviewed. 661 confirmed as functions. None rejected,
none left unknown. 84 names recovered with evidence**, three of them
correcting a name of wave 2.

The sweep now agrees with the review on **99,4 %** of the bodies. It
follows the control-flow graph, and the graph reads the **jump tables**:
232 computed jumps met, 221 tables resolved, 2 488 cases followed, and not
one of them outside the body that holds it.

The wave also bought the **placement table**. When two bodies hold the
same bytes, the second is a placement of the first, and one authored
source satisfies both — 652 distinct bodies over 661, in eight groups. It
is a cross-check on the naming too: `quaternion_to_matrix` was found
independently by two lots, at `0x000A35A4` and at `0x000E9814`, and the
hash of the body proves that the two are the same body.

And five traps of the resolvers, each of which was producing a wrong
answer, each found by a lot:

* the register that is written is **dead** — a superseded `lui` must not
  pair with a later completion;
* the immediate of `addiu` is **signed**, and the unsigned value puts the
  address in the wrong page, where another string waits;
* a **code address can look like a string**: two bodies were "reading" a
  comma and a digit four, and both were code;
* the main opcode of `jal` is **3**, not `0x0C` which is `andi`, and the
  main opcode of `j` is **2**, not `0x08` which is `addi`;
* on the Allegrex, the **delay slot of a likely branch** is executed only
  if the branch is taken.

The four bodies the sweep still gets wrong contain no computed jump:
they stop on a **strong start** inside the body, which is a class of
error of its own, and it is written down rather than papered over.



The sweep now agrees with the review on **99,1 %** of the bodies, against
93,3 % before. The rule it implements is the one the review measured: *a
body ends at the last instruction its control-flow graph reaches, plus
four*. The residual error is the last class — a computed jump through a
register, whose targets are in a table the graph does not read.

The wave also bought the naming mechanism: the engine's assert helper at
`0x7035C` takes the name of the enclosing function in `$a3` — the C
`__FUNCTION__` — and the target has **344** call sites of it. 339 resolve,
into 73 distinct names over 82 bodies.

And it said what does not pay: the two hundred and fifteen bodies that
keep their address are methods of game classes whose class name appears
nowhere. There is no RTTI. Naming them would be inventing.

---

## What is not done

| Item | Why it is blocked |
| --- | --- |
| the layout of the whole code | 421 of the 11 452 called candidates have been reviewed; the lots L15 to L24 are cut and waiting |
| the toolchain profile | needs a layout and a sample body |
| the first matched body | needs the two above |
| most of the names | the symbol table is empty, and the class names of the game objects are nowhere in the binary |

---

## The open questions, in the order they block the work

1. **The toolchain.** Nothing is assumed about which compiler built the
   retail bytes; see `config/toolchain.json`. What *is* measured is the
   shape of the code: 16-byte stack slots with the return address on top of
   the frame, no `$gp`, and **no** GCC debug-C equality idiom — the last
   being a measured difference from the PlayStation 2 Ratchet & Clank boot
   build, which does carry it. The PSPSDK Allegrex toolchain is a GCC 3.3
   lineage. This is the last obstacle between the layout and the first
   matched body.
2. **The last error class of the sweep.** The four bodies the control-flow
   graph still gets wrong end at a **computed jump** through a register,
   whose targets are in a table the graph does not read. The graph has to
   read the table.
3. **The class names of the game objects.** There is no RTTI, and the
   names of the game classes are nowhere in the binary. The two hundred and
   fifteen bodies that keep their address are methods of those classes.
   The sibling projects cannot help — their catalogue is of a different
   build, of a different engine generation — and a name without evidence
   would be a lie in the source.

---

## The next concrete step

> **Qualify the compiler.** The decisive test is the **`strcmp` of the
> retail code at `0x00245504`**: its behaviour is known — it compares
> the bytes of two strings and returns the difference of the first
> differing bytes, with a *signed* comparison. That is a known idiom,
> and the exact shape of the code is a fingerprint of the compiler and
> of the library it was built against. Compile the equivalent with each
> candidate toolchain and compare the **shape**: the frame size, the
> slot width, what the delay slot holds, the form of the comparison.
> `tools/harness.py` is the tool that will compare the bytes once the
> shape is right.

Then the two pieces of work that are already cut: the lots **L15 to
L24**, four hundred more targets with the bodies of the previous waves
left out, and the **jump tables** of the control-flow graph, so that
the last error class of the sweep disappears.

After those, the **body gate** is reachable: the layout is there, the
harness is there, and only the compiler stands between the project and
its first matched body.


## The next concrete step

> **Two things, in this order.**

> 1. **Finish the assert resolver.** Take the 344 call sites of the
>    helper at `0x7035C`, resolve the `$a3` argument in every form it
>    takes — the direct literal, the pointer loaded from the string pool
>    at `0x00340000`, the callee-saved register that carries it — and
>    publish the names. This is the largest naming source the project
>    has, and it is the code telling us its own names.
>
> 2. **Review the next lots.** L07 to L12 are cut and waiting: two
>    hundred and forty more targets, with the corrected sweep. Same
>    protocol, same deliverables.

After those, the **toolchain** becomes the only thing left between the
layout and the first matched body.

---

## The numbers

| Measure | Value |
| --- | --- |
| files on the disc | 1 104 |
| Pack containers | 342 |
| blobs in those containers | 19 255 |
| code objects | 1 |
| bytes of code (`.text`) | 3 335 156 |
| instructions | 888 485 |
| source modules identified | 25, in 11 libraries |
| call targets | 11 497 |
| virtual calls (`jalr`) | 6 070 |
| bounded candidates | 19 062 |
| function candidates | 14 655 |
| of which saving the return address | 13 494 |
| **targets reviewed** | **421** |
| **confirmed as functions** | **421** |
| **names recovered** | **48** |
| assert call sites | 344, of which 339 resolve |
| distinct names from the asserts | 73 |
| functions matched | 0 |
| gates passed | 1 of 4 |
