+++
priority = "p2"
kind = "bug"
summary = "native N8 UNATCO rotated-brush base FP diverges flipping node plane W and Region"
+++

# native N8 UNATCO rotated-brush base FP diverges flipping node plane W and Region

UNATCO `03_NYC_UNATCOHQ` fails the parity gate at N=8 (N=1-7 pass). Actor #8 = `Brush74`
(`Carter_window`, the only rotated brush in the prefix: `Rotation=(Yaw=-16384)` = 270deg,
`PrePivot=(-55.999664,-2.000244,1.000031)`, `Location=(448,64,416)`).

Three gate residuals, ONE root cause:

1. `Model Model2` body: `Vectors`(30) and `Points`(76) are BYTE-IDENTICAL; nodes/surfs/verts counts
   equal. Only node planes 29 & 30 differ, in W alone: native `-448.00006103515625` vs ued
   `-447.9998474121094` (normal exactly `(-1,0,0)` both sides).
2. `Polys Polys@Model Model2` (CSG soup) body: polys 14 & 33 (both normal `(-1,0,0)`, the x=448 face
   from Brush74's local -Y face) differ in `base` ONLY: native `(448.00006, 64.0001, 3.05e-5)` vs ued
   `(447.99985, 64.0001, 0.0)`. verts/normal/tu/tv identical.
3. `Brush74` body: sole prop diff is `Region` (PointRegion): native `(iLeaf=1, zone=1)` vs ued
   `(iLeaf=-1, zone=0)`.

## Root cause

Node plane W = `edpoly.base.dot(edpoly.normal)` (`build.rs:146`). With normal `(-1,0,0)`, W = -base.x, so
the residual is entirely in the poly BASE x: native 448.00006 vs ued 447.99985 (~2.1e-4, ~7 f32 ulp at
448).

native's soup/plane base for this face == world `Points[29]` = `(448.00006, 64.0001, 3.05e-5)` EXACTLY
(a deduplicated table point). ued's base `(447.99985, 64.0001, 0.0)` is NOT any point in the (identical)
Points table. So native's Model->Polys base and node-plane base are RECONSTRUCTED from `Surf.pBase`
(`bsp_node_to_fpoly`, `bspcsg.rs:1017` `base = points[s.p_base]`) during the repartition, i.e. snapped to
the deduped point, whereas UED22 keeps the RAW transformed FPoly base in `Model->Polys` and in the node
plane. `bspAddPoint`'s dedup threshold (~0.1) folds the raw base onto the nearby vertex-derived point 29,
losing the low mantissa bits. For all N<=7 (unrotated brushes) the raw base coincides with a table point
so the two agree; the 270deg yaw + fractional PrePivot is the first case where raw-base != any table point.

Residual 3 is DOWNSTREAM of 1/2: Brush74's origin (448,64,416) sits ON the x=448 plane, so `SetActorZone`'s
BSP descent (`materialize._model_point_region`) is decided by the sign of `pd = -1*448 - W`. The 2.1e-4 W
error flips the descent from the solid side (ued: iLeaf=-1) to air leaf 1 (native). All three residuals
resolve if the plane W matches.

## Evidence

`_scratch/cmp_nodes.py`, `_scratch/cmp_polys.py`, `_scratch/cmp_region.py`, `_scratch/diff_off.py`
(worktree `native-parity-incremental`). Fresh native_N8 rebuild reproduces. The editor DOES descend
Region for brushes (Brush777/420/418/324 non-solid values match native==ued) — the "brushes stay solid"
hypothesis is FALSE; only Brush74 flips, and only because of the plane-W FP error.

## Recommendation: FIX (not exclude)

A wrong node-plane W and a solid<->air Region flip are real geometry (BSP descent / collision / zoning),
not a GC/per-save artifact — NOT excludable. The fix is to make native carry the RAW transformed FPoly
base (as fed to CSG) into `Model->Polys` and the node plane, instead of re-deriving base from the
deduplicated `Surf.pBase` after repartition. This is an architectural change (raw bases are currently
lost when the repartition reconstructs polys from nodes via `bsp_node_to_fpoly`) and needs the exact
UED22 bspAddNode / bspBuildFPolys base-provenance confirmed before porting — not a self-authorizable
clamp/snap. Owner decision needed on approach.

## Base-provenance confirmed by disassembly + the "raw base" fix DISPROVEN (2026-09-04)

The provenance the recommendation asked for, decoded from `UED22/Editor.dll` + `Engine.dll`:

- `bspNodeToFPoly` (`0x365b0`): `EdPoly->Base` (offset 0x0) `= Model->Points(Surf.pBase)`. The editor's
  reconstruction reads the DEDUPED base point, same as native. It does NOT keep a separate raw base.
- `bspAddNode` (`0x34e80`): `Surf.pBase = bspAddPoint(&EdPoly->Base, Exact=1)` and `Node.Plane =
  FPlane(EdPoly->Base, Normal)` → `W = Base·Normal`. So the node plane W AND the soup base BOTH derive
  from the SAME `EdPoly->Base = Points[pBase]`, uniformly. There is no "pBase is texture-only, plane
  uses a separate raw base" split — that premise is wrong.

So the editor keeps the raw base for x=448 ONLY because its pre-repartition `pBase` for that face is a
DISTINCT un-snapped point (447.9998); native's is the snapped corner (448.0001). The divergence is a
CSG-phase `bspAddPoint` dedup difference, NOT a reconstruction bug:

- CSG trace (`UEDCLI_PT_TRACE`, world pool): a NEIGHBOUR face's base `(448.000061,64,3e-5)` is added at
  a point idx via its own `pBase` (tol 0.002); the x=448 face's base `(447.999847,64,0)` then MATCHES it
  at d=2.16e-4 < 0.002 → snaps. Two genuinely-distinct authored face bases 2.16e-4 apart get merged.
- The editor keeps them distinct. `bspAddPoint` (`0x35430`) dedups via `UModel::FindNearestVertex`
  (`Engine.dll 0x1adeb0`), a SPATIAL index at `Model+0x5c` that returns -1.0 ("not found") when the
  index misses the query — then `bspAddPoint` ADDS a new point (no snap). Native dedups with a LINEAR
  scan over ALL points, so it never misses and always snaps. Two points 2.16e-4 apart CANNOT both stay
  distinct under native's linear scan at any add order, yet the editor keeps both — so the cause is a
  spatial-index MISS (index build/update lag), not point order or the L2-vs-box metric (both ≤ 2.18e-4).

The prescribed "thread the raw base through reconstruction" fix was implemented and measured: it fixes
x=448 (nodes 29/30, polys 14/33, and the Brush74 Region flip) but REGRESSES three sibling Brush74 faces
where UED22 legitimately snapped — Z=240 (node 33, poly 35) and z=416 (polys 37/38): UED's base there IS
`Points[27]`/etc (snapped), while raw base is the un-snapped transform. Net gate still FAIL, residual
merely relocated. Reverted. Clean baseline reconfirmed = the 3 residuals above, x=448 only.

Correct fix = make native's CSG-phase `bspAddPoint` reproduce UED22's `FindNearestVertex` spatial-index
dedup (so the x=448 base stays a distinct pre-repartition point while Z=240 still snaps). This touches
every dedup call site and needs the `Model+0x5c` index build/update timing pinned by a live spike first
— a different, larger approach than the one recorded above. Owner direction needed before porting.

## Spike overturns the spatial-index framing (2026-09-04, `spikes/2026-09-04-bspaddpoint-dedup-base-provenance`)

The spatial-index dedup was decoded in full (`bspAddPoint 0x35430` → `FindNearestVertex 0x1adeb0`, a
STALE BSP descent over `Model->Nodes` +0x5c gated to MISS on empty; `AddThing 0x31ae0`'s linear box
fallback runs only when `!GFastRebuild`, and `csgRebuild 0x4a650` holds `GFastRebuild` (Editor+0x10c
bit0) set for the whole rebuild). BUT a native-vs-ref N8 build diff proves the divergence is **not**
dedup: `Points`(76) and every `Surf.pBase` are BYTE-IDENTICAL — `bspAddPoint` returns the SAME index
both sides; there is no distinct `447.99985` point in either table. The ONLY diff is `Node[29/30].plane.W`:
editor = raw `Base·N` (`-447.99985`), native = `Points[pBase]·N` (`-448.00006`). Loss site =
`bsp_node_to_fpoly` (`bspcsg.rs:1017 base = points[s.p_base]`): native's repartition rebuilds planes
from the snapped `pBase`; the editor keeps the raw base. So the fix is raw-base PROVENANCE (node plane +
`Polys` soup), not porting the spatial index. Open owner decision (see spike Part C): is the editor's
plane raw-base UNIFORM (then a correctly-scoped fix touches only 29/30, no regression) or SURVIVOR-ONLY
(then a blanket raw-base regresses rebuilt nodes, as the earlier attempt saw)? Decode `bspRepartition`
plane provenance or A/B-measure before porting.

## RESOLVED: provenance is UNIFORM point-dedup, not a scopeable raw-base carry (2026-09-04)

Both open questions above answered. The scoped raw-base fix STEP 2 assumed does NOT exist; the real
fix is the spatial-index dedup port. Evidence:

- **Disasm (uniform, no survivor path).** `bspBuild 0x35ef0` → `SplitPolyList 0x34530` → `FindBestSplit
  0x335d0` (ranks polys only, never sees `Model->Nodes`) → every splitter/coplanar becomes a node via
  vtable `[eax+0x224]` = `bspAddNode 0x34e80`, which sets `Node.Plane = FPlane(EdPoly->Base, Normal)`
  **unconditionally** (@0x351eb-0x35218). There is NO branch copying a pre-existing `FBspNode.Plane`.
  So every final node's W = its soup-FPoly `Base·Normal`, and the soup `Base = Points[Surf.pBase]`
  (`bspBuildFPolys 0x36090`→`bspNodeToFPoly 0x365b0` @0x36636). The "survivor-only raw plane"
  hypothesis is refuted. Node-plane provenance is uniform: `W = Points[pBase]·N` for all nodes.
- **Therefore the raw `-447.99985` can only be the VALUE `Points[pBase]` held at repartition** — i.e.
  the editor's incremental pre-repartition pool kept a DISTINCT `447.99985` point (FindNearestVertex
  MISS) for Brush74's x=448 face; `bspBuildFPolys` copied that value into the soup; `bspAddNode`
  stamped it into the node plane; the final re-add re-deduped `Surf.pBase` back onto `448.00006` (so
  the FINAL pool shows no `447.99985` — the spike Part B measured the final pool). Native's linear
  scan HITS `448.00006` and snaps at the incremental add, losing the distinct point.
- **Live A/B (confirms end-to-end).** Surgically keeping ONLY the x=448 base distinct in native's
  incremental pool (env-gated coordinate match, reverted) → native_N8 `Node[29/30].plane.W` matches
  the editor bit-for-bit, `Surf.pBase` matches, final point table 76/76 IDENTICAL, and
  `parity_gate.py` → **PARITY: YES** (all 3 residuals incl. Brush74.Region resolve). Proves the fix
  DIRECTION: keep the pre-repartition base point distinct, exactly as the editor's spatial index does.

**The fix = port `FindNearestVertex` (spike Part A) as native's incremental `bsp_add_point` dedup**
(stale BSP descent over `model.nodes`, wired points only, plane-side radius-pruned) replacing the
linear scan, so x=448 MISSES (stays distinct) while Z=240 still HITS (snaps). This is the "different,
larger approach" flagged above: it changes dedup at every incremental call site and must be
corpus-re-verified, not just N=8. NOT a scoped node-plane change. **Owner direction needed before
porting** — STEP 2's scoped raw-base carry is unsound (uniform provenance) and blanket-raw / blanket-
distinct both regress the siblings the editor legitimately snaps.

## The `FindNearestVertex` descent port was BUILT and REFUTED — insufficient AND a regression (2026-09-05)

The port above was implemented (WIP `f046d97`) and measured. It does NOT fix N=8, and it regresses the
point table. Reverted to the linear-scan baseline. Two decoded facts settle the approach:

- **The descent is an EXACT nearest-within-R query — it cannot structurally miss a wired within-tol
  point (refutes the "plane-side prune skips it" hypothesis).** Full disasm of the recursive helper
  `Engine.dll 0x1adb60` (called by `FindNearestVertex 0x1adeb0`): at each node it descends the near
  child, then tests the node's own surf-base + vert-pool, then the far child — pruning a child only
  when the whole half-space is beyond the CURRENT radius (`|pd| > R`), and `R` only ever shrinks to a
  real found distance (`0x1adc06-0x1adc1a`). So any point on the far side within `R` forces `|pd| <= R`
  → never pruned. A wired point within `tol` of the query is ALWAYS found. Therefore an editor MISS on
  the x=448 base means `448.00006` was NOT wired+reachable in the editor's incremental `Model->Nodes`
  at that add — a tree-CONTENTS/ordering fact, not a descent-algorithm fact.

- **Native's incremental tree ≠ the editor's, so descending it gives the wrong dedup both ways.**
  Trace (`UEDCLI_FNV_TRACE`, N=8): when native adds the -X base `447.99985`, point `448.00006` (the
  +Y face `ilink=32` base, nodes 48-50) IS wired as a reachable surf-base (`nodes=62`), so the exact
  descent finds it and snaps — x=448 STILL diverges. And the descent over native's divergent tree
  MISSES snaps the editor makes elsewhere: `diff_n8` with the port shows **points 81 vs 76** (5 spurious
  distinct points) with shifted `pBase` across most surfs. The linear scan gives **76/76 byte-identical**
  precisely because it dedups order-insensitively against all points; the final repartition re-dedup
  then yields the editor's table. Its ONLY residual is the x=448 incremental over-snap.

**Conclusion: porting `FindNearestVertex` is necessary-but-insufficient and cannot be verified in
isolation.** FindNearestVertex is exact GIVEN a tree; reproducing the editor's dedup requires native's
incremental world tree to be wired identically to the editor's at every `bspAddPoint` — which native's
approximated `bspBrushCSG`/`bspCleanup` does not achieve (it over-snaps x=448 and under-snaps 5 others).
The blocker is the incremental-tree WIRING divergence for Brush74's subtract, still unpinned. Pinning it
needs a live editor spike: gdb on `bspAddPoint 0x35430` / `bspAddNode 0x34e80` through Brush74's CSG,
capturing per-add `EdPoly->Base`, the returned `pBase`, and the reachable `Model->Nodes` surf-base/vert
set — to learn WHY the editor's tree lacks `448.00006` when the -X base is added (face order? a cleanup
splice?). Only then is the fix (match that wiring) implementable and corpus-verifiable. Owner direction
still needed; this is a spike, not a code port. Disasm reproducer: extend
`spikes/2026-09-04-bspaddpoint-dedup-base-provenance/harness/decode_dedup.py`; trace evidence in that
spike's `harness/`.
