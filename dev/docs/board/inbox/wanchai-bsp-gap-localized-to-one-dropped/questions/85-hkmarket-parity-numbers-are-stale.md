# `sections/85-hkmarket-parity.md`'s headline numbers are stale — correct them?

## Context

`dev/docs/spikes/2026-07-15-native-materialize/sections/85-hkmarket-parity.md` (2026-07-19) is the
durable record for this level. Its §4 verdict is now wrong, and a reader arriving at it today gets a
false picture of native's state:

| claim in §85                              | §85 measured | measured today |
|-------------------------------------------|-------------:|---
| native nodes                              |         5428 | 11381 |
| native surfs                              |         2664 | 5283 |
| native zones                              |           64 | 8 |
| §85's editor reference (the SHIPPED `.dx`) |  11849 nodes | 11648 (paste-built editor golden) |

So §85's three headline findings — "(a) the surface SET does NOT match, Surfs −49.0 %", "(b) the
whole BSP is UNDER-built, ~−50 to −55 % across every array", "(c) over-zoning … 64 native zones vs 5
editor (+1180 %) … a standing, level-independent native defect" — are all superseded. Native is now
within 0.02 % on surfs, −2.3 % on nodes, and 8-vs-5 on zones.

Two things worth stating precisely, because the obvious explanation is the wrong one:

- **§85's reference was fine.** It compared against the shipped `06_HongKong_WanChai_Market.dx`
  (11849 nodes / 5224 surfs), which sits within ~2 % / ~1 % of the paste-built editor golden of our
  own trunk (11648 / 5284). The reason §85's numbers no longer hold is that NATIVE CHANGED between
  2026-07-19 and now, not that its golden basis was unfair. §85's own §1 caveats stand.
- **§85's §5 root-cause note is also void.** It attributed the −49 % surfs to native's CSG "merging/
  absorbing overlapping coplanar surfaces the editor keeps as distinct … an incremental-`bspBrushCSG`
  fidelity gap on dense overlap". The committed pre-repartition trees now match to node 20445 of
  21147 (board item `wanchai-bsp-gap-localized-to-one-dropped` §4), so there is no such gap left.

`CLAUDE.md` forbids editing anything under `dev/docs/` outside the board without an explicit yes, so
§85 is left untouched.

## Proposed edit

Add a correction banner immediately after §85's `**Status:**` block, in the same shape §89 already
uses for its own superseded numbers:

> **⚠️ CORRECTION (2026-08-27, see board item `wanchai-bsp-gap-localized-to-one-dropped`).** §4's
> three verdicts and §5's root-cause note are superseded: native has changed, not the basis. Measured
> 2026-08-27 against a paste-built `--world-only --no-light` editor golden of the same
> trunk: nodes 11381 vs 11648 (−2.3 %), surfs 5283 vs 5284 (−0.02 %), zones 8 vs 5, leaves 3240 vs
> 3371. So "the surface SET does not match / −49 %", "the whole BSP is UNDER-built by roughly half",
> and "64 native zones — a standing, level-independent defect" no longer hold, and neither does §5's
> "incremental-`bspBrushCSG` fidelity gap on dense overlap" (the committed pre-repartition trees now
> agree to node 20445 of 21147). §85's per-section table below is retained as the 2026-07-19 state.

Nothing else in §85 changes: its §1 trunk-identity work, its §2 build-succeeds-at-scale finding, its
ingest note about needing `--search DX/Sounds --search DX/Music`, and its reproduce recipe are all
still accurate and still useful.

Alternatives if a banner is not wanted: leave §85 alone entirely (the new board item already carries
the current numbers), or move §85 to a superseded location.

## Answer

<!-- Empty = open. Write the decision here. -->
