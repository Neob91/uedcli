+++
priority = "p2"
kind = "debug"
summary = "DONE — not a divergence at all. The 941-against-940 Model.Lights bail came from a stale wheel (cargo skipped the rebuild); a real build of any of the six revisions blamed for it passes."
spikes = ["dev/docs/spikes/2026-09-07-native-ext-build-staleness/"]
+++

# UNATCO N=116 — the bail was a stale binary, not leaf 9

## DONE 2026-09-07

`ladder_run.py --dx 03_NYC_UNATCOHQ.dx --from 116 --to 116` PASSES, and the level walks to **N=162**
(bails at N=163, a different item). No code change closed it and none was needed.

This item first read the failure as real native output from a differently-compiled binary, and then
as a codegen-sensitive near-tie. Both are wrong. Cargo decides freshness by MTIME, so the crate
copies used to test each revision — restored with `git archive`/`tar`, which carry older timestamps —
were never recompiled: every run used one stale wheel. The six N=116 packages filed under six
different commits are byte-identical modulo the package GUID, which six materially different sources
cannot be. Rebuilt properly, `59ada80e` gives a different `.so` and the 940-light PASS package.
Root cause, forensics and the fix: `native-ext-binary-not-stable-across-builds`,
`dev/docs/spikes/2026-09-07-native-ext-build-staleness/`.

## What the stale build actually produced

Only the lighting differed (`bbox sphere vectors points nodes surfs verts zones bounds leafhulls
lightbits` all SAME; `leaves lightmap lights` DIFF). `Model.Lights` 941 vs 940: one extra entry at
index 40, light 74 prepended to **leaf 9**'s run `[31, 30, 28]`, shifting every later leaf's
`iPermeating` by +1 and every later `LightMap` record's `iLightActors` with it. That shift is what
the original report read as "13 of 214 lightmaps differ in both directions" — one insertion, not
thirteen decisions. A current build never brings light 74 adjacent to leaf 9 at all.

The flood does contain genuine knife-edges — leaf 9's closest near-miss is one f32 ULP from flipping
— but they are build-invariant, so they are not this. Detail in the spike.
