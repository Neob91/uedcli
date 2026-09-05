# UnrealEd's AI path build — reverse engineered

How `PATHS DEFINE` / `PATHS BUILD` turn placed NavigationPoints into the reachspec graph the game's
AI routes on, read from the binaries and verified against every retail map and live editor runs.
Evidence, harness and the instruction-level readings live in
`dev/docs/spikes/2026-09-05-pathing-build-re/` (`findings/*.md`, `harness/*.py`, `evidence/`);
`uedcli/tests/test_pathing_facts.py` pins the checkable facts.

Two engines matter, and they differ; every fact below says which:

| Key   | Binary                                   | What it is |
|-------|------------------------------------------|---
| `ued` | `uned/UED22/Engine.dll` (+ `Editor.dll`) | the OldUnreal 469 / UT-lineage editor uedcli drives; what `level materialize` would run |
| `dx`  | `dev/games/deusex/System/Engine.dll`     | Deus Ex 1112fm, Unreal-1 lineage; built the retail maps' graphs and consumes them in-game |

Markers: ✅ read from the code or the bytes · 🔬 live-probed / inferred, inference stated ·
📖 public-source knowledge, unconfirmed here. RVAs are image-relative (`ued` base `0x10000000`,
`dx` base `0x10300000`); `dx` exports are `jmp` thunks, the RVAs cited are the bodies. "Retail" =
the 88 shipped `.dx` maps (83 single-player, 79 of them with paths; the 5 `DXMP_*` maps have
deleted, off-roster nodes and are excluded from the replays).

## 1. What is on disk

### 1.1 `ULevel.ReachSpecs` — the edges ✅

A `TArray<FReachSpec>` in the `Level` export body (compact-index count), one directed edge each:

```
INT32 Distance   ci Start   ci End   INT32 CollisionRadius   INT32 CollisionHeight   INT32 reachFlags   u8 bPruned
```

`Start`/`End` are object refs to NavigationPoint actors. In memory the struct is 28 bytes with
pointers (`ued 0x10112b32`, `dx 0x44c80`). Specs are appended in creation order: all of a node's
ordinary edges together, in the order §3.1 visits its partners; a LiftCenter also appends the
reverse `LiftExit→LiftCenter` edges while it is processed (§3.2), so a LiftExit's edges are split.

`reachFlags` bits, from `APawn::calcMoveFlags` (`ued 0x10116cb0`, `dx 0x26d10`), which packs the
pawn's abilities in the same order: `R_WALK 1` (`bCanWalk`), `R_FLY 2`, `R_SWIM 4`, `R_JUMP 8`,
`R_DOOR 16` (`bCanOpenDoors`), `R_SPECIAL 32` (`bCanDoSpecial`), `R_PLAYERONLY 64` (`bIsPlayer`).
The builders write 1/2/4/8 (from the traversal test) and 32 (lift / teleporter / warp-zone edges).
No writer of 16 or 64 was found in either engine's builder or `*Reachable` code (a scan over
`[reg+0x14]` accesses; stack-held specs would escape it), and retail carries neither bit.

`FReachSpec::supports(r, h, flags)` — the consumer's one gate (`ued 0x1011aa40`, `dx 0x44c30`):

```
CollisionRadius >= r && CollisionHeight >= h && (reachFlags & flags) == reachFlags
```

The PAWN's flags must be a superset of the SPEC's: a `WALK|JUMP` spec is unusable by a pawn with
`bCanJump=False`.

### 1.2 The per-node arrays ✅

`NavigationPoint` carries `upstreamPaths[16]`, `Paths[16]`, `PrunedPaths[16]` (spec indices, `-1`
empty) and `VisNoReachPaths[16]` (actor refs). Layout `ued` +0x214/+0x254/+0x294/+0x2d4, `dx`
+0x320/+0x360/+0x3a0/+0x3e0 (`harness/layout.py`). On disk each used element is one `FPropertyTag`
with the array index in the info byte's bit 7 + one index byte (none for element 0); only elements
that differ from the default `-1` are written, always the contiguous prefix `0..k-1`
(`findings/30-script-side.md` §3.2 has a byte-level walk of `02_NYC_Bar.dx` `PathNode0`). Tag
order is the class chain, most-derived first.

Invariants that hold on every retail map and every UED22 build (`harness/retail_stats.py`):

- `Paths[i]` → a spec with `Start` = this node and `bPruned=0`; `upstreamPaths[i]` → `End` = this
  node, `bPruned=0`; `PrunedPaths[i]` → `Start` = this node, `bPruned=1`. Zero mismatches over the
  178 532 retail array entries.
- `Paths` and `upstreamPaths` are sorted by **descending** `Distance` (longest first).
- `len(Paths) + len(PrunedPaths) ≤ 16`: a node keeps its 16 shortest outgoing edges. A surplus spec
  stays in `ReachSpecs`, unmarked: 2 978 retail specs sit in no array at all, and 5 770 array slots
  are "one-sided" (in `Start.Paths` but not `End.upstreamPaths`, or the reverse), see §3.5.

### 1.3 Other fields the build writes ✅ (attribution 🔬 where marked)

No NavigationPoint variable is `Transient` in either `Engine.u`, so `MAP SAVE` writes every
non-default value the build leaves behind:

| Field                                   | Written by | Read at runtime? |
|-----------------------------------------|------------|---
| `nextNavigationPoint`, `LevelInfo.NavigationPointList` | `definePaths`: prepend in roster order, so the list is the reverse roster and its head is the roster-last node (`ued +0x464`, `dx +0x548`) | yes — the game never rebuilds them (`dx` writers exist only in the builder: `0xb102c/0xb1326/0xb160d/0xb110d/0xb159d`) |
| `visitedWeight = 10000000`, `cost = ExtraCost` | `clearPaths` inside the `findPathToward` calls of `addVisNoReach` (§3.7); live UED22 builds show them on every node | scratch, reset before every search |
| `bestPathWeight`, `previousPath`, `nextOrdered`/`prevOrdered`, `bEndPoint`, one node with `cost = 1000000` (retail, 27 maps) | 🔬 residue of the same searches (`findEndPoint`, `expandAnchor`, `breadthPathFrom` write exactly these; nothing else in the build does) | scratch |
| `Inventory.myMarker`, `InventorySpot.markedItem`, `WarpZoneMarker.markedWarpZone` | marker spawning (`ued` spawns InventorySpots, `dx` does not, §2) | yes |
| `bAutoBuilt` (`ued` only, +0x33c mask 0x40), `Velocity`, `bEndPoint`, moved `Location` | `PATHS BUILD` auto-placement (`ued`, §4.1) | — |

Authored inputs the builders read: `Location`, `Rotation` (only with `bOneWayPath`), `LiftTag`,
`Teleporter.URL`/`Tag`, `WarpZoneInfo` URLs. `bEndPointOnly`, `bPlayerOnly`, `bSpecialCost`,
`ExtraCost` do not change which edges are built or pruned; they act in the runtime search (§5),
which the build only runs for `VisNoReachPaths`.

## 2. Verbs and pipelines

| Verb            | `ued` (`Editor.dll 0x10064f11`) | `dx` (`Editor.dll 0x7ed6e`) |
|-----------------|---------------------------------|---
| `PATHS DEFINE`  | `undefinePaths` + `definePaths` = **the reachspec build** over the placed nodes (§3) | same |
| `PATHS BUILD [LOWOPT\|HIGHOPT]` | destroy `bAutoBuilt` PathNodes → `undefine`+`define` → `createPaths` (auto-place PathNodes, §4.1) → `undefine`+`define` again; logs `Built Paths: <auto nodes>` | `removePaths` (destroys **every** PathNode, hand-placed too — `dx` has no `bAutoBuilt`) → `buildPaths` = `createPaths` (auto-place only, §4.2). Does **not** connect: `PATHS DEFINE` is a separate step |
| `LOWOPT`/`HIGHOPT` | parsed (0/1/2), passed to `createPaths`, **never read** (`0x10177900`–`0x10178bc7` has no `[ebp+8]` access); identical output live | read once, for a log line |
| `PATHS UNDEFINE` | empty `ReachSpecs`, null `NavigationPointList`, destroy marker actors (`WarpZoneMarker`, `InventorySpot`, `TriggerMarker`, `ButtonMarker`), reset every node's arrays and list links; `visitedWeight`/`bEndPoint`/`bAutoBuilt` are left alone | same |
| `PATHS REMOVE`  | destroy every `IsA(PathNode)` actor (no `bAutoBuilt` filter) | same |
| `PATHS SHOW`/`HIDE` | `DrawType` = sprite / none on every PathNode | same |

The traversal tests trace against the level's BSP, so a path build belongs after `MAP REBUILD`
(`MAP REBUILD` does not clear reachspecs).

`definePaths` (`ued 0x10178c10`, `dx 0xb1280`):

```
(ued) trim trailing NULL slots off Actors while Num > 3            // shrinks the serialized roster
getScout()                     // reuse an AScout in the level or spawn one at (0,0,0); SetCollision(1,1,1), bCollideWorld; class-default size 52×50
NavigationPointList = NULL
for a in Actors:
    WarpZoneInfo  → findScoutStart(a.Location) (drop up to 50 × 50 uu to a floor with Normal.Z ≥ 0.7), retry at radius 20, then
                    FarMoveActor(bTest=1) as a last resort; spawn WarpZoneMarker at Scout.Location, markedWarpZone = a
    Inventory     → (ued ONLY) same drop, fallback a.Location + (0,0, 40 − a.CollisionHeight); spawn InventorySpot, markedItem/myMarker
for a in Actors, roster order, IsA(NavigationPoint) (ued also: !bDeleteMe):
    a.nextNavigationPoint = NavigationPointList; NavigationPointList = a          // prepend
    addReachSpecs(a)                                                              // §3.1–3.5
for n in NavigationPointList: Prune(n)                                            // §3.6, reverse roster order
for n in NavigationPointList: addVisNoReach(n)                                    // §3.7
DestroyActor(Scout)
```

Log lines (both engines): `Remove N old reachspecs`, `Add WarpZone and Inventory markers`, `Add
reachspecs`, `Added reachspecs to <node>`, `Added N reachspecs`, `Prune reachspecs`, `Pruned N
reachspecs`, `All done`.

The `dx` `definePaths` handles only `WarpZoneInfo` (`0xb1363`): it never spawns `InventorySpot`s,
matching the retail maps (0 InventorySpots against 0–175 `Inventory` actors each). The `ued` one
spawns one per `Inventory`, at a **garbage Location** (X ≈ 1.8e25 on the Bar, `pathlab2`: X/Y ≈
4.6e24/1.4e25); those spots get no specs and make the auto-placement log `No valid start found`.
🔬 The likely cause is the 469 `InventorySpot` class default `CollisionRadius/Height` = the corrupt
float `0x68670004` (`findings/30-script-side.md` §1.2), which the placement's `FindSpot` uses; not
traced instruction by instruction.

## 3. The reachspec build (`addReachSpecs`, both engines) ✅

`ued 0x10176eb0`, `dx 0xb2240`; identical structure, differing constants tabled.

### 3.1 Candidate pairs

For node `A`, in roster order over every other actor `B` with `IsA(NavigationPoint) &&
!IsA(LiftCenter) && B != A` (`ued` also `!bDeleteMe`) and **straight-line `|A−B|² < 1000²`**
(`ued .rdata 0x1020296c`, `dx 0x130a64`). With `A.bOneWayPath`, `B` must be in front:
`(B−A)·A.Rotation.XAxis > 0`. `|A−B|² < 1000` only logs `WARNING: … may be too close!`. No other
node flag is read. Line of sight is required by both engines, differently: `dx` traces the world
from `A` to `B` before sizing (`findBestReachable 0xd9870`, movers included); `ued` relies on
`pointReachable`'s BSP-only `FastLineCheck` from the scout's eye (§3.4).

Retail confirms the cutoff: the longest unpruned WALK edge is 999; UED22 live connects a 900-uu
gap and not a 1000-uu one.

### 3.2 Special edges (no traversal test; linked before the ordinary pass)

| Pair                                                     | Distance | R / H     | flags | Direction |
|----------------------------------------------------------|----------|-----------|-------|---
| `LiftCenter` ↔ every `LiftExit` with the same `LiftTag`  | 500      | 60 / 60   | 0x20  | both ways; a LiftCenter gets nothing else |
| `Teleporter` → `Teleporter` whose `Tag` == this `URL`    | 100      | 150 / 150 | 0x20  | one way, first match only (both engines) |
| `WarpZoneMarker` → marker whose zone `ThisTag` == this zone's `OtherSideURL` | 100 | 150 / 150 | 0x20 | one way, first match only |

Live UED22 (`pathlab2`): `G_Center ↔ G_ExitLo/Hi` 500/60/60/SPECIAL both ways, `H_T1 ↔ H_T2`
100/150/150/SPECIAL. Retail Deus Ex has no SPECIAL edge at all (its Teleporters are map-exit
markers with plain WALK edges to their neighbours; no LiftCenter/WarpZone in any map).

### 3.3 Sizing one edge — `FReachSpec::defineFor` → `findBestReachable`

`defineFor` (`ued 0x10193cd0`, `dx 0xd95b0`) parameterises the scout, then `findBestReachable`
(`ued 0x10193dd0`, `dx 0xd96e0`) searches for the largest scout cylinder that still traverses
`A→B`; the spec records that size:

| Parameter                | `ued` | `dx` |
|--------------------------|-------|---
| abilities                | walk, jump, swim; no fly; `PHYS_Walking` | same |
| `JumpZ` / `GroundSpeed` / `MaxStepHeight` | 320 / 320 / 25 | 120 / 120 / 25 (`BaseEyeHeight` 0) |
| radius search            | start 18 (height 39), step 52, cap 70, stop when step < 2 | start 12 (height 10), step 103, cap 115, stop when step < 1 |
| height search            | at the best radius: start 44 (= 40 + 4), step 26, cap 70, floor 40, stop when step < 1 | **at radius 12**: start 10, step 69, cap 79, floor 10, stop when step < 1 — the stored (R, H) pair is never tested together |
| probe                    | `FarMoveActor(Scout, A.Location)` (real placement: world fit + encroachment) then `pointReachable(B.Location, 0)` | scout on the traced floor under `A` (probe 79 uu down; else `A.Z − A.CollisionHeight`) + its own height; `pointReachable(B, 1)` |
| stored size              | `appRound` (`cvtss2si`) of the best radius / height | `(int)` truncation |
| `Distance`               | `appRound(‖B.Location − A.Location‖)`; **×2 if `R_SWIM`** | `int(‖B − A‖)`; ×2 if `R_SWIM` |
| `reachFlags`             | the mask returned by the last successful probe | same |

The search loop, both engines:

```
size = start; step = cap − start
loop: ok = probe(size)
      if ok: best = size; size += step    else: size −= step
      step /= 2
      stop if step < limit, or size > cap after a success, or size < floor after a failure
```

The last probe therefore uses the step before the final halving, and the recorded sizes fall on a
coarse grid. The retail data sits exactly on it:

- `dx` radius ∈ `int(12 + 103·k/32)` = 12 15 18 21 24 28 31 34 37 40 44 47 50 53 57 60 63 66 69 73
  76 79 82 86 89 92 95 98 102 105 108 111 115 — the complete set of 33 radii in 128 178 retail
  specs; height ∈ `int(10 + 69·k/32)` = 10 12 14 16 … 76 79, the complete set of 33 heights ✅.
- `ued` radius ∈ `appRound({18, 24.5, 31, 37.5, 44, 50.5, 57, 63.5, 70})` = 18 24 31 38 44 50 57 64
  70 (round-half-even), height ∈ {44, 47, 50, 54, 57, 60, 64, 67, 70} — the only values in the
  live builds 🔬 (corridor width 40 → R 18, 56 → 24, 72 → 31, 96 → 44, 128 → 64, ≥ 160 → 70;
  ceiling 96 → H 44, 128 → 60, ≥ 160 → 70; ceilings ≤ 80 gave **no spec**). The code can also
  record H = 40 (or 39, the radius phase's height) when the first height probe at 44 fails; no live
  ceiling in the 81–87 band was tried.

So a UED22-built graph never records a size above 70/70, while retail carries 115/79 and heights
down to 10. Rounding vs truncation shows as `Distance` +1 on 435 of the 816 Bar edges the two
builds share.

### 3.4 The traversal test — `pointReachable` → `Reachable` → `walkReachable` ✅

`pointReachable(Dest, bKnowVisible)` (`ued 0x10183340`, `dx 0xc0d30`): in the editor there is no
range cap (`GIsEditor`; in-game 800 uu `ued` / 1000 uu `dx` 2-D); the target zone must not be water
unless the scout can swim or is already in water; no hostile pain zone; unless `bKnowVisible`, a BSP
`FastLineCheck` from the scout's eye to `Dest`; `Dest` is nudged by a test `FarMoveActor`; then
`Reachable(Dest, 15.0, NULL)`, which dispatches on the scout's zone and `Physics`: water zone →
`swimReachable`; `PHYS_Walking`/`Swimming` → `walkReachable`; `PHYS_Flying` → `flyReachable`.

`walkReachable` (`ued 0x101846e0`, `dx 0xc1b70`), the test every ordinary edge runs:

```
reachFlags |= R_WALK; MoveSize = 16 (editor; in-game CollisionRadius, or max(128, CR) if bCanJump); ticks = 100
loop while stillmoving:
    Delta = Dest − Location (2-D); DeltaZ
    if DeltaZ > CollisionHeight and 0.8·(DeltaZ − CollisionHeight)² > Dist²: fail        // too steep up
    if Dist² ≤ 15²: success iff |DeltaZ| < CollisionHeight (slope special cases); stop
    r = walkMove(step of MoveSize toward Dest, threshold 8.0 near / 4.1 far)             // 1 moved, 0 blocked or too short, −1 ledge, 5 goal
    if r ≠ 1:
        fell out of the world (ZoneNumber 0) → fail
        bCanFly → flyReachable
        bCanJump → reachFlags |= R_JUMP; ledge (−1) → FindBestJump; wall (0): ued FindJumpUp, dx nothing (loop ends, fail)
        else ledge and MoveSize > MaxStepHeight → retry with MoveSize = MaxStepHeight
    hostile pain zone → fail; entered water → swimReachable if bCanSwim
    --ticks < 0 → stop
restore position and velocity; return success ? reachFlags : 0
```

`walkMove` = `MoveActor(Delta)` with the scout's cylinder against the BSP and blocking actors
(pawns/decorations ignored; the code blocks on a Mover iff the scout has `bCollideWorld` and the
Mover `bBlockActors`, `IsBlockedBy ued 0x10113fd0`; nothing opens doors, nothing emits `R_DOOR`).
On a hit: step up `MaxStepHeight`, finish the move, step down; wall if the landing normal has
`Z < 0.7`; then a floor probe `MaxStepHeight + 2` down: no floor → −1, floor with `Normal.Z < 0.7`
→ −1. 🔬 Live, a closed `Engine.Mover` across a corridor did **not** block the UED22 build
(`pathlab2` `F_N00↔F_N01` plain WALK); whether the imported Mover had `bBlockActors` was not checked
(§9).

Jumps: `FindBestJump` runs `jumpLanding`, a ballistic simulation at `dt = 0.1` (≤ 35 steps, `|v|² ≤
2.5e6`, `ZoneGravity`/`ZoneFluidFriction`/`ZoneVelocity`), with `JumpZ` and `SuggestJumpVelocity`'s
horizontal speed; success iff the landing is > 8 uu closer to `Dest` (`dx` additionally requires a
drop < 350 uu, `0xc30ce`; `ued` has **no fall limit**). `FindJumpUp` (`ued` only) is one `walkMove`
with `MaxStepHeight` temporarily 48.

Consequences seen live (UED22, `pathlab` hall): steps of 8 and 16 uu are WALK; a climb of 32–64 uu
from the hall floor onto a platform is WALK|JUMP; a climb of ≥ 80 gets no edge; every non-stair
drop (32 … 160 uu) is WALK|JUMP, a stair descent is WALK. `swimReachable`/`flyReachable` use 3-D
arrival, step `max(200, CR)`, no floor probe; a swim edge doubles `Distance` and a water room yields
SWIM-only edges (`pathlab2` room E: 722 = 2 × round(360.6)). `swimReachable`'s climb-out branch
calls `flyReachable` and then reports exactly `R_WALK` (both engines) — the reason retail's mixed
WALK|SWIM edges are so rare.

`R_JUMP` is OR'd in *before* the jump attempt, so a non-jumping pawn cannot use any edge whose test
needed one. UED22 tags 199 of the 1017 Bar edges WALK|JUMP where the retail build has 1 (§7).

### 3.5 Bookkeeping — `insertReachSpec` ✅ (`ued 0x10179820`, `dx 0xb1d70`)

```
link(A → B, S):
    n = insertReachSpec(A.Paths, S);         if n == -1: drop S entirely
    idx = ReachSpecs.AddItem(S);             A.Paths[n] = idx
    m = insertReachSpec(B.upstreamPaths, S); if m != -1: B.upstreamPaths[m] = idx   // else one-sided: the
                                             // runtime search (upstreamPaths, §5) never sees it; CanMoveTo does

insertReachSpec(list, S):
    n = 0; while n < 16 && list[n] != -1 && ReachSpecs[list[n]].Distance > S.Distance: n++   // equal Distance: newer first
    if list[15] == -1: shift list[n..] up one slot; return n           // sorted longest-first
    if n == 0: return -1                                                // full and S is the longest: refused
    shift list[0..n-1] down one slot (evicts list[0], the longest); return n-1
```

An evicted spec is not removed from `ReachSpecs` or marked and may still sit in the other node's
array. This is why `Paths` is descending, capped at the 16 shortest, and why retail has array-less
and one-sided specs.

### 3.6 `Prune` ✅ (`ued 0x10176790`, `dx 0xb1990`), per node in `NavigationPointList` order

```
for each upstream spec α = A→node, for each downstream spec β = node→B:
    k = specFor(A, B)   // scan A.Paths for End == B; -1 if none (already pruned or never existed)
    γ = ReachSpecs[k]; σ = α + β        // Distance sum, R = min, H = min, flags = α|β
    prune γ iff  σ.Distance ≤ 1.2 · γ.Distance   (see the table for the exact compare)
             and ( σ <= γ  ||  γ.BotOnlyPath()  ||  σ.MonsterPath() )
    on prune: remove k from A.Paths (shift-compact); append k to A.PrunedPaths (slot 15 overwritten when
              full); γ.bPruned = 1; remove k from B.upstreamPaths
```

| Helper           | `ued` | `dx` |
|------------------|-------|---
| `σ <= γ`         | `σ.R ≥ γ.R && σ.H ≥ γ.H && (σ.flags ∪ γ.flags) == γ.flags` — the detour carries pawns at least as big and needs no extra ability | same |
| `BotOnlyPath()`  | `R < 24` | `R < 12` (never true: the minimum radius is 12) |
| `MonsterPath()`  | `R ≥ 52 && H ≥ 40 && !R_FLY` | `R ≥ 22 && H ≥ 51 && !R_FLY` |
| the 1.2 compare  | `float32 1.2f` (`0x10212d5c`, = 1.20000005), `comiss`/`jb`: prune iff `σ ≤ 1.2f·γ` (non-strict) | opcode `≤` (`fild/fmul/fild/fcompp`), but the constant is the double **below** 1.2 (`0x130a48` = `0x3FF3333333333333` = 1.19999999999999996) and `Core.dll` sets the x87 to 64-bit precision (`appEnableFastMath(0)` at `0x6def1` → `_controlfp(_PC_64)`), so for integer distances it is effectively **strict**: `σ < 1.2·γ` |

Pinned by data as well as by reading: `harness/simulate_bookkeeping.py` replays §3.5 + §3.6 from a
map's `ReachSpecs` and roster and reproduces **every** `bPruned` bit and every
`Paths`/`upstreamPaths`/`PrunedPaths` array on all 83 single-player retail maps (120 976/120 976
specs, `evidence/replay-results.txt`) only with `<` — `02_NYC_Bar` spec 73: direct 165, detour
50+148 = 198 = 1.2×165 exactly, not pruned — and on every UED22 live build (the three committed
goldens, 674/674, plus the two Bar rebuilds) with `≤`; only the uncommitted Bar rebuild has an
edge exactly at 1.2×, and it is pruned there. The largest retail ratio actually pruned is 1.199737.

### 3.7 `addVisNoReach` ✅ (`ued 0x101774e0`, `dx 0xb1e50`)

For every node (not LiftCenter): scout sized 18×39 (`ued`) / 22×51 (`dx`) at the node; walk
`NavigationPointList` and take the first 16 other nodes within 2000 uu that are line-visible
(`SingleLineCheck` clear) but whose `findPathToward` from the scout either fails (weight taken as
2e8) or ends with a weight > 2 × the straight distance; a found route whose node still carries the
`10000000` sentinel is skipped. Result → `VisNoReachPaths[]`. Running the runtime search from every
node is what leaves the residue of §1.3 in the saved map. Nothing reads `VisNoReachPaths` at
runtime.

## 4. Automatic PathNode placement (`PATHS BUILD` only)

### 4.1 `ued` — `createPaths` (`0x10177900`) ✅ 🔬 — `findings/10-ued-pathbuilder.md` §4.12–4.20

Three passes with a scout set to `JumpZ −1`, `GroundSpeed 320`, `MaxStepHeight 24`:

1. **Wall-following walk** (`testPathsFrom` → `Pass2From`) from every `InventorySpot` and
   `PlayerStart` (log `----Starting From <name>`), for radii 70, 63, … 28 (step 7) at height 40 (`WALK
   WITH COLLISION SIZE r 40`), alternating the initial direction X/Y. The scout walks 16-uu steps to
   the first wall, turns along it, keeps an "anchor" node it can still reach (`Anchor <node>`); when
   it loses the anchor it looks for a node within 256 uu that is reachable from the scout, from the
   old anchor and from the previous spot; failing that, a node within 50 uu is **moved** to the
   scout's previous spot or the midpoint (hand-placed nodes included), else a PathNode is spawned
   (`newPath`: `bAutoBuilt=1`, 48 uu above the floor; `Added new path PathNodeK at x y`). Limits:
   200 steps per walk (`Total steps out of bounds`, which sets the stall counter to 2000 — the
   logged `Num steps 2000`), 1000 stalls, 2 turns.
2. **Merge**: for each `bAutoBuilt` node `A` and node `B` within 128 uu, line-visible and with
   `TestReach(A→B)` by a 52×40 scout: every neighbour `C` of `A` (within 800 uu, reachable from
   `A`) must stay reachable from the midpoint (tested when `B.bAutoBuilt`) or from `B`; then the
   `bAutoBuilt` one is destroyed and the survivor is **moved to the midpoint** unless a neighbour
   needed `B` — a hand-placed survivor included.
3. **Gap fill**: for every visible, walkable (`A→B`) pair of nodes more than 600 uu apart (`Found
   potential distant pair`), if no third node `C` satisfies `|A−C| < |A−B|`, `|B−C| < |A−B|`,
   `|A−C|+|C−B| < 1.3·|A−B|`, line-visible from both and reachable `A→C` and `C→B` (`Try C …
   Found C as intermediate`), spawn a PathNode at the midpoint. It runs whether or not `A→B`
   already has a spec.

Live: on the 8192-uu corridor with gaps 100..1200 the build added 8 nodes at the midpoints of the
700..1200 gaps and then split the 1200 gap twice more; the Bar gained 8 auto nodes + 22 (broken)
InventorySpots, 889 → 1017 specs. The `opt` argument is dead.

### 4.2 `dx` — the Unreal-1 explorer (`0xb2b70`) ✅ (structure), 🔬 (handedness untested live)

`buildPaths` allocates 3000 `FPathMarker` records (0x28 bytes: `Location`, `Direction`, flag
DWORD, radius, budget, weight). Existing PathNodes become permanent markers; from every `Pawn` and
`Inventory` the scout (115×10) walks +X to a wall and follows walls in 16-uu steps, probing for a
"left passage" every step, dropping *marked* markers at left turns whose previous mark is no
longer reachable (`fullyReachable`, both ways, and no single marked waypoint bridges), at stairs
(`ΔZ > MaxStepHeight + 1`) and where a previously visible beacon becomes occluded; it stops on a
marker within R/2 with the same direction or after 360° of turning. Marked markers within ≈ 162.6
uu (`26450`) that a 12×10 scout can walk between both ways merge into their weighted midpoint; a
marker with no floor within `MaxStepHeight + 10` is dropped. Surviving non-permanent markers become
PathNodes 48 uu above the floor (no `bAutoBuilt` exists). Full pseudocode:
`findings/20-dx-pathbuilder.md` §3.7–3.26. Retail maps carry no trace of it (every node is a plain
`PathNode`), so whether the designers used it is unknowable from the data.

## 5. The consumer — what the built data must satisfy (`dx`) ✅

`findings/21-dx-reachability-and-ai.md`. `APawn::findPathTo/findPathToward` (`0xdc1d0`/`0xdb3f0`):
collect up to 32 nodes near the pawn and 32 near the goal (🔬 an 800-uu radius, read as `640000`
in `FindVisiblePaths 0xda472` by one reading and not found as a literal by another); pick the
pawn's anchor (a node it stands on — `execactorReachable` uses `max(CR, 48)` horizontally and
`CollisionHeight` vertically) or the nearest visible, `pointReachable` node (marked `bEndPoint`,
`bestPathWeight` = distance); `expandAnchor` marks the anchor's `Paths` and `PrunedPaths`
neighbours that `supports()` the pawn as end points too (anchor `cost = 1000000`); then
`breadthPathFrom` — a Dijkstra with a sorted intrusive list — runs **backwards from the goal-side
node along `upstreamPaths`** with `w = visitedWeight(cur) + spec.Distance + next.cost
[+ next.bestPathWeight if bEndPoint]`, `cost = ExtraCost` (or the `SpecialCost` event with
`bSpecialCost`), `bPlayerOnly` nodes skipped for non-players, until it pops a `bEndPoint` node — the
next node the pawn should walk to. Limits: 500 insertion steps, 1000 advances, 4 with `bSinglePath`.
Script receives only that first node and re-runs the search per node; `RouteCache` is dead
(`SetRouteCache` logs "tell Doug").

Read at runtime: every spec field except `bPruned`; `Paths` (adjacency, anchor expansion,
`CanMoveTo`, `GetPathnodeList`), `upstreamPaths` (the route search), `PrunedPaths` (anchor
expansion and `CanMoveTo` only), `nextNavigationPoint`/`NavigationPointList`, `ExtraCost`,
`bSpecialCost`, `bPlayerOnly`. Never read: `VisNoReachPaths`, `bEndPointOnly`, `bNeverUseStrafing`,
`taken`, `ownerTeam`, `bOneWayPath` (builder input only). Doors matter here, not at build time:
`CanMoveTo`/`expandAnchor` line-trace the edge and reject a Mover hit unless the pawn has
`bCanOpenDoors` (and, for a non-player, the Mover's `bPlayerOnly` is clear).

For a pawn standing on a node, `actorReachable(node)` is answered from the graph alone
(`execactorReachable 0xbc1a0`, `CanMoveTo`), no physics — a missing or `supports`-failing spec is a
hard "unreachable" for the AI.

## 6. Verification

- **Retail corpus** (`harness/retail_stats.py`, `evidence/retail-stats.txt`): 88 maps, 16 151
  nodes, 128 178 specs. `Distance = int(euclid)` on 127 383, `2·int(euclid)` on the 791 SWIM edges,
  4 stale edges whose endpoint was moved after the build. Flags: WALK 125 879, WALK|JUMP 1 508, SWIM
  784, WALK|SWIM 5, WALK|SWIM|JUMP 2 — no FLY/DOOR/SPECIAL/PLAYERONLY. Radii/heights exactly the
  §3.3 grids. Descending order, 16-cap, evicted-are-the-longest and prune ≤ 1.2 hold with zero
  exceptions.
- **Replay** (`harness/simulate_bookkeeping.py`, `evidence/replay-results.txt`): §3.5 + §3.6
  reproduce every retail single-player map and every UED22 live build bit-for-bit (§3.6).
- **Live UED22** (`harness/live_paths.py`, `harness/make_trunk.py`, `evidence/*.dx`,
  `evidence/*-log-excerpt.txt`, `findings/50-live-ued22.md`): synthetic levels probing the distance
  cutoff, step/jump thresholds, water, doors, lifts, teleporters, pickups, node flags, corridor
  widths and ceiling heights; `02_NYC_Bar` reloaded (reachspecs survive `MAP LOAD`+`MAP SAVE`
  byte-for-byte), re-DEFINEd and re-BUILT (uncommitted outputs, reproducible with `live_paths.py`).
- **Class/defaults/on-disk** (`harness/scriptside.py`, `findings/30-script-side.md`): both `Engine.u`
  versions, tag encoding, script callers of the natives.

## 7. `ued` vs `dx` — what a UED22 path build changes for a Deus Ex map

Rebuilding `02_NYC_Bar` in UED22 (`PATHS DEFINE`): 867 specs vs 889 retail, 816 shared pairs; on
those, `CollisionHeight` differs on 816, `CollisionRadius` on 736, `Distance` on 435, flags on 95,
`bPruned` on 79. The mechanisms:

| Difference | Effect on the Deus Ex AI (`supports`, §1.1 / §5) |
|------------|---
| size caps 70/70 vs 115/79; retail records heights down to 10, UED22 gives low ceilings no edge | any pawn with radius > 70 or height > 70 fails `supports` on every UED22 edge; low-ceiling edges are absent for everyone |
| `R_JUMP` on every non-stair drop or climb | `ScriptedPawn` has `bCanJump=False`: 199/1017 Bar edges become unusable for NPCs (retail: 1). 🔬 Why the `dx` build does not flag the same drops is not established (candidates: the scout starts on the traced floor with `JumpZ` 120 and the 350-uu limit; `dx`'s `walkReachable` was read, not run) |
| `Distance` rounded vs truncated | +1 on ~half the edges; changes route costs and the prune outcome (79 Bar edges) |
| prune `≤` vs effectively `<` | boundary cases only |
| `InventorySpot` per `Inventory` at a garbage location | 22 junk nav actors on the Bar; harmless to routing (no specs), wrong for parity |
| `PATHS BUILD` auto nodes + moved survivors | new `bAutoBuilt` actors (a 469-only property); `dx`'s own BUILD instead deletes every PathNode |
| residue fields | same mechanism in both; values differ per search |

So a byte-faithful reproduction of a retail graph needs the `dx` rules (§3 with the `dx` column),
not the editor's; the editor's `PATHS DEFINE` is a different, coarser builder.

## 8. Corrections to earlier docs

`dev/docs/spikes/2026-07-15-native-materialize/sections/30-ulevel-paths-assembly.md` §4 and the
`PATHS` entry of `dev/docs/unrealed/commands.md` (correction pending the owner's yes, board item
`ued22-path-build-differs-from-the-deus-ex`): `PATHS DEFINE` builds the reachspecs (not markers
only); `createPaths` is the auto-placer, not the connector; the pair cutoff is 1000 uu (128²/800²
are `createPaths`' merge radii); `supports` is pawn ⊇ spec; the size sweep is a binary search;
`Distance` is rounded (`ued`) / truncated (`dx`) and doubled for swim; `MaxStepHeight` is 25 in
every spec test; 48 is `FindJumpUp`'s step-up; `R_DOOR=16`/`R_PLAYERONLY=64` are confirmed by
`calcMoveFlags`; `Paths` is descending, not "compact-sorted"; the on-disk
`nextNavigationPoint`/`NavigationPointList`/`visitedWeight`/`bestPathWeight` are real and must be
written; LOWOPT/HIGHOPT do nothing.

## 9. Open questions

- `dx` explorer handedness (`exploreWall` starts `followWall` with `R(N)`, `followWall` turns
  `L(N)`): needs a live `PATHS BUILD` in a Deus Ex editor or `UModel::LineCheck`'s normal sign.
- Movers: the code says a `bBlockActors` Mover blocks the scout; live, a closed `Engine.Mover` did
  not. Check the imported Mover's collision flags, or re-run with an explicit `bBlockActors=True`.
- `FarMoveActor(bTest=1)`: one reading (`dx`, `findings/20` §3.6) has it leave the actor in place,
  another (`ued`, `findings/11` §5) has it move; it decides where `findScoutStart`'s fallback and
  `addVisNoReach`'s scout actually stand on `dx`.
- Why `dx` flags so few drops `R_JUMP` (§7); `ued`'s merge/"closest path" moves of hand-placed
  nodes were read, not exercised live.
- Whether the retail designers ever ran `PATHS BUILD` (no data trace either way); the residue
  attribution in §1.3 is inferred from the search code, not observed instruction by instruction.
- `ReachablePathnodes` script argument order (`dx` only; unused by any builder).
