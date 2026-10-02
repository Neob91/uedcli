# 82 §11 — GROUND-TRUTH on-disk byte diff (native materialize vs UnrealEd)

**Status:** measurement + triage, CLOSED for this session. **Date:** 2026-07-18.
**Method:** raw-byte diff of the level `UModel` serial body, native `NativeCastle.dx` (rebuilt
fresh via `harness/build_native_castle.py`) vs the golden `DX/Maps/Test_Castle.dx` UnrealEd built.
**Reproduce:** `harness/ground_truth_bytediff.py` (whole-body + per-section byte-equality map) and
`harness/ground_truth_triage.py` (per-section cause attribution). Both load the two `.dx` directly
and normalize NOTHING except where a triage question explicitly needs it (every such normalization
is labelled in the output).

### Why this doc exists — the correction

A long chain of prior harnesses (`node_diff.py`, `pool_diff.py`, `surf_diff.py`, `subset_diff.py`,
`soup_cmp.py`, …) compared **normalized / subset / fp-tolerant projections** of the Model —
plane-rounded *multiset* keys, order-independent set compares, float tolerances, `iSurf` excluded
from node keys because the pools are reordered. Those tools answer "is the geometry the same shape?"
and legitimately reported many slices "matching". They do **NOT** measure on-disk bytes, and several
were read as "byte-exact" when they were not. This doc replaces those over-claims with the raw truth:

> **Nothing is called byte-exact here unless the raw serialized bytes are literally identical.**

### Confidence legend
✅ live-verified against the two real `.dx` this session · 📖 binary-extracted (cited from §82/§50).

---

## 1. TL;DR — the honest headline

Of the editor's **249,287-byte** Model body, exactly **12 bytes (0.005 %)** sit in byte-identical
sections (`NumZones` = 4 B, trailing `RootOutside,Linked` = 8 B). **Every other section differs on
raw bytes.** Raw whole-body first-difference is at **byte 0**. So on-disk byte parity today is
**effectively 0 %** — the earlier "byte-exact" reports were about normalized oracles, not bytes. ✅

**But the geometry core is genuinely close**, which is why the oracles matched — the divergences are
overwhelmingly **serialization ORDER, object-ref renumbering, occlusion flags, and the lighting
bake**, not different shapes:

- Node splitting **planes are the identical set** — multiset 1156/1156, zero planes only-on-either-side. ✅
- The 26 **Vectors are the identical set**, reordered (8/26 positional). ✅
- **Textures and `PolyFlags` on the 485 Surfs match as multisets.** ✅
- **Build-time node flags match exactly** — masking the two occlusion bits `0x08|0x10` makes editor
  `{0:1145, 5:11}` == native `{0:1145, 5:11}`. ✅
- **Zone `conn`/`vis` values are identical**; only the *ordering* of the two `conn=0x6` zones swaps. ✅

So the model is "the same map, serialized in a different order, with the light bake and the
render/collision aux arrays still diverging." That is the real remaining work — not a wrong shape.

---

## 2. Per-section byte-equality map (✅ `ground_truth_bytediff.py`)

Editor body = 249,287 B. Native body = 209,365 B (Δ −39,922). First differing byte (whole body): **0**.

| Section | editor B | native B | byte-equal? | first-diff (in-section) | count ed / nat |
|---|--:|--:|:--:|---|---|
| prefix | 42 | 42 | ❌ | @0 (name-idx) & @25 (FBox.IsValid) | — |
| Vectors | 313 | 313 | ❌ | @73 | 26 / 26 |
| Points | 24 422 | 20 210 | ❌ | @0 | 2035 / 1684 |
| Nodes | 54 034 | 53 268 | ❌ | @26 (node[0].NodeFlags) | 1156 / 1156 |
| Surfs | 8 930 | 8 951 | ❌ | @2 | 485 / 485 |
| Verts | 53 866 | 36 295 | ❌ | @0 | 16163 / 10418 |
| NumSharedSides | 4 | 4 | ❌ | @0 (2739 vs 2728) | — |
| **NumZones** | **4** | **4** | ✅ | — | 4 / 4 |
| Zones | 70 | 70 | ❌ | @17 | 4 / 4 |
| field_0x54 (Polys) | 2 | 1 | ❌ | @0 | ref vs null |
| LightMap (a8) | 14 528 | 14 408 | ❌ | @0 | 484 / 480 |
| LightBits (b4) | 49 516 | 48 018 | ❌ | @0 | 49513 / 48015 |
| Bounds (c0) | 12 102 | 1 | ❌ | @0 | 484 / 0 |
| LeafHulls (cc) | 15 466 | 16 114 | ❌ | @0 | 3866 / 4028 |
| Leaves | 4 585 | 4 226 | ❌ | @13 | 384 / 384 |
| Lights (e4) | 11 395 | 7 432 | ❌ | @0 | 11392 / 3928 |
| **trailing** | **8** | **8** | ✅ | — | — |

The GUID and save-timestamp live in the package **header**, not the Model body, so the body diff
excludes them by construction — there was nothing to strip.

---

## 3. Triage — every divergence, with evidence

### 3.A "AND SIMILAR" — excludable (non-deterministic editor-session / view artifact)

| Divergence | Evidence it is session/view, not a build gap | Verdict |
|---|---|---|
| **prefix byte 0** — `None` name-index (`0x00` vs `0x01`) | It is the ci-encoded index of `"None"` in each file's **name table**; name-table order is the editor's process-global FName-pool order (a session counter — `wrapper_diff.py` RESIDUAL). The trunk carries no such counter. | ✅ excludable |
| **NodeFlags `0x08` (`NF_PolyOccluded`) + `0x10` (`NF_BoxOccluded`)** — editor sets on 612 / 12 nodes, native on 0 | **Masking BOTH bits makes the editor's build-time flags EQUAL native's exactly** (`{0:1145,5:11}` both, ✅). The 12 `0x10` nodes are `node_flags=0` in native. These are **occlusion bits the editor's live-viewport render pass writes before the save** — view/camera-dependent, therefore session-dependent (📖 §50 "render.dll view-dependent"; 📖 §82 §10.11 "render-only occlusion bits"). A rebuild from a different viewport camera produces a different set. | ✅ excludable |
| **Object-ref VALUES** inside Surfs (`Texture`,`iActor`), Zones (`iZoneActor`), Lights (`e4`) | These are compressed-int **indices into each file's export/import tables**, whose numbering is the same session counter (`wrapper_diff.py`: `Polys176`,`Camera6`,… are session-global UObject numbers the trunk can't reproduce). The *referents* match — textures match as a multiset (✅), zone `conn`/`vis` match (✅). Only the index integers differ. | ✅ excludable *as ref-renumber* — but entangled with real reorder (see 3.B) |

### 3.B REAL must-fix — deterministic build output that genuinely differs

Ordered by editor-side byte impact.

| # | Divergence | editor B (≈%) | Root cause | Fix locus |
|--:|---|--:|---|---|
| 1 | **Lighting bake** — LightMap 484/480, LightBits 49513/48015, Lights e4 11392/3928, Surf `iLightMap` (484/485 differ) | ~75 k (30 %) | Native under-bakes: fewer surfaces lit, far fewer per-surf light runs, smaller shadow-bit pool. The `LIGHT APPLY` bake (§20) is incomplete/divergent. FP-determinism risk: the bake sums in x87 vs SSE order (§41) — exact bit-match is a hard sub-goal. | native light bake (§20 path; `lighting`/`materialize`) |
| 2 | **Node serialization ORDER** | ~54 k (22 %) | Plane **set is identical** (1156/1156 multiset, ✅) but positional order breaks at **node 51** (only 172/1156 planes match positionally). iFront/iBack/iPlane/iVertPool/iSurf/iZone all shift downstream. This is UnrealEd's `bspBuild` split-select + child/coplanar **emit order**, actively being ported (§82 §10.7–10.12). | Rust CSG/BSP core (`uedcli-native` bsp build / `bspcsg.rs`, `zones.rs` Pass D) |
| 3 | **Verts pool** — 16163 vs 10418 | ~54 k (22 %) | Sum of node `NumVertices` is close (5496 ed / 5533 nat), so the gap is the **un-referenced pool tail** = `bspOptGeom` side/vertex welding (`NumSharedSides` 2739 vs 2728) + point-pool order (#4) + node order (#2). Partly a benign un-compacted tail (§50 §2), partly real weld divergence. | `bspOptGeom` port (§82 §10.13–10.16) |
| 4 | **Points pool** — 2035 vs 1684 | ~24 k (10 %) | Pools genuinely differ: 484 points only-editor, 133 only-native, 1551 shared (NOT subset/superset). Emit/dedup order + residual over/under-production (§82 §10.14–10.16 has this actively narrowing). Cascades into Surf `pBase` + Verts. | `bspcsg.rs` / `bspOptGeom` point weld (§82 §10.16) |
| 5 | **LeafHulls (cc)** — 3866 vs 4028 | ~15 k (6 %) | Genuinely different collision-hull decomposition (int-multiset: only 1186 shared of 3866/4028). Downstream of node order (#2) + the box-sweep hull generator. | collision-hull emit (§60 path) |
| 6 | **Bounds (c0)** — 484 vs **0** | ~12 k (5 %) | Native **deliberately omits** the render-bound `FBox` array to dodge the `OccludeBsp` NULL-`Bounds` crash (§50 §0/§4) and sets every `iRenderBound=-1`. Regenerable render-cull data; to byte-match, native must build the 484 bounds AND set node `iRenderBound`. | `finalize`/bounds build (§50 §5.C) |
| 7 | **Surfs** — texture/flags multiset MATCH | ~9 k (4 %) | **UPDATED — see §83.** Geometry has since caught up: `vNormal`/`vTextureU/V`/`iLightMap`/`iBrushPoly`/`iZone`/`poly_flags` are now **byte-exact** (100 %), `pBase` 87 %. The ~21 % Surfs residual is now **two object-table-INDEX fields** (`texture_ref` 0 %, `iActor` 0 %) **plus a ~114 B pBase tail** (87 %, owned by the point-pool port). It is an index-ORDER problem (the trunk carries the names; only the editor's export/import ordering is missing). Deterministic-from-trunk ceiling ~40 %; the editor's own brush ORDER reaches ~92 %; whether a clean editor re-import of the trunk exposes that order as deterministic is the gating oracle question (§83 §5). | (index-order — §83) |
| 8 | **Vectors ORDER** — same 26-set, 8/26 positional | 313 B | Deterministic normal-pool **emit order** differs. Small itself but cascades into every Surf's `vNormal`/`vTexture*`. | vector-pool emit order (`bspcsg.rs`) |
| 9 | **Zones ORDER** — the two `conn=0x6` zones swapped | 70 B | Native orders `[generic, ZoneInfo]`, editor `[ZoneInfo, generic]` at indices 1/2. Deterministic function of portal/zone **discovery order**. Small itself but drives the `iZone (0,1)↔(0,2)` renumber on ~1058 nodes + all Leaves. | zone-numbering (`zones.rs`) |
| 10 | **prefix FBox.IsValid** — byte 25: native `1`, editor `0` | 1 B | The level Model's `UPrimitive` bbox is all-zero on both sides; native hardcodes `IsValid=1` in `_enc_prefix`, editor writes `0`. Trivial: emit `0` (or compute the real bbox + its valid flag). | `umodel._enc_prefix` / `model_write.rs` |
| 11 | **NumSharedSides** — 2739 vs 2728 | 4 B | `bspOptGeom` allocates 11 fewer side ids; same root as #3. | `bspOptGeom` (§82 §10.13) |
| 12 | **field_0x54 (Polys)** — editor ref vs native null | 1 B | Editor keeps the level's source `UPolys` export and refs it; native writes null. Editor-only re-edit source (§50 §3 "editor-only source polys"; not needed to render/play). Byte-matching it needs a `UPolys` export + ref — low priority. | assembly (`ulevel`/pkg) |

### 3.C The ordering — leverage, not just byte count

Several tiny sections are **high-leverage** because their order cascades:

- **Zones order (#9, 70 B)** decides the `iZone` integer on ~1058 nodes + 384 leaves.
- **Vectors order (#8, 313 B)** decides `vNormal`/`vTextureU/V` on ~440 surfs.
- **Node order (#2)** decides `iVertPool`/`iSurf`/child links on ~1100 nodes AND the Points/Verts
  emit order (#3/#4).

So the priority is not strictly byte-count: fixing the **emit-order roots (#2, #8, #9) and the point
weld (#4)** collapses the derived sections (#3, #7, and most of #5) with them. The lighting bake (#1)
is the largest *independent* block and the one with a genuine FP-determinism hazard.

---

## 4. Re-scoped worklist (ordered by leverage-adjusted impact)

1. **Node/point/vert emit ORDER + weld** (#2 → #3 #4 #7, ~75 k B of derived+direct bytes). The active
   port (§82 §10.7–10.16) is exactly this; plane SET is already exact, positional order + point weld
   are the open remainder. **Highest leverage.**
2. **Lighting bake byte-parity** (#1, ~75 k B, independent). Land the full `LIGHT APPLY` bake (§20);
   accept FP-bit-match (§41) as a hard sub-goal that may itself need x87-order emulation.
3. **Zone numbering + Vectors order** (#8 #9, small direct bytes, large cascade). Match UnrealEd's
   zone-discovery and normal-pool emit order.
4. **LeafHulls / collision hulls** (#5, ~15 k B). Match the box-sweep hull decomposition.
5. **Bounds array** (#6, ~12 k B). Build the 484 render `FBox`es and set `iRenderBound` (reverses the
   §50 crash-avoidance omission — needs the bound test to be correct, not just non-null).
6. **Trivia** (#10 prefix IsValid = 1 B, #11 NumSharedSides, #12 Polys ref). One-liners /
   assembly follow-ons; do last.

**Excluded by "and similar"** (do NOT chase for byte parity): prefix name-index, NodeFlags
`0x08`/`0x10` occlusion bits, and the raw object-ref index VALUES (export/import renumbering) — all
session/view artifacts, same category as the GUID and timestamps the user already excluded.

**Honest current state:** raw on-disk body parity is **0.005 %** (12 / 249,287 B). The geometry
*identity* (plane set, vector set, texture/flag multisets, build-time flags, zone values) already
matches; the bytes diverge on serialization order, the light bake, and the render/collision aux
arrays. The single biggest lever is the node/point emit-order port (already in flight in §82 §10);
the single biggest independent block is the light bake.
