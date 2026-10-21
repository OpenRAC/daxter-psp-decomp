# The private workspace

Everything in this directory is **private to your machine** and is never
committed, with the exception of the templates.

`work/` is where the material that must not be published lives: the
extracted modules, the measured bounds, the candidate shortlists, the lots
an agent works on, and the dossiers that describe them. The `.gitignore`
keeps all of it out of the repository; `tools/check_repository.py` refuses
a commit that contains a forbidden file even if the ignore rule was broken.

## Layout

| Path | Role |
| --- | --- |
| `work/E0/` | the foundation lot: the extraction, the pinned identity, the first shortlist |
| `work/lots/` | one directory per lot, one agent per lot |
| `work/templates/` | the tracked templates a lot is built from |
| `work/decrypted/` | the decrypted executable, if you produce one. **Never commit it.** |
| `work/modules/` | the extracted modules, if you produce any. **Never commit them.** |

## The rules

1. One writer in the clone: only the root integrates into `src/`.
2. An agent writes in its own lot directory and nothing else.
3. Nothing under `work/` is ever published, including by accident: the
   ignore rules cover it, but the guard is reading your own diff.

See `AGENTS.md` for the ten working rules, and `docs/METHOD.md` for the
protocol that uses this workspace.
