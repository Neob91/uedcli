# Retail-map ground truth (88 `.dx`, 83 with reachspecs) — `harness/retail_stats.py`

All 88 retail maps under `dev/games/deusex/Maps/`; 16 151 NavigationPoints, 128 178 reachspecs.
Every number below is from the on-disk data, decoded with `uedcli/upackage.py` (the retail maps were
built by the Deus Ex 1112fm engine's builder, not UED22). ✅ throughout.

## The `FReachSpec` values

| Field                          | Observed                                                                   |
|--------------------------------|----------------------------------------------------------------------------|
| `Distance`                     | `int(|End.Location − Start.Location|)` (truncation, never rounding) on 127 383/128 178. SWIM edges: exactly `2 × int(euclid)` (791). The 4 leftovers are stale specs whose `Teleporter`/`MapExit` endpoint was moved after the build. |
| `reachFlags`                   | WALK 125 879 · WALK\|JUMP 1 508 · SWIM 784 · WALK\|SWIM 5 · WALK\|SWIM\|JUMP 2. No FLY, no DOOR (16), no SPECIAL (32), no PLAYERONLY (64) anywhere in retail. |
| max `Distance`, unpruned WALK  | 999 (never ≥ 1000) → the candidate cutoff is a 1000-uu straight line. SWIM max 1838 = 2 × 919. |
| `CollisionRadius`              | exactly the 33 values `int(12 + 103·k/32)`, k = 0..32: 12 15 18 21 24 28 31 34 37 40 44 47 50 53 57 60 63 66 69 73 76 79 82 86 89 92 95 98 102 105 108 111 115. 115 (the cap) on 44 410. |
| `CollisionHeight`              | exactly the 33 values `int(10 + 69·k/32)`: 10 12 14 16 18 20 22 25 27 29 31 33 35 38 40 42 44 46 48 50 53 55 57 59 61 63 66 68 70 72 74 76 79. 79 (the cap) on 102 477. |
| `bPruned`                      | 68 401 (53 %).                                                             |
| `Start == End`                 | never. Duplicate `(Start,End)` pairs: never. `Distance == 0`: 10 (coincident nodes). |
| reverse edge exists            | 122 854 / 128 178 (96 %) — reachability is tested per direction; radius can differ per direction (`02_NYC_Bar` spec 15 vs 403: 50 vs 53). |

So the DX `findBestReachable` is a 32-step linear sweep of BOTH radius (12→115) and height (10→79),
recording the largest size that still passes; the stored ints are truncations of the float sizes.

## The per-node arrays (`Paths[16]`, `upstreamPaths[16]`, `PrunedPaths[16]`)

- Every non-`-1` entry points at a spec with the right `Start`/`End`/`bPruned`: 54 007 `Paths`,
  56 124 `upstreamPaths`, 68 401 `PrunedPaths` — zero mismatches.
- No gaps: used slots are `0..n-1`, unused are `-1` (default, not written).
- **`Paths` and `upstreamPaths` are sorted by DESCENDING `Distance`**: 14 507/14 507 and
  14 299/14 299 nodes with ≥ 2 entries. Not by spec index, not by End index.
- **Hard cap of 16 outgoing specs per node, chosen shortest-first**: `len(Paths)+len(PrunedPaths)`
  is never > 16 and equals 16 on 1 613 nodes. On those, the surplus (longer) specs still sit in
  `ULevel.ReachSpecs` unreferenced: 2 978 orphan specs corpus-wide (5 770 spec slots not in any
  array), always the longest of the node's candidates (1 300/1 300 nodes), never pruned.
- `VisNoReachPaths` (object refs) is written on 4 608 nodes.
- `bestPathWeight`/`visitedWeight` — runtime scratch — are nonetheless on disk on 15 356 / 15 980
  nodes (the saver writes every non-default property). `cost` on 27, `bEndPoint` on 111,
  `bAutoBuilt` on **none** (`autobuilt = 0` corpus-wide), `ExtraCost` never non-default.

## Prune criterion

For every pruned spec `A→B` there is a node `N` with node-referenced specs `A→N`, `N→B` and
`Distance(A→N)+Distance(N→B) ≤ 1.2 × Distance(A→B)`: 68 401/68 401, and the largest observed
ratio is **1.199737** — the factor is 1.2. Superseded by the replay (`harness/simulate_bookkeeping.py`,
`evidence/replay-results.txt`): only a STRICT `<` reproduces every retail `bPruned` bit (Bar spec 73 sits
exactly at 1.2× and is not pruned); the disassembly explains it (`20-dx-pathbuilder.md` §3.32).
21 726 of them also satisfy ≤ 1.0×. 7 080 unpruned specs would satisfy the same test (with
radius/height/flags dominance) — expected of a sequential prune whose legs get pruned later.

## Classes on the graph

Start/End classes: PathNode–PathNode 102 261, PatrolPoint 21 364 (either end), HidePoint 2 442,
Teleporter 550, SpawnPoint 738, PlayerStart 425, MapExit 229, HomeBase 144. Teleporter edges are
plain WALK edges to neighbours (DX uses Teleporters as map-exit markers, not `R_SPECIAL` warps).
`InventorySpot`/`WarpZoneMarker`/`LiftCenter`/`LiftExit` never appear.
