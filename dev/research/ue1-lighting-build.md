# UE1 lighting build — how `LIGHT APPLY` works, how far native got, what is left

**Date:** 2026-10-03 · **Status:** research only — no decisions taken, nothing implemented.
**Question:** How does UnrealEd's lighting build actually work, how far has the native
reimplementation got, and what is left?

## Summary

- **The UE1 lighting build is not a light-transport solver.** It stores, per lit BSP surface per
  reaching light, a **1-bit-per-lumel visibility mask**. No brightness, colour, falloff or bounce is
  baked. Everything radiometric is applied at render time from the live light actors. (Verified
  in-repo from disassembly; independently corroborated by a third-party reimplementation, below.)
- That collapses "port UE1 lighting" into "port a per-lumel BSP ray test plus a grid allocator" —
  which native has **done**, and to a high bar: UNATCO 99.998% of 3.76M lumel bits, NYC Bar 100.00%.
- The remaining lighting gaps are mostly **not in the bake**. Record-level byte parity sits at
  66–93% per level and the largest bucket is upstream `Points`/`Vectors` float drift (54–58% of bad
  records), not bake logic.
- Three lighting-side gaps are genuinely open: the per-surface **light run** membership on NYC Bar
  (N=153), the per-leaf **permeating** lists at the margins (~95.4% leaf-exact), and a small
  `lumel_axes` determinant-grouping ULP residual at shadow edges.
- **Only four light inputs reach the bake**: `Location`, `LightRadius`, `bSpecialLit`, and
  `LightType != LT_None` + (`bStatic` or `bNoDelete`) as the participation gate. Everything else —
  `LightBrightness`, `LightHue`, `LightSaturation`, `LightEffect`, `LightCone`, `LightPeriod`,
  `LightPhase`, all `Volume*` — is runtime-only and correctly **not** read by `light.rs`.
- The shadow caster is a **BSP node walk** (`linecheck.rs`, a port of the editor's own walker), not a
  triangle ray-tracer. `collision.rs` shares its primitives but serves path-building, not lighting.
- A third-party, **zlib-licensed** UE1 reimplementation (SurrealEngine) publishes the *render-time*
  half uedcli guessed: a `(1 + 2v³ − 3v²)/v` distance falloff, `|dot(L,N)|` angle term, and a
  3-sector/85-wide hue wheel over a `6.5127·√brightness` value curve. uedcli's `level photo
  --native` currently uses linear falloff and a 6-sector HSV wheel. Two concrete, testable
  discrepancies.
- Bit-exact parity is **demonstrated achievable** for the bake's own arrays (one bit per lumel — no
  quantisation to disagree about); positional byte identity is gated on geometry and export
  numbering owned elsewhere.

## What we have today

| piece | file | LOC | role |
|---|---|---:|---|
| the bake | `old/uedcli-native/src/light.rs` | 1908 | `shadowIlluminateBsp` output: grid alloc + per-lumel shadow mask + the three Model arrays |
| per-leaf lists | `old/uedcli-native/src/permeating_lights.rs` | 811 | `Model.Lights` region 1 — portal-beam flood per light |
| shadow ray | `old/uedcli-native/src/linecheck.rs` | 546 | `UModel::LineCheck` segment-vs-BSP walker |
| light visibility | `old/uedcli-native/src/visible_surfs.rs` | 2042 | `URender::GetVisibleSurfs` six-face cube-map rasterizer |
| collision | `old/uedcli-native/src/collision.rs` | 966 | path-build scout; shares `linecheck.rs` primitives, **not** used by the bake |
| light gather | `old/uedcli/native/materialize.py` | — | `gather_lights`, `gather_light_colors` |
| GUI atlas | `old/uedcli/serve/lightmap.py` | — | packs the baked lumel grids into one RGB atlas for the browser |

`UEDCLI_NATIVE_MATERIALIZE=1 level materialize` bakes lighting with no editor in the path. A full lit
build of the 1437-actor UNATCO trunk takes 12 s; the 2288-actor Wanchai Market trunk 37 s.

## Findings

### 1. What the editor actually does (verified in-repo, from `Editor.dll` disassembly)

`LIGHT APPLY` → `UEditorEngine::shadowIlluminateBsp` (RVA `0xa5e10`), four progress phases:

| phase | fn | what |
|---|---|---|
| "Rebuilding lighting" | — | clear `Model->LightMap` / `Model->LightBits`, set every `FBspSurf.iLightMap = -1` |
| "Computing visibility" | `0xa4ba0` | per light, open a 1024×1024 offscreen viewport at the light and call `URender::GetVisibleSurfs`; build a transient per-surf light list |
| "Allocating meshes" | `0xa5bf0` | per lightmappable surf, compute the lumel grid (`USize`/`VSize`/`UScale`/`VScale`/`Pan`) and store an `FLightMapIndex` |
| "Raytracing" | `0xa5010` | `illuminateSurf`: per lumel per listed light, radius cut-off + `UModel::LineCheck`, pack the bit |

Pinned mechanics, all reproduced in `light.rs`:

- **Lumel resolution from PolyFlags**: 32 uu default, 16 with `PF_HighShadowDetail`, 64 with
  `PF_LowShadowDetail`, 128 with both (`lumel_scale`).
- **Grid dimension** = `ceil((extent − 0.25)/scale)`, min 2; at >256 the editor **doubles the lumel
  scale and recomputes** rather than clamping (`axis_grid`). Fitted 6868/6868 axes on UNATCO.
- **World radius** = `(LightRadius + 1) × 25` uu (`AActor::WorldLightRadius`). Default
  `LightRadius=64` ⇒ ≈1625 uu.
- **Self-shadow bias** = `Normal × 4`, applied once to the grid origin, not per lumel.
- **One ray per lumel, at the grid corner** — no centre offset, no supersampling.
- **Record emission order is a BSP tree walk**, not surf order (`lightmap_emit_order`): visit surf,
  recurse back child, front child, then the `iPlane` coplanar chain, with a load-bearing
  `NumVertices != 0` gate. Exact on 161/161 shipped Deus Ex world Models.
- **`bSpecialLit` partitions**: a `bSpecialLit` light lights only `PF_SpecialLit` surfaces, and a
  normal light only surfaces without the flag. It is not additive.
- **`PF_BrightCorners`** does two unrelated things: insets the sample grid by 0.25 with a shrunk step
  (`bright_corners_step`), and raises the ray's `ExtraNodeFlags` from `0x04` to `0x14`, where `0x10`
  makes a ray that *starts inside solid* report clear. That flag alone was 84% of one residual.
- **Backface rule**: keep whenever `PlaneDot >= -1.0`; never cull a `PF_TwoSided` or `PF_Portal`
  surface (`light_in_front`).

### 2. Light properties × build-time / runtime / honoured by native

Honoured = read by `light.rs`/`gather_lights` for `level materialize`. "photo only" = read by
`gather_light_colors` for the `level photo --native` preview, which is explicitly not parity-bound.

| property | build-time input? | runtime? | honoured by native today | confidence |
|---|---|---|---|---|
| `Location` | yes | yes | yes | verified in-repo |
| `LightRadius` | yes (radius cut-off, `×25`) | yes (falloff extent) | yes | verified in-repo |
| `bSpecialLit` | yes (partitions surfaces) | yes | yes | verified in-repo |
| `LightType` | gate only (`!= LT_None`) | yes (animation) | gate only | verified in-repo |
| `bStatic` / `bNoDelete` | yes (participation) | — | yes | verified in-repo |
| `LightBrightness` | **no** | yes | photo only | verified in-repo |
| `LightHue` | **no** | yes | photo only | verified in-repo |
| `LightSaturation` | **no** | yes | photo only | verified in-repo |
| `LightEffect` | **no** | yes (spatial shape) | **no** | verified in-repo (grep: unread) |
| `LightCone` | **no** | yes (spot cone) | **no** | verified in-repo |
| `LightPeriod` / `LightPhase` | **no** | yes (animation speed/offset) | **no** | verified in-repo |
| `bDynamicLight` | **no** (dropped at `MAP IMPORT`) | yes | dropped on brushes, else ignored | verified in-repo |
| `VolumeBrightness` / `VolumeFog` / `VolumeRadius` | **no** | yes (volumetric fog) | **no** | verified in-repo |
| `bCorona` / `Skin` / `DrawScale` | **no** | yes (corona sprite) | **no** | verified in-repo |
| `Rotation` | **no** | yes (`LE_Spotlight`, `LE_Searchlight`) | **no** | third-party reimpl. |
| surface `PF_*ShadowDetail` | **yes** (lumel scale) | — | yes | verified in-repo |
| surface `PF_BrightCorners` | **yes** (inset + ray flags) | — | yes | verified in-repo |
| `ZoneInfo AmbientBrightness/Hue/Saturation` | **no** | yes (per-zone ambient floor) | **no** | third-party reimpl. |

The build/runtime split is the load-bearing claim and it is doubly sourced: the disassembly of
`illuminateSurf` reads none of the radiometric fields, and the community wiki says the same from the
other side — "lightmaps are pregenerated and can't be animated through the use of lighteffects"
([Legacy:Light Effects](https://unrealarchive.org/wikis/unreal-wiki/Legacy:Light_Effects.html)).

### 3. What the native bake does, stage by stage

`light::bake(model, lights)`:

1. Reset the four outputs; `validate_indices` / `validate_finite` (the FFI contract forbids a panic
   crossing into Python).
2. `permeating_lights::write_permeating_region` — `Model.Lights` region 1, computed here because this
   is the only native stage that has both the leaf graph and the light actors.
3. Per light, in parallel, `visible_surfs::get_visible_surfs` — the editor's own six-face cube-map
   occlusion rasterization, giving each light's candidate surf set.
4. Replay each light's `NF_BoxOccluded` box-test writes **in light order**, because the bit persists
   in `Model.Nodes` and the shadow ray reads it at a crossing.
5. Per surface, in parallel, `bake_surf`: grid descriptor, the four-part gather predicate
   (`bSpecialLit` partition, `light_in_front`, `GetVisibleSurfs` membership, and
   `WorldLightRadius >= |PlaneDot|`), then per lumel a squared-distance radius test and
   `linecheck::line_clear`, packed LSB-first with `row_padding` for the bits above `USize`.
6. Serial concat in **two different orders**: data arrays in surf-index order (`finalize_offsets`),
   the record array in BSP walk order (`push_record`). Deterministic regardless of thread scheduling.

Three record shapes are distinguished and all three match the editor: populated run, **empty run**
(gather listed the surf, every listed light lit no lumel — a lone `-1`, zero bytes), and **dark**
(`DataOffset=0`, `iLightActors=-1`).

**Explicitly stubbed / not ported, by the code's own comments:**

- The `OccludeBsp` frustum-cone subtree reject (step 6) — measured divergence, not a free
  optimization: native runs 276 box tests to the editor's 225 on UNATCO N=26 and marks one node the
  editor leaves clear.
- `FovAngle` for the cube-map faces is assumed **90°** from ini evidence, not pinned by disassembly.
  Flagged in `visible_surfs.rs` as an assumption.
- `lumel_axes` computes `det = tu·(tv×normal)`; `FCoords::Inverse` expands the same determinant with
  a different term grouping. Algebraically equal, not f32-identical; every accumulated lumel position
  inherits the ULP. Largest single remaining shadow-bit source (466 of ~4M bits on UNATCO, 487 at
  shadow edges vs 24 in solid blobs).
- `SP_Coplanar` caller behaviour in `split_with_plane_fast` is one unconfirmed branch.
- `light::radiance` duplicates `bake_surf`'s grid-origin derivation on purpose and has **no test
  enforcing the two stay in sync**.

### 4. `linecheck.rs` and `collision.rs` in the lighting pipeline

`linecheck.rs` **is** the shadow caster. It is a port of the editor's own bake-time walker
(`Editor.dll 0x17ce190`, the function `LIGHT APPLY` reaches through the `Model` vtable at `+0x58`),
not of the generic engine `LineCheck`. Load-bearing details:

- Solidity is `FBspNode::IsCsg`: `NumVertices > 0 && (NodeFlags & (ExtraNodeFlags|0x21)) == 0`.
  `NF_NotCsg` nodes — semisolid, portal, masked — never block.
- A ±0.001 `WHOLE_SEGMENT_EPS` band lets a node count as "whole segment" on one side rather than
  forcing a crossing split.
- The walker **threads** an accumulating open/solid `state` through the recursion
  (`combine_state`/`terminal`): a terminal is solid only when the walk has no positive evidence of
  open space in its ancestry. An earlier non-threaded crossing formula regressed both reference
  levels badly.
- It fails **open** past `MAX_DEPTH` — a missed shadow is cosmetic, a false shadow is not.

`collision.rs` plays **no role in lighting**. It imports `linecheck.rs`'s primitives (`child`,
`combine_state`, `crossing_mid`, `is_csg`, `plane_dot`, `terminal`, `WHOLE_SEGMENT_EPS`) and builds
the path-build scout's world on top (`CollisionModel`, `line_check`, `point_check`, `World`,
`Scout`). The sharing means a change to the walker's core rules moves lighting *and* pathing.

### 5. Recorded divergences (verified in-repo)

Per-level `LightMap` records byte-identical, after the 2026-09-01 `row_padding` fix:

| level | before | after |
|---|---:|---:|
| NYC Bar | 87.7% | **93.1%** |
| UNATCO | 83.6% | **90.9%** |
| Paris Club | 76.8% | 87.4% |
| Paris Chateau | 81.8% | 87.6% |
| Wanchai Market | 75.5% | 80.0% |
| NYC ShipFan | 69.7% | 75.0% |
| HK Helibase | 67.0% | 69.7% |
| NYC Underground | 55.8% | 66.6% |

Shadow bits: NYC Bar **100.00%** (421088/421088), UNATCO **99.998%** (80 bits of 3.76M).

Failure-mode buckets on bad records (Wanchai, current tree, 1233 bad): `pan`/`scale` 711 (57.7%),
`run` 261 (21.2%), `bits` 255 (20.7%), `grid` 6 (0.5%). The dominant bucket is upstream: a multiset
compare found 54/2762 NYC Bar points and 47/138 vectors whose *value* matches no golden entry even
where counts are exact; bad records are 14× enriched for touching a divergent point. No lighting-side
fix can move those.

Named open divergences:

| level / N | what diverges | state |
|---|---|---|
| NYC Bar N=153 | `Light5` lights 3 stair-tread surfs the editor leaves dark; the mirror mover face is unlit. `Lights` 484 vs 478, `LightBits` 6003 vs 5891 | 9 rounds; `GetVisibleSurfs`, box occlusion, zone crossing, clip formula all **cleared** by live capture. Narrowed to a per-light "any lumel visible" commit gate past the raytrace loop. Not fixed, not masked |
| UNATCO N=26 | the editor's shadow ray reads a stray `NF_BoxOccluded` bit written at a fixed `base + k*1024` byte stride, independent of geometry | no fix to port — the bit is a stray write, not real occlusion. Needs an owner ruling |
| Island N=123, Wanchai N=58, UNATCO N=226, OceanLab N=48 | per-leaf permeating runs over-include one light | all four **fixed**, root-caused to computation order / a portal graph recomputed after `merge_near_points` |
| permeating, overall | 727/762 UNATCO leaves exact (95.4%); residual is extra, never missing, lights | boundary-epsilon shaped, not an orientation bug |

### 6. How lighting is validated today, and the golden dataset

**There is a golden dataset of UnrealEd-produced lighting**, self-built, not shipped:
`build_ued_lit_golden.py` drives the real editor `MAP NEW` → `EDIT PASTE` → `MAP REBUILD` →
`LIGHT APPLY` → `MAP SAVE`, with an actor filter derived from `gather_lights` itself (hardcoding
`Light` silently drops `Engine.Spotlight` and reads as native inventing lights). The canonical
single-entry tool is `parity_report.py`, which caches the expensive golden by content hash and emits
a `FULL PARITY: YES/NO` verdict for geometry and lighting together.

Three hard methodology rules, all learned the expensive way:

1. The **production editor path is not a usable oracle** — `MAP LOAD` of an assembled package builds
   a different world BSP from the same brushes (3705/6254/776 vs 3616/6314/762), so record *k*
   describes a different surface on each side and no positional byte compare means anything.
2. The **shipped retail `.dx` is not a valid reference** — it is an accreted GUI rebuild,
   unreproducible from the trunk.
3. A golden must come from a **full rebuild**: `shadowIlluminateBsp` empties `LightMap` and
   `LightBits` but never `Model.Lights`, so a second `LIGHT APPLY` appends a third region and orphans
   the previous one.

Metrics in use: record byte-identity, per-(surf,light) plane byte-identity, lumel-bit agreement
percentage, run content+order, and `bit_asymmetry.py`'s shadow-edge-vs-solid-blob split (the shape
test that found the `NF_NotVisBlocking` bug after three fixes of flat aggregates).

Below the golden sits a unit layer: ~50 Rust tests in `light.rs` alone, pinning the grid rule, the
three record encodings, the skip mask, the `bSpecialLit` partition, row packing and padding carry,
the >256 scale doubling, BSP walk order, and the HSV/falloff probes. `linecheck.rs` and
`permeating_lights.rs` carry their own. The Python side has only `test_serve_lightmap.py`, which
tests the browser atlas packing, not bake fidelity. **No CI job runs the golden comparison** — it
needs a live editor container.

### 7. `bSpecialLit`, `Volumetric`, "permeating lights" as this tree defines them

- **`bSpecialLit`** — the partition rule in §1, decoded from `Editor 0x100a4ea0`. The community
  description agrees ("surfaces that can only be enlighted by lights that are set to special lit as
  well, or by ZoneLight" — [Lode](https://lodev.org/unrealed/lighting/lighting.html)).
- **Volumetric / `Volume*`** — per-light volumetric fog, gated on `ZoneInfo bFogZone=True`, built
  from `VolumeBrightness` / `VolumeFog` / `VolumeRadius`. Entirely render-time; the bake never reads
  it and uedcli never writes it. The third-party reimplementation has a separate `FogmapBuilder` for
  exactly this, confirming it is a distinct runtime map, not part of the lightmap.
- **"Permeating lights"** — `Model.Lights` **region 1**: per-BSP-leaf lists of which lights' light
  can reach that leaf, indexed by `FLeaf.iPermeating`. Produced by the *zoning* build
  (`csgRebuild` → `TestVisibility` → `Portalize`), not by the bake, via `ActorVisibility`
  (`Editor 0x100a6d00`) — a recursive **portal-beam flood** from the light's own leaf, not a radius
  test and not a `LineCheck`. Each leaf reached gets the light *prepended*, so a leaf's run ends up
  in descending actor index. The flood crosses every empty-leaf-to-empty-leaf BSP face, not only
  `PF_Portal` surfaces, and ignores zone connectivity entirely. Native computes it from
  `light::bake` purely because that is the only stage holding both the leaf graph and the lights.
  Its beam clip is `FPoly::SplitWithPlaneFast` with a `THRESH_SPLIT_POLY_WITH_PLANE = 0.25`
  **world-unit** epsilon on a normalized plane — getting the normalization wrong made the epsilon
  inert and cost a round.

### 8. External corroboration, and the render-time half uedcli guessed

SurrealEngine (`dpjudas/SurrealEngine`, **zlib licence** — MIT-compatible, so citable and
re-implementable without licence friction) is a from-scratch UE1 engine reimplementation. Its
`Light/` directory confirms the division of labour from the other side:

- `Shadowmap::Load` **reads** `model->LightBits` at `DataOffset + lightindex * pitch * height` with
  `pitch = (width + 7) / 8` and `bits[x >> 3] & (1 << (x & 7))` — byte-for-byte the same decode
  `light.rs` writes. Independent confirmation of the encoding, from a separate RE effort.
- It never **computes** shadow bits. `AddDynamicLights` clears the shadow buffer to 1.0, i.e. dynamic
  lights cast no shadows at all. There is no lightmap *builder* in the sense uedcli needs — only a
  consumer.
- It applies a 3×3 Gaussian blur to the loaded bit-plane before use. That is a smoothing choice in
  that project, not necessarily what UE1 did (marked unverified).
- `LightEffect::Run` reads `WorldLightRadius` and dispatches on `LightEffect`. The core
  (`NoneEffect`) is `shadow × distanceAttenuation × angleAttenuation` with
  `distanceAttenuation = min((1 + 2v³ − 3v²)/v, 1)` where `v = dist/radius`, and
  `angleAttenuation = |dot(L, N)|` (**absolute** — a light behind the plane still lights it).
- `hsbtorgb` is **not** standard HSV: `saturation >= 250` short-circuits to white; the hue wheel is
  **3 sectors of 85**, not 6 of 42.5; saturation is scaled by `1/2.5` with a `+2` kink above 32; and
  value runs through `hsbtorgb_v_table[b] = 6.512735 · √b`, peaking at **104.0**, not 255.

Two concrete discrepancies against uedcli's `level photo --native` preview (which is explicitly not
parity-bound, so these are preview-fidelity items, not parity bugs):

| aspect | uedcli `light.rs` | SurrealEngine | note |
|---|---|---|---|
| distance falloff | `1 − d/R`, linear | `min((1 + 2v³ − 3v²)/v, 1)` | the repo's own probe failed to pin the curve; this is a candidate shape with a near-light `1/v` singularity |
| brightness curve | linear × 2.0 overbright | `6.5127·√b` | the repo's probe measured 64→128 doubling the channel (ratio 1.99), which **contradicts** √b (would be 1.41). Unresolved |
| hue wheel | 6 sectors, `h/42.5` | 3 sectors, `h/85` | both put the primaries at 0/85/170; they differ mid-sector. The community hue tables (R0/Y40/G80/B160/P200) fit the 3-sector model |
| angle term | none | `abs(dot(L,N))` | uedcli's preview has no N·L term at all |
| zone ambient | none | `hsbtorgb(Ambient*)` as the lightmap floor | uedcli's preview starts from black |

### 9. Quake-lineage comparison, and what UE1 did not have

`ericw-tools light` (GPL-2.0) and GoldSrc `hlrad` do the equivalent job with a generation more
machinery: `-extra`/`-extra4` 2×2/4×4 supersampling, `-soft` post-process smoothing of shadow edges,
`_bounce` radiosity passes with `_bouncecolorscale` texture-coloured bounce, `_phong`/`_phong_angle`
smooth-normal interpolation across adjacent faces, emissive surface lights with
`-surflight_subdivide`, directional sunlight with `-sunsamples` penumbra, and `_dirt` ambient
occlusion. **UE1 has none of that.** One ray per lumel at the grid corner, a hard radius cut-off, direct light
only, no bounce, no phong, no area shadows, no AO. The lumel scale is not a mapper-tunable number but
a three-way choice through `PF_HighShadowDetail`/`PF_LowShadowDetail`. Community sources agree UE1 is
"direct-only lighting with pre-calculated static lightmaps" with no bouncing
([Lode](https://lodev.org/unrealed/lighting/lighting.html)); that same tutorial's
"pre-calculated radiosity" wording is loose, and refuted by the bit-mask format.

The "sample off the face" problem that Quake compilers solve by nudging samples back onto the
polygon, UE1 solves differently and crudely: the lumel grid is the surface's texture-space **bounding
box**, so on any non-rectangular or corner-adjacent face a lot of lumels sit inside neighbouring
solid brushes — and `PF_BrightCorners` exists precisely to make those rays report *clear* instead of
black. That is a flag-driven hack where the Quake tools do geometry. Reproducing it was 84% of one of
native's residuals.

### 10. Is bit-exact parity a reasonable target?

For the bake's own output: **yes, and it is largely achieved.** NYC Bar is at 100.00% of shadow bits,
UNATCO at 99.998%. There is no quantisation question to agonise over — the format is one bit per
lumel per light, with no RGB and no multi-byte value, so there is no rounding to disagree about.
Even the bits *above* `USize`, which the game masks off on read, are reproduced from the editor's
own last-`LineCheck`-result padding rule.

Two things are **not** reachable from `light.rs` alone, by the tree's own assessment: **object-ref
renumbering** (`Model.Lights` entries are compact-index export refs numbered by a session-global
counter, so an identical light *set* still serializes differently — wrapper-level), and **geometry
float values** (`Pan`/`UScale`/`VScale` are pure functions of `Points`/`Vectors`; that 54–58% bucket
is upstream CSG accumulation, x87-vs-SSE class).

So the honest framing: the bake's *algorithm* parity is a solved problem at the 99.99% bit level, and
record-level byte parity is a geometry problem wearing a lighting costume. The 66–93% per-level
numbers are a geometry scoreboard.

For the `level photo --native` preview the bar is explicitly **not** byte parity (owner ruling
2026-09-11) — "visibly lit" is the stated standard, and the swap point for a future exact effort is
confined to `hsv_multiplier` and `falloff`.

Nobody found who has reproduced UE1's lighting *bake* offline. SurrealEngine reproduces the
*consumer*. uedcli's bake appears to be the only independent reimplementation of
`shadowIlluminateBsp` (unverified — absence of evidence from the searches done, not a proof).

### 11. Rust crates for the ray-cast workload

The bake's inner loop is already a BSP node walk, which is what UE1 itself used, and the walk's exact
rules — the ±0.001 epsilon, the threaded open/solid state, the `NF_*` flag masks, the asymmetric
crossing formula — **are the parity target**. A third-party acceleration structure cannot express
them: `parry3d` (Apache-2.0), `bvh` (MIT) and `embree4-sys` (non-standard licence, wraps a C++
library) all answer "does this segment hit this geometry", which is a *different question* from "what
does the editor's walker conclude about this segment". Swapping in any of them would forfeit the
99.998% and gain nothing structural.

`rayon` (MIT OR Apache-2.0) is already a dependency and already carries the parallelism, at two
levels: per-light `get_visible_surfs` and per-surface `bake_surf`, with deterministic serial concat
afterwards. The one determinism hazard is documented in `bake` as an `assert!`: the parallel gather is
only order-independent while no node arrives carrying `NF_BoxOccluded`.


## Options

| Option | Pros | Cons |
|---|---|---|
| A. Close NYC Bar N=153 (the per-light commit gate) | the last gap that is genuinely the bake's own; 9 rounds of evidence already narrow it to one code region | needs live gdb on the editor container; 9 rounds in and not closed |
| B. Rule on UNATCO N=26's stray `NF_BoxOccluded` bit | unblocks a ladder stop; the alternative is an indefinite stall | the bit is provably not derivable from geometry — any resolution is a deliberate exclusion, i.e. an owner call, not an engineering fix |
| C. Fix `lumel_axes` to `FCoords::Inverse`'s exact term grouping | removes the largest named shadow-bit residual; small, local, testable | ~466 bits of 4M; pure ULP work, no visible effect |
| D. Re-derive the render-time colour/falloff from `Render.dll` | would replace both guessed formulas with evidence; SurrealEngine gives a strong prior to test against | preview-only payoff; owner already ruled byte parity out of scope here |
| E. Adopt SurrealEngine's published formulas in the preview as-is | cheap; better-motivated than linear falloff; licence-compatible | still third-party RE, and it **conflicts** with the repo's own brightness probe — would be trading one unverified model for another |

## Proposal (owner's call — not decided)

Treat the bake as **done** and stop measuring lighting as if it were the open problem: at 99.998%
and 100.00% shadow bits, the per-level 66–93% record figures are reporting geometry drift. Of the
lighting-side work, C is the only cheap, self-contained item and B is a decision rather than a task —
those two seem worth taking before A, which has already absorbed nine rounds. For the preview, D over
E: SurrealEngine's falloff is a much better prior than linear, but its √brightness curve directly
contradicts this repo's own live probe, and adopting a formula we can already see conflicts with our
own measurement would make the preview harder to reason about, not easier. One targeted re-probe
(brightness sweep at several radii, wide sample box) would settle it for an hour's work.

## Open questions / what to verify next

- **Brightness curve conflict.** The repo's probe says linear (64→128 gives ratio 1.99);
  SurrealEngine says `6.5127·√b`. Both cannot be right for the same renderer. A clean sweep at
  8/16/32/64/128/255 with the wide sample box the falloff round proved necessary would decide it.
- **Hue wheel sector count.** 3 sectors of 85 vs 6 of 42.5 predict different mid-sector channel
  ratios (G/R 0.603 vs 0.753 at `LightHue=32`); the repo measured 0.720. Neither fits well. Worth one
  probe at several hues, since the community tables favour the 3-sector shape.
- **The `|dot(L,N)|` angle term.** If UE1 really takes the absolute value, a light behind a surface's
  plane still lights it at render time — which would interact oddly with the bake's own
  `PlaneDot >= -1.0` backface keep. Unverified, and checkable from `Render.dll`.
- **`FovAngle = 90`** for the cube-map gather is still an ini-derived assumption, not disassembled.
- **Is the 3×3 Gaussian blur on the shadow plane a UE1 behaviour or a SurrealEngine choice?** It
  changes what "visually identical" means for any preview that mimics the game.
- **`radiance` / `bake_surf` grid-origin duplication** has no test keeping the two in sync; a future
  edit to the parity-pinned path can silently desync the preview.
- Whether any OldUnreal / UE1 community effort has reproduced `shadowIlluminateBsp` offline — not
  found, but the search budget ran out before this was exhausted.

## Sources

- `old/uedcli-native/src/light.rs`, `permeating_lights.rs`, `linecheck.rs`, `visible_surfs.rs`,
  `collision.rs` — the implementation and its inline disassembly citations.
- `old/dev/docs/spikes/2026-07-15-native-materialize/sections/20-lighting-bake.md` — the full RE of
  `LIGHT APPLY`: pipeline, every stored byte, grid formula, radius model, parity-limit assessment.
- `old/dev/docs/spikes/2026-08-27-native-light-apply-parity/spike.md` — the lit oracle, the seven
  fixes and what each was worth, the three remaining gaps.
- `old/dev/docs/spikes/2026-09-11-light-color-falloff-re/README.md` — the live colour/falloff probe;
  `old/dev/docs/spikes/2026-09-05-lightapply-node-flags/spike.md` — the stray `NF_BoxOccluded` bit.
- `old/dev/docs/unrealed/leveldesign/kb/lighting.md` — light properties, byte semantics, defaults,
  the `LightType`/`LightEffect` rosters read from the shipped `Engine.u`.
- `old/dev/docs/native-materialize-findings.md` — the divergence-bucket breakdown and the
  `row_padding` root cause.
- `old/dev/docs/board/inbox/nyc-bar-n-153-world-model2-lightmap-runs-ued22/overview.md` — nine rounds
  on the last bake-owned gap.
- https://github.com/dpjudas/SurrealEngine — zlib-licensed UE1 reimplementation (licence read via
  the GitHub API): `Light/Shadowmap.cpp` (independent confirmation of the `LightBits` decode),
  `Light/LightEffect.cpp` (falloff + per-effect math), `Light/LightmapBuilder.cpp` (`LightType`
  animation), `Math/hsb.h`+`hsb.cpp` (the HSB→RGB curve).
- https://unrealarchive.org/wikis/unreal-wiki/Legacy:Light_Effects.html — the `LightEffect` roster
  and the "lightmaps are pregenerated and can't be animated" statement. Community-documented;
  per-effect descriptions are mapper folklore, several marked "no apparent effects".
- https://lodev.org/unrealed/lighting/lighting.html — UnrealEd 1 lighting build, static vs dynamic
  lights, `bSpecialLit`, volumetric fog, shadow-detail surface settings, direct-only lighting.
  Community-documented.
- https://beyondunrealwiki.github.io/pages/actor-lighting.html — property meanings; its "factor of
  about 27 between `LightRadius` and UU" is a community estimate, superseded in-repo by the
  disassembled `(LightRadius + 1) × 25`.
- https://ericwa.github.io/ericw-tools/doc/light.html and `docs/light.rst` (GPL-2.0, read via the
  GitHub API) — supersampling, bounce, phong, soft shadows, surface lights, luxel scale.
- crates.io API — `parry3d` 0.31.1 Apache-2.0, `bvh` 0.12.0 MIT, `embree4-sys` 0.0.12 non-standard,
  `rayon` 1.12.0 MIT OR Apache-2.0.
- Not obtained: VRAD (403) and TWHL's hlrad page (404), so the GoldSrc/Source side of the comparison
  rests on the `ericw-tools` documentation alone. Treat `hlrad` specifics above as unverified.
