# RE: `bspBuildBounds` (Editor.dll 0xaace0) + UModel Zones/NumZones layout — 2026-07-16

Binary: `uned/UED22/Editor.dll` (base 0x10000000), `Engine.dll` (base 0x10100000 file RVAs shown
as 0x101xxxxx in adis output = RVA + base), `core.dll` (base 0x10000000). All quoted addresses
are VAs from `adis.py`. Struct offsets per the shared brief (UModel/FBspNode/FPoly).

---

## ASSIGNMENT 1 — `UEditorEngine::bspBuildBounds` @ Editor 0xaace0

### 1.0 Function map (all byte-decoded this session)

| RVA | name (guard string / import evidence) | role |
|---|---|---|
| 0xaace0 | `UEditorEngine::bspBuildBounds` (guard w"UEditorEngine::bspBuildBounds" @0x100fedf8) | top level |
| 0xa8850 | `FEditorVisibility::BuildZoneMasks` (guard @0x100fe758) — *also portalize "pass E"* | recursive node ZoneMask fill |
| 0xa8a40 | `FilterBound` (logs w"FilterBound: …" @0x100fecf0/0xfed84/0xfedc0) | THE recursive bound builder |
| 0xaa000 | `SplitPartitioner` (logs reuse the FilterBound strings "Got inficoplanar"/"Got infifront") | clip the node's infinite partition poly into the hull |
| 0xa7ae0 | `BuildInfiniteFPoly` (guard w"BuildInfiniteFPoly" @0x100feebc) | huge quad on a node's plane |
| 0xaaa20 | `UpdateBoundWithPolys` (guard w"UpdateBoundWithPolys" @0x100fec18) | AABB += poly verts |
| 0xaaae0 | `UpdateConvolutionWithPolys` (guard w"UpdateConvolutionWithPolys" @0x100fec44) | emit one LeafHulls run + set `iCollisionBound` |
| 0xa9fe0 | `TArray<FBox>::Shrink` (Realloc 0x1c if Max!=Num) | trim `Bounds` |

Key imports used (IAT slot → demangled): `[0x100ceea4]`=FPoly ctor, `[0x100ceea0]`=`FPoly::Init`,
`[0x100cee34]`=`FPoly::SplitWithPlane(FVector&,FVector&,FPoly*,FPoly*,int)`,
`[0x100cee40]`=`FPoly::SplitInHalf`, `[0x100cee94]`=FPoly copy-ctor, `[0x100cee28]`=`FPoly::operator=`,
`[0x100cee44]`=`FPoly::Reverse`, `[0x100ce4dc]`=`FBox::FBox(int)`, `[0x100ce4d8]`=`FBox::operator+=(FVector)`,
`[0x100ce004]`=`FBox::operator+=(FBox&)`, `[0x100ce1c4]`=`FBox::operator=`,
`[0x100ce5ec]`=`FArray::Add(int,int)`, `[0x100ce5f4]`=`FArray::Realloc(int)`,
`[0x100ce530]`=`FMemStack::PushBytes`, `[0x100ce52c]`=`FMemMark::Pop`, `[0x100ce508]`=`GMem`,
`[0x100ce264]`=`FVector::FindBestAxisVectors(FVector&,FVector&)`.

### 1.1 `bspBuildBounds(UModel* Model)` — pseudo-C

```c
void bspBuildBounds(UModel* Model) {                    // Model = ebx
    if (Model->Nodes.Num == 0) return;                  // 0xaad1c: cmp [ebx+0x5c],0; jne
    BuildZoneMasks(Model, 0);                           // 0xaad44: push 0; push ebx; call 0xa8850

    FPoly Polys[6]; FPoly* PolyList[6];                 // Polys at ebp-0xb3c (stride 0x1d8)
    for (i = 0..5) { FPoly(); Init();                   // 0xaad72 ctor / 0xaadaa Init
        PolyList[i] = &Polys[i];                        // 0xaada6: [ebp+esi*4-0x2c]
        Polys[i].NumVertices = 4;                       // 0xaadb0: mov [eax+0x1c0],4
        Polys[i].iBrushPoly  = -1; }                    // 0xaadbe: mov [eax+0x1c8],-1
    /* the 6 faces of the ±HALF_WORLD_MAX cube, HALF_WORLD_MAX = 32768.0f (0x47000000),
       Base = V0, outward normals, verified programmatically from the fill block
       0xaadd1..0xab58d (winding CCW seen from outside, cross(V1-V0,V2-V1) == Normal): */
    // P0 z=+32768 N=(0,0,+1)  V: (-,-,+)(+,-,+)(+,+,+)(-,+,+)
    // P1 z=-32768 N=(0,0,-1)  V: (-,+,-)(+,+,-)(+,-,-)(-,-,-)
    // P2 y=+32768 N=(0,+1,0)  V: (-,+,-)(-,+,+)(+,+,+)(+,+,-)
    // P3 y=-32768 N=(0,-1,0)  V: (+,-,-)(+,-,+)(-,-,+)(-,-,-)
    // P4 x=+32768 N=(+1,0,0)  V: (+,+,-)(+,+,+)(+,-,+)(+,-,-)
    // P5 x=-32768 N=(-1,0,0)  V: (-,-,-)(-,-,+)(-,+,+)(-,+,-)

    Model->Bounds.Num = Model->Bounds.Max = 0;          // 0xab5ad/0xab5b7: [ebx+0xc4]=[ebx+0xc8]=0
    Model->Bounds.Realloc(elem=0x1c);                   // 0xab5c1: push 0x1c; ecx=&[ebx+0xc0]
    Model->LeafHulls.Num = Max = 0; Realloc(elem=4);    // 0xab5d1..0xab5e7: ecx=&[ebx+0xcc]
    for (i = 0..Nodes.Num-1) {                          // 0xab5eb loop, node stride <<6
        Nodes[i].iRenderBound    = -1;                  // 0xab5fe: [node+0x30] = -1
        Nodes[i].iCollisionBound = -1; }                // 0xab609: [node+0x2c] = -1

    FilterBound(Model, /*ParentBound*/NULL, /*iNode*/0,
                PolyList, 6, Model->RootOutside);       // 0xab621: pushes [ebx+0xf0],6,&PolyList,0,0,ebx
    Model->Bounds.Shrink();                             // 0xab640: ecx=&[ebx+0xc0]; call 0xa9fe0
    debugf(L"bspBuildBounds: Generated %i bounds, %i hulls",  // str @0x100fee60
           Model->Bounds.Num /*[ebx+0xc4]*/, Model->LeafHulls.Num /*[ebx+0xd0]*/); // 0xab64d/0xab653
}
```

Confirms: `Bounds` = TArray at UModel **+0xc0** with mem elem **0x1c (FBox = 6×f32 + valid byte,
padded)**; `LeafHulls` = TArray<INT> at **+0xcc**; `RootOutside` at **+0xf0**.

### 1.2 `BuildZoneMasks(Model, iNode) -> u64` @0xa8850 (recursive, cdecl, ret in edx:eax)

```c
u64 mask = 0;                                           // 0xa888e xorps/movlpd
if (node.iZone[0] /*[ebx+0x34] byte*/ != 0) mask |= 1ull << iZone[0];   // 0xa8896..0xa88b8
if (node.iZone[1] /*[ebx+0x35] byte*/ != 0) mask |= 1ull << iZone[1];   // 0xa88c3..0xa88e9
if (node.iChild[1] /*+0x24*/ != -1) mask |= BuildZoneMasks(Model, iChild[1]);  // 0xa88ef
if (node.iChild[0] /*+0x20*/ != -1) mask |= BuildZoneMasks(Model, iChild[0]);  // 0xa890b
if (node.iPlane    /*+0x28*/ != -1) mask |= BuildZoneMasks(Model, iPlane);     // 0xa8929
node.ZoneMask /*+0x10 u64*/ = mask;                     // 0xa8947: mov [ebx+0x10],esi / [ebx+0x14],edi
return mask;
```
The 64-bit `1<<z` is the bts/cmovae idiom at 0xa88a4-0xa88b2. **Zone 0 contributes NO bit** (the
`test al,al; je` guards). This runs over the coplanar (`iPlane`) chain too. Called both by
portalize step 11 ("pass E") and again at the top of `bspBuildBounds`.

### 1.3 `FilterBound(Model, FBox* ParentBound, iNode, FPoly** PolyList, nPolys, Outside)` @0xa8a40

Stack/registers: Model=[ebp+8]→ebx, ParentBound=[ebp+0xc]→[ebp-0x214], iNode=[ebp+0x10],
PolyList=[ebp+0x14]→[ebp-0x200], nPolys=[ebp+0x18]→[ebp-0x1f4], Outside=[ebp+0x1c]→esi.
FMemMark saved at [ebp-0x23c] (GMem Top/+0xc snapshot, popped at 0xa9003).

```c
node = &Nodes[iNode]; surf = &Surfs[node.iSurf /*+0x1c*/];      // 0xa8a8d/0xa8a9e
FVector* Base   = &Points [surf->pBase   /*surf+8*/ ];         // 0xa8abc: *12 into [ebx+0x88]
FVector* Normal = &Vectors[surf->vNormal /*surf+0xc*/];        // 0xa8ad1: *12 into [ebx+0x78]
FBox Bound(0);                                                  // ebp-0x230, FBox(int) ctor
Bound.Min = (+65536,+65536,+65536); Bound.Max = (-65536,...);   // 0xa8aff..: 0x47800000/0xc7800000
   // NOTE: DEAD values — FBox(0) leaves IsValid=0 and operator+=(FVector) overwrites
   // Min=Max=first point when !IsValid (core.dll 0x186b8). Port as plain "invalid AABB".
FPoly** FrontList = New(GMem, (nPolys*2+16)*4);                 // 0xa8af5: esi = n*8+0x40; PushBytes
FPoly** BackList  = New(GMem, (nPolys*2+16)*4);
int nFront=0 /*[ebp-0x1e4]*/, nBack=0 /*[ebp-0x1e0]*/;
FPoly* FrontPoly = new(GMem) FPoly;                             // 0xa8b68: PushBytes(0x1d8)+ctor
FPoly* BackPoly  = new(GMem) FPoly;

for (i = 0; i < nPolys; i++) {                                  // 0xa8bbc..0xa8dbc
    switch (PolyList[i]->SplitWithPlane(*Base, *Normal, FrontPoly, BackPoly, /*VeryPrecise*/0)) {
    //                                                          0xa8bf1, push 0 at 0xa8a9c → T=0.25
    // jump table @0xa901c = [0]=0xa8c07, [1]=0xa8c50, [2]=0xa8c36, [3]=0xa8c6a  (raw bytes read)
    case 0 /*Coplanar*/:   debugf(L"FilterBound: Got coplanar");        // 0xa8c0c
                           FrontList[nFront++] = PolyList[i];           // 0xa8c2d
                           BackList [nBack++]  = PolyList[i]; break;    // 0xa8c42
    case 1 /*Front*/:      FrontList[nFront++] = PolyList[i]; break;    // 0xa8c50
    case 2 /*Back*/:       BackList [nBack++]  = PolyList[i]; break;    // 0xa8c36 (tail of case-0 block)
    case 3 /*Split*/:                                                    // 0xa8c6a
        if (FrontPoly->NumVertices >= 14) {                             // 0xa8c6a: cmp [edi+0x1c0],0xe
            FPoly* Half = new(GMem) FPoly; FrontPoly->SplitInHalf(Half); // 0xa8c9b
            FrontList[nFront++] = Half; }
        FrontList[nFront++] = FrontPoly;                                // 0xa8ccb
        if (BackPoly->NumVertices >= 14) { …same…; BackList[nBack++] = Half; } // 0xa8cda..0xa8d1d
        BackList[nBack++] = BackPoly;                                   // 0xa8d3b
        FrontPoly = new(GMem) FPoly; BackPoly = new(GMem) FPoly; break; // 0xa8d4a/0xa8d6f
    default: GError->Logf(L"FZoneFilter::FilterToLeaf: Unknown split code"); // 0xa8d9a, str 0x100fed28
    }
}

if (nFront && nBack) {                                          // 0xa8dce/0xa8dd7
    FPoly Part = BuildInfiniteFPoly(Model, iNode);              // 0xa8df3 (ret-buf ebp-0x1dc)
    Part.iBrushPoly = iNode;                                    // 0xa8dfe: mov [ebp-0x14],esi
                                                                //   ( -0x14 = -0x1dc + 0x1c8 )
    SplitPartitioner(Model, PolyList, FrontList, BackList,
                     /*n*/0, nPolys, &nFront, &nBack, Part /*by value*/);  // 0xa8e39 → 0xaa000
} else {
    if (!nFront) debugf(L"FilterBound: Empty fronthull");       // 0xa8e4b, str 0x100fed84
    if (!nBack ) debugf(L"FilterBound: Empty backhull");        // 0xa8e6e, str 0x100fedc0
}

// IsCsg(node) ≡ (NumVertices/*byte +0x36*/ > 0) && !(NodeFlags/*+0x37*/ & 0x21)
//   0x21 = NF_IsNew(0x20) | NF_NotCsg(0x01)  — tested at 0xa8e9c/0xa8ea2 (and 3 more sites)
if (nFront > 0) {                                               // 0xa8e8c
    if (node.iChild[1] /*+0x24 = FRONT*/ != -1)                 // 0xa8e90
        FilterBound(Model, &Bound, iChild[1], FrontList, nFront,
                    Outside || IsCsg(node));                    // 0xa8ea8..0xa8ec2 (ecx=0/1)
    else if (Outside || IsCsg(node))
        UpdateBoundWithPolys(&Bound, FrontList, nFront);        // 0xa8ef4 → 0xaaa20   (AIR leaf)
    else
        UpdateConvolutionWithPolys(Model, iNode, FrontList, nFront); // 0xa8edc → 0xaaae0 (SOLID leaf)
}
if (nBack > 0) {                                                // 0xa8f0a
    if (node.iChild[0] /*+0x20 = BACK*/ != -1)                  // 0xa8f17
        FilterBound(Model, &Bound, iChild[0], BackList, nBack,
                    Outside && !IsCsg(node));                   // 0xa8f21..0xa8f4e (eax=0/1)
    else if (Outside && !IsCsg(node))
        UpdateBoundWithPolys(&Bound, BackList, nBack);          // 0xa8f68            (AIR leaf)
    else
        UpdateConvolutionWithPolys(Model, iNode, BackList, nBack);   // 0xa8f85       (SOLID leaf)
}

if (node.iRenderBound /*+0x30*/ == -1 &&                        // 0xa8fa0
    (node.iChild[1] != -1 || node.iChild[0] != -1)) {           // 0xa8fa6/0xa8fac — interior node only
    i = Model->Bounds.Add(1, 0x1c);                             // 0xa8fb2: FArray::Add(1,0x1c), ecx=&[ebx+0xc0]
    node.iRenderBound = i;                                      // 0xa8fc8: mov [edi+0x30],eax
    Bounds.Data[i] = Bound;                                     // 0xa8fcb..0xa8fde: FBox::operator=
                                                                //   dest = [ebx+0xc0] + i*0x1c (i*7 dwords)
}
if (ParentBound) *ParentBound += Bound;                         // 0xa8fe4..0xa8ff7: FBox::operator+=(FBox&)
Mark.Pop();                                                     // 0xa9003
```

**Semantics.** FilterBound pushes the closed hull of the *current region* (initially the whole
±32768 world cube) down the tree. At each node it splits the hull polys by the node plane
(T=0.25 band), closes the two child hulls by clipping the node's own infinite plane-polygon into
the hull (`SplitPartitioner`), and recurses. `Outside` tracks air/solid exactly like the CSG
filter (front child: `Outside || IsCsg`, back child: `Outside && !IsCsg` — same convention as
`sections/60`, FRONT in `iChild[1]`).

- **`Bounds[i]` (one FBox per *interior* node, indexed by `node.iRenderBound`)** = the AABB of
  all hull-polygon vertices of every **AIR (empty) leaf region** in the node's subtree
  (solid leaves contribute nothing; child boxes fold in via `*ParentBound += Bound`). Leaf nodes
  (both children -1) keep `iRenderBound = -1` — matches `DXOnly.dx` (`iRenderBound = 4,3,2,1,0,-1`).
- **`LeafHulls` runs (indexed by `node.iCollisionBound`)** = one run per **SOLID leaf region**,
  emitted on the node whose child side terminates solid (see 1.5).

### 1.4 `UpdateBoundWithPolys(FBox* Bound, FPoly** List, int n)` @0xaaa20

```c
for (i=0..n-1) for (j=0..List[i]->NumVertices-1)        // 0xaaa5a/0xaaa67: [eax+0x1c0]
    *Bound += List[i]->Vertex[j];                       // 0xaaa6f: (j+4)*12 = +0x30+j*12; FBox+=(FVector)
```
`FBox::operator+=(FVector)` (core.dll 0x18650): if `IsValid` (byte +0x18) → per-component
minss/maxss into Min(+0)/Max(+0xc); else Min=Max=v, IsValid=1.

### 1.5 `UpdateConvolutionWithPolys(Model, iNode, FPoly** List, int n)` @0xaaae0

```c
FBox Box(0);                                            // ebp-0x44
Nodes[iNode].iCollisionBound = Model->LeafHulls.Num;    // 0xaab29: eax=[Model+0xd0]; 0xaab2f: [node+0x2c]=eax
for (i=0..n-1) {
    t = List[i]->iBrushPoly;                            // 0xaab3f: esi=List[i]+0x1c8
    if (t != -1) {                                      // 0xaab4a
        // dedup: skip if any j<i has the same tag
        for (j=0..i-1) if (List[j]->iBrushPoly == t) goto skip;   // 0xaab51..0xaab61
        Model->LeafHulls.AddItem(t);                    // 0xaab66: TArray<INT>::AddItem @0x123e0, ecx=&[Model+0xcc]
    }
skip:
    for (j=0..NumVertices-1) Box += List[i]->Vertex[j]; // 0xaab75..0xaab98
}
Model->LeafHulls.AddItem(-1);                           // 0xaab9e/0xaabb4 (terminator)
LeafHulls.AddItem(bitcast<i32>(Box.Min.X));             // 0xaabb9  ([ebp-0x44])
LeafHulls.AddItem(Box.Min.Y); AddItem(Box.Min.Z);       // 0xaabc4/0xaabcf
LeafHulls.AddItem(Box.Max.X); AddItem(Box.Max.Y); AddItem(Box.Max.Z);  // 0xaabda..0xaabf6
```

**LeafHulls run format** (per solid leaf, starting at that node's `iCollisionBound`):
`[taggedNodeIndex...] , -1 , MinX,MinY,MinZ,MaxX,MaxY,MaxZ` — the node indices whose planes bound
the convex solid region (bit `0x40000000` set when the plane faces the *front* way, i.e. must be
flipped — see 1.6), then a -1 terminator, then the region's AABB as 6 raw f32 bit-patterns.
The 6 world-cube polys carry tag -1 and are never emitted (only their verts feed the box).
Cross-check vs `DXOnly.dx` (§50 §1.1): runs at 0,12,24,34,44,52 with total 60 = runs of
5+1+6 / 4+1+6 / 3+1+6 / 3+1+6 / 1+1+6 / 1+1+6 ✓. If BOTH sides of a node terminate solid, the
back-side call **overwrites** `iCollisionBound` (front block runs first at 0xa8e8c, back at
0xa8f0a) — faithful port must keep that order.

### 1.6 `SplitPartitioner(Model, PolyList, FrontList, BackList, n, nPolys, INT& nFront, INT& nBack, FPoly Part)` @0xaa000

```c
FPoly Front, Back;                                      // ctors 0xaa04f/0xaa055
for (; n < nPolys; n++) {                               // 0xaa064/0xaa139
    if (Part.NumVertices >= 14) {                       // 0xaa070: cmp [ebp+0x1e8],0xe  (+0x28+0x1c0)
        FPoly Half; Part.SplitInHalf(&Half);            // 0xaa08f
        SplitPartitioner(…, n, nPolys, …, Half);        // 0xaa0cb (recurse on the other half)
    }
    switch (Part.SplitWithPlane(PolyList[n]->Base, PolyList[n]->Normal, &Front, &Back, 0)) { // 0xaa0f7
    case 0 /*Coplanar*/: debugf(L"FilterBound: Got inficoplanar"); break;  // 0xaa123, str 0x100fec7c
    case 1 /*Front*/:    debugf(L"FilterBound: Got infifront"); return;    // 0xaa169, str 0x100fecb8
                         // entirely outside the hull -> nothing added to either list
    case 2 /*Back*/:     break;                          // falls to loop inc — keep whole Part
    case 3 /*Split*/:    Part = Back; break;             // 0xaa116: FPoly::operator=(&Back)
    }
}
FPoly* F = new(GMem) FPoly; *F = Part;                  // 0xaa14e..0xaa197
F->Reverse();                                           // 0xaa19f
F->iBrushPoly |= 0x40000000;                            // 0xaa1ab: or [esi+0x1c8],0x40000000
FrontList[(*nFront)++] = F;                             // 0xaa1c4/0xaa1c7
FPoly* B = new(GMem) FPoly; *B = Part;                  // 0xaa1cf..0xaa1ed  (tag stays = iNode)
BackList[(*nBack)++] = B;                               // 0xaa1fc/0xaa202
```
So the hull invariant is: every list poly faces **outward** from the region it bounds (region is
on each poly's BACK side). The partition fragment kept is the piece behind all current hull polys;
the front child gets it **reversed** with tag `iNode|0x40000000`, the back child gets it as-is
with tag `iNode`. Those tags are exactly what `UpdateConvolutionWithPolys` writes into
`LeafHulls` — i.e. **bit 30 in a LeafHulls plane entry = "use the node plane flipped"**.

### 1.7 `BuildInfiniteFPoly(FPoly* ret, Model, iNode)` @0xa7ae0

```c
Base   = Points [Surfs[node.iSurf].pBase  ];            // 0xa7b16..0xa7b43
Normal = Vectors[Surfs[node.iSurf].vNormal];
FVector A, B; Normal->FindBestAxisVectors(A /*ebp-0x30*/, B /*ebp-0x24*/);   // 0xa7b50
ret->FPoly(); ret->Init(); ret->NumVertices = 4;        // 0xa7b59..0xa7b6b
ret->Normal = *Normal; ret->Base = *Base;               // 0xa7b75../0xa7b86..
FVector Ax = A * 65536.0f, Bx = B * 65536.0f;           // 0xa7b9e: mulss by f32=65536 @0x100dea10 (WORLD_MAX)
ret->Vertex[0] = Base + Ax + Bx;                        // 0xa7c3f (+0x30)
ret->Vertex[1] = Base - Ax + Bx;                        // 0xa7cc8 (+0x3c)
ret->Vertex[2] = Base - Ax - Bx;                        // 0xa7d66 (+0x48)
ret->Vertex[3] = Base + Ax - Bx;                        // 0xa7df7 (+0x54)
```
(`iBrushPoly` is then stamped with `iNode` by the caller, FilterBound 0xa8dfe.)

### 1.8 FBox exactness notes (core.dll, byte-decoded)

- `FBox::FBox(int)` @0xa6a0: all six floats = 0, IsValid(+0x18) = 0.
- `operator+=(FVector)` @0x18650: valid → minss/maxss expand; invalid → Min=Max=point, IsValid=1.
- `operator+=(FBox&)` @0x185b0: **only if BOTH boxes valid** → expand; **otherwise `*this = Other`
  (full copy incl. IsValid)**. Quirk: a valid accumulated bound gets *replaced* by an invalid
  child bound (e.g. a subtree with no air leaves) — port must reproduce this, it is the original
  UE1 semantics and affects the serialized `Bounds` floats.
- Serialized FBox = 25 B (6×f32 + IsValid byte); mem stride 0x1c. A node whose subtree has no air
  leaf serializes an all-zero, IsValid=0 box.

### 1.9 REQUIRED vs nice-to-have

- **REQUIRED for a working native map: NONE of the bound arrays.** `iCollisionBound = iRenderBound
  = -1` + empty `Bounds`/`LeafHulls` is a legal, live-verified state (render guard
  `Render.dll 0x17adb` skips; collision falls back to the plane walk — §50 §0/§3, §10 §7.4).
- **REQUIRED if you emit ZoneMask via this path:** `BuildZoneMasks` (1.2) is load-bearing for
  zone-culled rendering — mask = OR of `1<<iZone[k]` (zone 0 contributes nothing) over node +
  children + iPlane chain. (For the single-zone fallback the spec's all-ones mask is the
  alternative; the editor's own output on a zoned map is what 1.2 computes.)
- **Nice-to-have (perf/bit-parity only):** the `Bounds` FBoxes (render frustum culling via
  `iRenderBound`) and `LeafHulls` runs (collision early-out via `iCollisionBound`). To reproduce
  bit-identical arrays you must port 1.3–1.8 float32-faithfully including the T=0.25
  SplitWithPlane band, the 14-vert SplitInHalf guard, the FBox += quirks, and the
  front-first/back-overwrites `iCollisionBound` order.

### 1.10 Open questions / low confidence

- `FPoly::Init` default field values (import into Engine.dll) were not disassembled; the code
  explicitly sets the fields it uses (`NumVertices`, `iBrushPoly`, Base/Normal/verts), so this
  only matters if `Fix()`/`SplitWithPlane` reads other FPoly fields of the world polys (they
  don't, per §10 §3 decode). LOW RISK.
- `SplitInHalf`'s exact split geometry was not re-decoded here (same routine §10 already cites).
- The case-2 (Back) branch of SplitPartitioner keeps `Part` unchanged — confirmed by the branch
  layout (`sub eax,2; jne` falls to the loop), not by observing a Back-returning run. MEDIUM-HIGH.

---

## ASSIGNMENT 2 — `NumZones` + `FZoneProperties Zones[64]` in UModel

### 2.1 In-memory layout (byte-proven from THREE independent sites)

| field | UModel offset | evidence |
|---|---|---|
| `NumSharedSides` (i32) | **+0xfc** | `UModel::Serialize` 0x101707b6: raw 4-byte serialize of `[esi+0xfc]`; `EmptyModel` 0x101700ab sets it to **4** |
| `NumZones` (i32) | **+0x100** | Serialize 0x101707c7 (raw 4 bytes of `[esi+0x100]`); zone-loop bound 0x101707e0 `cmp eax,[esi+0x100]`; editor pass C 0xa9552 `mov [eax+0x100],ecx`; EmptyModel 0x101700a1 `= 0` |
| `Zones[64]` (FZoneProperties, **0x18 = 24 B each**) | **+0x104** | Serialize loop 0x101707ec: `lea eax,[eax+eax*2]; lea eax,[eax*8+0x104]` (i*24+0x104); legacy path 0x10170743 copies 16+8 B to `[esi+i*24+0x104]`; EmptyModel loop 0x101700bf `lea esi,[ebx+eax*8]` with eax=z*3 |

FZoneProperties (0x18 bytes, from the per-zone serializer Engine 0x1010c240 and EmptyModel):

| field | offset in struct | absolute for zone z | serial form |
|---|---|---|---|
| `AZoneInfo* ZoneActor` | +0 | `+0x104 + z*0x18` | **compact-index obj-ref** (`Ar` vtable+0x18 at 0x1010c27b with the struct base) |
| *(4 B alignment pad)* | +4 | — | not serialized |
| `QWORD Connectivity` | +8 | `+0x10c + z*0x18` | raw u64 (0x1010c288: Serialize(Z+8, 8)) |
| `QWORD Visibility` | +0x10 | `+0x114 + z*0x18` | raw u64 (0x1010c296: Serialize(Z+0x10, 8)) |

**On-disk order** (modern path, ArVer > 0x3d=61; DX v68 qualifies — `UModel::Serialize`
Engine 0x1705a0): `Vectors, Points, Nodes, Surfs, Verts` (each via its TArray serializer,
0x10170788-0x101707b1), then `NumSharedSides` (i32), `NumZones` (i32), then `NumZones ×
FZoneProperties` (ci ZoneActor + u64 Connectivity + u64 Visibility), then `Polys` obj-ref (ci,
0x10170649), `LightMap`(+0xa8), `LightBits`(+0xb4), `Bounds`(+0xc0), `LeafHulls`(+0xcc),
`Leaves`(+0xd8), `Lights`(+0xe4) (0x10170820-0x10170878), then raw i32 `RootOutside`(+0xf0) and
`Linked`(+0xf4) (0x101708a5-0x101708c1).

**Python serializer cross-check** (`uedcli/native/umodel.py`): matches exactly — header comment
lines 14-15 (`i32 NumSharedSides, i32 NumZones` then `NumZones * FZoneProperties (ci ZoneActor +
16 raw bytes)`) and `write_model_body` lines 228-230
(`enc_i32(len(m.zones))` + `write_ci(z.actor_ref) + enc_u64(z.connectivity) +
enc_u64(z.visibility)`), parse side lines 401-407. **No change needed.**

### 2.2 Who writes each field (Editor.dll portalize passes; all byte-decoded)

**Init — `UModel::EmptyModel` (Engine 0x16ff10), at 0x101700a1-0x10170107:**
```c
NumZones = 0; NumSharedSides = 4;
for (z = 0..63) {
    Zones[z].ZoneActor    = NULL;                  // [esi+0x104] = 0
    Zones[z].Connectivity = 1ull << z;             // [esi+0x10c]/[+0x110] via bts/cmovae
    Zones[z].Visibility   = 0xffffffffffffffff;    // [esi+0x114]/[+0x118] = -1,-1
}
```
(EmptyModel also empties Bounds/LeafHulls/Leaves/Lights/LightMap/LightBits — elem sizes
0x1c/4/0x14/4/0x28/1 read from the Realloc pushes at 0x1016ff6f-0x1016fffe.)

**NumZones — pass C = `FEditorVisibility::FormZonesFromLeaves` @0xa93c0** (guard str 0x100fe6a0,
logs w"Found %i zones" @0x100fe6f0):
1. Walks the portal-fragment list at `this+0x10044` (next link at rec+0x1e4); for each record
   with `rec+0x1fc == -1` (a non-zone-portal boundary), merges the two adjacent leaves' zone ids:
   `A = Leaves[rec.iLeaf0/*+0x1d8*/].iZone, B = Leaves[rec.iLeaf1/*+0x1dc*/].iZone;`
   every leaf with iZone==A gets iZone=B (0xa9415-0xa9472; leaf stride 0x14, iZone at +0).
2. Renumbers the surviving equivalence classes densely 0..K-1 (0xa947a-0xa94ec).
3. `debugf(L"Found %i zones", K)` (0xa94ee).
4. **Every leaf: `iZone = (iZone % 63) + 1`** (0xa9509-0xa9539: `idiv [ebp-0x2c]=0x3f; inc edx`)
   — leaf zones live in 1..63; zone 0 is reserved for "outside/zoneless".
5. **`Model->NumZones = Clamp(K+1, 1, 64)`** (0xa953b-0xa9552: `inc edi; cmp edi,1 / mov ecx,0x40;
   cmovl ecx,edi; mov [eax+0x100],ecx`).

**Connectivity — pass F = `FEditorVisibility::BuildConnectivity` @0xa7960** (guard 0x100fe7a0):
```c
for (z = 0..63) Zones[z].Connectivity = 1ull << z;      // 0xa79be/0xa79c5: [Model + z*24 + 0x10c/0x110]
for (iNode = 0..Nodes.Num-1) {
    surf = Surfs[node.iSurf];
    if (surf.PolyFlags /*mem surf+4*/ & PF_Portal /*0x4000000, 0xa79f7*/) {
        a = node.iZone[0] /*+0x34*/, b = node.iZone[1] /*+0x35*/;
        Zones[b].Connectivity |= 1ull << a;             // 0xa7a00-0xa7a35
        Zones[a].Connectivity |= 1ull << b;             // 0xa7a3b-0xa7a76
    }
}
```
Real-map check (`zone_ground_truth.py 02_NYC_Bar.dx`): zone0 conn=0x1, zone1=0x6, zone2=0x6,
zone3=0x8 — exactly self-bit + portal neighbors. ✓

**Visibility — NEVER written by the visibility passes.** No write to +0x114/+z*0x18 exists
anywhere in 0xa6970..0xaa370 (grep over the full disasm of all passes). It keeps EmptyModel's
**0xffffffffffffffff**. Real maps confirm: every zone of `02_NYC_Bar.dx` and
`03_NYC_UNATCOHQ.dx` has vis=0xffffffffffffffff. → native build: emit all-ones.

**ZoneActor — pass G = `FEditorVisibility::BuildZoneInfo` @0xa7e60** (guard 0x100fe7f0;
slow-task w"Computing zones" @0x100fe834; summary log
w"BuildZoneInfo: %i ZoneInfo actors, %i duplicates, %i zoneless" @0x100fe870 at 0xa87df):
```c
for (z = 0..63) Zones[z].ZoneActor = NULL;              // 0xa7ec1-0xa7ed7: [Model + z*24 + 0x104] = 0
// 1) default every actor's Region:
for (actor in Level->Actors /* [this+0xc]+0x2c/+0x30 */)
    actor->Region /*+0x88..+0x90*/ = { Level->GetLevelInfo(), INDEX_NONE, 0 };  // 0xa7edb-0xa7f31
// 2) claim zones:
for (actor in Level->Actors) {                          // 0xa7f33
    zi = AsZoneInfo(actor);                             // call 0xa6930: actor iff class chain
                                                        //   contains AZoneInfo::StaticClass()
    if (!zi) continue;
    if (actor is-a ALevelInfo) continue;                // 0xa7f67-0xa7f8a: class-chain vs
                                                        //   ALevelInfo::StaticClass() -> skip
    FPointRegion R = Model->PointRegion(Level->GetLevelInfo(), actor->Location /*+0xd0*/);
                                                        // 0xa7f90-0xa7fcb (import 0x100ceaa4)
    actor->Region = R;                                  // 0xa7fd1-0xa7fe0
    if (R.ZoneNumber == 0)        { zoneless++; continue; }        // 0xa7fe6
    if (Zones[R.ZoneNumber].ZoneActor) { duplicates++; continue; } // 0xa8002 cmp [ecx+eax*8+0x104],0
    Zones[R.ZoneNumber].ZoneActor = actor;              // 0xa801f: mov [ecx+eax*8+0x104],edi
    assigned++;
    if ((actor->+0x2b0 & 3) == 3) { … 256-iteration SSE block … }   // see 2.3
}
// 3) for every actor: virtual call vtable+0xac (actor->SetZone(1,1)-style re-zone)  // 0xa87b4-0xa87d4
debugf(L"BuildZoneInfo: %i ZoneInfo actors, %i duplicates, %i zoneless", assigned, dup, zoneless);
```
**So `ZoneActor` = the first `ZoneInfo`-classed actor (EXCLUDING `LevelInfo`, which derives from
ZoneInfo) whose Location falls in that zone number per `UModel::PointRegion`; zones with no
ZoneInfo keep `NULL`** (serialized obj-ref 0 = None — matches real maps where most zones have
actor_ref=0). The LevelInfo is only the *runtime* Region default, never stored in `Zones[]`.

### 2.3 Open questions / low confidence (assignment 2)

- The `(actor+0x2b0 & 3) == 3` block in pass G (0xa8037-0xa840a, 256 iterations of ray/trace-like
  SSE math per claimed ZoneInfo) writes actor-side state only, not `Zones[]` — left undecoded;
  believed to be a v469-era ZoneInfo post-process (ambient/reverb probe?). LOW confidence on its
  purpose, HIGH confidence it does not touch the Model.
- Pass C's merge phase reads portal-fragment records built by passes A/B (`this+0x10044` list,
  fields +0x1d8/+0x1dc/+0x1fc/+0x1e4); the record struct is only partially mapped — enough for
  the zone layout question, NOT enough to port the flood itself (that's the known §8 residual).
- `NumZones = K+1` counts the implicit zone 0; leaf zones wrap at 63 (`% 63 + 1`), so a map with
  >63 real zones aliases zones — inherent engine behavior, reproduced as-is.
