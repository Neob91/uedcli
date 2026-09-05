# `dx-engine` FPathBuilder — the Deus Ex path builder

Binary: `dx-engine` (Deus Ex 1112fm `Engine.dll`, base `0x10300000`). All RVAs below are in that
image unless prefixed `dx-editor`. Exports are `jmp` thunks; the RVAs cited are the real bodies.
Every function listed in the assignment was read to its `ret`. Confidence marks per
`00-method.md`: ✅ read from the code · 🔬 inferred, inference stated · 📖 public-UE1 hypothesis.

## 0. Entry points (`dx-editor` `PATHS` exec, `0x7ed6e`–`0x7f233`) ✅

| Command | Does |
|---------------------|--------------------------------------------------------------------|---
| `PATHS BUILD [LOWOPT\|HIGHOPT]` | `opt = 1`, `LOWOPT → 0`, `HIGHOPT → 2` (`0x7edbe`–`0x7ee1c`); `removePaths(Level)`; `n = buildPaths(Level, opt)`; log `Built Paths: %d` |
| `PATHS SHOW` / `HIDE` | `showPaths` / `hidePaths`; log ` %d Paths are visible!` / ` %d Paths are hidden!` |
| `PATHS REMOVE` | `removePaths`; log `Removed %d Paths` |
| `PATHS UNDEFINE` | `undefinePaths` |
| `PATHS DEFINE` | `undefinePaths` then `definePaths` (`0x7f1eb`, `0x7f201`) |

So `PATHS BUILD` only *places* PathNodes (with a scout walk); `PATHS DEFINE` only *connects* them
(reachspecs). `opt` is logged in `createPaths` and otherwise unused (see §3.9).

## 1. Layouts

### FPathBuilder (`this`) ✅

| Off | Field | Evidence |
|-------|------------------------|-------------------------------------------------------|---
| `+0` | `FPathMarker* markers` | `buildPaths 0xb0c62` stores the `GMalloc` result |
| `+4` | `ULevel* Level` | every entry point stores its arg here (`0xb0c28`) |
| `+8` | `AScout* Scout` | `getScout 0xb3381/0xb33f9` |
| `+0xc` | `INT numMarkers` | `buildPaths 0xb0c25` zeroes it; `addMarker 0xb5916` bumps it |

`ULevel`: `Actors` data `+0x2c`, count `+0x30`; `ReachSpecs` TArray at `+0x8c` (data `+0x8c`,
num `+0x90`, max `+0x94`), element size `0x1c` (`FArray::Realloc(0x1c)` at `0xb0fc6`,
`FArray::Add(1,0x1c)` at `0xb2345`). ✅

`ULevel` vtable slots used (vtable `??_7ULevel@@6BUObject@@@` at `0x128afc`) ✅:
34 `MoveActor`, 35 `FarMoveActor`, 36 `DropToFloor`, 37 `DestroyActor`, 39 `SpawnActor`,
43 `SetActorZone`, 48 `SingleLineCheck`.

Argument order of `SingleLineCheck` confirmed from `AActor::execTrace` (`0xe34e0`–`0xe3501`):
`(FCheckResult& Hit, AActor* Source, const FVector& End, const FVector& Start, DWORD Flags,
FVector Extent)` ✅. `FarMoveActor(Actor, Loc, bTest, bNoCheck)`: 3rd arg gates the location
write (`0x98d27`), 4th gates the encroach check (`0x98c3b`) ✅. `MoveActor(Actor, Delta, Rot,
Hit, bTest, bIgnorePawns, bIgnoreBases, bNoFail)`: 5th skips base-moving (`0x998ae`), 6th
ignores Pawn/Decoration hits (`0x995ea`), 7th `IsBasedOn` (`0x99651`), 8th (`0x997be`) 🔬.

### FPathMarker (0x28 bytes; 3000 allocated: `GMalloc->Malloc(0x1d4c0, "FPathMarker")` at `0xb0c34`) ✅

| Off | Type | Role (name by use) | Evidence |
|--------|---------|-----------------------------------------------|------------------------------------------------------|---
| `+0x00` | FVector | `Location` | every distance test reads `[m+0]`,`[m+4]`,`[m+8]` |
| `+0x0c` | FVector | `Direction` (walk direction when dropped; `(0,0,0)` for PathNode markers) | `createPaths 0xb2c3e`, `followWall 0xb5ca8`, `checkObstructionFrom 0xb4acb` |
| `+0x18` | DWORD | bit-flags, below | |
| `+0x1c` | float | `radius` — max scout radius that fits (12 written in `mergePath 0xb418e`; `min(A,B)` used as collision radius in `checkmergeSpot 0xb3b9c`, `markReachableFromTwo 0xb3e59`) | |
| `+0x20` | float | `budget` — remaining path distance when last visited by `tryPathThrough` (`0xb6ee8`); reset to 0 by `findPathTo 0xb7154` | |
| `+0x24` | float | `weight` — merge count; set 1.0 on creation, `+1.0` per merge (`mergePath 0xb47da`); weighted midpoint in `mergePath 0xb4362` | |

Flag bits of `+0x18` (roles inferred from every reader/writer; names are ours) ✅ bits, 🔬 names:

| Bit | Role | Set by | Cleared by / tested by |
|--------|-----------------------|---------------------------------------------------------------|-------------------------------------------------------|---
| `0x01` | `visible` — line of sight / reachable from the current spot | `markLeftReachable` (trace clear), `markReachable`, `markReachableFromTwo` | `markLeftReachable`; tested in `checkObstructionFrom`, `needPath`, `checkmergeSpot` |
| `0x02` | `obstruction` — needs `checkObstructionFrom` in `createPaths` | PathNode markers, left-turn, obstruction, new-obstruction markers | cleared after the check (`0xb2e56`) |
| `0x04` | `bigVisible` — reachable with the larger radius | `markReachableFromTwo` only (dead) | tested `checkmergeSpot`, `markReachableFromTwo` |
| `0x08` | `beacon` — candidate for visibility/`needPath`/`markReachable` tests | PathNode, left-turn, stairway, right-turn markers | tested `markReachable`, `needPath`, `checkmergeSpot` |
| `0x10` | `marked` — becomes a PathNode | PathNode, left-turn, stairway markers | cleared by `mergePath` (merged-away or floating); tested everywhere |
| `0x20` | `permanent` — pre-existing PathNode, never spawned/merged away | `createPaths 0xb2c61` | `createPaths 0xb2ea4`, `mergePath` |
| `0x40` | unknown; set on `markers[0]` when a stairway marker is dropped (`0xb5e67`, looks like a bug: writes marker 0, not the new marker) | | cleared on new markers |
| `0x80` | `leftSeen` — cleared for markers within 800 of every step | | `markLeftReachable 0xb55a2` clears; `sawNewLeft` skips markers with it |

`addMarker` treats a slot as free when `flags & 0x3a == 0` (`0xb5926`).

### FReachSpec (0x1c bytes) ✅

`+0 INT distance`, `+4 AActor* Start`, `+8 AActor* End`, `+0xc INT CollisionRadius`,
`+0x10 INT CollisionHeight`, `+0x14 INT reachFlags`, `+0x18 BYTE bPruned`.
Evidence: `Init` (`0x44c80`) zeroes exactly these; `specFor` compares `+8` with the End arg;
`Prune 0xb1b6f` sets byte `+0x18`; `findBestReachable 0xd9b04/0xd9b0f/0xd9b60` writes `+0xc`,
`+0x10`, `+0`; `operator+` adds `+0`.

`FCheckResult` (0x2c): `+0 Next, +4 Actor, +8 Location, +0x14 Normal, +0x20 Primitive,
+0x24 Time (init 1.0), +0x28 Item (init -1)` ✅ (every stack init in the builder).

### Actor / Pawn / NavigationPoint offsets used (`layout.py dx`) ✅

`Actor`: `Physics +0x30`, `Tag +0xb0`, `XLevel +0xac`, `Region.Zone +0xc8`, `Location +0x114`,
`Rotation +0x120`, `DrawType +0x164`, `CollisionRadius +0x1d4`, `CollisionHeight +0x1d8`,
`bCollideWorld +0x1dc&2`. `Pawn`: `bCanDoSpecial +0x318&0x20000`, `bCanJump|bCanWalk|bCanSwim =
0x7000`, `bCanFly 0x8000`, `MoveTarget +0x34c`, `GroundSpeed +0x378`, `JumpZ +0x388`,
`MaxStepHeight +0x38c`, `BaseEyeHeight +0x3f4`. `NavigationPoint`: `upstreamPaths +0x320`,
`Paths +0x360`, `PrunedPaths +0x3a0`, `VisNoReachPaths +0x3e0` (all `[16]`), `visitedWeight
+0x420`, `nextNavigationPoint +0x42c`, `nextOrdered +0x430`, `prevOrdered +0x434`, `startPath
+0x438`, `previousPath +0x43c`, `bOneWayPath +0x448&0x10`. `LevelInfo.NavigationPointList +0x548`.
`LiftCenter/LiftExit.LiftTag +0x44c`, `Teleporter.URL +0x44c` (FString), `WarpZoneMarker.
markedWarpZone +0x44c`, `WarpZoneInfo.OtherSideURL +0x474`, `.ThisTag +0x480`,
`InventorySpot.markedItem +0x44c`, `Inventory.myMarker +0x398`.
**`PathNode` has no own fields (`PropertiesSize 0x44c` = NavigationPoint): no `bAutoBuilt` in DX.** ✅

## 2. Constants ✅

| Value | Where | Meaning |
|---------------------|--------------------------------------------------------|---------------------------------------------|---
| `3000` / `0x28` | `buildPaths 0xb0c4b/0xb0c50` | marker pool count / stride |
| `2999`, `2990` | `addMarker 0xb5908/0xb5966` | pool full threshold; "ADDED MARKER #" log threshold |
| `320.0`, `-1.0`, `24.0` | `buildPaths 0xb0c9c/0xb0c8c/0xb0cac` | Scout `GroundSpeed`, `JumpZ`, `MaxStepHeight` for the walk |
| `120.0`, `120.0`, `25.0` | `defineFor 0xd95e8/0xd9604/0xd960a` | Scout `JumpZ`, `GroundSpeed`, `MaxStepHeight` for reachspecs |
| `12`, `10` | `SetCollisionSize` everywhere | small scout (radius, height) |
| `115`, `52`, `22/51`, `20` | `exploreWall`, `mergePath`, `addVisNoReach`, `definePaths` | big scout radius; medium radius; visnoreach scout; WarpZone retry radius |
| `48.0` | `newPath 0xb31e3` | spawn PathNode 48 above floor when scout height < 48 |
| `16.0` | all `walkMove` deltas | step length |
| `4.1` | all `walkMove` calls | `walkMove` threshold |
| `6.0` | `checkLeftPassage 0xb76cb` | forward probe step between left checks |
| `10.0` (`0x130ab0` f64) | `checkLeft 0xb7329` | min sideways travel to count as a passage |
| `2.0` (`0x130aac`) | `followWall 0xb5b71` | initial `prevLoc` offset |
| `90.0`, `360.0` | `followWall` | turn-angle bookkeeping / loop-closure test |
| `1e-8` (`0x12d538` f64) | `followWall`, `checkObstructionFrom`, `walkToward` | normalisation guard |
| `1e-4` (`0x12ac40` f64) | `followWall 0xb62da` | "same direction" tolerance |
| `0.25` (`0x12d528`) | `followWall 0xb6115` | near-marker test `(R/2)²` |
| `4.0` (`0x130a80` f64) | `oneWaypointTo 0xb5707` | `(2R)²` |
| `640000.0` (`0x130a74`) | `markReachable`, `markLeftReachable`, `needPath`, `sawNewLeft`, `markReachableFromTwo` | 800² search radius |
| `26450.0` | `mergePath 0xb4195` | merge distance² (≈162.6) |
| `800.0` (`0x130ac0`) | `boundedReachable 0xb78ca` | distance² bound (≈28.3) |
| `0.7` (`0x12adc0` f64) | `findScoutStart` | walkable floor `Normal.Z` |
| `-50.0`, `50` | `findScoutStart 0xb3559/0xb3785` | drop step; max iterations |
| `20.0` (`0x130a6c`) | `createPathsFrom 0xb3976` | retry start 20 higher |
| `5.0` (`0x12ada8` f64) | `findPathTo 0xb713a` | budget = dist + 5·R |
| `15.0` | `fullyReachable 0xb7ac5` | `walkReachable` threshold |
| `6.0` (`0x130ac8` f64) | `fullyReachable 0xb79eb/0xb7b26` | scout radius −6 during the test |
| `79.0`, `115.0`, `12`, `10` | `findBestReachable` | height/radius search bounds |
| `0.5` (`0x12ac10` f64) | `findBestReachable` | bisection step halving |
| `1000000.0` (`0x130a64`), `1000.0` (`0x130a60`) | `addReachSpecs 0xb2729/0xb2825` | 1000² candidate radius; "too close" warning at < √1000 ≈ 31.6 |
| `4000000.0` (`0x130a5c`), `4.0`, `1e7`, `2e8` | `addVisNoReach` | 2000² radius; `visitedWeight² > 4·dist²`; sentinel weights |
| `1.2` (`0x130a48` f64) | `Prune 0xb1aa4` | prune factor |
| `500`,`60`,`0x20` / `100`,`150`,`0x20` | `addReachSpecs` | lift spec / teleporter+warpzone spec |
| `300` (`0x12c`) | `pathDebugf 0xb313a` | debug log gate |

## 3. Pseudocode

Conventions: `L(d) = (-d.Y, d.X, 0)` is what the code calls "left" (`checkLeftPassage 0xb765b`
builds exactly this); `R(d) = (d.Y, -d.X, 0)`. `Scout` = `this->Scout`; `Level` = `this->Level`.
`walkMove(Delta, Hit, GoalActor, threshold, bAdjust)` is `APawn::walkMove` (`0xc3290`): returns
`1` when the pawn advanced more than `threshold` (`0xc3711`–`0xc3764`), `0`/`-1`/`5` otherwise
(not decoded further). `pathDebugf` = unexported `0xb3130`: `if (g_0x1058c14c <= 300)
GLog->Logf(0x2f8, fmt, ...)` — the global's meaning was not identified 🔬.

### 3.1 buildPaths(ULevel* Level, INT opt) — `0xb0c00` ✅

```c
numMarkers = 0; this->Level = Level;
markers = GMalloc->Malloc(3000 * 0x28, "FPathMarker");            // 0xb0c34
getScout();
Scout->SetCollision(1, 1, 1); Scout->bCollideWorld = 1;
Scout->JumpZ = -1.0; Scout->GroundSpeed = 320.0; Scout->MaxStepHeight = 24.0;   // 0xb0c8c..0xb0cac
INT n = createPaths(opt);
Level->DestroyActor(Scout, 0);                                     // vtable slot 37
return n;                                                          // (markers is never freed — no Free call in the function)
```

### 3.2 definePaths(ULevel*) — `0xb1280` ✅

```c
this->Level = Level; getScout();
LevelInfo->NavigationPointList = NULL;
Logf("Add WarpZone and Inventory markers");                        // only WarpZones are handled
for (A in Level->Actors) if (A && A->IsA(AWarpZoneInfo)) {
    if (!(findScoutStart(A->Location) && Scout->Region.Zone == A->Region.Zone)) {
        Scout->SetCollisionSize(20, Scout->CollisionHeight);
        if (!(findScoutStart(A->Location) && Scout->Region.Zone == A->Region.Zone))
            Level->FarMoveActor(Scout, A->Location, /*bTest*/1, /*bNoCheck*/1);   // 0xb140f: test-only, scout not moved
        Scout->SetCollisionSize(12, Scout->CollisionHeight);
    }
    M = Level->SpawnActor(WarpZoneMarker class, NAME_None, NULL, NULL, Scout->Location, rot(0,0,0), NULL, 0, 0);
    M->markedWarpZone = A;                                         // 0xb14bc
}
Logf("Add reachspecs");
for (A in Level->Actors) if (A && A->IsA(ANavigationPoint)) {
    A->nextNavigationPoint = LevelInfo->NavigationPointList; LevelInfo->NavigationPointList = A;   // list is built in reverse actor order
    addReachSpecs(A); Logf("Added reachspecs to %s", A->Name);
}
Logf("Added %d reachspecs", ReachSpecs.Num()); Logf("Prune reachspecs");
INT pruned = 0; for (N = NavigationPointList; N; N = N->nextNavigationPoint) pruned += Prune(N);
Logf("Pruned %d reachspecs", pruned);
for (N = NavigationPointList; N; N = N->nextNavigationPoint) addVisNoReach(N);
Level->DestroyActor(Scout, 0); Logf("All done");
```

No InventorySpot / TriggerMarker / ButtonMarker is ever spawned here (the loop tests only
`AWarpZoneInfo`, `0xb1363`); nothing in `dx-engine` FPathBuilder references `AInventorySpot`
except `undefinePaths`. No `bAutoBuilt` exists. ✅

### 3.3 undefinePaths(ULevel*) — `0xb0f60` ✅

```c
Logf("Remove %d old reachspecs", ReachSpecs.Num()); ReachSpecs.Empty();      // Num=Max=0, Realloc(0x1c)
LevelInfo->NavigationPointList = NULL;
for (A in Actors) if (A && A->IsA(ANavigationPoint)) {
    if (A->IsA(AWarpZoneMarker) || A->IsA(ATriggerMarker) || A->IsA(AInventorySpot) || A->IsA(AButtonMarker)) {
        if (A->IsA(AInventorySpot) && A->markedItem) A->markedItem->myMarker = NULL;
        Level->DestroyActor(A, 0);
    } else {
        A->nextNavigationPoint = nextOrdered = prevOrdered = startPath = previousPath = NULL;   // +0x42c..+0x43c
        for (i < 16) { Paths[i] = upstreamPaths[i] = PrunedPaths[i] = -1; VisNoReachPaths[i] = NULL; }
    }
}
```

### 3.4 removePaths / showPaths / hidePaths ✅

`removePaths` (`0xb0d70`): destroys **every** `APathNode` (no `bAutoBuilt` filter), returns the
count. `showPaths` (`0xb0e60`) / `hidePaths` (`0xb0ee0`): set `DrawType = 1` (sprite) / `0` on
every `APathNode`, return the count.

### 3.5 getScout — `0xb3320` ✅

```c
Scout = first actor IsA(AScout) in Actors, else SpawnActor(Scout class, NAME_None, 0, 0, (0,0,0), (0,0,0), 0, 0, 0);
Scout->SetCollision(1,1,1); Scout->bCollideWorld = 1;
Level->SetActorZone(Scout, 1, 1);                                  // slot 43
```
Collision size is **not** set here (AScout defaults apply until the first `SetCollisionSize`).

### 3.6 findScoutStart(FVector loc) — `0xb34d0` ✅

```c
if (!Level->FarMoveActor(Scout, loc, 0, 0)) { Logf("Scout didn't fit"); return 0; }
Hit = {Normal=(0,0,0), Time=1, Item=-1}; Delta = (0,0,-50);
for (iter = 0; iter < 50; iter++) {                                // 0xb3785
    if (Hit.Normal.Z >= 0.7) return 1;
    Level->MoveActor(Scout, Delta, Scout->Rotation, Hit, /*bTest*/1, /*bIgnorePawns*/1, 0, 0);
    if (Hit.Time < 1.0 && Hit.Normal.Z < 0.7) {                     // hit a wall/slope: slide
        Old = Hit.Normal;
        Slide = (Delta - Hit.Normal * (Delta | Hit.Normal)) * (1 - Hit.Time);
        if ((Slide | Delta) >= 0) {                                 // 0xb3687
            MoveActor(Scout, Slide, Rot, Hit, 1, 1, 0, 0);
            if (Hit.Time < 1.0 && Hit.Normal.Z < 0.7) {
                Scout->TwoWallAdjust(Delta.SafeNormal(), Slide, Hit.Normal, Old, Hit.Time);
                MoveActor(Scout, Slide, Rot, Hit, 1, 1, 0, 0);
            }
        }
    }
}
Logf("No valid start found"); return 0;
```
Because every `MoveActor` is a test move (5th arg = 1, see §1), the scout stays at `loc`; the loop
re-tests the same 50-unit drop up to 50 times. 🔬 (arg role) / ✅ (arg values).

### 3.7 createPaths(INT opt) — `0xb2b70` ✅

```c
numMarkers = 0; created = 0;
for (A in Actors) if (A && A->IsA(APathNode)) {                    // pass 1: existing PathNodes → permanent markers
    pathDebugf("Found a Pathnode");
    m = &markers[addMarker()]; m->Location = A->Location; m->Direction = (0,0,0); m->weight = 1.0;
    m->flags = (m->flags & ~0x64) | 0x1a; m->flags |= 0x20;         // obstruction|beacon|marked|permanent
}
for (A in Actors) if (A && (A->IsA(APawn) || A->IsA(AInventory))) {  // pass 2: explore from every pawn and item
    Logf("----------------------Starting From %s", A->Name); createPathsFrom(A->Location);
}
pathDebugf("Markers before obstruction check = [%6d]", numMarkers); pathDebugf("Check obstructions----…");
for (i < numMarkers) if (markers[i].flags & 0x02) {                 // note: numMarkers may grow inside
    pathDebugf("Check obstruction at [%6d]", i); pathDebugf("Out of [%6d]", numMarkers);
    checkObstructionFrom(&markers[i]); markers[i].flags &= ~0x02;
}
for (i < numMarkers) if (markers[i].flags & 0x10) mergePath(i);
pathDebugf("Build Paths");
for (i < numMarkers) if ((markers[i].flags & 0x10) && !(markers[i].flags & 0x20)) { newPath(markers[i].Location); created++; }
for (A in Actors) if (A && A->IsA(APawn)) A->SetCollision(1,1,1);   // restore (nothing in the builder turns it off — leftover)
pathDebugf("Optimization Level = [%6d]", opt); pathDebugf("Number of Markers = [%6d]", numMarkers);
return created;
```
`opt` ([ebp+8]) is read once, at `0xb2f0f`, for the log line. ✅

### 3.8 createPathsFrom(FVector start) — `0xb3900` ✅

```c
if (!(findScoutStart(start) && fabs(Scout->Location.Z - start.Z) <= Scout->CollisionHeight)) {
    start.Z += 20; if (!findScoutStart(start)) return;
}
exploreWall(FVector(1, 0, 0));                                     // always start walking +X
```

### 3.9 newPath(FVector loc) — `0xb31b0` ✅

```c
if (Scout->CollisionHeight < 48) loc.Z += 48 - Scout->CollisionHeight;
P = SpawnActor(PathNode class, NAME_None, NULL, NULL, loc, rot(0,0,0), NULL, /*bNoCollisionFail*/0, 0);
for (i < 16) P->Paths[i] = P->upstreamPaths[i] = -1;               // nothing else is set: no bAutoBuilt, PrunedPaths untouched
```

### 3.10 addMarker() — `0xb58e0` ✅

```c
if (numMarkers < 2999) numMarkers++;
else {                                                             // pool full: recycle
    found = 0;
    for (j = 0; j < 3000 && !found; j++)
        if (!(markers[j].flags & 0x3a)) { markers[j] = markers[numMarkers-1]; found = 1; }   // copy the last marker into a free slot
    pathDebugf("RAN OUT OF MARKERS!");                              // 0xb5956: printed on both outcomes (loop-exit test inverted)
}
if (numMarkers > 2990) pathDebugf("ADDED MARKER # [%6d]", numMarkers);
return numMarkers - 1;                                             // caller fills this slot
```

### 3.11 exploreWall(FVector dir) — `0xb4dd0` ✅

```c
Scout->SetCollisionSize(115, 10);
while (Scout->walkMove(dir * 16, Hit, NULL, 4.1, 0) == 1) ;        // walk until blocked
FVector N = -dir; FindBlockingNormal(N);                            // N := normal of what blocks (see 3.12)
INT before = numMarkers;
followWall(FVector(N.Y, -N.X, 0));                                  // = R(N); with N ≈ -dir this is L(dir)
pathDebugf("New paths created [%6d]", numMarkers - before);
```

### 3.12 FindBlockingNormal(FVector& N) — `0xb6a30` ✅

```c
Extent = (R, R, H)  (Scout CollisionRadius/Height);
SingleLineCheck(Hit, Scout, End = Scout->Location - N*16, Start = Scout->Location, 6, Extent);
if (Hit.Time < 1.0) { N = Hit.Normal; return; }                    // wall ahead
Ahead = Scout->Location - N*16;
SingleLineCheck(Hit, Scout, End = Ahead + (0,0,-MaxStepHeight), Start = Ahead, 6, Extent);
if (Hit.Time < 1.0) { Logf("Found landing when looking for ledge"); return; }   // N unchanged
SingleLineCheck(Hit, Scout, End = Ahead + (0,0,-MaxStepHeight), Start = Scout->Location + (0,0,-MaxStepHeight), 6, Extent);
if (Hit.Time < 1.0) N = Hit.Normal;                                // ledge face one step down
```

### 3.13 followWall(FVector dir) — `0xb5a50` ✅ (the wall-following walk; the unwind name is `FPathBuilder::followWall`)

```c
lastPathMark = lastMarked = Scout->Location; moveResult = 1; keepGoing = 1; turnAngle = 0; rightTurnMade = 0;
INT last = 0;                                                      // index of the marker dropped last (edi)
pathDebugf("Following wall [scout]");
prevLoc = Scout->Location + (2,2,2);
while (keepGoing) {
    prevLoc = Scout->Location; savedDir = dir;
    if (checkLeftPassage(dir)) {                                   // may rotate dir to L(dir) and advance the scout
        Logf("made left turn"); turnAngle -= 90;
        if (!fullyReachable(lastPathMark, Scout->Location) && !oneWaypointTo(lastPathMark)) {
            lastPathMark = prevLoc; last = addMarker(); m = &markers[last];
            m->Location = prevLoc; m->weight = 1; m->Direction = savedDir;
            m->flags = (m->flags & ~0x64) | 0x1a;                  // obstruction|beacon|marked
            Logf("made left turn marker %d", last); lastMarked = prevLoc;
        }
    } else {
        moveResult = Scout->walkMove(dir * 16, Hit, NULL, 4.1, 0);
        if (moveResult == 1) {
            markLeftReachable(prevLoc);
            if (needPath(Scout->Location)) {
                if (fullyReachable(lastPathMark, Scout->Location) || oneWaypointTo(lastPathMark)) goto obstruction;
                if (fabs(prevLoc.Z - Scout->Location.Z) > MaxStepHeight + 1) {        // 0xb5dfc: stairs
                    last = addMarker(); m = &markers[last]; m->Location = prevLoc; m->weight = 1; m->Direction = savedDir;
                    m->flags = (m->flags & ~0x66) | 0x18;          // beacon|marked
                    markers[0].flags |= 0x40;                      // 0xb5e67 (sic: marker 0)
                    lastPathMark = lastMarked = prevLoc; pathDebugf("marked stairway at [prevLoc]");
                } else {
                obstruction:
                    last = addMarker(); m = &markers[last]; m->Location = prevLoc; m->weight = 1; m->Direction = savedDir;
                    m->flags = (m->flags & ~0x7c) | 0x02;          // obstruction only
                    lastMarked = prevLoc; pathDebugf("marked obstruction at [prevLoc]");
                }
            } else if (sawNewLeft(Scout->Location)) {
                last = addMarker(); m = &markers[last]; m->Location = Scout->Location; m->weight = 1; m->Direction = -dir;
                m->flags = (m->flags & ~0x7c) | 0x02;
                lastMarked = Scout->Location; pathDebugf("marked out new obstruction at [scout]");
            }
        }
    }
    if (moveResult == 1) {                                         // 0xb60f6: did we bump into an existing marker?
        for (k = 0; k < numMarkers; k++) {
            if (k == last) continue;
            if (|markers[k].Location - Scout->Location|² >= R² * 0.25) continue;      // within R/2
            pathDebugf("Near path at [k]");
            d = dir - markers[k].Direction; if (|d|² >= 1e-8) d.Normalize();
            Logf("Current dir %f %f path direction is %f %f", dir.X, dir.Y, markers[k].Direction.X, .Y);
            same = fabs(d.X) < 1e-4 && fabs(d.Y) < 1e-4 && fabs(d.Z) < 1e-4;
            keepGoing = !same;
            if (same) { pathDebugf("Touched a compatible marker at [markers[numMarkers]]"); break; }   // prints one past the end
        }
    } else {                                                       // blocked: turn right
        lastPathMark = Scout->Location; pathDebugf("turn right at [scout]");
        if (!rightTurnMade) {
            rightTurnMade = 1; last = addMarker(); m = &markers[last]; m->Location = prevLoc; m->weight = 1; m->Direction = savedDir;
            m->flags = (m->flags & ~0x76) | 0x08;                  // beacon only
            pathDebugf("made right turn marker"); lastMarked = prevLoc;
        }
        N = -dir; FindBlockingNormal(N); turnAngle += 90;
        dir = FVector(-N.Y, N.X, 0);                               // = L(N); with N ≈ -dir this is R(dir)
        moveResult = 1; pathDebugf("new direction [dir]");
    }
    if (keepGoing && fabs(turnAngle) >= 360) {                     // 0xb65c6
        if (((lastMarked - Scout->Location) | dir) <= 0) { keepGoing = 0; pathDebugf("All the way around at [scout]"); }
        else keepGoing = 1;
    }
}
```
`dir` is the by-value argument slot (`[ebp+8]`), rewritten in place by `checkLeftPassage` and the
right turn.

### 3.14 checkLeftPassage(FVector& dir) — `0xb7630` ✅

```c
saved = Scout->Location; left = L(dir);
if (checkLeft(left, dir)) return 1;
r = Scout->walkMove(dir * 6, Hit, NULL, 4.1, 0);
if (checkLeft(left, dir)) return 1;
if (r) { Scout->walkMove(dir * 6, Hit, NULL, 4.1, 0); if (checkLeft(left, dir)) return 1; }
Level->FarMoveActor(Scout, saved, 0, 1); return 0;
```

### 3.15 checkLeft(FVector& left, FVector& dir) — `0xb7220` ✅

```c
saved = Scout->Location; result = 0;
if (Scout->walkMove(left * 16, Hit, NULL, 4.1, 0) == 1 && |Scout->Location - saved| > 10.0) {
    pathDebugf("Follow left passage [left]"); pathDebugf("Turned left at [saved]");
    dir = left; left = L(left);                                    // 0xb7403–0xb7429
    Scout->walkMove(dir * 16, Hit, NULL, 4.1, 0);
    result = 1; pathDebugf("New location [scout]");
} else Level->FarMoveActor(Scout, saved, 0, 1);
return result;
```

### 3.16 markLeftReachable(const FVector& pt) — `0xb54d0` ✅

```c
for (m in markers) {
    if (|pt - m.Location|² >= 640000) { m.flags &= ~0x01; continue; }
    m.flags &= ~0x01; m.flags &= ~0x80;
    SingleLineCheck(Hit, Scout, End = pt, Start = m.Location, 6);
    if (Hit.Time == 1.0) m.flags |= 0x01;
}
```

### 3.17 markReachable(const FVector& pt) — `0xb5370` ✅
For markers with `flags & 0x08` within 800: `flags.bit0 = fullyReachable(m.Location, pt)`.

### 3.18 needPath(const FVector& pt) — `0xb5000` ✅

```c
for (m in markers) if ((m.flags & 0x01) && (m.flags & 0x08) && |pt - m.Location|² < 640000) {
    SingleLineCheck(Hit, Scout, End = pt, Start = m.Location, 6);
    if (Hit.Time < 1.0 && !findPathTo(m.Location)) return 1;      // visible marker now occluded and unreachable via markers
}
return 0;
```

### 3.19 sawNewLeft(const FVector& pt) — `0xb5200` ✅
Returns 1 if any marker with `!(flags & 0x81) && (flags & 0x10)` within 800 has
`fullyReachable(m.Location, pt)`.

### 3.20 oneWaypointTo(const FVector& pt) — `0xb56d0` ✅

```c
maxD2 = 4 * R²; found = 0;
for (m in markers) { if (found) break;
    if (!(m.flags & 0x10) || |m.Location - Scout->Location|² >= maxD2) continue;   // marked, within 2R of the scout
    found = fullyReachable(pt, m.Location) && fullyReachable(m.Location, Scout->Location);
}
if (found) pathDebugf("Found an acceptable alternate left turn marker");
return found;
```

### 3.21 checkObstructionFrom(FPathMarker* m) — `0xb4a30` ✅

```c
if (!Level->FarMoveActor(Scout, m->Location, 0, 1)) Logf("obstruction far move failed");
Level->DropToFloor(Scout);                                         // slot 36
if (m->flags & 0x10) { pathDebugf("exploring out from left turn"); exploreWall(m->Direction); return; }
markLeftReachable(m->Location);
Scout->walkMove(m->Direction * 16, Hit, NULL, 4.1, 0);
for (k in markers) if (markers[k].flags & 0x01) {
    SingleLineCheck(Hit, Scout, End = Scout->Location, Start = markers[k].Location, 6);
    if (Hit.Time < 1.0 && !findPathTo(markers[k].Location)) {
        pathDebugf("found the obstruction");
        d = (markers[k].X - Scout->X, markers[k].Y - Scout->Y, 0); if (|d|² >= 1e-8) d.Normalize();
        exploreWall(d);                                            // recursion: explore toward the occluded marker
    }
}
```

### 3.22 mergePath(INT i) — `0xb40a0` ✅ (unwind name `FPathBuilder::premergePath`)

```c
m = &markers[i];
SingleLineCheck(Hit, NULL, End = m->Location - (0,0,MaxStepHeight+10), Start = m->Location, 6);
if (Hit.Time == 1.0) { m->flags &= ~0x18; return; }                // no floor within MaxStepHeight+10: unmark
m->radius = 12.0; maxD2 = 26450.0;
for (j in markers) { o = &markers[j];
    if (!(o->flags & 0x10) || (o->flags & 0x20) || j == i) continue;   // marked, not permanent, not self
    Scout->SetCollisionSize(12, 10);
    if (|m->Location - o->Location|² >= maxD2) continue;
    if (!fullyReachable(m->Location, o->Location)) continue;
    pathDebugf("Try to pre-merge path at [m]"); pathDebugf("And path at [o]");
    oNotPerm = !(o->flags & 0x20) /* always 1 here */; mNotPerm = !(m->flags & 0x20); both = oNotPerm && mNotPerm;
    mid = (m->Location * m->weight + o->Location * o->weight) / (m->weight + o->weight);
    for (k in markers) {                                           // 0xb43d6–0xb4713: results never used (dead)
        Scout->SetCollisionSize(12,10);  hM = boundedReachable(m->Location, markers[k].Location) ? 12 : 0;  hO = …(o) ? 12 : 0;  if (both) hMid = …(mid) ? 12 : 0;
        Scout->SetCollisionSize(52,10);  if (hM == 12 && boundedReachable(m, k)) hM = 52; … (o, mid likewise)
        Scout->SetCollisionSize(115,10); if (hM == 52) boundedReachable(m, k); … (results discarded)
    }
    newLoc = both ? mid : (oNotPerm ? m->Location : o->Location);
    pathDebugf("Successful merge at [newLoc]");
    m->Location = newLoc; m->weight += 1.0; o->flags &= ~0x18;      // o unmarked (loses beacon+marked)
}
```
Effective rule: two marked, non-permanent markers within √26450 ≈ 162.6 units that a 12×10 scout can
walk between (both ways, see `fullyReachable`) collapse into their weight-averaged midpoint; a
permanent (real PathNode) `m` absorbs `o` without moving. ✅

### 3.23 findPathTo(const FVector& dest) — `0xb70c0` ✅

```c
maxDist = |dest - Scout->Location| + 5 * Scout->CollisionRadius;
for (m in markers) m.budget = 0;
FPathMarker tmp; tmp.Location = Scout->Location;                   // only Location initialised
return tryPathThrough(&tmp, dest, maxDist);
```

### 3.24 tryPathThrough(FPathMarker* from, const FVector& dest, FLOAT maxDist) — `0xb6e60` ✅

```c
if (fullyReachable(from->Location, dest)) return 1;
from->budget = maxDist; result = 0;
for (m in markers) { if (result) break; if (!(m.flags & 0x10)) continue;
    d1 = |from->Location - m.Location|; d2 = |m.Location - dest|; remaining = maxDist - d1;
    if (m.budget >= remaining) continue;                           // already explored with a larger budget
    if (d1 + d2 >= maxDist) continue;
    if (fullyReachable(from->Location, m.Location)) result = tryPathThrough(&m, dest, remaining);
}
return result;
```
Depth-first search over `marked` markers with a straight-line distance budget.

### 3.25 fullyReachable(FVector a, FVector b) — `0xb79b0` ✅

```c
saved = Scout->Location; Scout->SetCollisionSize(Scout->CollisionRadius - 6, Scout->CollisionHeight);
ok = Level->FarMoveActor(Scout, a, 0, 0);
if (Scout->Physics != 1) Logf("Scout Physics is %d", Scout->Physics);  Scout->Physics = PHYS_Walking(1);
if (ok && Scout->pointReachable(b, 0)) {
    Level->FarMoveActor(Scout, b, 0, 0);
    ok = Scout->walkReachable(a, 15.0, 0, NULL) != 0;               // and back again
}
Level->FarMoveActor(Scout, saved, 0, 1); Scout->SetCollisionSize(Scout->CollisionRadius + 6, Scout->CollisionHeight);
return ok;
```
Reachability is required in **both** directions, with the scout 6 units thinner.

### 3.26 boundedReachable(FVector a, FVector b) — `0xb7880` ✅
`return |a - b|² <= 800.0 && fullyReachable(a, b);`

### 3.27 Dead functions (no caller anywhere in the builder region, checked by grep of all `call`s) ✅

- `checkmergeSpot(const FVector& spot, FPathMarker* A, FPathMarker* B)` (`0xb3a70`): for markers with
  `visible|beacon`, then with `bigVisible|marked`, tests `fullyReachable(m, spot)` with radius 12 /
  `min(A->radius, B->radius)`; on failure temporarily clears `marked` on A,B and requires
  `findPathTo(m)`; returns 0 at the first failure.
- `markReachableFromTwo(FPathMarker* A, FPathMarker* B)` (`0xb3d40`): writes `Scout->CollisionRadius
  = 12` directly, `markReachable(A)`, sets bit `0x01` from `fullyReachable(m, B)` for beacons
  within 800, then with radius `min(A->radius,B->radius)` (only if > 12) sets bit `0x04` from
  reachability to A then B; returns whether anything was set.
- `walkToward(const FVector& dest, FLOAT step)` (`0xb7c00`): 2-D delta to `dest`; returns 0 if
  `|d|² <= 1`; `walkMove(d)` if `|d|² < step²`, else `walkMove(d.Normal * step)`; result `== 1`.

### 3.28 addReachSpecs(AActor* node) — `0xb2240` ✅

```c
if (node->IsA(ALiftCenter)) {
    for (A in Actors) if (A && A->IsA(ALiftExit) && A->LiftTag == node->LiftTag) {
        spec.Init(); spec.Start = node; spec.End = A; spec.CollisionRadius = spec.CollisionHeight = 60; spec.reachFlags = 0x20; spec.distance = 500;
        addSpec(spec);                                             // (below)
        spec.Init(); spec.Start = A; spec.End = node; CR = CH = 60; reachFlags = 0x20; distance = 500; addSpec(spec);
    }
    return;                                                        // 0xb2291→0xb2976: LiftCenters get NO ordinary specs
}
if (node->IsA(ATeleporter) || node->IsA(AWarpZoneMarker)) {
    for (A in Actors) {
        match = node->IsA(ATeleporter) ? (A && A->IsA(ATeleporter) && A != node && !appStricmp(*node->URL, *A->Tag))
                                       : (A && A->IsA(AWarpZoneMarker) && A != node && !appStricmp(*node->markedWarpZone->OtherSideURL, *A->markedWarpZone->ThisTag));
        if (!match) continue;
        spec.Init(); spec.Start = node; spec.End = A; CR = CH = 150; reachFlags = 0x20; distance = 100; addSpec(spec);
        break;                                                     // first match only (0xb2602/0xb2656 → 0xb2665)
    }
}
for (A in Actors) {                                                // ordinary specs
    if (!A || !A->IsA(ANavigationPoint) || A->IsA(ALiftCenter) || A == node) continue;
    near = |node->Location - A->Location|² < 1000000.0;            // 1000 units
    ok = 1;
    if (node->bOneWayPath) { X = (GMath.UnitCoords / node->Rotation).XAxis; ok = ((A->Location - node->Location) | X) > 0; }
    if (!near || !ok) continue;
    if (|A->Location - node->Location|² < 1000.0) Logf("WARNING: %s and %s may be too close!", node->Name, A->Name);
    spec.Init();
    if (!spec.defineFor(node, A, Scout)) continue;
    addSpec(spec);
}
// addSpec(spec):   n = insertReachSpec(node->Paths, spec); if (n == -1) skip;
//                  idx = ReachSpecs.AddItem(spec); node->Paths[n] = idx;
//                  m = insertReachSpec(A->upstreamPaths, spec); if (m != -1) A->upstreamPaths[m] = idx;
```
`reachFlags` bit `0x20` (R_SPECIAL 📖 name) is written only for lift/teleporter/warpzone specs.
Bits `0x10`/`0x40` are never written by FPathBuilder; ordinary specs take `reachFlags` verbatim
from `APawn::pointReachable`'s return value (§3.31). ✅

### 3.29 insertReachSpec(INT* paths, FReachSpec& spec) — `0xb1d70` ✅

```c
n = 0;
while (n < 16 && paths[n] != -1 && ReachSpecs[paths[n]].distance > spec.distance) n++;   // 0xb1d9e: stop at first existing <= new
if (paths[15] == -1) {                                             // room
    if (paths[n] == -1 || n >= 15) return n;
    for (k = n; k < 15; k++) { t = paths[k+1]; paths[k+1] = paths[k]; if (t == -1) break; }   // shift up
    return n;
}
if (n == 0) return -1;                                             // full and new spec is the longest: dropped
for (k = 0; k < n-1; k++) paths[k] = paths[k+1];                   // drop paths[0], free slot n-1
return n-1;
```
So `Paths`/`upstreamPaths` are kept sorted by `distance` **descending** (longest at index 0), and on
overflow the longest one is evicted (or the new one refused if it is the longest). ✅ The caller
never writes when `-1` is returned, so a spec can exist in `ReachSpecs` and in `node->Paths` but be
missing from `End->upstreamPaths` (and vice versa is impossible: refusal in `Paths` skips the spec).

### 3.30 specFor(AActor* Start, AActor* End) — `0xb1cd0` ✅
`for (i < 16) { idx = Start->Paths[i]; if (idx == -1) return -1; if (ReachSpecs[idx].End == End) return idx; } return -1;`

### 3.31 FReachSpec::defineFor / findBestReachable — `0xd95b0` / `0xd96e0` ✅

```c
INT defineFor(AActor* begin, AActor* dest, APawn* Scout) {
    Start = begin; End = dest;
    Scout->bCanFly = 0; Scout->bCanJump = bCanWalk = bCanSwim = 1; Scout->Physics = PHYS_Walking;
    Scout->JumpZ = 120; Scout->GroundSpeed = 120; Scout->MaxStepHeight = 25; Scout->BaseEyeHeight = 0;
    return findBestReachable(begin->Location, dest->Location, begin->CollisionHeight, dest->CollisionHeight, Scout);
}
INT findBestReachable(FVector& start, FVector& end, FLOAT& startH, FLOAT& endH, APawn* Scout) {
    Scout->SetCollisionSize(12, 10); step = 115 - 12; bestR = 12; bestH = 10; success = 0;
    SingleLineCheck(Hit, Scout, End = start - (0,0,79), Start = start, 6);
    floor = (Hit.Time != 1.0) ? Hit.Location : start - (0,0,startH);
    SingleLineCheck(Hit, Scout, End = end, Start = start, 6);
    if (Hit.Time != 1.0) return 0;                                 // must be visible
    for (ok = 1; ok; ) {                                           // bisection on radius, 12..115
        if (FarMoveActor(Scout, floor + (0,0,Scout->CollisionHeight), 0, 0) && (flags = Scout->pointReachable(end, 1))) {
            reachFlags = flags; success = 1; bestR = Scout->CollisionRadius;
            SetCollisionSize(R + step, 10); step *= 0.5; if (R > 115) ok = 0;
        } else { SetCollisionSize(R - step, 10); step *= 0.5; if (R < 12) ok = 0; }
        if (step < 1.0) ok = 0;
    }
    if (success) {                                                 // bisection on height, 10..79
        SetCollisionSize(12, Scout->CollisionHeight); step = 79 - Scout->CollisionHeight;
        for (ok = 1; ok; ) {
            if (FarMoveActor(Scout, floor + (0,0,H), 0, 0) && (flags = pointReachable(end, 1))) { reachFlags = flags; bestH = H; SetCollisionSize(12, H + step); step *= 0.5; if (H > 79) ok = 0; }
            else { SetCollisionSize(12, H - step); step *= 0.5; if (H < 10) ok = 0; }
            if (step < 1.0) ok = 0;
        }
        CollisionRadius = (INT)bestR; CollisionHeight = (INT)bestH;
        distance = (INT)|End->Location - Start->Location|; if (reachFlags & 4) distance *= 2;   // 0xd9b62
    }
    return success;
}
```
`APawn::pointReachable` (`0xc0d30`) dispatches to `Reachable` → `walkReachable`/`swimReachable`/
`flyReachable` by physics and returns the reach-flag mask; those were **not** decoded (see §7).
`reachFlags & 4` doubling matches R_SWIM 📖.

### 3.32 Prune(AActor* node) — `0xb1990` ✅

```c
pruned = 0;
for (i < 16) { if (node->upstreamPaths[i] == -1) break;  alpha = ReachSpecs[node->upstreamPaths[i]];
  for (j < 16) { if (node->Paths[j] == -1) break;          beta  = ReachSpecs[node->Paths[j]];
    k = specFor(alpha.Start, beta.End); if (k == -1) continue;      // direct spec alpha.Start → beta.End
    gamma = ReachSpecs[k]; sum = alpha + beta;                       // distance added, CR/CH = min, flags OR'ed
    if (!(sum.distance <= (long double)gamma.distance * 1.2_f64)) continue;   // effectively STRICT, see below
    if (!(sum <= gamma || gamma.BotOnlyPath() || sum.MonsterPath())) continue;
    pruned++;
    remove k from gamma.Start->Paths (shift down, Paths[15] = -1);   // 0xb1af5–0xb1b35
    put k in first free gamma.Start->PrunedPaths slot (slot 15 overwritten if full);   // 0xb1b40–0xb1b53
    ReachSpecs[k].bPruned = 1;
    remove k from gamma.End->upstreamPaths (shift down, upstreamPaths[15] = -1);      // 0xb1b74–0xb1bad
  }
}
return pruned;
```
The distance test, instruction by instruction (`0xb1a97`–`0xb1ab6`) ✅:

```
0xb1a97  fild  dword ptr [ebp-0x44]      ; gamma.distance (INT) → x87, exact
0xb1aa4  fmul  qword ptr [0x10430a48]    ; × f64 constant: bytes 33 33 33 33 33 33 F3 3F = 0x3FF3333333333333
                                         ;   = 1.1999999999999999555910790149937 (the nearest double BELOW 1.2)
0xb1aac  fild  dword ptr [ebp-0x60]      ; sum.distance (INT) → x87, exact
0xb1aaf  fcompp                          ; compare ST0=sum with ST1=gamma·1.2
0xb1ab1  fnstsw ax
0xb1ab3  test  ah, 0x41                  ; C0 (sum < prod) | C3 (sum == prod)
0xb1ab6  je    0xb1bb7                   ; neither → skip; so the branch condition is sum <= prod
```

The opcode-level condition is `<=`, but the constant is not 1.2: for an integer `gamma` the exact
product is `1.2·gamma − 4.44e-17·gamma`, so equality with an integer `sum` can only occur if the
`fmul` rounds up to it. With the x87 at 64-bit mantissa precision it never does (ulp at 198 is
2⁻⁵⁶), and `dx-core` sets exactly that: `appEnableFastMath(UBOOL)` (`dx-core 0x6e050`) is
`_controlfp(Enable ? _PC_24 : _PC_64, _MCW_PC)` and is called with `0` from an unexported Core
function at `dx-core 0x6def1` (🔬 `appInit`); no other DX module calls it. Resolved semantics:
**`sum.distance < 1.2 · gamma.distance` (strict)** — e.g. `gamma=165`, `sum=198`: product
197.99999999999999267 < 198 → not pruned. (At the CRT default 53-bit precision the same product
would round to 198.0 and the spec would be pruned; that is not the configuration DX runs in.) Both
distances are `INT` converted with `fild` (no float32 anywhere in the test).

Operators (`0xd9490`–`0xd95b0`): `a + b` = `{a.distance + b.distance, min CR, min CH, a.flags | b.flags}`
(Start/End/bPruned left uninitialised); `a <= b` ⇔ `a.CR >= b.CR && a.CH >= b.CH && (a.flags | b.flags)
== b.flags`; `MonsterPath()` ⇔ `CR >= 22 && CH >= 51 && !(flags & 2)`; `BotOnlyPath()` ⇔ `CR < 12`;
`supports(r,h,f)` ⇔ `CR >= r && CH >= h && (flags & f) == flags`. ✅ Note the loop indices are
not re-checked after a removal shifts `Paths`/`upstreamPaths`, so the entry shifted into slot `j`
(or `i`) is skipped.

### 3.33 addVisNoReach(AActor* node) — `0xb1e50` ✅

```c
if (node->IsA(ALiftCenter)) return;
Scout->SetCollisionSize(22, 51); Level->FarMoveActor(Scout, node->Location, /*bTest*/1, 0);   // test only
Scout->MoveTarget = node; Scout->bCanDoSpecial = 1; n = 0;
for (N = NavigationPointList; N; N = N->nextNavigationPoint) {
    d2 = |node->Location - N->Location|²;
    if (N->IsA(ALiftCenter) || N == node || d2 >= 4000000.0 || n >= 16) continue;
    SingleLineCheck(Hit, Scout, End = N->Location, Start = node->Location, 6); if (Hit.Actor) continue;   // must be visible
    if (Scout->findPathToward(N, 0, &best, 1)) { w = (FLOAT)best->visitedWeight; if (w == 1e7) continue; }
    else w = 2e8;
    if (w * w > 4.0 * d2) node->VisNoReachPaths[n++] = N;         // route is > 2× the straight line (or none)
}
```

## 4. Answers to the assignment's questions

**(a) FPathMarker & the walk.** Layout in §1. The array is filled by `createPaths` (§3.7): one
permanent marker per existing PathNode, then `createPathsFrom` from every Pawn and Inventory
actor. The walk (`exploreWall` → `followWall`): 16-unit `walkMove` steps with a 115×10 scout;
each step first probes `L(dir)` for a "left passage" (16-unit sideways move that actually travels
> 10, tried at 0, 6 and 12 units ahead); when blocked ahead the scout turns to `L(N)` of the blocking
normal ("turn right"). Markers are dropped: at a left turn if the last path marker is not reachable
(and no single marked waypoint bridges) — `marked`; at a step change > `MaxStepHeight + 1`
("stairway") — `marked`; where a previously visible beacon becomes occluded and unreachable
("obstruction") — `obstruction` only, re-explored later; at the first right turn — `beacon` only.
The walk stops when it touches a marker within R/2 whose stored `Direction` equals the current
direction, or after |turn angle| ≥ 360° once the last marker is no longer ahead. Merging
(`mergePath`): two `marked` markers within ≈162.6 units, mutually walkable by a 12×10 scout, collapse
into the weight-averaged midpoint; a marker with no floor within `MaxStepHeight + 10` below is
unmarked. Handedness caveat in §7.

**(b) define vs build.** `PATHS BUILD` = `removePaths` (destroys **all** PathNodes) then
`buildPaths` → `createPaths` (auto-place, spawn plain `PathNode`s at floor + 48; no `bAutoBuilt`
flag exists in DX). `PATHS DEFINE` = `undefinePaths` + `definePaths`: spawns one `WarpZoneMarker`
per `WarpZoneInfo` at the scout's start position and nothing else (the log line says "Inventory
markers" but no InventorySpot is created), builds `NavigationPointList` (reverse actor order), adds
reachspecs, prunes, fills `VisNoReachPaths`. `undefinePaths` empties `ReachSpecs`, destroys
`WarpZoneMarker`/`TriggerMarker`/`InventorySpot`/`ButtonMarker` actors (unlinking
`Inventory.myMarker`), and resets the path arrays and list links on the remaining NavigationPoints.

**(c) createPaths / spec computation / bookkeeping.** Candidate pairing is in `addReachSpecs`
(§3.28): every other NavigationPoint (not LiftCenter, not self) within 1000 units, in front for
`bOneWayPath`, visible (line trace), then `findBestReachable` bisects the scout radius in 12..115 and
height in 10..79 (`step` halving from 103 / 69, stop when `step < 1`) with `pointReachable(end,1)`
from the point on the floor under `Start` (trace 79 down, else `Start.Z - CollisionHeight`);
`CollisionRadius/Height` = the largest passing values, `reachFlags` = `pointReachable`'s mask,
`distance` = straight-line distance (×2 if flag `0x4`). `Paths`/`upstreamPaths` (16 each) are kept
sorted by distance **descending**; overflow evicts index 0 (the longest) or refuses a new longest
(§3.29). LiftCenter↔LiftExit (same `LiftTag`): both directions, `distance 500, CR=CH=60, flags 0x20`,
and LiftCenters get no other specs. Teleporter→Teleporter (`URL` equals other's `Tag`) and
WarpZoneMarker→WarpZoneMarker (`OtherSideURL` equals other's `ThisTag`): one-way, first match,
`distance 100, CR=CH=150, flags 0x20`.

**(d) Prune.** For every (upstream α, downstream β) pair through `node` with a direct spec γ from
α.Start to β.End: prune γ iff `(α+β).distance < 1.2 · γ.distance` (opcode `<=` against the f64
constant `0x3FF3333333333333` < 1.2 at 64-bit x87 precision — strict in effect, §3.32) and (`α+β <= γ` [not less
capable] or `γ.CollisionRadius < 12` or (`(α+β).CR >= 22 && CH >= 51 && !(flags & 2)`)). Mutations:
γ's index moves from `Start->Paths` to `Start->PrunedPaths`, is removed from `End->upstreamPaths`,
and `ReachSpecs[γ].bPruned = 1`. `PrunedPaths[15]` is overwritten when full.

**(e) Special edges & flag bits.** §3.28. Bit `0x20` written for lift/teleporter/warpzone edges
only; bits `0x10` and `0x40` are not written by FPathBuilder (they can only come from
`pointReachable`, undecoded). Ordinary edges get the raw `pointReachable` mask.

**(f) Scout parameters.** `buildPaths`: `SetCollision(1,1,1)`, `bCollideWorld=1`, `JumpZ = -1`,
`GroundSpeed = 320`, `MaxStepHeight = 24`; collision size is then driven per test: 115×10 for the
walk (`exploreWall`), 12×10 for merge/reachability tests (minus 6 inside `fullyReachable`), 52×10 and
115×10 in `mergePath`'s dead loop; `newPath` spawns 48 above the floor. `definePaths`/`defineFor`:
`JumpZ = 120`, `GroundSpeed = 120`, `MaxStepHeight = 25`, `bCanJump|bCanWalk|bCanSwim`, `!bCanFly`,
`PHYS_Walking`; radius/height 12..115 / 10..79 for the bisection; 22×51 in `addVisNoReach`; 20 then 12
radius for WarpZone placement. `opt`: parsed by the editor (`LOWOPT 0`, default 1, `HIGHOPT 2`),
passed through, and only printed ("Optimization Level = [%6d]") — no effect on the build. ✅

**(g) Versus the UT-lineage builder (📖 unless marked).** UT/469 `UnPath.cpp` has no scout
exploration at all — `definePaths` there only places `InventorySpot`s, `WarpZoneMarker`s and builds
reachspecs; `PATHS BUILD` in UED22 is `definePaths` (see the `ued-engine` findings). DX still ships the
Unreal-1 explorer (`exploreWall`/`followWall`, 3000 markers) ✅. DX `Prune` matches the public
formula (`1.2`, `sum <= gamma`, BotOnlyPath/MonsterPath) 📖→✅ here. DX `insertReachSpec` sorts
descending and evicts the longest ✅ (public UT keeps ascending order 📖 — unverified). DX
`addReachSpecs` uses a 1000-unit radius and `findBestReachable` bisection 12..115 / 10..79 ✅ (UT
uses `MAXPATHDIST` 1000 and fixed size classes 📖). DX has no `bAutoBuilt`, no `PrunedPaths`
consumers in the builder, no `ButtonMarker`/`TriggerMarker` creation ✅.

## 5. Evidence table (key RVA → fact) ✅

| RVA | Fact |
|--------------|------------------------------------------------------------------------------|---
| `0xb0c34`–`0xb0c62` | `Malloc(0x1d4c0,"FPathMarker")`, 3000 × 0x28, stored at builder+0 |
| `0xb0c8c`,`0xb0c9c`,`0xb0cac` | Scout `JumpZ=-1`, `GroundSpeed=320`, `MaxStepHeight=24` |
| `0xb0dd4` | `removePaths` destroys every `APathNode` |
| `0xb0ea8`,`0xb0f28` | show/hide = `DrawType` 1/0 |
| `0xb0fc6`,`0xb102c` | `ReachSpecs.Empty()` (elem 0x1c), `NavigationPointList = NULL` |
| `0xb107c`–`0xb10f7` | `undefinePaths` marker classes: WarpZoneMarker, TriggerMarker, InventorySpot, ButtonMarker |
| `0xb1363` | `definePaths` only handles `AWarpZoneInfo` |
| `0xb13cb`,`0xb143f` | WarpZone placement radii 20 then 12 |
| `0xb140f` | `FarMoveActor(Scout, WZ.Location, 1, 1)` (test-only) |
| `0xb1451`,`0xb14bc` | spawns `WarpZoneMarker`, sets `markedWarpZone` |
| `0xb1597`–`0xb160d` | `nextNavigationPoint` linking (prepend) |
| `0xb1a97`–`0xb1ab6` | Prune distance test: `fild; fmul qword [0x10430a48]` (f64 `0x3FF3333333333333` = 1.19999999999999996); `fild; fcompp; test ah,0x41; je` → `<=` opcode, strict in effect |
| `dx-core 0x6e050`, `0x6def1` | `appEnableFastMath` = `_controlfp(E ? _PC_24 : _PC_64, _MCW_PC)`, called with 0 → 64-bit x87 precision |
| `0xb1ac3`,`0xb1acf`,`0xb1adb` | Prune: `operator<=`, `BotOnlyPath`, `MonsterPath` |
| `0xb1b6f` | `bPruned = 1` |
| `0xb1d9e` | insertReachSpec stops at first `existing.distance <= new.distance` |
| `0xb1de3`–`0xb1e0a` | full-array handling: refuse if n==0 else evict index 0 |
| `0xb1eaa`,`0xb1ff8`,`0xb20df` | addVisNoReach: 22×51, 2000², ×4 |
| `0xb2308`–`0xb232e` | lift spec: CR=CH=60, flags 0x20, distance 500 |
| `0xb25d7`–`0xb25f0` | teleporter/warpzone spec: 150, 0x20, 100 |
| `0xb2729`,`0xb2743`,`0xb2825` | 1000² radius, `bOneWayPath` facing test, "too close" 1000 |
| `0xb2884` | `defineFor(node, A, Scout)` |
| `0xb2c4d`–`0xb2c61` | PathNode marker flags `0x1a|0x20` |
| `0xb2c91`,`0xb2cb3` | explore from every Pawn and Inventory |
| `0xb2d90`,`0xb2e56` | obstruction pass on bit 0x02, cleared after |
| `0xb2e6f`,`0xb2ea0`–`0xb2ea7` | merge pass on 0x10; spawn on 0x10 && !0x20 |
| `0xb2f0f` | the only read of `opt` |
| `0xb31e3` | `newPath` +48 rule |
| `0xb3266`–`0xb327e` | new PathNode `Paths/upstreamPaths = -1` |
| `0xb3429` | `SetActorZone(Scout,1,1)` |
| `0xb3559`,`0xb3585`,`0xb3785` | findScoutStart: (0,0,-50), `MoveActor(...,1,1,0,0)`, 50 iterations |
| `0xb3976` | createPathsFrom retry +20 |
| `0xb39ae` | `exploreWall((1,0,0))` |
| `0xb418e`,`0xb4195`,`0xb43ab`,`0xb47da` | mergePath: radius 12, 26450, weighted midpoint, weight += 1 |
| `0xb4ae5`,`0xb4ccd` | checkObstructionFrom recursion into `exploreWall` |
| `0xb4dfb`,`0xb4e88`,`0xb4ef4` | exploreWall: 115×10, `walkMove(dir*16,…,4.1,0)`, `followWall((N.Y,-N.X,0))` |
| `0xb5926` | addMarker free test `flags & 0x3a` |
| `0xb5bcd`,`0xb5c07` | followWall left turn, `turnAngle -= 90` |
| `0xb5cb7`,`0xb5e59`,`0xb5f40`,`0xb64b8` | marker flag writes: `~0x64|0x1a`, `~0x66|0x18`, `~0x7c|0x02`, `~0x76|0x08` |
| `0xb5e67` | `markers[0].flags |= 0x40` |
| `0xb6115`,`0xb62da` | near-marker `R²/4`, same-direction 1e-4 |
| `0xb6516`–`0xb656a` | right turn: `FindBlockingNormal(-dir)`, `+90`, `dir=(-N.Y,N.X,0)` |
| `0xb65db`,`0xb661b` | 360° test, `(lastMarked - Scout)·dir <= 0` |
| `0xb6b19`,`0xb6c30`,`0xb6d03` | FindBlockingNormal's three traces |
| `0xb6f92`–`0xb6fa7` | tryPathThrough budget tests |
| `0xb713a` | findPathTo budget `dist + 5R` |
| `0xb7329`,`0xb7403`–`0xb7429` | checkLeft 10-unit test, `dir=left; left=L(left)` |
| `0xb765b`–`0xb7681` | `left = (-dir.Y, dir.X, 0)` |
| `0xb78ca` | boundedReachable 800 |
| `0xb79eb`,`0xb7a8d`,`0xb7ae0`,`0xb7b26` | fullyReachable: R−6, `pointReachable`, `walkReachable(…,15,0,0)`, R+6 |
| `0xd95dc`–`0xd961e` | defineFor scout setup |
| `0xd9709`–`0xd971d`,`0xd9770`,`0xd994f`,`0xd9a8b` | findBestReachable 12×10, 115, 79 bounds |
| `0xd9b62`–`0xd9b69` | `distance *= 2` if `reachFlags & 4` |
| `dx-editor 0x7edbe`–`0x7ee1c` | `opt` = 1 / LOWOPT 0 / HIGHOPT 2 |

## 6. Surprises

- `PATHS BUILD` never connects anything: `buildPaths` only places nodes; `PATHS DEFINE` is a
  separate step (and the editor calls `removePaths` first, deleting *all* PathNodes, hand-placed ones
  included, since DX has no `bAutoBuilt`).
- `opt` is decorative.
- `definePaths` creates only WarpZoneMarkers; InventorySpots are never created by this engine's
  builder although `undefinePaths` knows how to delete them.
- `insertReachSpec` keeps the 16 *shortest* specs but stores them longest-first.
- `mergePath`'s inner three-radius loop is dead computation; `checkmergeSpot`,
  `markReachableFromTwo`, `walkToward` are never called.
- `findScoutStart`, `definePaths`' fallback and `addVisNoReach` use test-only moves (`bTest = 1`),
  so the scout is not actually displaced by them.
- `markers[0].flags |= 0x40` on every stairway marker and the "RAN OUT OF MARKERS!" message on
  every recycle look like source bugs, not RE errors (re-read twice).

## 7. Open questions

- **Handedness / whether the walk works.** Algebraically: `exploreWall` starts `followWall` with
  `R(N)`; `followWall` probes passages on `L(dir)` and turns to `L(N)` when blocked. If
  `SingleLineCheck`'s `Hit.Normal` faces the trace start (UE1 convention 📖, consistent with the
  `Normal.Z >= 0.7` floor test in `findScoutStart`, which uses `MoveActor`), then `N ≈ -dir` and the
  scout turns *left* at the first wall (wall on its right) but then follows as a *left*-hand wall
  follower — it would immediately "find" a left passage into open space. I could not decide this
  statically: it needs `UModel::LineCheck`'s normal sign or a live `PATHS BUILD` in the DX editor.
  Tried: `execTrace` (settles arg order, not normal sign); `MoveActor`/`FarMoveActor` bool roles.
- `APawn::walkMove` return codes other than 1 (`0`, `-1`, `5`) and its `MoveActor(…,1,1,0,0)` call
  (5th arg = the `bTest` slot) were not decoded; `pointReachable`/`walkReachable` (`0xc0d30`,
  `0xc1b70`, ~0x600 bytes) which produce `reachFlags` were not decoded either — so which bits
  `0x1/0x2/0x4/0x8/0x10/0x40` mean is 📖 (UE1 `R_WALK=1, R_FLY=2, R_SWIM=4, R_JUMP=8, R_DOOR=16,
  R_SPECIAL=32, R_PLAYERONLY=64`).
- Global `0x1058c14c` (`pathDebugf` gate, `<= 300`) unidentified.
- `AScout` default collision size (used by `definePaths`' first `findScoutStart`) not looked up.
