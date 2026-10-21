# Contributing

Contributions are welcome. Read [`AGENTS.md`](AGENTS.md) before opening an
issue or a pull request: it holds the ten working rules and the list of what
must never be committed.

## The public boundary

This repository publishes **written** source, reusable tools, research
metadata and documentation. It never publishes:

* disc images, retail executables, decrypted executables, extracted modules;
* instruction listings or disassembly;
* assets, artwork, audio, video, text, fonts;
* proprietary tools, compiler binaries, SDK sources or headers;
* leaked or NDA source;
* personal paths.

Obtain your own lawful copy of the game. The project cannot supply one, and
the local tooling and receipts stay on your machine.

## Before you open a pull request

```sh
python3 tools/check_repository.py
python3 -m unittest discover -s tests
python3 tools/progress.py
```

All three must pass. `check_repository.py` also refuses the change if a
forbidden file has been added, so read its output rather than skipping it.

## What a good pull request says

* which functions it claims, and at which placements;
* the toolchain profile used, and why that profile;
* what was verified, and what remains provisional;
* the first difference of every body that did not match, and the hypothesis
  about its cause;
* every change to a shared definition, and the evidence that forced it.

A pull request that says "matches" without a byte comparison is not
acceptable, and will be asked for one.

## Style

* Public text is English.
* C and C++ follow the style of the sibling projects: the surrounding code
  decides, and the code wins.
* Python follows PEP 8, with a type hint on every public function.
* Every tool gets a test in `tests/`, on synthetic data only.
* Every change to the format readers is a change to `docs/FORMATS.md` too.

## Committing

The repository integrates one writer at a time. Agents work in their own
lot directory under `work/` and do not commit to `src/`; the root integrates.

## Licence

Contributions are licensed under GPL-3.0, like the rest of the repository.
See [`LICENSE`](LICENSE) and [`THIRD_PARTY_NOTICES.md`](THIRD_PARTY_NOTICES.md).
