+++
priority = "p2"
kind = "debug"
summary = "Vandenberg Gas' node/vert over-build (+606/+9480) traced to Brush230 (idx 0, CsgOper absent = CSG_Active). Round 2 (2026-09-01): disassembly shows the real editor dispatches CsgOper=Active identically to Subtract inside bspBrushCSG; fix shipped (uncommitted, worktree vandenberg-csg-active), node delta cut to +32, verified non-regressing on 5 tracked levels. CONFIRMED RECURRING: freeclinic08's Brush586 and nsfhq04's Brush8321 are the SAME pattern (also index-0, also CsgOper-absent) -- this item's own 'Brush230 is the ONLY instance' scope claim was wrong. Fully explains freeclinic08's entire structural-only residual; a major but not sole driver of nsfhq04's."
+++

# Vandenberg Gas: CSG_Active-CsgOper brush causes a real, unexplained geometry reduction

`12_Vandenberg_Gas.dx` (870 brushes) is the current worst-parity level: nodes native=11289
golden=10683 (d=+606), surfs d=+2, leaves d=-134, verts d=+9480, points d=+696, vectors d=+130 —
`LENGTH MISMATCH` on nodes/surfs/leaves (real tree-shape divergence). Confirmed on a fresh rebuild
against current master (post the OceanLab `Base`-fix and NYC 747 texture-identity fix, both
verified zero-effect here).

Full write-up, evidence, and the decisive live A/B/C test: `dev/docs/native-materialize-findings.md`,
search "Vandenberg Gas +606 node over-build".

## Summary

Per-brush attribution (surf-count + node-plane-owner) pointed at `Brush54` (world-CSG idx=3,
412-poly `CSG_Subtract`, non-uniformly scaled) as the dominant single outlier. Live isolation of
Brush54 ALONE (with a synthetic enclosing shell) showed the divergence is NOT intrinsic to its own
geometry — native produces literally zero effect in isolation while the real editor carves 472
nodes correctly. The real culprit is upstream: Brush54's true preceding context is
`[Brush230, Brush2054, Brush73]`, and `Brush230` (world-CSG idx=0) is a degenerate one-poly
`Engine.Brush` with NO `CsgOper=` property at all (an apparent stray original-game authoring
artifact — carries `LightBrightness`/`LightHue`/`LightSaturation`/`TempScale`, none normal Brush
properties).

`Engine.Brush.CsgOper`'s real class default is `CSG_Active` (ordinal 0), confirmed via
`uedcli.classdefaults`/the real `Engine.u` — NOT `CSG_Add`, which is what
`uedcli/native/brush_marshal.py::_build_brush_input` currently defaults an absent `CsgOper` to.

A decisive three-way live UED22 test (`[Brush2054, Brush73, Brush54]` preceded by a variant of
Brush230):

| build | Brush230 variant | editor nodes/surfs/leaves/verts/points/vectors |
|---|---|---|
| A | omitted entirely | 483 / 193 / 87 / 4938 / 301 / 426 |
| B | as authored (no `CsgOper=`) | **181 / 84 / 46 / 1904 / 184 / 182** |
| C | explicit `CsgOper=CSG_Add` (same geometry) | 483 / 193 / 87 / 4938 / 301 / 426 |

C == A exactly (an explicit leading Add on this geometry is a real no-op, as expected). B is wildly
different from BOTH A and C — refuting both "CSG_Active is skipped" and "CSG_Active behaves like
CSG_Add" (native's current, buggy assumption). The real editor does something else entirely for a
literal `CsgOper`-absent brush that roughly halves the resulting geometry of what follows it.
Native's own build of set B (504 nodes) reproduces neither A/C's correct value nor B's real,
drastic reduction (181) — it's simply wrong, in an unmeasured direction.

## Why not fixed

The Rust core has no representation for `CsgOper::Active` at all (`oper_from_i32` rejects ordinal
`0` outright) — there is no existing code path to redirect into. Per the standing no-guessing rule,
shipping either "treat as Add" (already what happens today, refuted by the A/B/C test) or "exclude
from world CSG" (also refuted — B ≠ A) would be shipping a confidently-WRONG behavior. The real
mechanism (why `CSG_Active` roughly halves the following subtracts' output) needs disassembly-level
investigation (`dev/docs/unrealed/extracting-from-dll.md`) not done this round — the live A/B/C test
proves WHAT happens, not WHY.

Already checked and ruled out: `bspcsg.rs`'s own already-filed `first_add_seed` gap ("a leading Add
that isn't a real world-shell corrupts everything downstream") — build C (a genuine leading
`CSG_Add` on this same degenerate geometry) matches A exactly, so that mechanism does not apply
here. This is a distinct, new, unexplained mechanism.

## Scope / regression risk

**CORRECTED (2026-09-01, `freeclinic08-nsfhq04-1-surf-under-build-root`'s 4th continuation) —
`Brush230` is NOT the only instance.** freeclinic08's `Brush586` and nsfhq04's `Brush8321` are BOTH
also non-Mover `Engine.Brush` actors with no `CsgOper=`, and BOTH sit at world-CSG index 0 — same as
`Brush230`. This looks like a recurring OG-DX authoring pattern (a level's first-ever placed brush,
before an explicit CSG op was chosen in the original editor), not a rare fluke: 3 of a handful of
levels checked so far carry it. Concretely measured impact on the other two:

- **freeclinic08**: removing `Brush586` alone from the 141-brush structural-only set makes the
  remaining 140 brushes build BYTE-IDENTICAL to the live editor (nodes/surfs/leaves all d=+0) — this
  ONE brush fully explains that level's entire structural-only residual (was nodes d=-38/leaves d=-23
  with it present).
- **nsfhq04**: removing `Brush8321` from the 660-brush structural-only set does NOT reach exact —
  d_nodes goes from +17 (with) to +237 (without), i.e. WORSE, revealing native's current handling
  barely reacts to this brush (native's own count moves 17 nodes) while the real editor's build moves
  237 nodes when it's added/removed — a large real effect native does not reproduce in either
  direction; the closer WITH-`Brush8321` match was accidental cancellation, not correctness.

Full write-up: `native-materialize-findings.md`, search "Vandenberg Gas mechanism confirmed on
freeclinic08/nsfhq04". Whether the same mechanism explains part of THIS level's own remaining diffuse
402-brush node-owner residual (net +606 vs Brush54's own +901, heavy cancellation) is still unmeasured.
**Now that the fix has shipped (Round 2), freeclinic08 and nsfhq04's residuals should be re-measured
against it directly** -- the fix may already substantially improve or fully close freeclinic08's
structural-only residual, since a lone-brush removal test showed that residual is 100% attributable
to this exact mechanism.

## Next steps (not done this round)

- Disassemble `csgRebuild`'s per-brush dispatch (`Editor.dll`) to find what it actually does for
  `CsgOper == CSG_Active` (0) — a genuinely different branch, an off-by-one jump-table read, or
  something else. `dev/docs/unrealed/extracting-from-dll.md` has the method. Now DECODED and FIXED (Round 2) -- was confirmed to fully explain freeclinic08's residual and be a major driver of nsfhq04's before the fix shipped; re-measure both against the shipped fix.
- Once understood, decide whether native needs a real `CsgOper::Active` handling path (would need
  Rust + marshal changes) and re-verify against this item's own A/B/C goldens
  (`dev/docs/spikes/2026-09-01-vandenberg-gas-node-overbuild/harness/`) plus the full level.
- Check whether other OG levels beyond freeclinic08/nsfhq04/Vandenberg Gas carry a similar
  CsgOper-absent first brush (still unmeasured across the rest of the 21-level corpus).

## Harness

Committed under `dev/docs/spikes/2026-09-01-vandenberg-gas-node-overbuild/harness/`:
`vandenberg_attrib.py` (per-brush surf + node-owner attribution), `vandenberg_isolate_golden.py` +
`vandenberg_isolate_check.py` (Brush54-alone live isolation, refuted "intrinsic" hypothesis),
`vandenberg_csgoper_test_golden.py` + `vandenberg_csgoper_test_compare.py` (the A/B live builds),
`vandenberg_csgoper_explicit_add_golden.py` (the C live build), `vandenberg_csgoper_native_compare.py`
(native vs editor on sets A/B).

## Round 2 (2026-09-01) — mechanism decoded via disassembly, fix shipped

Disassembled `bspBrushCSG` (`Editor.dll 0x355e0`) directly against this worktree's own
`uned/UED22/Editor.dll`. Every `CsgOper` dispatch that gates node/surf/vert output inside it is a
LITERAL equality test against a specific ordinal (`==1` for Add, `==3`/`==4` for Intersect/
Deintersect, one `==2`-only side effect irrelevant to geometry) — never a range/validity check — so
`CsgOper=0` (`CSG_Active`) falls through every one of them into the shared "not this value" branch,
which is the SUBTRACT-shaped one at all three sites that matter (`subtractMask`, the pass-1 filter
func, the world-thru-brush leaf func). **Net finding: `CsgOper::Active` dispatches inside
`bspBrushCSG` IDENTICALLY to `CsgOper::Subtract`** — refutes this item's hypothesis (a) ("a
structural/semisolid-adjacent flag changing subsequent filtering" — nothing in `bspBrushCSG`
special-cases ordinal 0 as anything but "not 1/not 3"), confirms a sharper version of hypothesis (b).
Full evidence, RVAs, and the one deliberately-unresolved residual (the §92 §48 Subtract-only normal
recompute, NOT extended to Active — no disassembly evidence either way):
`dev/docs/native-materialize-findings.md`, search "CSG_Active mechanism — DECODED".

**Fix shipped** (uncommitted, worktree `vandenberg-csg-active`): new `CsgOper::Active` variant
(`uedcli-native/src/csg.rs`); `oper_from_i32` maps `0` to it (`lib.rs`); `bsp_brush_csg`'s early
guard no longer no-ops it (`bspcsg.rs` — this was the actual bug: it used to catch any oper that
wasn't literally Add/Subtract, which would have shipped the already-refuted "skip" hypothesis once
`Active` became representable); `_build_brush_input`'s default flipped from `"CSG_Add"` to
`"CSG_Active"` (`brush_marshal.py`) to match `Engine.Brush.CsgOper`'s real class default. Every site
comments the mechanism and flags Brush230's authoring as likely-unintentional, reproduced faithfully
per the owner's 2026-09-01 ruling (see `native-materialize-findings.md` "Standing directives").

**Verified**: TDD test `csg_active_dispatches_exactly_like_subtract` (`bspcsg.rs`), `bin/test -k
bspcsg` green (102/102 cargo, 78/78 pytest). Live re-verification against this item's own A/B/C
harness (goldens rebuilt fresh — the round-1 worktree no longer exists): set B's tree structure
(nodes/surfs/leaves/points) now matches the editor EXACTLY (181/84/46/184); small pre-existing
verts/vectors residual confirmed present even in Brush230-FREE set A too (so provably unrelated to
this fix). Full Vandenberg Gas level: node delta `+606`→`+32`, verts `+9480`→`-126`, surfs now exact
(`d=+0`, was `+2`) — dominant residual closed, not yet full byte parity (a smaller, distinct
residual remains, out of scope this round). Non-regression on all 5 required goldens (DX.dx, NYC
Bar, UNATCO, OceanLab Lab, NYC 747) via `parity_report.py`: every one UNCHANGED from its documented
pre-fix baseline (expected — none contains a `CsgOper`-absent brush).

**Future reconsideration flag** (per the owner ruling): this authoring pattern (a brush actor with
no `CsgOper=` reaching world CSG at all) is almost certainly unintentional 1999-era level authoring,
not a deliberate use of `CSG_Active`. Worth a `level doctor`/lint warning surfacing any
`CsgOper`-absent, non-Mover `Engine.Brush` in a trunk, so a future stray one is caught at author time
rather than silently reproduced. Not built this round (out of scope; flagging per the ruling only).

**Not done this round**: whether the same mechanism explains part of the remaining diffuse
402-brush node-owner residual (this item's own round-1 open question) is still unmeasured; whether
any of the other ~13 OG levels beyond the 8 already checked carries a similar `CsgOper`-absent brush
is still unmeasured.

## Round 3 (2026-09-03) — Active-as-Subtract REFUTED at the outcome level by a 2-brush live A/B

Paris Underground's remaining `-108/+0/-4` residual prefix-searched live
(`dev/docs/spikes/2026-09-03-built-parity-worst-tier/`, log committed there): first diverging brush
is n=2. The pair is `Brush1246` — the level's `CsgOper`-absent first brush, a default 256-cube at
the origin (n=1 alone builds exact) — plus `Brush328`, a plain 6-poly `CSG_Subtract` overlapping
most of the cube. Counts:

| build                                        | nodes | surfs | leaves |
|----------------------------------------------|-------|-------|--------|
| editor, as authored (`CsgOper` absent)       | 16    | 12    | 6      |
| editor, `Brush1246` -> explicit `CSG_Subtract` | 14  | 11    | 2      |
| native, either variant                       | 14    | 11    | 2      |

Native matches the explicit-Subtract editor build exactly and is A/B-insensitive to the variant
(`pu_two_brush.py`) — so the shipped Round-2 model (`CsgOper::Active` behaves as Subtract) is
right about the filter dispatch but wrong about the outcome: the editor's
Active-led build KEEPS the cube's ceiling surf and full-height wall rings (un-split, T-vertex only)
and `Brush328`'s floor fragment over the cube footprint, partitioning the space into 6 leaves,
where the Subtract-led build annihilates/trims them (`pu_two_dump.py` has both models in full).
The retained faces mean later brushes never cut an Active brush's faces the way they cut a real
Subtract's, and the leaf structure differs — consistent with nsfhq04's earlier "the editor moves
237 nodes when `Brush8321` is added, native moves 17".

Round 2's disassembly showed every geometry-gating `CsgOper` test in `bspBrushCSG` is a literal
`==1`/`==3`/`==4` compare with one "`==2`-only side effect irrelevant to geometry" — that side
effect is now the prime suspect and needs re-reading; it is evidently not irrelevant. Freeclinic08
staying byte-exact under Active-as-Subtract is not a counterexample worth keeping the model for:
whether `Brush586`'s volume ends up identically carved either way there is untested, and the 2-brush
golden is strictly stronger evidence. Scope: this remaining gap plausibly drives Paris Underground's
whole `-108` (first divergence IS this pair) and part of nsfhq04's `-92`/Vandenberg's residual; it
cannot explain WanChai Garage or Training Final (no `CsgOper`-absent brush in either).
