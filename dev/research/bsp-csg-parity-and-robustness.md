# Native CSG/BSP parity — algorithm fidelity and numeric robustness

**Date:** 2026-10-03 · **Status:** research only — no decisions taken, nothing implemented.
**Question:** How close is the native BSP/CSG to UnrealEd, what are the remaining divergences, and
what does the robustness literature say about making this class of computation reproducible?

## Summary

- **The parity target is not a 1998 x87 binary.** The committed editor substrate (`uned/UED22`)
  is a **2022 MSVC 19.32 rebuild**: `TimeDateStamp` 2022-10-29, linker 14.32, and 32-bit MSVC has
  defaulted to `/arch:SSE2` since VS2012. A whole-`.text` census found **zero `fldcw`/`fnstcw` and
  zero FMA** in `Engine.dll`/`Editor.dll`. The "bit-exact emulation of a 1998 single-precision x86
  implementation" tension the brief poses **does not apply to this substrate** — it was measured and
  retired on 2026-07-15 (`old/dev/docs/spikes/2026-07-15-native-materialize/41-fp-model-x87-vs-sse.md`).
- What remains is **operation-order fidelity in f32**, not precision emulation. Every divergence
  closed in the last month was an op-order, op-shape or algorithm-step difference — never an
  unreachable rounding mode.
- **Parity is high and measured, not asserted.** Two of five ladder levels are byte-exact to
  **N=623** actors; the other three are byte-exact to N=152/200/202 and blocked on three named,
  individually root-caused divergences.
- **Every open divergence is now a lighting/visibility or gate-mechanism issue, not a CSG geometry
  issue.** The CSG/BSP core's last two blockers (OceanLab N=203 point weld, WanChai N=59 frontier
  recursion order) were both closed in September. The remaining three are `GetVisibleSurfs`
  occlusion, a lightmap-run gather, and one orphan-`Verts` count the gate cannot tolerate.
- The **ULP-level divergences are explained**, repeatedly and specifically: a double-precision
  matrix compose where the editor chains three f32 `FCoords`; a GMath sine table built with
  double π instead of float32 π (4683/16384 entries wrong); a `MergeNearPoints` that remapped
  `FVert.iVertex` but not `FBspSurf.pBase`. None needed x87.
- **The robustness literature mostly does not help here, and some of it actively hurts.** Exact
  predicates, simulation of simplicity and snap-rounding all buy *correctness*; the requirement is
  *reproducing another implementation's float behaviour*. Adopting them would move native away from
  the oracle. The one exception is diagnostics: an exact oracle is useful for *measuring* residue.
- **No reusable open implementation matches both the model and the licence.** The Quake-lineage
  compilers are the closest algorithmic cousins (brush CSG → BSP → portals → vis → radiosity) but
  are GPL-2.0; the modern robust kernels (CGAL Nef, Manifold, libigl) assume watertight manifold
  meshes, which UE1's polygon soup is not.
- **The plane-based-geometry literature is the one genuinely relevant external thread** — and it
  confirms the engine's own design choice rather than suggesting a change.
- **UE1's point-weld tolerance is 100× looser than modern UE** (`THRESH_POINTS_ARE_SAME` 0.002 vs
  0.00002). That one constant is why the campaign's hardest divergences are point-weld hit-vs-miss
  questions: at 0.002 uu the outcome turns on descent order and tree liveness, not on distance.
- **The functions this project depends on most have no public documentation at all** —
  `FilterLeaf`, `FilterWorldThroughBrush`, `bspZoneCSG`, `bspOptGeom` and the split-plane scoring
  formula appear in no Epic or community source. uedcli's disassembly is the only record of them,
  which is both a clean-room strength and the reason there is no external cross-check.

## What we have today

The native engine is `old/uedcli-native/` — 26,589 LOC of Rust across `src/`, of which the geometry
core is:

| File | LOC | Role |
|---|---|---|
| `bspcsg.rs` | 6150 | incremental `bspBrushCSG` pipeline, `FindBestSplit`, `SplitPolyList`, `bspMergeCoplanars`, repartition, point/vector pooling, `find_nearest_vertex` |
| `visible_surfs.rs` | 2042 | `URender::GetVisibleSurfs` — six-face 1024×1024 cube-map rasterization with per-zone span buffers |
| `zones.rs` | 1859 | `TestVisibility` portalization: leaves, portal graph, zone flood, per-zone fragment split |
| `build.rs` | 1542 | pooling (`bspAddPoint`/`bspAddVector`), `bspAddNode`, non-incremental build driver |
| `bspoptgeom.rs` | 980 | `bspOptGeom` — T-junction insertion + shared-side linking |
| `passes.rs` | 901 | `bspMergeCoplanars`, `bspRefresh`, `bspBuildBounds` |
| `fpoly.rs` | 791 | `FPoly`: `CalcNormal`, `Fix`, `RemoveColinears`, `Finalize`, `SplitWithPlane`, `Transform` |
| `csg.rs` | 534 | CSG leaf filter: `FilterEdPoly`/`FilterLeaf` and the four per-`CsgOper` leaf funcs |
| `f32.rs` | 21 | the f32-faithful plane-distance helper, plus the FP-fidelity contract in its header |

`light.rs` (1908), `linecheck.rs` (546) and `permeating_lights.rs` (811) complete the materialize
path; `render.rs`, `paths.rs`, `collision.rs` are adjacent.

### The stage pipeline as it exists

`bspcsg.rs::build_geometry_bspcsg` is the live path. Order, with the editor routine each stage
ports:

1. **Empty world, `root_outside = false`** — a DX level starts solid; `Subtract` carves (engine `UModel::RootOutside`).
2. **Pass 1 — structural brushes, incremental.** Walk brushes in actor order; per brush
   `bsp_brush_csg` (`bspBrushCSG`, `Editor.dll 0x355e0`): `brush_loop1` builds the transformed
   `FPoly` list, `filter_world_through_brush` (`FilterWorldThroughBrush 0x33250`) carves the
   accumulated world, `bsp_filter_fpoly`/`filter_ed_poly`/`filter_leaf` filter the brush's own faces
   down the live tree, `bsp_add_node` commits survivors, `cleanup_nodes` splices dead subtrees.
   Semisolid brushes are deferred to pass 2; `PF_NotSolid` non-semisolid brushes (portal or not) run
   here, because they are valid `FindBestSplit` candidates.
3. **World `bspRepartition`** — `bsp_build_fpolys`/`make_ed_polys` rebuild a fat fragment soup from
   the live tree, `bsp_merge_coplanars` reassembles each source face's fragments, then
   `bsp_build` → `split_poly_list` → `find_best_split_exact` re-cut the whole tree; then
   `passes::bsp_refresh` and `bsp_refresh_points_vectors`.
4. **`TestVisibility` / zones** — `zone_pass` → `zones::assign_leaves_and_zones`: leaves (Pass A),
   portal graph (Pass B `MakePortals`), zone barriers (Pass B′ `BlockPortal`), zone flood (Pass C),
   per-node `iZone` + per-zone fragment split (Pass D `AssignAllZones`), `ZoneMask` (Pass E),
   `Zones` + `Connectivity` (Pass F). Bracketed by `swap_node_children` because this pass reads the
   *engine* child convention while native's CSG carries the swapped one.
5. **Pass 2 — semisolid detail brushes, incremental, not world-repartitioned.**
6. **Frontier repartition** — `collect_repartition_frontier` snapshots the pre-detail frontier
   (209 nodes on UNATCO, matching the editor's own count); `repartition_frontier` re-cuts only the
   subtrees that grew; `compact_unreachable_nodes`; `bsp_refresh_points_vectors_stale_orphans`.
7. **`finalize`** — final `swap_node_children`, clear `NF_IsNew`, bbox from `Points`.
8. **`bspoptgeom::bsp_opt_geom`** — `merge_near_points`, T-junction vertex insertion (pass 1),
   shared-side `iSide` linking + `NumSharedSides` (pass 2), then the previously-unported
   `compact_unreferenced_surfs`.
9. **`passes::bsp_build_bounds`**.

Stage **order itself was a parity finding**: `TestVisibility` runs *between* the world repartition
and the detail-brush loop (`csgRebuild 0x4a650` → `bspRepartition` at `0x1004a89a` →
`TestVisibility` at `0x1004a8af` → detail loop at `0x1004a9e8`), live-confirmed on UNATCO
(repartition returns 2953 nodes, first detail brush sees 2984; the +31 is Pass D's own fragment
split). Running it afterwards inflated the fan-out to +81.

### Thresholds and float types

`fpoly.rs` holds the engine constants, all `f32`, all read from `.rdata` by the 2026-06-24
disassembly spike and re-stated in `old/dev/docs/unrealed/leveldesign/kb/csg-bsp.md` §5.3:

| Constant | Value | Where in native |
|---|---|---|
| `THRESH_SPLIT_POLY_WITH_PLANE` | `0.25` | `fpoly.rs` |
| `THRESH_SPLIT_POLY_PRECISELY` | `0.01` | `fpoly.rs` |
| `SMALL_NUMBER` | `1.0e-8` (length²) | `fpoly.rs` |
| `THRESH_COLINEAR` | `9.999999e-05` | `fpoly.rs` |
| `THRESH_POINTS_ARE_SAME` | `0.002` | `fpoly.rs` |
| `THRESH_POINTS_ARE_NEAR` | `0.015` | `build.rs` (also `RING_POINT_TOL`) |
| `THRESH_NORMALS_ARE_SAME` | `2.0e-5` | `build.rs`, `passes.rs` |
| `MERGE_OFFSET_TOL` | `0.002` | `passes.rs` |
| `MAX_VERTICES` | `16` | `fpoly.rs` |
| `BALANCE` / `PORTAL_BIAS` | `50` / `70` | `build.rs` — byte-verified `MAP REBUILD` params |

Float discipline, as the code states it:

- **f32 end-to-end** on the geometry path. `f64` appears 3 times in `bspcsg.rs`, 13 in `fpoly.rs`,
  21 in `bspoptgeom.rs` — and each is a *deliberate* reproduction of an editor site that widens:
  `safe_normal_slow` computes `1.0f32 / ((sq as f64).sqrt() as f32)`; `safe_normal` additionally
  evaluates the reciprocal in f64 because the editor's `0x10051104` stores the x87 result back to a
  32-bit slot; `FSphere`'s radius is `((max_dist_sq as f64).sqrt() * (1.001f32 as f64)) as f32`.
- **No FMA.** `fpoly.rs`'s header forbids `mul_add`; Rust does not auto-contract, and the engine
  emits none.
- **Dot products reduce left-to-right** with explicit parenthesisation: `Vec3::dot` and
  `transform_vector_by` write `(a*p + b*q) + c*r` to match the engine's op order.
- UnrealEd's single-precision behaviour is therefore emulated **deliberately and specifically**, but
  it is SSE2 single precision, not x87 — see Findings.

Opt levels: `bspcsg.rs::Opt` models two candidate-search strides —
`Lame` = `max(NumPolys/4, 1)` (temp brush BSP) and `Good` = `max((n * 0x66666667) >> 35, 1)`
= `NumPolys/20` (the world/frontier repartition path), decoded from the `imul 0x66666667; sar 3`
idiom. There is no separate `Optimal` stride variant; the KB records that `LAME`/`GOOD`/`OPTIMAL`
differ only in `FindBestSplit`'s stride, so whether a third stride exists for the `MAP REBUILD`
path is worth re-confirming against the decode.

### Where the ladder stands

From `old/dev/docs/spikes/2026-09-03-incremental-actor-parity/harness/parity_ladder_data.json`
(updated 2026-09-16):

| Level | Byte-exact to N | Total actors | Status |
|---|---|---|---|
| UNATCO HQ | 623 | 1437 | advancing (no bail; N=243..622 not individually spot-checked) |
| UNATCO Island | 623 | 3653 | advancing (same caveat from N=353) |
| OceanLab Lab | 202 | 2745 | blocked (gate mechanism) |
| WanChai Market | 200 | 2288 | blocked (`GetVisibleSurfs`) |
| NYC Bar | 152 | 487 | blocked (lightmap gather) |

The bar is full package-byte identity modulo a closed, evidence-backed exclusion set (per-save-random
fields, `MAP REBUILD` GC bookkeeping, orphan `iVertex`, `FName` case, two per-frame occlusion flag
bits). `old/NATIVE-MATERIALIZE.md` is the source of truth, and its prime directive is explicit: a
reproducible algorithm difference is **fixed, never masked**.

## Findings

### 1. The divergence record

Every recorded divergence, with magnitude, hypothesis and where it lives. "ULP" at |x|≈256 is
`2^-15` = `3.0517578125e-05`.

| # | What diverges | Magnitude | Hypothesis / cause | Where recorded | State |
|---|---|---|---|---|---|
| 1 | OceanLab N=203: two world `Model2.points` x-values near x=−256 | 2 ULP (`0xc3800004` vs `0xc3800002`) | **Root-caused**: the real `bspRepartition` calls `bspRefresh(Model, NoRemapSurfs=1)`, suppressing surf compaction, so a dead node's surf/point survives to `bspOptGeom`'s `merge_near_points`; native compacted eagerly, so the weld target was already gone | `board/to-spike/oceanlab-n-203-world-model2-split-vertex-ulp/`, spikes `2026-09-13-oceanlab-n203-pbase-provenance`, `2026-09-15-oceanlab-n203-{bspoptgeom-points,fwtb-classify,repartition-surf-defer}` | **points FIXED**; gate still FAILs on one extra orphan `Verts` entry (35265 vs 35264) — a `parity_gate.py` exclusion built for same-count orphans, not a count mismatch. Owner question filed. |
| 2 | WanChai N=201: world surf 616 gets no lightmap run (`dark`) where UED22 allocates an empty one; `Model.Lights` 2019 vs 2020 | 1 record | `GetVisibleSurfs` rejects a thin CSG-subtraction sliver (`Brush1164`'s `2DLoftSIDE` face) for `Light431`. Rasterizer, span subtraction, node visit order and 163/165 call sequence all proven byte-faithful against live capture; **remaining hypothesis: the real `FSpanBuffer`'s starting state is not fresh** at the matching chain's start | `board/to-spike/wanchai-n-201-world-model2-body-diverges/`, spikes `2026-09-15-wanchai-n201-{surf616-getvisiblesurfs-miss,raster-footprint,sequence-diff}` | NOT fixed |
| 3 | NYC Bar N=153: 3 world `LightMap` records get an `iLightActors` run UED22 leaves at −1; `Lights` 484 vs 478, `LightBits` 6003 vs 5891 | 3 records | Per-surf gather commit. Round 3's "shadow-ray never fires" finding was **refuted** by round 9's live capture (`illuminateSurf`'s raytrace at `0x100a5a04` fires with mixed results); a later per-light commit step (`0x100a5ab5`–`0x100a5ac2`) found but not identity-confirmed | `board/inbox/nyc-bar-n-153-world-model2-lightmap-runs-ued22/` | NOT fixed |
| 4 | UNATCO Pass-1: 100 nodes' plane floats | 1 ULP (first: `0xbf800000` vs `0xbf7fffff`, node 359, `Brush578`) | **Root-caused and fixed**: the editor builds the scaled-brush transform in per-step f32 (`FCoords::operator/=(FScale)` etc.); native composed in Python double. `1.0f/0.624999f` = `0x3fcccce3` in f32 vs `0x3fcccce2` in double — the one ULP decides whether `SafeNormalSlow` lands exactly ±1.0 | `native-materialize-findings.md` §"UNATCO live per-brush Pass-1 tree-shape trace" (2026-09-02); `rotation.editor_vector_xform`/`editor_point_xform` shipped | 100 → 73; the remaining 73 sit on unscaled Add/Subtract brushes (authored-vs-recomputed-normal thread) |
| 5 | Vandenberg Pass-1: 2996 nodes' plane values | up to ~32 ULP | **Root-caused and fixed, two mechanisms**: (a) `rotation.py`'s GMath sine table was built with **double π; the editor uses float32 π** — 4683 of 16384 entries wrong; (b) the per-face normal is `SNS(X · CalcNormal(local))` for every brush poly, authored normals ignored | `board/to-build/native-materialize/vandenberg-count-parity-was-error-cancellation/` | 2996 → 65 (all ~1 ULP, mostly `plw`, no count effect) |
| 6 | Vandenberg Gas counts | nodes −6 → +659 → +397 | The old −6 was **error cancellation**, not correctness: once the per-poly world inputs were live-proven bit-identical, the count swing exposed a large compensating divergence further down. Now localized entirely to the world `bspRepartition` (editor enters Pass 2 at 8702 nodes/4118 surfs, native 9191/3839; soups 6158 vs 6156 polys) | same item | open |
| 7 | OceanLab N=13: one CSG-soup split vertex | 1 ULP in x, `2^-15` in y | `MergeNearPoints` remapped `FVert.iVertex` but not `FBspSurf.pBase`, so a welded point survived `bspRefresh` with a stale base | `board/done/oceanlab-n13-csg-soup-split-vertex-1-ulp/` | FIXED (`db85703`) |
| 8 | WanChai N=19 / UNATCO N=8: node-plane `W`, CSG-soup `FPoly.Base`, `Brush.Region` | near-tie point dedup | Native's incremental CSG must dedup points with the editor's radius-pruned `FindNearestVertex` descent over the live world tree — walked in native's live child convention, which carries the swapped CSG `iFront`/`iBack`, so the descent must swap near/far | `board/to-build/native-materialize/faithful-incremental-bsp-dedup-rewrite/`, spike `2026-09-05-faithful-dedup-fix-attempt` | FIXED faithfully; the stopgap tie mask removed |
| 9 | WanChai N=59 | mover `Polys@Model2` | `collect_repartition_frontier` recursed `iBack` before `iFront`; the real editor checks `iFront` first | spike `2026-09-14-wanchai-n59-semisolid-repartition-order` | FIXED |
| 10 | UNATCO N=226 / Island N=332 | permeating-light / leaf vertex tie | portal-graph freeze | board items of the same names | FIXED (2026-09-13) |
| 11 | NYC 747 `Brush562` (Pitch=32768, Yaw=32768, Roll=59392) rotation matrix | 2 ULP in one matrix entry → **1–6 ULP in 3 of 8 node planes** | A genuine non-cardinal multi-axis `FRotator` composes as one Python-double matmul in `rotation.py`, where the editor chains three single-axis f32 `FCoords` (`((this*Roll)*Pitch)*Yaw`, `ABrush::BuildCoords 0x111390`) | `board/to-build/native-materialize/fpoly-rotation-matrix-ulp-gap-confirmed-real/`, `rotation-py-3-axis-non-cardinal-fcoords-compose/`, findings §"NYC 747 rotated-brush transform cross-validation" | **Real, measured, NOT shipped.** Corpus scan: only 2 brushes in 21 trunks have all three axes non-cardinal (Vandenberg `Brush2`, `Brush246`); `Brush246` diverges 1 ULP (`0x3cfd8b2e` vs `0x3cfd8b2d`). Blocks nothing today |
| 12 | Lighting "grid" bucket: 54–393 `Points`/`Vectors` values | **tens of ULPs** (e.g. `(0, −312, −255.99993896484375)` vs `(0, −312, −256.0)`); ~4.8e-6 / 6.0e-6 on some normals | Not a rounding-mode artifact. Traced to `CSG_Add`-face recompute provenance; partially closed by the `editor_vector_xform` fix, residue diffuse across the level | `native-materialize-findings.md` (several rounds) | open, diffuse |
| 13 | Residual node/leaf counts on non-ladder levels | Area51 +85 nodes/+51 leaves (`Brush1852`); TrainingFinal −59 (`Brush162`, recomputed-normal ULP drift); Garage −68 (three pool-snapped verts stall a wall merge and flip the repartition root); smuggler +4 surfs (4 `PF_Semisolid` Adds); WanChai +20 (one repartition splitter pick fed by a +2 root-soup delta) | per-item | `board/to-build/native-materialize/*` | open, each localized to one brush or one pick |
| 14 | `rotate --by` stored `Location` on a long lever | worst GMath matrix-entry deviation `1.7484555314695172e-07`; reaches 0.001 uu at **5719 uu** lever (two actors 24,000 uu apart rotated 90° store `X=11999.998951`) | UE1's GMath rotator entries are not exactly 0/±1, so a cardinal rotate still accumulates `|L−P| × deviation` | `board/to-spike/rotate-gmath-residue/` | open (p3). The item's own framing is the right one: **which tolerance band is the criterion** — the ~1e-4 vertex-merge band or the cosmetic `CLEAN_EPS` 0.001 — is unsettled, and an exact `Decimal` oracle for cardinal deltas is a free detector |
| 15 | `SplitWithPlane` degenerate-cut behaviour | classification | The engine degrades a degenerate cut to `SP_Back`/`SP_Front` (whole poly, one side); native always returns `Split` and leaves callers to drop the <3-vert fragment | `board/to-build/native-materialize/splitwithplane-degenerate-fragment-fallback/` | open |
| 16 | `CleanupNodes`' flip test | subtree transposition | The engine calls `FPlane::operator|`, a **four**-component dot; `bspcsg.rs` ports it as a three-component normal dot, so a sliver coplanar pair can transpose a whole subtree | `board/to-build/native-materialize/bsp-cleanup-ports-fplane-operator-as-a-3/` | open |

Pattern worth stating plainly: **every single resolved ULP divergence resolved to an op-order,
op-shape, constant-precision or algorithm-step difference.** Not one resolved to an unreachable
rounding behaviour. That is the strongest evidence available that the precision model is right.

### 2. UnrealEd's CSG/BSP as publicly documented

The engine source is **not open-licensed**; nothing below proposes copying it. What follows is the
public/community description plus this project's own disassembly of the binaries it owns.

The CSG model (community-documented, and binary-confirmed in
`old/dev/docs/unrealed/leveldesign/kb/csg-bsp.md`):

- The world starts as **infinite solid**; designers **subtract** rooms, then **add** detail inside
  the carved space. A single red "builder brush" is shaped and committed as Add or Subtract.
- Brushes resolve in **actor order** at rebuild; on overlap the last operation touching a region
  wins. `UEditorEngine::csgRebuild` (`Editor.dll 0x4a650`) empties the world `UModel`, iterates
  `ULevel::Brush()` in actor order calling `bspBrushCSG` per brush, then runs
  `bspBuild` → `bspRefresh` → `bspMergeCoplanars` → `bspOptGeom` → `bspBuildBounds`. `SENDTO
  FIRST/LAST` only reorders the list; no heuristic re-sorts.
- Three solidities: **Solid** (cuts the world BSP, can be subtracted from, can seal a zone),
  **Semisolid** (cuts only itself — the workhorse for off-grid/curved detail), **Nonsolid** (cuts
  nothing; zone-portal sheets, decoration).
- `Rebuild Geometry` discards the tree and reassigns polygons; a BSP rebuild then has to follow.
  "Build Visibility Zones" must stay on or zones are erased
  ([OldUnreal wiki](https://www.oldunreal.com/wiki/index.php?title=BSP_building)).
- The build sliders: **Balance Tree ↔ Minimise Cuts** and **Portals Cut All ↔ Ignore Portals**.
  The OldUnreal wiki gives the GUI defaults as **15/100** and **70%**; this project's byte-verified
  `MAP REBUILD` params are **Balance=50, PortalBias=70** (`build.rs`). The two are not in conflict —
  one is the GUI slider default, the other the console verb's hard-coded pair — but the gap is worth
  keeping in mind when citing "the default".
- **Lame / Good / Optimal** differ only in `FindBestSplit`'s splitter-candidate **stride**
  (`NumPolys/4` vs `NumPolys/20`, decoded from the `imul 0x66666667` idiom). `bspMergeCoplanars`
  runs at every level — the folklore that Optimal "also merges coplanars" is wrong, but different
  strides do produce different coplanar adjacencies, so the geometry really does differ.
- The scoring, byte-verified in `find_best_split_exact`:
  `Score2 = (100−Balance)·Splits`; `Score = |Front−Back|·Balance + Score2`; a portal candidate gets
  `Score −= Score2 · PortalBias/100`. A split of a portal poly counts 16, not 1. Structural
  (`PF_Semisolid|PF_NotSolid`, mask `0x28`) polys are skipped as candidates unless they are portals
  or the whole list is structural.
- The failure modes are **discrete tolerance bands, not overflow** — the community's "floating-point
  overflow, the engine gives up" explanation is false. A face dies in `FPoly::Finalize`
  (`Engine.dll 0x150ac0`) three ways: `RemoveColinears` collapse below 3 vertices (coincident
  vertices < ~1e-4 uu via `NormalizeSlow`'s `SMALL_NUMBER` = 1e-8 on length²; colinear compare at
  `9.999999e-05`), `NumVertices < 3`, or zero area in `CalcNormal` (`0x150510`). The upstream cause
  is `SplitWithPlane`'s ±0.25 uu band (`0x1518b0`): a poly entirely within the band is classified
  `SP_Coplanar` instead of split, producing slivers and T-junctions.
- Hard limits: ~65,536 static BSP nodes (overflow blocks the save) and ~128,000 points
  (`MAX_POINTS` — this is the one that crashes). The OldUnreal 227j patch raises the node ceiling to
  262,144; stock Deus Ex does not.
- The code lineage is UT-era: an `appFailAssert` in `SplitWithPlane` embeds
  `C:\GameDev\UnrealTournament\Engine\Src\UnFPoly.cpp`.

**Epic's own current API documentation is a citable primary source**, because the UE4/UE5 `FBSPOps`
class is the direct descendant of `UnBsp.cpp`/`UnEdBsp.cpp` with the names and parameter semantics
unchanged:

- `bspBuild(UModel*, EBspOptimization Opt, int32 Balance, int32 PortalBias, int32 RebuildSimplePolys, int32 iNode)` — "Builds Bsp from the editor polygon set (EdPolys) of a model." `EBspOptimization` = `BSP_Lame`/`BSP_Good`/`BSP_Optimal`; `Balance` 0–100, **"0 = only minimize splits, 100 = only balance tree"**.
- `bspRefresh` — "if the Bsp's point and vector tables are nearly full, reorder them and delete unused ones". `bspAddPoint`/`bspAddVector` — "add a new point/vector to the model, **merging near-duplicates**". `bspValidateBrush` — "set iLinks on all EdPolys to index of the first identical EdPoly in the list".
- `FPoly::SplitWithPlane(InBase, InNormal, FrontPoly, BackPoly, VeryPrecise)` — "split with plane. **Meant to be numerically stable.**" Plus `SplitWithPlaneFast`, `SplitWithNode`, `ESplitType`.
- `SplitPolyList` is a static `FBSPOps` member taking the model, node/parent info, a poly list and the optimization settings — the recursive splitter. `bspMergeCoplanars` is a `UEditorEngine` virtual.

**But the parts this project depends on most are exactly the parts with no public documentation.**
No public Epic or community source documents `FilterLeaf`, `FilterWorldThroughBrush`, `bspZoneCSG`,
`bspOptGeom`, or — critically — **the split-plane scoring formula**. They are file-static/editor-only
and appear only in circulating source. uedcli's `find_best_split_exact` scoring, its `Opt` strides,
its `FilterWorldThroughBrush` port and its `bspOptGeom` decode are therefore **derived from
disassembly of binaries this project holds, not from any document** — which is the right provenance
for a clean-room reimplementation, and also means there is no external cross-check for them.

### UE1 vs modern `THRESH_*` — the one constant that matters most

The UE1 constants circulate in `Core/Inc/UnMath.h` from Epic's **partial** UT 432 source release.
That release shipped **no licence statement** (the `stephank/surreal` mirror only *assumes* Artistic
License), so it is **not open-licensed** — cite for values, never copy code. The values below match
what this project independently measured from the shipped `.rdata`, which is the stronger tier:

| Constant | UE1 | UE4/UE5 | Measured in `uned/UED22` `.rdata`? |
|---|---|---|---|
| `THRESH_POINTS_ARE_SAME` | **0.002** | **0.00002** | yes — 0.002 |
| `THRESH_POINTS_ARE_NEAR` | 0.015 | 0.015 | yes |
| `THRESH_NORMALS_ARE_SAME` | 2e-5 | 2e-5 | yes |
| `THRESH_VECTORS_ARE_NEAR` | 0.0004 | 0.0004 | yes |
| `THRESH_SPLIT_POLY_WITH_PLANE` | 0.25 | 0.25 | yes |
| `THRESH_SPLIT_POLY_PRECISELY` | 0.01 | 0.01 | yes |
| `THRESH_VECTORS_ARE_PARALLEL` | 0.02 | (dropped) | yes |
| `THRESH_POINT_ON_PLANE` | 0.10 | 0.10 | not cited in the KB table |
| `THRESH_POINT_ON_SIDE` | 0.20 | 0.20 | not cited in the KB table |
| `THRESH_ZERO_NORM_SQUARED` | 0.0001 | 0.0001 | not cited (the KB cites `SMALL_NUMBER` 1e-8 instead) |

**UE1's point-weld tolerance is 100× looser than modern UE** (0.002 vs 0.00002 uu). That single
constant is the reason the campaign's hardest divergences are point-weld hit-vs-miss questions
(items #1, #7, #8 above): at 0.002 uu, a huge number of coordinates are *eligible* to weld, so the
outcome hinges on descent order and tree liveness rather than on distance. `THRESH_POINT_ON_PLANE`
(0.10) and `THRESH_POINT_ON_SIDE` (0.20) are not in the native constant set and are worth checking —
whether UE1's CSG path actually reaches them, or whether they are collision/`FPoly::Inside`-only.

### Deus Ex / UnrealEd 2.2 provenance

Two findings that corroborate §3's x87 verdict from a completely different direction:

- Deus Ex ships on the **UnrealEd 1.0** generation, and the community record states that "when UEd
  1.0 shipped there were bugs with rebuild options, which are fixed in UEd 2.0" — so the retail
  maps were built by the *buggier* build-option generation.
- **"UnrealEd 2.2 for Deus Ex" is a community backport derived from the UT 469e RC8 editor**,
  retargeted at Deus Ex maps. That is an independent explanation for why `uned/UED22`'s DLLs carry a
  2022 MSVC toolchain: they are a modern rebuild of UT-era engine code, not 1999 binaries. Two
  independent lines of evidence — the PE headers and the tool's community provenance — agree.
- OldUnreal's Unreal 227 line documents real *BSP builder* changes (227j: fixed a rebuilder error
  when a surface's texture U/V origin sat far from the surface origin, which caused BSP holes;
  auto-tessellates non-planar BSP surfaces; multithreads BSP partitioning; raises the node ceiling to
  262,144. 227k: a "Post build SemiSolids" option that builds semisolids last). **None of these apply
  to stock Deus Ex** — do not design DX content or parity expectations against 227 behaviour.
- No public document describes a Deus-Ex-specific divergence in the BSP builder beyond the
  UEd 1.0-vs-2.0 rebuild-option bugs. Gap, not a finding.

Design intent, for context: Sweeney's retrospective says CSG + BSP were updated "completely in
real-time" in the editor with no offline rebuild step, and that subtractive geometry existed because
"building is extremely tedious if you are only adding objects."

Community references, with their evidential tier marked:

| Source | Tier |
|---|---|
| [Epic API docs — `FBSPOps`](https://dev.epicgames.com/documentation/en-us/unreal-engine/API/Developer/BSPUtils/FBSPOps), [`bspBuild`](https://dev.epicgames.com/documentation/en-us/unreal-engine/API/Developer/BSPUtils/FBSPOps/bspBuild), [`FPoly::SplitWithPlane`](https://dev.epicgames.com/documentation/unreal-engine/API/Runtime/Engine/Engine/FPoly/SplitWithPlane) | **primary**, descendant code, names/semantics unchanged. `docs.unrealengine.com` deep links 403 to fetchers; use `dev.epicgames.com` |
| [OldUnreal wiki — BSP building](https://www.oldunreal.com/wiki/index.php?title=BSP_building) | community reverse engineering / mapper lore; slider defaults (15 % / 70 % / Optimal), Lame/Good/Optimal, measured node:poly ratios (1.88:1 default, 1.73:1 tuned, 3.04:1 unoptimized) |
| [Unreal Archive mirror — Legacy:CSG](https://unrealarchive.org/wikis/unreal-wiki/Legacy:CSG.html), [Legacy:Solidity](https://unrealarchive.org/wikis/unreal-wiki/Legacy:Solidity.html), [Legacy:Rebuild](https://unrealarchive.org/wikis/unreal-wiki/Legacy:Rebuild.html), [Legacy:Build](https://unrealarchive.org/wikis/unreal-wiki/Legacy:Build.html), [Legacy:Zoning](https://unrealarchive.org/wikis/unreal-wiki/Legacy:Zoning.html) | community wiki, fetchable mirror of `wiki.beyondunreal.com` (which 403s). Rebuild stage ordering, solidity semantics, brush order |
| [BeyondUnreal wiki mirror — BSP, BSP Tree, BSP Hole, Brush, Brush Order, Node Count](https://beyondunrealwiki.github.io/pages/bsp.html) | community wiki. `CsgOper` enum values, editor brush colours, node definition and the 65,536 ceiling |
| [Unreal Archive — Legacy:BSP Hole Background](https://unrealarchive.org/wikis/unreal-wiki/Legacy:BSP_Hole_Background.html) | community wiki; explicitly contains **no** FP or named-function detail. Also the source for "UEd 1.0 rebuild-option bugs fixed in UEd 2.0" |
| [`stephank/surreal`](https://github.com/stephank/surreal) — `Core/Inc/UnMath.h`, `Engine/Inc/UnModel.h` | **circulating source from Epic's partial UT 432 release, shipped with NO licence.** Cite constant *values* and struct layout; **never copy**. `UnBsp.cpp`/`UnEdBsp.cpp` were not in that release and could not be confirmed present in any public mirror |
| [UT99.org engine-limit thread](https://ut99.org/viewtopic.php?t=14671) | community measurement: 63 zones, 65,535 nodes, 128,000 points, world bounds ±32,700 uu — corroborates `UnModel.h`'s enums |
| [Sweeney retrospective](https://www.gamedeveloper.com/design/classic-tools-retrospective-tim-sweeney-on-the-first-version-of-the-unreal-editor) | interview; design intent for real-time CSG and subtractive worldbuilding |
| [Wolf's BSP FAQ](http://www.hypercoop.tk/infobase/archive/wolfsunreal/bspfaq.html) | mapper folklore, reconciled against disassembly in the KB. **Unverified** — HTTPS fails, page unread this pass |
| "Basic Level Design BSP (Unreal Tournament)" wiki page | **do not cite for UI** — the KB establishes it is actually UE4 content |
| `old/dev/docs/spikes/2026-06-24-bsp-csg-hole-mechanism-from-binary.md` + `2026-06-26-bsp-partition-heuristic-from-binary.md` | this project's own static disassembly of the binaries it owns — the strongest tier available, and the tier the KB defers to wherever folklore disagrees |

One further community oracle worth knowing about: **`yrex`'s BSP Tool** post-processes a *built* map
to remove insta-kill void holes and fix invisible polys with wrong zone assignment (it cannot fix
collision problems or zone leaks). That is a catalogue of what the real builder gets wrong — a useful
cross-check for D2's "should this face exist?" question.

### 3. The x87 question, settled

This is the brief's "crucial tension", and it has an answer specific to this substrate.

**What the general literature says.** On 32-bit x86 the x87 FPU computes in 80-bit registers; the
precision-control field selects 24/53/64-bit mantissas, and VC++ historically set 53-bit, so `float`
arithmetic ran at intermediate double precision. Double rounding (80→53→32) can round incorrectly.
D3D9 silently set 24-bit precision unless `D3DCREATE_FPU_PRESERVE` was passed, so identical code gave
different results on different threads
([Dawson, *Intermediate Floating-Point Precision*](https://randomascii.wordpress.com/2012/03/21/intermediate-floating-point-precision/)).
MSVC's 32-bit default changed from `/arch:IA32` to `/arch:SSE2` **in Visual Studio 2012**
([MS docs, `/arch (x86)`](https://learn.microsoft.com/en-us/cpp/build/reference/arch-x86?view=msvc-170)).
Shewchuk's own `predicates.c` carries the same warning — it "requires special configuration on
processors with extended-precision registers"
([CMU](https://www.cs.cmu.edu/~quake/robust.html)).

**What measurement says about *this* binary.** `old/dev/docs/spikes/2026-07-15-native-materialize/41-fp-model-x87-vs-sse.md`
disassembled the shipping `uned/UED22` DLLs:

- `Engine.dll` and `Editor.dll` carry **linker version 14.32** (MSVC 19.32 / VS2022) and
  `TimeDateStamp` **2022-10-29**. These are an OldUnreal-style rebuild, not 1999 retail binaries.
- Whole-`.text` census: `Engine.dll` 15 stray x87 arith (linear-sweep noise) vs 1494 SSE scalar +
  38,097 SSE packed; `Editor.dll` 6 vs 382 + 165. **Zero `fldcw`/`fnstcw` in either** — the build
  never touches the x87 precision-control word. **Zero FMA.**
- `FPlane::PlaneDot` (`core.dll 0x24e60`), the classify atom, is fully SSE: `movups`/`mulps` →
  `shufps 0xb1` → `addps` → `movhlps` → `addss`. The lone `fld dword` exists only to satisfy the
  32-bit float-return ABI on an already-rounded binary32. The ±0.25 comparison is a 32-bit `comiss`
  against `[0x10206780]`, not an 80-bit `fcomp`.
- One residual x87 site, `FVector::Normalize` (`core.dll 0x24940`, an `fdivrp` reciprocal) — **not**
  on the surf-normal path, which uses `SafeNormalSlow`/`CalcNormal`.

**Consequences.**

1. Bit-exact parity is reachable in Rust `f32`, and an extended-precision emulation layer would be
   actively **wrong** here — it would diverge from true-32-bit rounding rather than converge to it.
2. The remaining work is **op-order fidelity**, which is deterministic and testable. `PlaneDot`'s
   horizontal reduction is a specific pairwise tree, not a left-to-right sum; that shape has to be
   reproduced (or shown to agree bit-for-bit in range).
3. Rust guarantees IEEE-754 correctly-rounded `+ − × ÷` and `sqrt` with roundTiesToEven on `f32`
   ([`f32` primitive docs](https://doc.rust-lang.org/std/primitive.f32.html)), and SSE2 is the
   x86-64 baseline so there are no excess-precision intermediates. **Transcendentals are not
   guaranteed** by IEEE-754 and differ between libms — which is why the one transcendental the
   geometry path touches is already handled as a *table*: the fixed `rotation.py` builds the GMath
   sine table with float32 π and reproduces the live-captured editor table 16384/16384.
4. **But one caveat the record should carry**: the shipped retail `.dx` maps were built by the
   *original* 1998–2000 x87 editor. `old/NATIVE-MATERIALIZE.md` already rules those out as a parity
   reference for independent reasons (their trees are accreted GUI rebuilds, unreproducible from the
   trunk by any single command). If a future task ever needed to reproduce a *shipped* map's BSP
   rather than a self-built golden, the x87 question would return in full force.

Other recompilation projects confirm the general shape of the problem rather than offering a
technique this project needs: `sm64` reproduces its ROM byte-exactly by matching the **original
compiler and flags**, not by emulating FP at runtime
([n64decomp/sm64](https://github.com/n64decomp/sm64)); `OpenRCT2` reimplements an x86-assembly game
in C
([OpenRCT2](https://github.com/OpenRCT2/OpenRCT2)). Both are *source-matching* strategies. uedcli
cannot match source it does not have, so it matches **op order read from the disassembly plus a
differential gate** — which is the right adaptation, and is what the campaign already does.

### 4. Open reimplementations — what is and is not reusable

The decisive axis is the **geometric model**, not the robustness technique. UE1 is a plane-based BSP
over a **polygon soup** of brush faces, with per-face surf metadata and no watertightness
requirement. Most modern robust kernels require a closed manifold mesh.

| Project | Model | Robustness approach | Licence | Useful here? |
|---|---|---|---|---|
| id `qbsp`/`vis`/`light` (Quake, Quake 2 `qbsp3`, Quake 3 `q3map`) | **brush CSG → BSP → portals → vis → radiosity** — the closest cousin | epsilon-based (`ON_EPSILON`, `PLANESIDE_EPSILON`), plane snapping, explicit microbrush/sliver handling | GPL-2.0 | **Algorithm reference only.** Same problem shape; incompatible licence; different epsilons |
| [`ericw-tools`](https://github.com/ericwa/ericw-tools) | as above, modernised; "most robust map compiler suite for bsp maps" | epsilon-based, hardened over decades | **GPL-2.0** (GPLv3+ when built with Embree) | Read for *failure-mode taxonomy*; do not copy |
| ZHLT / VHLT (Half-Life tools) | as above | epsilon-based | GPL-era / mixed community licensing — verify per fork | same |
| `q3map2` / NetRadiant | as above, + lightmaps | epsilon-based | GPL-2.0 | same |
| csg.js lineage (ThreeCSG, three-bvh-csg) | BSP over triangle soup | epsilon | MIT | **Model matches loosely**; far too coarse to be an oracle |
| [Manifold](https://github.com/elalish/manifold) (OpenSCAD backend; Rust bindings [`manifold-csg`](https://crates.io/crates/manifold-csg) MIT/Apache-2.0) | **manifold triangle meshes only** — guarantees manifold-in → manifold-out | exact-ish predicates + topological guarantees | Apache-2.0 (core) | Wrong model |
| CGAL Nef polyhedra / CGAL booleans | half-space cell complexes, handles non-manifold | **exact arithmetic** | **GPL** for the Nef/boolean packages | Wrong licence, and exactness is not the goal |
| libigl `mesh_boolean` | triangle meshes | exact predicates via CGAL | MPL-2.0 core, but the boolean lives under `igl::copyleft::cgal` → GPL in practice | Wrong model + licence |
| Carve, Cork | triangle meshes | epsilon / exact-ish | Carve GPL-2.0; Cork LGPL/GPL-ish — verify | Wrong model |
| Clipper2 | **2D only** | integer/exact | BSL-1.0 | Not applicable |
| `parry3d` | collision queries, not CSG | epsilon | Apache-2.0 | Only for collision ideas; `linecheck.rs` is already an editor port |
| `robust` / `robust-predicates` (Rust ports of Shewchuk) | predicates only | **adaptive exact** | MIT/Apache-2.0 | **Usable — as a diagnostic oracle, not in the build path.** See §5 |
| `fornjot`, `truck` | CAD B-rep kernels | mixed | MIT/Apache-2.0 | Wrong model |
| OldUnreal 227 patches | UE1 itself | n/a | patch binaries, not open source | **Do not use as code.** Useful only as a *record of builder bugs* (227j's texture-origin rebuilder fix, non-planar auto-tessellation) — and those changes are not in stock Deus Ex |
| `stephank/surreal` and similar mirrors of Epic's partial UT 432 release | UE1 headers (`UnMath.h`, `UnModel.h`) | n/a | **no licence shipped with the release**; the mirror only *assumes* Artistic License; archived 2025-11-12 | **Values and struct layout only, never code.** `UnBsp.cpp`/`UnEdBsp.cpp` were not in the public release — so there is no public source for the filter recursion or the split scoring, and this project's disassembly is the only record |

No open project reproduces UE1's BSP. The practical consequence: the only oracle is the editor
itself, which is why the campaign's whole method is live capture + differential gate rather than
cross-validation against a sibling implementation.

### 5. What the robustness literature buys — and what it costs

This is the part of the brief that most needs an explicit answer, because the standard advice points
the wrong way for this task.

| Technique | What it guarantees | Effect on *this* goal |
|---|---|---|
| **Exact adaptive predicates** (Shewchuk 1996: `orient2d`/`orient3d`/`insphere`, staged floating-point filters escalating to exact arithmetic only when the sign is ambiguous; `predicates.c` is **public domain**, Rust ports MIT/Apache) | correct sign of a determinant, always | **Harmful in the build path.** The whole point of parity is to reproduce UnrealEd's *wrong* sign when it is wrong. Every near-tie this campaign has chased — `FindNearestVertex` hit-vs-miss, `FilterWorldThroughBrush` consume-vs-graze, Island N=332 — is a case where the editor's f32 answer is the specification. **Useful as a diagnostic**: an exact predicate tells you a call *is* a near-tie, which is precisely the signal the ULP spikes spend days establishing by hand |
| **Simulation of Simplicity** (Edelsbrunner & Mücke, *ACM ToG* 9(1):66–104, 1990; infinitesimal symbolic perturbation so predicates never return zero) | degeneracies simply never occur | **Harmful.** UE1's behaviour on degeneracies — `SP_Coplanar` inside the ±0.25 band, `Finalize` rejecting a sub-triangle face — *is* the behaviour to reproduce. SoS would systematically eliminate the cases that matter |
| **Plane-based representation with integer/homogeneous coordinates** (Thibault & Naylor 1987; Naylor et al. 1990; Nehring-Wirxel, Trettner & Kobbelt, *Fast Exact Booleans for Iterated CSG using Octree-Embedded BSPs*, [arXiv:2103.02486](https://arxiv.org/abs/2103.02486)) | unconditional robustness: a vertex is *defined* as the intersection of its three original planes, so only exact **predicates** are needed, never exact point coordinates | **Conceptually the most relevant external thread, and it validates the engine's design.** UE1 already stores planes (`Model->Vectors` + `Points`) as the primary data and derives vertices from them; the paper's observation that "six planes should intersect in a single point, something extraordinarily unlikely in floating point" is exactly why `bspAddPoint`'s 0.002/0.015 welds and `bspOptGeom`'s `merge_near_points` exist. But the paper's *fix* (integer homogeneous coordinates) changes the arithmetic, so it is not adoptable for parity — only for a hypothetical independent engine |
| **Snap rounding** (Hobby; Goodrich et al.; Iterated/Intersection-sensitive variants — round endpoints and intersections to grid "hot pixels" with globally consistent topology, using integer arithmetic) | fixed-precision output with consistent topology | **Harmful as a build-path change**, and explicitly ruled out by prior review: "the honest fallback is NOT snap". Relevant in a *different* register: the mappers' grid-discipline rule is snap rounding applied at authoring time, and the `rotate-gmath-residue` item is really asking whether uedcli should snap its own emitted coordinates |
| **Interval arithmetic / filtered predicates** | certified sign or "unknown" | Diagnostic value only, same as exact predicates |
| **Compiler-level determinism hygiene** (no FMA contraction, no `-ffast-math`, no reassociation, fixed op order, explicit parenthesisation, f32 literals) | the same program gives the same bits | **This is the technique that actually applies, and the codebase already follows it.** `fpoly.rs` forbids `mul_add`; dots are hand-parenthesised; `f64` appears only where the editor itself widens; spike 41 flags keeping `fma` out of the crate's target features |

The honest framing: **the requirement is emulation, not correctness.** The robustness literature is
written for people who want the right answer; this project wants *the editor's* answer. The only
parts that transfer are (a) determinism hygiene, which is already in place, and (b) exact arithmetic
as a **measuring instrument** for near-ties.

## Options

For the parity-vs-robustness question specifically.

| Option | Pros | Cons |
|---|---|---|
| **A. Status quo — f32 op-order emulation + live-capture differential gate** (what the campaign does) | The only approach with a proven track record here: every resolved divergence resolved this way. x87 risk measured and retired. Honours the prime directive — no masks. Two levels byte-exact to N=623 | Expensive per divergence: several open items need live gdb captures of the real editor, and the container/disk environment is flaky. Diffuse residues (tens-of-ULPs `Points` drift, 65 Vandenberg planes) resist single-cause fixes |
| **B. Status quo + exact predicates as a *diagnostic* oracle** (add `robust`/`robust-predicates` behind an env-gated trace, never on the default path) | Turns "is this a near-tie?" from a multi-day manual numeric replay into an automated flag. Near-tie classification is exactly where 5+ of the campaign's fixes landed. MIT/Apache, no licence friction. Zero effect on output bits | New dependency and a second code path to keep honest. Does not itself close any divergence — it only localizes faster. Needs a convention for "near-tie" magnitude |
| **C. Adopt exact/plane-based arithmetic in the build path** | Would make native *correct* and independent of the editor; the plane-based-integer literature says it can be unconditionally robust | **Abandons the goal.** Native would stop matching UED22 and the gate would go permanently red. Also abandons the exclusion-set discipline that makes the gate mean something. Only coherent if the project ever decides parity is no longer the bar |
| **D. Snap coordinates to grid before/during CSG** | Removes whole classes of near-tie by construction; matches the mappers' own Tier-A rule | Prior review already rejected it as a parity fallback. Would change bits on content that currently passes, and the shipped retail content is not all on-grid. Defensible only as an *authoring-time* uedcli feature (which is the `rotate-gmath-residue` question), never inside the build |
| **E. Widen the gate for the classes that keep blocking** (e.g. tolerate an orphan-`Verts` count mismatch) | Unblocks OceanLab immediately; the orphan-`iVertex` exclusion already exists for the same-count case and is evidence-backed | A deferral, not a fix, and the prime directive calls that out explicitly. Erodes what the gate proves. Needs the owner's yes plus an opus inconsequence review — already filed as a question |
| **F. Automate the live-capture loop** (a reusable harness for "break here, dump this struct, diff against native's env-gated trace") | The campaign has now built this ad hoc ~8 times (`pass1_brush_trace`, `probe_editor_fnv`, `raster_order_probe`, `raster_callsite_probe`, `bspopt_pool_oracle`, …). The next three open items all need the same shape | Infrastructure work that closes no divergence directly. The flaky shared Docker/disk environment is a real constraint on any such harness |

## Proposal (owner's call — not decided)

**B + F, keeping A as the method; explicitly reject C and D for the build path.**

The parity-vs-robustness tension is, on the evidence, already resolved in favour of parity and that
resolution is correct: the substrate is SSE2 f32, parity is reachable, and every ULP divergence has
proven to be a reproducible algorithm difference. Nothing in the robustness literature should enter
the build path.

What would help is **tooling that shortens the diagnosis of a near-tie**: an exact-predicate
diagnostic (option B) to flag, automatically, which `bspAddPoint`/`FilterWorldThroughBrush`/
`FindBestSplit` calls in a build sit within a few ULP of a classification boundary — plus a reusable
live-capture harness (option F) to replace the per-spike bespoke gdb scripts. Three of the five
levels are blocked behind exactly that capture loop.

On option E: the OceanLab orphan-`Verts` count question is already correctly filed as an owner
decision and should stay one.

## Open questions / what to verify next

1. **Is there a third `FindBestSplit` stride?** `bspcsg.rs::Opt` models `Lame` and `Good` only, and
   `build.rs` records the `MAP REBUILD` params as "Balance=50, PortalBias=70, OPTIMAL". Epic's own
   docs confirm `EBspOptimization` has **three** values (`BSP_Lame`/`BSP_Good`/`BSP_Optimal`), and the
   KB says they differ exactly in `FindBestSplit`'s stride. So either the byte-verified `MAP REBUILD`
   path genuinely uses the `NumPolys/20` stride (and the native `Good` name is just internal), or a
   distinct `OPTIMAL` stride is unmodelled. Cheap to settle from the existing decode; worth settling
   because every strided winner choice changes the whole tree.
2. **`CleanupNodes`' three-component vs four-component dot** (item #16) is an unambiguous,
   cheap-to-state algorithm divergence with a known fix shape. Why is it still open — is it blocked,
   or merely unscheduled?
3. **The diffuse residues** (65 Vandenberg plane ULPs, 54–393 `Points`/`Vectors` tens-of-ULPs drift,
   73 UNATCO unscaled-brush plane ULPs) all point at the same unresolved thread: authored-vs-
   recomputed face normals on unscaled Add/Subtract brushes. Is that one mechanism or several?
4. **`FPlane::PlaneDot`'s reduction shape.** Spike 41 flagged that the engine's horizontal sum is a
   `shufps 0xb1`/`addps`/`movhlps`/`addss` tree, not a left-to-right sum, and that native should
   either match the shape or *prove* the naive order agrees bit-for-bit in range. `fpoly.rs` says
   dots reduce left-to-right. Which of those two happened — a proof, or an assumption?
5. **Does the `rotate-gmath-residue` band question have an answer yet?** The item's own point stands:
   judged against the ~1e-4 vertex-merge band the threshold falls to ~572–1144 uu and would fire on
   ordinary content; judged against `CLEAN_EPS` it barely fires. The proposed exact-`Decimal` oracle
   for cardinal deltas is free and removes the need to pick a constant.
6. **The non-cardinal multi-axis `FCoords` compose** (item #11) is real, measured, and unshipped,
   with no live case blocked on it. If full byte parity is the standing goal, it is a known content
   gap — but there is no validation case for a fix. Build a synthetic one, or leave it?
7. **Unverified by me:** ZHLT/VHLT and Cork licensing (fork-dependent); whether any UE1-specific
   open reimplementation exists beyond the OldUnreal patch line. I found none.

## Sources

Internal (this repo):

- `old/NATIVE-MATERIALIZE.md` — the campaign's goal, reference recipe, parity bar, exclusion set, prime directive, ladder method.
- `old/dev/docs/unrealed/leveldesign/kb/csg-bsp.md` — the CSG/BSP mental model, solidity table, the `.rdata` tolerance-band table, problem catalog, myth corrections.
- `old/dev/docs/spikes/2026-07-15-native-materialize/41-fp-model-x87-vs-sse.md` — the x87-vs-SSE verdict: linker 14.32 / 2022-10-29, zero `fldcw`, zero FMA, fully-SSE `PlaneDot`.
- `old/dev/docs/spikes/2026-07-15-native-materialize/81-phase0-feasibility.md` — the per-site FP feasibility gate.
- `old/dev/docs/native-materialize-findings.md` (6544 lines) — the per-round divergence record; §"UNATCO live per-brush Pass-1 tree-shape trace" and §"NYC 747 rotated-brush transform cross-validation" are the two key ULP root-causes.
- `old/dev/docs/board/to-spike/{oceanlab-n-203-world-model2-split-vertex-ulp,wanchai-n-201-world-model2-body-diverges,rotate-gmath-residue}/overview.md`.
- `old/dev/docs/board/to-build/native-materialize/*/overview.md` — 47 items; `fpoly-rotation-matrix-ulp-gap-confirmed-real`, `vandenberg-count-parity-was-error-cancellation`, `bsp-cleanup-ports-fplane-operator-as-a-3`, `splitwithplane-degenerate-fragment-fallback` cited above.
- `old/dev/docs/board/to-spec/d2-fully-offline-bsp-csg-collision-engine/` — D2: the detector layer that would sit on top of the native build. Its `overview.md` is **stale** (claims a Python prototype in `_scratch/bspspike/`); the scoping spec records that the engine now exists in Rust, collision is ported (`linecheck.rs`), the `UModel` is readable/writable, and parity is measured by `test_csg_native_differential.py`. D2's remaining work is only the should-vs-did diff, and its stated risks are that "should this face survive?" has no editor oracle by construction, so confidence must come from constructed known-answer cases, and that it inherits every native-parity gap as a false-positive source.
- `old/dev/docs/spikes/2026-09-03-incremental-actor-parity/harness/parity_ladder_data.json` — live ladder state.
- `old/dev/docs/spikes/2026-08-29-unatco-repart-live-diff/` — the live-capture harness and logs (`fpolys-stage-order-*.log`, `pass1-brush-trace-unatco.log`, `fbs-world-poly-order-*.log`); `2026-09-01-dx-pbase-points-trace/harness/`.
- `old/uedcli-native/src/{bspcsg,fpoly,build,csg,passes,bspoptgeom,zones,visible_surfs,f32}.rs` — the code, read for the pipeline and the constants above.

External:

- <https://www.cs.cmu.edu/~quake/robust.html> — Shewchuk's adaptive-precision predicates; `predicates.c` public domain; the extended-precision-register caveat.
- <https://arxiv.org/abs/2103.02486> — Nehring-Wirxel, Trettner, Kobbelt (2021), plane-based representation + homogeneous integer coordinates; exact predicates without exact point coordinates.
- <https://www.cs.columbia.edu/cg/mesh-arrangements/mesh-arrangements-for-solid-geometry-siggraph-2016-compressed-zhou-et-al.pdf> — mesh arrangements for solid geometry (the manifold-mesh school, for contrast).
- Edelsbrunner & Mücke, "Simulation of Simplicity", *ACM ToG* 9(1):66–104, 1990 — <http://www.geom.uiuc.edu/~mucke/GeomDir/sos90.html>.
- <https://webdoc.sub.gwdg.de/ebook/serien/ah/UU-CS/2004-055.pdf> — de Berg et al., intersection-sensitive snap rounding (and the Hobby/Goodrich lineage).
- <https://randomascii.wordpress.com/2012/03/21/intermediate-floating-point-precision/> — Dawson on x87 80-bit intermediates, `_controlfp` precision control, double rounding, D3D9's FPU hijack.
- <https://learn.microsoft.com/en-us/cpp/build/reference/arch-x86?view=msvc-170> — MSVC 32-bit default changed to `/arch:SSE2` in VS2012.
- <https://doc.rust-lang.org/std/primitive.f32.html> — Rust `f32`: primitive ops rounded per IEEE-754 roundTiesToEven. Transcendentals are not standardised by IEEE-754 and differ between libms (libm/OpenLibm discussions).
- <https://github.com/ericwa/ericw-tools> — ericw-tools; **GPL-2.0** (GPLv3+ with Embree); qbsp/vis/light; "most robust map compiler suite for bsp maps".
- <https://www.oldunreal.com/wiki/index.php?title=BSP_building> — UnrealEd BSP build: Rebuild Geometry semantics, Balance 15/100 and Portal 70% GUI defaults, Lame/Good/Optimal, Build Visibility Zones, semisolid-vs-solid failure modes.
- <https://unrealarchive.org/wikis/unreal-wiki/Legacy:BSP_Hole_Background.html> — community BSP-hole explanation; node:poly 2–3:1; additive brushes last. **Contains no FP or named-function detail** — the mechanism in §2 comes from this project's disassembly, not from here.
- <https://beyondunrealwiki.github.io/pages/bsp.html> — BeyondUnreal wiki mirror (BSP, BSP Tree, BSP Hole).
- <https://crates.io/crates/manifold-csg> (MIT/Apache-2.0 bindings) and <https://github.com/elalish/manifold> — manifold-mesh-only robust CSG.
- <https://doc.cgal.org/latest/Nef_3/group__PkgNef3Ref.html> — CGAL Nef polyhedra; **GPL**; half-space cell complexes, non-manifold capable.
- <https://github.com/n64decomp/sm64>, <https://github.com/OpenRCT2/OpenRCT2> — source-matching recompilation projects, for contrast with uedcli's disassembly+differential method.
- <https://dev.epicgames.com/documentation/en-us/unreal-engine/API/Developer/BSPUtils/FBSPOps> and `.../FBSPOps/bspBuild` — primary: `bspBuild` signature, `EBspOptimization`, `Balance` semantics, `bspRefresh`, `bspAddPoint`/`bspAddVector` ("merging near-duplicates"), `bspValidateBrush`, `SplitPolyList`.
- <https://dev.epicgames.com/documentation/unreal-engine/API/Runtime/Engine/Engine/FPoly/SplitWithPlane> — primary: `SplitWithPlane` signature incl. `VeryPrecise`, "Meant to be numerically stable"; also `SplitWithPlaneFast`, `SplitWithNode`, `ESplitType`.
- <https://docs.unrealengine.com/5.1/en-US/API/Editor/UnrealEd/Editor/UEditorEngine/bspMergeCoplanars/> — `bspMergeCoplanars` as a `UEditorEngine` virtual.
- <https://unrealarchive.org/wikis/unreal-wiki/Legacy:CSG.html>, `Legacy:Solidity`, `Legacy:Rebuild`, `Legacy:Build`, `Legacy:Zoning`, `Legacy:Zone_Portal`, `Legacy:Snap_To_Grid` — community: CSG model, brush order ("only the last operation to be performed on the overlapping areas actually has an effect"), solidity, rebuild stage ordering and cumulative erasure, Lame/Good/Optimal in UI terms, zone discovery, grid and rotation snaps (16384 = 90°).
- <https://beyondunrealwiki.github.io/pages/brush.html>, `brush-order`, `bsp-tree`, `node-count`, `bsp-hole` — community: `CsgOper` values, builder-brush-vs-`Model` relationship, node:poly ratios, the 65,536 ceiling, the semisolid→invisible-poly vs solid→HOM split.
- <https://github.com/stephank/surreal> (`Core/Inc/UnMath.h`, `Engine/Inc/UnModel.h`) — circulating UT 432 headers, **no licence shipped**: UE1 `THRESH_*` values, `UModel` array layout, node/point enum caps. Values cited; no code used. `UnBsp.cpp`/`UnEdBsp.cpp` not present in the public release.
- <https://arkserverapi.wiki/ase/_unreal_math_utility_8h_source.html> — UE4/UE5 `UnrealMathUtility.h` mirror, for the modern `THRESH_*` column (notably `THRESH_POINTS_ARE_SAME` 0.00002).
- <https://ut99.org/viewtopic.php?t=14671> — community-measured UE1 engine limits (63 zones, 65,535 nodes, 128,000 points, ±32,700 uu).
- <https://www.oldunreal.com/wiki/index.php?title=227_release_notes/v227j> and `/v227k` — the 227 BSP-builder changes; **not applicable to stock Deus Ex**.
- <https://www.gamedeveloper.com/design/classic-tools-retrospective-tim-sweeney-on-the-first-version-of-the-unreal-editor> — design intent: real-time CSG, subtractive worldbuilding.
- <https://www.oldunreal.com/phpBB3/viewtopic.php?t=10244> — `yrex`'s BSP Tool: what it fixes post-build, and what it cannot.
- <https://www.oldunreal.com/phpBB3/viewtopic.php?t=3026> — "supercuts", the `15.999976` off-grid signature, the BSP Cuts view mode.
- <https://www.moddb.com/games/deus-ex/downloads/unrealed-22-for-deusex> — "UnrealEd 2.2 for Deus Ex" as a community backport derived from the UT 469e RC8 editor. **Unverified** (search snippet only; ModDB 403s to fetchers) — but it independently predicts the 2022 toolchain the PE headers show.

Unverified / not established by me: ZHLT and VHLT per-fork licensing; Cork's exact licence; `csgrs`
crate details (search did not surface it — possibly renamed or unmaintained); whether any open
reimplementation of UE1's BSP exists beyond the OldUnreal patch line; Wolf's BSP FAQ (HTTPS fails);
the UDN `UnGlossary` legacy page (403); whether any public mirror actually contains `UnBsp.cpp`
(worth confirming as a *contamination* check, not as a source); the ModDB "UnrealEd 2.2 for Deus Ex"
provenance claim.
