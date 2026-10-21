# Legal

## What this repository is

An open-source workspace for the **reverse engineering, preservation and
matching decompilation** of *Daxter* for the PlayStation Portable.

## What this repository is not

* It is **not** a copy of the game. No disc image, executable, asset,
  artwork, audio, video, text, font, or trademark is published here.
* It is **not** an endorsement, authorisation, sponsorship or partnership of
  Sony Interactive Entertainment, Insomniac Games, Ready at Dawn, or any
  other publisher, developer or rightsholder.
* It is **not** a playable copy of the game. Nothing here can be run to
  reproduce the game without the user's own lawful copy of the disc and the
  user's own tools.

## What the authors may publish

The authors of this repository may publish only material they wrote
themselves:

* written source code;
* reusable tools;
* research metadata — names, addresses, sizes, hashes, counts, offsets,
  container layouts — that they derived by measuring a copy of the game they
  lawfully own;
* documentation.

That is what the repository contains. The tools read **structure** and
deliberately never emit payload bytes, so their output is publishable.

## What the authors may not publish

* the disc image, or any part of it;
* the retail executable, the decrypted executable, or any extracted module;
* instruction listings or disassembly of the retail executable;
* assets, or any part of them;
* proprietary toolchains, SDK sources or headers;
* leaked, NDA-protected or otherwise unauthorised source;
* personal paths of any contributor.

`tools/check_repository.py` enforces the mechanical part of this list on
every commit, and `AGENTS.md` states the rest.

## Reverse engineering and interoperability

Reverse engineering for interoperability and preservation is lawful in many
jurisdictions, and this project exists for those purposes: to preserve a
game that is no longer sold, and to let the people who love it keep it
running. **The law of your own country applies to you**, and you are
responsible for having a lawful copy of the game and for what you do with it.

Nothing in this repository is legal advice.

## The licence, and what it does not cover

The independently authored material here is licensed under the **GNU General
Public License, version 3 or later**; see [`LICENSE`](LICENSE). Third-party
components keep their own licences; see
[`THIRD_PARTY_NOTICES.md`](THIRD_PARTY_NOTICES.md).

The GPL does **not** license *Daxter*, its code, its assets, its artwork,
its audio, its video, its text, its characters, its logos, or its
trademarks. It does not license any proprietary toolchain. Those remain
with their respective owners.

## Attribution

If you reuse the tools or the format documentation of this repository, keep
the attribution: the `OpenRAC` organisation, the GPL-3.0 licence, and the
provenance of the sibling projects named in
[`docs/REUSE.md`](docs/REUSE.md).
