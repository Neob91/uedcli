# Spec — native collision hulls (`bspBuildBounds`) + full-parity BSP

**Status:** root cause CONFIRMED; playability fix scoped (2026-07-16). Ephemeral per-feature
scratch; durable record → `sections/70-zones-portalization.md`, `re-raw-zones/linecheck-oracle.md`,
`architecture.md`, `decisions.md`.
**Goal:** make a native-materialized `.dx` **playable** (pawn `phys=1`, rests extent-above the
floor, stays) by emitting the collision hulls the editor's `bspBuildBounds` produces; then close the
remaining structural-parity gaps (leaves, zones).

## 1. Root cause — CONFIRMED (oracle decode + box-sweep oracle + A/B proof)

The pawn falls through the floor on **every** native map (single subtract reproduces it; not
multi-brush). Mechanism (`re-raw-zones/linecheck-oracle.md`, game `Engine.dll` base 0x10300000):

- `UModel::LineCheck` **forks on Extent**. `Extent==0` = the node-plane walk `0xf3560` (what
  section 60 decoded — uses `IsCsg`, no hulls, works on our maps). **`Extent!=0` — every pawn/actor
  sweep — takes a SEPARATE function `FBoxLineCheckInfo::BoxLineCheck` `0xf42f0`.** Its descent only
  *routes* to solid leaves; the sole hit (`DidHit=1` @0xf5678) is produced by **clipping the swept
  box against the terminal solid leaf's convex hull read from `Model.LeafHulls` via
  `Nodes[iParent].iCollisionBound`**. `0xf4602: iCollisionBound==-1 → return` — **no node-plane
  fallback for box traces.**
- Our native build ships `iCollisionBound=-1` on every node + empty `LeafHulls`, so the world is
  **totally non-solid to any box sweep**. The pawn's cylinder never lands; its *center* (a point via
  `PointRegion`) then crosses into the correctly-classified solid/zone-0 region → `FellOutOfWorld`
  → `PHYS_None` frozen center-on-plane (small rooms) or menu bounce (large rooms).
- **Box-oracle proof** (`harness/line_check.py --extent 20,20,44`): HIT on `Test_Castle`/`DXOnly`
  (land at floor+extent), NO-HIT on `NativeBig`/`NativeCSG`/`NativeCastle`. **A/B**: appending ONE
  hull to `NativeCSG`'s floor node (`[0|FLIP,1|FLIP,2|FLIP,3|FLIP,5,-1, bbox]`, set that node's
  `iCollisionBound`) — nothing else — makes the sweep land at `floor+44`.

This supersedes section 60's "`iCollisionBound=-1` is fine" (true only for the zero-extent line
trace) and refutes the review's objection (which trusted §60's mislabel of `0xf3560` as the box
path). §60's own fixes (NodeFlags, front/back slots, iLeaf) remain necessary — just insufficient.

## 2. The hull format (dumped from `Test_Castle` node 1152 + the `0xf460e` clip decode)

Per **solid terminal cell**, one `LeafHulls` run: `[plane-node ref, …, -1, 6× bit-cast-f32 bbox]`.
- Each plane-node ref = the bounding node's index, **OR `0x40000000` (FLIP) when the node plane's
  front faces INTO the solid** — normals must point **OUT of the solid** (cell interior has
  `PlaneDot < 0`). Read back as `Nodes[ref & 0xBFFFFFFF].Plane`, negated iff FLIP.
- Then `-1` terminator, then the cell's `FBox` as 6 raw-i32-bitcast f32 (min.x,min.y,min.z,
  max.x,max.y,max.z), `±32768` where the cell is unbounded. `≤0x40` planes per run.
- The **node whose `iChild[side]==-1` on the solid side** gets `iCollisionBound` = that run's start
  index. `Bounds`(+0xc0)/`iRenderBound` stay EMPTY/`-1` — the box sweep reads neither, and a bogus
  `iRenderBound>=0` re-arms the OccludeBsp NULL-FBox render crash (section 50). **Collision bounds
  and render bounds are separate; we build only collision.**

## 3. Work items (ordered; re-run the live `phys=1` gate after §3.2)

### 3.1 Serializer: carry + (de)serialize `LeafHulls` (+ `Bounds`) — land EMPTY first

Per reviewer-#2 finding 3 (safe sequencing), do NOT combine serializer and producer:
1. Add `leaf_hulls: list[int]` and `bounds: list[FBox]` fields to BOTH `umodel.Model` (Python
   oracle) and the Rust `model.rs::Model`; writer emits them, parser **captures** them (replacing
   `_skip_c0`/`_skip_i32_raw` and the `ci(0)` writes). Default **empty** ⇒ byte-identical to today
   (`bin/test`, §6 gate-5 dual-serializer, M0 `carved_box*`, the self-check all stay green). Pin
   Rust==Python. **Commit.**
2. Add a **byte-equality** round-trip test over the real `DXOnly.dx` `c0`/`cc` region (parse→write
   == original bytes): FBox = 6 f32 + 1 valid byte = 25 B serial; `LeafHulls` = `ci(count)` + i32×n.
   Proves the (de)serialization before any producer exists. **Commit.**

### 3.2 Producer: `bspBuildBounds` collision hulls (THE playability fix)

`passes::bsp_build_bounds` (today a no-op) → for each SOLID terminal cell (DFS with `Outside`
tracking seeded from `RootOutside`, `front:Outside||IsCsg`, `back:Outside&&!IsCsg`): collect the
path's bounding node planes, orient each so the cell has `PlaneDot<0` (set FLIP bit otherwise),
compute the cell bbox (clip the ±32768 world box by the bounding planes → vert AABB; ±32768 where
unbounded), append the run to `model.leaf_hulls`, set the solid-terminal's parent node
`i_collision_bound`. Leave `Bounds`/`i_render_bound` empty/`-1`.
- **Validate offline with `harness/line_check.py`**: box sweep (extent 20,20,44) must HIT the floor
  at `floor+44` on rebuilt `NativeCSG`/`NativeBig`/`NativeCastle`, matching `Test_Castle`.
- **Guard (reviewer-#2 finding 2):** setting `iCollisionBound>=0` flips the game's `PointCheck` onto
  the hull path — the hull must be correct or point-encroachment regresses. Keep `drop_probe.py`
  (PointRegion, unaffected) green AND add a point-in-hull check.
- Bounds are **regenerable build output** (`direction.md`): never fold into `canonical_level_hash`
  or the H3 materialize post-verify (reviewer-#2 finding 5).

### 3.3 Live gate

Rebuild `NativeCastle` → `uplayctl` → **numeric** rest check (pawn Z ≈ floor + CollisionHeight, not
just `phys=Walking` — reviewer's false-positive caution) + `shot` shows the castle first-person,
stays (no `DXONLY` bounce).

### 3.4 Full parity (separate, playability-NEUTRAL — do after §3.3 lands)

Real leaves (Pass A), zones B–G + `_patch_zone_refs`, side pool, node flags — per section 70. These
fix per-room `ZoneInfo`/gravity/regions and byte-parity, NOT collision (reviewer-#2 finding 4:
`AssignLeaves` is a zone fix; the blanket finalize swap is structurally safe).

## 4. Decisions to record (`decisions.md` on landing)

- Native playability blocker = **missing collision hulls** (`iCollisionBound`/`LeafHulls`), not
  zones. `UModel::LineCheck` forks on Extent; the box path `0xf42f0` has no node-plane fallback.
- `bspBuildBounds` collision hulls are **required** native build output (supersede section 60's
  "bounds optional", which held only for zero-extent line traces). Render bounds
  (`Bounds`/`iRenderBound`) remain optional and stay empty/`-1`.
