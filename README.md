# Daxter (PSP) — matching decompilation

A matching-decompilation workspace for **Daxter** for the PlayStation
Portable (Insomniac Games, 2006, title id `UCUS98618`, disc version 1.00).

The goal is to rebuild the retail program in **C/C++ compiled**, with a
proof: the bytes the qualified toolchain produces must be **identical** to the
retail bytes, at every applicable placement, and the complete program must
still hash to the pinned retail hash.

This repository holds the **method, the rules, the templates and the tooling**,
plus the first measured results: the disc is pinned, its four container
formats are read and documented, and its 342 asset containers are
inventoried. No function has been matched yet: see [`docs/STATE.md`](docs/STATE.md).

## Start here

| Document | What it gives you |
| --- | --- |
| [PROMPT.md](PROMPT.md) | the **starter prompt** — what an agent reads, and the prompt that launches a wave |
| [AGENTS.md](AGENTS.md) | the ten working rules, and what must never be committed |
| [docs/METHOD.md](docs/METHOD.md) | the wave protocol, from the foundation lot to the pull request |
| [docs/EVIDENCE.md](docs/EVIDENCE.md) | what counts as a proof, and what does not |
| [docs/GATES.md](docs/GATES.md) | the three gates: the body gate, the placement gate, the complete-program gate |
| [docs/STATE.md](docs/STATE.md) | the anchor: where the project stands, and what to do next |
| [docs/FORMATS.md](docs/FORMATS.md) | the **disc formats** of the target: `PARAM.SFO`, `~PSP`, `PSAR`, `Pack` |
| [docs/REUSE.md](docs/REUSE.md) | what to take from the sibling OpenRAC projects, and what not to |

## Layout

| Path | Role |
| --- | --- |
| `src/` | accepted authored C/C++ definitions, one per function |
| `src/boot/bodies/` | the proved bodies of the executable |
| `src/levels/bodies/` | the proved bodies of the asset-derived modules, when they exist |
| `nonmatching/` | useful but nonmatching attempts, indexed by function |
| `tools/` | reusable tools, with tests |
| `tests/` | the unit tests of the tools, on synthetic data only |
| `config/` | pinned metadata: target identity, toolchain profiles, disc and asset catalogues |
| `config/disc/` | the container manifest and the Pack index of the pinned disc |
| `config/levels/` | the asset-container catalogues |
| `docs/` | the method, the evidence standard, the gates, the formats, the anchor |
| `work/` | the private workspace: modules, bounds, lots, agent dossiers (git-ignored except the templates) |

## How Daxter for PSP is actually put together

This is the part that differs from the PlayStation 2 games of the same
studio, and it decides the whole shape of the work.

On the PS2 games, the retail executable is a small **loader**, and the game
code lives in **packed level overlays** that the loader maps in at run time.
That is why `OpenRAC/rac-deadlocked-decomp` spends its first phase on
unpacking, splitting and disassembling the overlays.

**Daxter for PSP does not work that way.** Measured on the pinned disc:

* the game code is **one monolithic executable**, `PSP_GAME/SYSDIR/EBOOT.BIN`,
  4 949 392 bytes, module name `dax`;
* that executable is stored **encrypted**, in the `~PSP` container, and has to
  be decrypted before it can be read as an Allegrex ELF;
* the 342 files under `PSP_GAME/USRDIR/data` are **assets only**. They are
  `Pack` containers holding meshes (`CfCm`), lighting data (`RADI`), float
  tables and texture pages. A scan of every blob for Allegrex function
  prologues and for PSP-range addresses finds **none**: there is no code in
  them.

The practical consequence is a simplification, not a complication: there is
one code object to qualify instead of forty-eight, and the asset side of the
project is a research problem, not a decompilation problem.

## The pipeline

```
  Daxter.iso  (1 405 845 504 bytes, SHA-1 6a54c86d…282cb)
        |
        |  mount or extract
        v
  PSP_GAME/SYSDIR/EBOOT.BIN          ~PSP encrypted executable
        |
        |  decrypt  (PPSSPP pspDecryptPRX, or an equivalent implementation)
        v
  decrypted.elf                      Allegrex ELF, MIPS32r2, little-endian
        |
        |  tools/psp_elf.py            structure only
        v
  sections, symbols, function inventory
        |
        |  compile with a qualified Allegrex toolchain
        v
  byte-identical executable?         the complete-program gate
```

The asset side runs in parallel and never touches the code:

```
  PSP_GAME/USRDIR/data/*.bin         342 Pack containers
        |
        |  tools/disc_inventory.py
        v
  config/disc/pack_index.tsv         index, sizes, hashes, type census
```

### Step 1 — decrypt the executable

`~PSP` uses a key derived from the disc identifier. The pragmatic route is a
local PPSSPP build, which exports the routine the project
[`anthonyhfm/daxter-recompiled`](https://github.com/anthonyhfm/daxter-recompiled)
already uses:

```c
int pspDecryptPRX(const unsigned char *encrypted,
                   unsigned char *output,
                   unsigned int size,
                   const unsigned char *key);
```

`tools/psp_formats.py` refuses to read a `~PSP` blob and says so; the
decrypted ELF is then read by `tools/psp_elf.py`.

### Step 2 — read the structure

```sh
python3 tools/psp_formats.py  <file>            # any of the four containers
python3 tools/psp_elf.py      <decrypted.elf>   # sections, programs, entry
python3 tools/psp_elf.py      <decrypted.elf> --functions --tsv
```

### Step 3 — qualify a toolchain

A byte-identical build needs the compiler the game was built with, or a
measured equivalent. `config/toolchain.json` records the candidate profiles
and the evidence each one rests on. The PS2 projects could not use a modern
GCC; the Allegrex situation has to be measured the same way, not assumed.

### Step 4 — match the functions

One authored C/C++ definition per function in `src/`, proved by compiling,
linking at the measured offset and comparing every byte with the retail
bytes. The body gate, the placement gate and the complete-program gate are
defined in `docs/GATES.md`.

## Tools

| Tool | Role |
| --- | --- |
| `tools/psp_formats.py` | readers for `PARAM.SFO`, `~PSP`, `PSAR` and `Pack` |
| `tools/psp_elf.py` | structure and function listing of an Allegrex ELF |
| `tools/disc_inventory.py` | the disc manifest and the Pack index, with a `--check` mode |
| `tools/check_repository.py` | the structural invariants of the repository |
| `tools/progress.py` | the progress snapshot |

```sh
python3 -m unittest discover -s tests
python3 tools/check_repository.py
python3 tools/progress.py
```

## Public boundary

This repository publishes **written** source, reusable tools, research
metadata (names, addresses, hashes, counts) and documentation. It never
publishes disc images, retail executables, decrypted executables, extracted
modules, instruction listings, disassembly, assets, proprietary toolchains,
SDK sources, or leaked or NDA source. See `AGENTS.md` and `LEGAL.md`.

Obtain your own lawful copy of the game; the project cannot supply one, and
the local tooling and receipts stay on your machine.

## Licence

The independently authored material here is GPL-3.0, like the sibling
projects; see `LICENSE`. That licence does not cover the game, its assets or
any proprietary toolchain. Contributions should be original or compatible with
that licence, with attribution where required.
