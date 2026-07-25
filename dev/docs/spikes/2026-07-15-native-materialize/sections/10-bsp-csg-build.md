# Section 10 — CSG → BSP world-geometry build (native, editor-free)

**Status:** implementation-ready spec section (native `level materialize` geometry path).
**Date:** 2026-07-15. **Method:** static disassembly of UED22 `Editor.dll` / `Engine.dll`
(`capstone`+`pefile`; the DLLs are the UnrealTournament v469-lineage engine — provenance string
`C:\GameDev\UnrealTournament\Engine\Src\UnFPoly.cpp` in `SplitWithPlane`), cross-checked against a
real built `UModel` parsed from `/home/neob91/Games/LutrisDX/drive_c/DX/Maps/*.dx`.
**Reproduce:** `UED22=…/uned/UED22 python harness/verify_csg_build.py` (33/33 byte/RVA/vtable/constant
checks pass). All RVAs are file RVAs at ImageBase `0x10000000`; subtract nothing.

### Confidence legend
- ✅ live-verified (used by uedctl / matched against a real `.dx`)
- 🔬 live-probed (differential editor run in a prior spike)
- 📖 binary-extracted (read out of the compiled code / `.rdata` this session or a cited prior spike)

This section closes the two D2 gaps the design spec flagged: **gap #1** the CSG leaf-filter
(`bspBrushCSG` + `FilterEdPoly` + the keep/discard FilterFuncs) and **gap #2** the
`bspBuild`/`SplitPolyList`/`bspAddNode` node emission. It also decodes `SplitWithPlane`'s cut
geometry, the cleanup passes, portalize/zones, and the exact mapping onto the proven serializer
arrays (`harness`… `bspspike/umodel_serialize.py`).

---

## 0. Data structures (in-memory offsets, all 📖 byte-confirmed)

### 0.1 `FPoly` — the working polygon (size **0x1d8** = 472 bytes)
The unit of all CSG. `bspBrushCSG` / `FilterEdPoly` / `bspAddNode` all pass `FPoly*`.

| Field | Offset | Type | Note |
|---|---|---|---|
| `Base` | `0x00` | FVector (3×f32) | a point on the poly plane |
| `Normal` | `0x0c` | FVector | unit outward normal (authored winding = authoritative) |
| `TextureU` | `0x18` | FVector | texture basis U |
| `TextureV` | `0x24` | FVector | texture basis V |
| `Vertex[16]` | `0x30` | FVector[16] | ring, CCW seen from front; `MAX_VERTICES = 16` |
| `PolyFlags` | `0x1b0` | u32 | `PF_*` bits (§5) |
| `Actor` | `0x1b4` | ptr | owning brush actor (→ Surf.iActor) |
| `Texture` | `0x1b8` | ptr | → Surf texture obj-ref |
| `iLink` | `0x1c4` | i32 | surf-sharing link (== `Model.NumSurfs` ⇒ allocate a new surf; §6.4) |
| `iBrushPoly` | `0x1c8` | i32 | → Surf.iBrushPoly |
| `iZone[2]` | `0x1cc` | u16[2] | zone pair → Surf.iZone |
| `NumVertices` | `0x1c0` | i32 | current ring length |

Vertex i is at `0x30 + i*12`. `Vertex[14]` starts at `0xe4` (used by `bspAddNode`'s >16-vert split).
Verified: `harness/verify_csg_build.py` (SplitInHalf guard reads `[FPoly+0x1c0]`; `Normal` used as the
plane operand at `FilterEdPoly` `0x10032e2e`; verts read at `[FPoly+i*12+0x30]` in `SplitWithPlane`).

### 0.2 `FBspNode` — in-mem 0x40 (64 B); serialized differently (§9)
Offsets used by the build (from `bspAddNode` / `FilterEdPoly` / `csgRebuild` disasm):

| Field | Mem off | Serialized as | Note |
|---|---|---|---|
| `Plane` | `0x00` | f32×4 (X,Y,Z,W) | node partition plane; `W` = offset (`N·P = W`) |
| `ZoneMask` | `0x10` | u64 | zone visibility bitmask |
| `PolyFlags`/`NodeFlags` | `0x04`(surf) / node byte | u8 `NodeFlags` | NF_* (§6.4) |
| `iVertPool` | — | ci | first index into `Verts` |
| `iSurf` | `0x1c`? | ci | index into `Surfs` |
| `iBack` | `0x20` | ci `iFront` | back child (-1 = leaf) *(see §9 name caveat)* |
| `iFront` | `0x24` | ci `iBack` | front child (-1 = leaf) |
| `iPlane` | `0x28` | ci | **coplanar chain** next node (-1 = end) |
| `iCollisionBound` `iRenderBound` | — | **ci×2** | → `bspBuildBounds` Bounds-array indices; -1 = none (renderer skips the bound test) |
| `iZone[2]` | — | ci×2 | zone indices |
| `NumVertices` | — | ci | ring length |
| `iLeaf[2]` | — | **i32×2** | per-side leaf index; -1 = solid (no leaf) |

> **⚠ Corrected 2026-07-15 — see [`50-model-ondisk-layout-and-render.md`](50-model-ondisk-layout-and-render.md).**
> An earlier draft of the two rows above had the field order inverted: it listed the **ci pair**
> after `iPlane` as `iLeaf[2]`+`iZone[2]` and the trailing **fixed-i32 pair** as
> `iCollisionBound`/`iRenderBound`. The correct on-disk order (hand-decoded from `DXOnly.dx`,
> RVA-cited disasm of the `OccludeBsp` bound guard) is: ci `iCollisionBound`,`iRenderBound`, then
> ci `iZone[2]`, then ci `NumVertices`, then fixed-i32 `iLeaf[2]`. This inversion is exactly the
> bug fixed in commit 51e47618b (a leaf marker written into what was really the `iRenderBound`
> slot shipped `iRenderBound=0` into an empty Bounds array → NULL-FBox crash).

**Node-child offset caveat (📖, load-bearing):** in the in-memory struct the CSG walker reads
child links at `[node+0x20]` and `[node+0x24]` and the coplanar link at `[node+0x28]`
(`FilterEdPoly` `0x10032e59/0x10032e68`, `bspAddNode` `0x10034eca`). The *serialized* order writes
these two children as `iFront` then `iBack` (parser field names), i.e. the serialized `i_front`
field carries the memory `[+0x20]` value. For a faithful writer, treat them as an ordered
(childA=[+0x20], childB=[+0x24]) pair and reproduce whatever `SplitPolyList` wrote — do **not**
attach semantic front/back meaning beyond "the side `PlaneDot<0` goes to childA" (§6.3).

### 0.3 `FBspSurf`, `FBspVert`, `FBspLeaf`, `FZoneProperties`
Serial layouts are exactly as `bspspike/umodel_parser.py` decodes them (✅ round-trips byte-exact on
the whole real-map corpus via `umodel_serialize.py`). Key fields the build fills — see §9.

---

## 1. The rebuild pipeline (✅ pass order fully decoded)

Two entry points share the same machinery:
- **F8 / `csgRebuild`** — `UEditorEngine::csgRebuild(ULevel*, INT)` `Editor.dll 0x4a650`.
- **`MAP REBUILD`** — exec handler `Editor.dll 0x65220` (params, §6.1), then the same passes.

`csgRebuild`'s decoded body (📖, `0x4a650`–`0x4ab09`; every vtable slot resolved in
`verify_csg_build.py`):

```
csgRebuild(Level):
  Model = Level.Model
  Model.Modify();  Model.EmptyModel(1,1)          # clear Nodes/Surfs/Verts/Vectors/Points
  count brushes                                    # for the progress bar
  # ---- PASS A: structural brushes (Solid + Portal) ----
  for actor in Level.Actors in ACTOR ORDER:
      if actor is a static brush and it is structural (Solid or Portal, not detail):
          flags = actor.PolyFlags
          if (flags & PF_Semisolid) and actor.CsgOper==CSG_Add and not (flags & PF_Portal):
              continue                             # a semisolid Add is a DETAIL brush -> pass B
          if flags & PF_Portal:                    # portal special-case (collision spike, 0x4a814):
              flags = (flags & ~PF_Semisolid) | PF_NotSolid
          bspBrushCSG(actor, Model, flags, actor.CsgOper, 0, 1)     # vtable+0x214
  bspRepartition(Model, 0)                          # vtable+0x1ec  -> §1.1
  TestVisibility(Model, 0, 0)                       # vtable+0x264  (portal/zone flood; §8)
  # ---- PASS B: detail brushes (Semisolid Add) ----
  for actor in Level.Actors in ACTOR ORDER:
      if (actor.PolyFlags & (PF_Portal|PF_Semisolid))==PF_Semisolid and actor.CsgOper==CSG_Add:
          bspBrushCSG(actor, Model, actor.PolyFlags, actor.CsgOper, 0, 1)
  for each recorded Add/Subtract child subtree: bspRepartition(Model, iChild, 2)   # re-partition
  bspOptGeom(Model)                                 # vtable+0x218  -> §7.2
  bspBuildBounds(Model)                              # vtable+0x208  -> §7.4
```

`bspBrushCSG` is called with `(brush, model, PolyFlags, CsgOper, 0, 1)`; the last two constants are
`bMergePolys=0`, `bReplaceNULL/bBuildBounds=1` per the calling convention. **Brushes process in
actor order; last op wins** — this is the binary confirmation of "brush order determines geometry".

### 1.1 `bspRepartition` (✅ `Editor.dll 0x49fc0`) — the build core
```
bspRepartition(Model, balancePortal):
  bspBuildFPolys(Model, 1, balancePortal)   # vtable+0x20c: regenerate the world FPoly list from Surfs
  bspMergeCoplanars(Model, 0, 0)            # vtable+0x210: §7.1
  bspBuild(Model, OPTIMAL/GOOD, 12/…, PortalBias, balancePortal)   # vtable+0x1fc: §6
  bspRefresh(Model, 1)                      # vtable+0x200: §7.3 compact arrays
```
So the **complete ordered pass list a native materialize must reproduce** is:

1. `EmptyModel`
2. per structural brush → **CSG leaf-filter** (`bspBrushCSG`, §4) — emits world Surfs/Nodes soup
3. `bspBuildFPolys` — flatten Surfs back into an `FPoly` list for partitioning (§6.2)
4. `bspMergeCoplanars` (§7.1)
5. `bspBuild` → recursive `SplitPolyList` → `FindBestSplit` + `bspAddNode` (§6) — builds the tree
6. `bspRefresh` (§7.3)
7. `TestVisibility` → portalize/zones/leaves (§8)
8. per detail (semisolid) brush → `bspBrushCSG` again
9. subtree re-partition, `bspOptGeom` (§7.2)
10. `bspBuildBounds` (§7.4) — per-node collision hulls

**F8 vs `MAP REBUILD` params differ** (📖): F8 calls `bspRepartition(Model,0)` (BalancePortal=0);
`MAP REBUILD` resolves `Balance=50, PortalBias=70, Optimization=OPTIMAL` (byte-verified prior spike
`2026-06-26…/harness/verify_heuristic.py`, `0x65220`). **Target the `MAP REBUILD` params** — that is
the canonical geometry every shipped `.dx` was built with.

---

## 2. FPoly survival gates (📖, prior spike `2026-06-24-bsp-csg-hole-mechanism`; re-confirmed)

Every emitted face passes `FPoly::Finalize(NoError)` `Engine.dll 0x150ac0`:
1. `Fix()` `0x150da0` — drop near-duplicate verts.
2. `NumVertices < 3` → **reject** (`-1`); `NoError=0` ⇒ `appErrorf` **aborts the whole build**.
3. If `Normal` zero → `CalcNormal()` `0x150510`: triangle-fan sum `Σ (V[i-1]-V[0])×(V[i]-V[0])`;
   `NormalizeSlow` floors at `|N|² < 1e-8` (`SMALL_NUMBER`, ~1e-4 uu length) → zero-area → **reject**.
`RemoveColinears()` `0x151090`: pass 1 drops coincident verts (< ~1e-4 uu); pass 2 drops colinear
verts (side-plane normals equal within `9.999999e-05`); if it thins below 3 verts, `NumVertices=0`
→ the poly vanishes. These predicates are the "silent-absence hole" source and must be ported
exactly (float32-faithful).

Constants (📖 `.rdata`): `THRESH_SPLIT_POLY_WITH_PLANE=0.25`, `THRESH_SPLIT_POLY_PRECISELY=0.01`,
`SMALL_NUMBER=1e-8`, colinear `9.999999e-05`, `THRESH_POINTS_ARE_SAME=0.002`,
`THRESH_POINTS_ARE_NEAR=0.015`, `THRESH_NORMALS_ARE_SAME=2e-5`, `THRESH_VECTORS_ARE_PARALLEL=0.02`.

---

## 3. `SplitWithPlane` — classify **and** cut (📖 fully decoded, `Engine.dll 0x1518b0`)

Signature `FPoly::SplitWithPlane(const FVector& Base, const FVector& Normal, FPoly* Front,
FPoly* Back, int VeryPrecise) const → int`. Used by the CSG filter (§4) and (as `…Fast`) by
`FindBestSplit`. Returns `1=Front, 2=Back, 0=Coplanar, 3=Split`.

**Threshold** `T` (📖 `0x10151902`): `T = VeryPrecise ? 0.01 : 0.25`. The CSG filter passes
`VeryPrecise=0` ⇒ **T=0.25** (`FilterEdPoly` `0x10032d0c`).

**Classify (first loop, `0x101519c0`):** for each vertex compute `d = (V[i] − Base) · Normal`
(float32 SSE). Track `MaxDist`, `MinDist`. Per-vertex side flag: `d > +T` marks "front seen";
`d < −T` marks "back seen"; `−T ≤ d ≤ +T` marks neither (on-plane). **Decision (📖, exact branch
map at `0x10151a70`):**

| condition | return |
|---|---|
| `MaxDist < T` **and** `MinDist > −T` | `0` Coplanar |
| `MaxDist < T` and `MinDist ≤ −T` | `2` Back |
| `MaxDist ≥ T` and `MinDist > −T` | `1` Front |
| else (straddles) | `3` Split → cut below |

**Cut geometry (second loop, `0x10151b25`):** Front/Back output polys are copied from `this`
(`operator=`), then `NumVertices=0`, `PolyFlags |= 0x80000000` (a transient marker), and
`DiscardVertexDeltas`. Walk each directed edge `(Prev=V[i-1], This=V[i])` with signed dists
`(PrevD, ThisD)`; per-vertex **side** = `This_d > +T → FRONT(0)` / `This_d < −T → BACK(1)` /
else on-plane. For each edge:
- both FRONT → append `This` to Front.
- both BACK → append `This` to Back.
- FRONT→BACK or BACK→FRONT (a real crossing) → compute the **intersection vertex**
  `I = Prev + (This − Prev) · ( PrevD / (PrevD − ThisD) )` (the universal UE1 lerp; the code builds
  it inline from the stored `PrevD`/`ThisD` and appends `I` to **both** Front and Back), then append
  `This` to whichever side it belongs.
- an **on-plane** vertex (within ±T) is appended to both sides (it is a shared boundary vertex — this
  is exactly where T-junctions/cracks originate off-grid).
After the loop both output polys get `Fix()` (`0x10151f10`); if either ends `< 3` verts the split is
demoted (the caller sees fewer real fragments). Winding is preserved: Front keeps CCW-from-front,
Back keeps CCW-from-front (they share the interpolated edge with opposite traversal).

*(Port note: the ±0.25 band means the SIDE used for emitting a vertex and the SIDE used for the
front/back/coplanar decision are the SAME band here — unlike `SplitWithPlaneFast` where the band only
gates the decision. Reproduce float32-faithfully; a vertex exactly at ±0.25 is treated as on-plane
`jbe`/`jb` → inclusive of the band.)*

---

## 4. CSG leaf-filter — carving solid/void (📖 gap #1 CLOSED)

### 4.1 `bspBrushCSG` (✅ `Editor.dll 0x355e0`) — apply ONE brush
```
bspBrushCSG(brush, Model, PolyFlags, CsgOper, ..):
  subtractMask = (CsgOper==CSG_Add) ? 0 : 0x28          # 0x28 = PF_Semisolid|PF_NotSolid  (📖 0x3567e)
  Model.Modify()
  TempModel.EmptyModel()
  coords = brush.BuildCoords()                          # Location/Rotation/Scale -> FModelCoords
  for each brush FPoly P:
      Q = copy(P)
      Q.Transform(coords, brush.PrePivot, ..)           # world space = Location + R·S·(v − PrePivot)
      Q.Fix()
      Q.PolyFlags = (Q.PolyFlags | PolyFlags) & ~subtractMask
      # push Q into TempModel poly list
  # ---- two-direction filter, FilterFunc chosen PER-CsgOper via a cmove (📖 0x35a84/0x35b03) ----
  # PASS 1 (brush-through-world; the func ADDS world nodes for kept fragments):
  f1 = (CsgOper == CSG_Add) ? AddFunc_0x31770 : SubtractFunc_0x348c0     # 📖 cmove @0x35a95
  for each transformed brush FPoly Q:  bspFilterFPoly(f1, Model, Q)      # §4.3
  # PASS 2 (world-through-brush; the func COLLECTS surviving fragments into TempModel, no nodes):
  f2 = (CsgOper == CSG_Intersect) ? IntersectFunc_0x339e0 : OutsideFunc_0x32390   # 📖 cmove @0x35b14
  for each world Surf FPoly W:  bspFilterFPoly(f2, Model, W)             # §4.3
  … bspBuild(TempModel) … cleanup … bspBuildBounds …
```
**The FilterFunc is NOT constant across CsgOper** — each pass's leaf callback is selected by a
`cmove` on `CsgOper` (📖 `bspBrushCSG 0x35a84`–`0x35b18`): `cmp [CsgOper],1; cmove eax,0x31770`
(pass 1) and `cmp [CsgOper],3; cmove eax,0x339e0` (pass 2). Four distinct functions are used across
the four opers; all four are byte-decoded (§4.3). *(`harness/verify_csg_build.py` asserts the CsgOper
`0x28` mask and the `0x348c0`/`0x32390` branch tables; the two `cmove`s and `0x31770`/`0x339e0` are
decoded from the disassembly at the cited addresses in §4.3 and not yet added to that harness's
assertion set.)*
`Transform` = `FPoly::Transform(coords, PrePivot, PostAdd, Orientation)` `Engine.dll 0x152360`
(same `Location + R·(v−PrePivot)` uedctl already mirrors). `CsgOper` enum: `CSG_Add=1,
CSG_Subtract=2, CSG_Intersect=3, CSG_Deintersect=4`.

### 4.2 The recursion `FilterEdPoly` (📖 `Editor.dll 0x32bf0`) — dispatched via `bspFilterFPoly 0x31f50`
`bspFilterFPoly` `0x31f50`: if `Model.Nodes` is empty, call the FilterFunc directly with
`Filter = F_OUTSIDE(0)` (bare-world case); else descend `FilterEdPoly`.

`FilterEdPoly(FilterFunc, Model, iNode, EdPoly, CoplanarInfo, Outside)` recursively pushes the poly
fragment down the world BSP:
```
FilterEdPoly:
  if EdPoly.NumVertices >= 14:                 # 📖 0x32c56 (headroom for a split adding verts)
      EdPoly.SplitInHalf(&Half)                # split, recurse Half first, then continue on EdPoly
      FilterEdPoly(.., Half, ..)
  node   = Model.Nodes[iNode]
  surf   = Model.Surfs[node.iSurf]
  base   = Model.Points[surf.pBase]            # 📖 node.iSurf@+0x1c, surf.pBase@+8
  normal = Model.Vectors[surf.vNormal]         # 📖 surf.vNormal@+0xc
  r = EdPoly.SplitWithPlane(base, normal, &Front, &Back, VeryPrecise=0)   # T=0.25
  switch r:
    FRONT(1): descend the node's FRONT side  with EdPoly
    BACK(2):  descend the node's BACK  side  with EdPoly
    SPLIT(3): descend FRONT with Front, BACK with Back
    COPLANAR(0):
        facing = sign( node.plane · EdPoly.Normal )      # 📖 FPlane::operator| vs EXACT 0.0 (0x32e54)
        if facing >= 0:  treat EdPoly as coplanar-FACING-OUT, descend FRONT side
        else:            treat EdPoly as coplanar-FACING-IN,  descend BACK side
        (record CoplanarInfo so the leaf sees F_COPLANAR_* / F_COSPATIAL_*)
  # at a leaf (child == -1) call FilterFunc(Model, iNode, fragment, Filter, ENodePlace)
```
The **coplanar facing test uses EXACT 0.0** (not the ±0.25 band) — the band gates only the
front/back/coplanar split decision; whether a coplanar poly is treated as facing the same way as the
node (F_COSPATIAL_FACING_OUT) or opposite (…_IN) is the sign of the dot at exactly 0.

**`EPolyNodeFilter` at the leaf (📖 confirmed via the FilterFunc branch tables):**
`F_OUTSIDE=0, F_INSIDE=1, F_COPLANAR_OUTSIDE=2, F_COPLANAR_INSIDE=3, F_COSPATIAL_FACING_OUT=4,
F_COSPATIAL_FACING_IN=5`.

### 4.3 The four keep/discard/reverse FilterFuncs (📖 the CSG heart — ALL byte-decoded)
`EPolyNodeFilter` again: `F_OUTSIDE=0, F_INSIDE=1, F_COPLANAR_OUTSIDE=2, F_COPLANAR_INSIDE=3,
F_COSPATIAL_FACING_OUT=4, F_COSPATIAL_FACING_IN=5`. Four distinct leaf callbacks exist; the `cmove`
(§4.1) selects two of them per CsgOper. **Each is byte-decoded from its Filter branch table below**,
at the cited RVA. (`harness/verify_csg_build.py` byte-asserts the `0x348c0`/`0x32390` branch patterns;
the `0x31770`/`0x339e0` tables are shown here directly from their disassembly.)

**PASS-1 funcs — these ADD world nodes (`bspAddNode`, NodeFlags=0x20) for kept fragments:**

**`SubtractFunc` `0x348c0`** (used pass-1 by Subtract/Intersect/Deintersect):
```
if Filter in {F_INSIDE(1), F_COPLANAR_INSIDE(3)}:        # 📖 sub 1 je / sub 2 jne => {1,3}
    EdPoly.Reverse();  bspAddNode(.., 0x20, EdPoly);  EdPoly.Reverse()   # REVERSED winding, faces inward
# else discard
```
**`AddFunc` `0x31770`** (used pass-1 by Add only):
```
if Filter == F_OUTSIDE(0) or F_COPLANAR_OUTSIDE(2):      # 📖 sub 0 je / sub 2 je
    bspAddNode(.., 0x20, EdPoly)                          # NO Reverse — winding as-authored
elif Filter == F_COSPATIAL_FACING_IN(5) and not (EdPoly.PolyFlags & PF_Semisolid):   # 📖 sub 3 jne / test 0x20
    bspAddNode(.., 0x20, EdPoly)                          # NO Reverse
# else discard
```
→ Confirms the Add conclusion (keep OUTSIDE, no reverse) **and** decodes the extra rule: a
cospatial-facing-in fragment is also kept unless the brush is semisolid.

**PASS-2 funcs — these COLLECT surviving fragments into the TempModel list (Fix, keep if ≥3 verts;
no node added):**

**`OutsideFunc` `0x32390`** (used pass-2 by Add/Subtract/Deintersect):
```
if Filter in {F_OUTSIDE(0), F_COPLANAR_OUTSIDE(2)}:      # 📖 sub 0 je / sub 2 jne => {0,2}
    if EdPoly.Fix() >= 3: save copy(EdPoly)              # 📖 appMalloc(0x1d8)+copy-ctor
```
**`IntersectFunc` `0x339e0`** (used pass-2 by Intersect only):
```
if Filter in {F_INSIDE(1), F_COPLANAR_INSIDE(3)}:        # 📖 sub 1 je / sub 2 jne => {1,3}
    if EdPoly.Fix() >= 3: save copy(EdPoly)              # 📖 identical body, keeps INSIDE instead
```

**Per-CsgOper resolution (📖 both `cmove`s decoded):**

| CsgOper | pass-1 func (adds nodes) | pass-1 keep set | winding | pass-2 func (collects) | pass-2 keep set |
|---|---|---|---|---|---|
| **Add**(1) | `0x31770` | F_OUTSIDE, F_COPLANAR_OUTSIDE, F_COSPATIAL_FACING_IN (¬semisolid) | as-authored | `0x32390` | F_OUTSIDE, F_COPLANAR_OUTSIDE |
| **Subtract**(2) | `0x348c0` | F_INSIDE, F_COPLANAR_INSIDE | **Reverse()** | `0x32390` | F_OUTSIDE, F_COPLANAR_OUTSIDE |
| **Intersect**(3) | `0x348c0` | F_INSIDE, F_COPLANAR_INSIDE | **Reverse()** | `0x339e0` | F_INSIDE, F_COPLANAR_INSIDE |
| **Deintersect**(4) | `0x348c0` | F_INSIDE, F_COPLANAR_INSIDE | **Reverse()** | `0x32390` | F_OUTSIDE, F_COPLANAR_OUTSIDE |

**Correction (was wrong in the prior draft):** Deintersect does **not** "keep F_OUTSIDE as-authored".
It falls through both `cmove`s to the Subtract pair `(0x348c0, 0x32390)`, so its pass-1 keeps
**F_INSIDE reversed** (identical to Subtract) — the pass-2 collect func is the only thing it shares
with the "outside" family. For level CSG, Solid Add and Subtract are the only opers that occur;
Intersect/Deintersect are brush-builder operations (rarely in a level's actor list).

---

## 5. Solidity classes (📖 collision spike + `csgRebuild` re-confirmed)

`PF_NotSolid=0x08, PF_Semisolid=0x20, PF_Portal=0x04000000, PF_Invisible=0x01, PF_TwoSided=0x100`.

| Class | CSG behavior | Node result |
|---|---|---|
| **Solid** (default) | Add fills / Subtract carves the solid/empty structure; **cuts the BSP** | full blocking node structure; collides + renders |
| **Semisolid** (`PF_Semisolid`) | processed in **PASS B** as an Add that **adds surfaces without re-cutting** solidity | thin surface nodes only; collides at the face, no closed solid volume ("unreliable underfoot") |
| **Nonsolid** (`PF_NotSolid`) | **no node** contributed to collision structure | decorative; walk through it |
| **Portal** (`PF_Portal`) | `csgRebuild` forces `flags = (flags & ~PF_Semisolid) \| PF_NotSolid` **before CSG** (📖 `0x4a814`); it cuts zones for visibility but never collides | zone-portal node; used by `TestVisibility` (§8), never blocks |

Collision is **structural** (no per-node `PolyFlags` test at trace time; `UModel::LineCheck`
`0x1ae4c0`) — so a missing node = fall-through, a stray sliver node = invisible wall. `bspAddNode`
stores `Surf.PolyFlags & 0x3cffffff` (📖 `0x34fa9`) — high render-only bits are masked off the surf,
and it derives `NodeFlags`: `PF_NotSolid(8)→NF|=1`, `PF_Portal|PF_Invisible(0x4000001)→NF|=4`,
`0x2→NF|=2`, `0x10020000→NF|=2`.

---

## 6. `bspBuild` → `SplitPolyList` → `FindBestSplit` → `bspAddNode` (gap #2)

### 6.1 Params (📖 byte-verified, prior spike `2026-06-26`)
`MAP REBUILD`: `Balance=50, PortalBias=70, Optimization=OPTIMAL(2)`. `BalancePortal` word =
`Balance | (PortalBias<<8)`. `Optimization` → `FindBestSplit` candidate stride
`Inc = {OPTIMAL:1, GOOD:n//10, LAME:n//4}` (floored at 1); OPTIMAL is exact.

### 6.2 `bspBuildFPolys` (`Editor.dll 0x36090`)
Regenerates the world `FPoly` list from the current `Surfs` (each surf → one `FPoly`, texture/normal
vectors resolved from the pools). This is the input list `bspBuild` partitions. Node count target =
`# FPolys hung on the tree` (each coplanar poly at a node = its own node in the `iPlane` chain).

### 6.3 `FindBestSplit` (📖 ported, `Editor.dll 0x335d0`) — see `harness/find_best_split.py`
`Score = (100−Balance)·Splits + Balance·|Front−Back|`; portal candidate bonus
`−(100−Balance)·Splits·PortalBias`; a *split of a portal* poly counts ×16. Structural
(`PolyFlags & 0x28`) non-portal polys are skipped as candidate splitters unless every remaining poly
is structural. Strict `<` tie-break → earliest wins. Classification via `SplitWithPlaneFast`
`0x151f90` (±0.25 band, classify-only). **The `0x336d2` structural-splitter skip is fully decoded**
(prior spike §2b; reproduced in the port) — the open item is closed.

`SplitPolyList` (`Editor.dll 0x34530`, recursive): pick `iBest = FindBestSplit(list)`; its plane
becomes the node plane; partition the remaining polys with `SplitWithPlane` (VeryPrecise per the
build), recurse front/back; polys coplanar with the chosen plane are **chained onto the node via
`bspAddNode(ENodePlace=NODE_Plane)`** rather than recursed. `bspBuild` calls it with the whole world
poly list (`bspBuild 0x35fe1` → `SplitPolyList(model,-1,3,PolyList,NumPolys,…)`).

### 6.4 `bspAddNode` (📖 fully decoded, `Editor.dll 0x34e80`) — emits Nodes/Surfs/Verts/Vectors/Points
```
bspAddNode(Model, iParent, ENodePlace, NodeFlags, EdPoly):     # ENodePlace: 0=BACK,1=FRONT,2=PLANE,3=ROOT
  if ENodePlace == NODE_PLANE(2):                    # 📖 0x34ebd: walk to end of coplanar chain
      iParent = last node in Nodes[iParent].iPlane chain
  if EdPoly.NumVertices > 16:                        # 📖 0x35058: split for storage (MAX 16/node)
      A = first 16 verts;  B = verts[14..] (NumVertices-14)          # overlap 2 verts (shared edge)
      i = bspAddNode(A, ENodePlace);  bspAddNode(B, NODE_PLANE chained to i);  return i
  iNode = Model.Nodes.Add()                          # new node slot
  # ---- surf sharing ----
  if EdPoly.iLink == Model.NumSurfs:                 # 📖 0x34ee3: allocate a NEW surf
      s = Model.Surfs.Add()
      s.pBase     = bspAddPoint (Model, EdPoly.Base,     exact=1)    # dedup into Points  (vtable+0x1f4)
      s.vNormal   = bspAddVector(Model, EdPoly.Normal,   exact=1)    # dedup into Vectors (vtable+0x1f0)
      s.vTextureU = bspAddVector(Model, EdPoly.TextureU, exact=0)
      s.vTextureV = bspAddVector(Model, EdPoly.TextureV, exact=0)
      s.Texture   = EdPoly.Texture
      s.PolyFlags = EdPoly.PolyFlags & 0x3cffffff     # 📖 0x34fa9  (mask render-only bits)
      s.iActor    = EdPoly.Actor ;  s.iBrushPoly = EdPoly.iBrushPoly ;  s.iZone = EdPoly.iZone
      s.iLightMap = -1
  else:
      s = Model.Surfs[EdPoly.iLink]                   # reuse existing surf (shared face)
  node.iSurf = index(s)
  node.Plane = FPlane(EdPoly.Base, EdPoly.Normal)     # X,Y,Z,W where W = Base·Normal
  node.NodeFlags = NodeFlags | derive_from(s.PolyFlags)   # §5 derivation
  # ---- vert pool: one FBspVert per EdPoly vertex ----
  node.iVertPool = Model.Verts.NumVerts
  for v in EdPoly.Vertex[0..NumVertices):
      Model.Verts.Add( FBspVert{ iVertex = bspAddPoint(Model, v, exact=1), iSide = <edge side id> } )
  node.NumVertices = EdPoly.NumVertices
  link node under iParent per ENodePlace (BACK->parent.iBack, FRONT->parent.iFront, PLANE->iPlane chain)
  return iNode
```

**`bspAddVector`/`bspAddPoint` are the pooling dedup** (📖 `bspAddVector 0x35530`): return
an existing index if the vector/point already in the pool within tolerance (`exact=1` uses tight
`THRESH_NORMALS_ARE_SAME=2e-5` / `THRESH_POINTS_ARE_SAME=0.002`; `exact=0` for texture vectors is
looser), else append. **This is how `Vectors`/`Points` are deduplicated/pooled** — every distinct
plane normal, base, and vertex appears once, and `Surfs`/`Verts` index into the pools.

### 6.5 The `abutting_subtracts` 11-vs-10 discrepancy (diagnosis)
The prior port read 11 surface nodes vs the editor's 10 on two abutting subtracts sharing a face. The
mechanism is now decoded: two coincident **opposite-facing** coplanar surfaces from the two rooms'
shared wall **annihilate** — the leaf-filter's exact-0.0 coplanar facing test (§4.2) routes one
F_COSPATIAL_FACING_OUT and one F_COSPATIAL_FACING_IN to opposite leaf sides, and only one survives as
a bounding surface (the other is a buried interior face → discarded). The port's placeholder
`csg_world_surfaces` cancelled by coordinate coincidence but did **not** reproduce the facing-sign
route, so it kept one extra interior face (11). **Fix:** implement §4.2/§4.3 faithfully — the extra
node is an un-annihilated interior face, not a heuristic drift. (The heuristic/`FindBestSplit` is
byte-exact and not the cause.)

---

## 7. Cleanup passes

### 7.1 `bspMergeCoplanars` (📖 `Editor.dll 0x36200`)
Merges adjacent coplanar surfaces sharing an edge into one poly and **re-runs `RemoveColinears`** on
the result (a second collapse point — a merge can thin a face below 3 verts → it vanishes). Coplanar
test uses `THRESH_NORMALS_ARE_SAME = 2e-5`. Logs `BspMergeCoplanars reduced %i->%i`. For a native
port: group Surfs by (normal within 2e-5, offset within 0.002); within a group, union edge-adjacent
polys; re-run colinear removal; drop any that fall < 3 verts.

### 7.2 `bspOptGeom` (✅ decoded to instruction level — spike `42-bspoptgeom-decode.md`)
**CORRECTION (an earlier draft of this section was wrong):** `bspOptGeom` is a **pure T-junction /
side-link pass — it does NOT remove nodes and changes NO array length.** Its only writes are
`Verts[i].iSide` (mem +4) and `Model.NumSharedSides` (mem +0xfc); it never calls `bspAddNode`, never
edits a vertex ring, never drops a node. Logs: `"BspOptGeom begin"` → `"building sidelinks"` →
`"Processed %i T-points, linked: %i/%i sides"` → `"BspOptGeom end"`. Algorithm: reset all `iSide=-1`,
`NumSharedSides=4`; **pass 1** builds a point→node link table via recursive `AddPointLink 0x325e0`
(descends the BSP by `PlaneDot`, ±0.25 band); **pass 2** finds node pairs sharing a coincident
*adjacent* edge and assigns them a common `iSide` (allocating from `NumSharedSides++`). Purely
adjacency bookkeeping — irrelevant to the per-surf **vertex sets** (Tier-S). A native build can defer
it entirely (empty sidelinks) without affecting solid/void or surf-set parity.
**The `Nodes: %i -> %i` / `Polys: %i -> %i` reduction logs belong to `bspRefresh`, NOT bspOptGeom.**

### 7.3 `bspRefresh` (📖 `Editor.dll 0x36cd0`)
Compaction: drops **tree-UNREACHABLE** nodes/verts/surfs (CSG residue) — via a mark helper `0x34aa0`
that recurses reachable children (+0x20/+0x24) + the coplanar chain (+0x28) from root — and renumbers
the child/`iVertPool` indices. **Owns the `Nodes: %i -> %i` / `Polys: %i -> %i` logs.** It drops only
*unreachable* nodes; a partition split chosen by `Balance=50` FindBestSplit **survives intact** — there
is NO "over-split then remove redundant partitions" recovery. **Load-bearing consequence for the port:**
the per-surf vertex sets come ENTIRELY from the CSG leaf-filter cuts + `SplitPolyList`/`SplitWithPlane`
under the real `Balance=50, PortalBias=70` heuristic (§6.3). A split-**minimizing** stand-in can never
reproduce a balance-driven "gratuitous" split (e.g. an off-grid wedge splitting a far wall at a plane
no surf is adjacent to) — so a faithful port MUST run the real `Balance=50` FindBestSplit inside a
faithful `SplitPolyList 0x34530` (coplanar chaining + candidate stride + structural-splitter skip). No
geometry decisions of its own — pure array GC + reindex.

### 7.4 `bspBuildBounds` (📖 `Editor.dll 0xaace0`) — the collision hulls
Builds per-node **bounding volumes** used by `LineCheck`/`PointCheck`. Emits
`bspBuildBounds: Generated %i bounds, %i hulls`. Fills the `iCollisionBound`/`iRenderBound` node
fields (i32, -1=none) that index the raw **FBox `LeafHulls`/`Bounds` arrays** at UModel `+0xc0`
(TArray<FBox>, 25-byte serial elems) and the `+0xcc`/`+0xe4` INT arrays. For a native build these are
**synthesizable**: for each convex leaf, the hull is the set of node planes bounding it (`Bound`
array of plane indices) plus an `FBox` AABB of the leaf's verts. §9 says exactly which array each
feeds.

---

## 8. Portalize / zones / leaves (`TestVisibility` `Editor.dll 0xaa940`)

> **Confidence: the OUTPUT field meanings are 📖 (byte-decoded, §9-validated) and the top-level
> pass SKELETON is 📖 (decoded this session); the per-pass flood-fill ALGORITHM is NOT yet decoded
> to instruction level — it is a large multi-function zoning flood left as inferred / a bounded
> follow-on. Do not treat §8's algorithm sketch as port-ready.** Only §8.1 (pass skeleton) and the
> field meanings (§9) are decoded; §8.3 is explicitly the fallback to build against tonight.

### 8.1 What IS decoded — the pass skeleton (📖)
`csgRebuild` calls `TestVisibility(Model, 0, 0)` (vtable+0x264, `0xaa940`) after `bspRefresh`.
`TestVisibility` dispatches to a **portalizer** `sub_aa370` that runs a `"Zoning"` slow-task as an
**ordered sequence of ~8 helper passes** (📖 call order at `0xaa480`–`0xaa55a`), then logs
`Portalized: %i portals, %i zone portals (%i fragments), %i leaves, %i nodes`. One of those passes,
`sub_a93c0` (`0xaa4f8`), is the **zone-setter** and emits `Found %i zones`. So the decoded control
flow is:

```
TestVisibility(Model):
  sub_ac880; sub_a6970
  portalize = sub_aa370:                      # "Zoning" slow-task
     sub_a7760                                # build portal set from PF_Portal node faces (inferred)
     sub_31450 (×3)                           # filter/split bound polys (inferred)
     sub_a9750
     sub_a93c0  -> logs "Found %i zones"       # enumerate leaves, assign each to a zone
     sub_a7400; sub_a8850; sub_a7960; sub_a7e60
     log "Portalized: … leaves, … nodes"
  sub_a6c70
```
The pass *identities* and order are byte-read; the *body* of each pass (how portals are enumerated,
how a leaf is flood-assigned to a zone, how the u64 masks are filled) is **not** disassembled here —
each is a substantial function and a faithful port is a bounded follow-on slice, not closed tonight.

### 8.2 Output fields (📖 field meanings, ✅ §9-validated) — what the passes must produce
- **`Leaves` (`FBspLeaf`)** — one per convex empty region of the finished tree (a node child == -1
  points at a leaf, index stored in the node's `iLeaf[side]`); fields `iZone`, `iPermeating`,
  `iVolumetric` (lighting flood indices), `iExclusive` (u64 lighting mask).
- **`Zones` (`FZoneProperties[NumZones]`)** — `ZoneActor` obj-ref (the `ZoneInfo`/`LevelInfo` actor,
  or 0 for the default zone) + `Connectivity` (u64) + `Visibility` (u64). `NumZones ≤ 64` (mask
  width); zone 0 = the outside/default zone.
- Node `ZoneMask` (u64 @ node+0x10) and `iZone[2]` are set by the flood; `PF_Portal` faces are the
  zone boundaries. *(These field meanings are confirmed by the ✅ byte-exact serializer round-trip and
  the real-map parse — `Model300` in `02_NYC_Bar.dx`: 4 zones, 631 leaves — but the algorithm that
  computes the values is the un-decoded part.)*

### 8.3 First-cut fallback (BUILD AGAINST THIS tonight): single-zone
**Full portalization is NOT required for a valid carved-room build.** A single-zone model is
legitimate and lets the geometry pipeline (N-1..N-4) proceed:
- `NumZones = 0` (or 1 with a null `ZoneActor`); **every leaf `iZone = 0`**; every node `iZone = {0,0}`
  and `ZoneMask` = all-ones (`0xffffffffffffffff`) so nothing is culled.
- `Connectivity`/`Visibility` trivial (a single zone sees itself).
- Leaves are still enumerated from the finished tree (one per `child==-1`), which the build already
  knows — only the zone-assignment/portal-flood is skipped.

This produces a fully collidable, fully rendered single-zone level (correct for interiors that aren't
split by zone portals — the common case). **Multi-zone visibility/connectivity is a bounded follow-on
slice** that decodes `sub_aa370`'s passes; until then a native `materialize` should emit single-zone
and note it. (Zones are a rendering-visibility optimization + a gameplay `ZoneInfo` hook, not a
correctness requirement for solid/void geometry.)

---

## 9. Output mapping — how the build fills the serializer arrays

The proven writer is `bspspike/umodel_serialize.py` (✅ byte-exact round-trip on every real `.dx`
Model). A native build produces these and serializes in this exact order after the 42- (or 57-) byte
UPrimitive prefix:

| Serializer array | Filled by | Contents |
|---|---|---|
| **`Vectors`** (FVector[]) | `bspAddVector` pool (§6.4) | every distinct surf normal + texture U/V basis, deduped (2e-5 / looser). ✅ real: unit normals e.g. `(-0,-0,-1)` |
| **`Points`** (FVector[]) | `bspAddPoint` pool | every distinct vertex + surf base point, deduped (0.002). ✅ real: `(0,0,256)` |
| **`Nodes`** (FBspNode[]) | `bspAddNode` + `SplitPolyList` | plane(f32×4), ZoneMask(u64), NodeFlags(u8), iVertPool, iSurf, iFront/iBack children (mem `[+0x20]/[+0x24]`), iPlane coplanar chain, **iCollisionBound/iRenderBound (ci), iZone[2] (ci), NumVertices (ci), iLeaf[2] (i32)** *(order corrected 2026-07-15 — see §0.2 note + [`50-…`](50-model-ondisk-layout-and-render.md))*. ✅ real node: `plane=(1,0,0,-1512), iSurf=154, iVertPool=0, nVerts=4` |
| **`Surfs`** (FBspSurf[]) | `bspAddNode` surf alloc (§6.4) | Texture ref, PolyFlags(`&0x3cffffff`), pBase→Points, vNormal/vTextureU/vTextureV→Vectors, iActor(owning brush), iBrushPoly, iZone[2](u16), iLightMap. ✅ real surf: `polyFlags=0x8000, pBase/vNormal/vTexU/vTexV=0/0/1/2, iActor=109` |
| **`Verts`** (FBspVert[]) | `bspAddNode` vert pool | per node-vertex: `iVertex`→Points, `iSide` (shared-edge side id). Contiguous per node: `Verts[node.iVertPool .. +NumVertices]` |
| **`NumSharedSides`** (i32) | `bspOptGeom`/refresh | count of shared node edges (T-junction bookkeeping) |
| **`NumZones`** (i32) + **`Zones`** (FZoneProperties[]) | `TestVisibility` (§8) | ZoneActor ref + Connectivity(u64) + Visibility(u64) per zone. **First-cut: `NumZones=0`, single-zone (§8.3)** |
| **`Leaves`** (FBspLeaf[]) | `TestVisibility` (leaf enum from finished tree) | iZone, iPermeating, iVolumetric (ci), iExclusive (u64). **First-cut: one leaf per `child==-1`, all `iZone=0` (§8.3)** |
| raw aux `+0xa8` FLightMesh, `+0xb4` BYTE[] | lighting | **empty for an unlit native build** — emit count 0 (the meshes/vertex-lighting are populated only by a light rebuild, out of scope) |
| raw `+0xc0` FBox[], `+0xcc` INT[], `+0xe4` INT[] | `bspBuildBounds` (§7.4) | `+0xc0` = per-leaf/node bounding `FBox` (6×f32 min/max + 1 BYTE valid); `+0xcc` = `LeafHulls`/`Bound` plane-index list; `+0xe4` = `Leaves`-side bound INT array. Node `iCollisionBound`/`iRenderBound` index these. Synthesize per §7.4; for a first cut a native build may emit **empty bound arrays with node `iCollisionBound=iRenderBound=-1`** (collision then falls back to plane walk — correct but slower; matches a `bspBuildBounds`-skipped state) |
| trailing INT `+0xf0`, `+0xf4` | misc | `NumSharedSides`-adjacent scalars; emit `0` for a fresh build (raw-passthrough today) |

**UPrimitive prefix (42 or 57 bytes):** `ci(None) + FBox(25) + FSphere(16)` = the primitive bound.
For a native build, compute the model's overall AABB (`FBox` = min/max over all Points) and bounding
`FSphere` and emit the 42-byte form (the 57-byte variant carries a 15-byte DeusEx lead block only on
some brush models; the level model uses 42). `umodel_serialize.detect_prefix` disambiguates on read.

---

## 10. What is closed vs residual

**Fully closed (📖 byte-decoded + reproducible via `harness/verify_csg_build.py`, 33/33):**
- The complete pass pipeline + vtable slots (`bspRepartition`=BuildFPolys→MergeCoplanars→bspBuild→
  bspRefresh; the F8 & MAP-REBUILD orderings). §1
- `SplitWithPlane` classify+cut geometry, thresholds, the crossing-vertex lerp. §3
- The CSG leaf-filter: `bspBrushCSG` CsgOper→0x28 mask + Transform+Fix; `FilterEdPoly` recursion incl.
  the 14-vert SplitInHalf guard, per-node `SplitWithPlane`, and the **exact-0.0 coplanar facing
  test**; the **per-CsgOper `cmove` FilterFunc selection** and **ALL FOUR** keep/discard/reverse leaf
  callbacks byte-decoded from their Filter branch tables — `SubtractFunc 0x348c0`, `AddFunc 0x31770`,
  `OutsideFunc 0x32390`, `IntersectFunc 0x339e0` (§4.3 table). §4 — **gap #1 closed**.
- `bspAddNode` node/surf/vert emission, the coplanar-chain walk, the >16-vert split, surf sharing via
  `iLink==NumSurfs`, the `0x3cffffff` PolyFlags mask, `bspAddVector`/`bspAddPoint` pooling. §6.4 —
  **gap #2 node-emission closed**.
- Solidity classes + the portal `~Semisolid|NotSolid` force (§5); the `abutting_subtracts` 11-vs-10
  diagnosis (§6.5).
- Output mapping to every serializer array, validated against `Model300` in `02_NYC_Bar.dx`. §9

**N-2 native-port status (2026-07-15, `uedctl-native/src/{passes,build}.rs`):** the cleanup passes
are ported — `bspMergeCoplanars` (§7.1) is implemented as a **T-junction-aware per-surface
reassembly** (`passes::bsp_merge_coplanars` + `union_group`): CSG world fragments are grouped by
source brush face (owning `actor` + `iBrushPoly`) and each group's coplanar edge-tiling fragments
are unioned into ONE boundary polygon (split every edge at interior verts → cancel internal shared
edges → trace the boundary ring → `RemoveColinears`); distinct surfaces never fuse (golden `d`).
`bspRefresh` (§7.3, drop unreferenced surfs + re-pack the vert pool) and `bspBuildBounds` (§7.4,
empty bounds / `iCollisionBound=iRenderBound=-1`) are wired into the pass order. Surf sharing keys
on brush-face identity so a clipped face is ONE surf across its many nodes. **Result: corpus a/c/d/e
are Tier-S EXACT (full surf-set + node/surf counts); b now matches node COUNT (19) + surf COUNT (11)
exactly** but 5 surfs' per-surf vertex sets still differ. The block is `find_best_split`: it runs a
**split-minimizing deviation** (splits dominate; portal candidates keep the `PortalBias` discount)
rather than the true `Balance=50` heuristic, because `Balance=50` over-splits (case c 12→24) and the
editor only recovers via `bspOptGeom`'s redundant-node removal (below). `bspOptGeom` (§7.2) is NOT
ported.

**Residual (needs a differential editor run or a further slice, NOT more static disassembly):**
- **`bspOptGeom` redundant-node removal (`0x36870`) is the block on EXACT split-distribution
  parity** for b (and f's wall splits). To reproduce the editor's tree the port must run the true
  `Balance=50` heuristic (which over-splits) then trim redundant split nodes — but the trim
  predicate is decoded structurally only (§7.2). A split-minimizing stand-in avoids the trim but
  can't make the editor's "gratuitous" splits (e.g. b's far +X wall split at y=-87.5 by a wedge
  plane), so the per-surf vertex sets diverge. Simple adjacency-based trims were ruled out (they
  drop b's far-wall split, which no surf is adjacent to). Tracked: `board/inbox.md` [spike].
- **Per-CsgOper keep-sets are now byte-decoded (§4.3), NOT canonical-guessed** — the four FilterFuncs
  and both `cmove`s are read from the binary and byte-verified. The one remaining check is a cheap
  confirmation-only differential `MAP REBUILD` (e.g. an add-in-subtract case) to observe the decoded
  Add/Intersect rules in a live build; the decode itself no longer depends on it. *(The prior draft's
  "Add is the documented mirror" caveat is retired — Add's `0x31770` is now read directly, incl. the
  cospatial-facing-in¬semisolid rule.)*
- **Multi-zone portalization (§8) is the largest residual — NOT decoded to port level.**
  `TestVisibility`'s pass skeleton is byte-read (§8.1) but the flood-fill bodies (`sub_aa370`'s ~8
  passes: portal enumeration, leaf→zone assignment, `Connectivity`/`Visibility` u64 fill) are not
  disassembled. **First-cut = single-zone (§8.3), which is valid for a carved room and unblocks
  N-1..N-4.** Multi-zone is a bounded follow-on disassembly slice of `sub_aa370`.
- `bspOptGeom` **T-junction linking** internals (§7.2) are described structurally, not
  instruction-by-instruction. Not needed for solid/void parity; needed for crack-free surf parity —
  a bounded follow-on disassembly of `0x36870`.
- `bspBuildBounds` hull-plane packing (§7.4) — a native build can ship correct-but-slower with empty
  bound arrays (`iCollisionBound=-1`); exact hull reproduction is a bounded follow-on if bit-identical
  bound arrays are ever required (they are regenerable build output, never authored state — §
  design-spec "lighting/BSP are build output").
- Node-PLANE bit-identity across a full real map is gated on the differential harness
  (`bspspike/corpus_oracle.py`) once the leaf-filter port lands; counts + leaf/zone structure remain
  the ship gate (design spec §5 Tier-S).
