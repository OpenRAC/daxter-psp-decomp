# Reuse

What to take from the sibling OpenRAC projects, and what not to. This
project is a PSP target inside a PS2-centric organisation; the difference in
platform changes more than it looks.

## The siblings

| Project | Platform | Language | Note |
| --- | --- | --- | --- |
| `rac1-decomp` | PS2 | C | the original Ratchet & Clank, PAL |
| `rac2-gc-decomp` | PS2 | C | Going Commando, USA |
| `rac3-uya-decomp` | PS2 | C | Up Your Arsenal |
| `rac-deadlocked-decomp` | PS2 | C | the closest in shape: loader plus packed overlays |
| `rac5-sm-decomp` | PS2 | Python | Size Matters |
| `rac-sac-decomp` | **PSP** | Python | **Secret Agent Clank — the direct model** |

---

## Take

**The layout and the discipline.** `rac-sac-decomp` is the model, because it
is the other PSP target of the same studio. Its structure is reproduced
here almost unchanged:

```
config/       pinned metadata and catalogues
docs/         the method, the evidence standard, the gates, the anchor
src/          one authored file per proved function
nonmatching/  the parked attempts, indexed by function
tools/        the reusable tools, with tests
tests/        the unit tests, on synthetic data only
work/         the private workspace and the agent templates
```

**The evidence standard.** The ten working rules of `AGENTS.md`, the three
gates of `docs/GATES.md`, and the distinction between *proved* and
*provisional* come straight from the siblings and are not renegotiated here.

**The `~PSP` decryption route.** `anthonyhfm/daxter-recompiled` and the
`psprism` toolchain both decrypt a `~PSP` executable with a local PPSSPP
build. That route is adopted; the code is not vendored, it is called.

**The reading of the disc.** `caws/daxtertoolset` unpacks the `Pack`
containers of this very game and converts the text blobs. Its format
reading agrees with the one in `docs/FORMATS.md`; its tools are C# and its
output is a flat directory of blobs, which is not what this project wants.
The format was re-measured here rather than inherited, and the readers were
rewritten in Python with tests.

---

## Do not take

**The compilers.** The PS2 projects fight a R5900 and its register modes;
their toolchain profiles say nothing about the Allegrex. `config/toolchain.json`
starts empty on purpose.

**The "loader plus overlays" layout.** This is the trap. On PS2 the code
sits in packed level overlays, and the first phase of `rac-deadlocked-decomp`
is to unpack and split them. **Daxter for PSP does not work that way**: the
code is one monolithic executable, and the asset containers hold no code at
all. The measurement is in `docs/FORMATS.md` §5. A contributor coming from
the PS2 projects will otherwise spend weeks unpacking meshes.

**The `.recomp.json` `toolchain` field.** `PSPRecomp` is the right family
of tools, but nothing here is built with it yet, so it is listed as a
candidate rather than as the toolchain of record.

**The naming of the phases.** The siblings' phases are about *overlays*;
the phases here are about *visibility* and *layout*, because the code is not
readable on the disc.

---

## The one difference that shapes everything

The PS2 siblings could open the retail executable on day one and start
disassembling. This project cannot: the executable on the disc is encrypted.

That is why `docs/GATES.md` opens with a **visibility gate** that the
siblings do not need, and why `docs/STATE.md` ends with a single concrete
next step rather than a list of functions to match.

The lesson from the siblings that applies here is their own: the hard part
of a matching decompilation is not the assembly, it is the **layout and the
toolchain**. The difference is that here both have to be earned before a
single instruction can be read.
