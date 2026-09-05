# UED22 `FPathBuilder` — the `PATHS` build, read from `ued-engine` / `ued-editor`

Binary keys, RVAs and ✅/🔬/📖 marks per `00-method.md`. Addresses are VAs at image base
`0x10000000`. Field names come from `layout.py ued Engine.<Class>`; the offsets quoted below were
re-derived this session (NavigationPoint `upstreamPaths`/`Paths`/`PrunedPaths`/`VisNoReachPaths` =
`+0x214`/`+0x254`/`+0x294`/`+0x2d4`, flag word `+0x33c`: `bPlayerOnly 1`, `bEndPoint 2`,
`bEndPointOnly 4`, `bOneWayPath 0x10`, `bAutoBuilt 0x40`).

## 0. Corrections to the 2026-07-15 reading (`30-ulevel-paths-assembly.md` §4)

| Prior claim | What the code does |
|---|---|
| `definePaths` only spawns markers, touches no ReachSpecs | ✅ **`definePaths` IS the reachspec builder**: markers → `addReachSpecs` per node → `Prune` → `addVisNoReach` (`0x10178c10`–`0x101791ea`). |
| `createPaths(opt)` builds all reachspecs | ✅ `createPaths` (`0x10177900`) never touches ReachSpecs. It is the **automatic PathNode placer** (wall-following scout walk from every InventorySpot/PlayerStart, then a merge pass and a gap-fill pass). |
| `createPaths` pairs nodes within 128² / 800² | ✅ 128²=`16384` is the *merge* threshold for auto-built nodes, 800²=`640000` the neighbour radius of the merge check; the reachspec pair cutoff is **1000 uu** (`1000000.0` at `0x1020296c`, `addReachSpecs 0x101772f0`). |
| `opt`: LOWOPT→0, default→1, HIGHOPT→2 | ✅ values right, but `createPaths` never reads its argument (no `[ebp+8]` access in `0x10177900`–`0x10178bc7`, `ret 4`). **LOWOPT/HIGHOPT are no-ops.** |
| "Built Paths: %d" = reachspec count | ✅ It is `createPaths`' return: the number of NavigationPoints with `bAutoBuilt` after the build (`0x10178b47`–`0x10178bb3`). |
| Scout sweep starts at (18, 39) | ✅ confirmed; the height is a second binary search (§4.7). `defineFor` sets `MaxStepHeight = 25`, not 24. |
| `PATHS REMOVE` removes auto paths | ✅ `removePaths` destroys **every** actor that `IsA(PathNode)`, hand-placed included (`0x10179b6b` walks the superclass chain, no `bAutoBuilt` test). |

## 1. `UEditorEngine::Exec` — `PATHS` (`ued-editor 0x10064f11`)

```
PATHS
  BUILD [LOWOPT|HIGHOPT]   opt = LOWOPT ? 0 : HIGHOPT ? 2 : 1          0x10064f4b–0x10064f81
        Trans->Begin("Paths"); Level->Modify();  🔬 slot names          0x10064f84–0x10064fa3
        n = FPathBuilder().buildPaths(Level, opt)                      0x10064fb2
        RedrawLevel(Level)  🔬                                          0x10064fcc
        Ar.Logf("Built Paths: %d", n)                                   0x10064fcf
  SHOW      n = showPaths(Level);   Logf(" %d Paths are visible!", n)   0x1006502a / 0x10065047
  HIDE      n = hidePaths(Level);   Logf(" %d Paths are hidden!", n)    0x100650a8 / 0x100650c5
  REMOVE    n = removePaths(Level); Logf("Removed %d Paths", n)         0x10065126 / 0x10065143
  UNDEFINE  undefinePaths(Level); RedrawLevel                           0x100651a4 → 0x10063c7d
  DEFINE    GWarn->BeginSlowTask("AI Paths", 1, 0);                     0x100651e7–0x100651f3
            undefinePaths(Level); definePaths(Level);                   0x10065201 / 0x10065213
            GWarn->EndSlowTask(); RedrawLevel                           0x10065222 → 0x10063c7b
```
✅ Strings `0x100e8a04`–`0x100e8b28`. SHOW/HIDE/REMOVE/UNDEFINE/DEFINE also call `[this+0x90]`
vtable `+0x54` with `"Paths"` first (🔬 `Trans->Begin`). Each `FPathBuilder` is a fresh stack
object (`lea ecx,[ebp-0xa94]` …); it holds only `Level` (`+0`) and `Scout` (`+4`).

## 2. Layout facts used below

| Thing | Offsets | Evidence |
|---|---|---|
| `FPathBuilder` | `+0 ULevel* Level`, `+4 AScout* Scout` | ✅ `buildPaths 0x101777b7 mov [edi],ebx`; `getScout 0x10179625 mov [esi+4],0` |
| `ULevel` | `Actors.Data +0x2c`, `Actors.Num +0x30`, `ReachSpecs.Data +0x8c`, `.Num +0x90`, `Model +0x98` | ✅ loops `[eax+0x2c]/[eax+0x30]`; `undefinePaths 0x1017a05b lea ecx,[Level+0x8c]`; `SetReachSpec 0x101621fc cmp edi,[ecx+0x90]`; 🔬 `+0x98` is the `this` of `UModel::FastLineCheck` (`0x10177c2e`) and `UModel::PointRegion` (`0x101833ec`) |
| `FReachSpec` (28 B) | `+0 Distance`, `+4 Start`, `+8 End`, `+0xc CollisionRadius`, `+0x10 CollisionHeight`, `+0x14 reachFlags`, `+0x18 bPruned` (byte) | ✅ `Init 0x10112b32`–`0x10112b5b`; `AddItem 0x10174f14 push 0x1c` |
| `ULevel` vtable (`0x101fca5c`) | slot 34 `MoveActor`, 35 `FarMoveActor`, 37 `DestroyActor`, 39 `SpawnActor`, 43 `SetActorZone`, 48 `SingleLineCheck` | ✅ dumped `0x101fcae4..0x101fcb1c` → `0x1608e0/0x15ff80/0x15f8c0/0x162810/0x161e10/0x162400` |
| `FCheckResult` | `+4 Actor`, `+0x14 Normal`, `+0x24 Time` | ✅ ctor `0x101247d0`; uses `0x101776a6`, `0x10175068`, `0x10176d4b` |
| Scout class defaults (UED22 `Engine.u`) | `CollisionRadius 52`, `CollisionHeight 50`, `JumpZ 325`, `GroundSpeed 320`, `MaxStepHeight 25` | 🔬 read with `uedcli.uprops.resolve_class_defaults`, not from code |
| Class lookups | `FindObjectChecked<UClass>(ANY_PACKAGE, "Scout" / "WarpZoneMarker" / "InventorySpot" / "PathNode")` | ✅ `0x10153510` = `StaticFindObjectChecked(UClass::StaticClass(), -1, name, 0)` |

`IsA(X)` below = walk `Class` (`+0x24`) through `SuperField` (`+0x28`) comparing with
`&X::PrivateStaticClass`; the code inlines that everywhere (e.g. `0x101777d2`–`0x101777f9`).
`SpawnActor(Class, Name, Owner, Instigator, Location, Rotation, Template, bNoCollisionFail,
bRemoteOwned)`; `FarMoveActor(Actor, Loc, bTest, bNoCheck)`; `SingleLineCheck(Hit, Source, End,
Start, TraceFlags, Extent)` — argument order read off the pushes.

## 3. Pipeline

```
buildPaths(Level, opt)                                                  0x10177770  ✅
  t = -appSecondsNew()
  this.Level = Level
  for a in Actors: if a && IsA(PathNode) && a.bAutoBuilt: DestroyActor(a, 0)          0x101777bb–0x101777f9
  undefinePaths(Level); definePaths(Level)          // full reachspec build #1        0x101777fe / 0x10177806
  getScout()                                                                          0x1017780d
  Scout->SetCollision(1,1,1); Scout.bCollideWorld = 1                                 0x1017781b / 0x10177829
  Scout.JumpZ = -1.0; Scout.GroundSpeed = 320; Scout.MaxStepHeight = 24               0x10177835 / 0x10177842 / 0x1017784f
  n = createPaths(opt)                              // auto PathNode placement        0x1017785e
  DestroyActor(Scout, 0)                                                              0x1017786e
  undefinePaths(Level); definePaths(Level)          // full reachspec build #2        0x10177877 / 0x1017787f
  GLog->Logf("Total paths build time %lf seconds", t + appSecondsNew())               0x101778a9
  return n
```
`PATHS BUILD` = strip old auto nodes + DEFINE + auto-placement + DEFINE. `PATHS DEFINE` = the
reachspec build alone. The `JumpZ=-1 / MaxStepHeight=24` scout only serves `createPaths`; every
reachspec test re-parameterises the scout in `defineFor` (§4.6), and `definePaths` destroys its
scout at the end, so build #2 runs on a freshly spawned one.

## 4. Functions

### 4.1 `undefinePaths(Level)` — `0x1017a000` ✅
```
this.Level = Level
GLog->Logf("Remove %d old reachspecs", ReachSpecs.Num)                                0x1017a050
ReachSpecs.Num = 0; ReachSpecs.Max = 0; FArray::Realloc(0x1c)     // Empty()          0x1017a06e–0x1017a07e
LevelInfo.NavigationPointList = NULL                              // +0x464           0x1017a08b
for i, a in Actors:  GWarn->StatusUpdatef(i, Num, "Undefining Paths")                 0x1017a0bd
  if !a || !IsA(NavigationPoint): continue
  if IsA(WarpZoneMarker) || IsA(TriggerMarker) || IsA(InventorySpot) || IsA(ButtonMarker):   0x1017a0f4–0x1017a134
      if IsA(InventorySpot) && a.markedItem: a.markedItem.myMarker = NULL   // +0x340 / +0x28c  0x1017a14b–0x1017a155
      DestroyActor(a, 0)                                                              0x1017a166
  else:
      nextNavigationPoint = nextOrdered = prevOrdered = startPath = previousPath = NULL   // +0x320..+0x330  0x1017a17c–0x1017a1a4
      for k<16: Paths[k] = upstreamPaths[k] = PrunedPaths[k] = -1; VisNoReachPaths[k] = NULL   0x1017a1b8–0x1017a1d9
```
TriggerMarker/ButtonMarker are destroyed but never spawned by this build (Unreal-1 leftovers) 🔬.
`visitedWeight`, `bEndPoint`, `bAutoBuilt` are not reset here.

### 4.2 `definePaths(Level)` — `0x10178c10` ✅ (the reachspec build)
```
this.Level = Level
n = Actors.Num; while n > 3 && Actors[n-1] == NULL: n--            // trim trailing NULL slots   0x10178c56–0x10178c68
if n < Actors.Num: Actors.Remove(n, Num-n)                          // 0x1015bde0 = TArray::Remove (GUndo-aware)
getScout()                                                                              0x10178c7e
LevelInfo.NavigationPointList = NULL                                                    0x10178c8a
GLog->Logf("Add WarpZone and Inventory markers")                                        0x10178ca5
for i, a in Actors:  GWarn->StatusUpdatef(i, Num, "Defining Paths")                     0x10178cd6
  if !a: continue                                                   // no bDeleteMe test here
  if IsA(WarpZoneInfo):                                                                 0x10178cf8
      ok = findScoutStart(a.Location) && Scout.Region.Zone == a.Region.Zone             0x10178d2c–0x10178d49
      if !ok:
          Scout->SetCollisionSize(20, Scout.CollisionHeight)                            0x10178d62–0x10178d69
          ok = findScoutStart(a.Location) && same zone                                  0x10178d97–0x10178db1
          if !ok: FarMoveActor(Scout, a.Location, bTest=1, bNoCheck=1)                  0x10178db3–0x10178de7
          Scout->SetCollisionSize(24, Scout.CollisionHeight)                            0x10178e05–0x10178e0c
      m = SpawnActor(Class("WarpZoneMarker"), None, 0, 0, Scout.Location, (0,0,0), 0, 0, 0)   0x10178e16–0x10178e95
      m.markedWarpZone = a                                          // +0x340           0x10178e97
  elif IsA(Inventory):                                                                  0x10178eb8
      ok = findScoutStart(a.Location) && |Scout.Z - a.Z| <= Scout.CollisionHeight       0x10178eec–0x10178f1b
      if !ok: FarMoveActor(Scout, a.Location + (0,0, 40 - a.CollisionHeight), 1, 1)    0x10178f20–0x10178f83
      s = SpawnActor(Class("InventorySpot"), None, 0, 0, Scout.Location, (0,0,0), 0, 0, 0)     0x10178f8b–0x1017900a
      s.markedItem = a; a.myMarker = s                              // +0x340 / +0x28c  0x1017900c / 0x10179012
GLog->Logf("Add reachspecs")                                                            0x1017903d
for i, a in Actors:  GWarn->StatusUpdatef(i, Num, "%s (%d/%d)", "Adding reachspecs", i, Num)   0x10179070
  if a && !a.bDeleteMe && IsA(NavigationPoint):
      a.nextNavigationPoint = LevelInfo.NavigationPointList; LevelInfo.NavigationPointList = a   // prepend  0x101790a2–0x101790b5
      addReachSpecs(a)                                                                  0x101790be
      GLog->Logf("Added reachspecs to %s", a.Name)                                      0x101790dd
GWarn->StatusUpdatef(0, 0, "Cleaning up")                                               0x10179103
GLog->Logf("Added %d reachspecs", ReachSpecs.Num); GLog->Logf("Prune reachspecs")       0x10179125 / 0x10179138
pruned = 0; for n = NavigationPointList; n; n = n.nextNavigationPoint: pruned += Prune(n)   0x10179150–0x1017916a
GLog->Logf("Pruned %d reachspecs", pruned)                                              0x1017917e
for n in NavigationPointList: addVisNoReach(n)                                          0x10179194–0x101791a6
DestroyActor(Scout, 0); GLog->Logf("All done")                                          0x101791b1 / 0x101791c8
```
Marker spawns use `bNoCollisionFail = 0`. The Scout's collision size going into the WarpZone
/Inventory tests is whatever it is at that moment (class default 52/50 until a WarpZone shrinks
it to 20 then 24; nothing resets it inside the loop).

### 4.3 `getScout()` — `0x101795f0` ✅
```
Scout = NULL; for a in Actors: if a && IsA(Scout): Scout = a          // last one wins   0x1017962e–0x10179659
if !Scout: Scout = SpawnActor(Class("Scout"), None, 0, 0, (0,0,0), (0,0,0), 0, 0, 0)   0x10179663–0x101796cc
Scout->SetCollision(1,1,1); Scout.bCollideWorld = 1; Level->SetActorZone(Scout, 1, 1)   0x101796d8–0x101796fa
```
No collision size is set here.

### 4.4 `addReachSpecs(AActor* node)` — `0x10176eb0` ✅
```
if IsA(LiftCenter):                                                                     0x10176ef8
    for e in Actors: if e && IsA(LiftExit) && e.LiftTag == node.LiftTag:   // +0x340 both, FName index compare  0x10176f38–0x10176f4a
        S = {Distance 500, Start node, End e, R 60, H 60, flags 0x20 (R_SPECIAL), bPruned 0}    0x10176f58–0x10176f76
        link(node → e, S)
        S' = same with Start e, End node;  link(e → node, S')                           0x10176fe8–0x10177065
    return                                   // a LiftCenter gets nothing else          0x1017707d
if IsA(Teleporter) || IsA(WarpZoneMarker):                                              0x101770a4 / 0x101770bb
    for o in Actors:
        match = IsA(Teleporter) ? o && IsA(o,Teleporter) && o != node && node.URL == *o.Tag          0x10177104–0x10177123
              : o && IsA(o,WarpZoneMarker) && o != node && node.markedWarpZone.OtherSideURL == *o.markedWarpZone.ThisTag   0x1017723d–0x1017726b
        if match: S = {Distance 100, node, o, R 150, H 150, flags 0x20}; link(node → o, S)          0x10177141–0x101771b9
    // falls through to the general pass
for o in Actors:                                                                        0x101771c2
    if !o || o.bDeleteMe || !IsA(o,NavigationPoint) || IsA(o,LiftCenter) || o == node: continue   0x101771d6–0x10177285
    if |node.Location - o.Location|² >= 1000000 (1000²): continue                        0x101772f0–0x101772fb
    if node.bOneWayPath && dot(o.Location - node.Location, node.Rotation.Vector()) <= 0: continue   0x10177301–0x10177373
    if |o - node|² < 1000: GLog->Logf("WARNING: %s and %s may be too close!")            0x101773cc–0x101773f7  (continues)
    S.Init(); if !S.defineFor(node, o, Scout): continue                                 0x10177403–0x10177417
    link(node → o, S)                                                                   0x10177419–0x1017746f

link(A → B, S):
    i = insertReachSpec(A.Paths, S);         if i == -1: return          // spec dropped entirely
    idx = ReachSpecs.AddItem(S)              // 0x10174f10: FArray::Add(1, 0x1c), copy 28 B, return Num-1
    A.Paths[i] = idx
    j = insertReachSpec(B.upstreamPaths, S); if j == -1: return          // spec kept, but absent from B's list
    B.upstreamPaths[j] = idx
```
No `bEndPointOnly`, `bPlayerOnly`, `bSpecialCost` or Mover/door test anywhere in this function. The
only node flag it consults is `bOneWayPath` (`+0x33c & 0x10`).

### 4.5 `insertReachSpec(INT* list, FReachSpec& S)` — `0x10179820` ✅
```
n = 0
while n < 16 && list[n] != -1 && ReachSpecs[list[n]].Distance > S.Distance: n++     0x1017985c–0x10179885
if list[15] == -1:                             // not full
    if list[n] != -1: shift list[n..] up one slot, stopping after the first -1 moved   0x1017988f–0x101798bb
    return n
// full
if n == 0: return -1                           // S longer than all 16: dropped        0x101798bd–0x101798c1
shift list[0..n-1] down one slot (list[0] — the longest — is evicted); return n-1      0x101798d8–0x101798f5
```
Every list is sorted **longest first** and keeps the 16 *shortest* edges. An evicted edge is not
marked pruned and stays in `ReachSpecs` and in the other endpoint's list.

### 4.6 `FReachSpec::defineFor(Start, End, Scout)` — `0x10193cd0` ✅
```
this.Start = Start; this.End = End
Scout.Physics = PHYS_Walking(1); Scout.JumpZ = 320; bCanWalk=bCanJump=bCanSwim=1; bCanFly=0      0x10193d14–0x10193d4e
Scout.GroundSpeed = 320; Scout.MaxStepHeight = 25                                       0x10193d54 / 0x10193d5e
return findBestReachable(Start.Location, End.Location, Scout)                           0x10193d7d
```

### 4.7 `FReachSpec::findBestReachable(FVector& A, FVector& B, Scout)` — `0x10193dd0` ✅
```
Scout->SetCollisionSize(18, 39); success = 0; step = 70 - R (= 52)                      0x10193e0c–0x10193e39
// phase 1: radius, binary search
loop while moving:
    r = FarMoveActor(Scout, A, 0, 0) && Scout.pointReachable(B, 0)                      0x10193e9b / 0x10193ec5
    oldstep = step; step *= 0.5
    if r: reachFlags = r; success = 1; bestR = R; bestH = H; SetCollisionSize(R + oldstep, 40)   0x10193eed–0x10193f29
          stop if step < 2 or R > 70                                                    0x10193f3d–0x10193f59
    else: SetCollisionSize(R - oldstep, H); stop if step < 2 or R < 18                  0x10193f5b–0x10193fac
// phase 2: height
if success: SetCollisionSize(bestR, H + 4); step = 70 - H                               0x10193fc2–0x10194009
loop while moving:
    r = FarMoveActor(Scout, A) && pointReachable(B, 0)
    if r: reachFlags = r; bestH = H; SetCollisionSize(R, H + step); step *= 0.5; stop if step < 1 or H > 70    0x10194082–0x101940f1
    else: SetCollisionSize(R, H - step); step *= 0.5; stop if step < 1 or H < 40                            0x101940f3–0x10194150
if success:
    CollisionRadius = (int)Scout.CollisionRadius; CollisionHeight = (int)bestH           0x10194167–0x1019418c  (cvtss2si = round-to-nearest)
    Distance = (int)|End.Location - Start.Location|; if reachFlags & R_SWIM(4): Distance *= 2   0x1019418f–0x101941c6
return success
```
`reachFlags` is whatever `pointReachable` returned: `walkReachable`/`fly`/`swim`/`jump` OR in
`1/2/4/8` (`0x10184718`, `0x101822f6`, `0x10183ccb`, `0x10182c88`); no `0x10` or `0x40` is ORed
anywhere in `pointReachable → Reachable → *Reachable` (grepped `0x10183340`, `0x1017d8f0`,
`0x101846e0`, `0x101822c0`, `0x10183c90`, `0x10182c50`). In the editor `pointReachable` skips its
800-uu 2-D cutoff (`GIsEditor` test `0x10183375`) 🔬; with `Physics = 1` `Reachable` dispatches
to `walkReachable` (`0x1017d9fc`).

### 4.8 `specFor(Start, End)` — `0x10179cb0` ✅
`for i<16: idx = Start.Paths[i]; if idx == -1 return -1; if ReachSpecs[idx].End == End return idx; return -1`.

### 4.9 `Prune(AActor* node)` — `0x10176790` ✅
```
count = 0
for i<16 while (ui = node.upstreamPaths[i]) != -1:        up = ReachSpecs[ui]   // A → node   0x101767d5–0x10176819
  for j<16 while (di = node.Paths[j]) != -1:              dn = ReachSpecs[di]   // node → B   0x1017681e–0x1017686b
    k = specFor(up.Start, dn.End); if k == -1: continue    direct = ReachSpecs[k]   // A → B  0x10176880–0x101768c1
    combined = up + dn      // Distance sum, R = min, H = min, flags = OR  (operator+ 0x10193a20)   0x101768d5
    if (float)direct.Distance * 1.2f < (float)combined.Distance: continue    // 1.2f at .rdata 0x10212d5c   0x101768f4–0x10176912
    if !( combined <= direct || direct.BotOnlyPath() || combined.MonsterPath() ): continue          0x10176922–0x10176944
    // prune `direct`:
    count++
    A = direct.Start: remove k from A.Paths (find in [0..15], shift-compact, Paths[15] = -1)           0x1017694e–0x101769ad
    A.PrunedPaths[first -1 slot, or slot 15 if none] = k                                                 0x101769ad–0x101769c4
    ReachSpecs[k].bPruned = 1                                                                            0x101769d9
    B = direct.End: remove k from B.upstreamPaths (same compaction, [15] = -1)                           0x101769de–0x10176a23
return count
```
Helpers (all ✅): `operator<=(other)` (`0x10193ad0`): `R >= other.R && H >= other.H &&
(flags | other.flags) == other.flags` — the combined route carries pawns at least as big and
needs no ability the direct edge does not. `BotOnlyPath` (`0x10193b90`): `R < 24`. `MonsterPath`
(`0x10193c20`): `R >= 52 && H >= 40 && !(flags & R_FLY)`. `operator==` (`0x10193960`) compares
Distance/R/H/flags only and is unused by the builder.

"No reachability lost" therefore means `combined <= direct`; the other two arms prune anyway when
the direct edge is bot-only or the detour is a monster-sized non-flying route. Only the direct
edge's index bookkeeping and its `bPruned` byte change; the spec stays in the array.

### 4.10 `addVisNoReach(AActor* node)` — `0x101774e0` ✅
```
if IsA(LiftCenter): return                                                              0x10177524
Scout->SetCollisionSize(18, 39); FarMoveActor(Scout, node.Location, 1, 0)               0x10177548–0x10177596
Scout.MoveTarget = node; Scout.bCanDoSpecial = 1                     // +0x240, +0x20c|0x20000   0x1017759f–0x101775b3
n = 0
for o = NavigationPointList; o; o = o.nextNavigationPoint:
    d2 = |node - o|²
    if IsA(o,LiftCenter) || o == node || d2 >= 4000000 (2000²) || n >= 16: continue      0x1017762c–0x10177659
    Hit(1.0); SingleLineCheck(Hit, Scout, End=o.Location, Start=node.Location, 6, Extent 0)   0x1017766c–0x101776a0
    if Hit.Actor: continue                                            // not visible    0x101776a6
    if Scout.findPathToward(o, 0, &best, 1):  w = (float)best.visitedWeight; if w == 10000000.0: continue   0x101776bb–0x101776dd
    else w = 200000000.0                                                                 0x101776e1
    if w*w > 4*d2: node.VisNoReachPaths[n++] = o                      // w > 2·dist     0x101776e9–0x10177709
```

### 4.11 `showPaths` / `hidePaths` / `removePaths` — `0x10179be0` / `0x10179750` / `0x10179b10` ✅
For every actor with `IsA(PathNode)`: `DrawType (+0x124) = DT_Sprite(1)` / `= DT_None(0)` /
`DestroyActor(a, 0)`; return the count. No `bAutoBuilt` filter in any of the three.

### 4.12 `createPaths(opt)` — `0x10177900` ✅ (auto PathNode placement; `opt` unused)
```
for a in Actors: if a && !bDeleteMe && IsA(NavigationPoint): a.visitedWeight = 1; a.bEndPoint = 0     0x1017793a–0x10177975
// pass 1: walk out from every pickup marker / player start
for a in Actors: if a && (IsA(InventorySpot) || IsA(PlayerStart)):                      0x101779a4 / 0x101779b7
    GLog->Logf("----------------------Starting From %s")
    if a.bEndPoint: GLog->Logf("%s already visited!"); continue                          0x101779e0
    testPathsFrom(a.Location)                                                            0x10177a12
// pass 2: merge auto-built nodes that sit within 128 uu of another node
Scout->SetCollisionSize(52, 40)                                                          0x10177a52–0x10177a64
for A in Actors: if !A || A.bDeleteMe || !A.bAutoBuilt || !IsA(NavigationPoint): continue   0x10177a8a–0x10177ab1
  for B in Actors: if !ValidNode(A, B): continue                                         0x10177ad4
    if |A - B|² >= 16384: continue                                                       0x10177b40–0x10177b4b
    if A.bOneWayPath && dot(B - A, A.Rotation.Vector()) <= 0: continue                   0x10177b51–0x10177bd8
    if !Model->FastLineCheck(A.Location, B.Location): continue                           0x10177c34
    GLog->Logf("Found potential merge pair %s and %s")
    if !TestReach(A.Location, B.Location): continue                                      0x10177cb9
    M = (A + B) * 0.5; midBad = 0; abort = 0                                             0x10177cce–0x10177d4c
    for C in Actors: if !ValidNode(A, C) || C == B: continue                             0x10177d70–0x10177d82
        if |A - C|² >= 640000 || |B - C|² >= 640000: continue                            0x10177de7–0x10177e57
        Scout->SetCollisionSize(52, 40)
        reach = FastLineCheck(A, C) && (TestReach(A, C) || (SetCollisionSize(24, 40), TestReach(A, C)))   0x10177ed0–0x10177fb9
        if !reach: continue
        if B.bAutoBuilt && !midBad:
            if FastLineCheck(M, C) && TestReach(M, C): continue     // C still reachable from the merged spot   0x1017803a–0x10178093
            midBad = 1                                                                   0x101780a8
        if FastLineCheck(B, C) && TestReach(B, C): continue                              0x10178108–0x1017816d
        abort = 1; break                                                                 → 0x10178283
    if abort: SetCollisionSize(52, 40); continue                                         0x10178286
    if B.bAutoBuilt: keep = A; GLog->Logf("remove %s", B); DestroyActor(B, 0)            0x101781a0–0x101781d3
    else:            keep = B; GLog->Logf("remove %s", A); DestroyActor(A, 0); removedA = 1   0x101781db–0x1017820b
    if !midBad: keep.Location = M; GLog->Logf("Move %s to %f %f")                        0x10178212–0x1017826b
    if removedA: break (next A)  else SetCollisionSize(52,40); next B                    0x10178274–0x1017827e
// pass 3: bridge visible, reachable pairs farther than 600 uu apart that have no intermediate
for A in Actors: if !A || A.bDeleteMe || !IsA(NavigationPoint) || IsA(LiftCenter): continue   0x101782d2–0x101782ff
  for B in Actors: if !ValidNode(A, B): continue
    if |A - B|² <= 360000: continue                                                      0x101783a5–0x101783ac
    if A.bOneWayPath && dot(B - A, A.Rotation.Vector()) <= 0: continue                   0x101783b2–0x10178434
    if !FastLineCheck(A, B): continue                                                    0x10178493
    GLog->Logf("Found potential distant pair %s (%f, %f) and %s (%f, %f)")
    FarMoveActor(Scout, A.Location, 0, 0); Scout.Physics = 1; if !Scout.pointReachable(B.Location, 0): continue   0x10178544–0x10178587
    dist = |A - B|; found = 0                                                            0x101785d2
    for C in Actors: if !ValidNode(A, C) || C == B: continue                             0x10178605–0x10178617
        if |A - C|² >= dist² || |B - C|² >= dist²: continue                              0x10178688–0x10178701
        if C.bOneWayPath && dot(B - C, C.Rotation.Vector()) <= 0: continue               0x10178707–0x10178766
        if !FastLineCheck(A, C) || !FastLineCheck(B, C): continue                        0x101787c5 / 0x1017882b
        GLog->Logf("Try %s Total %f versus %f + %f", C, dist, |A-C|, |C-B|)
        if 1.3 * dist <= |A-C| + |C-B|: continue                    // double 1.3 at 0x10212d68   0x10178939–0x10178945
        FarMoveActor(Scout, A); Physics=1; if !pointReachable(C): continue               0x10178980–0x101789c0
        FarMoveActor(Scout, C); Physics=1; if !pointReachable(B): continue               0x101789f8–0x10178a3b
        GLog->Logf("Found %s as intermediate"); found = 1; break                         0x10178a52
    if !found: M = (A + B) * 0.5; if FarMoveActor(Scout, M, 0, 0): newPath(Scout.Location)   0x10178a70–0x10178b28
// wrap-up
for a in Actors: if IsA(a, Pawn): a->SetCollision(1,1,1)                                 0x10178b69–0x10178b76
return count of actors with IsA(NavigationPoint) && bAutoBuilt                           0x10178b94–0x10178bb3
```
Pass 2 moves the survivor to the midpoint even when it is a hand-placed node (`keep = B`; the
midpoint test only runs when `B.bAutoBuilt`, so `midBad` stays 0).

### 4.13 `ValidNode(A, B)` — `0x10176de0` ✅
`B && B != A && !B.bDeleteMe && IsA(B, NavigationPoint) && !IsA(B, LiftCenter)`.

### 4.14 `TestReach(FVector from, FVector to)` — `0x10176aa0` ✅
`saved = Scout.Location; FarMoveActor(Scout, from, 0, 0) (result ignored); Scout.Physics = 1;
r = Scout.pointReachable(to, 0); FarMoveActor(Scout, saved, 0, 1); return r`.

### 4.15 `TestWalk(FVector delta, FCheckResult hit, float threshold, int bAdjust)` — `0x10176c00` ✅
```
saved = Scout.Location
r = Scout.walkMove(delta, hit, NULL, threshold, bAdjust); if r != 1: return r            0x10176ca4–0x10176cac
SingleLineCheck(hit, Scout, End = Location - (0,0, MaxStepHeight + CollisionHeight + 4), Start = Location, 6, Extent (16,16,1))   0x10176cb2–0x10176d3d
if hit.Time < 1: return 1                                          // floor under the scout       0x10176d43–0x10176d51
FarMoveActor(Scout, saved, 0, 1); return -1                        // ledge: undo the step        0x10176d6b–0x10176d9e
```

### 4.16 `FindBlockingNormal(FVector& n)` — `0x10174f60` ✅
```
Hit(1.0); E = Extent(R, R, H)
SingleLineCheck(Hit, Scout, End = Location - n*16, Start = Location, 6, E); if Hit.Time < 1: n = Hit.Normal; return   0x10175054–0x10175080
p = Location - n*16                                                                     0x101750dc
SingleLineCheck(Hit, Scout, End = p - (0,0,MaxStepHeight), Start = p, 6, E); if Hit.Time < 1: return   // floor ahead: keep n   0x1017517e–0x10175190
SingleLineCheck(Hit, Scout, End = p - (0,0,MaxStepHeight), Start = Location - (0,0,MaxStepHeight), 6, E); if Hit.Time < 1: n = Hit.Normal   0x10175235–0x10175261
```

### 4.17 `findScoutStart(FVector start)` — `0x10179230` ✅
```
if !FarMoveActor(Scout, start, 0, 0): GLog->Logf("Scout didn't fit"); return 0           0x1017929b–0x101795a9
Hit(1.0); down = (0,0,-50); i = 0
while Hit.Normal.Z < 0.7 && i < 50:                                                      0x101792e1 / 0x10179568
    MoveActor(Scout, down, Scout.Rotation, Hit, bTest=1, bNoFail=1, 0, 0)                0x1017933a
    if Hit.Time < 1 && Hit.Normal.Z < 0.7:                            // hit a steep surface: slide
        slide = (1 - Time) * (down - Normal * dot(down, Normal))                          0x10179368–0x1017942b
        if dot(down, slide) >= 0:
            MoveActor(Scout, slide, ..., 1, 1, 0, 0)                                      0x1017949b
            if Hit.Time < 1 && Normal.Z < 0.7: TwoWallAdjust(down.SafeNormal(), slide, Normal, OldNormal, Time, 0); MoveActor(Scout, slide, ..., 1,1,0,0)   0x101794fc–0x10179551
    i++
if Normal.Z >= 0.7: return 1;  GLog->Logf("No valid start found"); return 0              0x101795a2 / 0x10179571
```
`MoveActor` with `bTest=1` still moves the actor; the flag skips encroachment/touch work
(`0x10160e98`, `0x1016110a`, `0x10161470`) 🔬.

### 4.18 `testPathsFrom(FVector start)` — `0x10179d90` ✅
```
if !(findScoutStart(start) && |Scout.Z - start.Z| <= Scout.CollisionHeight):             0x10179de7–0x10179e14
    if !findScoutStart(start + (0,0,20)): return                                          0x10179e6c
dir = (1,0,0); f = 1
for radius = 70; radius >= 24; radius -= 7:                          // 70,63,...,28     0x10179edd / 0x10179f91
    Scout->SetCollisionSize(radius, 40)                                                   0x10179efc
    Pass2From(start, dir, f)                                                              0x10179f52
    f = -f; dir = (dir.y, dir.x, 0)                                  // X,Y,X,Y…         0x10179f5c–0x10179f87
```

### 4.19 `Pass2From(FVector start /*unused*/, FVector dir, float f)` — `0x101752c0` 🔬 (structure), ✅ (constants)
A wall-following walk. `perp = (-f·dir.y, f·dir.x, 0)` is the side the wall is expected on.
`start` is never read (no `[ebp+8..0x10]` access).
```
GLog->Logf("WALK WITH COLLISION SIZE %f %f")
for all live NavigationPoints: visitedWeight = 1; bEndPoint = 0                          0x10175336–0x10175374
Hit(1.0); while TestWalk(dir*16, Hit, 4.1, 0) == 1: ;               // walk to a wall    0x101753a0–0x101753ff
n = -dir; FindBlockingNormal(n); dir = (n.y, -n.x, 0)                                     0x10175401–0x10175486
anchor = NULL; best2 = 640000
for nav in live NavigationPoints: if |nav - Scout|² < best2 && TestReach(Scout.Location, nav.Location):   0x101754a6–0x101755cf
    GLog->Logf("----------------------Anchor %s"); anchor = nav; nav.Velocity = dir; nav.bEndPoint = 1; best2 = |nav - Scout|²
    (FarMoveActor(Scout, saved) after every test)
turns = 0; stall = 0; total = 0; last = Scout.Location; side = 0
while turns < 2 && stall < 1000:                                                          0x10175740–0x1017574f
    if |Scout.Location - last|² > 40000: stall = 0; last = Scout.Location  else stall++   0x101757b6–0x101757fc
    if ++total > 200: GLog->Logf("Total steps out of bounds"); stall = 2000               0x1017580d–0x1017582a
    prev = Scout.Location
    r = TestWalk(perp*16, Hit, 12.0, 0); fwd = (r == 1) ? 1 : TestWalk(dir*16, Hit, 4.1, 0)   0x10175907 / 0x1017596c
    SingleLineCheck(Hit, Scout, Location - (0,0,MaxStepHeight+CollisionHeight+4), Location, 6, (16,16,1))   0x10175a1a
    if anchor && Hit.Time < 1 && !TestReach(Scout.Location, anchor.Location):             // lost the anchor   0x10175a23–0x10175ac4
        old = anchor; best = NULL; bestd2 = 65536; lim = 65536
        for nav in live NavigationPoints with |nav - Scout|² < lim:                       0x10175aef–0x10175b9a
            if TestReach(Scout, nav): if |nav-Scout|² < bestd2: best = nav, bestd2 = …     0x10175beb–0x10175c0c
               if TestReach(nav, anchor) && TestReach(nav, prev):                          0x10175c58 / 0x10175cb0
                   GLog->Logf("---------------------- New Anchor %s"); anchor = nav
                   turns = (nav.bEndPoint && dot(dir, nav.Velocity) > 0.9) ? turns+1 : 0   // 0.9 double at 0x10212d60   0x10175ceb–0x10175d29
                   nav.Velocity = dir; nav.bEndPoint = 1; lim = |nav - Scout|²
        if anchor == old:                                                                 0x10175e3a
            GLog->Logf("didn't find new anchor")
            if bestd2 < 2500:                                                             0x10175e62
                GLog->Logf("Check closest path %s", best); M = (prev + best.Location)/2; ok1 = ok2 = 1
                for nav with ValidNode(best,nav) && |best-nav|² < 640000 && pointReachable-from-best(nav):   0x10175f7e–0x10176038
                    if ok1: ok1 = TestReach(prev, nav);  if ok2: ok2 = TestReach(M, nav);  if !ok1 && !ok2: break
                if ok2: anchor = best; best.Location = M                                  0x1017619b–0x101761c5
                elif ok1: anchor = best; best.Location = prev                             0x101761df–0x10176206
                elif bestd2 >= 1000: goto ADD                                             0x1017621a
            else ADD:
                new = newPath(prev); if !new: return                                      0x10176258–0x10176278
                if |new - old|² < 1000: DestroyActor(new); new = old                      0x101762e4–0x101762fa
                elif best && |new - best|² < 1000: DestroyActor(new); new = best          0x1017648c–0x101764f5
                else for nav in live NavigationPoints != new: if |new-nav|² < 1000 && FastLineCheck(new, nav): DestroyActor(new); new = nav; break   0x101764ff–0x1017661a
                anchor = new; if ++new.visitedWeight > 10: stall = 5000                   0x10176303–0x1017631e
                new.Velocity = dir; new.bEndPoint = 1; GLog->Logf("---------------------- ADD Anchor %s at %f %f")
            if anchor != old: total = 0                                                   0x1017639c–0x101763aa
        FarMoveActor(Scout, saved location)                                               0x101763e0
    if r == 1:                                                        // open on the wall side
        if !anchor && side == 0: anchor = newPath(prev)                                    0x101763f3–0x1017641f
        if ++side > 100: stall = 3000                                                      0x1017642a–0x10176439
        if side < 3: dir = perp                                                            0x1017643f–0x10176480
    elif fwd != 1:                                                    // blocked both ways
        side = 4; n = -dir; FindBlockingNormal(n); dir = (-f·n.y, f·n.x, 0)                0x10176648–0x101766ef
    else: side = 0                                                                         0x101766f8
GLog->Logf("Num steps %d", stall)                                                          0x10176722
```
Side effects on existing nodes: `Velocity`, `bEndPoint`, `visitedWeight`, and in the "closest
path" case `Location`. These happen only under `PATHS BUILD`, never `DEFINE`.

### 4.20 `newPath(FVector loc)` — `0x10179950` ✅
```
if Scout.CollisionHeight < 48: loc.Z += 48 - Scout.CollisionHeight                       0x10179990–0x101799aa
p = SpawnActor(Class("PathNode"), None, 0, 0, loc, (0,0,0), 0, bNoCollisionFail=1, 0)     0x101799b1–0x10179a1e
if !p: GLog->Logf("Failed to add path!"); return NULL
GLog->Logf("Added new path %s at %f %f"); p.bAutoBuilt = 1; Paths[] = upstreamPaths[] = -1; return p   0x10179a9e–0x10179ac7
```

## 5. Answers

**(a) buildPaths pipeline / `opt`.** §3. `opt` reaches `createPaths` and is never read; LOWOPT,
default and HIGHOPT run identical code. ✅

**(b) definePaths spawns** a `WarpZoneMarker` (`markedWarpZone` = the zone) per `WarpZoneInfo` and
an `InventorySpot` (`markedItem` = item; item `myMarker` = spot) per `Inventory`, at the scout's
dropped-to-floor position (§4.2), then builds every reachspec. The auto-placement functions are
reachable **only** through `createPaths` ← `buildPaths` (`--callers`: `testPathsFrom` ←
`createPaths 0x10177a12`; `Pass2From` ← `testPathsFrom 0x10179f52`; `newPath` ← `Pass2From
0x10176258/0x1017641f`, `createPaths 0x10178b28`; `findScoutStart` ← `definePaths` (marker
placement only) and `testPathsFrom`; `TestWalk`/`FindBlockingNormal` ← `Pass2From` only).
`PATHS DEFINE` never auto-places. ✅

**(c) createPaths ≠ reachspec builder.** Candidate pairs come from `addReachSpecs` (§4.4): every
ordered pair of live NavigationPoints (LiftCenter excluded; LiftCenter↔LiftExit and
Teleporter/WarpZone pairs hardwired), straight-line distance < 1000 uu, `bOneWayPath` honoured
via the node's `Rotation`; `bEndPointOnly`/`bPlayerOnly` are not consulted. Per pair: one
`defineFor` → `findBestReachable` (radius search from 18 in [18,70], then height from 40+4 in
[40,70]); spec = round(largest radius), round(largest height), flags from `pointReachable`,
Distance = round(|End−Start|) (×2 if swim). Bookkeeping: §4.5 — lists sorted longest-first, a
17th edge evicts the longest (or is dropped if it is the longest itself); one-sided drops
possible. VisNoReach: §4.10 — up to 16 visible-but-unreachable-or-2×-detour nodes within 2000 uu.

**(d) Prune** §4.9: `1.2f` at `0x10212d5c`; criterion `combined.Distance ≤ 1.2·direct.Distance &&
(combined <= direct || direct.R < 24 || combined is a 52/40 non-fly path)`. Mutates `A.Paths`,
`A.PrunedPaths`, `B.upstreamPaths`, `spec.bPruned`.

**(e) Special edges** §4.4: Lift 500/60/60/0x20 both ways; Teleporter and WarpZone 100/150/150/0x20
one way per matching URL/Tag. Nothing in this cluster or in the `*Reachable` family writes `0x10`
or `0x40` into `reachFlags`; `R_DOOR`/`R_PLAYERONLY` stay 📖 (enum values unconfirmed, and UED22
has no writer).

**(f) On-disk.** All of these are non-transient properties (flags read from `Engine.u`: none carries
`0x2000`), so they land in the map when non-default: `ULevel.ReachSpecs` (28-B in-memory records
incl. `bPruned`); per NavigationPoint `Paths[16]`, `upstreamPaths[16]`, `PrunedPaths[16]`,
`VisNoReachPaths[16]`, `nextNavigationPoint` (const, set by definePaths); `Inventory.myMarker`,
`InventorySpot.markedItem`, `WarpZoneMarker.markedWarpZone`; `LevelInfo.NavigationPointList`.
BUILD additionally leaves `visitedWeight`/`bEndPoint`/`Velocity` (and moved `Location`s) on
nodes and `bAutoBuilt` on new PathNodes; SHOW/HIDE change `DrawType`. Which of these the retail
`.dx` files actually carry is for the on-disk finding. 🔬

## 6. Constants

| Value | Where | Meaning |
|---|---|---|
| `1000000.0` `0x1020296c` | addReachSpecs `0x101772f0` | pair cutoff 1000² |
| `1000.0` `0x10202960` | addReachSpecs `0x101773cc`; Pass2From dedupe `0x101762dc` | "too close" warning (d² < 1000); node dedupe radius² |
| `500 / 60 / 60 / 0x20` | `0x10176f58`–`0x10176f76` | Lift edge |
| `100 / 150 / 150 / 0x20` | `0x10177141`–`0x1017715c` | Teleporter / WarpZone edge |
| `18, 39` / `70` / `40` / `+4` / `2` / `1` | findBestReachable | sweep start, max radius/height, height base, height bump, step floors |
| `320 / 25 / 1(walk)` | defineFor `0x10193d18`–`0x10193d5e` | scout JumpZ, MaxStepHeight, Physics |
| `-1.0 / 320 / 24` | buildPaths `0x10177835`–`0x1017784f` | createPaths scout JumpZ / GroundSpeed / MaxStepHeight |
| `1.2f` `0x10212d5c` | Prune `0x101768fc` | detour factor |
| `24` / `52, 40` / `R_FLY` | BotOnlyPath / MonsterPath | prune helpers |
| `18, 39` / `4000000.0` `0x10212d94` / `16` / `6` / `10000000.0` `0x10212d98` / `200000000.0` `0x10212d9c` / `4.0` | addVisNoReach | scout size, 2000² radius, list cap, TRACE flags, "unreachable" weight, no-path weight, (2·dist)² |
| `52, 40` / `24, 40` | createPaths | merge-test scout sizes |
| `16384.0` `0x10212d84` / `640000.0` `0x10212d90` / `360000.0` `0x10212d8c` / `1.3` `0x10212d68` (f64) | createPaths | merge radius², neighbour radius², distant-pair floor², detour factor |
| `70 → 24 step 7` / `40` / `20` | testPathsFrom | walk radii, walk height, retry lift |
| `16` / `4.1` / `12.0` / `(16,16,1)` / `+4` | Pass2From, TestWalk | step length, walkMove thresholds, floor-probe extent, probe slack |
| `640000` / `65536` / `2500` / `1000` / `40000` / `200` / `1000` / `2` / `0.9` / `10` / `100` / `3` | Pass2From | anchor radius², re-anchor radius², closest-path radius², dedupe², progress², total-step cap, stall cap, turn cap, heading dot, visit cap, side-step cap, turn limit |
| `-50` / `0.7` / `50` | findScoutStart | drop step, floor normal Z, iteration cap |
| `48` | newPath `0x10179990` | PathNode spawn height |
| `52, 50` | Scout class defaults (`Engine.u`) 🔬 | initial scout size in definePaths |

## 7. Evidence table (RVA → fact)

| RVA | Fact |
|---|---|
| `ued-editor 0x10064f60/0x10064f7c` | `xor esi,esi` on LOWOPT; `cmovne esi,2` on HIGHOPT; else 1 |
| `ued-editor 0x10064fb2` | `call [0x100ceba4]` = `FPathBuilder::buildPaths(Level, opt)` |
| `ued-editor 0x10065201/0x10065213` | DEFINE = `undefinePaths` then `definePaths` |
| `0x101777d6+0x101777dd` | strip: `IsA(PathNode) && [+0x33c]&0x40` → `DestroyActor` (vslot 37) |
| `0x1017785e` | `createPaths([ebp+0xc])`; `0x10177900`–`0x10178bc7` contain no `[ebp+8]` read |
| `0x10178c7e..0x101791b1` | definePaths order: getScout, markers, addReachSpecs loop, Prune loop, addVisNoReach loop, destroy scout |
| `0x101790a2/0x101790b5` | `NavigationPointList` prepend (`LevelInfo+0x464`) |
| `0x10178d43/0x10178dab` | WarpZone marker: `Scout.Region.Zone (+0x88) == WZ.Region.Zone` |
| `0x10178d62/0x10178e05` | scout radius 20 then 24 for the WarpZone retry |
| `0x10178f20` | Inventory fallback offset `40 - Inv.CollisionHeight` |
| `0x10176f58..0x10176f76` | Lift spec 0x3c/0x3c/0x20/0x1f4 |
| `0x10177141..0x1017715c` | Teleporter/WarpZone spec 0x96/0x96/0x20/0x64 |
| `0x10177116/0x10177123` | `FName::operator*` on `o.Tag`; `FString::operator==` on `node.URL (+0x340)` |
| `0x10177252/0x10177265` | `markedWarpZone.ThisTag (+0x374)` vs `markedWarpZone.OtherSideURL (+0x368)` |
| `0x101772f0` | `comiss 1000000.0, d²; jbe skip` |
| `0x10177301` | `test [node+0x33c], 0x10` (bOneWayPath) |
| `0x10177410` | `FReachSpec::defineFor(node, o, Scout)` |
| `0x1017742b/0x10177467` | `insertReachSpec == -1` → skip AddItem / skip upstream write |
| `0x1017987d..0x10179885` | insert loop continues while `ReachSpecs[list[n]].Distance > S.Distance` |
| `0x101798bd..0x101798f5` | full list: `n==0 → -1`, else evict slot 0, return `n-1` |
| `0x10193e0c/0x10193e29` | sweep start (18,39), step `70-R` |
| `0x10193f16` | success → `SetCollisionSize(R+step, 40)` |
| `0x10193fca/0x10193ffc` | height phase `H+4`, step `70-H` |
| `0x101941a5..0x101941c6` | Distance = round(size), ×2 if `flags & 4` |
| `0x10193d5e` | defineFor `MaxStepHeight = 25.0` |
| `0x101768fc/0x1017690f` | `direct.Distance*1.2f` vs `combined.Distance`, `jb` skip |
| `0x10176922/0x1017692e/0x1017693d` | `operator<=`, `BotOnlyPath`, `MonsterPath` chain |
| `0x101769d9` | `ReachSpecs[k].bPruned = 1` |
| `0x101769a3/0x10176a23` | `Paths[15] = -1` / `upstreamPaths[15] = -1` after compaction |
| `0x10193b04..0x10193b1d` | `operator<=`: R,H ≥ and `(a.flags|b.flags)==b.flags` |
| `0x10193c52..0x10193c5e` | MonsterPath `R>=0x34 && H>=0x28 && !(flags&2)` |
| `0x10193bc4` | BotOnlyPath `R < 0x18` |
| `0x101775ae` | addVisNoReach `Scout.bCanDoSpecial` (`+0x20c|=0x20000`) |
| `0x1017764d/0x10177656` | `4000000.0` radius², `edi < 0x10` cap |
| `0x101776a6` | `Hit.Actor (+4) != 0` → not visible |
| `0x101776d2..0x101776fd` | weight `== 1e7` skip; `w² > 4·d²` |
| `0x10177702` | `VisNoReachPaths[n] (+0x2d4)` |
| `0x10177a52` | createPaths scout (52,40) |
| `0x10177b40/0x10177de7/0x101783a5/0x10178939` | 16384 / 640000 / 360000 / 1.3 |
| `0x101781a0..0x1017820b` | merge keeps A if `B.bAutoBuilt`, else keeps B and destroys A |
| `0x10178b70` | `SetCollision(1,1,1)` on every Pawn |
| `0x10178b9b` | return counts `[+0x33c]&0x40` NavigationPoints |
| `0x10176b41/0x10176b6c/0x10176ba0` | TestReach: `Physics=1`, `pointReachable`, restore with `bNoCheck=1` |
| `0x10176cb9..0x10176ce0` | TestWalk floor probe extent (16,16,1), depth `MaxStep+H+4` |
| `0x10174fdc/0x101750e5` | FindBlockingNormal probe `n*16`, drop `MaxStepHeight` |
| `0x101792c5/0x101792d9/0x10179568` | findScoutStart `-50`, `0.7`, `50` |
| `0x10179ee6..0x10179efc`, `0x10179f91` | testPathsFrom radii `70`, `-7`, height `40` |
| `0x101753aa/0x101758c0` | TestWalk thresholds `4.1` / `12.0` |
| `0x101757b6/0x1017580d/0x10175749/0x10175740` | `40000`, `0xc8`, `0x3e8`, turns `2` |
| `0x10175ad3/0x10175e62/0x1017621a/0x10176313/0x10176431/0x1017643f` | `65536`, `2500`, `1000`, `10`, `100`, `3` |
| `0x10175d1a` | `comisd` with `0.9` (`0x10212d60`) |
| `0x10175605..0x10175628`, `0x10175d30..0x10175d48` | anchor `Velocity = dir`, `bEndPoint |= 2` |
| `0x101761ab/0x101761ec` | closest-path node `Location = M` / `= prev` |
| `0x10179990/0x101799d6/0x10179a9e` | newPath `48`, `bNoCollisionFail=1`, `bAutoBuilt` |
| `0x10179c46/0x101797b6/0x10179b7d` | show/hide `DrawType (+0x124)`; remove `DestroyActor` on `IsA(PathNode)` |
| `0x1017a0f4..0x1017a134` | undefinePaths marker classes (WarpZoneMarker, TriggerMarker, InventorySpot, ButtonMarker) |
| `0x1017a155` | `markedItem.myMarker (+0x28c) = 0` |

## 8. Open questions

- `R_DOOR = 16` / `R_PLAYERONLY = 64`: no writer found in Engine.dll's builder or `*Reachable`
  code; the enum values stay 📖. Tried: OR-instruction grep over the six reachability functions
  and this cluster; `describeSpec` (`0x10171fe0`) prints no flag names.
- Whether retail `.dx` files carry `visitedWeight`/`bEndPoint`/`Velocity`/`nextNavigationPoint` on
  NavigationPoints (non-transient here, so UED22 would write them when non-default) — check
  against real files; also whether DX's own builder (`dx-engine`) has the same side effects.
- `ULevel::MoveActor` `bTest` semantics (🔬 "moves but skips encroach/touch") was read from three
  branch sites only, not the whole 0xc00-byte function.
- `walkMove`'s `threshold` (4.1 / 12.0) and `pointReachable`'s exact editor-mode behaviour belong to
  the reachability cluster; not read here beyond the dispatch (`Physics 1|3 → walkReachable`,
  `4 → flyReachable`, water zone → `swimReachable`, `0x1017d923`–`0x1017d9fc`).
- The Scout's default collision size (52/50) comes from the `.u` via uedcli, not from the DLL.
