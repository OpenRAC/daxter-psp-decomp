# The starter prompt

This is the prompt an agent reads before it works on this project, and the
prompt that launches a wave. It is meant to be pasted verbatim.

---

## The prompt

> You are working on **Daxter** for the PlayStation Portable, in the
> repository `OpenRAC/daxter-psp-decomp`. The goal is a **matching
> decompilation**: authored C/C++ that compiles to bytes identical to the
> retail executable.
>
> Read, in this order, and do not skip any of it:
>
> 1. `README.md` — what the project is and how the target is put together.
> 2. `AGENTS.md` — the ten working rules. They are not negotiable.
> 3. `docs/METHOD.md` — the wave protocol.
> 4. `docs/EVIDENCE.md` — what counts as a proof.
> 5. `docs/GATES.md` — the four gates, in order.
> 6. `docs/STATE.md` — where the project stands, and what to do next.
> 7. `docs/FORMATS.md` — the four container formats of the disc.
> 8. The lot brief you were given, under `work/lots/`.
>
> **The visibility gate comes first.** The retail executable on the disc is
> encrypted in a `~PSP` container. Until it has been decrypted locally, its
> structure measured with `tools/psp_elf.py`, and its hash recorded in
> `config/target.json`, **no function may be named, counted or claimed**.
> Check `config/target.json` before you start; if `decrypted_sha256` is
> still null, then the visibility gate is not passed and there is nothing
> for you to match yet — say so and stop.
>
> **Your lot.** You are given a shortlist of candidate functions, each with
> its address range, its size, and the number of placements that carry it.
> Write **one authored C/C++ definition per candidate**, in your own
> directory under `work/lots/<your-lot>/`, and prove each one by compiling
> it with the qualified toolchain of `config/toolchain.json`, linking it at
> the measured offset, and comparing **every byte** with the retail bytes.
>
> **The rules that matter most for you.** Pure C: no inline assembly, no
> raw instruction words, no fixed-register bindings, no edits to compiler
> output. One hypothesis at a time. After three attempts with the same
> mismatch class, stop, recover context, and park the best source with its
> first difference and a concrete reopening condition. Never commit disc
> images, executables, decrypted executables, extracted modules,
> instruction listings, disassembly, assets, SDK sources, or personal
> paths.
>
> **When you are done**, report, for each candidate: the source you wrote,
> the toolchain profile you used, whether the bytes matched, and if they did
> not, the first difference and what you think causes it. A body that
> matches but whose boundary you had to guess is **provisional** and you
> must say so. Do not count anything yourself.

---

## Why the prompt leads with the visibility gate

The sibling OpenRAC projects could open the retail executable on day one.
This one cannot. An agent that skips the gate will happily invent function
names from the strings and the file names of the disc, and produce a pull
request that looks like progress and is not.

The gate is cheap to check and impossible to fake: `config/target.json` has
a `decrypted_sha256` field, and it is either null or it is a hash.
