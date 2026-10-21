# Third-party notices

The independently authored material of this repository is licensed under the
GNU General Public License, version 3 or later; see `LICENSE`. This file
records the material that comes from elsewhere, and the material that is
referenced but **not** vendored here.

## Vendored

### `tools/psp_crypto.py` — the KIRK key material

The key vault of the KIRK engine (128 AES-128 keys, indexed by key slot),
the KIRK1 key, and the per-tag seed blocks of the retail executables.

* Origin: **PPSSPP**, the open-source reference implementation of the PSP
  (`ext/libkirk/kirk_engine.c` and `Core/ELF/PrxDecrypter.cpp`), which took
  them from the **JPCSP** and **PSARDUMPER** projects.
* Licence of the original: **GPL-2.0-or-later**.
* Licence here: the file carries the GPL-3.0-or-later of this repository.
  The GPL-2.0-or-later licence of PPSSPP permits that: a derivative of a
  GPL-2.0-or-later work may be distributed under the GPL-3.

The file is data, not code: a table of keys and a description of where each
one sits. It is vendored because the decryption needs it and because
fetching it from a checkout of PPSSPP at run time would make the tool
depend on a repository it has no business depending on.

Everything else in `tools/` is this project's own work.

## Adapted

### `tools/psp_elf.py`

The structure of the reader — the header validation, the program and section
reporting — follows the ELF readers of the sibling OpenRAC projects
(`OpenRAC/rac-sac-decomp`, `OpenRAC/rac5-sm-decomp`), which are themselves
GPL-3.0. The reader here is written for the Allegrex, accepts the PSP PRX
type `0xFFA0`, and copes with an executable that has no symbols.

Attribution: the `OpenRAC` organisation.

## Referenced, not vendored

### `anthonyhfm/daxter-recompiled`

* <https://github.com/anthonyhfm/daxter-recompiled>
* Licence: GPL-3.0 (the project skeleton and its authored patches).

The sibling project for the same game, by the same studio. It is a
**static recompilation**, not a matching decompilation. Its `psprism`
toolchain establishes the `~PSP` decryption route this project adopts. No
code is copied here; the route is *called*.

### `anthonyhfm/psprism`

* <https://github.com/anthonyhfm/psprism>
* Licence: GPL-3.0.

The PSP static-recompilation toolchain. It establishes that the Allegrex
code of this game can be recompiled. No code is copied here.

### `PPSSPP`

* <https://github.com/hrydgard/ppsspp>
* Licence: GPL-2.0-or-later.

The reference implementation of the PSP. Its `Core/ELF/PrxDecrypter.cpp`
and `ext/libkirk` describe the `~PSP` container, the PRX types and the KIRK
primitives, and its key vault is vendored in `tools/psp_crypto.py` as
described above.

Its release build does **not** export `pspDecryptPRX`, so the decryption
could not simply be called: the release exports only two vendor symbols.
That is why this project implements the algorithm itself.

### `caws/daxtertoolset`

* <https://github.com/caws/daxtertoolset>
* Licence: as stated in the repository (no licence file was published with
  it at the time of writing).

The toolset that unpacks the `Pack` containers of this very game and
converts its text blobs. Its reading of the container agrees with the one
measured here. **No code is copied here**; the format was re-measured and
the readers were rewritten in Python with tests.

### `PPSSPP`

* <https://github.com/hrydgard/ppsspp>
* Licence: GPL-2.0-or-later.

The reference implementation of the PSP. Its `pspDecryptPRX` routine is the
documented route for decrypting a `~PSP` executable. It is **called as an
external program or shared library** on the user's machine; it is not
vendored, linked or modified here.

### `PPSSPP` (continued)

The `PSAR` format of the firmware updater, and the reading of the `~PSP`
header, follow `docs/PsarFileFormat.md` of PPSSPP and the description of
the PRX types in `Core/ELF/PrxDecrypter.h`.

### `OpenRAC` sibling projects

* `rac1-decomp`, `rac2-gc-decomp`, `rac3-uya-decomp`, `rac-deadlocked-decomp`,
  `rac5-sm-decomp`, `rac-sac-decomp` — <https://github.com/OpenRAC>
* Licence: GPL-3.0.

The method, the evidence standard, the gates and the source layout of this
repository come from these projects. See `docs/REUSE.md` for what is taken
and what is not.

## Trademarks

*Daxter*, *Ratchet & Clank*, *Jak & Daxter*, PlayStation, PlayStation
Portable, PSP and Insomniac Games are trademarks of their respective
owners. Their use here is nominative: to identify the target of the
reverse engineering.

## The game

*Daxter* for the PlayStation Portable, developed by Insomniac Games and
published by Sony Computer Entertainment America in 2006, is **not**
distributed by this repository and is **not** covered by its licence.
