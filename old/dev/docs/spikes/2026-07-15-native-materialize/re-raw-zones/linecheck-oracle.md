# UModel::LineCheck decode + offline oracle — root cause of the native fall-through

**Date:** 2026-07-16. **Binary:** GAME `Engine.dll` (`/home/neob91/Games/LutrisDX/drive_c/DX/System/Engine.dll`,
ImageBase `0x10300000`; all RVAs below are file-RVAs at that base).
**Oracle:** `dev/docs/spikes/2026-07-15-native-materialize/harness/line_check.py` (validated below).

## TL;DR — root cause

`UModel::LineCheck` has **two disjoint implementations** selected by `Extent`:

- **`Extent == (0,0,0)`** → the node-plane recursion at **0xf3560** (what section 60 decoded).
  Solidity = `FBspNode::IsCsg` during the plane walk. Needs NO LeafHulls. **Works on our maps.**
- **`Extent != (0,0,0)`** (every pawn / anything with a collision cylinder) → outer branch
  **0xf3f6e** builds an `FBoxLineCheckInfo` (ctor 0xf18e0) and calls
  **`FBoxLineCheckInfo::BoxLineCheck` at 0xf42f0** — a *different* function from 0xf3560.
  Its descent uses `IsCsg` + plane push-out only to *route* to solid leaves; **the HIT itself is
  produced exclusively by clipping the swept box against the terminal leaf's convex hull**, read
  from `Model.LeafHulls` via `Nodes[iParent].iCollisionBound`:

  ```
  0xf45fa  test ecx,ecx / jne 0xf5682      ; Outside      -> return (in empty space, fine)
  0xf4602  mov  ecx,[ebp+0x2c]             ; iCollisionBound of the solid leaf's parent node
  0xf4605  cmp  ecx,-1
  0xf4608  je   0xf5682                    ; NO HULL -> return WITHOUT REGISTERING ANYTHING
  ```

  The **single** `DidHit = 1` store in the whole 5 KB function is at **0xf5678**, reachable only
  through the hull-clip path. There is **no node-plane fallback** for the box case.

Our native builds emit `iCollisionBound = -1` on **every** node and an **empty `LeafHulls`**
(`Test_Castle.dx`: 308/1156 nodes carry hulls, 3866 LeafHulls ints; `NativeE2E/NativeCastle/
NativeCSG`: 0 and 0). Therefore **every swept-box trace against a native map misses everything**
— the pawn's downward sweep never lands, regardless of NodeFlags / front-back topology / iLeaf
(all of which are now correct after the section-60 fix). It is **not multi-brush specific**; the
single-brush maps only *look* different because the pawn's **center** then crosses into the
(correctly classified) solid/zone-0 region below the floor, and the engine's zone tracking
(`PointRegion` on the pawn **center** — point semantics) triggers the fell-out-of-world handling
→ `PHYS_None`, frozen with the center ~at the floor plane. On big rooms the same fall simply
runs away → bounce to the DXOnly menu. Section 60's "NativeCSG works, PHYS_Walking z=-134"
conclusion is **superseded** — live re-test shows phys=0, center-on-plane there too.

Answers to the coordinator's three questions:

1. **Which function lands a falling pawn?** `ULevel::MoveActor → SingleLineCheck →
   UModel::LineCheck(Extent=cylinder) → FBoxLineCheckInfo::BoxLineCheck (0xf42f0)`. Not
   `PointCheck` (0xf19b0 — that's FarMoveActor/FindSpot/encroachment), not the 0xf3560 line walk.
2. **Does it degrade to a point test without hulls?** No — worse: it registers **no hit at all**
   (gate above). The "center rests on the plane" is *not* LineCheck degrading; it is the
   zone/PointRegion machinery (a genuine point test on the center) taking over after the sweep
   fails: center crosses the floor plane → zone 0 → FellOutOfWorld → PHYS_None at ~the plane.
   The zero-extent oracle reproduces the resting heights exactly (see validation).
   `UModel::PointCheck` behaves consistently: its `iCollisionBound==-1` guard (0xf1bff) jumps to
   the epilogue (0xf2baf) returning the accumulated flag — i.e. hull-less solid space does not
   block a box point-check either.
3. **Is bspBuildBounds (LeafHulls + iCollisionBound) REQUIRED?** **Yes.** It is the only hit
   source for any Extent≠0 trace. Proven sufficient by A/B: synthesizing a hull for NativeCSG's
   below-floor solid leaf (5 plane refs + bbox, nothing else changed) makes the oracle's box
   sweep land at floor+extent (see §5). Zones are not involved in the sweep at all.

---

## 1. Function map

| RVA | What | Evidence |
|---|---|---|
| 0xf3c20 | `UModel::LineCheck(FCheckResult&, AActor* Owner, FVector End, FVector Start, FVector Extent, DWORD ExtraNodeFlags)` outer | export `?LineCheck@UModel@@...` thunk 0x3e5e |
| 0xf3560 | zero-extent recursion ("LineCheckR") | called from 0xf3d26 region |
| 0xf3f6e | box branch of outer (Extent≠0, tested vs 0.0f at 0xf3c56) | |
| 0xf18e0 | `FBoxLineCheckInfo::FBoxLineCheckInfo(Hit, Model, Owner, Extent(3f), ExtraFlags)` (thunk 0x103034ef) | |
| 0xf42f0 | `FBoxLineCheckInfo::BoxLineCheck(INT iParent, INT iNode, UBOOL IsFront(unused), UBOOL Outside)` (thunk 0x10302838) | |
| 0xf5b80 | `FBoxLineCheckInfo::ClipTo(FPlane&, INT)` (thunk 0x10302676) | |
| 0xf6590 | `FBoxPushOut(Extent, Normal)` = Σ\|Eᵢ·Nᵢ\| (thunk 0x1030143d) | |
| 0xf6600 | `FIntersectPlanes2(I, D, P1, P2)` (thunk 0x1030112c) | |
| 0xf68b0 | `FBspNode::IsCsg(ExtraFlags)` (thunk 0x1030150f) | section 60 §2.1, re-confirmed |
| 0xf19b0 | `FBoxPointCheckInfo::PointCheck`-recursion (UModel::PointCheck path) | section 60; guard 0xf1bff→0xf2baf |

Core.dll imports used (resolved from the IAT): `FVector::operator|` (dot, 0x1059a0ac),
`operator^` (cross, 0x1059a10c), `operator-`/`operator+` (0x1059a070/0x1059a038),
`operator*=` (0x10599ca8 — **mutates in place**, used to flip edge-plane normals),
`FVector(x,y,z)` (0x10599b28), `TransformVectorBy` (0x10599b30), `Size` (0x1059a0bc),
`UnsafeNormal` (0x1059a100), `FPlane::PlaneDot` (0x1059a110), `FPlane::Flip` (0x1059a114),
`FPlane::TransformPlaneByOrtho` (0x1059a118), `FPlane(Point,Normal)` (0x10599edc),
`GMath` (0x10599b2c — UnitCoords at +0x18 when Owner==NULL), `appSqrt` (0x10599ca4).

Constants: `-0.001/+0.001` doubles @0x104335b8/0x1042ac20 (line-walk side epsilons and the
edge-pair dot threshold), `±1e-5` @0x104335d8/0x104335c8 (slab entry/exit epsilon),
`1e-6` @0x10433610 (FIntersectPlanes2 parallel guard), `0.0/1.0/-1.0` doubles
@0x10429838/0x104298a0/0x10429c58, `0.1f` @0x10431c54 (time truncation), **`1.1f` @0x10431c34
(descent extent inflation)**, `0.1` double @0x1042bcb0 (leaf-box face push), `0.5f` @0x10426d74
(zero-extent time backoff), `0.0f` @0x10426d54.

## 2. `FBoxLineCheckInfo` layout (ctor 0xf18e0 + outer stores)

```
+0x000 FCheckResult& Hit          +0x048 DWORD ExtraFlags (unused by BoxLineCheck itself)
+0x004 UModel*       Model        +0x04c INT   NumHullPlanes (this trace's scratch)
+0x008 AActor*       Owner        +0x050 FVector BestNormal   (hit normal accumulator)
+0x00c FCoords Coords (Owner->    +0x05c FBox  LeafBox (6 floats, loaded per leaf)
       ToLocal(), vtbl+0x88;      +0x078 FLOAT T0 (= -1.0 init per leaf)
       GMath.UnitCoords if NULL)  +0x07c FLOAT T1 (= Hit.Time init per leaf)
+0x03c FVector Extent             +0x080 FPlane[0x40] hull-plane scratch
                                  +0x480 INT[0x40]   per-plane axis-sign flags
+0x580 INT* current hull ptr      +0x584 FVector End      +0x590 FVector Start
+0x59c FVector (End-Start)        +0x5a8 FLOAT Dist       +0x5ac INT DidHit
```
Outer (0xf3f8f..0xf402d): `Hit.Time=2.0f`, ctor, store End/Start/Vector/Dist, `DidHit=0`,
`BoxLineCheck(0, 0, 0, Model->RootOutside /*Model+0xf0*/)`.

## 3. `BoxLineCheck` decode (0xf42f0)

Iterative near/far walk, recursion for the near side:

```
while iNode != -1:                                        # 0xf42fa / 0xf45d1
    n,w   = Nodes[iNode].Plane                            # Owner==NULL: raw plane (0xf43ae)
    d0    = n·Start - w        (this+0x590)               # 0xf4407..
    d1    = n·End   - w        (this+0x584)               # 0xf43cf..
    push  = FBoxPushOut(Extent * 1.1f, n)                 # 0xf442d.. (const 0x10431c34!)
    useBACK  = (d0 <= push)  or (d1 <= push)              # 0xf4497.. [esp+0x1c]
    useFRONT = (d0 >= -push) or (d1 >= -push)             # 0xf44b9.. [esp+0x20]
    side  = 1 if d0 >= d1 else 0                          # 0xf44e3 (side start moves FROM)
    if use[side]:                                         # 0xf4500
        childOut = Outside or IsCsg(node)        if side==1   # inline, mask 0x21, NO ExtraFlags (0xf451e)
                 = Outside and not IsCsg(node,0) if side==0   # thunk call w/ 0 (0xf452f)
        BoxLineCheck(iNode, iChild[side], side, childOut)     # 0xf4556 recursion
    if use[1-side]:                                       # 0xf455b
        Outside  = same update for far side               # 0xf458c..
        iParent  = iNode (ebx, 0xf456a)                   # leaf's parent for the hull lookup
        iNode    = iChild[1-side]                         # 0xf4575
    else: return
# terminal:
if Outside: return                                        # empty leaf, nothing to do (0xf45fa)
if Nodes[iParent].iCollisionBound == -1: return           # *** NO HULL -> NO HIT *** (0xf4602)
<hull clip, below>
```

`iChild[1]` (serial +0x24) = FRONT, `iChild[0]` (+0x20) = BACK — same convention section 60
proved; the walk itself behaves identically on correct-topology native maps. Note the descent
inflates the extent by **1.1** for routing (so borderline leaves are still visited), but the
hull clip uses the exact extent.

### The leaf hull clip (0xf460e..0xf5678) — the only hit source

```
hull = &LeafHulls[iCollisionBound]                        # Model+0xcc (0xf460e)
planes: while hull[k] != -1 and k < 0x40:                 # 0xf4624..
    P = Nodes[hull[k] & 0xBFFFFFFF].Plane                 # bit 0x40000000 = Flip (negate all 4)
    (Owner: TransformPlaneByOrtho)                        # 0xf467f (skipped, Owner NULL)
    flags[k] = sign bits: x<0:1 x>0:2 y<0:4 y>0:8 z<0:16 z>0:32     # 0xf46d4..
box  = 6 floats bit-stored in LeafHulls after the -1      # 0xf47b2 (leaf's FBox)
T0 = -1.0; T1 = Hit.Time; Best = (0,0,0)                  # 0xf47df/0xf47e6

clip(plane P, pushout PO):                                # inlined + ClipTo 0xf5b80
    d0 = P·Start - W;  d1 = P·End - W
    A  = d0 - PO
    if d0 > d1 and -PO <= A < 0: A = 0                    # interpenetrating start -> t=0
    delta = d0 - d1
    if   delta < -1e-5:  T1 = min(T1, A/delta)            # exit plane
    elif delta > +1e-5:  if A/delta > T0: T0 = A/delta; Best = P.n   # entry plane
    else:                if d0 > PO and d1 > PO: MISS     # parallel & fully outside
    if T0 >= T1: MISS                                     # empty interval

1. for each hull plane:      clip(P, FBoxPushOut(Extent, n))          # 0xf480a..
2. for the 6 leaf-box faces: normals ±axis, W pushed OUT by 0.1:      # 0xf4968..0xf51a9
     (0,0,-1, 0.1-min.z) (0,0,1, max.z+0.1) (-1,0,0, 0.1-min.x)
     (1,0,0, max.x+0.1)  (0,-1,0, 0.1-min.y) (0,1,0, max.y+0.1)
     clip(F, FBoxPushOut(Extent, n))
3. edge pairs (i, j<i over hull planes; 0xf51af..0xf55fd):
     fl = flags[i]|flags[j]
     for axis A in X(mask 3), Y(mask 0xc), Z(mask 0x30):
         if fl & mask != mask: continue                    # pair must straddle the axis
         if (A^Ni)·(A^Nj) <= 0.001: continue               # 0xf5273
         I, D = FIntersectPlanes2(Pi, Pj)                  # 0xf6600: D=Ni^Nj;
                                                           #   I=(Wi*(Nj^D)+Wj*(D^Ni))/|D|² ; |D|²<1e-6 -> zeros
         n = UnsafeNormal(A ^ D);  if n·Ni < 0: n = -n     # 0xf52d0/0xf52e3 (operator*= -1)
         ClipTo(FPlane(I, n), -1)  -> MISS propagates      # 0xf5337

accept (0xf561d): T0 > -1.0  and  T0 < T1  and  T1 > 0.0
   -> Hit.Time = T0; Hit.Normal = Best; Hit.Actor = Owner; Hit.Primitive?=Model; DidHit=1  # 0xf564a..0xf5678
```
`MISS` = jump to the shared epilogue 0xf5682 (abandon this leaf; recursion elsewhere continues).
T1 is seeded from the *current* `Hit.Time`, so an earlier (nearer) hit automatically rejects
farther leaves; the near-side-first recursion order makes the first accepted hit the nearest.

Editor hull convention (dumped from `Test_Castle.dx`, node 1152, iColl=3854): the hull describes
the **solid** leaf cell, plane normals pointing **out of the solid** (interior of the cell has
PlaneDot < 0), plus the cell's FBox (extends to ±32768 where the solid is unbounded).

### Outer post-processing (0xf4032..0xf413b)

```
if !DidHit: return 1                                      # unobstructed
Hit.Time = clamp(Hit.Time - max(0.1/Dist, 0.1), 0, 1)     # 0xf403b.. (0.1f @0x10431c54)
Hit.Location = Start + (End-Start)*Hit.Time               # 0xf408d..
return Hit.Time == 1.0                                    # 0xf40f3 (1 = treat as no-hit)
```

## 4. Zero-extent path (0xf3560) — for completeness

Decoded in full (see `line_check.py::_line_check_zero`); matches section 60 plus:
argument layout `(Result, Model, BoxInfo, iHitNode, iNode, End, Start, Outside, ExtraFlags)`;
non-split branches strip flag `0x10` from ExtraFlags before the inline IsCsg (0xf3736), split
branches pass full flags to the IsCsg thunk; front branch when both dists > -0.001, back when
both < 0.001, else split at `Middle = Start + (Start-End)*(d0/(d1-d0))`, near side = `d0 > 0`,
near recursion `Start→Middle`, far iteration `Middle→End` with `iHitNode = iNode` recorded —
the hit normal is the **last crossed node's plane**. Terminal: `Outside≠0` sets the global
`GDidHitEmpty` (0x1058f34c) and returns 1; `Outside==0` fills `Result.Location=Start(current)`,
`Normal=Nodes[iHitNode].Plane`, returns 0 — **no LeafHulls anywhere**. Trace flag 0x10 =
"ignore solid-before-any-empty" (start-in-solid tolerance, 0xf3a1f).

## 5. Oracle validation (`line_check.py`)

Downward pawn sweep, `Extent=(20,20,44)`:

| Map | sweep | result |
|---|---|---|
| Test_Castle.dx (editor) | (0,-250,48) → z-10048 | **HIT** t=0 (already resting), n=(0,0,1), node 1152 |
| Test_Castle.dx | (0,-250,148) → (0,-250,-52) | **HIT** t=0.42 → contact center z=44 = floor 0 + extent 44 (0.1-trunc backoff reported) |
| Test_Castle.dx | horizontal (0,-250,100)→(0,-280,100) | no hit (open room) ✓; upward → HIT ceiling n=(0,0,-1) ✓ |
| NativeE2E.dx | (0,-200,-150) → down | **NO HIT** (falls through) |
| NativeCastle.dx | (0,-250,48) → down | **NO HIT** |
| NativeCSG.dx | (0,0,-88) → down | **NO HIT** |

Zero-extent (point) trace on the native maps — matches the live "center rests on the plane":

| Map | floor plane | point-trace hit z |
|---|---|---|
| NativeE2E.dx | -192 | **-191.5** (plane + 0.5 backoff) — live pawn froze at -192 |
| NativeCSG.dx | -128 | **-127.5** — live pawn froze at -128 |
| NativeCastle.dx | ~0 | 0.5 |

A/B fix proof (in-memory, `NativeCSG.dx`): append one hull —
`[0|FLIP, 1|FLIP, 2|FLIP, 3|FLIP, 5, -1, box(-256,-256,-32768 .. 256,256,-128)]`, set
`Nodes[5].iCollisionBound=0`, change nothing else → sweep (0,0,0)→(0,0,-200) **HITS** with
contact center z = -84 = floor(-128) + extent(44); half-buried start blocks at t=0; a sweep at
(200,200) also lands (walls/edges clip correctly). **Hulls alone flip native maps from
fall-through to landing.**

## 6. What must change in the native build

Port **`bspBuildBounds`** (editor `0xaace0` decode already on file): for every terminal BSP cell
that is **solid** (`Outside == 0` side), emit into `Model.LeafHulls`:
`[plane-node refs with bit 0x40000000 when the node plane's front faces INTO the solid, ..., -1,
6 bit-cast f32 bbox mins/maxs]` (normals must point **out of the solid**, bbox = the cell's box,
±32768 where unbounded, ≤0x40 planes), and point the **parent node's `iCollisionBound`** at the
entry (`Bounds`/`iRenderBound` are separate and can stay -1: the box sweep reads neither).
Zone portalization is NOT needed for collision. The section-60 fixes (NodeFlags, front/back
slots, iLeaf) remain necessary — the descent and the zone classification depend on them — they
were just not *sufficient*.

Superseded: section 60's closing claim that `iCollisionBound = -1` is fine for the pawn
("collision hull NOT required") — true only for zero-extent traces; every real actor sweep is
a box sweep and requires the hulls.
