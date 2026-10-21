# State

The anchor: where the project stands, and what to do next.

**Target:** *Daxter* (USA), PSP, title id `UCUS98618`, disc version 1.00.
**Status:** `exploring`. No function has been matched.

---

## What is done

| Item | Evidence | Where |
| --- | --- | --- |
| the disc is pinned | SHA-1 `6a54c86d…282cb`, SHA-256 `648e237a…59f4`, 1 405 845 504 bytes | `config/target.json` |
| the disc is inventoried | 1 104 files, 342 Pack containers | `config/disc/containers.tsv`, `config/disc/pack_index.tsv` |
| the target identity is read from the disc itself | `UCUS98618`, `UG`, `1.00`, region `0x8000`, firmware `2.60` | `tools/psp_formats.py` |
| four container formats are read and documented | `PARAM.SFO`, `~PSP`, `PSAR`, `Pack` | `docs/FORMATS.md` |
| the readers are tested | synthetic fixtures, no game data in the tests | `tests/test_tools.py` |
| the binary layout is settled | the code is one monolithic executable, not a loader plus overlays | `docs/FORMATS.md` §5 |

## What is not done

| Item | Why it is blocked |
| --- | --- |
| the decrypted executable | the `~PSP` payload needs a PSP implementation and a lawful local copy; the result stays local |
| the section and symbol tables | need the decrypted executable |
| the function inventory | need the decrypted executable |
| the toolchain profile | need the layout and a sample body |
| the first matched body | needs the two above |

---

## The open questions, in the order they block the work

1. **How is the `~PSP` payload laid out, and how is the disc key derived?**
   The header parameter at `0x04` differs between the disc executable
   (`0x00000000`) and the update executable (`0x00000800`), so it is not a
   common payload offset. In the meantime, the decryption is delegated to a
   local PPSSPP build, which is known to work on this target.
2. **What is `BOOT.BIN`?** It is 351 bytes smaller than `EBOOT.BIN`, starts
   with 0x30 zero bytes and is not an ELF. Is it the pre-encryption image,
   a template, or something else? It may be the cheapest possible route to
   a readable executable and deserves a look before anything else.
3. **Is the base executable the right target, or the update one?** The
   update executable is 998 680 bytes smaller and has the module name
   `update`. The update folder is the later revision; mixing the two would
   corrupt every comparison.
4. **Which Allegrex toolchain can reproduce the retail bytes?** Nothing is
   assumed here; see `config/toolchain.json`.
5. **What are the five header words of `Pack`, and the three words of the
   `CfCm` header?** Not blocking the decompilation, but they are what the
   asset side of the project needs.

---

## The next concrete step

> Install a local PPSSPP build, decrypt `PSP_GAME/SYSDIR/EBOOT.BIN` on a
> lawful copy, run `tools/psp_elf.py` on the result, and publish the
> **structure**: the section table, the symbol table and the function
> inventory, together with the SHA-256 of the decrypted executable written
> into `config/target.json`.

That single step unblocks everything else. It is the highest-leverage
action available, and it is the one thing this repository cannot do on the
contributor's behalf.

---

## The numbers

| Measure | Value |
| --- | --- |
| files on the disc | 1 104 |
| Pack containers | 342 |
| blobs in those containers | 19 255 |
| code objects | 1 |
| functions matched | 0 |
| functions named | 0 |
| gates passed | 0 of 4 |
