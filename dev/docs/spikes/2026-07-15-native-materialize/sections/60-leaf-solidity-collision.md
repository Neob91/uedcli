# Section 60 — BSP leaf solidity & why the player falls through the floor

**Status:** RE spike, root-cause CLOSED + fix spec. **Date:** 2026-07-15.
**Method:** byte-level decode of two real single-box `.dx` Models (`DXOnly.dx` known-good vs our
`NativeCSG.dx`) with `uedcli/native/umodel.py`, plus static disassembly of the **game's**
`System/Engine.dll` collision/zone functions (`capstone`+`pefile`; ImageBase `0x10300000`), plus a
Python simulation of the engine's BSP descent applied to both models.
**Reproduce:** harness in this spike's `harness/`:
`leaf_dump_nodes.py` (node/leaf table), `leaf_disas.py` / `leaf_scan.py` (Engine.dll disasm),
`leaf_fix_classify.py` (the fix applied to a parsed Model), `leaf_descent.py` (engine descent sim).
All RVAs below are file-RVAs at base `0x10300000` unless written as absolute VAs.

### Confidence legend
- ✅ live-verified / byte-exact against a real `.dx`
- 📖 binary-extracted (read out of the compiled game `Engine.dll` this session)

---

## 0. TL;DR — the collision root cause is NOT iLeaf

The pre-spike hypothesis was: *"`finalize_leaves_and_bbox` marks every solid exterior terminal as
the interior leaf 0, so `LineCheck`/`PointCheck` never find solid space."* **Disassembly disproves
that as the cause.** The game's `UModel::LineCheck` / `UModel::PointCheck` **never read `iLeaf`**.
They decide solidity from **`FBspNode::IsCsg()`** — a test on **`NodeFlags`** and `NumVertices` — and
descend by re-deriving each node's front/back side from the plane. So the pawn falls through the
floor for **two** reasons, *neither of which is `iLeaf`*:

1. **`NodeFlags` carries `NF_IsNew` (0x20) on every node.** 📖 `FBspNode::IsCsg` (`Engine.dll
   0xf68b0`) returns "solid CSG splitter" **only if `(NodeFlags & (NF_NotCsg|NF_IsNew)) == 0`**.
   Our nodes are `0x20` → every node is treated as **non-solid** → the collision walk never enters
   solid. (`DXOnly` ships `NodeFlags = 0x00`.)
2. **Front/back children are stored in the wrong slots (topology inversion).** 📖 The engine indexes
   `iChild[side]` with **`side = 1` for the FRONT (positive, `PlaneDot ≥ 0`) halfspace** (proven from
   `UModel::PointRegion` `0xf5db0` and `UModel::LineCheck` `0xf3560`). So the FRONT child **must** live
   in `iChild[1]` (serial `+0x24`, our field `i_back`). Our build puts the front child in
   `i_front` (`+0x20` = `iChild[0]`). The engine therefore descends our tree **inverted**: an
   interior segment hits a leaf at node 0 and **never reaches the floor plane** → no floor hit.

`iLeaf` is still **wrong** and must be fixed — but for **zone/region correctness** (`PointRegion`),
not to stop the fall. **A collision hull (`LeafHulls`/`iCollisionBound`) is NOT required**: with
`iCollisionBound = -1` the engine skips the hull test (📖 guard `0xf1bff`) and uses the node walk.

**The fix (one pass, `build.rs :: finalize_leaves_and_bbox`)**: put the front child in `iChild[1]`,
clear `NF_IsNew`, and set `iLeaf` by front=empty / back=solid. Applied to the parsed `NativeCSG.dx`
Model this reproduces `DXOnly`'s node/flag/leaf/zone table **exactly** (§3) and makes every region
resolve correctly in the engine descent sim (§4). **iLeaf alone is NOT sufficient; the load-bearing
fixes are `NodeFlags` + front/back slot.**

---

## 1. Ground truth — the two Models side by side (✅)

`leaf_dump_nodes.py DXOnly.dx NativeCSG.dx`. Serial `FBspNode` field names per section 50:
`iChild[0]=+0x20`(parser `i_front`), `iChild[1]=+0x24`(parser `i_back`), `NodeFlags=+0x37`,
`iCollisionBound=+0x2c`, `iRenderBound=+0x30`, `iZone=+0x34/35`, `iLeaf[2]` = trailing i32 pair.

**`DXOnly.dx`** (a single subtracted cube ±512; player stands on the floor):

```
 ni | plane(n, w)          | nf  | iChild0 iChild1 | iColl iRend | iZone | iLeaf
  0 | (0,0,-1, -512)       |0x00 |   -1      1     |  52     4   | 0, 1  | (-1,-1)
  1 | (0,0, 1, -512)       |0x00 |   -1      2     |  44     3   | 0, 1  | (-1,-1)
  2 | (0,-1,0, -512)       |0x00 |   -1      3     |  34     2   | 0, 1  | (-1,-1)
  3 | (0, 1,0, -512)       |0x00 |   -1      4     |  24     1   | 0, 1  | (-1,-1)
  4 | (-1,0,0, -512)       |0x00 |   -1      5     |  12     0   | 0, 1  | (-1,-1)
  5 | ( 1,0,0, -512)       |0x00 |   -1     -1     |   0    -1   | 0, 1  | (-1, 0)
leaves=[iZone=1]  zones=2  num_shared_sides=16
```

**`NativeCSG.dx`** (our build; single subtract, cube ±256 X/Y ±128 Z; **pawn falls to z≈-2e6**):

```
 ni | plane(n, w)          | nf  | iChild0 iChild1 | iColl iRend | iZone | iLeaf
  0 | (-1,0,0, -256)       |0x20 |    1     -1     |  -1    -1   | 0, 1  | (-1, 0)
  1 | ( 1,0,0, -256)       |0x20 |    2     -1     |  -1    -1   | 0, 1  | (-1, 0)
  2 | (0,-1,0, -256)       |0x20 |    3     -1     |  -1    -1   | 0, 1  | (-1, 0)
  3 | (0, 1,0, -256)       |0x20 |    4     -1     |  -1    -1   | 0, 1  | (-1, 0)
  4 | (0,0,-1, -128)       |0x20 |    5     -1     |  -1    -1   | 0, 1  | (-1, 0)
  5 | (0,0, 1, -128)       |0x20 |   -1     -1     |  -1    -1   | 0, 1  | ( 0, 0)
leaves=[iZone=1]  zones=2  num_shared_sides=0
```

Two structural differences jump out and are the whole story:
- **`nf`**: `DXOnly = 0x00` everywhere; **ours = `0x20` (`NF_IsNew`) everywhere.**
- **which child recurses**: `DXOnly` recurses through **`iChild[1]`** (`iChild[0]` is the `-1` solid
  terminal); **ours recurses through `iChild[0]`** (`iChild[1]` is the `-1` terminal). **Mirror image.**
- `iLeaf`: `DXOnly` puts leaf 0 on **one** terminal only (node 5, `iChild[1]`); ours puts leaf 0 on
  **every** `iChild[1]==-1` terminal (the blanket bug) — but see §5: this is a *zone* bug, not the fall.

---

## 2. What actually drives collision (📖 DEFINITIVE, from `Engine.dll`)

### 2.1 `FBspNode::IsCsg()` — the solidity predicate (`0xf68b0`)

```
0xf68b0  mov  al, [ecx+0x36]        ; NumVertices
0xf68b3  test al,al  / jbe .no      ; NumVertices==0 -> not a splitter
0xf68b7  mov  eax, [esp+4]          ; ExtraNodeFlags
0xf68bb  mov  dl,  [ecx+0x37]       ; NodeFlags
0xf68be  or   al, 0x21              ; force NF_NotCsg(0x01) | NF_IsNew(0x20)
0xf68c0  test al, dl / jne .no      ; (ExtraFlags|0x21) & NodeFlags != 0  -> NOT solid
0xf68c4  mov  eax, 1 ; ret 4        ; else SOLID splitter
.no: xor eax,eax ; ret 4
```

**Blocking ⇔ `NumVertices>0 && (NodeFlags & (0x01|0x20|ExtraNodeFlags)) == 0`.** Our
`NodeFlags = 0x20` ⇒ `IsCsg` returns 0 ⇒ **no node blocks** ⇒ collision walk sees only empty space.
This exact predicate is inlined in both collision recursions:
- `UModel::LineCheck` box/line recursion `0xf3560`: `0xf3733`–`0xf373e` and `0xf3798`–`0xf37a1`.
- `UModel::PointCheck` recursion `0xf19b0`: `0xf1b53`–`0xf1b5d` and `0xf1b94`–`0xf1b9f`.

### 2.2 The front/back convention — `iChild[1]` is FRONT (`0xf5db0`, `0xf3560`)

`UModel::PointRegion` (`0xf5db0`) descent:
```
0xf5e3d fsub [ecx+0xc]              ; PlaneDot = N·P − W
0xf5e40 fcomp [0x10429838]          ; threshold = 0.0 (📖 read from .rdata)
0xf5e48 test ah,1 / jne .neg        ; PlaneDot < 0 -> side 0
0xf5e4d mov esi,1                    ; PlaneDot >= 0 -> side 1  (FRONT)
0xf5e99 mov edi,[ecx+esi*4+0x20]     ; next = iChild[side]   (+0x20 + side*4)
```
`side=1` (front/positive) ⇒ `iChild[1]` at `+0x24`. `UModel::LineCheck` agrees: both-front →
`[esi+0x24]` (`0xf3750`), both-back → `[esi+0x20]` (`0xf37ac`), split → `[esi+edi*4+0x20]`
(`0xf3924`). **So the engine requires: `iChild[1]`(`+0x24`) = FRONT/positive child, `iChild[0]`
(`+0x20`) = BACK/negative child, and `iLeaf[k]` pairs with `iChild[k]`.**

**Proof this convention is right (and ours is inverted):** `DXOnly` is known-good. Descend its
interior point `(0,0,0)`: at every node `PlaneDot = +512 ≥ 0` → front → `iChild[1]` → node 1,2,…,5 →
`iChild[1] = -1` → `iLeaf[1] = 0` = the interior leaf. ✅ If the convention were `iChild[0]=front`,
the same point would take `iChild[0] = -1` at node 0 → `iLeaf[0] = -1` = **solid**, i.e. the engine
would think the room interior is solid — which contradicts a map you can stand in. So `iChild[1]=front`
is the only convention consistent with the shipping map. Our `NativeCSG` recurses through `iChild[0]`
⇒ **inverted** ⇒ the engine mis-descends it (§4).

### 2.3 The collision hull is OPTIONAL (`0xf1bff`)

`UModel::PointCheck` leaf-hull test:
```
0xf1bfb mov ecx,[edx+ecx+0x2c]      ; iCollisionBound
0xf1bff cmp ecx,-1 / je 0xf2baf     ; == -1  ->  SKIP the whole LeafHulls test
0xf1c08 mov edx,[eax+0xcc]          ; Model.LeafHulls   (only if iCollisionBound != -1)
```
With `iCollisionBound = -1` (our build, and correct per section 50), the `LeafHulls` convex-hull
test is skipped and solidity comes from the node walk (§2.1). `UModel::LineCheck`'s recursion
(`0xf3560`) reads **no** `LeafHulls`/`iCollisionBound` at all. **So no collision hull needs to be
built for the pawn to stand.** (`DXOnly` ships real hulls purely as a query optimisation.)

---

## 3. The fix reproduces `DXOnly` exactly (✅)

`leaf_fix_classify.py` applies, to every final node:

1. **relocate children to engine slots** — put the FRONT (positive) child in `iChild[1]`(`i_back`),
   the BACK child in `iChild[0]`(`i_front`). In our build the front child is currently in `i_front`,
   so this is an **exchange `i_front ↔ i_back`**.
2. **`iLeaf`** — `iLeaf[0]` (back/solid side) `= -1` always; `iLeaf[1]` (front/empty side)
   `= 0` (the single interior leaf) when that front child is terminal (`== -1`), else `-1`.
3. **clear `NF_IsNew`** — `node_flags &= ~0x20`.
4. **`iZone = (0,1)`** (back = solid = zone 0, front = interior = zone 1); `iCollision/iRenderBound
   = -1`.

Result on `NativeCSG.dx` (`leaf_fix_classify.py` output):
```
 ni | iChild0 iChild1 | nf  | iLeaf   | iZone
  0 |   -1      1      |0x00 | (-1,-1) | (0,1)
  1 |   -1      2      |0x00 | (-1,-1) | (0,1)
  2 |   -1      3      |0x00 | (-1,-1) | (0,1)
  3 |   -1      4      |0x00 | (-1,-1) | (0,1)
  4 |   -1      5      |0x00 | (-1,-1) | (0,1)
  5 |   -1     -1      |0x00 | (-1, 0) | (0,1)
invariants: interior_leaf_terminals=1  front_solid_terminals=0  back_slots_with_leaf=0  NF_IsNew=0
```
This is **structurally identical** to the `DXOnly` table in §1 (same child topology, `nf=0`,
`iLeaf=(-1,-1)` except the one interior terminal `(-1,0)`, `iZone=(0,1)`). The `DXOnly` invariants are
byte-identical: `interior_leaf_terminals=1, front_solid_terminals=0, back_slots_with_leaf=0,
NF_IsNew=0`.

## 4. Engine descent sim — before vs after (✅)

`leaf_descent.py` simulates the proven descent (`side = PlaneDot ≥ 0 ? iChild[1] : iChild[0]`) on the
parsed models (box ±256 X/Y, ±128 Z):

```
NativeCSG BEFORE fix                       NativeCSG AFTER fix
  interior(0,0,0)      -> leaf0 path[0]      interior(0,0,0)      -> leaf0 path[0,1,2,3,4,5]
  below floor(0,0,-200)-> leaf0 path[0]      below floor(0,0,-200)-> SOLID path[0,1,2,3,4,5]
  outside +X(300,0,0)  -> leaf0 path[0,1]    outside +X(300,0,0)  -> SOLID path[0]
  above ceiling(0,0,300)-> leaf0 path[0]     above ceiling(0,0,300)-> SOLID path[0,1,2,3,4]
```

BEFORE: **all space resolves to the interior leaf** and the walk short-circuits at node 0 (inversion)
— every region looks empty, nothing is solid → fall-through. AFTER: only the interior is empty; below
the floor / outside the walls / above the ceiling is SOLID, reached by the full plane walk.

> **What this sim does and doesn't show.** `leaf_descent.py` is a `PointRegion`-style point walk that
> labels each terminal cell via `iLeaf` — it demonstrates the *topology* is now correct (interior
> reachable, exterior classified solid). It is NOT a `LineCheck` box-sweep. The *"pawn stops on the
> floor"* conclusion rests on the **separate** `IsCsg` decode (§2.1): once topology is correct, the
> down-sweep reaches the floor node (`NumVertices>0`, `NodeFlags=0` after the fix ⇒ `IsCsg` true), and
> `LineCheck`'s front→back plane crossing at that CSG node is what it reports as a solid hit. The two
> pieces of evidence together (descent sim for topology + `IsCsg` decode for the block) are what
> support the fix; the final in-engine confirmation (§7) is now ✅ live-verified (`phys=PHYS_Walking`,
> `z=-134` stable).

---

## 5. Why `iLeaf` still must be fixed (zones, not the fall)

`iLeaf` is unread by `LineCheck`/`PointCheck`, but `UModel::PointRegion` (`0xf5db0`) walks to a
terminal and reads **both** `node.iZone[side]` (📖 `0xf5ef2`, `mov al, byte ptr [eax+esi+0x34]` —
a **BYTE** read at `+0x34`, `side` stride **1** (`esi=side`; the node base comes from `shl eax,6` ==
`node*0x40`), NOT a `*4`-scaled read: `iZone[0..1]` are the adjacent bytes `+0x34`/`+0x35`) for the
zone byte **and** `node.iLeaf[side]` (📖 `0xf5ee7`, `mov edx, [ecx+edx*4+0x38]` — an **i32** read,
`side` stride **4**) as the leaf index the point lands in —
together giving the region's zone/leaf (gravity, water, `ZoneInfo`, sound). With the blanket bug
(`iLeaf[1]=0` on every terminal) a point in solid would report the interior leaf; with the inversion,
`PointRegion` for the interior short-circuits at node 0.
Fixing `iLeaf` per §3 gives every interior point zone 1 and every solid point "no leaf" (zone 0),
matching `DXOnly`. It is required for a correct model and future portalization — just not for the
"stops falling" symptom, which is `NodeFlags` + topology.

**Answer to the spike's part-1 question (propagate `csg.rs leaf_outside` vs classify independently):**
do **neither** in a heavyweight way. The final tree already encodes solidity **locally in each node's
surface normal**: every surviving CSG face's normal points *from solid toward empty* (invariant of
subtract/add), so the FRONT (positive) side of any CSG node is empty and the BACK side is solid, and
because a BSP leaf cell is homogeneous (no surface inside it), the bounding node's orientation
classifies the whole terminal cell. Hence **front terminal → empty leaf, back terminal → solid (`-1`)**,
read straight off the node — no `leaf_outside` propagation (it lives on the transient per-brush
classify trees, a different partition) and no point-sampling needed. This rule **generalises to
arbitrary CSG** (multiple adds/subtracts, non-convex): only the *single* leaf 0 is single-zone-specific
— multi-room needs the deferred `TestVisibility` leaf/zone flood to hand out distinct leaves. Point-in-
CSG sampling is a valid fallback/validator but is unnecessary here.

---

## 6. Fix spec — `build.rs :: finalize_leaves_and_bbox` (concrete, implementable)

Replace the current per-node body (build.rs ~356–368). The build's internal convention
(`split_poly_list` pushes `Split::Front` → `NODE_FRONT` → `i_front`, and every built node carries
`NF_IsNew` via `derive_nf`/the `NF_IS_NEW` base) is unchanged; we correct it **only on the final level
Model**, at finalize. Do **not** change `model_write::put_node` order or `umodel.py` (that would break
the `DXOnly` round-trip and the §6-gate-5 oracle — the on-disk byte positions are already correct).

```rust
const NF_IS_NEW: u8 = 0x20; // already defined at top of build.rs
const EMPTY_LEAF: i32 = 0;  // the single interior leaf (leaves[0], zone 1)

for ni in 0..model.nodes.len() {
    let n = &mut model.nodes[ni];

    // (1) TOPOLOGY: the engine indexes iChild[1] (serial +0x24 == our `i_back`) for the FRONT
    //     (positive, PlaneDot>=0) halfspace and iChild[0] (+0x20 == `i_front`) for BACK.
    //     Our build put the FRONT child in `i_front`; exchange so FRONT lands in `i_back`.
    //     (Evidence: PointRegion 0xf5db0, LineCheck 0xf3560 — section 60 §2.2.)
    std::mem::swap(&mut n.i_front, &mut n.i_back);
    // after the swap: i_front = BACK/negative child, i_back = FRONT/positive child.

    // (2) iLeaf pairs with iChild slot: [0]=BACK/solid, [1]=FRONT/empty.
    //     Every CSG face normal points solid->empty, so the FRONT terminal cell is empty
    //     (gets the interior leaf) and the BACK terminal cell is solid (-1). A non-terminal
    //     side recurses -> -1. (section 60 §5.)
    n.i_leaf = [-1, if n.i_back == -1 { EMPTY_LEAF } else { -1 }];

    // (3) NodeFlags: clear NF_IsNew so FBspNode::IsCsg() treats a solid wall as a blocker
    //     (else every node is non-solid and the pawn falls through). Keep the other derived
    //     bits (NF_NotCsg for genuine non-solid/portal faces must survive). (section 60 §2.1.)
    n.node_flags &= !NF_IS_NEW;

    // (4) zones + bounds (unchanged intent; now consistent with the corrected slots).
    n.i_zone = [0, 1];          // iChild[0]=back=solid=zone 0 ; iChild[1]=front=interior=zone 1
    n.zone_mask = 0b10;         // interior in zone 1
    n.i_collision_bound = -1;   // no LeafHulls -> engine skips the hull test (0xf1bff)
    n.i_render_bound = -1;      // OccludeBsp bound-guard skip (section 50)
}
```

Leave the rest of `finalize_leaves_and_bbox` (leaves/zones arrays, bbox) as is: `leaves = [{iZone:1}]`,
`zones = [solid, interior]`, `NumZones = 2`. `passes::bsp_build_bounds` (runs after) re-asserts the
`-1` bounds — harmless.

**Notes / scope:**
- The exchange is safe: child *indices* are unchanged, only which slot holds each subtree moves;
  `i_plane` (coplanar chain) and the per-node vert pool are untouched. `bsp_refresh` runs *before*
  finalize; `bsp_build_bounds` runs after and ignores front/back.
- **Coplanar-chain nodes** (multi-fragment faces sharing a plane; added via `NODE_PLANE`) have
  `i_front==i_back==-1` and would get `iLeaf[1]=EMPTY_LEAF`. The single room has none (6 distinct
  planes). For the multi-brush slice, verify coplanar siblings against an editor golden before relying
  on this — flagged for the deferred `TestVisibility` port.
- **Multi-room is single-zone (guarded, not silent).** `finalize` emits exactly TWO zones (0=solid,
  1=one interior) regardless of geometry, so a level with several disjoint rooms / a `ZoneInfo` / a
  `PF_Portal` brush collapses to one interior zone (per-room gravity/water/sound/`ZoneInfo` wrong).
  This never blocks load or a human playthrough, so `materialize._multizone_warning` (in
  `native/materialize.py`) emits a **warning** (heuristic: >1 Subtract brush, a `PF_Portal` brush, or
  a `*ZoneInfo` actor) rather than failing — the real fix is the deferred `TestVisibility` leaf/zone
  flood. Test: `test_multizone_warning_fires_for_multi_room_and_is_quiet_for_single`.
- **Semisolid/portal faces**: `derive_nf` sets `NF_NotCsg` for `PF_NotSolid`; those nodes stay
  non-blocking (correct). Full semisolid solidity is out of single-room scope.
- **Scope — this fixes the real build path only.** The corrected pass is `build_geometry_from_brushes`
  → `finalize_leaves_and_bbox`. `build.rs::carved_box` / `materialize.py::carved_box_model` (the M0
  Python-parity fixtures) bypass `finalize` and build 6 unlinked nodes; they are serializer
  cross-check fixtures, not a shipping build, so they neither need nor get the fix.
- **`NumSharedSides`** ships `0` for us vs `DXOnly`'s `16` (per-node `iSide` links from `bspOptGeom`,
  deferred — section 50 §2). That is a vertex-pool/T-junction concern, **not** collision: neither
  `LineCheck`/`PointCheck` nor `PointRegion` index the side pool. Out of scope for this fix.

---

## 7. Answers to the spike questions

- **Is fixing `iLeaf` alone sufficient for collision?** **No.** `LineCheck`/`PointCheck` never read
  `iLeaf`. The load-bearing collision fixes are **(a) clear `NF_IsNew`** and **(b) put the FRONT child
  in `iChild[1]`**. `iLeaf` must still be corrected, but for `PointRegion`/zone correctness.
- **Is a collision hull (`LeafHulls`/`iCollisionBound`) required?** **No.** `iCollisionBound = -1`
  makes `PointCheck` skip the hull test; `LineCheck` never uses it. The node-plane walk is the
  fallback and is correct.
- **`NumZones`/`Zones`/`leaf.iZone`/`zone_mask`?** Unchanged and correct after the topology fix:
  `NumZones=2`, `leaves[0].iZone=1`, node `iZone=(0,1)`, `zone_mask=0b10`. These match `DXOnly` once
  FRONT sits in `iChild[1]`.
- **How is per-terminal solidity obtained?** From the bounding node's **surface-normal orientation**
  (front=empty, back=solid), read straight off the final tree — no `leaf_outside` propagation, no
  point-sampling. Correct for the single room and general CSG; only the single interior leaf is
  single-zone-specific.

**Residual risk / open item — ✅ CLOSED (live-verified 2026-07-15).** The conclusion was from static
disassembly + a descent simulation, both byte-anchored to the known-good `DXOnly`; the final gate was a
**live** run. That run is now done: with the §6 fix landed in `build.rs::finalize_leaves_and_bbox` and
`NativeCSG.dx` regenerated, the live game (`bin/uplayctl session start --map NativeCSG` →
`GetPlayerPosition`) reports **`phys=PHYS_Walking`, `speed=0`, `z=-134` STABLE** (was `phys=PHYS_Falling`,
`z≈-2,000,000`). The pawn rests on the floor and the render stays clean. Pinned by
`test_finalize_collision_topology_matches_dxonly`. **Remaining (separate slices):** multi-room leaf/zone
(deferred `TestVisibility`) and wall/ceiling collision not separately exercised (same BSP mechanism as
the verified floor).
