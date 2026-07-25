# Section 50 — `UModel` on-disk layout (FBspNode/FBspVert) & the `OccludeBsp` render crash

**Status:** RE spike, root-cause CLOSED + fix spec. **Date:** 2026-07-15.
**Method:** byte-level hand-decode of two real single-box `.dx` Models (known-good `DXOnly.dx`
vs our native `NativeCSG.dx`) + static disassembly of the **game's** `Render.dll`
(`capstone`+`pefile`; ImageBase `0x10b00000`). All RVAs below are file-RVAs at that base.
**Reproduce:** the decode/dump scripts are `rawdump.py` / `trailingdump.py` (byte layout) and the
`Render.dll` disasm one-liners in this doc; parser under test is
`uedctl/native/umodel.py`, writer `uedctl-native/src/model_write.rs`.

### Confidence legend
- ✅ live-verified / byte-exact against a real `.dx`
- 📖 binary-extracted (read out of the compiled `Render.dll` this session)

---

## 0. TL;DR — the root cause and the fix

Our native `FBspNode` writer has **two serialized index-pairs mislabeled and cross-wired**. The
byte *positions* are correct (the writer round-trips byte-exact), but `finalize_leaves_and_bbox`
fills them **by the wrong names**, so on disk:

- the **leaf markers** we computed land in the **`iCollisionBound`/`iRenderBound`** slots, and
- the real **`iLeaf[0]`/`iLeaf[1]`** slots stay `-1`.

Result: every node ships with **`iRenderBound = 0`** while the model's **`Bounds` array is empty
(count 0)**. The renderer's `URender::OccludeBsp` does `if(iRenderBound!=-1) BoundVisible(&Model.Bounds[iRenderBound])`
— with `iRenderBound=0` it indexes element 0 of a **null** `Bounds.Data` pointer → access
violation in `BoundVisible`, caught per-frame by `DrawWorld`'s guard → *"Anomalous singularity"*.

**Fix (load-bearing):** write the **leaf** indices into the real `iLeaf` slots and set
`iCollisionBound = iRenderBound = -1`. The `-1` makes `OccludeBsp` **skip** the bound test
entirely (📖 guard at `Render.dll 0x17adb`), so **no `Bounds` array is needed at all** — exactly
what §7.4 (section 10) predicted ("empty bounds + `iCollisionBound=iRenderBound=-1` is correct,
just slower"). This is a `build.rs`/`model_write.rs` field-naming fix; the on-disk byte positions
do not change.

---

## 1. `FBspNode` — exact byte layout in DX v68 (✅ hand-decoded)

The parser (`umodel._parse_node`) already reads the correct byte *boundaries* (it round-trips
`DXOnly` byte-exact), but four of its field **names are wrong**. Here is the ground-truth layout,
proven by hand-decoding `DXOnly.dx` node[0] below. Serialized element size for this map = **43
bytes**.

| # | Serial field (REAL UE1 name) | Encoding | mem off | `umodel.py` parser name | Correct? |
|---|---|---|---|---|---|
| 1 | `Plane` (X,Y,Z,W) | 4×f32 (16 B) | `+0x00` | `plane` | ✅ |
| 2 | `ZoneMask` | u64 (8 B) | `+0x10` | `zone_mask` | ✅ |
| 3 | `NodeFlags` | **BYTE** (1 B) | `+0x37` | `node_flags` | ✅ |
| 4 | `iVertPool` | ci | `+0x18` | `i_vert_pool` | ✅ |
| 5 | `iSurf` | ci | `+0x1c` | `i_surf` | ✅ |
| 6 | `iChild[0]` (a.k.a. iFront/iBack) | ci | `+0x20` | `i_front` | ✅ (position) |
| 7 | `iChild[1]` (a.k.a. iBack/iFront) | ci | `+0x24` | `i_back` | ✅ (position) |
| 8 | `iPlane` (coplanar chain) | ci | `+0x28` | `i_plane` | ✅ |
| 9 | **`iCollisionBound`** | ci | `+0x2c` | `i_leaf[0]` | ❌ **WRONG NAME** |
| 10 | **`iRenderBound`** | ci | `+0x30` | `i_leaf[1]` | ❌ **WRONG NAME** |
| 11 | `iZone[0]` | ci | `+0x34` | `i_zone[0]` | ✅ |
| 12 | `iZone[1]` | ci | `+0x35` | `i_zone[1]` | ✅ |
| 13 | `NumVertices` | ci | `+0x36` | `num_vertices` | ✅ |
| 14 | **`iLeaf[0]`** | **i32** (fixed 4 B) | `+0x38` | `i_collision_bound` | ❌ **WRONG NAME** |
| 15 | **`iLeaf[1]`** | **i32** (fixed 4 B) | `+0x3c` | `i_render_bound` | ❌ **WRONG NAME** |

**The two cross-wired pairs:**
- parser `i_leaf[0..1]` (the ci pair, fields 9–10) is really **`iCollisionBound`, `iRenderBound`**;
- parser `i_collision_bound`/`i_render_bound` (the trailing i32 pair, fields 14–15) is really **`iLeaf[0]`, `iLeaf[1]`**.

`iZone` (fields 11–12) is, despite sitting between them, already named correctly.

### 1.1 Hand-decode of `DXOnly` node[0] (✅ raw bytes)

Raw 43 bytes at body offset 213:
```
00 00 00 80  00 00 00 80  00 00 80 bf  00 00 00 c4   Plane = (-0, -0, -1, -512)
02 00 00 00 00 00 00 00                               ZoneMask = 0x2
00                                                    NodeFlags = 0
00                                                    iVertPool = 0            (ci)
00                                                    iSurf = 0                (ci)
81                                                    iChild[0] = -1           (ci)  [parser i_front]
01                                                    iChild[1] = 1            (ci)  [parser i_back]
81                                                    iPlane = -1              (ci)
34                                                    iCollisionBound = 52     (ci)  [parser i_leaf[0]]
04                                                    iRenderBound = 4         (ci)  [parser i_leaf[1]]
00                                                    iZone[0] = 0             (ci)
01                                                    iZone[1] = 1             (ci)
04                                                    NumVertices = 4          (ci)
ff ff ff ff                                           iLeaf[0] = -1            (i32) [parser i_collision_bound]
ff ff ff ff                                           iLeaf[1] = -1            (i32) [parser i_render_bound]
```

**Proof the names are right, across all 6 `DXOnly` nodes:**
- field 9 (`iCollisionBound`) = `52,44,34,24,12,0` — descending offsets into the **`LeafHulls` INT
  array** (count 60, §3): impossible as leaf indices (only 1 leaf exists), exactly a per-node hull
  run-start.
- field 10 (`iRenderBound`) = `4,3,2,1,0,-1` — indices into the **`Bounds` FBox array** (count 5,
  §3): `max=4 < 5` ✅, and node[5] = `-1` proves `-1` ("no bound") is a legal value.
- fields 14–15 (`iLeaf`) = `(-1,-1)` on nodes 0–4 and **`(-1, 0)` on node[5]** — the single
  carved room's interior is leaf 0, attached to the one terminal child of the deepest node. This
  is precisely "1 leaf, on exactly one child slot", which cannot be true of fields 9–10.

### 1.2 The child pair & the interior leaf (naming caveat)

`iChild[0]`=`+0x20`, `iChild[1]`=`+0x24`; `iLeaf[k]` pairs with `iChild[k]`. In `DXOnly` the tree
is a linear chain: each node's `iChild[0]`=`-1` (terminates) and `iChild[1]`=next node (or `-1` at
node[5]). Only node[5]'s second child terminates into the interior → `iLeaf[1]=0`; every other
terminal child is solid space → `iLeaf=-1`.

The literal *names* "front" vs "back" for the two child slots are version-ambiguous and **not
load-bearing for the fix** — keep the parser's positional `i_front`/`i_back`. What matters:
`iLeaf[k]` must be the leaf index for the child slot `k` that terminates into an **empty** region,
and `-1` for a slot that terminates into **solid** (or that has a child node). Our native tree
chains through the *other* child slot than `DXOnly` (diff item #4); that is a benign
different-but-valid partition **for RENDER** **provided** each node's `iChild`/`iLeaf` assignment is
consistent with its own `Plane` — it is not the render crash.
> ⚠ **But it IS the COLLISION bug (see `sections/60-leaf-solidity-collision.md`).** The engine's
> `UModel::LineCheck`/`PointRegion` require the FRONT (positive `PlaneDot`) child in **`iChild[1]`**
> (`+0x24`); our build puts it in `iChild[0]`, so the collision descent runs inverted and the pawn
> falls through the floor. "Benign different-but-valid partition" is true only of the *render* walk
> (which visits both children); it is NOT slot-agnostic for collision. Fixed in
> `finalize_leaves_and_bbox` by exchanging the slots (§60 §6).

---

## 2. `FBspVert` layout & `NumSharedSides` (✅)

`FBspVert` serializes as **`ci(iVertex)` + `ci(iSide)`** (parser `_parse_vert` — correct). Node
`n` owns `Verts[n.iVertPool .. +NumVertices]`.

- `iVertex` → index into `Points`.
- `iSide` → shared-edge id from `bspOptGeom` (§7.2, section 10); `-1` = unlinked.
- `Model.NumSharedSides` (i32, after the Verts array) = the count of allocated side ids.

**Our build leaves every `iSide=-1` and `NumSharedSides=0`** (diff items #1, #2-`numSharedSides`)
because `bspOptGeom` is deferred. This is **not** the crash — sidelinks only remove T-junction
seams; the renderer never indexes an empty side pool when `iSide=-1`. `DXOnly`'s 48-entry Verts
pool vs our 24 (diff item #5) is likewise benign: only the 24 entries referenced by
`node.iVertPool` are read; `DXOnly`'s extra 24 (all `iSide=-1`, duplicate vertices) are an
un-compacted editor tail the renderer never touches.

---

## 3. Trailing `UModel` arrays after `Zones` (✅ decoded, real names)

Serial order after the `Zones` block, with our parser's placeholder skip-name → **real UE1 name**,
and the observed counts:

| Serial slot | Parser skip-name | **Real name** | Encoding | DXOnly | Ours | Needed to render? |
|---|---|---|---|---|---|---|
| after Zones | `field_0x54` | **`Polys`** (UPolys obj-ref) | ci | `19` (an export) | `0` (null) | No — editor-only source polys |
| a8 | `_skip_a8` | **`LightMap`** (`TArray<FLightMapIndex>`) | ci count, 32 B/elem | 6 | 0 | No (unlit) |
| b4 | `_skip_bulk_bytes` | **`LightBits`** (`TArray<BYTE>`) | ci count + bytes | 0 | 0 | No (unlit) |
| c0 | `_skip_c0` | **`Bounds`** (`TArray<FBox>`) | ci count, **25 B/elem serial (28 B in mem)** | **5** | **0** | **only if a node's `iRenderBound != -1`** |
| cc | `_skip_i32_raw` | **`LeafHulls`** (`TArray<INT>`) | ci count + INT×n | **60** | **0** | only if a node's `iCollisionBound != -1` |
| Leaves | (parsed) | `Leaves` (`TArray<FBspLeaf>`) | ci count, per §…​ | 1 | 1 | yes (interior leaf) |
| e4 | `_skip_e4` | trailing INT array (portal/leaf-node list; unidentified) | ci count + ci×n | 4 (`[4,3,5,0]`) | 0 | No — empty tolerated (map loads + player spawns) |
| tail | trailing i32×2 | `RootOutside`, `Linked` | i32×2 | `0,0` | `0,0` | matches |

**Key finding:** the game **loads and spawns fine with all of `Polys/LightMap/LightBits/Bounds/
LeafHulls/e4` empty** (our `NativeCSG.dx` did). The renderer only *reads* `Bounds` when a node's
`iRenderBound != -1`. So an empty `Bounds` array is legal — **as long as every `iRenderBound` is
`-1`.** Our bug is that they are `0`, not that the array is empty.

`Render.dll` loads the `Bounds` base from **`[Model + 0xc0]`** (📖 `0x17b50`) and indexes it with
FBox stride 28 (`iRenderBound*7*4`, 📖 `0x17b41`–`0x17b56`) — confirming `+0xc0` == the `Bounds`
member and matching the 25-B serial / 28-B mem `FBox`.

---

## 4. Root cause — the `OccludeBsp` "Anomalous singularity" (📖 DEFINITIVE)

### 4.1 The guard, byte-decoded from `Render.dll`

`URender::OccludeBsp` (export thunk `0x10f0` → real `0x173d0`), per-node bound test at
**`0x17adb`** (`ebx` = `FBspNode*`):

```
0x17adb: cmp dword ptr [ebx + 0x30], -1     ; if (Node.iRenderBound == INDEX_NONE)
0x17adf: je   0x17c1a                        ;     -> SKIP the bound test (node stays visible)
   ... (frustum/zone predicate) ...
0x17b41: mov eax, dword ptr [ebx + 0x30]     ; eax = iRenderBound
0x17b44: lea edi, [eax*8]                     ; \
0x17b4b: sub edi, eax                          ;  > edi = iRenderBound * 7
0x17b4d: mov eax, dword ptr [ebp - 0x60]      ; eax = Model
0x17b50: mov eax, dword ptr [eax + 0xc0]      ; eax = Model->Bounds.Data   (+0xc0)
0x17b56: lea eax, [eax + edi*4]               ; eax = &Bounds[iRenderBound]  (stride 28 = sizeof FBox)
0x17b59: push eax                              ; arg FBox*
0x17b5a: push esi                              ; arg FSceneNode*
0x17b5b: call dword ptr [edx + 0x80]          ; virtual -> URender::BoundVisible
```

`node+0x30` is `iRenderBound` (§1). With our on-disk `iRenderBound = 0` and `Bounds.Data = NULL`
(empty `TArray`), `0x17b50` loads `NULL`, `0x17b56` computes `&NULL[0]`, and `BoundVisible`
dereferences that FBox's floats → access violation. That AV is the exact reported stack:
`URender::BoundVisible` → `URender::OccludeBsp` → `URender::OccludeFrame`, caught each frame by
`URender::DrawWorld`'s `__try/__except` → `Log: Anomalous singularity in URender::DrawWorld`.

### 4.2 Why our `iRenderBound` is `0` — the field cross-wire

`finalize_leaves_and_bbox` (`build.rs`) sets `node.i_leaf = [fr==-1?0:-1, bk==-1?0:-1]` and never
touches `i_collision_bound`/`i_render_bound` (they stay `-1` from `BspNode::leaf`). But the writer
(`model_write::put_node`, mirrored in `umodel.py`) emits `i_leaf[0..1]` into serial fields 9–10 =
the **real `iCollisionBound`/`iRenderBound`**, and `i_collision_bound`/`i_render_bound` into fields
14–15 = the **real `iLeaf`**. So the leaf marker `0` lands in `iRenderBound`, and the real `iLeaf`
ships `-1`. Confirmed on disk (rawdump): our node[0] fields = `iCollisionBound(f9)=-1,
iRenderBound(f10)=0, iLeaf(i32,i32)=(-1,-1)`; **every** node has `iRenderBound=0`.

### 4.3 Candidate ranking

| Candidate | Verdict | Evidence |
|---|---|---|
| **`iRenderBound=0` into empty `Bounds`** (field cross-wire) | ✅ **THE CAUSE** | guard `0x17adb`; null `Bounds.Data` deref in `BoundVisible`; matches the exact crash stack |
| Real `iLeaf` all `-1` (same cross-wire, other half) | contributing — breaks interior-leaf/zone lookup, view would be empty even once the crash is gone | `DXOnly` node[5] `iLeaf[1]=0`; ours all `-1` |
| Missing `Bounds`/`LeafHulls` arrays | **not** independently fatal | `-1` guard at `0x17adb` proves empty bounds render fine; map loads with them empty |
| Missing sidelinks (`iSide=-1`, `NumSharedSides=0`) | not the crash | render never indexes an empty side pool; only cosmetic T-junctions |
| Front/back swap (diff #4) | not the **render** crash — **but IS the collision bug** (§60) | render visits both children; **collision requires FRONT in `iChild[1]`** — inverted slots ⇒ pawn falls through floor. Fixed by the slot exchange in `finalize` (§60 §6) |
| `NodeFlags=0x20` (NF_IsNew) vs 0 (diff #3) | not the **render** crash — **but IS the collision bug** (§60) | `FBspNode::IsCsg()` returns non-solid while `NF_IsNew` set ⇒ **no node blocks** ⇒ pawn falls through. Must be cleared for collision, not merely "for cleanliness" (§60 §2.1) |
| `Polys=null`, `field_0x54=0` (diff #2) | not the crash | editor-only source polys; map renders without them |

---

## 5. Fix spec (concrete, implementable)

The on-disk byte positions are already correct; the fix is **(A)** put the right values in the
right slots and **(B)** de-alias the field names so this trap can't recur.

### 5.A Minimal, guaranteed crash fix — `build.rs :: finalize_leaves_and_bbox`

Route the leaf indices to the real `iLeaf` slots and force both bound slots to `-1`. With the
**current (mislabeled) struct field names** that is literally:

```rust
for ni in 0..model.nodes.len() {
    let (fr, bk) = (model.nodes[ni].i_front, model.nodes[ni].i_back);
    // REAL iLeaf lives in the fields named i_collision_bound / i_render_bound (serial fields 14–15).
    model.nodes[ni].i_collision_bound = if fr == -1 { 0 } else { -1 }; // iLeaf[0]
    model.nodes[ni].i_render_bound    = if bk == -1 { 0 } else { -1 }; // iLeaf[1]
    // REAL iCollisionBound / iRenderBound live in the fields named i_leaf[0..1] (serial fields 9–10).
    model.nodes[ni].i_leaf = [-1, -1]; // no bounds -> OccludeBsp skips the bound test (0x17adb)
    model.nodes[ni].i_zone = [0, 1];
    model.nodes[ni].zone_mask = 0b10;
}
```

That single change makes every serialized `iRenderBound = -1` (kills the crash) and puts the
interior-leaf pointer where the renderer looks for it.

> Leaf-index value note: `0` on **every** terminal child (as above / as today) is non-crashing
> (`Leaves[0]` exists, zone 1 exists) and is fine for a single convex room, but it marks *solid*
> terminal sides as the interior leaf too. `DXOnly` attaches leaf 0 to **only** the one true
> interior terminal (node[5] `iLeaf[1]`), all other terminals `-1`. Exact parity needs the
> `TestVisibility` leaf/zone flood (§8, section 10) and is the tracked portalize slice — not
> required to stop the singularity or to render the room.

### 5.B Recommended — rename the fields to reality (same bytes)

To remove the latent mislabel, rename across `model.rs`, `model_write.rs`, and `umodel.py`
**without changing byte order**:

- serial fields 9–10 (the ci pair after `iPlane`): rename `i_leaf[0..1]` → **`i_collision_bound`,
  `i_render_bound`**;
- serial fields 14–15 (the trailing i32 pair): rename `i_collision_bound`/`i_render_bound` →
  **`i_leaf[0..1]`**.

`put_node` then reads (top-to-bottom): `… i_plane, i_collision_bound(ci), i_render_bound(ci),
i_zone[0], i_zone[1], num_vertices, i_leaf[0](i32), i_leaf[1](i32)`. After the rename,
`finalize` reads naturally: `i_leaf = [fr==-1?0:-1, bk==-1?0:-1]; i_collision_bound = -1;
i_render_bound = -1;`. **The emitted bytes are identical to 5.A** — verify the `DXOnly`
round-trip and the Rust↔Python §6-gate-5 cross-check stay byte-exact after the rename (they must,
since only names move).

### 5.C Optional cleanups (not required for the crash)

- Clear `NF_IsNew`: emit `node_flags = 0` for finished nodes (matches `DXOnly`).
- Populate `Bounds`/`LeafHulls` + real `iRenderBound`/`iCollisionBound` only if bound-based frustum
  culling is later wanted (§7.4 — regenerable build output; empty + `-1` is correct, just slower).
- Sidelinks (`bspOptGeom`) and multi-zone portalization remain the deferred slices; neither blocks
  the render.

### 5.D Collision path

Setting `iCollisionBound = -1` (`node+0x2c`) everywhere removes the same empty-`LeafHulls`
indexing hazard on the collision side that `iRenderBound` had on the render side — necessary, and
done by 5.A/5.B.

> **⚠ Corrected 2026-07-15 (live-verified) — the `-1` bound is NECESSARY but NOT SUFFICIENT for
> collision.** An earlier draft claimed collision then "falls back to the plane walk — correct, no
> separate change needed." A live test disproved this: once the render crash was fixed and
> `NativeCSG.dx` ran, `GetPlayerPosition` showed the pawn at `z ≈ -2,000,000`, `phys=PHYS_Falling`
> — **it drops straight through the floor.** The `UModel::LineCheck` plane-walk fallback does exist,
> but it is useless here because `finalize_leaves_and_bbox` blanket-marks **every** terminal node
> side as the single interior leaf 0 (`i_leaf = [fr==-1?0:-1, bk==-1?0:-1]`), so the SOLID exterior
> half-spaces are mislabeled EMPTY and collision never finds solid space to stop against. The
> correct pattern (this doc, §3 hand-decode of `DXOnly.dx`) is `iLeaf=(-1,-1)` on solid terminals
> and leaf 0 on ONLY the true interior terminal — which requires tracking CSG **solidity** per
> terminal during `bsp_brush_csg` (the deferred N-2 leaf/zone-solidity slice; the `csg.rs` filter
> already carries `leaf_outside`, so the information exists but isn't yet propagated into `iLeaf`).
> Tracked on the board: inbox "[plan] Native BSP leaf/solidity assignment — player falls through
> the floor". So the render path is fully fixed and clean; **collision is a separate open slice.**
>
> **⚠ SUPERSEDED 2026-07-15 by `sections/60-leaf-solidity-collision.md` (Engine.dll disasm):** the
> fall is **not** caused by `iLeaf`. `UModel::LineCheck`/`PointCheck` never read `iLeaf`; they gate
> solidity on `FBspNode::IsCsg()` (`NodeFlags`/`NumVertices`) and descend by re-deriving side. The
> two real causes are **`NodeFlags=0x20` (`NF_IsNew`) on every node** (→ `IsCsg` false → nothing
> blocks) and the **front/back slot inversion** (FRONT must sit in `iChild[1]`, we put it in
> `iChild[0]`). `iLeaf` still needs correcting, but for `PointRegion`/zones. No collision hull is
> required. Fix spec: section 60 §6.
```
