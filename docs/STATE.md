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
| **the layout is established** | 421 targets reviewed, 421 confirmed as functions, 48 named | `config/boot/layout.tsv` |
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

Fourteen lots of forty targets, each verified against the code, and the
sweep corrected to follow the control-flow graph.

**421 distinct bodies reviewed. 421 confirmed as functions. None rejected,
none left unknown. 48 names recovered with evidence**, three of them
correcting a name of wave 1.

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

> **The toolchain, and the rest of the layout.**

> 1. **Qualify the compiler.** The decisive test is the **`strcmp` of the
>    retail code at `0x00245504`**: its behaviour is known — it compares
>    the bytes of two strings and returns the difference of the first
>    differing bytes, with a *signed* comparison. That is a known idiom,
>    and the exact shape of the code is a fingerprint of the compiler and
>    the library it was built against. Compile the equivalent with each
>    candidate toolchain and compare the **shape**: the frame size, the
>    slot width, what the delay slot holds, the form of the comparison.
>    `tools/harness.py` is the tool that will compare the bytes when the
>    shape is right.
>
> 2. **Review the lots L15 to L24.** They are cut, with the bodies of the
>    previous waves left out: four hundred more targets, same protocol.
>
> 3. **Read the jump tables** in the control-flow graph, so that the last
>    error class of the sweep disappears.

After those, the **body gate** is reachable: the layout is there, the
harness is there, and only the compiler stands between the project and its
first matched body.

---

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
