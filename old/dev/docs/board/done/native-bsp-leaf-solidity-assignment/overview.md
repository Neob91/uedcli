+++
priority = "p1"
kind = "unknown"
summary = "Native BSP leaf/solidity assignment — player FALLS THROUGH THE FLOOR (no collision)"
+++

# Native BSP leaf/solidity assignment — player FALLS THROUGH THE FLOOR (no collision)

p1. Surfaced 2026-07-15 once the render-crash was fixed and `NativeCSG.dx` (single-subtract room)
finally ran: the game renders the room with ZERO render errors, but `GetPlayerPosition` shows the
pawn at `z=-2,000,000+` and `phys=2` (PHYS_Falling) — it drops straight through the floor.
**ROOT CAUSE RE'd (spike `sections/60-leaf-solidity-collision.md`, 2026-07-15): NOT iLeaf.** The
game's `UModel::LineCheck`/`PointCheck` never read `iLeaf`; they decide solidity from
`FBspNode::IsCsg()` (`Engine.dll 0xf68b0`: blocks iff `NumVertices>0 && (NodeFlags &
(NF_NotCsg|NF_IsNew))==0`) and descend by re-deriving each node's side (`iChild[1]`=FRONT/positive).
Two real bugs, both fixable in one `finalize_leaves_and_bbox` pass: (1) every node ships
`NodeFlags=0x20` (`NF_IsNew`) → `IsCsg`=false → NO node blocks (DXOnly ships `0x00`); (2) our build
stores the FRONT child in `i_front`(+0x20=`iChild[0]`) but the engine reads FRONT from `iChild[1]`
(+0x24) → topology INVERTED → interior segment hits a leaf at node 0, floor plane unreachable.
Fix (spec in §6 of the spike): exchange `i_front↔i_back`, clear `NF_IsNew`, set `iLeaf` front=empty
/back=solid, `iZone=(0,1)`. Applied to parsed `NativeCSG.dx` it reproduces `DXOnly`'s node/flag/leaf
/zone table exactly and makes every region resolve correctly in an engine-descent sim. `iLeaf` still
gets fixed but for `PointRegion`/zone correctness, not the fall. A collision hull (`LeafHulls`) is
NOT needed (`iCollisionBound=-1` skips the hull test, `0xf1bff`). **✅ RESOLVED + LIVE-VERIFIED
2026-07-15:** §6 fix landed in `build.rs::finalize_leaves_and_bbox`; the live game now reports
`phys=PHYS_Walking`, `speed=0`, `z=-134` STABLE (was `phys=Falling`, `z=-2,000,000+`) — the pawn
stands on the floor, render still clean. Pinned by `test_finalize_collision_topology_matches_dxonly`.
Remaining: multi-room leaf/zone (deferred `TestVisibility`), and wall/ceiling collision not
separately exercised (same BSP mechanism as the verified floor). Repro: regen `NativeCSG.dx`
(scratch `regen.py`), boot `dx-lum-game` with `DX_MAP=NativeCSG`,
`docker exec -i <cn> python3 /work/client.py GetPlayerPosition`.
