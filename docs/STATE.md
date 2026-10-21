# State

The anchor: where the project stands, and what to do next.

**Target:** *Daxter* (USA), PSP, title id `UCUS98618`, disc version 1.00.
**Status:** `in-progress`. The visibility gate is passed. No function has
been matched.

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
| **the function candidates are inventoried** | 14 655 frame openings, 8 794 of them saving the return address | `config/boot/functions.tsv` |
| the readers are tested | synthetic fixtures, no game data in the tests | `tests/test_tools.py` |

### The decryption

The executable is a **type 1 PSP PRX** behind the `~PSP` container, tag
`0xC0CB167C`, decrypt mode 9. The decryption is implemented in this
repository, in Python, from the published description of the format:

```sh
python3 tools/decrypt_psp.py <EBOOT.BIN> <decrypted.elf>
python3 tools/boot_inventory.py --elf <decrypted.elf> --out config
```

The key material is in `tools/psp_crypto.py`; its provenance is in
`THIRD_PARTY_NOTICES.md`. The decrypted ELF is **never committed**: only the
structure it yields is.

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
* `BOOT.BIN` is **entirely zeroed** and exactly the size of the
  decrypted ELF: it is the buffer the firmware decrypts into, not another
  version of the program.

---

## What is not done

| Item | Why it is blocked |
| --- | --- |
| the layout of the code | the function boundaries are not known yet |
| the toolchain profile | needs a layout and a sample body |
| the first matched body | needs the two above |
| the names of the functions | the symbol table is empty; the names have to come from the code, from the strings, or from the sibling PS2 games |

---

## The open questions, in the order they block the work

1. **Which of the 14 655 frame openings are functions?** This is the
   assembly baseline the method calls for, and it is the whole of the next
   phase. A frame is not a function: the review has to establish, for each
   candidate, that it is entered from a call, that it returns, and where it
   ends.
2. **Which toolchain can reproduce the retail bytes?** Nothing is assumed
   here; see `config/toolchain.json`. The candidates are the Allegrex GCC
   and the PSPSDK toolchain.
3. **Where do the names come from?** The PS2 games of the same studio share
   the engine and most of the engine's function names: `GLOBAL_GetFlagBit`,
   `LEVEL_RequestRestart`, `TEXMGR_GetWidth`, `AglSubMeshMgr` and the
   rest. `OpenRAC/rac-sac-decomp` already has a catalogue of them for
   *Secret Agent Clank*, which is the same engine on the same processor.
   That is a large, legitimate head start, and it has to be **proved**
   against this target rather than assumed.
4. **The disc key.** The `PSAR` archive of the firmware updater stays
   unreadable without it, and it is the only thing left on the disc that
   the readers cannot reach.

---

## The next concrete step

> Take the first hundred candidates of `config/boot/functions.tsv`, and
> establish which of them are functions: entered from a call, returning
> through `$ra`, bounded by a known terminator. Publish the result as the
> first **assembly baseline** of the project, with the measured boundary of
> each body.

That is the phase the sibling projects call *layout*, and it is what turns
14 655 candidates into a work list.

---

## The numbers

| Measure | Value |
| --- | --- |
| files on the disc | 1 104 |
| Pack containers | 342 |
| blobs in those containers | 19 255 |
| code objects | 1 |
| bytes of code (`.text`) | 3 335 156 |
| function candidates | 14 655 |
| of which saving the return address | 8 794 |
| functions matched | 0 |
| functions named | 0 |
| gates passed | 1 of 4 |
