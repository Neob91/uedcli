+++
priority = "p2"
kind = "debug"
summary = "smuggler's +4 surf residual (nodes/leaves exact) isolated to 4 PF_Semisolid CSG_Add brushes; PASS-A structural tree confirmed byte-exact (a NEW, cleaner shape than freeclinic08/nsfhq04); root mechanism not found, no fix shipped"
+++

# smuggler +4 surf delta traced to 4 PF_Semisolid brushes, PASS-A exact

Follow-up to the breadth sweep after the mirror-determinant fix
(`mirrored-brush-determinant-fix-closes-the`): `smuggler` is now the closest non-UNATCO/Wanchai OG
level to exact geometry — nodes 7007/7007 (golden 7007, `d=+0`, EXACT), leaves `d=+0`, but surfs
`d=+4`, verts `d=-70`, points `d=+135`, vectors `d=+13` (measured via `breadth_gate.py`, project
`_scratch/geo-confirm-smuggler`, golden `golden_smuggler_resume.dx`).

## Isolated to 4 specific brushes

Per-brush surf-count attribution (`smuggler_surf_diff.py`, same method as the earlier
freeclinic08/nsfhq04 investigation's `fc08_surf_diff.py` — matches native's `BspSurf.i_actor`
world-CSG brush index against the golden's editor obj-ref) finds **exactly 4 brushes**, each
`d=+1`:

| brush | world-csg idx | native surfs | editor surfs |
|---|---:|---:|---:|
| Brush547 | 119 | 65 | 64 |
| Brush550 | 120 | 65 | 64 |
| Brush273 | 124 | 65 | 64 |
| Brush457 | 266 | 45 | 44 |

All four are `CsgOper=CSG_Add PolyFlags=32` (`PF_Semisolid`), all 128-poly composite props sharing
texture `CoreTexMetal.Heli_LiftMetl_A` — the same "Heli Lift"-style stacked-panel prop placed 4
times (`Brush547`/`Brush550`/`Brush273` look like straight copies at different placements/rotations;
`Brush457` differs slightly).

## PASS-A (structural) confirmed byte-exact — the decisive new fact

freeclinic08/nsfhq04's own `+1 surf` (`freeclinic08-nsfhq04-1-surf-under-build-root`) was traced to
their PASS-A (non-semisolid) structural tree already being `-38 nodes/-23 leaves` off (same face
set, wrong tree shape) BEFORE their one semisolid brush is even processed — an instance of the same
open "correct per-call, wrong in aggregate" repartition-tie-break class as UNATCO's residual, judged
not locally fixable.

Reused that item's methodology on smuggler: `smuggler_filter_trunk.py` drops all 79
`PF_Semisolid` brushes from the trunk (660 of 739 actors kept), `smuggler_native_structural.py` gets
native's structural-only counts, and `geo_golden_resume_structural.py` (a structural-only variant of
the existing crash-resume-capable `_scratch/geo_golden_resume.py` driver, needed because a bare
`EDIT PASTE` of this many brushes reliably GPFs the editor — same crash documented for the original
full smuggler golden) builds a fresh editor golden of the SAME filtered trunk.

**Result: byte-exact.**

| | nodes | surfs | leaves | verts | points | vectors |
|---|---:|---:|---:|---:|---:|---:|
| native structural-only | 2526 | 1378 | 614 | 34164 | 3872 | 123 |
| editor structural-only (live) | 2526 | 1378 | 614 | 34099 | 3871 | 124 |

nodes/surfs/leaves match exactly; verts/points/vectors are within noise (`+65/+1/-1`). This is the
OPPOSITE of freeclinic08's shape — smuggler's `+4` surf delta is **entirely a PASS-2 (semisolid)
effect landing on an otherwise-exact PASS-A tree**, not inherited from an already-wrong repartition
gap. A genuinely cleaner, more tractable residual than freeclinic08/nsfhq04's, and a different
mechanism from UNATCO's (already-fixed) `repartition_frontier` gap, which was never about PASS-2.

## Per-brush poly attribution

`smuggler_brush_surf_detail.py` matches native's and the golden's surfs per brush by
`i_brush_poly` (the brush-local authored-poly index a surviving surf traces back to):

- **Brush547 / Brush550 / Brush273 — a clean single addition.** Native keeps local poly index
  **124** (the SAME index all three times) as an extra surf with no editor counterpart at all — not
  a swap, a pure addition. Poly 124 is the BOTTOM-most stacked panel of the prop: its `Z` range sits
  exactly at the brush's own `PrePivot.Z` (e.g. `Brush547`: `PrePivot=(12,-40,-52)`, poly124 spans
  `Z=[-52,-40]`) — suggestive of a face coincident with, or immediately adjacent to, whatever
  structural geometry the prop's base rests on. `bspcsg.rs`'s `leaf_func` (`LeafFunc::Add` arm,
  lines 604-613) already special-cases exactly this: an `F_COSPATIAL_FACING_OUT` classification is
  gated OFF for `PF_SEMISOLID` faces (only non-semisolid coincident faces get added), which is the
  textbook mechanism for dropping a semisolid brush's face that lies exactly on top of real solid
  geometry. **This is a hypothesis, not a confirmed mechanism** — see below.
- **Brush457 — a different shape.** Native keeps poly **99**, editor instead keeps poly **16** — a
  genuine one-for-one SWAP between two geometrically distinct, non-coplanar, non-duplicate faces
  (different normals, different Z ranges), net `+1`. Possibly a related but not identical
  sub-mechanism, not investigated further.

## Attempted live/native differential — inconclusive, not a confirmed root cause

Tried to confirm the coincident-face hypothesis using the existing `UEDCLI_BSPCSG_DESCENT=<i_link>`
env-gated tracer (`bspcsg.rs`, an existing per-poly `filter_ed_poly` descent logger). Ran with
`UEDCLI_BSPCSG_DESCENT=124` (poly124's LOCAL brush-poly index) across the whole smuggler build: 37
lines fired, none showing the expected near-zero-distance coincident-plane signature the hypothesis
predicts.

**This is NOT evidence against the hypothesis** — `i_link` inside `filter_ed_poly` is a per-brush-
CSG-call-LOCAL temp index (freshly assigned inside `bsp_brush_csg` per brush, `bspcsg.rs`
~2382-2460), not a global/stable poly identifier. Every brush with ≥125 polys hits local index 124
once during its own CSG call, so the 37 captured lines are a mix of MANY different (mostly
unrelated) brushes' own 125th poly — `Brush547`'s specific call was never confirmed to be among
them. The tracer as it exists is not brush-scoped, so this attempt is inconclusive rather than a
refutation.

## Why not fixed this session

Per the standing rule (a fix must replicate the real, live-verified mechanism — never a rounding
tweak or a plausible-looking guess), no fix was attempted without confirming the actual mechanism.
The coincident-face-drop hypothesis is well-motivated (the exact code path exists and matches the
geometric signature) but unconfirmed. Isolating and confirming it needs either:

- a brush-scoped version of the descent tracer (gate on the enclosing world-CSG brush index, not
  just the reused-per-brush `i_link`), or
- a minimal single-brush repro: rebuild with `Brush547` as the ONLY `PF_Semisolid` addition onto the
  already-confirmed-exact structural tree, then trace its own poly124 in isolation.

Neither attempted this round — logging the isolation work (which is itself real, checkable
progress: 4 brushes named, PASS-A confirmed exact, the swap-vs-addition distinction found) rather
than grinding further on an open-ended reverse-engineering task.

## Harness (all committed, `dev/docs/spikes/2026-08-29-unatco-repart-live-diff/harness/`)

`smuggler_surf_diff.py`, `smuggler_brush_surf_detail.py`, `smuggler_filter_trunk.py`,
`smuggler_native_structural.py`, `smuggler_structural_compare.py`, `geo_golden_resume_structural.py`
(+ its dependency `geo_golden_driver.py`, promoted from `_scratch/` where it already existed for the
original full-smuggler golden build).

## No fix shipped

No `uedcli-native/src/` changes this round. `bin/test`/`regression_gate.py`/`breadth_gate.py` all
unaffected (verified via `git status` — no source edits made). smuggler stays at nodes/leaves
EXACT, surfs `d=+4`.
