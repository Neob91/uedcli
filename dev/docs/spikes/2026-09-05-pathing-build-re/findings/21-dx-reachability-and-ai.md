# 21 — Deus Ex: reachability tests and the AI path consumer

Binary: `dx-engine` (`dev/games/deusex/System/Engine.dll`, base `0x10300000`). All RVAs below are
`dx-engine` unless marked. Field names come from `layout.py dx Engine.<Class>`; ✅ = read from the
code, 🔬 = inferred (inference stated), 📖 = public UT/Unreal source knowledge, unconfirmed here.
Script-side facts come from the UT-lineage `Pawn.uc`/`NavigationPoint.uc` reference and the DX SDK
`ScriptedPawn.uc` found in `.claude/worktrees/uscript-compiler/_scratch/` (read-only); DX's own
`Engine` script source was not available, so DX native *declarations* are inferred from the exec
wrappers (🔬).

Every function listed was read to its `ret` (`--nostop`); the unwind stubs (`appUnwindf` + the
`w"Class::func"` string) gave the names of the unexported `FSortedPathList` methods.

## Structures

`FReachSpec` — 28 bytes (`operator=` at `0x44cb0` copies 7 dwords; `Init` at `0x44c80`) ✅:

| off  | field           | type   | notes |
|------|-----------------|--------|-------|
| +0   | distance        | INT    | `(int)|End.Location - Start.Location|`, ×2 if `R_SWIM` (`findBestReachable 0xd9b5d..0xd9b69`) |
| +4   | Start           | AActor*| |
| +8   | End             | AActor*| |
| +0xc | CollisionRadius | INT    | largest scout radius that passed, 12..115 |
| +0x10| CollisionHeight | INT    | largest scout height that passed, 10..79 |
| +0x14| reachFlags      | INT    | `R_*` bits below |
| +0x18| bPruned         | BYTE   | written by the builder only; no runtime reader found |

Level access: `ULevel+0x8c` = `ReachSpecs` data, `+0x90` = count (`findPathTo 0xdc27b` returns 0
when 0), stride 28 (`lea ecx,[eax*8]; sub ecx,eax` everywhere). `ULevel+0x2c` = `Actors` data,
`Actors(0)` = `LevelInfo` (asserted), `LevelInfo+0x548` = `NavigationPointList`, `ULevel+0x98` =
`Model`.

`FSortedPathList` (stack object, 0x104 bytes) ✅: `+0` `AActor* Path[32]`, `+0x80` `INT Dist[32]`,
`+0x100` `INT numPoints`. `addPath(N, dist)` (`0xdd170`) = sorted insert by `Dist` ascending, capped
at 32 (a 33rd entry with the largest distance is dropped; the insert point is found with a coarse
half/quarter probe then a linear scan). `removePath(i)` (`0xdd2a0`) shifts down.

`_FNavInfo` (`GetPathnodeList`) ✅: 8 bytes `{AActor* node; FLOAT dist}`.

`FCheckResult` in DX ✅: `+0 Next, +4 Actor, +8 Location, +0x14 Normal, +0x20 <extra dword, always
0>, +0x24 Time, +0x28 Item(-1)` — one dword bigger than UT's; `Time` is at `+0x24` in every
function below.

`APawn::calcMoveFlags` (`0x26d10`) ✅ builds the pawn-side mask from `Pawn+0x318` bits:

    moveFlags = bCanWalk<<0 | bCanFly<<1 | bCanSwim<<2 | bCanJump<<3
              | bCanOpenDoors<<4 | bCanDoSpecial<<5 | bIsPlayer<<6

so `R_WALK=1, R_FLY=2, R_SWIM=4, R_JUMP=8, R_DOOR=16, R_SPECIAL=32, R_PLAYERONLY=64` — the names are
📖 (UT `UnPath.h`), the bit→pawn-bool mapping is ✅.

`ETestMoveResult` as consumed ✅: `0` stopped, `1` moved, `-1` fell (no floor within
`MaxStepHeight+2`, or floor too steep), `5` hit the goal actor.

`EPhysics` values used: `1` Walking, `2` Falling, `3` Swimming, `4` Flying — enum order confirmed in
the reference `Actor.uc` (🔬 for DX: DX's `Engine.u` enum was not decoded, but `Reachable` dispatches
`4 → flyReachable` and `findPathToward` treats `2` as "falling → simulate landing", which is
self-consistent).

ZoneInfo fields used: `+0x388` bit0 `bWaterZone`, bit5 `bPainZone`; `+0x350` `DamageType`;
`+0x31c/0x328/0x338` `ZoneGravity/ZoneVelocity/ZoneFluidFriction`. `Pawn+0x444` = `ReducedDamageType`,
`+0x330` `FootRegion.Zone`, `Actor+0xc8` `Region.Zone`, `+0xd0` `Region.ZoneNumber`.

## Part 1 — the reachability tests (shared by builder and game)

Vtable slots used: `ULevel` slot 34 (`+0x88`) = `MoveActor(Actor, Delta, NewRot, Hit, bTest,
bNoFail, 0, 0)`, slot 35 (`+0x8c`) = `FarMoveActor(Actor, Loc, bTest, bNoCheck)`, slot 48 (`+0xc0`) =
`SingleLineCheck(Hit, Source, End, Start, TraceFlags, Extent)` (🔬 from argument shapes and UT
naming; every use below is consistent). `TRACE_World = 6` 📖 (the only flag value passed).

### `FReachSpec::defineFor(AActor* Start, AActor* End, APawn* Scout)` — `0xd95b0` ✅

    this->Start = Start; this->End = End;
    Scout->bCanFly = 0; Scout->bCanJump = bCanWalk = bCanSwim = 1;   // 0x318 &= ~0x8000, |= 0x7000
    Scout->Physics = PHYS_Walking;                                    // byte +0x30 = 1
    Scout->JumpZ = 120; Scout->GroundSpeed = 120; Scout->MaxStepHeight = 25; Scout->BaseEyeHeight = 0;
    return findBestReachable(Start->Location, End->Location, Start->CollisionHeight,
                             End->CollisionHeight, Scout);

The only caller is `FPathBuilder::addReachSpecs` (`0xb2884`). 📖 UT sets larger scout `JumpZ`/
`GroundSpeed`; DX's 120/120 makes jump specs short.

### `FReachSpec::findBestReachable(FVector& begin, FVector& dest, FLOAT& startHeight, FLOAT& endHeight, APawn* Scout)` — `0xd96e0` ✅

`endHeight` (`[ebp+0x14]`) is never read. `startHeight` = `Start->CollisionHeight` from `defineFor`.

    Scout->SetCollisionSize(12, 10);                       // MINCOMMONRADIUS=12, MINCOMMONHEIGHT=10
    stepsize = 115 - Scout->CollisionRadius;               // MAXCOMMONRADIUS=115 → 103
    bestRadius = 12; bestHeight = 10; success = 0;
    // floor under the start
    SingleLineCheck(Hit, Scout, begin - (0,0,79), begin, TRACE_World, 0);   // MAXCOMMONHEIGHT=79
    floor = Hit.Time == 1 ? begin - (0,0,startHeight) : Hit.Location;
    // straight line of sight begin→dest must be clear, else no spec at all
    SingleLineCheck(Hit, Scout, dest, begin, TRACE_World, 0);
    if (Hit.Time != 1) return 0;
    // grow radius (binary search 12..115, height fixed at 10)
    loop = 1;
    while (loop) {
        if (FarMoveActor(Scout, floor + (0,0,Scout->CollisionHeight), 0, 0)
            && (flags = Scout->pointReachable(dest, 1))) {
            reachFlags = flags; success = 1; bestRadius = Scout->CollisionRadius;
            SetCollisionSize(CollisionRadius + stepsize, 10); stepsize *= 0.5;
            if (CollisionRadius > 115) loop = 0;
        } else {
            SetCollisionSize(CollisionRadius - stepsize, 10); stepsize *= 0.5;
            if (CollisionRadius < 12) loop = 0;              // first failure at r=12 ends it
        }
        if (stepsize < 1) loop = 0;
    }
    if (success) {                                          // grow height 10..79 at radius 12
        SetCollisionSize(12, Scout->CollisionHeight); stepsize = 79 - CollisionHeight; loop = 1;
        while (loop) { same shape with SetCollisionSize(12, CollisionHeight ± stepsize),
                       stop when CollisionHeight > 79 / < 10 / stepsize < 1; bestHeight updated on success }
    }
    if (success) {
        this->CollisionRadius = (int)bestRadius; this->CollisionHeight = (int)bestHeight;
        this->distance = (int)|End->Location - Start->Location|;
        if (reachFlags & R_SWIM) this->distance *= 2;
    }
    return success;

Consequences: a spec exists only if the 12×10 scout passes; the spec's `reachFlags` is whatever the
*last successful* `pointReachable` returned (the largest passing size); `distance` is straight-line,
not path length. `pointReachable(...,1)` with the scout at `floor + (0,0,CollisionHeight)` means the
scout starts standing on the traced floor, so the start actor's own `CollisionHeight` only matters
when there is no floor within 79 uu.

### `APawn::Reachable(FVector Dest, FLOAT thresh, AActor* Goal)` — `0xc1000` ✅

    if (Region.Zone->bWaterZone)                 return swimReachable(Dest, thresh, 0, Goal);
    if (Physics == PHYS_Walking || Physics == PHYS_Swimming) return walkReachable(Dest, thresh, 0, Goal);
    if (Physics == PHYS_Flying)                  return flyReachable(Dest, thresh, 0, Goal);
    return 0;

(`reachFlags` starts at 0; each test ORs its own bit in.) Note `PHYS_Falling` is *not* handled — a
falling pawn is unreachable-tested as 0 (UT dispatches Falling to walk 📖).

### `APawn::walkReachable(FVector Dest, FLOAT thresh, INT reachFlags, AActor* Goal)` — `0xc1b70` ✅

    reachFlags |= R_WALK; success = 0; OrigPos = Location; OrigVel = Velocity;
    MoveSize = 16;                                            // editor value
    if (!GIsEditor) MoveSize = bCanJump ? max(128, CollisionRadius) : CollisionRadius;
    ticks = 100;
    zThresh = Goal ? max(CollisionHeight, Goal->CollisionHeight) : CollisionHeight;
    Hit(1.0); stillmoving = 1;
    while (stillmoving == 1) {
        Dir = Dest - Location; zDiff = Dir.Z; Dir.Z = 0; Dist2 = Dir.X²+Dir.Y²;
        if (zDiff > zThresh && Dist2 < 0.8*(zDiff - zThresh)²) { stillmoving = 0; continue; }  // too steep up
        if (Dist2 <= thresh²) {                               // arrived horizontally
            stillmoving = 0;
            if (|zDiff| < zThresh) success = 1;
            else if (0.7 < Hit.Normal.Z < 0.95) {             // standing on a slope: tolerate
                tanA = sqrt(1/Nz² - 1);
                if (zDiff < 0 && CollisionRadius*tanA + CollisionHeight > -zDiff) success = 1;
                else { goalR = Goal ? Goal->CollisionRadius : 46;
                       if (CollisionRadius < goalR && zDiff < (goalR + 15 - CollisionRadius)*tanA + zThresh) success = 1; }
            }
            continue;
        }
        r = Dist2 < MoveSize² ? walkMove(Dir, Hit, Goal, 8.0, 0)
                              : walkMove(Dir.SafeNormal()*MoveSize, Hit, Goal, 4.1, 0);
        stillmoving = r;
        if (r == 5) { success = 1; stillmoving = 0; }
        else if (r != 1) {
            if (Region.ZoneNumber == 0) { stillmoving = 0; success = 0; }            // fell out of world
            else if (bCanFly) { stillmoving = 0; reachFlags = flyReachable(Dest, thresh, reachFlags, Goal); success = reachFlags; }
            else if (bCanJump) { reachFlags |= R_JUMP;
                                 if (r == -1) stillmoving = FindBestJump(Dest, Dir.SafeNormal()*GroundSpeed, tmp, 1); }
            else if (r == -1 && MoveSize > MaxStepHeight) { MoveSize = MaxStepHeight; stillmoving = 1; } // retry smaller
        }
        if (FootRegion.Zone->bPainZone && Zone->DamageType != ReducedDamageType) { stillmoving = 0; success = 0; }
        if (Region.Zone->bWaterZone) { stillmoving = 0;
            if (bCanSwim && !(Zone->bPainZone && Zone->DamageType != ReducedDamageType))
                { reachFlags = swimReachable(Dest, thresh, reachFlags, Goal); success = reachFlags; } }
        if (--ticks < 0) stillmoving = 0;
    }
    if (!success && Goal && Goal->IsA(AWarpZoneMarker)) success = (Region.Zone == ((AWarpZoneMarker*)Goal)->markedWarpZone);
    FarMoveActor(this, OrigPos, 1, 1); Velocity = OrigVel;
    return success ? reachFlags : 0;

Note `reachFlags |= R_JUMP` is set whenever a jump-capable pawn gets any non-`moved` result, even
`r == 0` (stopped) which then ends the loop with `success = 0`.

### `APawn::flyReachable(...)` — `0xc1190` ✅ and `swimReachable(...)` — `0xc15a0` ✅

Both: `reachFlags |= R_FLY` / `R_SWIM`; `MoveSize = max(200, CollisionRadius)`; `ticks = 100`;
loop: `Dir = Dest - Location; Dist2 = |Dir|²`; if `Dist2 <= thresh²` and `|Dir.Z| <= CollisionHeight`
→ `success = 1`, stop; else `r = Dist2 < MoveSize² ? xMove(Dir, Goal, 8.0, 0) : xMove(Dir.SafeNormal()*MoveSize, Goal, 4.1, 0)`;
`r == 5` → success; `r == 0` → stop.

fly: if moved into water: stop; if `bCanSwim` (and not a hostile pain zone) → `reachFlags =
swimReachable(...)`, `success = reachFlags`.

swim: if left water: stop; if `bCanFly` → `reachFlags = flyReachable(...)`, `success = reachFlags`;
else if `bCanWalk && Dest.Z < Location.Z + MaxStepHeight + 50`: `MoveActor(this, (0,0,max(CollisionHeight+MaxStepHeight, Dest.Z-Location.Z)), Rotation, Hit, 1, 1)`;
if `Hit.Time == 1`: `success = flyReachable(Dest, thresh, reachFlags, Goal); reachFlags = R_WALK`
(`0xc1925..0xc1933` — it calls **flyReachable**, not walkReachable, and then reports plain `R_WALK`;
read twice, the thunk `0x10303c9c` is `flyReachable`). If still in water and the zone is a pain zone
with a foreign damage type: stop, fail. Both end with the WarpZoneMarker check and the position/velocity
restore, returning `success ? reachFlags : 0`.

### `APawn::jumpReachable(FVector Dest, FLOAT thresh, INT reachFlags, AActor* Goal)` — `0xc2380` ✅

    reachFlags |= R_JUMP; OrigPos = Location;
    jumpLanding(Velocity, Landing, 1);
    if (Landing == Location) return 0;          // never left the ground / simulation aborted
    reachFlags = walkReachable(Dest, thresh, reachFlags, Goal);
    FarMoveActor(this, OrigPos, 1, 1);
    return reachFlags;

No caller inside `dx-engine` (`--callers` empty); reachable only from other DLLs/script.

### `APawn::pointReachable(FVector Dest, INT bKnowVisible)` — `0xc0d30` ✅

    if (!GIsEditor && (Dest - Location).SizeSquared2D() > 1000000) return 0;      // 1000 uu
    DestRegion = Model->PointRegion(Level, Dest);
    if (!Region.Zone->bWaterZone && !bCanSwim && DestRegion.Zone->bWaterZone) return 0;
    if (!FootRegion.Zone->bPainZone && DestRegion.Zone->bPainZone && DestZone->DamageType != ReducedDamageType) return 0;
    if (!bKnowVisible && !Model->FastLineCheck(Dest, Location + (0,0,BaseEyeHeight))) return 0;
    Old = Location;
    if (FarMoveActor(this, Dest, 1, 0)) { Dest = Location; FarMoveActor(this, Old, 1, 1); }   // let the engine nudge Dest
    return Reachable(Dest, 15.0, NULL);

### `APawn::actorReachable(AActor* Other, INT bKnowVisible)` — `0xc0630` ✅

    if (!Other) return 0;  Dir = Other->Location - Location; Dist2 = |Dir|²;
    if (!Other->IsA(APawn)) { if (!GIsEditor) { if (Dist2 > 640000) return 0;              // 800 uu
                              if (Other->Region.Zone->bPainZone && DamageType != ReducedDamageType) return 0; } }
    else if (((APawn*)Other)->FootRegion.Zone->bPainZone && DamageType != ReducedDamageType) return 0;
    if (Other->Region.Zone->bWaterZone && !bCanSwim) return 0;
    if (!bKnowVisible) { SingleLineCheck(Hit, this, Other->Location, Location + (0,0,BaseEyeHeight), TRACE_World, 0);
                         if (Hit.Time != 1 && Hit.Actor != Other) return 0; }
    if (Other->IsA(APawn)) {
        thresh = max(1.5*CollisionRadius, MeleeRange) + Other->CollisionRadius + CollisionRadius;
        if (Dist2 <= thresh²) return 1;
        if (Dist2 > 640000) thresh = max(thresh, sqrt(Dist2) - 800);
        Dest = nudged Other->Location (FarMoveActor test as in pointReachable);
        return Reachable(Dest, thresh, Other);
    }
    thresh = 15; if (Other->IsA(AInventory) || Other->IsA(ATrigger)) thresh = Other->CollisionRadius + CollisionRadius - 2;
    Dest = nudged Other->Location;
    return Reachable(Dest, thresh, (Other->bBlockActors || Other->IsA(AWarpZoneMarker)) ? Other : NULL);

### `APawn::AIDirectionReachable(FVector Focus, INT Yaw, INT Pitch, FLOAT minDist, FLOAT maxDist, FLOAT unused, FVector* Result)` — `0xc78a0` ✅ (DX-only)

Script call shape (DX `ScriptedPawn.uc`): `AIDirectionReachable(Location, rot.Yaw, rot.Pitch, minDist, maxDist, outPos)`;
the 6th C++ float (`[ebp+0x24]`) is never read (🔬 an optional script param with no native use).
`assert(!GIsEditor)` (`UnPawnExt.cpp:680`).

    MoveSize = clamp(CollisionRadius, 5, 25); ticks = 100; success = 0;
    band(d²) = d² < minDist² ? -1 : d² > maxDist² ? 1 : 0;   startBand = band(|Location - Focus|²);
    mode = Region.Zone->bWaterZone ? SWIM : Physics in {Walking,Swimming} ? WALK : Physics == Flying ? FLY : return 0;
    Dir = (UnitCoords / FRotator(mode==WALK ? 0 : Pitch, Yaw, 0)).XAxis;
    while (stillmoving) {
        r = WALK ? walkMove(Dir*MoveSize, Hit, NULL, 4.1, 0) : FLY ? flyMove(Dir*MoveSize, NULL, 4.1, 0) : swimMove(Dir*MoveSize, NULL, 4.1, 0);
        if (r != 1) { if (Region.ZoneNumber == 0) stop; else if (WALK && r == -1 && MoveSize > MaxStepHeight) { MoveSize = MaxStepHeight; continue-ish; } }
        pain zone with foreign damage → stop;  (SWIM && !bWaterZone) || (!SWIM && bWaterZone) → stop;
        if (--ticks < 0) stop;
        if (stillmoving) { b = band(|Location - Focus|²);
            if (b == 0) { success = 1; *Result = Location; if (startBand > 0) stop; else startBand = 0; }
            else if (b != startBand) { if (startBand == 0) stop; else { success = 1; *Result = Location; stop; } } }
    }
    restore position/velocity; return success;

Used by `AIPickRandomDestination` (`0xc7fc0`): up to `tries` random biased rotations, each tested with
`AIDirectionReachable(Location, yaw, pitch, minDist/scale, maxDist/scale, 15?, &out)` — the literal
`15.0` is the unused 6th float. This family never touches reachspecs.

### Per-step helpers

`APawn::walkMove(FVector Delta, FCheckResult& Hit, AActor* Goal, FLOAT thresh, INT bAdjust)` — `0xc3290` ✅

    Delta.Z = 0; GravDir = ZoneGravity.Z > 0 ? +1 : -1; Orig = Location;
    Down = (0,0,MaxStepHeight*GravDir); Up = -Down;
    MoveActor(this, Delta, Rotation, Hit, 1, 1);  if (Goal && Hit.Actor == Goal) return 5;
    if (Hit.Time < 1) {                                   // blocked: step up, finish move, step down
        Delta *= (1 - Hit.Time);
        MoveActor(Up); MoveActor(Delta); if (Goal && Hit.Actor == Goal) return 5;
        MoveActor(Down);                 if (Goal && Hit.Actor == Goal) return 5;
        if (Hit.Time < 1 && Hit.Normal.Z < 0.7) { FarMoveActor(Orig,1,1); return 0; }   // landed on a steep face
    }
    Pre = Location;
    MoveActor(this, (0,0,(MaxStepHeight+2)*GravDir), Rotation, Hit, 1, 1);          // find the floor
    if (Hit.Time == 1)      { FarMoveActor(bAdjust ? Orig : Pre, 1, 1); return -1; } // nothing within MaxStepHeight+2
    if (Hit.Normal.Z < 0.7) { FarMoveActor(Orig, 1, 1); return -1; }                  // floor too steep
    if (|Location - Orig|² > thresh²) return 1;
    if (bAdjust) FarMoveActor(Orig, 1, 1);  return 0;

No gravity/velocity integration: "fell" only means no floor within `MaxStepHeight + 2` below.

`APawn::flyMove(Delta, Goal, thresh, bAdjust)` — `0xc3900` ✅ and `swimMove` — `0xc3ca0` ✅: `Up = (0,0,MaxStepHeight)`;
`MoveActor(Delta)`; hit goal → 5; if blocked: `Delta *= (1-Time); MoveActor(Up); MoveActor(Delta)`;
hit goal → 5; return `|Location-Orig|² > thresh² ? 1 : (bAdjust ? restore, 0 : 0)`. `swimMove` first
checks leaving the water: if `!Region.Zone->bWaterZone` after the move, `findWaterLine(Orig, &line)`
(bisection to 1 uu, `0xd3b10`) moves the pawn back to the water line and returns 0.

`APawn::jumpLanding(FVector testVel, FVector& Landing, INT bMoveActor)` — `0xc2530` ✅ — the only
gravity simulation:

    timeTick = 0.1; ticks = 0; Orig = Location; success = 0;
    while (!success) {
        Z = Region.Zone;
        testVel = testVel*(1 - Z->ZoneFluidFriction*0.1) + Z->ZoneGravity*0.1;
        Delta = (testVel + Z->ZoneVelocity)*0.1;
        MoveActor(this, Delta, Rotation, Hit, 1, 1);
        if (Region.Zone->bWaterZone) success = 1;
        else if (Hit.Time < 1) {
            if (Hit.Normal.Z > 0.7) success = 1;                     // landed
            else { Delta2 = (Delta - N*(Delta·N))*(1-Hit.Time);      // slide along the wall
                   if (Delta2·Delta >= 0) { MoveActor(Delta2); if (Hit.Time < 1) { if (Nz > 0.7) success = 1;
                        TwoWallAdjust(Delta.SafeNormal(), Delta2, Hit.Normal, OldNormal, Hit.Time); MoveActor(Delta2);
                        if (Hit.Normal.Z > 0.7) success = 1; } } }
        }
        ticks++;
        if (Region.ZoneNumber == 0 || ticks > 35 || |testVel|² > 2500000) { FarMoveActor(Orig,1,1); success = 1; }
    }
    Landing = Location; if (!bMoveActor) FarMoveActor(Orig, 1, 1);

So a jump is simulated for at most 3.5 s at 0.1 s steps, aborted above ~1581 uu/s. Abort leaves the
pawn at `Orig`, which is why `jumpReachable` treats `Landing == Location` as failure.

`APawn::SuggestJumpVelocity(FVector Dest, FVector& Vel)` — `0xc2c80` ✅: `g = ZoneGravity.Z (< 0 else -100)`;
integrate `Vel.Z += 0.05*g; t += 0.05; z += Vel.Z*0.05` until `z <= Dest.Z-Location.Z && Vel.Z <= 0`;
refine `t -= (z - dz)/Vel.Z` when `|Vel.Z| > 1`; `Vel.XY = (Dest-Location).XY / t` capped at
`GroundSpeed` (or `SafeNormal*GroundSpeed` when `t <= 0`); `Vel.Z` = the incoming `Vel.Z` (JumpZ).

`APawn::FindBestJump(FVector Dest, FVector Vel, FVector& Landing, INT bMoveActor)` — `0xc2f50` ✅:
`Vel.Z = JumpZ; SuggestJumpVelocity(Dest, Vel); jumpLanding(Vel, Landing, 1)`; fail on pain zone or
non-swimmer in water; else `nc = |Dest-Orig| - |Dest-Landing|`; success iff `Orig.Z - Landing.Z < 350
&& nc > 8`; a fall ≥ 350 logs `"FAILING FBJ: nc %f from odS %f and dS %f and dz "`. `FindJumpUp`
(`0xc2b20`) = `walkMove(Dir.SafeNormal()*MaxStepHeight, Hit, NULL, 4.1, 1)` with `MaxStepHeight`
temporarily 48 (returns 1 for 5).

### The rest of `FReachSpec`

- `supports(INT r, INT h, INT flags)` (`0x44c30`) ✅: `CollisionRadius >= r && CollisionHeight >= h && (reachFlags & flags) == reachFlags`.
- `MonsterPath()` (`0xd9440`) ✅: `CollisionRadius >= 22 && CollisionHeight >= 51 && !(reachFlags & R_FLY)`.
- `BotOnlyPath()` (`0xd9470`) ✅: `CollisionRadius < 12`.
- `operator+` (`0xd9490`) ✅: `{dist = a.dist + b.dist, Start = a.Start, End = a.End, r = min, h = min, flags = a|b, bPruned = a.bPruned}` (copies 7 dwords of a temp built from `a`).
- `operator<=` (`0xd9510`) ✅: `r >= b.r && h >= b.h && (flags | b.flags) == b.flags`.
- `operator==` (`0xd9560`) ✅: `dist, r, h, flags` equal (Start/End/bPruned ignored).
- `Init` ✅: zero all 7 fields incl. `bPruned`.
All four helpers are called only from `FPathBuilder::Prune` (`0xb1a92..0xb1adb`); the game never
calls them.

## Part 2 — the consumer

### Scratch reset: `clearPath(N)` `0xd9f90` / `clearPaths()` `0xda050` ✅

Per node: `visitedWeight = 10000000; nextOrdered = prevOrdered = NULL; bEndPoint = 0;
cost = bSpecialCost ? SpecialCost(pawn) : ExtraCost` (`SpecialCost` via `FindFunctionChecked(ENGINE_SpecialCost @0x183604)`).
`clearPaths` walks `Level.NavigationPointList` → `nextNavigationPoint`. `previousPath`, `startPath`,
`bestPathWeight` are **not** reset; they are only read after being written in the same search.

### The sorted lists (`FSortedPathList`, unexported)

`FindVisiblePaths(APawn* P, FVector goalLoc, FSortedPathList* EndPts, INT bClearPaths, INT* bAnchor, INT* bEndFound)` — `0xda210` ✅
(`this` = StartPts):

    if (P->MoveTarget IsA NavigationPoint && |MT.Z - P.Z| < MT.CollisionHeight + P.CollisionHeight
        && horiz² < CollisionRadius² * (P->bIsPlayer && MT IsA InventorySpot ? 2 : 1))
        { *bAnchor = 1; StartPts = {MT, 0}; }
    for (N = NavigationPointList; N; N = N->nextNavigationPoint) {
        if (bClearPaths) clearPath-inline(N);
        if (!*bAnchor  && (int)|P.Location - N.Location|² < 640000) StartPts.addPath(N, d²);   // 800 uu
        if (!*bEndFound && (int)|goalLoc - N.Location|²   < 640000) EndPts.addPath(N, d²);
    }

`Dist[]` holds squared distances here; callers `sqrt` them when they promote an entry.

`findEndPoint(APawn* P, INT* bAnchor)` — `0xda610` ✅ (on StartPts): pop entries until one is
`FastLineCheck(N.Location, P.Location+(0,0,BaseEyeHeight)) && P->pointReachable(N.Location, 1)`;
then `Dist[0] = sqrt(Dist[0])`; if `Dist[0] < max((int)CollisionRadius, 48) && |N.Z - P.Z| < CollisionHeight`
→ `*bAnchor = 1` (the pawn is *on* this node); else `N->bEndPoint = 1; N->bestPathWeight = Dist[0]`.
Returns 0 when the list empties.

`checkAnchorPath(APawn* P, FVector Dest)` — `0xda880` ✅: if `|Dest - Path[0].Location|² < 640000 &&
FastLineCheck(Dest, Path[0].Location) && FarMoveActor(P, Path[0].Location, 1, 0) && P->pointReachable(Dest, 0)`
→ 1; otherwise `numPoints = 1` and 0.

`expandAnchor(APawn* P)` — `0xdaaa0` ✅: `anchor = Path[0]; anchor->cost = 1000000;` for every spec
in `anchor->Paths[]` then `anchor->PrunedPaths[]` that `supports(radius, height, calcMoveFlags())`:
`SingleLineCheck(Hit, P, spec.End.Location, spec.Start.Location, TRACE_World)`; if `Hit.Actor` is a
Mover: skip unless `bCanOpenDoors && (bIsPlayer || !Mover->bPlayerOnly)`; then
`spec.End->bEndPoint = 1; spec.End->bestPathWeight = spec.distance`.

`findAltEndPoint(APawn* P, ANavigationPoint*& best)` — `0xdb0e0` ✅: `base = Path[0].visitedWeight + Dist[0]`;
for `i ≥ 1`: `w = Path[i].visitedWeight + (int)sqrt(Dist[i])`; candidate if `w < base && |N.Z - P.Z| < 120 &&
((goal - P)·(N - P) < 0 || w < max((int)(0.85*base), base - 150))`; first candidate that is visible
from the eye and `pointReachable(...,1)` replaces `best`.

### `APawn::breadthPathFrom(AActor* start, AActor*& bestPath, INT bSinglePath, INT moveFlags)` — `0xdcd60` ✅

Dijkstra over the **upstream** edges, from the goal side toward the pawn:

    radius = (int)CollisionRadius; height = (int)CollisionHeight;
    cur = start; LastAdd = start; numNodes = 1; moveCount = 0; p = 0;
    while (cur) {
        if (cur->bEndPoint) { start->previousPath = NULL; bestPath = cur; return 1; }
        if (!cur->bPlayerOnly || bIsPlayer || cur == start)
          for (i = 0; i < 16 && cur->upstreamPaths[i] != -1; i++) {
            spec = &ReachSpecs[cur->upstreamPaths[i]];
            if (!spec->supports(radius, height, moveFlags)) continue;
            next = spec->Start;
            newW = cur->visitedWeight + spec->distance + next->cost + (next->bEndPoint ? next->bestPathWeight : 0);
            if (next->visitedWeight <= newW) continue;
            unlink next from the ordered list if present (LastAdd/numNodes bookkeeping);
            next->previousPath = cur; next->visitedWeight = newW;
            ins = (LastAdd->visitedWeight < newW) ? LastAdd : cur;
            walk ins = ins->nextOrdered while ins->next->visitedWeight < newW, at most 500 steps
                (else log "Breadth path list overflow from %s", return 0);
            link next after ins (nextOrdered/prevOrdered);
        }
        numNodes++; while (moveCount < numNodes/2 && LastAdd->nextOrdered) { moveCount++; LastAdd = LastAdd->nextOrdered; }
        cur = cur->nextOrdered; p++;
        if (bSinglePath && p > 4) return 0;
        if (p > 1000) { log "1000 navigation nodes searched from %s!"; return 0; }
    }
    return 0;

`bestPath` is the first popped node flagged `bEndPoint` — one of the pawn-side anchors from
`findEndPoint`/`expandAnchor` — i.e. the *next node the pawn should go to*. Its `previousPath`
chain runs toward the goal (each node's `previousPath` is the node it was expanded from).

### `APawn::findPathTo(FVector Dest, INT bSinglePath, AActor*& bestPath, INT bClearPaths)` — `0xdc1d0` ✅

    bestPath = NULL; if (!NavigationPointList || ReachSpecs.Num() == 0) return 0;
    Orig = Location; bAnchor = 0; bEndFound = 0;
    StartPts.FindVisiblePaths(this, Dest, &EndPts, bClearPaths, &bAnchor, &bEndFound);
    if (!StartPts.num || !EndPts.num) return 0;
    if (!bAnchor && !StartPts.findEndPoint(this, &bAnchor)) { restore; return 0; }
    if (bAnchor) { if (StartPts.checkAnchorPath(this, Dest)) { bestPath = StartPts.Path[0]; restore; return 1; }
                   StartPts.expandAnchor(this); }
    if (!bEndFound)
        for (i in EndPts) if (FastLineCheck(EndPts[i].Location, Dest) && FarMoveActor(this, EndPts[i].Location, 1, 0)
                              && pointReachable(Dest, 1)) { bEndFound = 1; EndPts.Path[0] = EndPts[i]; EndPts.Dist[0] = (int)sqrt(EndPts.Dist[i]); break; }
    if (!bEndFound) { restore; return 0; }
    EndPts.Path[0]->visitedWeight = EndPts.Dist[0];
    if (!breadthPathFrom(EndPts.Path[0], bestPath, bSinglePath, calcMoveFlags())) { restore; return 0; }
    restore;
    if (!bAnchor && !bSinglePath) StartPts.findAltEndPoint(this, bestPath);
    return 1;

### `APawn::findPathToward(AActor* goal, INT bSinglePath, AActor*& bestPath, INT bClearPaths)` — `0xdb3f0` ✅

Same skeleton with these differences:
- `if (Physics != PHYS_Flying && goal IsA APawn && goal->Physics == PHYS_Falling)`: `((APawn*)goal)->jumpLanding(goal->Velocity, Landing, 0); return findPathTo(Landing, ...)`.
- If `goal IsA NavigationPoint`: `EndPts = {goal, 0}`, `bEndFound = 1`.
- Anchor short-cut: `if (bAnchor && ((goal IsA NavigationPoint && CanMoveTo(StartPts.Path[0], goal)) || StartPts.checkAnchorPath(this, goal->Location)))` → `bestPath = goal IsA NavigationPoint ? goal : StartPts.Path[0]`; return 1.
- End-point promotion uses `actorReachable(goal, 1)` after `FarMoveActor` to the candidate; if none and `bHunting` → use `EndPts[0]` anyway (`0xdb840`).
- If still no end point (not hunting): the reverse fallback at `0xdb901`: `FindVisiblePaths` again, `EndPts.expandAnchor(this)`, `findEndPoint(EndPts...)` if needed, seed `StartPts.Path[0]->visitedWeight = StartPts.Dist[0]`, `breadthPathFrom(StartPts.Path[0], node, ...)`; reject unless `|goal - node| <= |goal - pawn|`; `root` = end of `node`'s `previousPath` chain; `ReverseRouteFor(node)`; `bestPath = root`, then `root->previousPath` if it is within 120 uu vertically (or the pawn is anchored on `root`) and visible + `pointReachable`. Return 1.

### `APawn::findPathTowardBestInventory(AActor*& best, INT, FLOAT MinWeight, INT bPredictRespawns)` — `0xdbe40` ✅ (returns FLOAT)

`FindVisiblePaths(this, (0,0,0), &dummy, bClearPaths, &bAnchor, &one)` (`bEndFound` preset to 1 so no
goal list); `findEndPoint`; if the pawn is not anchored: `best = StartPts.Path[0]`, return `5e-5`;
else `expandAnchor`, `Path[0]->visitedWeight = max(Dist[0], 10)`,
`w = breadthPathToInventory(Path[0], best, calcMoveFlags(), MinWeight, bPredictRespawns)`; return `w > MinWeight ? w : 0`.

`breadthPathToInventory(AActor* start, AActor*& best, INT moveFlags, FLOAT bestWeight, INT bPredictRespawns)` — `0xdd310` ✅:
forward search over `Paths[]` (`spec.End`), `newW = cur->visitedWeight + spec->distance + next->cost`,
`next->startPath = cur->startPath` (anchors set `startPath = self`); at each `AInventorySpot` with
`markedItem` (`+0x44c`): skip unless the item `IsProbing(0x139)` (🔬 `BotDesireability` state probe)
or (`bPredictRespawns && item->LatentFloat < 5`); if `item->MaxDesireability / cur->visitedWeight > bestWeight`
call the item's `ENGINE_BotDesireability` (`@0x183698`) event with the pawn; `w = result / visitedWeight`;
if `w > bestWeight`: `bestWeight = w; best = cur->startPath`. Stops after 250 nodes if something was
found (else continues 50 more), same 500-step insert cap; finally `ReverseRouteFor(bestNode)`.

### Other consumers

`APawn::TraverseFrom(AActor* N, INT moveFlags)` — `0xdcba0` ✅: `N->bEndPoint = 1`; for each
`N->Paths[i]` spec whose `End` is a NavigationPoint, `!End->bEndPoint`, `(!End->bPlayerOnly || bIsPlayer)`
and `supports(...)`: `count += TraverseFrom(End)`. Returns nodes marked (1 + children). Only caller:
`findRandomDest` (`0xdc700`): collect ≤4 nav points within 500 uu (`250000`) visible from the eye;
for each not yet `bEndPoint` and `actorReachable(N, 1)`: `TraverseFrom`; then pick uniformly
(`appFrand`) among all `bEndPoint` nodes in `NavigationPointList`.

`APawn::CanMoveTo(ANavigationPoint* From, AActor* To)` — `0xdad20` ✅: over `From->Paths[]` then
`From->PrunedPaths[]`: spec with `End == To` and `supports(radius, height, calcMoveFlags())`;
`SingleLineCheck(Hit, this, To.Location, From.Location, TRACE_World)`; a Mover hit needs
`bCanOpenDoors && (bIsPlayer || !Mover->bPlayerOnly)` (`Mover+0x4ec` bit3); else return 1. 0 if no spec.

`APawn::execactorReachable` (`0xbc1a0`, DX-extended ✅): `target = Other`; if `Other IsA Inventory && Other->myMarker`
→ `target = myMarker`. If `target IsA NavigationPoint && ReachSpecs.Num() && CollisionRadius <= 115`:
`r = max(CollisionRadius, 48)`; the pawn is "standing at" any nav point `N` (`MoveTarget` first, then
the whole list) with `|N.Z - Z| < CollisionHeight && horiz² < r²`; if `N == target || CanMoveTo(N, target)`
→ return 1; if some such `N` exists and `Physics != PHYS_Flying` → return 0 **without any physics test**;
otherwise `actorReachable(Other, 0)`. So for a pawn on a node, `actorReachable(node)` is answered
purely from the reachspec graph. `execpointReachable` (`0xbc710`) is plain `pointReachable(p, 0)`.

`execFindPathTo` / `execFindPathToward` (`0xbc800`/`0xbc9c0`) ✅: `(target, optional bool bSinglePath=0,
optional bool bClearPaths=1)`; after the search: `bShootSpecial = 0; SpecialPause = 0;` if the result
`IsProbing(0x15a)` (🔬 `SpecialHandling`) → `HandleSpecial(&result)`; if `result == SpecialGoal` →
`SpecialGoal = NULL`. Timing goes to `ULevel+0x1128`. `execFindRandomDest(bClearPaths=1)`,
`execClearPaths`, `execFindBestInventoryPath(out MinWeight, bPredictRespawns)` are thin wrappers.

`APawn::GetPathnodeList(_FNavInfo* list, INT max, AActor* start, INT bIncludePruned, INT bSort)` — `0xc6490` ✅:
`startNode = start IsA NavigationPoint ? start : (MoveTarget IsA NavigationPoint && IsOverlapping(MoveTarget)) ? MoveTarget : first N in NavigationPointList with IsOverlapping(N)`.
With a start node: entries `{spec.End, spec.distance}` for each `Paths[]` (and `PrunedPaths[]` if
`bIncludePruned`) spec whose `End` is a NavigationPoint and `supports(...)`. Without: every nav point
within 1000 uu of `start->Location` (or `Location`), keeping the `max` nearest (the replacement rule
at `0xc6871` replaces the entry with the *smallest* distance above the new one — 🔬 probably a bug,
harmless), then filtered by `actorReachable(N, 0)`. `bSort` → `appQsort` by distance.

`execReachablePathnodes` (`0xc8bb0`) ✅ iterator: args `(class BaseClass, out actor N, out float Dist, actor Start, bool bIncludePruned)`
(🔬 declaration order from the arg reads; `ScriptedPawn.uc` calls it as `(Class'NavigationPoint', navPoint, None, dist)` —
that only fits if DX's declaration puts `Start` before `Dist`; the native writes `Dist` through the
*third* captured address and passes the fourth value as `Start`. Unresolved without DX `Pawn.uc`);
`GetPathnodeList(list, 32, Start, bIncludePruned, 1)`; `BaseClass` is defaulted but never used.

`execComputePathnodeDistances(actor start)` (`0xc8910`) ✅: `clearPaths(); n = GetPathnodeList(list, 32, start, 0, 0)`;
for each: `visitedWeight = min(visitedWeight, (int)dist)` then a recursive relax (`0xc8a40`) over
`Paths[]`: `End->visitedWeight = min(End->visitedWeight, node->visitedWeight + spec->distance)` for
specs that `supports(...)` — a plain forward flood (no `cost`), leaving distances in `visitedWeight`.

`ANavigationPoint::execdescribeSpec(int iSpec, out actor Start, out actor End, out int ReachFlags, out int Distance)` — `0xbaad0` ✅ (copies `ReachSpecs[iSpec]`).

`APawn::SetRouteCache` (`0xdd7e0`) ✅ is a stub: logs `"HEY! who called SetRouteCache! tell Doug now"`.
Neither `Pawn.RouteCache` (`+0x514`) nor `NavigationPoint.RouteCache` (`+0x424`) is referenced by any
code in `0xb9000..0xdf000`. `ReverseRouteFor(N)` (`0xdd810`) reverses `N`'s `previousPath` chain in
place.

`AActor::physPathing(FLOAT dt)` (`0xdd8a0`) ✅ is **not** navigation: it is `PHYS_Interpolating`
(`PhysRate`, `PhysAlpha`, `bInterpolating`, `Target IsA InterpolationPoint`, `Next`/`RateModifier`,
`eventInterpolateEnd`). Skimmed only (calls/constants), not read to the instruction.

`ALevelInfo::RemoveNavigationPoint`: no such export in `dx-engine` (`--exports "Remove"` lists only
`FPathBuilder::removePaths`, `FCollisionHash::RemoveActor`, `execRemovePawn`, `RemoveColinears`,
`RemoveAdditionalView`).

### How `NavigationPointList` is built ✅

A linear sweep of `.text` for `[reg+0x548]` (`LevelInfo.NavigationPointList`) and `[reg+0x42c]`
(`nextNavigationPoint`) found **writes only in the path builder**: `0xb102c`, `0xb1326`, `0xb160d`
(`+0x548`, inside `removePaths`/`undefinePaths`/`definePaths`, `0xb0d70..0xb1990`) and `0xb110d`,
`0xb159d` (`+0x42c`), plus the `LevelInfo`/`NavigationPoint` copy constructors (`0x37d2a`, `0x38760`,
`0x3bdfb`…). `ULevel::SpawnActor` (`0x94f60`), `AActor::InitExecution`, `SetActorZone` and the
`BeginPlay` events write neither. The game therefore consumes the list and chain **as saved in the
map by `definePaths`**; a builder must serialize `LevelInfo.NavigationPointList` and every
`nextNavigationPoint` (both are `const` script vars, so nothing in script rebuilds them either — the DX
`ScriptedPawn.uc` only reads them, e.g. lines 10132/13007).

## Answers

**(a) Traversal constants in this engine** — see the table below. Versus public UT (📖, from memory,
unconfirmed here): DX scout size limits 12–115 × 10–79 and floor probe 79; DX scout `JumpZ =
GroundSpeed = 120`, `MaxStepHeight = 25`; `walkReachable` step `max(128, r)` when jump-capable;
`fly/swimReachable` step `max(200, r)`; 100 ticks; `pointReachable` 1000 uu cap, `actorReachable` 800
uu cap (game only, `!GIsEditor`).

**(b) Fields the game reads at runtime** (all ✅ from the functions above plus the displacement sweep):

| data | read by | must be built? |
|------|---------|----------------|
| `ReachSpec.Start` | `breadthPathFrom` (via `upstreamPaths`), `expandAnchor` line check | yes |
| `ReachSpec.End` | `GetPathnodeList`, `CanMoveTo`, `expandAnchor`, `TraverseFrom`, `breadthPathToInventory`, `ComputePathnodeDistances`, `describeSpec` | yes |
| `ReachSpec.distance` | every cost sum, `GetPathnodeList`, `expandAnchor` (`bestPathWeight`) | yes |
| `ReachSpec.CollisionRadius/Height`, `reachFlags` | `supports` in every consumer | yes |
| `ReachSpec.bPruned` | builder only | scratch |
| `NavigationPoint.Paths[16]` | `GetPathnodeList`, `CanMoveTo`, `expandAnchor`, `TraverseFrom`, `breadthPathToInventory`, `ComputePathnodeDistances` | yes (`-1` terminated, in order) |
| `upstreamPaths[16]` | `breadthPathFrom` only — the main route search | yes |
| `PrunedPaths[16]` | `CanMoveTo`, `expandAnchor`, `GetPathnodeList(bIncludePruned)` | yes (used as extra edges from the anchor / adjacency test) |
| `VisNoReachPaths[16]` | nobody at runtime (builder writes `0xb1147`, `0xb20f3`) | scratch |
| `nextNavigationPoint`, `LevelInfo.NavigationPointList` | `clearPaths`, `FindVisiblePaths`, `GetPathnodeList`, `findRandomDest`, script | yes |
| `ExtraCost`, `bSpecialCost` (+`SpecialCost` event), `bPlayerOnly` | `clearPath(s)`/`FindVisiblePaths`; `breadthPathFrom`, `TraverseFrom` | designer input, preserved |
| `bEndPoint`, `visitedWeight`, `cost`, `bestPathWeight`, `nextOrdered`, `prevOrdered`, `previousPath`, `startPath` | search scratch, rewritten before use | no (serialized but overwritten) |
| `bEndPointOnly`, `bNeverUseStrafing`, `taken`, `ownerTeam`, both `RouteCache`s | no native reader in the AI region | no |
| `bOneWayPath` | builder only (`addReachSpecs 0xb2743`) | builder input |

**(c) reachFlags bits as consumed**: only through `supports()` — `(spec.reachFlags & pawnFlags) ==
spec.reachFlags`, pawn flags from `calcMoveFlags`: 1 walk, 2 fly, 4 swim, 8 jump, 16 `bCanOpenDoors`,
32 `bCanDoSpecial`, 64 `bIsPlayer`. Bits 16/32/64 are never *produced* by the DX reachability tests
(`walk/fly/swim/jumpReachable` only OR 1/2/4/8), so a spec carrying them would be usable only by
door-opening/special/player pawns; whether the DX builder ever sets them is the builder doc's question.
`R_SWIM` additionally doubles `distance` at build time; `R_FLY` excludes a spec from `MonsterPath`;
`MonsterPath`/`BotOnlyPath` are pruning-only.

**(d) The algorithm**: Dijkstra (uniform-cost search with a sorted intrusive open list, no heap),
run **backwards** from a node near the goal along `upstreamPaths` (`spec.Start`) until it pops a node
flagged `bEndPoint` — the pawn's anchor node or the anchor's out-neighbours. Cost:
`visitedWeight(next) = visitedWeight(cur) + spec.distance + next.cost [+ next.bestPathWeight if next.bEndPoint]`,
`cost = ExtraCost` or `SpecialCost(pawn)`, `bestPathWeight` = straight-line distance pawn→anchor
(`findEndPoint`) or `spec.distance` anchor→neighbour (`expandAnchor`); the anchor itself gets
`cost = 1000000` so routes are not pulled through it. Seeds: `visitedWeight = 10000000` everywhere,
goal-side node `= (int)|goal - node|`. Limits: 32 candidates per side within 800 uu, 5 popped nodes
when `bSinglePath`, 1000 popped nodes, 500 insertion steps, 16 edges per array. The result handed to
script is the first node only (`MoveTarget = FindPathToward(dest)`, re-run at each node — DX
`ScriptedPawn.uc` 10024–10032, 10211–10220); `previousPath` is not read by script and `RouteCache` is
dead.

## Constants

| value | where | meaning |
|-------|-------|---------|
| 12 / 10 | `findBestReachable 0xd9709/0xd970e`, `0xd99c3` | min scout radius / height |
| 115 / 79 | `0xd971d` (`0x10431434`), `0xd9770` (`0x1043207c`) | max scout radius / height; 79 also floor probe depth |
| 120, 120, 25, 0 | `defineFor 0xd95e8..0xd9614` | scout `JumpZ`, `GroundSpeed`, `MaxStepHeight`, `BaseEyeHeight` |
| 0x7000 / ~0x8000 | `defineFor 0xd95e2/0xd95ed` | scout `bCanJump|bCanWalk|bCanSwim`, `!bCanFly` |
| 22 / 51 / 12 | `MonsterPath 0xd9440`, `BotOnlyPath 0xd9470` | prune thresholds |
| 16 / 128 | `walkReachable 0xc1be7 / 0xc1c03` | editor step / game step `max(128, r)` (jumpers) |
| 200 | `flyReachable 0xc120c`, `swimReachable 0xc1621` | step `max(200, r)` |
| 100 | `0xc1c3c`, `0xc124b`, `0xc165a`, `0xc7929` | ticks per test |
| 8.0 / 4.1 | all `*Reachable`/`AIDirectionReachable` | `xMove` threshold near / far |
| 15.0 | `pointReachable 0xc0f0b`, `actorReachable 0xc0a26` | arrival threshold |
| 1000000 / 640000 | `pointReachable 0xc0d81`, `actorReachable 0xc06f1`, `FindVisiblePaths 0xda472` | 1000 uu / 800 uu range caps |
| 800 | `actorReachable 0xc0934` | far-pawn threshold slack |
| 1.5, 46, 15, 0.8, 0.7, 0.95, 50, 2.0 | `actorReachable 0xc08a9`; `walkReachable 0xc207a/0xc20c9/0xc1d42/0xc2012/0xc1ff5`; `swimReachable 0xc17ff`; `actorReachable 0xc0a7a` | see pseudocode |
| 0.7 | `walkMove`, `jumpLanding` | max walkable slope `Normal.Z` |
| `MaxStepHeight+2` | `walkMove 0xc358a` | floor probe below |
| 0.1 s, 35, 2500000 | `jumpLanding 0xc2569/0xc28f6/0xc2911` | jump sim step, max ticks, `|v|²` cap |
| 0.05 s, -100 | `SuggestJumpVelocity 0xc2e90/0xc2cc6` | sim step, gravity fallback |
| 350 / 8.0 | `FindBestJump 0xc30ce/0xc30de` | max drop / min gain |
| 48 | `FindJumpUp 0xc2b58`, `findEndPoint 0xda717`, `execactorReachable 0xbc2a4` | temp step height / anchor radius |
| 10000000 / 1000000 | `clearPath 0xd9fa1`, `expandAnchor 0xdaad1` | `visitedWeight` init / anchor `cost` |
| 32, 500, 4, 1000, 250, 200 | `addPath 0xdd1e7`, `breadthPathFrom 0xdcf46/0xdd00f/0xdd014`, `breadthPathToInventory 0xdd648/0xdd684` | list cap, insert cap, single-path pops, max pops, inventory pops |
| 120, 0.85, 150 | `findPathToward 0xdbaa4`, `findAltEndPoint 0xdb18d/0xdb20a/0xdb218` | vertical tolerance, alt-endpoint margins |
| 5, 25 | `AIDirectionReachable 0xc7992/0xc79ab` | step clamp |
| 5.0, 5e-5, 10 | `breadthPathToInventory 0xdd3ed`, `findPathTowardBestInventory 0xdbffd/0xdc03b` | respawn window, token weight, min seed |

## Evidence (key RVAs)

| RVA | fact |
|-----|------|
| `0x44c30` | `supports`: three compares on `+0xc/+0x10/+0x14` |
| `0xd95dc..0xd9614` | scout setup in `defineFor` |
| `0xd9627..0xd964b` | `findBestReachable` call: `(Start.Loc, End.Loc, &Start.CH, &End.CH, Scout)` |
| `0xd97ca`, `0xd9870` | two `SingleLineCheck`s (floor probe, LOS) — `Hit.Time != 1` → `ret 0x14` with 0 at `0xd9886` |
| `0xd98e1..0xd9905` | `FarMoveActor` + `pointReachable(dest, 1)` per size step |
| `0xd9af6..0xd9b69` | spec `r/h/distance` write, `test cl,4` → `distance*2` |
| `0xc1024..0xc10ed` | `Reachable` dispatch on `bWaterZone`, `Physics` 1/3/4 |
| `0xc1e21` | `Region.ZoneNumber == 0` → fail |
| `0xc1e7c..0xc1f0a` | `reachFlags |= 8`, `FindBestJump` on `r == -1` |
| `0xc1925..0xc1933` | swim→`flyReachable`, `reachFlags = 1` |
| `0xc3395..0xc33b9` | `walkMove`: `Hit.Actor == Goal` → 5 |
| `0xc361e..0xc3694` | `walkMove`: no floor → `-1` |
| `0xc2588..0xc25fd` | `jumpLanding` velocity integration |
| `0x26d10` | `calcMoveFlags` bit packing |
| `0xda0f6..0xda145` | `clearPaths` per-node reset, `SpecialCost` event |
| `0xda3e2..0xda4e4` | `FindVisiblePaths` loop, 800 uu, `addPath` |
| `0xda6e7..0xda789` | `findEndPoint`: sqrt, anchor test, `bEndPoint`/`bestPathWeight` |
| `0xdaad1`, `0xdac23..0xdac3a` | `expandAnchor`: anchor `cost`, neighbour marking |
| `0xdce1f..0xdcea7` | `breadthPathFrom` cost formula |
| `0xdcdca..0xdcde2` | `bEndPoint` pop → return |
| `0xdd00f..0xdd044` | single-path (4) and 1000-node limits |
| `0xdb857..0xdb889` | `findPathToward` seeds `visitedWeight = Dist[0]` and searches |
| `0xdb840` | `bHunting` fallback |
| `0xbc275..0xbc3b6`, `0xbc4d1..0xbc4e9` | `execactorReachable` graph short-cut, `Physics != 4` → 0 |
| `0xdd7e0` | `SetRouteCache` stub string |
| `0xb102c/0xb1326/0xb160d`, `0xb110d/0xb159d` | only writers of `NavigationPointList` / `nextNavigationPoint` |
| `0xb1147`, `0xb20f3` | only writers of `VisNoReachPaths`; no reader in `0xb9000..0xdf000` |

## Open questions

- DX `Pawn.uc` declaration order for `ReachablePathnodes`/`AIDirectionReachable` (only the UT-lineage
  reference and the DX SDK game classes were available). The natives were read from the exec arg
  parsing; the `ScriptedPawn.uc` call `ReachablePathnodes(Class'NavigationPoint', navPoint, None, dist)`
  does not match my inferred `(class, out N, out Dist, Start, bIncludePruned)` — either DX declares
  `(class, out N, optional actor Start, out float Dist, ...)` and the native writes `Dist` into the
  third slot by design, or the third exec read really is `Dist`. Decoding DX `Engine.u`'s function
  export would settle it; not attempted.
- Name indices `0x139` / `0x15a` used with `IsProbing` are inferred as `BotDesireability` /
  `SpecialHandling` from the adjacent `FindFunctionChecked(ENGINE_BotDesireability)` and UT usage 📖.
- `swimReachable`'s water-exit branch calling `flyReachable` and reporting `R_WALK` — read twice via
  the thunk table; not cross-checked live.
- `GetPathnodeList`'s far-list replacement rule (keeps the smallest entry above the new distance)
  looks inverted; not verified live.
- `bEndPointOnly` / `bNeverUseStrafing`: no `dx-engine` reader; `DeusEx.dll` exports no path natives
  (`--exports "Path|Nav|Reach|Route"` on `dx-deusex` matches nothing), so any use would be in script
  (the DX SDK `ScriptedPawn.uc` has none).
- Public-UT constants quoted as 📖 were not checked against a UT binary; the `ued-engine` findings own
  that comparison.
