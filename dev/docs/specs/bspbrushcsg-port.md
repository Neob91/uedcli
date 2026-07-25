# Spec — port UnrealEd's incremental `bspBrushCSG` for a byte-identical native `.dx`

**Status:** DESIGN ONLY (no code in this spec). Ephemeral per-feature scratch — the durable
record is `dev/docs/decisions.md` (the load-bearing choices, appended alongside this spec) plus,
on landing, `architecture.md` + `unrealed/*.md`. **Date:** 2026-07-17.

**Goal.** Make native `level materialize` produce a `.dx` `UModel` **byte-for-byte identical** to
UnrealEd's build of the *same* trunk. The native build is today functionally-equivalent but
structurally different (see §1). The reverse-engineering is done (`sections/80-bspbuild-topology.md`,
`re-raw-zones/bspbuild-splitpolylist-decode.md`, `sections/70`, `re-raw-zones/bounds-and-zonelayout.md`);
this spec sequences the *port* foundation-first with a byte-diff gate at every phase, and settles
(as far as static evidence allows) whether literal byte-identity is even reachable.

**Read first (this spec assumes them):**
- `sections/80-bspbuild-topology.md` — why the native tree leaks + the synthetic scaffold to delete.
- `re-raw-zones/bspbuild-splitpolylist-decode.md` — the instruction-level `bspBuild`/`SplitPolyList`/
  `FindBestSplit`/`bspBrushCSG`/`csgRebuild` decode (the port's ground truth).
- `sections/70-zones-portalization.md` + `re-raw-zones/bounds-and-zonelayout.md` — `TestVisibility`
  and `bspBuildBounds` (`Bounds` + `LeafHulls`), both already partly ported.
- Current code being replaced/extended: `uedctl-native/src/csg.rs`, `build.rs`, `passes.rs`,
  `zones.rs`, `fpoly.rs`, `model.rs`, `model_write.rs`.

---

## 0. Definitions and the parity oracle

**Trunk** — the git-tracked T3D tree of a level (`uedctl/maps/<level>/`). **Editor build** —
UnrealEd materializing that trunk (`MAP IMPORT` of the assembled `.t3d` then `MAP REBUILD` with
`Balance=50, PortalBias=70, OPTIMAL` — the byte-verified `MAP REBUILD` params,
`bspbuild-splitpolylist-decode.md §FindBestSplit`). **Native build** —
`uedctl_native::build_geometry` over the same brush inputs.

**The castle golden.** `Maps/Test_Castle.dx` is the committed editor build of the castle trunk at
`_scratch/castle/uedctl/maps/foobar`. `harness/bytediff_baseline.py` already loads both and prints
per-section counts. Current gap (native → editor):

| section | native (repaired) | editor golden | body |
|---|---|---|---|
| nodes | 909 | **1156** | |
| verts (FVert pool) | 3604 | **16163** | |
| surfs | 438 | **485** | |
| points | 1563 | 2035 | |
| Bounds (render) | 0 | **484** | |
| body bytes | ~102 KB | ~249 KB | |

**Oracle definition (this spec).** Parity is judged by **materializing the SAME trunk both ways and
byte-diffing the `UModel` export body and object tables.** `Test_Castle.dx` is the castle golden;
`DXOnly.dx` is a trivial second golden; the CSG differential fixtures (a/c/d/e single/few-brush
cases in `build.rs` tests) are the micro-goldens. **The oracle must be regeneratable on demand** —
the editor-materialize path (`uedctl/materialize.py` → `driver.MAP IMPORTADD` + `rebuild()`) can
rebuild the golden from the current trunk, so a Phase-0 task pins a script that (re)builds the
editor golden from a trunk with the exact `MAP REBUILD` params, guarding against the checked-in
`.dx` drifting from the trunk it is diffed against.

**Byte-identity scope (OPEN — see §7 Q1).** The package header carries a **per-save random GUID**
(`appCreateGuid`) and generation counts; the whole *file* can therefore never be bit-identical to an
independent editor save. This spec's working target is the **`UModel` export body + the Name/Import/
Export tables identical, GUID/timestamps excluded** (or copied from the golden for a whole-file
diff). Whether Andrzej wants literal whole-file identity (requires copying the golden GUID) or
body+tables identity is Q1.

---

## 1. Why the current core cannot be byte-identical (root cause, decoded)

The editor and native pipelines diverge at the very top:

**Editor `csgRebuild` (`Editor.dll 0x4a650`, decoded):**
1. `EmptyModel`.
2. **LOOP 2 — structural brushes → incremental `bspBrushCSG` (`0x355e0`).** Each brush filters its
   polys through the **growing world `Model`** via `FilterFPoly` (`0x33250`), adding surviving
   fragments as nodes with `bspAddNode`, bounded by the brush's own **temp-BSP bevel/bounding
   planes**. The world tree GROWS incrementally and every solid leaf ends watertight.
3. **`bspRepartition` (`0x49fc0`)** = `bspBuildFPolys` (nodes→Polys) → `bspMergeCoplanars` →
   from-scratch `bspBuild`/`SplitPolyList` over the merged soup → `bspRefresh`. The repartition
   input is **fat CSG-fragmented, coplanar-fused faces** that retain every CSG boundary/T-junction
   vertex → ~14 FVerts/node.
4. **`TestVisibility` (`0xaa940`)** — leaves/zones/portals (splits nodes: `AssignAllZones` frags).
5. **LOOP 3 — semisolid/nonsolid brushes → incremental `bspBrushCSG` again, NOT repartitioned.**
6. **`bspOptGeom` (`0x36870`)** (T-junction/redundant-node trim) → **`bspBuildBounds` (`0xaace0`)**.

**Native `build_geometry_from_brushes` (`build.rs`):** per-brush `csg::bsp_brush_csg` produces a
**surface FPoly list** (point-in-solid classifier, not a growing tree) → `bsp_merge_coplanars` →
**ONE** from-scratch `build_bsp_opt` over clean convex faces → synthetic `bound_leaked_solid_leaves`
scaffold → `bsp_refresh` → `finalize`/`zones` → `bsp_build_bounds` (LeafHulls only).

**Consequences (`bspbuild-splitpolylist-decode.md §Verdict`):** we partition clean convex quads, not
fat fragmented faces, so ~4 FVerts/node (3604 vs 16163); we skip the semisolid incremental layer and
the zone-split fragments, so fewer nodes (909 vs 1156); we run one lean partition, so the `outside`
propagation is not watertight (the leak the scaffold patches). **`SplitPolyList` is a pure partition
— there is no hidden leaf-bounding pass to add** (proven at instruction level); the extra nodes and
FVerts come *only* from the incremental construction. Therefore **byte-identity requires replacing
the classifier core with the faithful incremental pipeline** — the point-in-solid classifier is
structurally incapable of it (it collapses the very fragments that make up the difference).

---

## 2. Target architecture

### 2.1 What is replaced

`build_geometry_from_brushes` (`build.rs`) and `csg.rs`'s surface-list `bsp_brush_csg` are replaced
by a faithful `csgRebuild` port:

```
EmptyModel  (empty Model)
for each STRUCTURAL brush in trunk order:
    bspBrushCSG_incremental(world_model, brush)      # grows the node tree
bspRepartition(world_model):
    polys   = bspBuildFPolys(world_model)            # nodes -> FPoly list
    polys   = bspMergeCoplanars(polys)               # fuse per-surf coplanar fragments
    world_model.EmptyModel(keep polys)               # bspBuild rebuilds nodes from polys
    bspBuild(world_model, polys, OPTIMAL, Balance=50/PortalBias=70)
    bspRefresh(world_model)
TestVisibility(world_model)                          # zones.rs (already ported — re-validate)
for each SEMISOLID/NONSOLID brush in trunk order:
    bspBrushCSG_incremental(world_model, brush)      # NOT repartitioned
bspOptGeom(world_model)                              # NEW port (T-junction / redundant-node trim)
bspBuildBounds(world_model)                          # Bounds (render) + LeafHulls (collision)
```

### 2.2 What stays (reused verbatim or as validation)

- **`bspAddNode` / `bspAddPoint` / `bspAddVector`** (`build.rs`) — the node emitter + pool dedup.
  Reused by BOTH the incremental filter (adds fragment nodes) and `bspBuild` (adds splitter/coplanar
  nodes) and the temp brush BSP. **Pool order is produced here** — Phase B hinges on these.
- **`SplitPolyList` / `FindBestSplit` / `bspBuild`** (`build.rs`) — the from-scratch partition, used
  by `bspRepartition` AND the per-brush temp BSP. **`FindBestSplit` must be reverted to the EXACT
  engine scoring** (drop the `SPLIT_WEIGHT` deviation; §2.4).
- **`FPoly` primitives** (`fpoly.rs`) — `SplitWithPlane`, `Fix`, `RemoveColinears`, `Finalize`,
  `Reverse`, `SplitInHalf`, thresholds. Unchanged geometry; the FP hot path (§6).
- **`zones.rs` `TestVisibility`** — leaves/flood/ZoneActor. Re-validate against the new tree (node
  order changes; Pass A/D consume it). Currently drives node-split fragments (Pass D) — needed for
  the 1156 count.
- **`model.rs` / `model_write.rs`** — serialization. `Bounds` field already exists (populate it in
  Phase D); no serializer change expected (`bounds-and-zonelayout.md §2.1` confirms the layout).
- **`point_in_solid`** (`csg.rs`) — **demoted from classifier to VALIDATION ORACLE.** It no longer
  decides which fragments survive; it becomes the differential check that the faithful CSG produces
  the same solid/void field (grid-solidity gate, §4 safety net). Keep the function; delete its use
  in the build path.

### 2.3 What is DELETED (once faithful CSG lands and its phase gate is green)

The synthetic scaffold that exists only to paper over the leak the faithful build removes:
- `build.rs::bound_leaked_solid_leaves`, `collect_leaks`, `insert_solid_bound`,
  `region_interior_point`, `HalfSpace`, `node_face_centroid`, and the `NF_SOLID_BOUND` (0x40)
  transient marker + its handling in `finalize_leaves_and_bbox` and `zones::assign_leaves`.
- The post-`bsp_build_bounds` **point-in-solid leaf correction** loop in
  `build_geometry_from_brushes` (build.rs tail) — the faithful tree's `assign_leaves` is watertight,
  so there is no spurious-empty-leaf to correct.
- `passes.rs::cull_parallel_planes` and the ±WORLD_MAX bbox shortcut in `bsp_build_bounds` — replaced
  by the faithful `FilterBound`/`SplitPartitioner` hull construction (`bounds-and-zonelayout.md §1.3-1.6`).
- The `find_best_split` `SPLIT_WEIGHT` deviation and the winding-normal re-derivation hacks in
  `build_geometry_from_brushes` — the faithful path carries fat fragments with their true CSG
  windings, so these compensations are unnecessary and would perturb byte-identity.

**Deletion is gated:** each scaffold piece is removed only in the phase whose gate proves the
faithful path subsumes it (the collision box-drop test must stay green across the swap — §4).

### 2.4 The pieces to port faithfully (new work)

**`bspBrushCSG_incremental` (`0x355e0`).** Per brush: (a) transform polys to world space, adjust
flags `(pf|PolyFlags)&~mask` per CsgOper; (b) build the **temp brush BSP** in a scratch model
(`EmptyModel`, per-poly `bspAddNode`, `bspBuild(temp,…,RebuildSimplePolys=1)`, `bspRefresh`) — this
carries the brush's bounding/bevel planes; (c) **`FilterFPoly` (`0x33250`)** the brush polys through
the growing world `Model`, and at world leaves add the surviving fragment as a node via `bspAddNode`,
the keep/discard governed by the per-CsgOper world-filter leaf funcs.
> ✅ **Decode gap CLOSED 2026-07-17** (`sections/82-bspbrushcsg-port-decode.md` +
> `re-raw-zones/bspbrushcsg-filter-decode.md`). `bspFilterFPoly` (`0x31f50`), `FilterEdPoly`
> (`0x32bf0`), `FilterLeaf` (`0x33130`), the leaf callbacks `AddBrushToWorldFunc` (`0x31770`) /
> `SubtractBrushFromWorldFunc` (`0x348c0`), `FilterWorldThroughBrush` (`0x33250`), `bspNodeToFPoly`
> (`0x365b0`), and `bspBuildFPolys` (`0x36090`) are all decoded to instruction level.
> **KEY CORRECTION: there are NO bevel planes.** The "temp-BSP bevel-plane generation" was a
> misconception — the temp brush BSP is a plain convex `bspBuild` of the brush's own face planes,
> used by `FilterWorldThroughBrush` to cut world faces; watertightness comes from filtering each
> brush face down the world tree and adding the surviving OUTSIDE fragments as nodes carrying the
> brush's own face plane (`FilterEdPoly → AddBrushToWorldFunc → bspAddNode(…, NF_IsNew, …)`), each
> fragment already clipped to its leaf cell by the ancestor planes. Residual micro-gaps (coplanar
> cascade child-order; `FPoly::TryToMerge` splice; the subtract mirror) are low-risk and gated by the
> CSG differential fixtures — see `sections/82 §6`.

**`FindBestSplit` exact scoring** (`bspbuild-splitpolylist-decode.md`): `Balance=packed&0xff`,
`PortalBias=(packed>>8)&0xff`; per candidate over the list, `Splits += PF_Portal?16:1` on a straddle;
`Score2=(100−Balance)·Splits`; `Score=Score2+Balance·|Front−Back|`; portal candidate
`Score −= Score2·(PortalBias/100)`; **min wins, first candidate always taken; OPTIMAL stride 1.**
Structural-skip: a candidate with `PF_NotSolid|PF_Semisolid (0x28)` and not `PF_Portal` is skipped
unless every poly is structural. This replaces the deviating `find_best_split`.

**`bspBuildFPolys` (`0x36090`)** — walk the node tree, reconstitute each node's stored poly (verts
from the FVert pool + surf plane/texture), emit the FPoly list `bspRepartition` merges.

**`bspMergeCoplanars` (`0x36200`)** — the engine's real coplanar merge over the `bspBuildFPolys`
output (called `(Model,0,0)`). The current `passes.rs::bsp_merge_coplanars` is a plausible
reassembly but was written against the surface list, not decoded from `0x36200`; Phase 0 decodes the
real one and Phase A/B replaces ours if they differ (T-junction vertex retention is exactly what
drives the 16163 FVerts, so this must be faithful).

**`bspOptGeom` (`0x36870`)** — currently un-ported (a documented residual). Part of `csgRebuild`
after the semisolid layer; it trims redundant nodes and links T-junction sides. Required for both
the node count and the `iSide` fields in the FVert pool. **Not decoded to instruction level yet** —
Phase 0.

**`bspBuildBounds` render `Bounds`** — extend `passes.rs::bsp_build_bounds` to build the `Bounds`
`FBox` array via the faithful `FilterBound`/`BuildInfiniteFPoly`/`SplitPartitioner`/`UpdateBound*`
port (`bounds-and-zonelayout.md §1.3-1.8`), setting `iRenderBound` per interior node (0→484).
**Guard:** a bogus `iRenderBound>=0` into an empty `Bounds` re-arms the OccludeBsp NULL-FBox render
crash (`sections/50`); the Bounds array must be populated in lockstep with the indices.

---

## 3. Phasing — foundation-first, each phase a byte-diff gate

Order is dictated by data dependency: **topology → pool order → surfs → bounds → lightmaps →
wrapper.** A later section cannot be byte-identical until the earlier one is, because each is indexed
off the previous (nodes index surfs + FVerts; bounds index nodes; the wrapper's export table sizes
depend on the body length). Every phase states its **harness assertion** and the **goldens that must
not regress**.

**Honest caveat — the phases are diagnostic checkpoints, not independently-shippable milestones.**
Node topology (A) and the vert/point pool (B) are **one coupled milestone**: `SplitPolyList`'s
`SplitInHalf(NumVertices>=14)` ties node count to fragment fatness, and `bspAddNode` emits the FVert
pool *as* nodes are added — so the Nodes byte-diff cannot go green until Surfs + the pool land too.
Likewise the whole core swap (point-in-solid classifier → faithful incremental `bspBrushCSG`) is a
**big-bang cutover**: there is **no incrementally-green path** through it — replacing the classifier
reds every geometry golden until the faithful pipeline is complete. Plan for an **all-or-nothing
core-replacement branch** whose acceptance is the **full offline suite (1241 pass / 1 skip / 2 xfail
baseline) + `cargo test` + the live render/collision/lit gates all green at once**, with the A–F
gates below used as *internal* progress diagnostics on that branch, not as separately-mergeable
deliverables. B/C in particular are mostly harness + dedup-threshold fidelity, not separable work.

### Phase 0 — decode completion + feasibility gates (BLOCKING) — **DONE 2026-07-17, verdict GO**

No production code. **Result: `81-phase0-feasibility.md` (verdict GO) +
`re-raw-zones/fp-classification-sites.md` (per-site FP table + evidence).** The four gates and their
verdicts:

1. **FP characterization (§6) — PASS.** Every classification/pool hot site
   (`SplitWithPlane`/`SplitWithPlaneFast`/`PlaneDot` classify, the split-param `divss`, `bspAddPoint`
   dedup, `CalcNormal`→`NormalizeSlow`) is **SSE-scalar** (or f64-`sqrtsd`+f32-`divss` for the
   normalize) — no x87, no `rsqrt` on the surf path. This is because the UED22 DLLs are a **2022
   MSVC/VS2022 rebuild** (linker 14.32; the golden-building container ships the MD5-identical
   binaries), so `/arch:SSE2` scalar float is the default — literal `f32` bit-parity is reachable.
   Per-site table + disassembly: `re-raw-zones/fp-classification-sites.md`.
2. **Input identity — PASS (castle).** All 95 castle brushes are identity-scale / zero-rotation /
   zero-sheer / zero-prepivot ⇒ world transform is a bit-trivial `v + Location` translation. Rotated
   brushes (UNATCO) are a gated future blocker (editor `BuildCoords` uses a sine TABLE, not libm).
3. **The four missing decodes — DONE.** `bspAddPoint` dedup = `UModel::FindNearestVertex` (recursive
   BSP nearest search, thresh 0.002; **not** a flat scan or spatial hash) — fixes Points/Vectors
   ORDER; `bspRefresh` = reachability-GC compaction (pool survives + compacts deterministically);
   `NumSharedSides` = `bspOptGeom` T-junction tally (serialized field, portable); **normal provenance
   = PRESERVE the authored T3D normal** (`Finalize` recomputes only a zero normal). Evidence in
   `81-phase0-feasibility.md §4` + `re-raw-zones/fp-classification-sites.md`.
4. **Editor determinism — PASS (static).** Deterministic tree-walk + array-append pool emission; no
   RNG/hash-order/pointer-sort/uninitialized-slack; only the random GUID + timestamp vary (excluded
   from scope). Empirical double-build (GUID-masked) recommended as corroboration; not run (crash-prone
   editor). The oracle-regen script (rebuild `Test_Castle.dx` from the trunk with pinned `MAP REBUILD`
   params) remains a Phase-0-completion follow-on, folded into the determinism corroboration.

**Phase-A prerequisites — ALL DECODED 2026-07-17** (`sections/82-bspbrushcsg-port-decode.md` +
`re-raw-zones/bspbrushcsg-filter-decode.md`): `bspBrushCSG` (`0x355e0`) full CFG; the filter half
(`bspFilterFPoly` `0x31f50`, `FilterEdPoly` `0x32bf0`, `FilterLeaf` `0x33130`, leaf callbacks
`0x31770`/`0x348c0`, `FilterWorldThroughBrush` `0x33250`, `bspNodeToFPoly` `0x365b0`); `bspBuildFPolys`
(`0x36090`); `bspMergeCoplanars` (`0x36200`, the REAL algorithm — group by iLink+coplanar+normal+tex,
`MergeCoplanarPolys` `0x33cb0` = fixpoint `FPoly::TryToMerge`); and `FindBestSplit`'s exact
score-loop op-order (`0x335d0`). **No bevel planes exist** (misconception corrected). Residual
micro-gaps (§2.4) are low-risk and differential-gated. The port can be written from the docs alone
(modulo `bspOptGeom`, a separately-tracked from-scratch port).

### Phase A — node topology

Port `bspBrushCSG_incremental` (structural loop) + `bspRepartition` + the semisolid loop +
`bspOptGeom`; revert `FindBestSplit` to exact scoring; run `TestVisibility` on the new tree. **Delete
the synthetic scaffold** (§2.3) as its collision role is now carried by real bounded leaves.

- **A1 gate — count:** `bytediff_baseline.py` nodes native == editor (**1156** for castle; DXOnly and
  differential fixtures match their editor counts).
- **A2 gate — structure (order-independent):** new harness `node_multiset.py` — the multiset of
  `(quantized plane, node_flags, iSurf-role)` matches; every solid leaf watertight (no leak: the
  grid-solidity oracle finds 0 leaked-solid cells, down from 95).
- **A3 gate — node-for-node (index order):** `Nodes[i]` identical for `plane`, `iFront`/`iBack`
  (`iChild`), `iPlane`, `iSurf`, `node_flags`, `iZone`, `NumVertices` — the editor's exact node
  emission order. (A3 may partially depend on B/C for `iSurf`/`iVertPool` values; assert the
  structural fields first, tighten to exact indices as B/C land.)
- **Must not regress (continuous — behaviour gates):** collision box-drop
  (`test_native_collision.py`), zone membership (`zone_ground_truth.py`), and the **non-geometry**
  offline suite. **Branch-end acceptance (not mid-phase):** CSG differential a/c/d/e byte-diffs and
  the full offline suite (baseline **1241 passed, 1 skipped, 2 xfailed**) + `cargo test` — these
  geometry goldens are red by design until the faithful pipeline is complete (§3/§4).

### Phase B — FVert pool + point/vector dedup ORDER

The 3604→16163 jump and the point pool 1563→2035 come from the fat fragments retained through
`bspBuildFPolys`+`bspMergeCoplanars` and stored by `bspAddNode`. Byte-identity here requires the
**exact insertion order and dedup thresholds** of `bspAddPoint`/`bspAddVector` (the linear
first-within-tolerance scan) to match, AND the consecutive-duplicate collapse in `bspAddNode`'s vert
loop (`bspbuild-splitpolylist-decode.md §bspAddNode`), AND the `iSide` fields from `bspOptGeom`.

- **B gate:** serialized `Verts` array byte-identical (`iVertex`, `iSide` per FVert; count 16163);
  `Points` and `Vectors` arrays byte-identical (count + order + f32 bit-patterns). Harness:
  `pool_diff.py` compares each array bytewise.
- **Must not regress:** everything from A.

### Phase C — surf parity

438→485 surfs is downstream of the fragment/zone differences (surfs are allocated by `bspAddNode`
when `iLink==Surfs.Num`). Once A/B produce the editor's node+fragment set, surf allocation order
follows.

- **C gate:** serialized `Surfs` array byte-identical (`texture` ref, `PolyFlags & 0x3cffffff`,
  `pBase`, `vNormal`, `vTextureU`, `vTextureV`, `iActor`, `iBrushPoly`, `iZone`, `iLightMap` — the
  last `-1` until Phase E). Count 485. Harness: `surf_diff.py`.
- **Must not regress:** A/B + the material/texture-catalog goldens.

### Phase D — render `Bounds` (0→484) + `LeafHulls`

Port the faithful `bspBuildBounds` (`FilterBound` + `SplitPartitioner` + `BuildInfiniteFPoly` +
`UpdateBoundWithPolys`/`UpdateConvolutionWithPolys`, `bounds-and-zonelayout.md §1.3-1.8`), replacing
the `cull_parallel_planes`/±WORLD_MAX shortcut. Emit `Bounds` FBoxes + `iRenderBound` and the real
`LeafHulls` runs + `iCollisionBound`, reproducing the FBox `+=` quirks (§1.8) and the
front-first/back-overwrites `iCollisionBound` order.

- **D gate:** `Bounds` array byte-identical (484 FBoxes; 6×f32 + valid byte each); `LeafHulls`
  byte-identical; per-node `iRenderBound`/`iCollisionBound` identical.
- **Must not regress:** the **live render gate** (no OccludeBsp NULL-FBox crash — `iRenderBound`
  must never index past a populated `Bounds`) and the **live collision gate** (pawn `phys=1`, rests
  at the editor Z — `test_native_collision.py` + the `uplayctl` box-drop numeric check).

### Phase E — lightmaps byte-identical

Run the native `LIGHT APPLY` bake (`sections/20`, `light.rs`) on the now-identical geometry.
`LightMap`/`LightBits`/`Lights` are functions of the surfs + lights; identical geometry is the
precondition, then the lumel grid + shadow bits must match the editor's bake.

- **E gate:** `LightMap`, `LightBits`, `Lights` arrays byte-identical; `harness/lit_diff.py` +
  `lightmap_reconcile.py` clean. (This may be the hardest FP surface — the bake integrates many
  light contributions; if §6 finds x87 anywhere it is likely here.)
- **Must not regress:** the lightmap goldens; the lit-render live gate.

### Phase F — package wrapper

Name table, Import table, Export table (offsets/sizes now that the body is fixed), and generations.
The body is byte-identical from A–E, so the wrapper is the last mile.

- **F gate:** the full `.dx` diffs to zero **except the excluded GUID/timestamps** (Q1) — or, if
  Andrzej wants whole-file identity, with the golden GUID copied in. `self_check` + a whole-file
  `cmp` (masking the GUID bytes) against the golden.
- **Must not regress:** `self_check` invariants (Actors[0]=LevelInfo, Actors[1]=Brush, PlayerStart);
  the level round-trips and loads in-game.

---

## 4. Parity preservation during the transition (the safety net)

The rewrite touches the load-bearing build core. **Reconciled with the big-bang caveat (§3):** the
core swap is one branch, so the *geometry-shaped* goldens (the CSG differential a/c/d/e byte-diffs,
the `bytediff_baseline` counts, and any test asserting exact node/pool/surf output) are **expected
red mid-branch** and go green only when the faithful pipeline is complete — for those, "must not
regress" means **green at branch-end acceptance**, and the A–F gates are the *internal* progress
diagnostics that walk them back to green. The safety nets below are the ones that must hold
**continuously** (they gate *playability/behaviour*, which must never regress even mid-swap), not the
exact-byte goldens:

- **`point_in_solid` stays as a differential oracle.** After each phase, a dense-grid solidity
  sweep (the existing `csg_divergence_repro.py`/grid sampler) asserts the faithful tree's solid/void
  field agrees with `point_in_solid` at ≥ today's 99.76% and the leaked-solid-cell count is 0 (the
  faithful build must be watertight, strictly better than the scaffold's 95 residual leaks).
- **The collision box-drop test is the swap tripwire.** `test_native_collision.py` (box sweep lands
  at floor+extent) and the `cargo` `leaf_bounding_*` unit tests are kept until the scaffold is
  deleted; when Phase A removes the scaffold, the box-drop test must pass on the faithful hulls in
  the SAME commit — a red box-drop blocks the deletion.
- **The full suite is the branch-end acceptance, not a per-phase gate.** `bin/test` (baseline
  **1241 passed, 1 skipped, 2 xfailed**) + `cargo test` must be green **when the core-replacement
  branch merges** — that is the all-or-nothing acceptance (§3). Mid-branch, the geometry goldens
  (CSG differential a/c/d/e, `bytediff_baseline`) are red *by design* while the faithful pipeline is
  assembled; the A–F gates track their return to green. The **non-geometry** suite (CLI, texture-
  catalog, trunk I/O, materialize plumbing) must stay green throughout. The a/c/d/e fixtures are the
  fast inner loop for the geometry work; b/f are currently xfail (the un-ported `bspOptGeom`) and
  should flip to **pass** at branch-end once `bspOptGeom` lands — a positive gate, not a regression.
- **Live gates** (per phase that changes runtime-visible output): D re-runs the pawn-rest + render
  checks; E re-runs the lit render; F re-runs an in-game load.

---

## 5. Data-flow summary (the new plumbing)

```
trunk brushes ──> [structural?] ──┐
                                   ├─> bspBrushCSG_incremental(world Model)   # grows nodes+surfs+verts
                                   │      uses: temp brush BSP (bspBuild), FilterFPoly, bspAddNode
                                   ▼
                          world Model (fat, watertight)
                                   │
                          bspRepartition:
                            bspBuildFPolys ─> [fat FPoly list] ─> bspMergeCoplanars
                                   │
                            bspBuild(SplitPolyList/FindBestSplit exact) ─> repartitioned nodes
                            bspRefresh
                                   ▼
                          TestVisibility (zones.rs) ─> leaves, iZone, ZoneMask, Zones[]
                                   │
                  [semisolid brushes] ─> bspBrushCSG_incremental (NOT repartitioned)
                                   │
                            bspOptGeom  (T-junction/redundant trim; sets iSide)
                                   ▼
                            bspBuildBounds ─> Bounds + iRenderBound, LeafHulls + iCollisionBound
                                   ▼
                  model_write::serialize ─> UModel body ─> assemble ─> .dx
                                   │
                  point_in_solid ── (validation oracle only; grid-solidity gate)
```

Pool order (Points/Vectors/Verts) and surf identity are emitted **inside** `bspAddNode` as nodes are
added — so Phases B/C are not separate passes but the *observable byte-consequences* of getting the
node-emission order (Phase A) exactly right, plus faithful dedup thresholds. They are gated
separately because a topology that is structurally right can still mis-order the pools.

---

## 6. Risk register — floating-point determinism is the crux

Byte-identity of a BSP built from FP split-scoring + FP vertex dedup requires the port to reproduce
UnrealEd's **exact f32 results, bit for bit**, at three coupled surfaces:

1. **Classification counts drive topology.** `FindBestSplit`'s `Splits/Front/Back` come from
   `SplitWithPlane` classifying each poly against a candidate plane with the **0.25 threshold** on an
   f32 dot product. A single poly landing on the other side of the band picks a different splitter →
   the whole subtree diverges → nothing downstream can be byte-identical. This is a **hard,
   cliff-edged** dependence, not a tolerance.
2. **Split vertices are stored verbatim.** `SplitWithPlane`'s intersection
   `inter = prev + (cur-prev)·(prev_d/(prev_d−this_d))` is serialized as raw 4-byte f32. Even a
   last-ULP difference changes the on-disk bytes AND can flip a `bspAddPoint` dedup (threshold
   0.002) → different pool order. Byte-identity here is unforgiving.
3. **Normalization / sqrt.** `CalcNormal` does `1/sqrt(|n|²)`; `size()` does `sqrt(dot)`. If the
   editor uses `sqrtss` (IEEE correctly-rounded, == Rust `f32::sqrt`) parity is reachable; if it
   uses `rsqrtss` (fast ~12-bit approx) or an x87 `fsqrt`+reciprocal, Rust cannot match without
   emulating that exact approximation.

**FP evaluation model — RESOLVED by Phase 0 (was "the decisive unknown"): SSE-scalar, bit-exact
reachable.** The premise that this might be a **1999 MSVC6/x87** build (80-bit intermediates ⇒
bit-exact unreachable without emulation) is **false for these binaries.** The UED22 DLLs are a
**2022 MSVC/VS2022 rebuild** (linker 14.32, TS 2022-10-29; the `dx-lum-uned` container that builds
the golden ships the **MD5-identical** `Editor.dll`/`Engine.dll`). 32-bit MSVC has defaulted to
`/arch:SSE2` since VS2012, so scalar float is `movss/addss/mulss/divss/comiss` on XMM — true 32-bit,
rounded every op, exactly Rust `f32`. Phase 0 disassembled **every** classification/pool site and
found them **all SSE-scalar** (`re-raw-zones/fp-classification-sites.md`): the ±0.25 classify band
(`comiss`), the split-param `t=num/den` (**`divss`**, IEEE == Rust `f32/f32`), the split-vertex
interpolation (`mulss/addss`), `PlaneDot` (packed `mulps`+shuffle reduction), the `bspAddPoint`
dedup (SSE **squared**-distance vs 0.002), and the surf-normal normalize `NormalizeSlow` (`|n|²`
f32 → `sqrtsd` f64 → f32 → `1.0f/s` `divss`). **No x87 and no `rsqrt` on the surf path.** (The one
x87 site, `FVector::Normalize` `0x24940`'s `fdivrp` reciprocal, is NOT the normalize `CalcNormal`
calls — residual xref, §below.)

**Verdict (Phase-0, evidence-backed):** *ACHIEVABLE — GO.* Bit-exact `f32` parity is reachable; the
reviewer's caution that "observed `minss/mulss` might be localized FVector intrinsics, not proof the
scalar CSG hot path is SSE" is **dispositively answered** by disassembling the scalar hot path
itself (the `divss` split-param, the `comiss` classify band) — it *is* SSE-scalar. The remaining FP
work is **operation-ORDER fidelity** (match `PlaneDot`'s pairwise reduction and each dot's
left-to-right shape; `fpoly.rs` is already built for this), proven per-site by a differential trace —
engineering, not precision emulation. **Fallbacks, in preference order:**
- **SSE-scalar+`sqrtss`/`divss` (the actual finding):** match operation order → bit-exact. Pin with
  a per-op differential (identical inputs to a captured editor trace vs the Rust op).
- **If a *future* site (e.g. rotated-brush `BuildCoords`, the lightmap bake) uses `rsqrt`/x87/a sine
  TABLE:** emulate that exact op locally (a `rsqrtss`+Newton replica, f64 intermediates rounded at
  the store point, or a ported `GMath` sine table) — scoped to that site.
- **If a CLASSIFICATION-affecting site is x87/rsqrt-bound and unemulatable — the honest fallback is
  NOT snap.** Canonicalization is **narrow**: a snap pass only rescues sub-ULP value noise on an
  **already topology-identical** tree. A 1-ULP split vertex can flip a `bspAddPoint` dedup or
  reclassify a poly across the ±0.25 band → a **topology cliff** no snap can fix. So if such a site
  existed the honest target would be **"abandon literal byte-identity; keep structural + functional
  parity"** (topology multiset + section-count parity + a snapped-float diff as the fidelity bar),
  not "byte-identical after snap". **Phase 0 found no such site on the castle surf path**, so this
  fallback is not triggered here — but it is the honest answer if the lightmap bake (Phase E) or
  rotated content later surfaces one. This is Q2 for Andrzej.

**Other risks:**
- **Decode gap (§2.4).** `FilterFPoly` leaf funcs, bevel-plane generation, `bspBuildFPolys`,
  `bspMergeCoplanars`, `bspOptGeom` are not yet instruction-exact. Mitigation: Phase 0 blocks on
  decoding them. Highest-uncertainty item after FP.
- **`bspOptGeom` is a from-scratch port** with no prior native code; it affects node count AND FVert
  `iSide`. Risk it is large/subtle. Mitigation: decode first; gate on the b/f fixtures flipping to
  pass.
- **Editor non-determinism** (Phase-0 gate 3). If the editor's own build is not reproducible
  (e.g. hash-map iteration order, uninitialized pool slack serialized), byte-identity is impossible
  by construction. Low likelihood (BSP build is deterministic given fixed params) but decisively
  checked early.
- **Package GUID/timestamp** (Q1) — the header can never match an independent save; scope must
  exclude or copy it.
- **Scope creep vs playability.** The current build is playable; the rewrite must not regress that
  at any phase (the box-drop tripwire, §4). Risk that deleting the scaffold before the faithful hulls
  are proven opens a collision hole — mitigated by same-commit deletion+gate.

---

## 7. Open questions for Andrzej / the coordinator

- **Q1 — byte-identity scope.** Is the target the **`UModel` body + Name/Import/Export tables**
  (GUID/timestamps excluded, since the package GUID is a per-save random value and can never match an
  independent editor save), or **literal whole-file identity** (which requires copying the golden's
  GUID into the native save)? The phases are written for the former; F can do either.
- **Q2 — fallback if bit-exact FP proves infeasible at some site.** Phase 0 found the castle CSG
  surf path **fully SSE-scalar** (no such site), so this is moot for the castle. It re-arms only if a
  **classification-affecting** site in the lightmap bake (Phase E) or rotated content turns out
  x87/`rsqrt`/sine-table and unemulatable. **If it does, the honest fallback is NOT snap** — a snap
  pass only fixes sub-ULP noise on an already topology-identical tree, and a 1-ULP split vertex can
  flip a dedup / reclassify across the ±0.25 band into a topology cliff. So the real question for
  Andrzej is: if a classification site resists emulation, is **"abandon literal byte-identity, keep
  structural + functional parity"** (topology multiset + section-count parity + snapped-float diff as
  the bar) the accepted target, or is literal byte-identity abandoned entirely for that content class?
- **Q3 — effort ceiling / sequencing.** This is a large multi-phase port (est. N-3+: a decode spike
  plus ~6 build phases, including two from-scratch ports — `bspOptGeom` and the faithful
  `bspBrushCSG`). Is full byte-identity the priority now, or is the current **playable + structurally
  close** build acceptable to ship while this proceeds in the background? (The playability blocker is
  already fixed; byte-identity is a fidelity bar, not a functional one.)
- **Q4 — is `Test_Castle.dx` the authoritative golden, or should the oracle always regenerate?** The
  committed `.dx` could drift from the trunk. Recommendation: treat the regen script (Phase-0 gate 4)
  as authoritative and diff against a freshly-built golden, keeping the committed `.dx` only as a
  convenience snapshot. Confirm.
- **Q5 — does the editor's `MAP REBUILD` semisolid/detail handling depend on brush `PolyFlags` our
  trunk doesn't yet carry faithfully?** (The semisolid LOOP-3 layer contributes nodes; if the trunk's
  brush flags don't round-trip exactly, the node count can't match.) Flagged for verification during
  Phase A.

---

## 8. Decisions recorded

The load-bearing choices (port the faithful incremental `bspBrushCSG`; delete the synthetic
scaffold; the byte-identity scope + FP-feasibility stance; the oracle definition) are appended to
`dev/docs/decisions.md` under `2026-07-17 04:36 UTC` — this spec is ephemeral; the ledger is durable.
