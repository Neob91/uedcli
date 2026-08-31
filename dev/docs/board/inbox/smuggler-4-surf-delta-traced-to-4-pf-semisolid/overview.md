+++
priority = "p2"
kind = "debug"
summary = "smuggler's +4 surf residual (nodes/leaves exact) isolated to 4 PF_Semisolid CSG_Add brushes; PASS-A structural tree confirmed byte-exact; F_COSPATIAL_FACING_OUT/PF_SEMISOLID hypothesis REFUTED; round 3 LIVE-CONFIRMED via isolated single-brush editor rebuild that native's self-coincidence classification (Brush547 poly124 vs its own poly5) genuinely diverges from the real editor; exact transform-precision mechanism still not pinned, no fix shipped"
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

## No fix shipped (round 1)

No `uedcli-native/src/` changes this round. `bin/test`/`regression_gate.py`/`breadth_gate.py` all
unaffected (verified via `git status` — no source edits made). smuggler stays at nodes/leaves
EXACT, surfs `d=+4`.

## Round 2 (2026-08-30): tracer fixed, hypothesis REFUTED

The old `UEDCLI_BSPCSG_DESCENT=<i_link>` tracer was unusable for attribution — `i_link` is a
per-brush-call speculative surf-slot number that collides across unrelated brushes whenever an
earlier candidate never actually committed. Fixed: added `UEDCLI_BSPCSG_DESCENT_ACTOR`/`_POLY`,
keyed off `FPoly.actor`/`i_brush_poly` (stable, `empty_copy`-preserved, already present but unused
by the tracer), refactored into a shared `descent_scope_matches` helper, plus a new `LEAF` trace
inside `leaf_func`'s `Add` arm exposing the actual terminal classification.

Ran the whole smuggler build scoped to `Brush547`'s poly124 (`actor=119 i_brush_poly=124`) —
every captured line unambiguous. Result: `filter=2` (`F_COPLANAR_OUTSIDE`), added unconditionally,
`semisolid` gate never in play. Matches the disassembly-confirmed real `AddFunc`
(`Editor.dll 0x31770`, `sections/10-bsp-csg-build.md` §4.3): `F_OUTSIDE`/`F_COPLANAR_OUTSIDE` are
added unconditionally in both native and the real editor — the coincident-face-drop hypothesis does
not apply to this poly at all. **REFUTED.**

New characterization instead: the unscoped descent trace shows this poly hitting a genuine
`COPLANAR dot=-1.00000` node partway down that belongs to `Brush547`'s OWN earlier-added faces from
the same `bsp_brush_csg` call, not world/structural geometry — the coincidence is internal to the
brush's own reconstructed geometry (two touching faces of the same stacked-panel prop). Whether
native's classification of this self-coincidence diverges from the real editor's, or whether real
PASS-2 uses a mechanism beyond the shared `AddFunc`/`leaf_func` that native's Pass 2 doesn't model,
is undetermined — needs a live editor-side capture of this exact poly or a single-brush isolated
repro, neither attempted.

Also noted, not acted on: this file's `F_COSPATIAL_FACING_OUT=5`/`F_COSPATIAL_FACING_IN=4` are the
reverse of `sections/10-bsp-csg-build.md`'s disassembly-derived values — not a functional bug (the
semisolid gate correctly keys off raw value 5 either way) but a naming mismatch worth fixing later;
out of scope this round (touches unrelated call sites, zero behavior change).

No fix shipped this round either — only the tracer (env-gated, zero default-path effect). Verified:
full `bin/test` 12517 passed/0 failed + 90/90 cargo test; `regression_gate.py` UNATCO/Wanchai both
EXACT; `breadth_gate.py` unchanged (4/17 exact, smuggler still surfs `d=+4`, severe-under-build
family unaffected). Committed `fd67aa6`. Full trace details: `native-materialize-findings.md`.

## Round 3 (2026-08-31): self-coincidence LIVE-CONFIRMED as a real divergence, root cause still open

Picked up round 2's exact open lead ("does native's classification of poly124's self-coincidence
with `Brush547`'s own poly5 genuinely diverge from the real editor, or does real PASS-2 use a
mechanism native doesn't model — needs live editor capture or a single-brush isolated repro").

**Step 1 — re-verified round 2's finding still holds.** Re-ran the actor/poly-scoped descent tracer
(`UEDCLI_BSPCSG_DESCENT_ACTOR=119 UEDCLI_BSPCSG_DESCENT_POLY=124`) on the current tree: unchanged —
poly124 descends ~20 nodes, hits `COPLANAR dot=-1.00000` at node 2706, ends in 3 `LEAF filter=2
semisolid=true add=true` lines (all `F_COPLANAR_OUTSIDE`, added unconditionally, semisolid gate never
in play — matches round 2). Confirmed node 2706's surf (`nsurf=1473`) is `i_actor=119
i_brush_poly=5` — Brush547's own poly5, not world/structural geometry. Pulled the raw T3D: poly5
(`normal=(0,1,0)`, `Y=32` plane) and poly124 (`normal=(0.00208,-1,0)`, `Y=32` plane) are two AUTHORED
faces of the same "Heli Lift" stacked-panel brush, touching at Y≈32 with opposite normals — a real
internal seam in the original prop geometry, not a build artifact.

**Step 2 — single-brush isolated repro, live editor build (the decisive test).** Built
`_scratch/smuggler-b547-isolated`: the confirmed-exact PASS-A structural trunk (429 non-semisolid
brushes, same relative order) + `Brush547` appended LAST as the sole PF_Semisolid addition. This
ordering is faithful to the real algorithm, not a guess — `10-bsp-csg-build.md`/
`82-bspbrushcsg-port-decode.md` document PASS B (semisolid) as a full, unrepartitioned second pass
over ALL PASS-A brushes, run strictly after PASS A completes, in trunk order — so by the time any
semisolid brush is processed for real, every structural brush is already in the tree and no other
semisolid brush has touched it yet.

- Native, offline, on this isolated trunk: reproduces the full-level result exactly — 65 surfs for
  `Brush547`, `i_brush_poly=124` still the sole native-only key. Proves the effect has ZERO
  dependency on the other 78 semisolid brushes.
- Real editor, live, on the SAME isolated trunk (`smuggler_b547_isolated_golden.py`, a
  `geo_golden_resume_structural.py` copy, chunked `MAP NEW`→`EDIT PASTE`→`MAP REBUILD`→`MAP SAVE`,
  27 chunks, ~40 min real editor time): **64 surfs for `Brush547`, `i_brush_poly=124` absent** — the
  identical delta, in complete isolation, with a real editor.

**Conclusion: CONFIRMED, not just hypothesized — native's classification of this self-coincidence is
a genuine algorithmic divergence from the real editor**, reproduced with zero cross-brush
interference. This resolves round 2's open question in favor of "native has a real bug here," ruling
out "real PASS-2 uses an unmodeled mechanism that happens to look the same on the full level."

**Two more candidate mechanisms checked and ruled out:**
- `splitwithplane-degenerate-fragment-fallback` (the catalogued `SplitWithPlane` degenerate-sliver
  fallback native is missing): the two `SPLIT`s poly124 passes through en route to node 2706 both
  produce `f_nv=4 b_nv=4` — no degenerate fragment involved, so that gap doesn't apply here.
- A surf-reuse/dedup difference in `bsp_add_node`'s `i_link`: `brush_loop1`'s pre-pass groups
  same-brush polys sharing an identical plane AND orientation via `links[i]`; poly5
  (`normal=(0,1,0)`) and poly124 (`normal=(0.00208,-1,0)`, opposite-facing) are not in the same
  orientation class, so each gets an independent surf slot on both sides regardless — not the
  mechanism. The node-2706 `Coplanar` classification itself is also not threshold-borderline: vertex
  distances to the plane are `0.0`-`0.0166`, well inside `THRESH_SPLIT_POLY_WITH_PLANE`'s `±0.25`
  band.

**Best remaining candidate, NOT confirmed:** a small (sub-0.001, ULP-level) floating-point difference
between native's and the real editor's vertex/normal transform for this Yaw=`-16384`-rotated brush.
The per-brush surf-key diff shows small plane-key mismatches (e.g. normal `(0.0,-1.0,-0.002)` vs
`(-0.0,-1.0,-0.002)`, dist `-60.6` vs `-60.7`) across MOST of `Brush547`'s other surviving faces too
(harmless there — neither side's classification flips) — plausibly enough to tip the ~20-node-deep
descent path just before node 2706, changing poly124's final classification without the coplanar test
itself being a near-miss. Pinning this needs bit-level comparison of the two transform code paths —
the same class of work as the still-open `wanchai-verts-points-residual-independently` Points
residual. Out of this round's scope.

**No fix shipped** (mechanism narrowed, not confirmed — per the standing rule). Harness added:
`smuggler_b547_isolated_golden.py` (`dev/docs/spikes/2026-08-29-unatco-repart-live-diff/harness/`).
Trunk `_scratch/smuggler-b547-isolated/` is scratch, not committed. `bin/test`/`regression_gate.py`
not run this round — no `.rs` source changes were made (git status showed `bspcsg.rs` untouched
throughout). Full detail: `native-materialize-findings.md`.
