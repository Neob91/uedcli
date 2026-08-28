# TryToMerge step 3: use the NEAR threshold (0.015) instead of SAME (0.002) for the neighbour test

## Context

The Wanchai +2/+20 gap (this item) is a `try_to_merge` seam-tolerance miss on two same-ilink coplanar
fragment pairs whose seam corners differ by `0.00439` (provenance: Brush754's `PostScale Y=4.499965`
puts a genuine fractional door-face plane at `y=-768.0044`; the upper z-band fragment is bounded at
`y=-768.0` by the door jamb). `try_to_merge` step 3's forward/backward neighbour test uses
`points_are_same` (`THRESH_POINTS_ARE_SAME`=0.002), so the 0.00439 gap refuses the merge.

Proposed change (one switch, `uedcli-native/src/bspcsg.rs`): in step 3, use a NEAR box coincidence test
at `THRESH_POINTS_ARE_NEAR` (0.015) instead of `points_are_same` for the *neighbour* test only — step 2
(find-first-coincident) stays at SAME. `THRESH_POINTS_ARE_NEAR = 0.015` is already an engine constant
(`build.rs:18`), and the codebase already uses the SAME-vs-NEAR dichotomy (`build.rs:37-42`), so this
reuses existing semantics rather than introducing a magic number.

Measured with the switch (research-only, current tree, threw away after):

| | baseline | with switch | editor |
|---|---:|---:|---:|
| Wanchai soup | 8189 | 8187 | 8187 |
| Wanchai nodes | 11668 | 11648 | 11648 |
| Wanchai surfs | 5284 | 5284 | 5284 |
| Wanchai points | 16819 | 16807 | 16791 (: +16 residual) |
| UNATCO nodes/surfs/points | 6314/3616/10758 | 6314/3616/10758 | 6314/3616/10758 |

The fused west poly becomes exactly the editor's captured pentagon (keeps both `-768.00439` and `-768`
corners) through the existing `remove_colinears`, no vertex rewriting. The +2 and +20 close in one
switch; UNATCO is unchanged (no over-fusion on the other gated level). Tolerance 0.005..0.05 all give
the same result, so this is not sensitivity-tuned.

Two caveats, why this is your call, not an implementer's:

1. The NEAR-threshold attribution to the editor is inferred from the editor's own output (native with
   the switch matches the editor byte-for-byte on soup/nodes/surfs on both gated levels). It is a strong
   hypothesis from current-tree measurement, not a confirmed live probe or a post-2026-08-14 disassembly.
2. Widening step 3 could in principle over-fuse on an as-yet-untested level. The only two gated levels
   both hold, but neither is exhaustive.

Options:

- **Adopt the change** (`step 3` at `THRESH_POINTS_ARE_NEAR`, step 2 untouched) as the fix, then build
  it as a `to-build/` item.
- **Reject / investigate further** — keep step 3 at SAME and run a live editor probe (`ed_soup.py`) to
  confirm the editor's actual threshold before touching code.
- **Something else.**

## Answer

<!-- Empty = open. Write the decision here. -->
