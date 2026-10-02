# Live UED22 path builds (`harness/live_paths.py`, `harness/make_trunk.py`) — 2026-09-05 🔬

Ephemeral UED22 editors (`ensure_editor`), one `EXEC` batch each, every step `MAP SAVE`d and decoded
with `harness/retail_stats.py` / `harness/graph_tool.py`. Levels: the synthetic `pathlab`
(`make_trunk.py`: 8192-uu corridor with node gaps 100..1200, a hall with platforms 16..160 high,
a PlayerStart room) and `pathlab2` (water ZoneInfo, a closed door Mover, a lift with
LiftCenter/LiftExit, a Teleporter pair, a `DeusEx.MedKit`, node property variants, corridor widths
40..200, ceiling heights 48..200), plus retail `02_NYC_Bar.dx`. Evidence: `evidence/pathlab-*.dx`,
`evidence/pathlab2-define.dx`, `evidence/*-editor-log-excerpt.txt`.

## What each verb does (from the DevPath log + the saved files)

| Verb | Log | Result |
|------|-----|--------|
| `MAP LOAD` + `MAP SAVE` | – | retail reachspecs and node arrays survive **byte-for-byte** (Bar: 889/889 specs identical, all fields) |
| `PATHS DEFINE` | `Remove N old reachspecs` → `Add WarpZone and Inventory markers` → `Add reachspecs` (`Added reachspecs to <node>` per node, roster order) → `Added N reachspecs` → `Prune reachspecs` → `Pruned N` → `All done` | the **full reachspec build** over the placed nodes: `ReachSpecs`, `Paths`/`upstreamPaths`/`PrunedPaths`, `bPruned`. (The 2026-07-15 spike's "DEFINE only spawns markers" is wrong.) Spawns one `InventorySpot` per `Inventory` actor. No auto PathNodes. |
| `PATHS BUILD` | a full DEFINE pass, then `----Starting From <PlayerStart>` / `WALK WITH COLLISION SIZE 70 40` … `28 40` (7 sizes, step 7) / `----Anchor <node>` / `Total steps out of bounds` / `Num steps 2000`, then `Found potential distant pair A (x,y) and B (x,y)` / `Try N Total t versus a + b` / `Found N as intermediate` / `Added new path PathNodeK at x y`, then a second full DEFINE pass, `Total paths build time 24.1 seconds`, `Built Paths: 8` | DEFINE + **auto-placement of `bAutoBuilt=True` PathNodes** (8 on pathlab, 8 on the Bar) + DEFINE again. Re-running BUILD first deletes the previous auto nodes (`Remove 329 old` → 281 specs → 329 again). |
| `PATHS BUILD LOWOPT` / `HIGHOPT` | identical log | **identical graphs** to plain BUILD (329 specs / 210 pruned; files differ by 6–8 bytes of session stamps). No visible effect of `opt` on these levels. |

Bar rebuilt with BUILD: 80 → 110 nav actors (22 `InventorySpot` + 8 auto `PathNode`), 889 → 1017
specs; with DEFINE only: 102 nav actors, 867 specs.

## Auto-placement (`PATHS BUILD` only)

- Starts from the `PlayerStart` (`Starting From D_Start`), then from each `InventorySpot`
  (`Starting From InventorySpot1` → `No valid start found` when the spot is at a garbage location).
- The scout walk uses radius 70,63,…,28 (step 7) at height 40, a `2000` step budget per size
  (`Num steps 2000`, `Total steps out of bounds`); every reachable existing node is logged as an
  `Anchor`.
- "Potential distant pair" = two nodes **without a reachspec between them** (regardless of
  distance: `A_N00`–`A_N12` at 7800 uu is listed); for each, an intermediate node `N` with legs to
  both is looked for (`Try A_N09 Total 1450.02 versus 1000.00 + 450.07` → `Found A_N09 as
  intermediate`, so the sum may exceed the direct distance); with no intermediate, a new PathNode is
  spawned at the **midpoint** (`Added new path PathNode0 at -1450 0` for `A_N06`(−1800)–`A_N07`
  (−1100), which already had a direct 700-uu spec — the pair is re-tested after the spec build?
  see the disassembly findings) at z = floor + 48/52.
- On pathlab the 8 new nodes sit at the midpoints of the 700, 800, 900, 1000, 1100 and 1200-uu gaps
  and then split the 1200 gap twice more (`A_N11`–`PathNode5` 600 → `PathNode6`; `PathNode5`–`A_N12`
  → `PathNode7`), while the 600-uu gap `A_N05`–`A_N06` (which had a spec) got none.

## Reachspec values UED22 writes (define pass)

| Field | Observed |
|-------|----------|
| `Distance` | `appRound(|End−Start|)` (round-to-nearest, never truncation: 94/281 pathlab specs and 435/816 common Bar specs differ from retail's truncated value by +1). SWIM edges: **2 ×** straight line (`E_N00→E_N01` 361.2 → 722; 600 → 1200 — and a 1200 SWIM spec exists, so the cutoff is on the straight line). |
| candidate cutoff | straight-line **< 1000 uu**: gap 900 connects (`A_N08→A_N09` 900), gap 1000 does not; nodes with no neighbour < 1000 get no specs. Same as retail's max 999. |
| `CollisionRadius` | sweep **70 → 18 in steps of 6.5** (9 values), stored `appRound` (round-half-even: 24.5→24, 37.5→38, 50.5→50, 63.5→64): corridor width 40 → 18, 56 → 24, 72 → 31, 96 → 44, 128 → 64, ≥160 → 70. Never above 70 (retail goes to 115). |
| `CollisionHeight` | 70 on open floor; ceiling 96 → 44, 128 → 60, ≥160 → 70; ceilings 48/64/80 → **no spec at all** (the scout's smallest height does not fit). Never above 70 (retail 79) and never below 44 (retail down to 10). |
| `reachFlags` | WALK; WALK\|JUMP for any drop or climb the scout cannot step (see below); SWIM inside a `bWaterZone` ZoneInfo (all three water-room specs SWIM-only); SPECIAL on Lift and Teleporter edges. **DOOR (16) and PLAYERONLY (64) never written**: a closed Mover across the corridor is ignored (`F_N00↔F_N01` plain WALK 600 — the code blocks on a `bBlockActors` Mover, so the imported `Engine.Mover`'s collision flags need checking), a `bPlayerOnly=True` node gets ordinary edges. |
| step / jump | stair steps of 8 and 16 uu: WALK. Climb of 32–64 uu (floor node → platform top): WALK\|JUMP. Climb ≥ 80: no spec. Any drop (−32 … −160) that is not a stair: WALK\|JUMP; a drop down a 8/16-uu stair: WALK. |
| Lift | `LiftCenter ↔ LiftExit` (both exits, both directions): `Distance=500, R=60, H=60, SPECIAL` — hard-coded, the far exit is 576 uu away and 512 uu higher. |
| Teleporter pair | `H_T1 ↔ H_T2` (URL both ways): `Distance=100, R=150, H=150, SPECIAL`. |
| `bEndPointOnly=True` node | still gets outgoing specs (not a build-time filter). |
| `ExtraCost=500` node | `cost=500` written on the node (`LiftCenter` gets `cost=400` = its default `ExtraCost`). |
| `InventorySpot` | spawned per `Inventory` at a **garbage Location** (X = 1.8e25 on the Bar, X/Y = 4.6e24/1.4e25 on pathlab2 — the 469 `InventorySpot` class defaults carry the `0x68670004` float in `CollisionRadius/Height`, see `30-script-side.md`), no specs. The BUILD exploration then reports `No valid start found` from them. |
| per-node arrays | `Paths`/`upstreamPaths` sorted by **descending Distance** (28/28, 28/28 nodes), `Paths+PrunedPaths ≤ 16` with the longest specs dropped (3 nodes at 16), zero mismatches — the same shape as retail. `visitedWeight=10000000` and `bestPathWeight` residue written on every node (`bestPathWeight` = distance from the roster-first node on the corridor: 100, 200, … 900). |
| prune | 184/184 pruned specs have a two-hop route ≤ 1.2× (109 ≤ 1.0×). |

## UED22 vs the retail (DX 1112fm) build of the same map (`02_NYC_Bar`)

DEFINE-only: 867 specs vs 889; 816 common (Start,End) pairs, 73 retail-only, 51 UED22-only. On the
common edges: `H` differs on 816 (79 → 70), `R` on 736 (115-cap sweep vs 70-cap sweep), `Distance`
on 435 (+1 from rounding), `bPruned` on 79, flags on 95 (UED22 adds JUMP; the BUILD rebuild has 199 WALK|JUMP of 1017 specs vs
retail's 1 of 889). Plus 22 `InventorySpot`
actors at garbage locations. So a UED22 path build is **not** a reproduction of the retail build:
pawns with radius > 70 or height > 70 (retail specs go to 115/79) lose every edge under
`supports()`, and non-jumping pawns lose the edges UED22 tags JUMP (if the game's `supports` treats
JUMP as a requirement — see `21-dx-reachability-and-ai.md`).
