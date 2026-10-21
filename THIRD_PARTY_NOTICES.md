# Third-party notices

The independently authored material of this repository is licensed under the
GNU General Public License, version 3 or later; see `LICENSE`. This file
records the material that comes from elsewhere, and the material that is
referenced but **not** vendored here.

## Vendored

Nothing is vendored. The repository contains no third-party source code.

## Adapted

### `tools/psp_elf.py`

The structure of the reader — the header validation, the program and section
reporting, the function listing restricted to the symbols that carry a size
— follows the ELF readers of the sibling OpenRAC projects
(`OpenRAC/rac-sac-decomp`, `OpenRAC/rac5-sm-decomp`), which are themselves
GPL-3.0. The reader here is written for the Allegrex and accepts the
`~PSP` container case explicitly.

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

The PSP static-recompilation toolchain. It establishes both the decryption
route and the expectation that the Allegrex code can be recompiled. No code
is copied here.

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
