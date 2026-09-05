+++
priority = "p?"
kind = "owner-question"
summary = "UED22 path build differs from the Deus Ex builder; InventorySpot spawn is broken"
+++

# UED22 path build differs from the Deus Ex builder; InventorySpot spawn is broken

Findings of the 2026-09-05 path-build reverse engineering (`PATHING-BUILD.md`,
`dev/docs/spikes/2026-09-05-pathing-build-re/`). Three things need a ruling.

1. **A UED22 `PATHS DEFINE`/`BUILD` does not reproduce a retail Deus Ex graph** (§7 of the doc):
   size caps 70/70 vs 115/79, `R_JUMP` on every non-stair drop (unusable by `ScriptedPawn`,
   `bCanJump=False`), rounded vs truncated `Distance`, a different prune boundary. If
   `level materialize` is ever to emit paths that match retail, it needs the `dx` rules natively
   (the bookkeeping + prune replay in `harness/simulate_bookkeeping.py` already reproduces every
   retail map bit-for-bit; the traversal test and `findBestReachable` would be the native work).
   Ruling wanted: build paths with the editor (UED22 semantics), natively (`dx` semantics), or not at
   all for now (a map with `ReachSpecs.Count = 0` loads and plays; only NPC routing is absent).
2. **UED22's `definePaths` spawns one `InventorySpot` per `Inventory` at a garbage Location**
   (X ≈ 1.8e25): the 469 `Engine.u` `InventorySpot` defaults carry the corrupt float `0x68670004` in
   `CollisionRadius/Height`. Any path build in UED22 litters junk actors; `PATHS UNDEFINE` removes
   them again. Ruling wanted: whether to patch the substrate `Engine.u` defaults, strip the spots
   after a build, or avoid the editor build.
3. **`dev/docs/unrealed/commands.md` "PATHS" and the 2026-07-15 spike §4 are wrong** (`PATHS DEFINE`
   is the reachspec build, `createPaths` is the auto-placer, cutoff 1000 uu, `supports` direction,
   LOWOPT/HIGHOPT no-ops, on-disk residue fields). Proposed replacement text: `PATHING-BUILD.md` §2
   and §8. Needs the owner's yes before `dev/docs/unrealed/commands.md` is edited.
