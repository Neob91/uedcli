# 11 — UED22 reachability: `APawn::*Reachable`, `FReachSpec`, `ANavigationPoint` path lists

Binary: `ued-engine` (`uned/UED22/Engine.dll`, base `0x10000000`). All RVAs below are VAs in that
image. Field names come from `layout.py ued Engine.<Class>`; every function was read to its `ret`.
Legend per `00-method.md`: ✅ read from the code · 🔬 inferred (inference stated) · 📖 public-source
hypothesis, not confirmed here.

Struct offsets used throughout (✅ from `layout.py` + the disassembly):
`Actor`: `+0x28` flag word (`bStatic` 0x1, `bDeleteMe` 0x80), `+0x2c Physics`, `+0x64 Level`,
`+0x68 XLevel`, `+0x88 Region.Zone`, `+0x90 Region.ZoneNumber`, `+0xd0 Location`, `+0xdc Rotation`,
`+0x100 Velocity`, `+0x11c` (`bSelected` 0x4), `+0x160` (`bCollideWhenPlacing` 0x8000, `bMovable`
0x20000), `+0x190 CollisionRadius`, `+0x194 CollisionHeight`, `+0x198` (`bCollideActors` 0x1,
`bCollideWorld` 0x2, `bBlockActors` 0x4, `bBlockPlayers` 0x8). `Pawn`: `+0x20c` flag word
(`bIsPlayer` 0x2, `bCanJump` 0x1000, `bCanWalk` 0x2000, `bCanSwim` 0x4000, `bCanFly` 0x8000,
`bCanOpenDoors` 0x10000, `bCanDoSpecial` 0x20000), `+0x224 FootRegion.Zone`, `+0x268 MeleeRange`,
`+0x26c GroundSpeed`, `+0x27c JumpZ`, `+0x280 MaxStepHeight`, `+0x2e8 BaseEyeHeight`,
`+0x338 ReducedDamageType`. `ZoneInfo`: `+0x210 ZoneGravity`, `+0x21c ZoneVelocity`,
`+0x22c ZoneFluidFriction`, `+0x244 DamageType`, `+0x27c` (`bWaterZone` 0x1, `bPainZone` 0x20).
`NavigationPoint`: `+0x214 upstreamPaths[16]`, `+0x254 Paths[16]`, `+0x294 PrunedPaths[16]`,
`+0x320 nextNavigationPoint`, `+0x33c` (`bAutoBuilt` 0x40). `LevelInfo`: `+0x418 NetMode`,
`+0x464 NavigationPointList`. `WarpZoneMarker +0x340 markedWarpZone`. `Inventory +0x28c myMarker`.
`ULevel` (native): `+0x8c ReachSpecs.Data`, `+0x90 ReachSpecs.Num`, `+0x98 Model` 🔬, `+0x1150`
flag word (bit 0x2 = "reachspecs need cleanup", see §6). `FCheckResult`: `+4 Actor`, `+0x1c
Normal.Z`, `+0x24 Time` (ctor `0x101247d0` zeroes `+4..+0x20`, stores `Time` at `+0x24` ✅).
`ULevel` vtable (`0x101fca5c`): slot 34 `MoveActor`, 35 `FarMoveActor`, 44 `FindSpot`, 46
`CheckEncroachment`, 48 `SingleLineCheck`, 58 `SetReachSpec` ✅ (resolved from the vtable). Actor
vtable slot 7 = `Core.dll!UObject::Modify` ✅ (`0x101b349a` thunk).

## Key results (details below)

- `supports()` is `(spec.reachFlags & pawnFlags) == spec.reachFlags` — the PAWN must have every flag
  the SPEC needs (✅ `0x1011aa53`). The prior reading had it backwards.
- `defineFor` does not compute anything itself: it sets the scout to walking / `JumpZ=320` /
  `GroundSpeed=320` / `MaxStepHeight=25` / `bCanWalk|bCanJump|bCanSwim`, `!bCanFly`, then
  `findBestReachable` does the whole job — including `Distance` (✅ `0x10193d14`–`0x10193d7d`).
- `Distance = appRound(|End.Location − Start.Location|)` (`cvtss2si`, round-to-nearest, NOT
  truncation), then `×2` if `R_SWIM` (✅ `0x101941a5`–`0x101941c6`). `CollisionRadius/Height` are
  `appRound` of the best scout size found.
- `findBestReachable` is two binary searches: radius from 18 with step 52 (cap 70, stop when
  step < 2), then height from 44 with step 26 (cap 70, stop when step < 1); the height sweep starts
  at `CollisionHeight+4` after the radius sweep forced height 40 (✅ §3.8).
- In the editor (`GIsEditor`) `walkReachable` steps **16 uu** per `walkMove`, ≤100 iterations, arrival
  = 2-D distance ≤ 15 and |ΔZ| < `CollisionHeight` (✅ §4.4). `MAXTESTMOVESIZE=128` is the in-game
  value for jumping pawns only.
- Step-up = `MaxStepHeight` (25 for `defineFor` tests, 48 inside `FindJumpUp`); drop test =
  `MaxStepHeight+2`; floor slope limit `Normal.Z ≥ 0.7`. A ledge is not a failure: the scout
  `bCanJump`, so a fall of ANY height is accepted via `FindBestJump` as long as it lands ≥ 8 uu closer
  (✅ §4.5, §4.10).
- `R_DOOR=16`, `R_PLAYERONLY=64`, `R_SPECIAL=32` confirmed from `calcMoveFlags` (✅ §8). Nothing in
  this cluster reads those bits; `supports` compares them generically.
- Path-list order: `insertReachSpec` keeps `Paths[]` sorted by DESCENDING `Distance` and evicts the
  longest edge when 16 are full (✅ §6.7). `SortPaths` (ascending) runs only from
  `UEngine::CleanupDestroyed` after a node is deleted, and `SetReachSpec` re-sorts ascending — the
  build calls neither: no direct call to `SortPaths` and no vtable-slot-58 call anywhere in
  `0x10174000`–`0x10179d00` (the `FPathBuilder` code) (✅ §1, §6.8). See open question 1 for the
  `Editor.dll` side.

## 1. Who calls what (direct `call rel32` scan of `.text`, ✅)

```
FPathBuilder::addReachSpecs ─┬─ FReachSpec::defineFor (0x10177410) ─ findBestReachable ─ pointReachable ─ Reachable ─ walk/fly/swimReachable
                             └─ insertReachSpec ×8
FPathBuilder::createPaths / Pass2From ── TestReach (×N) ── pointReachable          Pass2From ── TestWalk ── walkMove
<unexported fn after definePaths, 0x10179157> ── Prune ── specFor, operator+, operator<=, BotOnlyPath, MonsterPath
UEngine::CleanupDestroyed ── ANavigationPoint::SortPaths ── CompactSortPathList ×3
ANavigationPoint::Destroyed ── RemoveNavigationPoint, CompactSortPathList ×2, FreePaths, SetReachSpec (vslot 58)
ULevel::SetReachSpec ── CompactSortPathList ×4          APawn::CanMoveTo / TraverseFrom / breadthPath* ── supports
```
`operator==` has no caller in `Engine.dll`. `Editor.dll` imports `buildPaths` (called from
`UEditorEngine::Exec` `0x10064fb2`), `definePaths`, `undefinePaths`, `hidePaths`, `showPaths`,
`removePaths`, and `SetReachSpec` (referenced only by an unused `jmp [iat]` thunk `0x100aba8b`) —
not `SortPaths`.

## 2. `FReachSpec` layout and serializer ✅

In memory 28 bytes: `+0 INT Distance`, `+4 AActor* Start`, `+8 AActor* End`, `+0xc INT
CollisionRadius`, `+0x10 INT CollisionHeight`, `+0x14 INT reachFlags`, `+0x18 BYTE bPruned`
(`Init` `0x10112b32`–`0x10112b5b` zeroes exactly these; element stride `7*4` everywhere:
`lea ecx,[eax*8]; sub ecx,eax`).

`operator<<(FArchive&, FReachSpec&)` `0x10167960`: `Distance` (4, `ByteOrderSerialize`), `Start`
(vslot 6 = `operator<<(UObject*&)`, compact-index object ref), `End` (same), `CollisionRadius` (4),
`CollisionHeight` (4), `reachFlags` (4), `bPruned` (`0x101673e0` → `Ar.Serialize(&b, 1)`, 1 byte).
After reading, `Distance < 0` logs `"WARNING: ReachSpec has negative distance - %ls"` with
`String()`. `TArray<FReachSpec>` serializer `0x10167520`: compact-index count, then elements; on load
it `Empty()`s, `Realloc`s and appends one at a time. Confirms the prior reading's on-disk order.

`String()` `0x10115fe0` → `"[START] %ls [END] %ls [DIST] %d [COLRADIUS] %d [COLHEIGHT] %d [FLAGS]
%08x [PRUNED] %d"` (`.rdata 0x101fb0e0`), names via `GetFullName`-style helper `0x10112270` 🔬.

## 3. `FReachSpec` methods

### 3.1 `supports(INT r, INT h, INT flags)` `0x1011aa40` ✅
```
return CollisionRadius >= r && CollisionHeight >= h && (reachFlags & flags) == reachFlags;
```
(`0x1011aa53` `and eax,[flags]; cmp eax,[this+0x14]`). The query's flags must be a superset of the
spec's. Callers pass `calcMoveFlags()` (§8).

### 3.2 `operator==` `0x10193960` ✅
`Distance == o.Distance && CollisionRadius == && CollisionHeight == && reachFlags ==`. `Start`/`End`/
`bPruned` are NOT compared. No caller.

### 3.3 `operator+` `0x10193a20` ✅
```
R.CollisionRadius = min(a.CollisionRadius, b.CollisionRadius);   // 0x10193a57-64
R.CollisionHeight = min(a.CollisionHeight, b.CollisionHeight);   // 0x10193a67-71
R.reachFlags      = a.reachFlags | b.reachFlags;                 // 0x10193a74-7a
R.Distance        = a.Distance + b.Distance;                     // 0x10193a7d-81
// R.Start / R.End / R.bPruned are left uninitialised (caller's temporary).
```

### 3.4 `operator<=(const FReachSpec& o)` `0x10193ad0` ✅
```
return CollisionRadius >= o.CollisionRadius && CollisionHeight >= o.CollisionHeight
    && (reachFlags | o.reachFlags) == o.reachFlags;     // this.flags ⊆ o.flags
```
Read "this is at least as roomy as `o` and needs no ability `o` doesn't".

### 3.5 `BotOnlyPath()` `0x10193b90` ✅ — `return CollisionRadius < 24;` (`0x10193bc4`).

### 3.6 `MonsterPath()` `0x10193c20` ✅ — `return CollisionRadius >= 52 && CollisionHeight >= 40 && !(reachFlags & R_FLY);` (`0x10193c52`–`0x10193c5e`).

### 3.7 `defineFor(AActor* begin, AActor* dest, APawn* Scout)` `0x10193cd0` ✅
```
Start = begin; End = dest;                                     // 0x10193d08, 0x10193d0e
Scout->Physics = 1 /*PHYS_Walking 📖 enum value*/;             // 0x10193d14
Scout->JumpZ = 320.0;                                          // 0x10193d18
Scout->bCanWalk = bCanJump = bCanSwim = 1; Scout->bCanFly = 0; // 0x10193d22-4e (0x2000|0x1000|0x4000, &~0x8000)
Scout->GroundSpeed = 320.0;                                    // 0x10193d54
Scout->MaxStepHeight = 25.0;                                   // 0x10193d5e
return findBestReachable(begin->Location, dest->Location, Scout);   // 0x10193d7d
```
So `buildPaths`' `MaxStepHeight=24` (prior reading) is overwritten to **25** for every `defineFor`
test; the scout's collision size is also reset by `findBestReachable`.

### 3.8 `findBestReachable(FVector& Start, FVector& End, APawn* Scout)` `0x10193dd0` ✅
```
Scout->SetCollisionSize(18.0, 39.0);                         // 0x10193e0c-1d
int success = 0; float step = 70.0 - Scout->CollisionRadius; // = 52   0x10193e29
int trying = 1; float bestRadius = 0, bestHeight = 0;
while (trying) {                                             // radius sweep, 0x10193e60
   int r = XLevel->FarMoveActor(Scout, Start, /*Test*/0, /*bNoCheck*/0);   // real move + FindSpot + encroachment, 0x10193e9b
   if (r) r = Scout->pointReachable(End, 0);                 // 0x10193ec5
   float oldStep = step; step *= 0.5;                         // 0x10193ed2 (halved BEFORE the branch)
   if (r) {
      reachFlags = r; success = 1;                            // 0x10193eed
      bestRadius = Scout->CollisionRadius; bestHeight = Scout->CollisionHeight;   // 0x10193ef7-f11
      Scout->SetCollisionSize(Scout->CollisionRadius + oldStep, 40.0);            // 0x10193f16-29
      if (step < 2.0 || Scout->CollisionRadius > 70.0) trying = 0;                // 0x10193f3d-59
   } else {
      Scout->SetCollisionSize(Scout->CollisionRadius - oldStep, Scout->CollisionHeight);  // 0x10193f5b-7c
      if (step < 2.0 || Scout->CollisionRadius < 18.0) trying = 0;                // 0x10193f90-ac
   }
}
if (success) {                                               // 0x10193fbc
   Scout->SetCollisionSize(bestRadius, Scout->CollisionHeight + 4.0);   // 0x10193fc2-e7  (height 40 → 44)
   trying = 1; step = 70.0 - Scout->CollisionHeight;          // = 26   0x10193ff4
   while (trying) {                                          // height sweep, 0x10194010
      int r = XLevel->FarMoveActor(Scout, Start, 0, 0) && Scout->pointReachable(End, 0);
      if (r) {
         reachFlags = r; bestHeight = Scout->CollisionHeight;                       // 0x10194085-90
         Scout->SetCollisionSize(Scout->CollisionRadius, Scout->CollisionHeight + step);  // 0x10194095-b2
         step *= 0.5; if (step < 1.0 || Scout->CollisionHeight > 70.0) trying = 0;  // 0x101940b7-f1
      } else {
         Scout->SetCollisionSize(Scout->CollisionRadius, Scout->CollisionHeight - step);  // 0x101940f3-118
         step *= 0.5; if (step < 1.0 || Scout->CollisionHeight < 40.0) trying = 0;  // 0x1019411d-50
      }
   }
   CollisionRadius = appRound(Scout->CollisionRadius);      // cvtss2si 0x10194174 (== bestRadius)
   CollisionHeight = appRound(bestHeight);                   // cvtss2si 0x10194188
   Distance = appRound((End->Location - Start->Location).Size());   // 0x1019418f-bc
   if (reachFlags & R_SWIM) Distance *= 2;                   // 0x101941be-c6
}
return success;
```
Sweep in practice: radius 18 → (ok) 70 → (ok: 96, out of range, stop; bestRadius 70) / (fail: 44 →
57 → 63.5 → 66.75 …) — the accepted radius is the last successful one; the height starts at 44 and
walks 44 → 70/18 → ±13 → ±6.5 → … until step < 1. In both sweeps the size change uses the step
before halving and the stop test the halved step. `bestHeight` stays 39 if the very first test is the only success (the height
loop then starts at 44 and fails). `reachFlags` is whatever `pointReachable` returned on the LAST
successful test (a smaller scout may have got `R_JUMP` where a larger one did not).

## 4. `APawn` reachability

### 4.1 `Reachable(FVector Dest, FLOAT Threshold, AActor* GoalActor)` `0x1017d8f0` ✅
```
if (Region.Zone->bWaterZone) return swimReachable(Dest, Threshold, 0, GoalActor);   // 0x1017d929-64
switch (Physics) { case 1: case 3: return walkReachable(Dest, Threshold, 0, GoalActor);   // 0x1017d981-87, 0x1017d9fc
                   case 4:         return flyReachable (Dest, Threshold, 0, GoalActor);   // 0x1017d989, 0x1017d9bf
                   default: return 0; }
```
📖 1 = `PHYS_Walking`, 3 = `PHYS_Swimming`, 4 = `PHYS_Flying` (standard `EPhysics`; consistent with
`defineFor`/`TestReach` writing 1 for the walking scout and `rotateToward` testing 10 = `PHYS_Spider`).

### 4.2 `pointReachable(FVector aPoint, INT bKnowVisible)` `0x10183340` ✅
```
if (!GIsEditor) { FVector d = aPoint - Location; d.Z = 0; if (d.SizeSquared() > 640000.0) return 0; }   // 0x10183380-be; editor: no range cap
FPointRegion pr = XLevel->Model->PointRegion(Level, aPoint);                       // 0x101833f2
if (!Region.Zone->bWaterZone && !bCanSwim && pr.Zone->bWaterZone) return 0;        // 0x101833fd-1c
if (!FootRegion.Zone->bPainZone && pr.Zone->bPainZone && pr.Zone->DamageType != ReducedDamageType) return 0;   // 0x10183438-5c
if (!bKnowVisible) {
   FCheckResult Hit(1.0);
   if (!XLevel->Model->FastLineCheck(aPoint, Location + FVector(0,0,BaseEyeHeight))) return 0;   // 0x10183497-e9 (BSP-only line check)
}
FVector RealLocation = Location;
if (XLevel->FarMoveActor(this, aPoint, /*Test*/1, /*bNoCheck*/0)) {   // FindSpot fit test, may adjust; 0x1018354d
   aPoint = Location;                                                   // use the adjusted spot   0x10183553-6b
   XLevel->FarMoveActor(this, RealLocation, 1, 1);
}
return Reachable(aPoint, 15.0, NULL);                                   // 0x101835a7 (Threshold 15.0)
```
If the scout cannot be placed at `aPoint` the ORIGINAL point is still tested. The build never passes
a `GoalActor`, so all "reached GoalActor" (=5) branches below are dead for `PATHS BUILD`.

### 4.3 `actorReachable(AActor* Other, INT bKnowVisible)` `0x1017df30` ✅ (game use; summary)
Pain/water/range guards as above (range cap 640000 only when `!GIsEditor` and `Other` is not a
Pawn); visibility via `XLevel->SingleLineCheck(Hit, this, Other->Location, eye, TraceFlags=6, Extent=0)`
(`0x1017e0b8`, 6 = `TRACE_Level|TRACE_Movers` 📖) requiring `Hit.Time == 1` or `Hit.Actor == Other`;
Threshold = `CollisionRadius + min(1.5·CollisionRadius, MeleeRange) + Other->CollisionRadius` for a
Pawn (`0x1017e0f7`–`0x1017e11e`, and if `Dist2 > 640000` Threshold = max(that, Dist−800)), else
15.0, or `Other->CollisionRadius + CollisionRadius − 2` for Inventory/Trigger (`0x1017e2f7`);
`FarMoveActor(Other->Location, 1, 0)` adjust as in 4.2; `GoalActor = Other` for a Pawn, else
`Other` if `Other->bBlockActors` or `Other` is a `WarpZoneMarker`, else NULL (`0x1017e421`–`0x1017e44c`);
`return Reachable(aPoint, Threshold, GoalActor)`.

Exec wrappers ✅: `execpointReachable(FVector aPoint)` `0x10181f20` → `pointReachable(aPoint, 0)`.
`execactorReachable(AActor* A)` `0x10181c80`: one actor arg; `A==NULL` → 0; an `Inventory` with
`myMarker` is replaced by its marker; if `A` is a `NavigationPoint`, `ReachSpecs.Num() > 0` and
`CollisionRadius ≤ 70`, a fast path walks `NavigationPointList` for nodes within
`max(48, CollisionRadius)` horizontally and `CollisionHeight` vertically and answers via
`CanMoveTo(node, A)` (returns 0 without tracing when a nearby node exists, `A` is unreachable from
it and `Physics != 4`); otherwise `actorReachable(A, 0)`.

### 4.4 `walkReachable(FVector Dest, FLOAT Threshold, INT reachFlags, AActor* GoalActor)` `0x101846e0` ✅
```
reachFlags |= R_WALK;                                       // 0x10184718
int success = 0, stillmoving = 1, ticks = 100;              // 0x101847f4
FVector OriginalPos = Location, OriginalVel = Velocity;
float Threshold2 = Threshold*Threshold;
float MaxTestMoveSize = 16.0;                               // 0x101847a6
if (!GIsEditor) { MaxTestMoveSize = CollisionRadius; if (bCanJump) MaxTestMoveSize = max(128.0, CollisionRadius); }   // 0x101847b8-ef
float MoveSize2 = MaxTestMoveSize²;
float MaxHeight = CollisionHeight; if (GoalActor) MaxHeight = max(MaxHeight, GoalActor->CollisionHeight);   // 0x10184807-23
FCheckResult Hit(1.0);
while (stillmoving == 1) {                                  // 0x10184840
   FVector Delta = Dest - Location; float DeltaZ = Delta.Z; Delta.Z = 0;
   float Dist2 = Delta.X² + Delta.Y²;                       // 2-D
   if (DeltaZ > MaxHeight) {                                // 0x101848b8
      double d = DeltaZ - MaxHeight;
      if (0.8*d*d > Dist2) { stillmoving = 0; continue; }   // too steep: 0x101848cd-df  → fail
   }
   if (Dist2 > Threshold2) {                                // 0x101848f3
      if (MoveSize2 > Dist2) stillmoving = walkMove(Delta, Hit, GoalActor, 8.0, 0);                             // 0x10184907-33
      else                   stillmoving = walkMove(Delta.SafeNormal()*MaxTestMoveSize, Hit, GoalActor, 4.1, 0); // 0x10184935-99
      if (stillmoving == 5) { stillmoving = 0; success = 1; }                        // reached GoalActor 0x101849ac
      else if (stillmoving != 1) {
         if (Region.ZoneNumber == 0) { stillmoving = 0; success = 0; }              // fell out of the world 0x101849c6
         else if (bCanFly) { stillmoving = 0; reachFlags = flyReachable(Dest, Threshold, reachFlags, GoalActor); success = reachFlags; }   // 0x101849e1-a2d
         else if (bCanJump) {                                                        // 0x10184a3f
            reachFlags |= R_JUMP;                                                    // 0x10184a4d (set BEFORE the attempt)
            if (stillmoving == -1)      stillmoving = FindBestJump(Dest, GroundSpeed*Delta.SafeNormal(), Landing, 1);   // ledge 0x10184ae4
            else if (stillmoving == 0)  stillmoving = FindJumpUp (Dest, GroundSpeed*Delta.SafeNormal(), Delta3D, 1);    // wall  0x10184b83
         }
         else if (stillmoving == -1 && MaxTestMoveSize > MaxStepHeight) { stillmoving = 1; MaxTestMoveSize = MaxStepHeight; }   // retry finer 0x10184b8f-b3
      }
      if (FootRegion.Zone->bPainZone && FootRegion.Zone->DamageType != ReducedDamageType) { stillmoving = 0; success = 0; }   // 0x10184bbb-e2
      if (Region.Zone->bWaterZone) {                                                  // 0x10184be5
         stillmoving = 0;
         if (bCanSwim && (!Region.Zone->bPainZone || Region.Zone->DamageType == ReducedDamageType))
            { reachFlags = swimReachable(Dest, Threshold, reachFlags, GoalActor); success = reachFlags; }   // 0x10184c57
      }
   } else {                                                 // within Threshold horizontally: 0x10184c79
      stillmoving = 0;
      if (MaxHeight > fabs(DeltaZ)) success = 1;            // 0x10184c88
      else if (0.95 > Hit.Normal.Z && Hit.Normal.Z > 0.7) { // standing on a slope: 0x10184ca8-cd
         if (DeltaZ < 0 && CollisionHeight + sqrt(1/Nz² - 1)*CollisionRadius > -DeltaZ) success = 1;   // 0x10184cd3-d42
         else {
            float GoalRadius = GoalActor ? GoalActor->CollisionRadius : 46.0;                        // 0x10184d62-7e
            if (GoalRadius > CollisionRadius && sqrt(1/Nz² - 1)*(GoalRadius + 15.0 - CollisionRadius) + MaxHeight > DeltaZ) success = 1;   // 0x10184d83-e16
         }
      }
   }
   if (--ticks < 0) stillmoving = 0;                        // every path: 0x10184e19 etc.
}
if (!success && GoalActor && GoalActor->IsA(AWarpZoneMarker)) success = (Region.Zone == GoalActor->markedWarpZone);   // 0x10184e2d-66
XLevel->FarMoveActor(this, OriginalPos, 1, 1); Velocity = OriginalVel;   // 0x10184e69-ba
return success ? reachFlags : 0;                            // 0x10184ec2
```
Arrival: 2-D distance ≤ Threshold (15) and |ΔZ| < `MaxHeight` (= scout `CollisionHeight` in the
build). `Hit` is the result of the LAST `walkMove` (its final downward move), so the slope
special-cases use the floor normal under the scout.

### 4.5 `walkMove(FVector Delta, FCheckResult& Hit, AActor* GoalActor, FLOAT threshold, INT bAdjust)` `0x101841b0` ✅
```
FVector StartLocation = Location; Delta.Z = 0;                      // 0x10184212
float GravDir = (Region.Zone->ZoneGravity.Z > 0) ? 1.0 : -1.0;      // 0x10184237-57
FVector Down = (0,0,GravDir*MaxStepHeight), Up = -Down;             // 0x1018425a-a5
XLevel->MoveActor(this, Delta, Rotation, Hit, /*Test*/1, /*IgnorePawns*/1, 0, 0);   // 0x101842f7
if (GoalActor && Hit.Actor == GoalActor) return 5;                  // 0x101842fd-30e
if (Hit.Time < 1.0) {                                               // blocked: step up, 0x10184313
   Delta *= (1 - Hit.Time);
   MoveActor(Up); MoveActor(Delta); if (GoalActor && Hit.Actor == GoalActor) return 5;   // 0x101843ad, 0x10184400
   MoveActor(Down);                 if (GoalActor && Hit.Actor == GoalActor) return 5;   // 0x1018445e
   if (Hit.Time < 1.0 && Hit.Normal.Z < 0.7) { if (bAdjust) FarMoveActor(StartLocation,1,1); return 0; }   // wall 0x10184474-8e
}
FVector Loc = Location;
MoveActor(this, (0,0,GravDir*(MaxStepHeight + 2.0)), Rotation, Hit, 1, 1, 0, 0);   // drop test 0x101844ca-54b
if (Hit.Time == 1.0) { FarMoveActor(bAdjust ? StartLocation : Loc, 1, 1); return -1; }   // no floor within MaxStepHeight+2: ledge 0x10184551-b5
if (Hit.Normal.Z < 0.7) { FarMoveActor(StartLocation, 1, 1); return -1; }               // floor too steep 0x101845cd-e3 (unconditional restore)
if (threshold² > (Location - StartLocation).SizeSquared()) { if (bAdjust) FarMoveActor(StartLocation,1,1); return 0; }   // moved too little 0x10184611-8e
return 1;
```
Return codes: 5 = touched `GoalActor`, 1 = advanced ≥ threshold, 0 = blocked (wall or too little
progress; with `bAdjust=0` the scout stays where it got to), −1 = ledge/steep floor.

### 4.6 `flyReachable` `0x101822c0` / `flyMove` `0x10181f90` ✅
```
flyReachable: reachFlags |= R_FLY; MaxTestMoveSize = max(200.0, CollisionRadius); ticks = 100;  // 0x101822f6, 0x1018238e
  loop: Dir = Dest - Location; Dist2 = |Dir|² (3-D);
        if (Dist2 <= Threshold² && |Dir.Z| <= CollisionHeight) { success = 1; break-ish }   // 0x1018242a-4d
        r = (MoveSize2 > Dist2) ? flyMove(Dir, GoalActor, 8.0, 0) : flyMove(Dir.SafeNormal()*MaxTestMoveSize, GoalActor, 4.1, 0);   // 0x101824f7
        if (r == 5) success = 1, stop; else if (r && Region.Zone->bWaterZone) { stop; if (bCanSwim && !(painzone…)) reachFlags = swimReachable(...), success = reachFlags; }   // 0x10182521-99
        ticks--.
  tail: WarpZoneMarker check, FarMoveActor(OriginalPos,1,1), Velocity restore, return success ? reachFlags : 0.
flyMove(Delta, GoalActor, threshold, bAdjust): Up = (0,0,+MaxStepHeight) (no gravity-direction test);
  MoveActor(Delta,1,1,0,0); GoalActor hit → 5; if (Hit.Time < 1) { Delta *= 1-Hit.Time; MoveActor(Up); MoveActor(Delta); GoalActor hit → 5; }
  if (threshold² > moved²) { if (bAdjust) restore; return 0; } return 1;                       // no drop move, no slope test
```

### 4.7 `swimReachable` `0x10183c90` / `swimMove` `0x10183870` ✅
Same skeleton as fly (`R_SWIM`, `MaxTestMoveSize = max(200, CollisionRadius)`, 3-D arrival,
`swimMove` thresholds 8.0 / 4.1, 100 ticks). Differences:
```
after swimMove: if (!Region.Zone->bWaterZone) {                          // left the water 0x10183ef5
      stillmoving = 0;
      if (bCanFly) { reachFlags = flyReachable(...); success = reachFlags; }                       // 0x10183f44
      else if (bCanWalk && Location.Z + 50.0 + MaxStepHeight > Dest.Z) {                            // 0x10183f73-96
         FCheckResult Hit(1.0);
         MoveActor(this, (0,0,max(CollisionHeight + MaxStepHeight, Dest.Z - Location.Z)), Rotation, Hit, 1,1,0,0);   // 0x10183fb3-4013
         if (Hit.Time == 1.0) { success = flyReachable(Dest, Threshold, reachFlags, GoalActor); reachFlags = R_WALK; }   // 0x10184032-73: flags become exactly 1
      }
   } else if (Region.Zone->bPainZone && DamageType != ReducedDamageType) { stillmoving = 0; success = 0; }   // 0x1018407f-a3
swimMove: Up/Down = ±MaxStepHeight (no gravity test). MoveActor(Delta); GoalActor → 5;
   if (!Region.Zone->bWaterZone) { FVector wl = findWaterLine(StartLocation, Location); if (wl != Location) MoveActor(wl - Location); return 0; }   // 0x101839b5-a9f: back to the water line
   step-up as flyMove; threshold test; return 1.
```

### 4.8 `jumpReachable(FVector Dest, FLOAT Threshold, INT reachFlags, AActor* GoalActor)` `0x10182c50` ✅
```
reachFlags |= R_JUMP; FVector Landing = Location;                  // 0x10182c88
jumpLanding(Velocity, Landing, 1);                                  // 0x10182ce8
if (Landing == Location_original) return 0;                         // 0x10182ced-d18
int r = walkReachable(Dest, Threshold, reachFlags, GoalActor);      // 0x10182d64 (from the landing spot)
XLevel->FarMoveActor(this, OriginalLocation, 1, 1); return r;
```
Not used by the build path (`walkReachable` calls `FindBestJump`/`FindJumpUp` instead).

### 4.9 `jumpLanding(FVector testVel, FVector& Landing, INT movePawn)` `0x101826b0` ✅
Ballistic simulation, `dt = 0.1` (`0x10202940`):
```
OriginalPos = Location; landed = 0; ticks = 0;
while (!landed) {
   Z = Region.Zone;
   testVel = testVel*(1 - 0.1*Z->ZoneFluidFriction) + 0.1*Z->ZoneGravity;     // 0x10182754-7f6
   FVector Delta = 0.1*(testVel + Z->ZoneVelocity);                           // 0x101827fb-84f
   FCheckResult Hit(1.0); MoveActor(this, Delta, Rotation, Hit, 1,1,0,0);      // 0x101828b3
   if (Region.Zone->bWaterZone) landed = 1;                                    // 0x101828bf
   else if (Hit.Time < 1.0) {
      if (Hit.Normal.Z > 0.7) landed = 1;                                      // 0x101828e9
      else { slide: Delta = (Delta - Normal*(Delta·Normal))*(1-Hit.Time); if (Delta·origDelta >= 0) { MoveActor(Delta); if (Hit.Time<1) { landed |= Normal.Z > 0.7; TwoWallAdjust(...); MoveActor(adjusted); landed |= Normal.Z > 0.7; } } }   // 0x101828fc-b03
   }
   ticks++;
   if (Region.ZoneNumber == 0 || ticks > 35 || testVel.SizeSquared() > 2500000.0) { FarMoveActor(OriginalPos,1,1); landed = 1; }   // 0x10182b0d-8b (abort → Landing = OriginalPos)
}
Landing = Location; if (!movePawn) FarMoveActor(OriginalPos, 1, 1);           // 0x10182b93-bea
```

### 4.10 `FindBestJump(FVector Dest, FVector vel, FVector& Landing, INT movePawn)` `0x1017b150` ✅
```
OriginalPos = Location; vel.Z = JumpZ;                                        // 0x1017b1a8 (320 for the scout)
SuggestJumpVelocity(Dest, vel);                                               // 0x1017b1db
jumpLanding(vel, Landing, 1);                                                 // 0x1017b209
if (FootRegion.Zone->bPainZone && DamageType != ReducedDamageType) r = 0;     // 0x1017b22d-4c
else if (!bCanSwim && Region.Zone->bWaterZone) r = 0;                         // 0x1017b24e-6b
else r = ((Dest - OriginalPos).Size() - (Dest - Location).Size() > 8.0);      // 0x1017b26d-96: landed ≥ 8 uu closer
if (!movePawn) FarMoveActor(OriginalPos, 1, 1); return r;
```
There is no fall-height limit: any landing counts (`walkReachable` continues from it). A miss only
happens when `jumpLanding` aborts (>35 steps = 3.5 s, |v|² > 2 500 000, or leaving the world).

`SuggestJumpVelocity(FVector Dest, FVector& vel)` `0x1017db40` 🔬 (read in full; summary):
`g = Region.Zone->ZoneGravity.Z`, or −100 if `g ≥ 0` (`0x1017db8b`); integrates `vz += g·0.05,
z += vz·0.05, t += 0.05` (`0x1017dd1a`) until descending at or below `Dest.Z − Location.Z`, corrects
`t` by `(z − dz)/vz` when |vz| > 1; then `vel.XY = dir(Dest−Location).XY × min(GroundSpeed, dist/t)`
(or `GroundSpeed` if `t ≤ 0`), `vel.Z` unchanged (= `JumpZ`).

### 4.11 `FindJumpUp(FVector Dest, FVector vel, FVector&, INT)` `0x1017b320` ✅
```
float saved = MaxStepHeight; MaxStepHeight = 48.0;                             // 0x1017b362
FCheckResult Hit(1.0);
int r = walkMove(vel.SafeNormal() * saved, Hit, NULL, 4.1, /*bAdjust*/1);     // 0x1017b3d0: one step of the OLD step length with a 48-uu step-up
if (r == 5) r = 1; MaxStepHeight = saved; return r;
```
This is the "jump height ≈ 48" of the prior reading: a wall ≤ 48 uu high is climbable as a jump
(`R_JUMP` was already OR'd in by the caller).

## 5. What blocks the scout (`MoveActor` / `FarMoveActor` / `IsBlockedBy`) ✅ partial

`ULevel::MoveActor` `0x101608e0` (read `0x10160b60`–`0x10160d5a` only): traces
`MultiLineCheck(GMem, Location+Delta, Location, Extent=(CollisionRadius,CollisionRadius,
CollisionHeight), bCheckActors = bCollideActors && !IsMovingBrush, Level = bCollideWorld &&
!IsMovingBrush ? GetLevelInfo() : NULL, 0)` (`0x10160bc1`–`0x10160c90`; `ebx = [Actor+0x198]` at
`0x10160b60`). Hits are then filtered (`0x10160cc6`–`0x10160d48`): skipped when `bIgnoreBases` and
based on the actor, when `IgnorePawns` and the hit actor is a non-static `Pawn` or `Decoration`,
when `IsBasedOn`, or when `!IsBlockedBy(hit)`. `walkMove/flyMove/swimMove/jumpLanding` all pass
`(Test=1, IgnorePawns=1, bIgnoreBases=0, bNoFade=0)` (📖 parameter names).

`AActor::IsBlockedBy(AActor* Other)` `0x10113fd0`: `Other == Level` → `bCollideWorld`; `Other` is a
`Brush` with a `Brush` model (Movers) → `bCollideWorld && (IsPlayer ? Other->bBlockPlayers :
Other->bBlockActors)` (`0x10114059`–`0x10114081`); otherwise `(GetPlayerPawn() || IsA(Projectile)) ?
Other->bBlockPlayers : Other->bBlockActors`. So a Mover (door) in its current state blocks the scout
iff the scout has `bCollideWorld` and the Mover has `bBlockActors` — closed doors are walls for the
build; nothing here opens them or emits `R_DOOR`.

`ULevel::FarMoveActor(Actor, Dest, Test, bNoCheck)` `0x1015ff80`: returns 0 for `bStatic`/
`!bMovable` actors outside the editor; `if (!bNoCheck && (bCollideWorld || (bCollideWhenPlacing &&
NetMode != 3))) result = FindSpot(Extent, newLocation, 0, 0)` (`0x1016006d`–`0x101600c3`, may nudge
the location); `if (result && !Test && !bNoCheck) result = !CheckEncroachment(Actor, newLocation,
Rotation, 1)` (`0x101600d7`–`0x1016012f`); on success sets `Location` and `OldLocation`
(`0x101601c9`–`0x1016020f`, skipped when `CollisionTag != 0` 🔬 unexplained gate), re-hashes, and
`SetActorZone(Actor, Test, 0)`. So `findBestReachable`'s `(0,0)` call is a real placement with
world-fit and encroachment checks; a scout size that does not fit at `Start` fails that size.

## 6. `ANavigationPoint` path lists, `ULevel::SetReachSpec`, related

### 6.1 `CompactSortPathList(INT* Paths)` `0x10171950` ✅ (unwind name `SortPathList`)
```
n = 0;
for (i = 0; i < 16; i++) { idx = Paths[i];
   if (idx >= 0 && idx < ReachSpecs.Num() && ReachSpecs[idx].Start && ReachSpecs[idx].End) n++; else Paths[i] = -1; }   // 0x101719a0-e8
j = 0; for (i = 0; i < n; i++) { while (Paths[j] == -1) j++; if (i != j) swap(Paths[i], Paths[j]); j++; }              // 0x101719ea-a1b: pack valid to the front
for (i = 0; i < n; i++) { best = i; for (j = i+1; j < n; j++) if (ReachSpecs[Paths[j]].Distance < ReachSpecs[Paths[best]].Distance) best = j;
                          if (best != i) swap(Paths[i], Paths[best]); }                                                  // 0x10171a1d-88: selection sort, ascending Distance
return n;
```
Slots `[n..15]` are `-1`. Ties keep the first encountered (subject to selection-sort swaps).

### 6.2 `SortPaths()` `0x10171f30` ✅ — `CompactSortPathList(Paths); CompactSortPathList(upstreamPaths); CompactSortPathList(PrunedPaths);`

### 6.3 `FreePaths()` `0x10171d70` ✅
For each of `Paths`, `PrunedPaths` (specs where `Start == this`) and `upstreamPaths` (`End == this`):
set the slot to −1, null the matching endpoint in the spec and `XLevel->SetReachSpec(zeroSpec, idx)`
(vslot 58) — the spec is wiped in place; the array never shrinks.

### 6.4 `Destroyed()` `0x10171ae0` ✅ (guard label "RestorePrunes")
```
check(Level);
if (nextNavigationPoint && !nextNavigationPoint->bDeleteMe) Level->RemoveNavigationPoint(this);   // 0x10171b32-46
nPaths = CompactSortPathList(Paths); nUp = CompactSortPathList(upstreamPaths);
TArray<INT> restore(nUp*16);
for each upstream spec u: A = Cast<ANavigationPoint>(u.Start); if (!A || (GIsEditor && A->bSelected)) continue;   // 0x10171bd1-e2
   for each p in A->PrunedPaths with ReachSpecs[p].Start == A: B = Cast<NavPt>(ReachSpecs[p].End);
      if (B && some Paths[m] of this has ReachSpecs[Paths[m]].End == B) restore.Add(p);           // 0x10171bf0-c6e
FreePaths();
for p in restore: spec = ReachSpecs[p]; spec.bPruned = 0; XLevel->SetReachSpec(spec, p);           // 0x10171c98-e1
XLevel->flags(+0x1150) |= 2;                                                                       // 0x10171cf0
```
Deleting a node un-prunes the direct edges A→B it had made redundant.

### 6.5 `execdescribeSpec` `0x10171fe0` ✅ — UnrealScript `describeSpec(int i, out Actor Start, out Actor End, out int ReachFlags, out int Distance)` (five args stepped in that order); `0 ≤ i < ReachSpecs.Num()` copies `Start`, `End`, `reachFlags`, `Distance`, else logs `"describeSpec: invalid ReachSpec index: %i/%i"` and zeroes the outs.

### 6.6 `ALevelInfo::RemoveNavigationPoint(N)` `0x1012e3e0` ✅ — unlinks `N` from the singly linked `NavigationPointList` (`+0x464` → `nextNavigationPoint`), calling `Modify()` on the predecessor object and on `N`, and nulls `N->nextNavigationPoint`.

### 6.7 `ULevel::SetReachSpec(const FReachSpec& spec, INT idx)` `0x101621c0` ✅
```
if (idx < 0 || idx >= ReachSpecs.Num()) idx = ReachSpecs.AddZeroed(1);                       // 0x101621f8-21e
FReachSpec& old = ReachSpecs[idx];
if (S = Cast<NavPt>(old.Start)) { list = old.bPruned ? S->PrunedPaths : S->Paths;
   for k<16: if (list[k] == idx) { S->Modify(); list[k] = -1; S->CompactSortPathList(list); break; } }   // 0x1016223f-8b
if (!old.bPruned && (E = Cast<NavPt>(old.End))) { same on E->upstreamPaths }                 // 0x1016228e-d9
ReachSpecs[idx] = spec;                                                                       // 0x101622de-f7
if (S = Cast<NavPt>(spec.Start)) { list = spec.bPruned ? S->PrunedPaths : S->Paths;
   for k<16: if (list[k] == -1) { S->Modify(); list[k] = idx; S->CompactSortPathList(list); break; } }   // 0x101622fa-348: silently dropped when full
if (!spec.bPruned && (E = Cast<NavPt>(spec.End))) { first -1 slot of E->upstreamPaths = idx; CompactSortPathList }   // 0x10162350-94
```
`FPathBuilder::insertReachSpec(INT* Paths, FReachSpec& spec)` `0x10179820` ✅ (the builder's own
insertion — returns the slot to write, the caller stores the index):
```
n = 0; while (n < 16 && Paths[n] != -1 && ReachSpecs[Paths[n]].Distance > spec.Distance) n++;   // 0x1017985c-85: skip LONGER edges
if (Paths[15] == -1) { shift Paths[n..] up one (stop at the first -1); return n; }             // 0x10179889-bb
if (n == 0) return -1;                                                                        // full and new edge is the longest: rejected 0x101798bd-c1
shift Paths[1..n-1] down one (drops Paths[0], the longest); return n-1;                       // 0x101798d8-f5
```
So during the build `Paths[]` is ordered by DESCENDING `Distance` (ties: newer first) and holds the
16 shortest edges.

### 6.8 `UEngine::CleanupDestroyed` `0x1014dfd0` (read `0x1014e0c0`–`0x1014e1c8`) ✅
For every level whose `+0x1150` has bit 2 (set by `Destroyed` above): clear it; for every reachspec
whose `Start` or `End` is `bDeleteMe`: null it, call `SortPaths()` on the surviving endpoint(s) that
are `NavigationPoint`s, and zero the spec. This is the ONLY caller of `SortPaths` in `Engine.dll`.

## 7. Consumers of the operators: `FPathBuilder::Prune(AActor* Node)` `0x10176790` ✅
```
pruned = 0;
for i<16 while upstreamPaths[i] != -1: up = ReachSpecs[upstreamPaths[i]];                    // A→Node
  for j<16 while Paths[j] != -1: down = ReachSpecs[Paths[j]];                                 // Node→B
     k = specFor(up.Start, down.End); if (k == -1) continue;                                  // 0x10176880 (specFor 0x10179cb0: scan A->Paths for End == B)
     direct = ReachSpecs[k]; combined = up + down;                                            // 0x101768d5
     if ((float)direct.Distance * 1.2 < (float)combined.Distance) continue;                   // 0x101768f4-912 (float compare)
     if (!(combined <= direct) && !direct.BotOnlyPath() && !combined.MonsterPath()) continue; // 0x10176922-44
     pruned++; A = direct.Start; B = direct.End;
     remove k from A->Paths (shift down, Paths[15] = -1); append k at A->PrunedPaths' first -1;  // 0x10176953-cb
     ReachSpecs[k].bPruned = 1;                                                               // 0x101769d9
     remove k from B->upstreamPaths (shift down, [15] = -1);                                  // 0x101769de-a23
return pruned;
```
Prune criterion: `combined.Distance ≤ 1.2·direct.Distance` AND (`combined` is at least as roomy and
needs no extra ability, OR the direct edge is bot-only (radius < 24), OR the combined route is a
monster path (≥52/≥40, no fly)).

`FPathBuilder::TestReach(FVector start, FVector end)` `0x10176aa0` ✅: `FarMoveActor(Scout, start,
0, 0)` (result ignored — if placement fails the test runs from the scout's previous spot 🔬);
`Scout->Physics = 1`; `r = Scout->pointReachable(end, 0)`; `FarMoveActor(Scout, old, 0, 1)`; return
`r`. Uses the scout's CURRENT size and `MaxStepHeight` (whatever `buildPaths` set), not `defineFor`'s.
`FPathBuilder::TestWalk` `0x10176c00` 🔬 (unexported, read once): `r = Scout->walkMove(Delta, Hit,
NULL, threshold, bAdjust)`; if `r != 1` return it; then `SingleLineCheck` straight down by
`MaxStepHeight + CollisionHeight + 4` with extent `(16,16,1)`, flags 6; floor hit → 1, else restore
and −1.

## 8. `APawn::calcMoveFlags()` `0x10116cb0` ✅ — the flag values
```
return bCanWalk<<0 | bCanFly<<1 | bCanSwim<<2 | bCanJump<<3 | bCanOpenDoors<<4 | bCanDoSpecial<<5 | bIsPlayer<<6;   // 0x10116ce2-d2c
```
i.e. `R_WALK=1, R_FLY=2, R_SWIM=4, R_JUMP=8, R_DOOR=16, R_SPECIAL=32, R_PLAYERONLY=64` — closes the
prior reading's open item (16 and 64 were inferred). Callers: `CanMoveTo` `0x10194708`,
`findRandomDest` `0x101972fa`; the result feeds `supports()` (§3.1).

## 9. Answers

(a) **Traversal test per mode.** Walking (the build): `walkReachable` with Threshold 15, per-step
`walkMove` of 16 uu (`GIsEditor`; in-game `CollisionRadius`, or `max(128, CollisionRadius)` if
`bCanJump`), ≤ 100 steps; each step = `MoveActor(Delta.XY)`, on a hit step up `MaxStepHeight`
(25 via `defineFor`; the `TestReach` path uses the scout's own value), retry, step down, wall if
`Normal.Z < 0.7`; then drop `MaxStepHeight + 2`: no floor → ledge → `FindBestJump` (ballistic sim,
JumpZ 320, dt 0.1, ≤ 35 steps, accept if ≥ 8 uu closer, no fall limit); wall → `FindJumpUp`
(one 25-uu step with 48-uu step-up). Steepness pre-check `0.8·(ΔZ−MaxHeight)² > Dist²` fails the
edge. Zone tests: pain zone (unless `ReducedDamageType`) fails; entering water hands over to
`swimReachable`. Arrival: 2-D distance ≤ 15 and |ΔZ| < `CollisionHeight` (slope special cases §4.4).
Fly/swim: 3-D arrival, step `max(200, CollisionRadius)`, no drop test. Collision: cylinder
`(CollisionRadius, CollisionRadius, CollisionHeight)` against the BSP (`bCollideWorld`) and against
actors passing `IsBlockedBy` with pawns/decorations ignored; Movers block iff `bBlockActors`.
Success value = `reachFlags` (`R_WALK` always, `R_JUMP` if any step needed a jump attempt, `R_SWIM`
if it swam, `R_FLY` never for the scout).

(b) **`findBestReachable`.** Start (18, 39); radius binary search step 52 → 26 → 13 → … (stop
< 2, cap 70, success forces height 40); then height from 44, step 26 → 13 → … (stop < 1, cap 70,
floor 40). Returns success; spec gets `appRound(radius)`, `appRound(bestHeight)`, `reachFlags` of
the last success. §3.8.

(c) **`defineFor`.** No flag assembly of its own: flags = return of `pointReachable` (walk → optional
jump/swim handoff, §4). Water is decided by the scout's `Region.Zone->bWaterZone` at each step and by
`pointReachable`'s target-zone check. `Distance = appRound(straight-line 3-D length)`, doubled for
`R_SWIM` — rounded, not truncated (`cvtss2si`).

(d) `supports`: pawn flags ⊇ spec flags, size ≥. `BotOnlyPath`: radius < 24. `MonsterPath`:
radius ≥ 52 ∧ height ≥ 40 ∧ ¬fly. `+`: min/min/or/sum. `==`: four ints. `<=`: this roomier and
this.flags ⊆ other.flags. `Prune` use in §7.

(e) **Ordering.** `CompactSortPathList`: valid indices packed to the front, ascending `Distance`,
`-1` tail. `insertReachSpec` (the builder): descending `Distance`, evict-longest at 16. `SortPaths`
runs only on node deletion. Which order lands on disk after `PATHS BUILD` is decided by
`addReachSpecs` (out of scope) — open question 1.

(f) **R_DOOR / R_PLAYERONLY / R_SPECIAL readers.** None in this cluster. A `.text`-wide scan for
`test/and/or/cmp` of 0x10/0x20/0x40 against a `[reg+0x14]` field (or a register loaded from one
within 4 instructions) found only `findBestReachable`'s `R_SWIM` test; the bits are consumed
generically by `supports` via `calcMoveFlags` (`bCanOpenDoors`/`bCanDoSpecial`/`bIsPlayer`). Stack-
local specs are not covered by that scan (see open question 4).

## 10. Constants

| Value | Where | Meaning |
|-------|-------|---------|
| 18.0 / 39.0 | `0x10193e0c`, `0x10193e14` | initial scout size |
| 70.0 (`0x10212d7c`) | `0x10193e29`, `0x10193f52`, `0x10193ff4` | size cap / initial step base |
| 40.0 (`0x10193f16`, `0x10212d74`) | radius-sweep success height; height floor |
| 4.0 (`0x10202954`) | `0x10193fca` | height sweep starts at `CollisionHeight + 4` |
| 2.0 / 1.0 | `0x10193f3d`, `0x101940d5` | sweep stop thresholds (radius / height) |
| 0.5 | `0x10193ed2` … | step halving |
| 320.0 | `0x10193d18`, `0x10193d54` | scout `JumpZ`, `GroundSpeed` |
| 25.0 | `0x10193d5e` | scout `MaxStepHeight` in `defineFor` |
| 48.0 (`0x10212d78`) | `0x1017b362` | `FindJumpUp` step-up; also `execactorReachable` radius floor |
| 15.0 (`0x102043a4`) | `0x101835a7` | `pointReachable` threshold; slope-goal margin `0x10184dc9` |
| 16.0 (`0x1020fe2c`) | `0x101847a6` | editor `MaxTestMoveSize` |
| 128.0 (`0x10213898`) | `0x101847de` | in-game jumping `MaxTestMoveSize` floor |
| 100 (0x64) | `0x101847f4`, `0x101823b2`, `0x10183d87` | tick budget walk/fly/swim |
| 8.0 / 4.1 | `0x1018490a`, `0x10184962` … | `walkMove` thresholds (near / far) |
| 2.0 | `0x101844d2` | drop test depth `MaxStepHeight + 2` |
| 0.7 (`0x1020eaa0`, `0x10213858`) | `0x10184482`, `0x101845d5`, `0x101828e9` | walkable floor `Normal.Z` |
| 0.95 / 0.7 (`0x10213868`/`0x10213858`) | `0x10184cb3`, `0x10184cc5` | slope band for the arrival special case |
| 0.8 (`0x10213860`) | `0x101848cd` | steepness pre-check |
| 46.0 (`0x10213894`) | `0x10184d62` | default goal radius (no `GoalActor`) |
| 200.0 (`0x1020af18`) | `0x1018238e`, `0x10183d63` | fly/swim `MaxTestMoveSize` floor |
| 50.0 (`0x1020eab4`) | `0x10183f82` | swim→walk exit height allowance |
| 0.1 (`0x10202940`) | `0x1018273e` | `jumpLanding` dt |
| 35 (0x23) / 2 500 000.0 (`0x102138ac`) | `0x10182b16`, `0x10182b47` | `jumpLanding` abort limits |
| 8.0 (`0x10202958`) | `0x1017b28f` | `FindBestJump` "closer by" margin |
| 0.05 (`0x1020e690`), −100.0 (`0x102138c0`) | `0x1017dbc0`, `0x1017db8b` | `SuggestJumpVelocity` dt, fallback gravity |
| 640000.0 (`0x10212d90`) | `0x101833b7`, `0x1017dfef` | in-game 800-uu range cap (not in the editor) |
| 24 / 52 / 40 | `0x10193bc4`, `0x10193c52`, `0x10193c56` | `BotOnlyPath`, `MonsterPath` |
| 1.2 (`0x10212d5c`) | `0x101768fc` | `Prune` distance ratio |
| 6 | `0x1017e0a3`, `0x10176d31` | `SingleLineCheck` trace flags (📖 `TRACE_Level|TRACE_Movers`) |

## 11. Open questions

1. **Final `Paths[]` order on disk — probably descending `Distance`.** `insertReachSpec` orders
   descending; `SetReachSpec`/`SortPaths` order ascending. The `FPathBuilder` code
   (`0x10174000`–`0x10179d00`) has no call to `SortPaths` and no vtable-slot-58 call; `Editor.dll`
   references its `SetReachSpec` import only from an unused `jmp [iat]` thunk (`0x100aba8b`) and
   never `SortPaths`; its `PATHS` handler calls `buildPaths` (`0x10064fb2`). So unless `buildPaths`/
   `createPaths` reorder the lists in code not read here (`addReachSpecs`/`createPaths` are another
   finding's scope), a fresh `PATHS BUILD` leaves each node's `Paths[]` longest-first. Confirm by
   reading a `ReachSpecs`/`Paths` pair from a UED22-built map.
2. **`Prune` call site `0x10179157`.** Nearest export is `definePaths` (`0x10178c10`); the prior
   reading says `definePaths` only spawns markers, so this is probably an unexported function between
   `definePaths` and `insertReachSpec`. Not resolved here.
3. **`EPhysics` values** (1/3/4) are taken from the standard enum, not read from `Engine.u`.
4. **Bit-reader scan coverage.** Only `[reg+0x14]` accesses (and registers loaded from them) were
   scanned; a spec held on the stack (`[ebp-…]`) would be missed. `addReachSpecs` (prior reading:
   writes `reachFlags = 0x20`) was not re-read here.
5. **`FarMoveActor` `CollisionTag` gate** (`0x1016013b`, `0x101601bc`): a non-zero `Actor+0xbc`
   skips writing `Location`. Meaning unknown; assumed 0 for the scout.
6. **Scout collision flags** (`bCollideWorld`/`bCollideActors`) come from `Scout` defaults or
   `getScout`; not read here. `IsBlockedBy` needs `bCollideWorld` for Movers to block.
7. `MoveActor` was read only around the trace/filter (`0x10160b60`–`0x10160d5a`); the step/slide/
   zone-change tail was skipped. `FindSpot`/`CheckEncroachment` bodies were not read.

## 12. Corrections to the prior reading (`30-ulevel-paths-assembly.md` §4)

- `supports` flag test is the reverse of what §4.3 says (pawn ⊇ spec).
- The sweep is not "18/39 → 70 in increments": it is a halving binary search on radius, then height
  (§3.8); "max radius 70" holds, height also caps at 70 and floors at 40.
- `MAXTESTMOVESIZE = 128` applies to in-game jumping pawns; the editor build steps 16 uu.
- `MaxStepHeight` is 25 (`defineFor`), not the 24 set by `buildPaths`, for every spec-defining test;
  the "jump height ≈ 48" is `FindJumpUp`'s temporary step-up, not a jump height.
- `Distance` is rounded (`cvtss2si`), not truncated, and doubled for swim edges.
- `R_DOOR=16` and `R_PLAYERONLY=64` are now ✅ (`calcMoveFlags`).
- `operator+` does not set `Start`/`End`; `operator==` ignores them.
- The prune criterion is `combined ≤ 1.2·direct` AND (`combined <= direct` ∨ `direct.BotOnlyPath()`
  ∨ `combined.MonsterPath()`), compared in float.
