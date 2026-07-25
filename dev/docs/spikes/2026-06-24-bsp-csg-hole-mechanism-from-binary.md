# How UnrealEd builds the BSP, and why holes appear — from the binaries

**Date:** 2026-06-24
**Method:** static disassembly of the shipped UED22 DLLs (no editor run). Built a
`capstone`+`pefile` harness (scratch: `_scratch/bspspike/`), resolved the C++-mangled
exports, disassembled the CSG/BSP/`FPoly` functions, and read the embedded float
constants and diagnostic strings directly out of `.rdata`.
**Confidence:** these are **decompiled facts** — read out of the actual compiled code, a
tier *stronger* than the 📖 "string-extracted" marker used elsewhere (we read the
instructions and constants, not just string literals). Where this spike connects the code
mechanism to a *mapper-observable* symptom that wasn't separately reproduced live, that
link is called out as inference.

> **Why this spike exists.** `unrealed/leveldesign/kb/csg-bsp.md` and `unrealed/quirks.md`
> already describe BSP holes *behaviorally* — the symptoms (HOM smearing) and the community
> repairs (grid discipline, reorder brushes, flip a semisolid, Transform Permanently, rebuild
> the face by hand). What was missing is *the actual code-level reason a face disappears*. This
> spike answers that from the binary, so the repair advice has a mechanism under it instead of
> folklore.

---

## 0. Vocabulary (read this first)

- **CSG** — Constructive Solid Geometry. The world starts as infinite solid; **subtractive**
  brushes carve empty space, **additive** brushes put solid back. See `csg-and-bsp.md`.
- **BSP** — Binary Space Partition. A tree of planes that indexes the world's polygons for
  rendering, collision, and zone/visibility. "The BSP" = that tree plus the polygons hung off
  its nodes.
- **`FPoly`** — the engine's in-memory convex polygon: an array of up to 16 vertices
  (`MAX_VERTICES`), a `Normal`, texture vectors, flags. Brushes are lists of `FPoly`s; the BSP
  build chops `FPoly`s against planes.
- **A "hole"** — a missing or invalid world face. In game it renders as a **HOM** (hall of
  mirrors: the framebuffer isn't cleared where a face should be, so you see smeared garbage).
  Mechanically, a hole is almost always **an `FPoly` that the build code *discarded* or
  *collapsed*** because it failed a numeric validity test.
- **`Finalize` / `Fix` / `RemoveColinears` / `CalcNormal`** — the four `FPoly` cleanup methods
  that decide whether a polygon survives. These are where faces die.
- **`SplitWithPlane`** — splits one `FPoly` by a plane into front/back pieces, or classifies it
  as entirely front / back / **coplanar**. The BSP build runs this on every poly against every
  partitioner plane.

## 1. Where the code lives (binary map)

The geometry code is split across three DLLs. ImageBase for all of them is `0x10000000`;
addresses below are **file RVAs** (subtract nothing — they're what `pefile` reports). The
exports are MSVC-mangled C++ names, so they map 1:1 to the original engine source.

| Function | Module | RVA | Role |
|---|---|---|---|
| `UEditorEngine::csgRebuild` | Editor.dll | `0x4a650` | the F8/"Rebuild Geometry" driver |
| `UEditorEngine::bspBrushCSG` | Editor.dll | `0x355e0` | apply ONE brush's CSG to the world model |
| `UEditorEngine::bspBuild` | Editor.dll | `0x35ef0` | build the BSP tree (recursive partition) |
| `UEditorEngine::bspRefresh` | Editor.dll | `0x36cd0` | drop unused nodes/verts after a build |
| `UEditorEngine::bspMergeCoplanars` | Editor.dll | `0x36200` | merge adjacent coplanar polys |
| `UEditorEngine::bspOptGeom` | Editor.dll | `0x36870` | geometry-optimization pass |
| `UEditorEngine::bspBuildBounds` | Editor.dll | `0xaace0` | build bounding volumes |
| `UEditorEngine::bspAddNode` | Editor.dll | `0x34e80` | add one node+surf to the tree |
| (internal) CSG leaf-filter | Editor.dll | `0x31f50` | classify+split a poly through the tree |
| `FPoly::SplitWithPlane` | Engine.dll | `0x1518b0` | split/classify a poly vs a plane |
| `FPoly::SplitWithPlaneFast` | Engine.dll | `0x151f90` | faster split used inside the build |
| `FPoly::Split` | Engine.dll | `0x151500` | split helper |
| `FPoly::Fix` | Engine.dll | `0x150da0` | remove near-duplicate vertices |
| `FPoly::RemoveColinears` | Engine.dll | `0x151090` | remove coincident + colinear vertices |
| `FPoly::CalcNormal` | Engine.dll | `0x150510` | compute normal; detect zero-area |
| `FPoly::Finalize` | Engine.dll | `0x150ac0` | the survival gate (calls the above) |
| `FPoly::Area` | Engine.dll | `0x1503c0` | polygon area |
| `FVector::NormalizeSlow` | Core.dll | `0x249d0` | normalize; the zero-length test |

**Provenance.** An `appFailAssert` in `SplitWithPlane` embeds the original source path:
`C:\GameDev\UnrealTournament\Engine\Src\UnFPoly.cpp`, with the asserts `NumVertices>=3` and
`NumVertices <= MAX_VERTICES`. So UED22's geometry code is the **Unreal Tournament (v469-era)
engine** — the same lineage the editor runs on. The algorithm matches the well-known UE1
`UnFPoly.cpp` / `UnBsp.cpp` / `UnEdCsg.cpp`.

## 2. The rebuild pipeline (what F8 / `MAP REBUILD` actually does)

`csgRebuild` (Editor.dll `0x4a650`) is the top of the pipeline. From its disassembly it:

1. `EmptyModel` — clears the level's world `UModel` (the BSP + poly soup).
2. Iterates the level's brushes **in actor order** (`ULevel::Brush()`, `AActor::IsStaticBrush`).
3. For each brush, applies its CSG to the world via `bspBrushCSG` (a virtual call on
   `UEditorEngine`; see §3).
4. After all brushes: `bspBuild` (partition into a tree), then `bspRefresh`,
   `bspMergeCoplanars`, `bspOptGeom`, `bspBuildBounds` — the cleanup/optimize tail.

**This is the binary confirmation of "brush order determines the final geometry"** (`csg-and-bsp.md`):
brushes are processed in sequence and each `bspBrushCSG` mutates the accumulated world, so the
*last* operation touching a region wins. `MAP SENDTO FIRST/LAST` reorders the actor list that
this loop walks. No heuristic re-sorts them.

## 3. How one brush is applied — `bspBrushCSG`

`bspBrushCSG` (Editor.dll `0x355e0`) does, per its call sequence:

1. `UModel::Modify` (undo) + `EmptyModel` on a scratch model.
2. `ABrush::BuildCoords` — builds the brush→world transform from `Location`/`Rotation`/scale.
3. For each of the brush's `FPoly`s: copy it, `FPoly::Transform` it into world space (apply the
   coords **and subtract `PrePivot`** — confirmed by the `FVector::operator-=` between
   `Transform` and the next step; this is the same `Location + R·(v − PrePivot)` transform
   uedctl mirrors, see `quirks.md` "Pivots"), then `FPoly::Fix` it.
4. Run the transformed brush through the world via the recursive **leaf-filter** static
   (`0x31f50`, called twice — the classic two-direction CSG: filter the world's polys against
   the brush, and the brush's polys against the world).

The leaf-filter (`0x31f50`) classifies each polygon against a plane using `FPlane::operator|`
(the dot product) compared against `0.0`, then `FPoly::Fix`es the resulting fragments and
**`FPoly::Reverse`s winding** for the subtractive case (a subtracted brush's faces point
*inward* relative to the brush, i.e. into the room). Fragments that survive become world
surfaces via `bspAddNode`.

## 4. WHERE FACES DIE — the four `FPoly` survival tests (the hole mechanism)

Every world face passes through `FPoly::Finalize` (Engine.dll `0x150ac0`). Finalize is the
gate, and it can reject a poly three ways. All thresholds below are **read from the compiled
code**, not assumed.

### 4a. `Finalize` — the gate

Disassembly of `Finalize(int NoError)`:

1. Calls `FPoly::Fix` (`0x150da0`) — collapses near-duplicate vertices (see 4b).
2. **If `NumVertices < 3` → reject.** Logs `"FPoly::Finalize: Not enough vertices (%i)"`
   (a warning if `NoError`, else `appErrorf` → **`Critical Error`**) and returns `-1`.
3. If `Normal` is still all-zero, calls `CalcNormal` (`0x150510`).
4. **If `CalcNormal` reports zero area → reject.** Logs
   `"FPoly::Finalize: Normalization failed, verts=%i, size=%f"` (warning, or `Critical Error`)
   and returns `-1`.

A `-1` from `Finalize` means *this face does not exist in the world* → **hole**. The two
critical-error variants are why a *bad enough* brush doesn't just leave a hole but **crashes
the rebuild** (matches `quirks.md`: degenerate geometry GPFs CSG).

### 4b. `Fix` + `RemoveColinears` — vertex collapse

`RemoveColinears` (Engine.dll `0x151090`) runs two passes over the vertex ring:

- **Pass 1 — drop coincident vertices.** For each vertex it forms `Side = V[i] − V[i−1]`,
  crosses it with the poly `Normal` (`FVector::operator^`), and tries to normalize the result
  with `FVector::NormalizeSlow`. NormalizeSlow (Core.dll `0x249d0`) returns *false* when
  `X²+Y²+Z² < 1e-8` (constant at Core `0xa0a40` = `SMALL_NUMBER`), i.e. **length < 1e-4 uu**.
  Because `Normal` is unit and `Side` lies in the poly plane, that cross length ≈ `|Side|`, so
  the test fires when two consecutive vertices are **closer than ~1e-4 uu** — they're treated
  as the same point and one is deleted.
- **Pass 2 — drop colinear vertices.** It compares each vertex's two adjacent side-plane
  normals component-wise (`FVector::Equals`-style, helper `0x10150880`) with threshold
  **`9.999999e-05` (≈ 1e-4)** — the immediate `0x38d1b717`. Two parallel side-planes mean the
  shared vertex lies on a straight edge → it's redundant and removed.
- **After either removal, if `NumVertices < 3`: it sets `NumVertices = 0` and returns false**
  → the caller discards the poly entirely.

So a face whose vertices have drifted into near-coincidence or near-colinearity gets *thinned*,
and if thinning drops it below a triangle it **vanishes**. This is the direct mechanism behind
"off-grid / accumulated-float geometry produces holes."

### 4c. `CalcNormal` — zero-area detection

`CalcNormal` (Engine.dll `0x150510`) accumulates a triangle-fan normal: for `i = 2..N` it sums
`(V[i−1] − V[0]) ^ (V[i] − V[0])` into `Normal` (this equals twice the area-weighted normal),
then calls `NormalizeSlow`. If the summed normal has `length² < 1e-8` (the same `SMALL_NUMBER`),
the polygon has **effectively zero area**: it logs `"FPoly::CalcNormal: Zero-area polygon"` and
reports degenerate (returns 1). A sliver poly — a long thin fragment produced by a near-miss
split — fails here and is dropped.

### 4d. Numeric summary (all read from `.rdata`)

| Constant | Value | Where | Effect |
|---|---|---|---|
| `THRESH_SPLIT_POLY_WITH_PLANE` | **0.25** | Engine `0x206780` (5 refs), Editor (2) | a poly within ±0.25 uu of a partition plane is **coplanar**, not split (§5) |
| `THRESH_SPLIT_POLY_PRECISELY` | **0.01** | Engine `0x1fee1c` | the "very precise" split band, used where exactness matters |
| `SMALL_NUMBER` | **1e-8** (size²) | Core `0xa0a40` | NormalizeSlow's zero-length floor → ~1e-4 uu length |
| colinear/coincident compare | **~1e-4** | immediate `0x38d1b717` | `RemoveColinears` vertex-drop threshold |
| `THRESH_POINTS_ARE_SAME` | 0.002 | Engine + Editor | point-equality elsewhere in CSG |
| `THRESH_POINTS_ARE_NEAR` | 0.015 | Engine + Editor | near-point tests |
| `THRESH_NORMALS_ARE_SAME` | 2e-5 | Editor | coplanar-merge normal equality (`bspMergeCoplanars`) |
| `THRESH_VECTORS_ARE_NEAR` | 0.0004 | Editor | vector near-equality |
| `THRESH_VECTORS_ARE_PARALLEL` | 0.02 | Engine + Editor | parallelism tests |

## 5. The 0.25 split band — the *upstream* cause

`FPoly::SplitWithPlane` (Engine.dll `0x1518b0`) is the workhorse of `bspBuild`. Disassembled,
its logic is:

1. Pick the threshold: the 5th arg `VeryPrecise` selects **0.01** (precise) or **0.25**
   (normal). Call it `T`.
2. For every vertex compute the **signed distance to the plane** `d = (V[i] − Base) · Normal`.
   Track the max and min `d` over all vertices, and per-vertex side:
   - `d > +T` → vertex is in **front**
   - `d < −T` → vertex is **behind**
   - `−T ≤ d ≤ +T` → vertex is **on** the plane (within the band)
3. Decide the whole poly:
   - `maxd < +T` **and** `mind > −T` → return **SP_Coplanar** (entirely inside the ±T band).
   - all front → SP_Front; all back → SP_Back; otherwise actually **split** it.

The load-bearing fact: **`T = 0.25` units is a *wide* band.** Any face that lies within a
quarter-unit of a partitioning plane is treated as *coplanar with that plane* rather than being
cleanly split by it. That is exactly the situation off-grid geometry creates:

- A brush rotated by a non-90° angle, or vertex-edited off the grid, or fed through CSG with a
  live (non-permanent) float transform, produces planes that are *almost* but not *exactly*
  aligned with neighbouring faces.
- Faces that "should" be split cleanly instead get mis-classified as coplanar, or get split
  with a vertex landing inside the band, producing a **sliver** (→ killed by §4c) or a
  **T-junction** (a vertex on one face that has no matching vertex on the abutting face → a
  crack the renderer leaks through).
- Each split also generates new vertices by interpolation; on a non-grid plane those land on
  irrational coordinates, so the *next* split accumulates more error. This is the "off-grid
  diagonal cuts spray through everything behind them" failure (`csg-and-bsp.md`) seen from the
  numeric side.

This is why the repairs in `csg-and-bsp.md` work, mechanistically:

| Repair (from `csg-and-bsp.md`) | Why it works (this spike) |
|---|---|
| **Grid discipline / clean multiples** | keeps face planes exactly coincident, so splits are exact and nothing lands in the ±0.25 band as a sliver |
| **Transform Permanently** | bakes the float transform into vertices once, so CSG sees stable coords instead of re-deriving drifting ones every rebuild |
| **Reorder brush (To First/Last)** | changes which planes partition which region → a different, cleaner set of splits (the `csgRebuild` order loop, §2) |
| **Flip semisolid ↔ solid** | changes whether a brush cuts the world BSP at all → re-partitions locally, avoiding the bad split |
| **Rebuild the face by hand (clockwise)** | re-adds an `FPoly` that survives `Finalize`; clockwise = correct winding so `CalcNormal` faces it outward (random order → degenerate/`Critical Error`, §4a) |

## 6. The coplanar/merge tail — a second collapse point

`bspMergeCoplanars` (Editor.dll `0x36200`) merges adjacent coplanar surfaces and **re-runs
`RemoveColinears`** on the merged result. So even a face that survived initial CSG can be
collapsed during the merge pass if merging two polys produces colinear vertices that thin it
below 3. `bspMergeCoplanars` uses `THRESH_NORMALS_ARE_SAME = 2e-5` to decide two surfaces are
coplanar. This is the build stage where `BSP REBUILD GOOD/OPTIMAL` (which run the coplanar pass)
can differ from `LAME` (which skips it) — see `commands.md` "Build pipeline".

## 7. What this does NOT cover (honest scope)

- The recursive partition-selection heuristic inside `bspBuild` (which plane it picks to split
  at each node, the balance/split-count tradeoff) is internal/static and was not fully
  disassembled — only its outer structure (MemStack temp alloc, `SplitWithPlaneFast` usage,
  progress logging) was confirmed. A bad partition *choice* can also cause node blowup; the
  *face-death* mechanism (§4–5) is the part this spike nails.
- No hole was reproduced live this session — the static evidence is definitive for *how the
  code decides*, but turning a specific off-grid brush into a specific HOM and capturing it is a
  separate, crash-prone live exercise (left as a follow-up if a concrete repro is ever needed).
- Lightmap/HOM rendering itself (the *visual* of a hole) is renderer-side (`render.dll`), out of
  scope here — this spike is the geometry side: why the face is absent.

## 8. Reusable tooling

`_scratch/bspspike/` (gitignored throwaway) holds the harness, reusable for any future binary
spike:
- `pe.py` — `pefile`+`capstone` helpers: export map, RVA↔offset, disassemble, read embedded
  floats/strings.
- `disfn2.py` — disassemble a function and **resolve `call` targets to export/import names**
  and annotate float operands. This is what made the call graphs above readable.
- `strings_dump.py` — regex over ASCII runs (the C++ symbol/RTTI names).

Install once into the uedctl venv: `pip install capstone pefile`. Everything is **static** (reads
the DLLs, never runs the editor), so it's safe and fast — complements
`unrealed/extracting-from-dll.md` (which covers the *wide string table*; this adds *code
disassembly*).
