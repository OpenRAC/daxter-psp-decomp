# Lot brief

<!--
The brief an agent receives for its lot. It is filled by the root, from the
shortlist, and it is the only thing the agent needs besides the documents
the starter prompt lists.
-->

## The lot

- **id:** `L<number>`
- **target:** the single object this lot attacks (the executable, the boot
  module, one asset family)
- **visibility gate:** passed / not passed — and the evidence
- **toolchain profile:** the id from `config/toolchain.json`

## The candidates

| Candidate | Address range | Size | Placements | Note |
| --- | --- | --- | --- | --- |
| | | | | |

The address range is a **measurement**, not an estimate. A range whose
boundary is not justified is provisional and is not counted.

## The hypothesis

<!--
One sentence. What do you believe these bodies are, and why? If you cannot
state it, say so: a lot without a hypothesis is a fishing expedition, and
the siblings' method forbids it.
-->

## The method

1. Write one authored C/C++ definition per candidate, in
   `work/lots/<lot-id>/`.
2. Compile with the profile above, link at the measured offset, and compare
   **every byte** with the retail bytes.
3. For each body: matched, or the first difference and the hypothesis about
   its cause.
4. After three attempts with the same mismatch class: stop, recover context,
   and park the best source with a concrete reopening condition.

## The budget

<!--
How many candidates, and how many attempts each. The siblings keep the lots
small enough that an agent finishes them.
-->

## The report

For each candidate, report: the source, the profile used, whether the bytes
matched, and if not, the first difference and the suspected cause. Mark a
body as **provisional** when it matches but its boundary was guessed. Count
nothing yourself.
