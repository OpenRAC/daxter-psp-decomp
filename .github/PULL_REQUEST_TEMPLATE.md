## What this pull request claims

<!-- The functions it claims, and at which placements. -->

## The toolchain profile used

<!-- The id from config/toolchain.json, and why that profile. -->

## What was verified

<!-- The byte comparisons that were actually run, and their result. -->

## What remains provisional

<!-- Bodies that match but whose boundary was guessed. Say "none" if there are none. -->

## The first differences

<!-- For every body that did not match: the first difference, and the
     hypothesis about its cause. A pull request without this section is
     incomplete. -->

## Changes to shared definitions

<!-- Every change to a shared header, a type, a field size or a prototype,
     and the evidence that forced it. -->

## Checks

- [ ] `python3 tools/check_repository.py`
- [ ] `python3 -m unittest discover -s tests`
- [ ] `python3 tools/progress.py`
- [ ] the diff contains no disc image, no executable, no decrypted
      executable, no instruction listing, no asset, and no personal path
