# 60 — the collision layer the scout moves through (`ued-engine`, cross-checked against `dx-engine`)

Binary key `ued-engine` = `uned/UED22/Engine.dll`, base `0x10000000`; every RVA below is `ued` unless
prefixed `dx`. Marks per `00-method.md`: ✅ read from the code · 🔬 inferred (inference stated) ·
📖 public-source hypothesis, unconfirmed here. Field names come from `harness/layout.py ued
Engine.Actor|Pawn|Brush` (`+0x28` `bStatic` bit0 / `bDeleteMe` bit7, `+0x64` `Level`, `+0x68`
`XLevel`, `+0x84` `Base`, `+0x88` `Region`, `+0x98` `StandingCount`, `+0xbc` `CollisionTag`, `+0xd0`
`Location`, `+0xdc` `Rotation`, `+0xe8` `OldLocation`, `+0x138` `Brush`, `+0x140` `PrePivot`,
`+0x160` `bCollideWhenPlacing` 0x8000 / `bMovable` 0x20000, `+0x190` `CollisionRadius`, `+0x194`
`CollisionHeight`, `+0x198` `bCollideActors` 1 / `bCollideWorld` 2 / `bBlockActors` 4 /
`bBlockPlayers` 8, `+0x1a8` `bJustTeleported` 0x100; Pawn `+0x224` `FootRegion`, `+0x230`
`HeadRegion`, `+0x2d0` `ViewRotation`, `+0x2ec` `EyeHeight`, `+0x44c` `PlayerReplicationInfo`; Brush
`+0x220` `MainScale`, `+0x234` `PostScale`).

`FCheckResult` layout (✅ from every fill site): `+0` `Next`, `+4` `Actor`, `+8` `Location`, `+0x14`
`Normal`, `+0x20` `Primitive`, `+0x24` `Time`, `+0x28` `Item`; size `0x2c`. `FBspNode` (0x40 B):
`+0` `Plane`, `+0x20` `iChild[0]` (BACK), `+0x24` `iChild[1]` (FRONT), `+0x2c` `iCollisionBound`,
`+0x34` `iZone[2]`, `+0x36` `NumVertices`, `+0x37` `NodeFlags`, `+0x38` `iLeaf[2]`. `UModel`:
`+0x58` `Nodes` data, `+0x5c` `Nodes.Num`, `+0xcc` `LeafHulls` data, `+0xf0` `RootOutside`,
`+0x100` `NumZones`, `+0x104` `Zones[]` (0x18 B each, `ZoneActor` first).

## 0. Vtables (✅ dumped)

`ULevel` vtable at `0x101fca5c`: 34 `MoveActor` `0x1608e0`, 35 `FarMoveActor` `0x15ff80`, 36
`DropToFloor`, 43 `SetActorZone` `0x161e10`, 44 `FindSpot` `0x1602e0`, 45 `AdjustSpot` `0x15f140`,
46 `CheckEncroachment` `0x15f370`, 47 `SinglePointCheck` `0x162620`, 48 `SingleLineCheck`
`0x162400`, 49 `MultiPointCheck` `0x161c70`, 50 `MultiLineCheck` `0x161500`. The slot numbers the
earlier findings assumed (34/35/44/46/48) are confirmed.

`UModel` vtable `0x101fa254`: slot 21 `UModel::PointCheck` `0x1aeba0`, slot 22 `UModel::LineCheck`
`0x1ae4c0` (these are the `UPrimitive` virtuals `MultiPointCheck`/`MultiLineCheck`/`ActorLineCheck`
call). `AActor` vtable slot 38 (`+0x98`) = `AActor::ToWorld` `0x116290`; `ABrush`/`AMover` override
it with `ABrush::ToWorld` `0x1162f0`. `FCollisionHash` slot 2 `AddActor`, 3 `RemoveActor`, 4
`ActorLineCheck` `0x125080`, 5 `ActorPointCheck` `0x125380` (🔬 from call sites + exports).

## 1. `UModel::LineCheck(Hit, Owner, End, Start, Extent, ExtraNodeFlags)` `0x1ae4c0` ✅

```
if (Nodes.Num() == 0) return RootOutside;                                   // 0x101ae507, 0x101aea19
if (Extent == (0,0,0)) {                                                    // 0x101ae511-44
    GLineCheckSeenEmpty (0x102dbbb4) = 0;                                   // 0x101ae54a
    Coords = Owner ? Owner->ToWorld() : UnitCoords  (Owner==NULL: no transform)
    hit = !FastWalker_0x101ae190(Hit, this, [Coords], End, Start, 0, 0, RootOutside, ExtraNodeFlags);   // 0x101ae616 (the walker already ported in linecheck.rs)
    if (hit) {                                                              // 0x101ae620
        Dir = End - Start;  Hit.Time = ((Hit.Location - Start) | Dir) / |Dir|²;    // 0x101ae63c-6bf
        Hit.Time = Clamp(Hit.Time - 0.5/|Dir|, 0, 1);                       // 0x101ae6ca-6fe: pull back HALF A UNIT
        Hit.Location = Start + Dir*Hit.Time;  Hit.Actor = Owner;            // 0x101ae73f-787
        if (Owner) Hit.Normal = Hit.Normal.TransformVectorBy(Owner->ToWorld());   // 0x101ae791-7c1
        if ((Hit.Normal | Dir) > 0) Hit.Normal = -Hit.Normal;               // 0x101ae7c4-862: face the ray
    }
    return !hit;
}
// box sweep
Hit.Time = 2.0;                                                             // 0x101ae888 (sentinel; walker uses it as T1 upper bound)
FBoxLineCheckInfo Check(Hit, this, Owner, End, Start, Extent, ExtraNodeFlags);   // ctor 0x101ab9e0
Check.BoxLineCheck(iParent=0, iNode=0, IsFront=0, Outside=RootOutside);    // 0x101abc10
if (!Check.DidHit) return 1;                                                // 0x101ae918
Hit.Time = Clamp(Hit.Time - Max(0.1, 0.1/Check.Dist), 0, 1);               // 0x101ae922-952  (Dist = |End-Start|)
Hit.Location = Start + (End-Start)*Hit.Time;                                // 0x101ae957-9f1
return Hit.Time == 1.0;                                                     // 0x101ae9f6-a14 (0 = blocked)
```

Return value: 1 = clear, 0 = hit (both paths). The box path pulls `Time` back by a **fraction**
`max(0.1, 0.1/Dist)` — for a 16-uu walk step (`Dist` = 18 after `MoveActor`'s 2-uu overshoot, §5)
that is 1.8 uu; the zero-extent path pulls back a fixed 0.5 uu. `ExtraNodeFlags` is stored
(`+0x48`) but the box walker never reads it — it tests `NodeFlags & 0x21` only (🔬: no read of `+0x48`
anywhere in `0x101abc10`–`0x101ac881` or `SetupHull`); the point walker (§2) does use it.

### 1.1 `FBoxLineCheckInfo` (ctor `0x101ab9e0`, `ret 0x34`) ✅ — layout

| off      | field                                                                 |
|----------|-----------------------------------------------------------------------|---
| `+0`     | `Hit*` · `+4` `Model*` · `+8` `Owner*`                                |
| `+0xc`   | `FCoords Coords` = `Owner ? Owner->ToWorld() : GMath.UnitCoords`     | `0x101aba1c-46`
| `+0x3c`  | `Extent` · `+0x48` `ExtraNodeFlags`                                  |
| `+0x4c`  | `NumHulls` · `+0x50` `Normal` (best) · `+0x5c` `FBox Box` (Min/Max)  |
| `+0x78`  | `T0` (entry time, init −1) · `+0x7c` `T1` (exit time, init `Hit.Time`) |
| `+0x80`  | `FPlane Hulls[64]` · `+0x480` `INT Flags[64]` · `+0x580` `INT* HullData` |
| `+0x584` | `End` · `+0x590` `Start` · `+0x59c` `End−Start` · `+0x5a8` `Dist=|End−Start|` · `+0x5ac` `DidHit` |

### 1.2 `BoxLineCheck(iParent, iNode, IsFront, Outside)` `0x101abc10` ✅ (read in full)

```
while (iNode != -1) {
    Node = Nodes[iNode];
    Plane = Owner ? Node.Plane.TransformPlaneByOrtho(Coords) : Node.Plane;          // 0x101abc4e-75
    Dist1 = Plane.PlaneDot(Start);  Dist2 = Plane.PlaneDot(End);                     // 0x101abc89, 0x101abc9c
    MaxDist = |Plane.X*Extent.X*1.1| + |Plane.Y*Extent.Y*1.1| + |Plane.Z*Extent.Z*1.1|;   // 0x101abca2-cfd, 1.1 = [0x10214618]
    IsBack  = (Dist1 <= MaxDist) || (Dist2 <= MaxDist);      // [ebp-8]  0x101abd06-1e
    IsFrontS= (Dist1 >= -MaxDist)|| (Dist2 >= -MaxDist);     // [ebp-4]  0x101abd25-3d
    Near = (Dist1 >= Dist2) ? FRONT(1) : BACK(0);            // 0x101abd3f: side the START is nearer to
    if (side flag of Near)                                                            // 0x101abd4f
        BoxLineCheck(iNode, Node.iChild[Near], Near, ChildOutside(Near));             // 0x101abd99 (recursion)
    if (!side flag of Far) return;                                                    // 0x101abdad -> ret
    iParent = iNode; iNode = Node.iChild[1-Near]; IsFront = 1-Near; Outside = ChildOutside(1-Near);   // 0x101abdb6-e06
}
// leaf, reached through iParent's side IsFront
if (Outside) return;                                                                  // 0x101abe23
Node = Nodes[iParent]; if (Node.iCollisionBound == -1) return;                        // 0x101abe33
SetupHull(Node);                                                                      // 0x101af0d0 (§1.4)
T0 = -1.0; T1 = Hit.Time; Normal = 0;                                                 // 0x101abe49-64
for (i < NumHulls) if (!ClipTo(Hulls[i], HullData[i] & ~0x40000000)) return;         // 0x101abe80-ac (§1.3; Item arg unused)
if (Owner == NULL) {                                                                  // 0x101abeb7: level model only
    6 × ClipTo(plane, INDEX_NONE) in this order:                                      // 0x101abec0-bffe
        (0,0,-1, 0.1 - Box.Min.Z)  (0,0,+1, Box.Max.Z + 0.1)
        (-1,0,0, 0.1 - Box.Min.X)  (+1,0,0, Box.Max.X - 0.1)      <- note: Max.X/Max.Y use MINUS 0.1, Max.Z uses PLUS
        (0,-1,0, 0.1 - Box.Min.Y)  (0,+1,0, Box.Max.Y - 0.1)
    each returning 0 -> return
}
for (i < NumHulls) for (j < i) {                                                      // 0x101ac00c-81c: edge bevel planes
    f = Flags[i] | Flags[j];
    for (axis, mask) in ((1,0,0),3), ((0,1,0),0xc), ((0,0,1),0x30):                 // 0x101ac057, 0x101ac2b1, 0x101ac54d
        if ((f & mask) != mask) continue;                                            // planes i,j have opposite-sign normals on this axis
        if (((axis ^ Hulls[i]) | (axis ^ Hulls[j])) <= 0.001) continue;             // 0x101ac0dc, [0x1020293c]
        FIntersectPlanes2(I, D, Hulls[i], Hulls[j]);                                 // 0x101ad7a0: D = (Pi ^ Pj), I = ((Pj^D)*Pi.W + (D^Pi)*Pj.W)/|D|², D normalised; |D|² < 1e-6 -> I=D=0
        N = (axis ^ D).UnsafeNormal(); if ((Hulls[i] | N) < 0) N = -N;             // 0x101ac12d-165  (3-component dot, `??UFPlane@@QBEMABVFVector@@@Z`)
        P = FPlane(I, N);                                                            // 0x101ac19a
        inline ClipTo(P) WITHOUT the 1.1 factor (push-out = |N.x Ex|+|N.y Ey|+|N.z Ez|), Item unchanged;   // 0x101ac1a0-2a8
        if (it returns 0) return;
}
if (T0 > -1.0 && T1 > T0 && T1 > 0.0) {                                               // 0x101ac825-844
    Hit.Time = T0; Hit.Normal = Normal; Hit.Actor = Owner; Hit.Primitive = Model; DidHit = 1;   // 0x101ac846-872  (Hit.Item NOT written, Hit.Location NOT written here)
}
```

`ChildOutside(side)` (inlined at `0x101abd56-8e`, `0x101abdce-e06`): FRONT → `Outside ||
Node.IsCsg()`; BACK → `Outside && !Node.IsCsg()`, with `IsCsg = NumVertices > 0 && !(NodeFlags &
0x21)`. Same rule as `linecheck.rs::combine_state`; child index convention `iChild[1]` = FRONT
(`+0x24`), `iChild[0]` = BACK (`+0x20`) — identical to the zero-extent walker.

Note the shape difference from the zero-extent walker: no crossing split of the segment (the whole
`[Start,End]` is passed down both sides, classified by the push-out band), the recursion is into
the START's side first, and only a leaf reached with `Outside == 0` is tested, against the leaf's
**collision hull** (`iCollisionBound`), not the node planes.

### 1.3 `ClipTo(const FPlane& Hull, INT Item)` `0x101ad540` ✅

```
PushOut = |Hull.X*Extent.X| + |Hull.Y*Extent.Y| + |Hull.Z*Extent.Z|;    // 0x101ad557-8c (no 1.1)
Dist1 = Hull.PlaneDot(Start); Dist2 = Hull.PlaneDot(End);               // 0x101ad591, 0x101ad5a3
Num = Dist1 - PushOut;                                                   // 0x101ad5be
if (Dist1 > Dist2 && Num >= -PushOut) Num = Max(0, Num);                // 0x101ad5c2-dd  (i.e. if Dist1 >= 0 when moving inward)
Den = Dist1 - Dist2;  T = Num / Den;                                     // 0x101ad5eb-f2
if (Den < -1e-5)      { if (T1 > T) T1 = T; }                           // 0x101ad5ef-602: exiting this plane
else if (Den > 1e-5)  { if (T > T0) { T0 = T; Normal = Hull.xyz; } }    // 0x101ad61d-642: entering
else if (Dist1 > PushOut && Dist2 > PushOut) return 0;                  // 0x101ad644-655: parallel & outside
return T1 > T0;                                                          // 0x101ad607-61a
```
`Item` is never read (🔬: `[ebp+0xc]` unused) — the box `LineCheck` leaves `Hit.Item` untouched.
Constants: `1e-5` = `[0x10217610]`, `-1e-5` = `[0x10217618]`.

### 1.4 `SetupHull(FBspNode& Node)` `0x101af0d0` ✅

```
HullData = &Model->LeafHulls[Node.iCollisionBound];  NumHulls = 0;              // 0x101af0dd-f3
for (i = 0; HullData[i] != -1 && i < 64; i++) {                                 // 0x101af0fb, 0x101af107
    Hulls[i] = Nodes[HullData[i] & 0x3fffffff].Plane;   (`shl 6` drops bit 30)   // 0x101af116-27
    if (Owner) Hulls[i] = Hulls[i].TransformPlaneByOrtho(Coords);               // 0x101af12a-43
    if (HullData[i] & 0x40000000) Hulls[i] = Hulls[i].Flip();                   // 0x101af14f-67
    Flags[i] = (X<0?1:X>0?2:0) | (Y<0?4:Y>0?8:0) | (Z<0?0x10:Z>0?0x20:0);       // 0x101af16d-1cd
    NumHulls++;
}
Box.Min = (float)HullData[N+1..N+3]; Box.Max = HullData[N+4..N+6];              // 0x101af1f1-226 (the 6 floats after the -1)
```

## 2. `UModel::PointCheck(Hit, Owner, Location, Extent, ExtraNodeFlags)` `0x1aeba0` ✅

```
Hit.Normal = 0; Hit.Location = Location; Hit.Primitive = this; Hit.Actor = Owner; Hit.Time = 0;   // 0x101aec06-3f
Result = RootOutside; if (Nodes.Num() == 0) return Result;                                        // 0x101aec46-56
if (Extent == 0) {                                                                                // 0x101aec7a-aa
    Coords = Owner ? Owner->ToWorld() : UnitCoords;
    iNode = 0; Outside = RootOutside;
    do { Node; front = Node.Plane.TransformPlaneByOrtho(Coords).PlaneDot(Location) > 0;         // 0x101aed16-3a (NOTE: > 0, PointRegion uses >= 0)
         Outside = ChildOutside_0x101ad4f0(Node, front, Outside, ExtraNodeFlags=0);             // 0x101aed48 (ExtraNodeFlags forced 0 here)
         last = iNode; iNode = Node.iChild[front]; } while (iNode != -1);
    Hit.Item = last*2 + front;                                                                    // 0x101aed5c-65
    return Outside;                                                                               // 1 = free
}
FBoxPointCheckInfo Check(Hit, this, Owner, Location, Extent, ExtraNodeFlags);   // ctor 0x101abb20: same layout as §1.1, +0x584 Location, +0x590 BestDist = 100000.0
Result = Check.BoxPointCheck(0, 0, RootOutside);                                 // 0x101ac890
check(Hit.Actor == Owner);  return Result;                                       // 1 = free, 0 = box in solid
```

`BoxPointCheck(iParent, iNode, Outside)` `0x101ac890` ✅ (read `0x101ac890`–`0x101acec1` and
`0x101ad3f9`–`0x101ad4e6`; the Y/Z edge sections `0x101acebb`–`0x101ad3f9` are the X section
repeated with axis (0,1,0)/(0,0,1) and masks `0xc`/`0x30` — skimmed, same code as §1.2):
```
Result = 1;
while (iNode != -1) {
    Plane (transformed if Owner); PushOut = |P.X Ex 1.1| + |P.Y Ey 1.1| + |P.Z Ez 1.1|; Dist = P.PlaneDot(Location);   // 0x101ac8fe-96f
    if (Dist > -PushOut) Result &= BoxPointCheck(iNode, iChild[1], Outside || IsCsg(ExtraNodeFlags));   // 0x101ac981-9c1 (uses NodeFlags & (ExtraNodeFlags|0x21))
    iParent = iNode; iNode = iChild[0]; Outside = Outside && !IsCsg(ExtraNodeFlags);              // 0x101ac9c4-f2
    if (Dist > PushOut) return Result;                                                             // 0x101ac9ef
}
if (Outside) return Result; if (Nodes[iParent].iCollisionBound == -1) return Result;              // 0x101aca18-2e
SetupHull; for each hull: if (!ClipToPoint(Hulls[i], HullData[i] & ~0x40000000)) return Result;   // 0x101aca62
if (!Owner) 6 box planes as §1.2 (same W's), each via ClipToPoint(…, -1);                          // 0x101aca8a-bca
pairwise edge planes as §1.2, inline ClipToPoint with Item = -1;                                   // 0x101acbd0-4ca
return 0;                                                                                          // 0x101ad4d0: box is inside every plane -> in solid
```
`ClipToPoint(Hull, Item)` `0x101ad660` ✅:
```
PushOut = |Hull.X Ex| + |Hull.Y Ey| + |Hull.Z Ez|;  Dist = Hull.PlaneDot(Location);
if (Dist > 0 && Dist < BestDist && PushOut > Dist) {                                  // 0x101ad6c5-e2
    BestDist = Dist;
    Hit.Location = Location + Hull.xyz * (1.02 * (PushOut - Dist));                   // 0x101ad6e8-749, 1.02 = [0x10217614]
    Hit.Normal = Hull.xyz; Hit.Actor = Owner; Hit.Primitive = Model; Hit.Item = Item; Hit.Time = 0;   // 0x101ad74e-7b
}
return PushOut > Dist;                                                                 // 0x101ad784
```
So the push-out reported by `PointCheck` is along the hull plane the box penetrates **least deeply**
(smallest positive `Dist`), scaled 1.02, and `Hit.Time` is always 0; the zero-extent path reports
only in/out (`Hit.Item` = node*2+side).

## 3. `ULevel::FindSpot(Extent, Location&, bCheckActors, bAssumeFit)` `0x1602e0` ✅

```
FCheckResult Hit(1.0);
if (Extent == 0) return SinglePointCheck(Hit, Location, Extent, 0, GetLevelInfo(), bCheckActors) == 1;   // 0x10160348-e2
if (bAssumeFit && SinglePointCheck(Hit, Location, Extent, 0, Level, bCheckActors) == 1) return 1;       // 0x101603e4-455
Adjusted = Location;  Big = Extent.Size() + 2.0;                                                          // 0x10160472-9e
for (i in {-1, +1}) {                                                                                      // 0x101604a1-600
    AdjustSpot(Adjusted, Adjusted + (i*Ex, 0, 0), Ex, Hit);
    AdjustSpot(Adjusted, Adjusted + (0, i*Ey, 0), Ey, Hit);
    AdjustSpot(Adjusted, Adjusted + (0, 0, i*Ez), Ez, Hit);
}
if (SinglePointCheck(Hit, Adjusted, Extent, 0, Level, bCheckActors) == 1) { Location = Adjusted; return 1; }   // 0x10160605-8e
for (x in {-1,1}) for (y in {-1,1}) for (z in {-1,1})                                                      // 0x10160693-75b
    AdjustSpot(Adjusted, Adjusted + (x*Ex, y*Ey, z*Ez), Big, Hit);
if ((Adjusted - Location).SizeSquared() > 1.5 * Extent.SizeSquared()) return 0;                          // 0x10160760-df (double math, 1.5 = [0x1020e460])
if (SinglePointCheck(Hit, Adjusted, Extent, 0, Level, bCheckActors) == 1) { Location = Adjusted; return 1; }   // 0x101607e4-86d
return 0;
```
`AdjustSpot(Adjusted&, TraceDest, TraceLen, Hit&)` `0x15f140` ✅:
```
SingleLineCheck(Hit, NULL, TraceDest, Adjusted, TraceFlags=6 (Movers|Level), Extent=(0,0,0), ExtraNodeFlags=0);   // 0x1015f172
if (Hit.Time < 1.0) Adjusted += Hit.Normal * ((1.05 - Hit.Time) * TraceLen);     // 0x1015f178-d3, 1.05 = [0x1020e458]
```
Fourteen zero-extent traces per failed spot (6 axis + 8 diagonal), at most 3 point checks; no
iteration beyond that. `FarMoveActor` calls it with `bCheckActors = 0, bAssumeFit = 0`, so the nudge
runs on every scout placement (§5).

`SinglePointCheck(Hit, Location, Extent, ExtraNodeFlags, Level, bActors)` `0x162620` ✅: `list =
MultiPointCheck(GMem, …)` (slot 49); no list → return 1; else `Hit` = the entry whose
`Hit.Location` is nearest `Location` (`0x10162711-7b6`), return 0.
`MultiPointCheck` `0x161c70` ✅: `bActors && Hash` → `Hash->ActorPointCheck(Mem, Location, Extent,
0x13, ExtraNodeFlags)` (slot 5); then if `Level`: `Level->XLevel->Model->PointCheck(Hit, NULL,
Location, Extent, **0**)` (slot 21, ExtraNodeFlags NOT forwarded, `0x10161d37`) and on hit prepend a
copy with `Actor = Level`.

## 4. `ULevel::MultiLineCheck(Mem, End, Start, Extent, bCheckActors, Level, ExtraNodeFlags)` `0x161500` ✅

```
FCheckResult Hits[64]; NumHits = 0; Dilation = 1.0; bCloseWall = 0; bHitLevel = 0;
if (Level) {
    if (!Level->XLevel->Model->LineCheck(Hits[0], NULL, End, Start, Extent, ExtraNodeFlags)) {   // 0x1016164c (slot 22, Owner NULL)
        bHitLevel = 1; Hits[0].Actor = Level;                                                    // 0x10161657-61
        Dist = |Hits[0].Location - Start|;                                                       // 0x10161668-b6
        Dilation = Min(1.0, (Dist + 5.0) * Hits[0].Time / (Dist + 1e-4));                        // 0x101616bc-70b: 5.0=[0x10206784], 1e-4=[0x10202934]
        End = Start + (End - Start) * Dilation;                                                  // 0x10161713-b3: actor traces stop 5 uu past the wall hit
        if (Hits[0].Time < 0.01) bCloseWall = (Dist < 30.0);                                     // 0x101617b8-d8
        NumHits = 1;
    }
}
if (bCheckActors && Hash) {                                                                      // 0x1016180c-1d
    Link = Hash->ActorLineCheck(Mem, End, Start, Extent, bCloseWall ? 2 : 0x13, ExtraNodeFlags);   // 0x101618ad (slot 4); 2 = movers only
    for (; Link && NumHits < 64; Link = Link->Next) {
        if (bHitLevel && Link->Actor->IsA(AMover) && Link->Normal == Hits[0].Normal
            && |Link->Location - Hits[0].Location|² < 4.0) {                                     // 0x101618d1-998: mover hit coincident with the wall hit
            Dir = (End - Start).SafeNormal(); Link->Location = Hits[0].Location - 2*Dir;          // 0x1016199e-a92
            Link->Time = |Link->Location - Start| / |End - Start|;                                // 0x10161a97-ae5
        }
        Link->Time *= Dilation;  Hits[NumHits++] = *Link;                                        // 0x10161aea-b0f
    }
}
appQsort(Hits, NumHits, 0x2c, byTimeAscending 0x1015f890);                                       // 0x10161b50
return a Mem-allocated linked copy (NULL when NumHits == 0).                                     // 0x10161b59-bc1
```

`FCollisionHash::ActorLineCheck` `0x125080` ✅ (how a Mover is tested): bump the global visit
stamp `GCollisionTag` (`0x1028bfac`, wraps to 1); box = `FBox(Start,End) ± Extent`; walk the hash
cells; for each link whose `Actor->CollisionTag != GCollisionTag`, whose cell key matches, and whose
`link.flags & TraceFlags` ≠ 0: `Actor->CollisionTag = GCollisionTag`; `Prim = Actor->GetPrimitive()`
(`0x112980`); `if (!Prim->LineCheck(TestHit, Actor, End, Start, Extent, ExtraNodeFlags))` (slot 22)
copy `TestHit` into the result list. `AActor::GetPrimitive()` `0x112980` ✅ = `Brush ? Brush : Mesh ?
Mesh : XLevel->Engine->Cylinder`, so a Mover goes through §1 with `Owner = Mover` and every
node/hull plane `TransformPlaneByOrtho(Owner->ToWorld())`. `ABrush::ToWorld()` `0x1162f0` ✅ is the
chain `GMath.UnitCoords * Location * PostScale * Rotation * MainScale * (-PrePivot)` (`Origin -=
Location`, then `FCoords::operator*(FScale PostScale)`, `*(FRotator Rotation)`, `*(FScale
MainScale)`, then `Origin -= -PrePivot`; `AActor::ToWorld()` `0x116290` is `UnitCoords * Location *
Rotation`). `TestHit` is constructed `FCheckResult(Time = 0.0, Next = NULL)` (`0x1012521c-2c`,
ctor `0x1247d0` stores arg 1 at `+0x24`); harmless, because `UModel::LineCheck` overwrites
`Hit.Time = 2.0` before the box walk (`0x101ae888`) and the zero-extent walk ignores it.

`SingleLineCheck(Hit, Source, End&, Start&, TraceFlags, Extent, ExtraNodeFlags)` `0x162400` ✅:
`MultiLineCheck(GMem, End, Start, Extent, bActors = (TraceFlags & 0x17) != 0, Level = (TraceFlags &
4) ? LevelInfo : NULL, ExtraNodeFlags)`, then takes the first hit that is not owned by `Source` and
whose class passes the flag (`LevelInfo` ↔ 4, `Pawn` ↔ 1, `Mover` ↔ 2, else ↔ 0x10).

## 5. `ULevel::MoveActor(Actor, Delta, NewRotation, Hit&, bTest, bIgnorePawns, bIgnoreBases, bNoFade)` `0x1608e0` ✅ (read in full)

```
if ((bStatic || !bMovable) && !GIsEditor) return 0;                                              // 0x1016093a-54
if (Delta.IsNearlyZero()) {                                                                       // 0x1016095a
    if (NewRotation == Rotation) return 1;                                                        // 0x10160967-88
    if (StandingCount == 0 && !IsMovingBrush()) { Rotation = NewRotation; return 1; }             // 0x101609a5-cc
}
Hit = FCheckResult(1.0);  FMemMark Mark(GMem);                                                    // 0x101609d1-f7
DeltaSize = |Delta|; DeltaDir = Delta/DeltaSize (0 if Delta == 0);                                // 0x10160a36-b15
TestDelta = Delta + 2.0*DeltaDir;                                                                 // 0x10160b1a-4c: trace 2 uu past the target
bBlocked = 0; FirstHit = NULL;
if ((bCollideActors || bCollideWorld) && !IsMovingBrush() && Delta != 0) {                       // 0x10160b60-bb
    FirstHit = MultiLineCheck(GMem, Location + TestDelta, Location,
                              Extent = (CollisionRadius, CollisionRadius, CollisionHeight),
                              bCheckActors = bCollideActors && !IsMovingBrush(),
                              Level = (bCollideWorld && !IsMovingBrush()) ? LevelInfo : NULL, 0);  // 0x10160bc1-c96
    if (bIgnoreBases) unlink hits h with Actor->IsBasedOn(h.Actor);                              // 0x10160c99-cc3
    if (bCollideWorld || bBlockActors || bBlockPlayers)                                          // 0x10160cc6
        for (h : FirstHit) {                                                                     // 0x10160ce0-d57
            if (bIgnorePawns && !h.Actor->bStatic && (h.Actor->IsA(APawn) || IsA(ADecoration))) continue;
            if (h.Actor->IsBasedOn(Actor)) continue;
            bBlocked = 1;
            if (!Actor->IsBlockedBy(h.Actor)) continue;                                          // 0x10160d41
            Hit = h; break;                                                                      // 0x10160d52
        }
}
FinalDelta = Delta;
if (Hit.Time < 1.0 && !bNoFade) {                                                                // 0x10160d6a-88
    moved = (2.0 + DeltaSize) * Hit.Time;                                                        // 0x10160d8e-9e
    if (moved <= 2.0) { FinalDelta = 0; Hit.Time = 0; }                                          // 0x10160da2-c2
    else { FinalDelta = TestDelta*Hit.Time - 2.0*DeltaDir; Hit.Time = (moved - 2.0)/DeltaSize; }  // 0x10160dd4-e7a: stop 2 uu before the contact
}
if (StandingCount && !bTest) move every actor whose Base == Actor by FinalDelta (+ yaw pivot) via MoveActor(.., 0,1,0,0), Pawns get ViewRotation.Yaw += dYaw;   // 0x10160e8b-1108 (riders; skipped under bTest)
if (!bTest && !bNoFade && !Actor->IsA(APawn) && CheckEncroachment(Actor, Location + FinalDelta, NewRotation, 0))   // 0x1016110a-1251
    { undo rider moves; Mark.Pop(); return 0; }                                                  // 0x10161257-399
if (bCollideActors && Hash) Hash->RemoveActor(Actor);                                            // 0x10161117-2d
Location += FinalDelta; Rotation = NewRotation;                                                  // 0x10161130-57
if (bCollideActors && Hash) Hash->AddActor(Actor);                                               // 0x1016115d-73
if (!bTest) {                                                                                     // 0x10161176
    if (Hit.Actor && Hit.Actor != LevelInfo && !Actor->IsBasedOn(Hit.Actor)) { Hit.Actor->eventBump(Actor); Actor->eventBump(Hit.Actor); }   // 0x10161181-c1
    touch: for h in FirstHit with h.Time < Hit.Time, not based, !IsBlockedBy, h.Time <= TouchTime: BeginTouch; CheckTouchList   // 0x101613a1-467
}
SetActorZone(Actor, bTest, 0);                                                                    // 0x10161476 (slot 43) — ALSO under bTest
Mark.Pop(); return Hit.Time > 0.0;                                                                // 0x1016147c-b5
```
Return value: 1 iff the actor moved at all (`Hit.Time > 0` after the pull-back), so a step that
stops within 2 uu of the start returns 0 with `Hit.Time == 0`. Under `bTest` (`walkMove` etc. pass
`bTest=1, bIgnorePawns=1, bIgnoreBases=0, bNoFade=0`): no rider handling, no encroachment, no
Bump/Touch, but the location IS written and `SetActorZone` runs (with `bTest`, so no zone events).

## 6. `ULevel::FarMoveActor(Actor, Dest, bTest, bNoCheck)` `0x15ff80` ✅ (read in full)

```
if ((bStatic || !bMovable) && !GIsEditor) return 0;                                              // 0x1015ffd9-f1
if (bCollideActors && Hash) Hash->RemoveActor(Actor);   // sets CollisionTag = 0 (0x10126181)     // 0x10160032-48
NewLoc = Dest; Result = 1;
if (!bNoCheck) {
    if (bCollideWorld || (bCollideWhenPlacing && NetMode != NM_Client))                          // 0x1016006d-8c
        Result = FindSpot((CR, CR, CH), NewLoc, 0, 0);                                            // 0x101600bd (slot 44): world only, always nudges
    if (Result && !bTest) Result = !CheckEncroachment(Actor, NewLoc, Rotation, 1);               // 0x101600d7-135 (slot 46)
}
if (CollisionTag != 0 && !bTest) return Result;                                                   // 0x1016013b-48  (gate, see below)
if (Result) {
    if (!bTest && NetMode != NM_Client) { if (StandingCount) for A in Actors: if (A->Base == Actor) A->SetBase(NULL, 1);  bJustTeleported = 1; }   // 0x10160166-1b6
    if (CollisionTag == 0) { Location = NewLoc; OldLocation = NewLoc; } else skipReadd = 1;       // 0x101601bc-217
}
if (bCollideActors && Hash && !skipReadd) Hash->AddActor(Actor);                                  // 0x1016021a-34 (sets CollisionTag = GCollisionTag)
if (Result) SetActorZone(Actor, bTest, 0);                                                        // 0x1016023a-48
return Result;
```
The `CollisionTag` gate (`0x1016013b`) is explained ✅: `FCollisionHash::AddActor` writes the global
stamp into `CollisionTag` (`0x10125a69`) and `RemoveActor` zeroes it (`0x10126181`), so
`CollisionTag != 0` means "still in the collision hash". After the `RemoveActor` above the tag is 0
for any `bCollideActors` actor, and 0 for an actor that was never hashed; the gate only fires for an
actor that is in the hash without `bCollideActors` set (inconsistent state) and then refuses the
relocation. For the scout it is inert (🔬: assumes the scout's `bCollideActors` is consistent with
its hash membership, which `SetActorCollision` maintains).

## 7. `PointRegion`, `SetActorZone`, `IsBlockedBy` ✅

`UModel::PointRegion(Zone, Location)` `0x1aee60`:
```
Result = {Zone, iLeaf = -1, ZoneNumber = 0};  if (Nodes.Num() == 0) return Result;
iNode = 0; do { front = Nodes[iNode].Plane.PlaneDot(Location) >= 0; prev = iNode; iNode = Nodes[iNode].iChild[front]; } while (iNode != -1);   // 0x101aeed5-f0c (>= 0 -> FRONT = iChild[1])
Result.iLeaf = Nodes[prev].iLeaf[front];                                                          // 0x101aef0e-1c
Result.ZoneNumber = NumZones ? Nodes[prev].iZone[front] : 0;                                      // 0x101aef1f-35
Result.Zone = Zones[ZoneNumber].ZoneActor ? that : Zone;                                          // 0x101aef38-4d
```
No solidity test: a point in solid lands on a node's solid side, whose `iLeaf`/`iZone` are −1/0, so
it reports `ZoneNumber 0`, `Zone = LevelInfo`, `iLeaf −1` (📖 that the BSP builder stores −1/0 on
solid sides — the reachability code's "ZoneNumber == 0 ⇒ fell out of the world" relies on it).

`ULevel::SetActorZone(Actor, bTest, bForceRefresh)` `0x161e10`:
```
if (bDeleteMe || XLevel != this) return;                                                          // 0x10161e64-6d
if (Actor == LevelInfo) { Region = {LevelInfo,-1,0}; return; }                                    // 0x10161e76-9f
Pawn = Actor->IsA(APawn) ? Actor : NULL;
if (bForceRefresh) { Region = {LevelInfo,-1,0}; if (Pawn) FootRegion = HeadRegion = same; }        // 0x10161ee0-f48
New = Model->PointRegion(Actors.Num() ? LevelInfo : Actor, Location);                            // 0x10161f4e-93
if (New.Zone != Region.Zone && !bTest) { Region.Zone->eventActorLeaving; Actor->eventZoneChange(New.Zone); }   // 0x10161fa1-bb
Region = New;  if (changed && !bTest) New.Zone->eventActorEntered(Actor);                         // 0x10161fc0-e8
if (Pawn) {
    Foot = PointRegion(LevelInfo, Location - (0,0,CollisionHeight)); if (Foot.Zone != FootRegion.Zone && !bTest) eventFootZoneChange; FootRegion = Foot;   // 0x10162008-9e
    Head = PointRegion(LevelInfo, Location + (0,0,EyeHeight));      if (Head.Zone != HeadRegion.Zone && !bTest) eventHeadZoneChange; HeadRegion = Head;   // 0x101620a4-133
    if (NetMode != NM_Client && PlayerReplicationInfo) PRI->PlayerZone = Region.Zone;             // 0x10162139-59
}
```
So it writes `Region` from `Location`, `FootRegion` from `Location − CollisionHeight`, `HeadRegion`
from `Location + EyeHeight`; the region fields are written under `bTest` too, only the events are
suppressed.

`AActor::IsBlockedBy(Other)` `0x113fd0` (confirmed, read in full):
```
if (Other == Level) return bCollideWorld;                                                         // 0x10113fda-ed
if (Other->Brush && Other->IsA(ABrush)) return bCollideWorld && (GetPlayerPawn() ? Other->bBlockPlayers : Other->bBlockActors);   // 0x10113ff0-81
if (Brush && IsA(ABrush))            return Other->bCollideWorld && (Other->GetPlayerPawn() ? bBlockPlayers : bBlockActors);       // 0x1011400f-2e, 0x10114083-94
a = (GetPlayerPawn() || IsA(AProjectile)) ? Other->bBlockPlayers : Other->bBlockActors; if (!a) return 0;                          // 0x1011402e-a1
return (Other->GetPlayerPawn() || Other->IsA(AProjectile)) ? bBlockPlayers : bBlockActors;                                         // 0x101140a3-e4
```
`AActor::IsMovingBrush()` `0x1141e0`: `Brush && IsA(ABrush) && !bStatic`.

## 8. `dx-engine` (Deus Ex 1112fm) cross-check — constants skimmed, not read line by line

Export bodies (thunks followed): `UModel::LineCheck 0xf3c20`, `PointCheck 0xf1570`, `PointRegion
0xf5db0`, `FastLineCheck 0xf3280`, `ULevel::FindSpot 0x98480`, `AdjustSpot 0x98360`, `FarMoveActor
0x98ba0`, `MoveActor 0x990e0`, `MultiLineCheck 0x9b220`, `SetActorZone 0x9b940`,
`AActor::IsBlockedBy 0x4c5e0`, `FCollisionHash::ActorLineCheck 0x59160`.

| Item                                   | `ued`                                     | `dx` (✅ = same constant seen)                         |
|----------------------------------------|-------------------------------------------|---
| zero-extent pull-back                  | 0.5 uu                                    | ✅ `0x103f3dac` (`0.5`)                                |
| box sentinel / pull-back               | `Time=2.0`; `max(0.1, 0.1/Dist)`          | ✅ `0x103f3fa9` (2.0), `0x103f403b-55` (three `0.1`) |
| node push-out factor                   | 1.1                                       | ✅ `0x103f1a6c` etc. (`[0x10431c34]`)                  |
| point push-out scale                   | 1.02; `BestDist` init 100000              | ✅ `0x103f167e`, `[0x104335b4]`                        |
| leaf box planes                        | ±0.1                                      | ✅ (`[0x1042bcb0]` = 0.1 as f64, 6 uses)               |
| edge-plane dot threshold               | 0.001                                     | ✅ `[0x1042ac20]`                                      |
| `FindSpot`                             | `Size()+2`, `1.5·|Extent|²`               | ✅ `0x103986c8`, `0x1039896f`                          |
| `AdjustSpot`                           | `1.05 − Time`, TraceFlags 6               | ✅ `0x103983c6`; flags not checked                     |
| `MoveActor` overshoot                  | 2.0 uu                                    | ✅ `0x103993bc`                                        |
| `MultiLineCheck` dilation              | `(Dist+5)·T/(Dist+1e-4)`, `<0.01`, `<30`, mover tie `<4.0`, `−2·Dir` | ✅ `0x1039b34d-5e1` |
| `ActorLineCheck` TraceFlags            | `0x13` / `2` (movers only near a wall)    | absent — dx signature is `(FMemStack&, FVector×3, BYTE)`, no flags |
| `FarMoveActor` `CollisionTag` gate     | present (`0x1016013b`)                    | absent (no `[+0xfc]` access in `0x98ba0`–`0x98ea0`; dx `CollisionTag` = `+0xfc`) |
| `PointRegion`                          | `>= 0` → FRONT                            | ✅ same shape (`0x103f5e40`)                            |

No constant differs where checked; the `dx` walkers use x87 doubles for some intermediates
(`0.1`, `0.001` are f64 loads), so bit-exactness against `dx` is not guaranteed even with the same
constants. Not skimmed in `dx`: the `IsBlockedBy` branch structure, `SetActorZone`.

## 9. Constants table (`ued`)

| Value        | Address / immediate           | Used by                                                    |
|--------------|-------------------------------|---
| 0.5          | `[0x101fee20]`                | zero-extent `LineCheck` pull-back (uu)                     |
| 2.0          | imm `0x40000000`, `[0x10207904]` | box `LineCheck` `Time` sentinel; `MoveActor` overshoot/pull-back; `FindSpot` `Big` |
| 0.1          | `[0x10202940]`                | box `Time` pull-back fraction; leaf box-plane offsets      |
| 1.1          | `[0x10214618]`                | node-plane push-out factor (line and point walkers)        |
| 1.02         | `[0x10217614]`                | point-check push-out scale                                 |
| 1e-5 / −1e-5 | `[0x10217610]` / `[0x10217618]` | `ClipTo` parallel band                                   |
| 1e-6         | `[0x1021760c]`                | `FIntersectPlanes2` degenerate `|D|²`                      |
| 0.001        | `[0x1020293c]`                | edge-plane pair dot threshold                              |
| 100000.0     | imm `0x47c35000`              | point-check `BestDist` init                                |
| 1.05         | `[0x1020e458]`                | `AdjustSpot`                                               |
| 1.5          | `[0x1020e460]` (f64)          | `FindSpot` rejection radius                                |
| 5.0 / 1e-4   | `[0x10206784]` / `[0x10202934]` | `MultiLineCheck` dilation                                |
| 0.01 / 30.0  | `[0x101fee1c]` / `[0x1020e468]` | `MultiLineCheck` close-wall → movers-only actor query    |
| 4.0          | `[0x10202954]`                | `MultiLineCheck` mover/wall coincidence (`|Δ|² < 4`)      |
| 0x13 / 2 / 6 | immediates                    | TraceFlags: all-colliding / movers only / movers+level     |
| 0x40000000   | immediate                     | `LeafHulls` flip bit                                       |
| 0x21         | immediate                     | `NF_NotCsg|NF_IsNew` in `IsCsg`                            |

## 10. Evidence table (RVA → fact), the load-bearing ones

| RVA (`ued-engine`)   | Fact                                                              |
|----------------------|-------------------------------------------------------------------|---
| `0x101ae511-44`      | `Extent == 0` selects the fast walker; `0x101ae888` box path sets `Hit.Time = 2.0` |
| `0x101ae6ca-6fe`     | zero-extent `Time -= 0.5/|Dir|`, clamped                          |
| `0x101ae922-952`     | box `Time -= max(0.1, 0.1/Dist)`, clamped                         |
| `0x101abca2-cfd`     | node push-out `Σ|P·E·1.1|`                                        |
| `0x101abd3f`         | near side = `Dist1 >= Dist2`; `0x101abd99` recursion; `0x101abdc3` far child `iChild[1-Near]` |
| `0x101abd60-8e`      | `ChildOutside` uses `NodeFlags & 0x21` (no `ExtraNodeFlags`)      |
| `0x101abe33`         | leaf needs `iCollisionBound != -1`; `0x101abe80-ac` hull `ClipTo` loop |
| `0x101abec0-bffe`    | six box planes only when `Owner == NULL`; `Max.X/Y − 0.1`, `Max.Z + 0.1` |
| `0x101ac0e3`         | edge pair dot `> 0.001`; `0x101ac0fb` `FIntersectPlanes2`; `0x101ac141-165` normal sign fix |
| `0x101ac825-872`     | hit fill: `Time=T0`, `Normal`, `Actor=Owner`, `Primitive=Model`, `DidHit=1` |
| `0x101ad5ef-655`     | `ClipTo` enter/exit/parallel branches, `±1e-5`                    |
| `0x101ad6c5-77b`     | point `ClipTo`: `0 < Dist < BestDist`, `PushOut > Dist`, `1.02` |
| `0x101af16d-1cd`     | `Flags[i]` sign encoding; `0x101af1f1-226` `Box` from `HullData[N+1..N+6]` |
| `0x101aec06-3f`      | `PointCheck` presets `Hit` (`Time = 0`); `0x101aed37` zero-extent uses `> 0` |
| `0x101ad4d0` / `0x101ad4dc` | `BoxPointCheck` returns 0 only when the box passed every plane |
| `0x101aeefd`         | `PointRegion` `>= 0` → `iChild[1]`; `0x101aef0e-4d` leaf/zone/actor fill |
| `0x10160348-e2`      | `FindSpot` zero extent → single point check                       |
| `0x101604a1-600`, `0x10160693-75b` | 6 axis nudges then 8 diagonal nudges               |
| `0x10160760-df`      | `1.5·|Extent|²` rejection                                         |
| `0x1015f172-d3`      | `AdjustSpot`: flags 6, zero extent, `(1.05 − Time)·TraceLen`     |
| `0x10160b1a-4c`      | `MoveActor` traces `Delta + 2·Dir`                                |
| `0x10160cc6-d57`     | hit filter (`bIgnorePawns`, `IsBasedOn`, `IsBlockedBy`)          |
| `0x10160d8e-e7a`     | pull-back: stop 2 uu before contact; `Time = (moved−2)/|Delta|`  |
| `0x10161176`         | `bTest` skips Bump/Touch; `0x10161476` `SetActorZone` always     |
| `0x1016149d`         | `MoveActor` returns `Hit.Time > 0`                                |
| `0x1016164c-7b3`     | `MultiLineCheck` level trace, dilation, end shortening            |
| `0x10161823-2f`      | TraceFlags `2` when `Time < 0.01 && Dist < 30`, else `0x13`      |
| `0x101618d1-ae5`     | mover hit coincident with wall hit pulled back 2 uu               |
| `0x10161b50`         | hits sorted by `Time` (`0x1015f890`)                              |
| `0x1016006d-c3`      | `FarMoveActor` → `FindSpot(…, 0, 0)`; `0x101600d7-135` encroach unless `bTest` |
| `0x1016013b-48`, `0x101601bc` | `CollisionTag` gate; `0x10125a69`/`0x10126181` hash add/remove write it |
| `0x10161f4e-93`, `0x10162008-9e`, `0x101620a4-133` | `SetActorZone` writes `Region`, `FootRegion` (−CH), `HeadRegion` (+EyeHeight) |
| `0x10113fda-ed`, `0x10113ff0-81` | `IsBlockedBy`: Level → `bCollideWorld`; mover → `bCollideWorld && bBlockActors/Players` |
| `0x10125238-c0`      | `ActorLineCheck` stamps `CollisionTag`, calls `GetPrimitive()->LineCheck` (slot 22) |
| `0x1011634c-3c5`     | `ABrush::ToWorld` chain                                          |

## 11. Port notes — what a Rust implementation must reproduce

Call order for one `walkMove` step (§4.5 of `11-ued-reachability.md`), scout with `bCollideWorld`,
`bCollideActors` per its class defaults, `Extent = (CR, CR, CH)`:

1. `MoveActor(Delta.Z=0, bTest=1, bIgnorePawns=1)` → `MultiLineCheck(Start=Location, End=Location +
   Delta + 2·Dir, Extent, bCheckActors, Level, 0)` → `UModel::LineCheck` box path (§1) on the level
   with `Owner = NULL`; then, if `bCheckActors`, `ActorLineCheck` (only Movers matter for the build:
   §1 again with `Owner = Mover`, planes transformed by `ABrush::ToWorld`). Apply the dilation and
   sort; `MoveActor` filters (`IsBasedOn`, `IsBlockedBy`), pulls back 2 uu, writes `Location`, calls
   `SetActorZone(bTest=1)` (§7: `Region`/`FootRegion`/`HeadRegion` via `PointRegion`), returns
   `Time > 0`.
2. Step-up / step-down / drop probe are the same call with `Delta = ±(0,0,MaxStepHeight)` and
   `(0,0,−(MaxStepHeight+2))`.
3. `FarMoveActor(StartLocation, bTest=1, bNoCheck=1)` restores: with `bNoCheck` no `FindSpot`, no
   encroachment; writes `Location`/`OldLocation`, `SetActorZone(bTest=1)`.
4. `findBestReachable`'s placement is `FarMoveActor(A.Location, 0, 0)`: `FindSpot(Extent, loc, 0,
   0)` (§3 — up to 14 zero-extent `SingleLineCheck` traces with flags 6 and 3 `SinglePointCheck`s,
   each a `PointCheck` box test, §2), then `CheckEncroachment` (not read), then `bJustTeleported`.

Must-match details (each one changes edges):

- Box walker: push-out with the **1.1** factor at node planes, **without** it at hull/box/edge planes;
  `Near = Dist1 >= Dist2`; `Outside` threading with plain `0x21`; leaf test only on `Outside == 0`
  leaves with a collision hull; the six box planes with the asymmetric `−0.1`/`+0.1` W's only when
  `Owner == NULL`; the pairwise bevel planes from `Flags` sign bits and `FIntersectPlanes2`; the
  `ClipTo` `±1e-5` bands and the `Max(0, Num)` clamp when moving inward with `Dist1 >= 0`; hit fill
  `Time = T0`, then `Time = clamp(T0 − max(0.1, 0.1/Dist), 0, 1)`, `Location = Start + Dir·Time`.
  `Hit.Item` is untouched; `Hit.Normal` is the untransformed hull normal (world space for the level).
- The leaf hull data: `LeafHulls[iCollisionBound..]` = node indices with bit 30 = flip, `−1`, then
  six floats `Min/Max` — the native BSP build must produce exactly the editor's hull sets and boxes
  (the same hull composition = the same bevel planes = the same hits).
- `MoveActor`: 2-uu overshoot and pull-back, `Time` rescale `(moved − 2)/|Delta|`, zero-move when
  `moved <= 2`, return `Time > 0`; hit filter order; `SetActorZone` also under `bTest`.
- `MultiLineCheck`: dilation `min(1, (Dist+5)·T/(Dist+1e-4))` shortening the actor query; movers-only
  query when the wall hit is `< 0.01` and `< 30 uu`; the mover/wall 2-uu tie-break; sort by `Time`.
- `PointCheck` (through `FindSpot`): `1.1` push-out at nodes, `ExtraNodeFlags` honoured here (but
  `MultiPointCheck` passes 0), `1.02·(PushOut − Dist)` push-out along the least-penetrated hull
  plane, `Time = 0`; zero-extent path uses `> 0` where `PointRegion` uses `>= 0`.
- `FindSpot`: exact nudge order (X−, Y−, Z−, X+, Y+, Z+ — note the loop is `for i in {−1,+1}` with
  X,Y,Z inside), zero-extent traces of length = the extent component, diagonal traces of length
  `|Extent| + 2`, `1.5·|Extent|²` cutoff, three point checks max.
- `IsBlockedBy` for the scout vs a Mover: `scout.bCollideWorld && Mover.bBlockActors` (the scout is
  not a player).
- `PointRegion`: `>= 0` descent, zone 0 / leaf −1 on a solid side; `ZoneNumber == 0` is the
  reachability code's "out of the world" signal.

What is NOT needed for the build path: rider/`StandingCount` handling, Bump/Touch, encroachment
(only on the non-test placement — whether `CheckEncroachment` can fail a scout placement in an
editor level without other colliding actors is unverified), the cylinder `UPrimitive::LineCheck`
(pawns/decorations are `bIgnorePawns`-skipped and the build map has no other movable colliders).

## 12. Open points

- `CheckEncroachment` (slot 46, `0x15f370`) not read; it runs on every non-test `FarMoveActor`
  (`findBestReachable`'s placement) — could reject a scout size where a pawn/decoration overlaps.
- `FPlane::TransformPlaneByOrtho` `W` adjustment and the `FCoords * FScale/FRotator` algebra are
  Core's and were not decoded — needed only for Mover brushes (`Owner != NULL`).
- Whether a `LeafHulls` entry can carry other high bits than `0x40000000` (`SetupHull` masks by
  `shl 6`, the walkers mask `~0x40000000` for the `Item` value, which is never used).
- `0x1aea70` — an SSE zero-extent walker variant with an unknown caller; not on the scout path as far
  as read.

## 13. Ranges read / skipped

Read in full: `0x1ae4c0`–`0x1aea5d` (LineCheck), `0x1ab9e0`–`0x1abc0b` (both check-info ctors),
`0x1abc10`–`0x1ac881` (BoxLineCheck), `0x1ac890`–`0x1acec1` + `0x1ad3f9`–`0x1ad4e6` (BoxPointCheck;
`0x1acec1`–`0x1ad3f9` skimmed as the Y/Z repeats), `0x1ad4f0`–`0x1ad531` (ChildOutside),
`0x1ad540`–`0x1ad655` (both ClipTo), `0x1ad7a0`–`0x1ada04` (FIntersectPlanes2), `0x1aeba0`–`0x1aee17`
(PointCheck), `0x1aee60`–`0x1aef74` (PointRegion), `0x1af0d0`–`0x1af22e` (SetupHull),
`0x1602e0`–`0x10160870` (FindSpot), `0x15f140`–`0x15f1db` (AdjustSpot), `0x1608e0`–`0x1614b5`
(MoveActor), `0x161500`–`0x161bdf` (MultiLineCheck), `0x15ff80`–`0x160261` (FarMoveActor),
`0x161e10`–`0x162178` (SetActorZone), `0x162400`–`0x16256b` (SingleLineCheck, filter tail skimmed),
`0x162620`–`0x1627c6` (SinglePointCheck), `0x161c70`–`0x161dce` (MultiPointCheck),
`0x125080`–`0x12533b` (ActorLineCheck), `0x113fd0`–`0x1140ed` (IsBlockedBy), `0x1141e0`–`0x11420c`,
`0x116290`–`0x1163dd` (ToWorld ×2), `0x15f890`–`0x15f8b6` (hit comparator), Core `0x17d90`
(`FPlane|FVector`), Core `0x2db90`–`0x2dc8a` (TransformPlaneByOrtho, partial).
Skipped: `0x1ae190` (zero-extent walker — already ported), `0x1aea70` (an SSE line walker, caller
unknown), `0x15f1e0` (rider list builder), `0x15f370` (CheckEncroachment), `0x112980`
(GetPrimitive), `0x125380` (ActorPointCheck), `FCollisionHash::AddActor/RemoveActor` beyond the
`CollisionTag` writes, the `UPrimitive` cylinder `LineCheck`.
