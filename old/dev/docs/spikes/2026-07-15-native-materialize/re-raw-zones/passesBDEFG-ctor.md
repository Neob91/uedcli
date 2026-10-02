# RE: TestVisibility supporting zoning passes B, D, E, F, G + FEditorVisibility ctor

Editor.dll (UED22, ImageBase 0x10000000). All addresses are VAs (RVA = VA − 0x10000000).
Decoded 2026-07-16 by static disassembly (`adis.py`). Source-file provenance: the assert strings
in this cluster cite `C:\GameDev\UnrealTournament\Editor\Src\UnVisi.cpp` (read at 0x100fe394),
i.e. this IS the classic FEditorVisibility zoning machinery.

Legend: `this` = FEditorVisibility (esi/ebx/ecx per function); `Model` = `this+0x10`;
`Level` = `this+0xc`; node = FBspNode 0x40; leaf = FBspLeaf 0x14 (iZone @+0).

---

## 0. The FPortal record (0x200 bytes, FMemStack-allocated) — the shared data structure

Every pass below traffics in this record; pinning it first. Allocated in callback 0xa72a0 via
`FMemStack::PushBytes(0x200, 0x10)` on `GMem [0x100ce508]` (import 0x100ce530 =
`?PushBytes@FMemStack@@QAEPAEHH@Z`), constructed by **0xa6ab0**:

```
0x100a6ab9  call dword ptr [0x100cee94]        ; FPoly copy-ctor: record[0..0x1d8) = poly
0x100a6ac2  mov dword ptr [esi + 0x1d8], eax   ; iFrontLeaf  (arg +0xc)
0x100a6acb  mov dword ptr [esi + 0x1dc], eax   ; iBackLeaf   (arg +0x10)
0x100a6ad4  mov dword ptr [esi + 0x1e0], eax   ; iNode       (arg +0x14)
0x100a6add  mov dword ptr [esi + 0x1e4], eax   ; GlobalNext  (arg +0x18 = old this+0x10044)
0x100a6ae6  mov dword ptr [esi + 0x1e8], eax   ; FrontLeafNext (arg +0x20 = old this+0x10050[iFrontLeaf])
0x100a6aef  mov dword ptr [esi + 0x1ec], eax   ; BackLeafNext  (arg +0x24 = old this+0x10050[iBackLeaf])
0x100a6af8  mov dword ptr [esi + 0x1f0], eax   ; NodeNext    (arg +0x1c = old this+0x1004c[iNode])
0x100a6b00  mov word  ptr [esi + 0x1f4], 0     ; u16 flags/visit marks, zeroed
0x100a6b09  mov dword ptr [esi + 0x1f8], 0     ; zeroed (unknown use; likely pass-C scratch)
0x100a6b13  mov dword ptr [esi + 0x1fc], -1    ; iZoneSurf: -1 = plain portal; set by 0xa7870
```

| off | field | evidence |
|---|---|---|
| +0x000 | FPoly (0x1d8) of the portal fragment | copy-ctor above |
| +0x1d8 | `iFrontLeaf` | appErrorf text `"iLeaf==iFrontLeaf \|\| iLeaf==iBackLeaf"` (0x100fe444), UnVisi.cpp:0xe7/0xf8, checked against +0x1d8 first |
| +0x1dc | `iBackLeaf` | same assert |
| +0x1e0 | `iNode` the portal lies on | ctor |
| +0x1e4 | next in GLOBAL portal list (head `this+0x10044`) | 0xa7870 walks `ecx=[ecx+0x1e4]` from `[edx+0x10044]` |
| +0x1e8 | next in iFrontLeaf's per-leaf list | `FPortal::Next(iLeaf)` @0xa9b70: `ret [esi+0x1e8]` if `[esi+0x1d8]==iLeaf` else `[esi+0x1ec]` |
| +0x1ec | next in iBackLeaf's per-leaf list | same |
| +0x1f0 | next in per-node list (head `this+0x1004c[iNode]`) | ctor arg wiring in 0xa72a0 |
| +0x1f4 | u16, zero-init (visit/traversal marks for pass C) | ctor |
| +0x1f8 | i32, zero-init | ctor |
| +0x1fc | `iZoneSurf`: iSurf of the PF_Portal surf this fragment belongs to, else -1 | 0xa7870 write; pass G reads it |

Helper **0xa96a0 = FPortal::GetNeighborLeaf(iLeaf)** (thiscall on record): appErrorf
(UnVisi.cpp line 0xe7) unless `iLeaf ∈ {iFrontLeaf, iBackLeaf}`; returns the OTHER one:
`0x100a96d8 cmp eax,edi / jne → ret [esi+0x1d8]; else ret [esi+0x1dc]`.

Helper **0xa9b70 = FPortal::Next(iLeaf)** (thiscall): same assert (line 0xf8); returns
`+0x1e8` if `iLeaf==iFrontLeaf` else `+0x1ec` — the per-leaf chain step.

---

## 1. Ctor 0xa6970 — `FEditorVisibility::FEditorVisibility(ULevel*, UModel*, INT A)`

Role: memberwise init of the ~0x10060-byte stack object; no Model/Level writes.

Field map (every write, quoted where non-obvious):

| this+off | init | meaning |
|---|---|---|
| +0x00..0x0b | FMemMark on `GMem`: `+0 = &GMem`, `+4 = [GMem+0]`, `+8 = [GMem+0xc]` (`0x100a699b..0x100a69b0`) | mem-stack mark; dtor 0xa6c70 pops it (frees ALL FPortal records + the +0x1004c/50/54 arrays) |
| +0x0c | arg1 `Level` | `mov eax,[ebp+8]; mov [ecx+0xc],eax` |
| +0x10 | arg2 `Model` | `mov eax,[ebp+0xc]; mov [ecx+0x10],eax` |
| +0x14 .. +0x10013 | NOT initialized | **the node-path stack**: 0x4000 u32 entries; entry = ancestor iNode, bit 0x40000000 = "descended the BACK (+0x20) child". Pushed/popped by pass B; depth = +0x1001c. This maps the brief's "middle ~0x10000 bytes". |
| +0x10014 | 0 | portal count ("%i portals") — inc'd in 0xa72a0 |
| +0x10018 | NOT initialized | (never seen touched in this cluster) |
| +0x1001c | 0 | path-stack depth (see +0x14) |
| +0x10020, +0x10024, +0x10028, +0x1002c, +0x10030 | 0 | counters/scratch not touched by B/D/E/F/G (likely pass C / light passes) |
| +0x10034 | 0 | zone-portal count ("%i zone portals") — inc'd in pass B |
| +0x10038 | 0 | fragment count ("(%i fragments)") — inc'd in 0xa7870 |
| +0x1003c | arg3 `A` | `mov eax,[ebp+0x10]; mov [ecx+0x1003c],eax` |
| +0x10040 | NOT initialized | scratch: "current zone-portal iSurf" (written by pass B before each marking filter, read by 0xa7870) |
| +0x10044 | 0 | global FPortal list head |
| +0x10048 | 0 | (untouched in this cluster) |
| +0x1004c | 0 | → per-NODE FPortal list heads, FMemStack array of `2*Nodes.Num+0x100` u32 (alloc'd in portalize step 6; doubled size = headroom for nodes added by pass D fragments) |
| +0x10050 | 0 | → per-LEAF FPortal list heads (`Leaves.Num` u32); chains via record +0x1e8/+0x1ec |

Returns `this`. No other writes. (+0x10054, the second per-leaf array, is only alloc'd/zeroed
by portalize itself, not the ctor.)

---

## 2. Pass B — 0xa9750 `MakePortalsAndMarkZonePortals(this; INT iNode)` (thiscall, recursive; entry `(this, 0)`)

**Role:** for every BSP node, generate the **portal set** (FPortal records connecting leaf pairs
across the node plane), and mark which portals are **zone portals** (lie on a PF_Portal surf),
counting `this+0x10014` / `+0x10034` / `+0x10038`.

```
Pass_B(iNode):                                            # this = ebx
  # (1) whole-plane portal for this node's plane
  FPoly quad = BuildPlaneQuad_0xa7ae0(Model, iNode)       # ±65536-unit square on node plane
  ClipToCellAndFilter_0xa9970(this; iNode, quad, 0, cb=0xa72a0)
      #  clips quad by every ancestor on the path stack (this+0x14[0..depth)),
      #  then filters it down iNode's back then front subtree; every surviving
      #  fragment connecting (frontLeaf, backLeaf) => new FPortal (cb 0xa72a0)
  # (2) recurse, recording the path
  n = Nodes[iNode]
  if n.iChild[1](+0x24) != -1:                            # FRONT side, plain entry
      stack[depth++] = iNode;              Pass_B(n.iChild[1]); depth--
  if n.iChild[0](+0x20) != -1:                            # BACK side, flagged entry
      stack[depth++] = iNode | 0x40000000; Pass_B(n.iChild[0]); depth--
  # (3) zone-portal marking, AFTER the whole subtree is portalized
  for i = iNode; i != -1; i = Nodes[i].iPlane:            # coplanar chain incl. self
      if Surfs[Nodes[i].iSurf].PolyFlags & PF_Portal(0x4000000):
          if GEditor->bspNodeToFPoly(Model, i, &poly):    # vtbl+0x1f8; 0 => degenerate, skip
              this+0x10034 ++                             # ZONE-PORTAL COUNT
              this+0x10040 = Nodes[i].iSurf               # scratch for the callback
              FilterThroughSubtrees_0xa9030(this; 0, i, iNode,
                    Nodes[iNode].iLeaf[0](+0x38), Nodes[iNode].iChild[0](+0x20),
                    poly, cb=0xa7870, -1)
```

Persistent writes (all via callbacks, itemized in §2.3/§2.4): FPortal records + the three list
head stores + the three counters. Pass B itself writes only `this+0x14[]`/`+0x1001c` (path
stack), `+0x10034`, `+0x10040`.

Evidence for the load-bearing lines:
```
0x100a97e1  cmp dword ptr [eax+edi+0x24], -1        ; front child exists?
0x100a97ee  mov [ebx+eax*4+0x14], esi               ; stack[depth] = iNode (plain)
0x100a97f2  inc dword ptr [ebx+0x1001c]             ; depth++
0x100a981e  or  ecx, 0x40000000                      ; back-side flag
0x100a9870  test dword ptr [eax+4], 0x4000000        ; Surf.PolyFlags & PF_Portal (surf+4 = PolyFlags)
0x100a9890  call dword ptr [eax+0x1f8]               ; GEditor->bspNodeToFPoly(Model, i, &poly)
0x100a98a0  inc eax / mov [ebx+0x10034], eax         ; zone-portal count++
0x100a98aa  mov [ebx+0x10040], eax                   ; = Nodes[i].iSurf
0x100a98f3  mov esi, [edi+0x28]                      ; chain next (iPlane)
```
(Also confirms **FBspSurf.PolyFlags @ mem +0x04** — the `[eax+4]` test above, surf base
`Surfs.Data + iSurf*0x40`.)

### 2.1 Helper 0xa7ae0 — `BuildPlaneQuad(FPoly* out, UModel*, INT iNode)`

Builds a huge square lying on the node's plane: `surf = Surfs[node.iSurf]`;
`Base = Points[surf.pBase(+0x08)]`, `Normal = Vectors[surf.vNormal(+0x0c)]`
(`0x100a7b2e mov eax,[ecx+8]` / `0x100a7b3a mov eax,[ecx+0xc]`);
`Normal.FindBestAxisVectors(A1, A2)` (import 0x100ce264); FPoly default-ctor + `FPoly::Init`
(imports 0x100ceea4/0x100ceea0); then:
```
out.NumVertices = 4        ; 0x100a7b6b mov dword ptr [ecx+0x1c0], 4
out.Normal = Normal        ; +0xc..0x14
out.Base   = Base          ; +0..8
A1 *= 65536; A2 *= 65536   ; 0x100a7b9e movss xmm0,[0x100dea10] ; f32=65536
Vertex[0](+0x30) = Base + A1 + A2
Vertex[1](+0x3c) = Base - A1 + A2
Vertex[2](+0x48) = Base - A1 - A2
Vertex[3](+0x54) = Base + A1 - A2
```
No persistent writes (fills the caller's FPoly only). Note winding: (+A1+A2, −A1+A2, −A1−A2,
+A1−A2) with normal = surf normal.

### 2.2 Helper 0xa9970 — `ClipToCellAndFilter(this; INT iNode, FPoly ByVal, INT iDepthStart, void* cb)` (ret 0x1e4)

Clips the plane-quad to the node's convex cell using the recorded ancestor path, then hands it
to the leaf-pair filter:

```
for s = iDepthStart; s < depth(this+0x1001c); s++:
    iAncestor = stack[s] & ~0x40000000        ; 0x100a99dc/0x100a99e0
    if poly.NumVertices >= 14:                ; 0x100a99e6 cmp [ebp+0x1cc], 0xe / jl
        poly.SplitInHalf(&half)               ; import 0x100cee40
        recurse 0xa9970(this; iNode, half, s, cb)      # continue the OTHER half from depth s
    r = poly.SplitWithNode(Model, iAncestor, &Front, &Back, 1)   ; import 0x100ceaa8, VeryPrecise=1
    flag = stack[s] & 0x40000000
    r==0 (coplanar)        -> DISCARD (return)
    r==1 (front): flag set -> DISCARD; clear -> keep poly
    r==2 (back):  flag set -> keep poly;  clear -> DISCARD
    r==3 (split): poly = flag ? Back : Front  ; 0x100a9a95 test ecx,ecx / cmove eax,edx; op= 0x100cee28
# survived every ancestor: seed the two-phase filter on iNode itself
FilterThroughSubtrees_0xa9030(this; 0, iNode, iNode,
      Nodes[iNode].iLeaf[0], Nodes[iNode].iChild[0], poly, cb, -1)
      ; 0x100a9b08 push [esi+0x20] / 0x100a9b0b push [esi+0x38] / 0x100a9b10 push 0
```
No persistent writes of its own.

### 2.3 Core 0xa9030 — `FilterThroughSubtrees(this; INT Phase, INT iSrcNode, INT iOrigNode, INT iLeaf, INT iNode, FPoly ByVal, void* cb, INT iOtherLeaf)` (ret 0x1f4)

The leaf-pair filter both B and D use. Iterative descent from `iNode` (arg5) with `iLeaf`
(arg4) tracking the leaf of the current side; FPoly at `[ebp+0x1c]`, `cb` at `[ebp+0x1f4]`,
`iOtherLeaf` at `[ebp+0x1f8]`.

```
while iNode != -1:
    if poly.NumVertices > 14: SplitInHalf; recurse(this; Phase, iSrcNode, iOrigNode, iLeaf, iNode, half, cb, iOtherLeaf)
    r = poly.SplitWithNode(Model, iNode, &Front, &Back, 1)      ; 0x100a9123 call [0x100ceaa8]
    if r==1 or r==3:
        recurse(this; Phase, iSrcNode, iOrigNode,
                Nodes[iNode].iLeaf[1](+0x3c), Nodes[iNode].iChild[1](+0x24),   # FRONT side
                (r==1 ? poly : Front), cb, iOtherLeaf)          ; 0x100a916c push [esi+0x24] / 0x100a916f push [esi+0x3c]
    if r==2 or r==3:
        if r==3: poly = Back                                    ; 0x100a91a6 call [0x100cee28]
        iLeaf = Nodes[iNode].iLeaf[0](+0x38); iNode = Nodes[iNode].iChild[0](+0x20)   # tail-iterate BACK
        ; 0x100a91b2 mov ebx,[eax+edi+0x38] / 0x100a91b6 mov edi,[eax+edi+0x20]
    if r==0: return                                             # coplanar fragment DISCARDED
# iNode == -1: reached a leaf-side; iLeaf = that side's leaf index (may be -1 = solid)
if Phase == 0:
    # fragment survived the BACK subtree of iOrigNode, landing in back-leaf `iLeaf`;
    # now push it down the FRONT subtree, remembering the back leaf in iOtherLeaf:
    recurse(this; 1, iSrcNode, iOrigNode,
            Nodes[iOrigNode].iLeaf[1](+0x3c), Nodes[iOrigNode].iChild[1](+0x24),
            poly, cb, iLeaf)                                    ; 0x100a91f1 push [esi+0x24] / [esi+0x3c] ... 0x100a91d8 push ebx (=iOtherLeaf slot)
else:
    cb(this; &poly, iLeaf /*front leaf*/, iOtherLeaf /*back leaf*/, iSrcNode, iOrigNode)
    ; 0x100a9220 call dword ptr [ebp-0x5a4]
```
So: **every maximal fragment of the input poly that separates back-leaf LB from front-leaf LF
invokes `cb(poly, LF, LB, iSrcNode, iOrigNode)`** (either leaf may be -1 = solid side). No
persistent writes of its own.

### 2.4 Callback 0xa72a0 (pass B phase: portal creation) — writes THE portal set

Args `(this; FPoly* poly, INT iFrontLeaf, INT iBackLeaf, INT iNode, INT iOrigNode)`:
```
if iFrontLeaf==-1 or iBackLeaf==-1: return                 ; 0x100a72da/0x100a72e3 cmp,-1
rec = GMem.PushBytes(0x200, 0x10)                          ; 0x100a72ee push 0x10/0x200; call [0x100ce530]
rec = FPortal_ctor_0xa6ab0(rec; poly, iFrontLeaf, iBackLeaf, iNode,
        this+0x10044, this+0x1004c[iNode], this+0x10050[iFrontLeaf], this+0x10050[iBackLeaf])
this+0x1004c[iNode]      = rec                             ; 0x100a737b mov [edx+eax], ecx
this+0x10050[iFrontLeaf] = rec                             ; 0x100a7387
this+0x10050[iBackLeaf]  = rec                             ; 0x100a7393
this+0x10044             = rec  (global head)              ; 0x100a7396
this+0x10014 ++            # PORTAL COUNT                  ; 0x100a739c..0x100a73a3
```
(If PushBytes returns NULL — practically impossible — the same stores happen with rec=0,
truncating the lists; the count still increments.)

### 2.5 Callback 0xa7870 (pass B phase: zone-portal marking)

Args `(this; FPoly* poly, INT iFrontLeaf, INT iBackLeaf, ...)` — walks the GLOBAL portal list
and stamps every portal joining this exact leaf pair (either orientation):
```
if iFrontLeaf==-1 or iBackLeaf==-1: return
for rec = this+0x10044; rec; rec = rec->GlobalNext(+0x1e4):     ; 0x100a78fb
    if {rec.iFrontLeaf, rec.iBackLeaf} == {iFrontLeaf, iBackLeaf}:   ; 0x100a78c4..0x100a78e0 both orders
        rec.iZoneSurf(+0x1fc) = this+0x10040                    ; 0x100a78e8 (the PF_Portal surf)
        this+0x10038 ++          # FRAGMENT COUNT               ; 0x100a78ee..0x100a78f5
```
Note: it does NOT stop at the first match — every portal on that leaf pair gets stamped, and
the fragment counter increments once per (fragment × matching record).

**Pass B summary of persistent state produced:** the FPortal graph (records + heads
`this+0x10044/0x1004c[]/0x10050[]`), `this+0x10014` (# portals), `this+0x10034` (# PF_Portal
node polys successfully converted = "zone portals"), `this+0x10038` (# leaf-pair fragment
matches = "fragments"), `rec.iZoneSurf` on zone portals. **No Model/node/leaf writes at all** —
pass C (0xa93c0, not in this assignment) reads this graph to flood zones into `Leaves[].iZone`.

---

## 3. Pass D — 0xa7400 `AssignNodeZonePairs(this; INT iNode, INT Outside)` (thiscall, recursive; entry `(this, 0, Model->+0xf0)`)

**Role:** now that leaves have zones (pass C), stamp **every node's `iZone[2]`** by refiltering
each node's polygon through the tree; where one node face straddles multiple zone pairs, split
it into per-zone-pair fragment nodes.

```
Pass_D(iNode, Outside):
  n = Nodes[iNode]
  if n.iChild[1](+0x24) != -1: Pass_D(n.iChild[1], Outside || n.IsCsg(4))
  if n.iChild[0](+0x20) != -1: Pass_D(n.iChild[0], Outside && !n.IsCsg(4))
  for i = iNode; i != -1; i = Nodes[i].iPlane(+0x28):        # coplanar chain incl. self
      FPoly poly;                                             # default-ctor 0x100ceea4
      if Nodes[i].NodeFlags(+0x37) & 0x20 (NF_IsNew): continue   # skip fragments we added
      if !GEditor->bspNodeToFPoly(Model, i, &poly): continue     # vtbl+0x1f8
      OldNum = Nodes.Num
      FilterThroughSubtrees_0xa9030(this; 0, i, iNode,
            Nodes[iNode].iLeaf[0], Nodes[iNode].iChild[0], poly, cb=0xaa220, -1)
      if Nodes.Num > OldNum:               # the callback added fragment nodes
          BYTE zone[2] = {0,0}
          for j in [OldNum..Nodes.Num), k in 0..1:
              if Nodes[j].iZone[k](+0x34+k) != 0: zone[k] = Nodes[j].iZone[k]   # last nonzero wins
          Match = for all j,k: Nodes[j].iZone[k]==0 or Nodes[j].iZone[k]==zone[k]
          if Match:
              for j in [OldNum..Nodes.Num): Nodes[j].NumVertices(+0x36) = 0    # kill fragments
              Nodes[iNode].iZone[0..1] = zone[0..1]                            # stamp ORIGINAL node
          else:
              Nodes[iNode].NumVertices(+0x36) = 0                              # kill original poly
              for j in [OldNum..Nodes.Num):
                  if Nodes[j].iZone[0]==0 and Nodes[j].iZone[1]==0:
                      Nodes[j].NumVertices = 0                                 # kill zoneless fragments
```

⚠ note the stamping target: the reconciliation always writes **`Nodes[iNode]`** — the chain
HEAD whose subtree we filtered through — even when the poly came from chain node `i`
(`0x100a766b mov ebx,[ebp-0x1f4]` = iNode<<6, used for both the `+0x36` zero at `0x100a769a`
and the `+0x34+k` stores at `0x100a7693`). Since all chain members share the plane and the
fragments' zones come from the same leaf set, head/chain agree in the Match case; in the
mismatch case the HEAD's poly is the one zeroed. (Faithful port must replicate exactly this.)

`IsCsg` helper **0x10033b80** (thiscall on node, arg ExtraFlags):
```
0x10033b83  cmp byte ptr [ecx+0x36], 0 ; NumVertices > 0 ?
0x10033b8c  or  al, 0x21               ; ExtraFlags | NF_NotCsg(0x01) | NF_IsNew(0x20)
0x10033b8e  test byte ptr [ecx+0x37], al ; NodeFlags
```
→ `IsCsg(E) = NumVertices>0 && !(NodeFlags & (E|0x21))`. Pass D calls it with `E=4`
(`0x100a7469 push 4`) → effective mask 0x25 (0x04 is the portal/invisible-derived NF bit).
Outside propagation evidence: front `0x100a7465 test esi,esi / jne push1` + `jne push1` after
IsCsg; back `0x100a74b7 je push0` + IsCsg nonzero → 0. The Outside value is ONLY passed down
(never used in the node's own processing here).

### 3.1 Callback 0xaa220 (pass D) — adds a zone-stamped fragment node

Args `(this; FPoly* poly, INT iFrontLeaf, INT iBackLeaf, INT iSrcNode, INT iOrigNode)`:
```
iNew = GEditor->bspAddNode(Model, iSrcNode, NODE_Plane(2),
                           Nodes[iSrcNode].NodeFlags | 0x20 (NF_IsNew), poly)
       ; 0x100aa276 or eax,0x20 ; 0x100aa27a push 2 ; 0x100aa27e call [edx+0x224]
       ;   (GEditor vtbl+0x224 == 0x10034e80 == bspAddNode — read from the vtable at
       ;    file-off 0xce038; +0x214=0x355e0 bspBrushCSG and +0x218=0x36870 bspOptGeom check out)
side = ( dot(Nodes[iOrigNode].Plane.Normal, poly.Normal) < 0 ) ? 1 : 0
       ; 0x100aa298..0x100aa2c8: plane at [Nodes+iOrig*64+0..8], poly normal at [poly+0xc..0x14],
       ;   comiss xmm0(=0),xmm1 / seta dl
Nodes[iNew].iZone[side]   = (iBackLeaf ==-1) ? 0 : Leaves[iBackLeaf].iZone
       ; 0x100aa2dd mov eax,[eax+0xd8]; 0x100aa2e3 mov ecx,[eax+ecx*4]  (leaf stride 0x14: lea ecx,[eax+eax*4])
       ; 0x100aa2ee mov byte ptr [eax+edx+0x34], cl
Nodes[iNew].iZone[side^1] = (iFrontLeaf==-1) ? 0 : Leaves[iFrontLeaf].iZone
       ; 0x100aa310 xor edx,1 ; 0x100aa316 mov byte ptr [edx+esi+0x34], cl
```
So the fragment is chained as an NF_IsNew coplanar node under `iSrcNode`, its iZone pair =
(zone of back-descent leaf, zone of front-descent leaf), swapped when the fragment poly's
normal opposes the ORIGINAL node's plane normal. Solid sides (leaf −1) give zone 0.
(bspAddNode itself also appends Surfs/Verts/Points as usual — pass D can therefore grow
`Verts`/`Points` too, and `NumZones`-adjacent arrays are untouched.)

**Pass D summary of persistent state produced:** `Nodes[*].iZone[0..1]` for every non-NF_IsNew
node (bytes +0x34/+0x35); NEW NF_IsNew coplanar nodes for zone-straddling faces (via
bspAddNode, with iZone set, immediately `NumVertices=0`-killed unless the zones disagreed);
`NumVertices=0` zeroing per the Match logic above. Runs before `bspCleanup`/`bspRefresh`
(portalize step 10), which then GCs the zeroed/unreachable fragments.

---

## 4. Pass E — 0xa8850 `BuildZoneMasks(UModel*, INT iNode)` (cdecl, recursive; entry `(Model, 0)`; returns u64 in edx:eax)

**Role:** bottom-up OR of zone bits into every node's `ZoneMask`.

```
u64 mask = 0
if n.iZone[0](+0x34) != 0: mask |= 1u64 << n.iZone[0]      ; 0x100a8896/0x100a88a4 bts + cmovae (u64 shift)
if n.iZone[1](+0x35) != 0: mask |= 1u64 << n.iZone[1]      ; 0x100a88c3..
if n.iChild[1](+0x24) != -1: mask |= Pass_E(Model, n.iChild[1])   ; 0x100a88ef
if n.iChild[0](+0x20) != -1: mask |= Pass_E(Model, n.iChild[0])   ; 0x100a890b
if n.iPlane   (+0x28) != -1: mask |= Pass_E(Model, n.iPlane)      ; 0x100a8929
n.ZoneMask(+0x10, u64) = mask                              ; 0x100a8947 mov [ebx+0x10],esi / 0x100a894a mov [ebx+0x14],edi
return mask
```
**Zone 0 contributes NO bit** (the `test al,al / je` guards). So a fully-zone-0 subtree gets
`ZoneMask == 0`, not all-ones — the single-zone fallback's all-ones mask is the *conservative*
variant, not what the editor writes. Only write: `Nodes[*].ZoneMask`.

---

## 5. Pass F — 0xa7960 `BuildConnectivity(this)` (thiscall)

**Role:** fill per-zone `Connectivity` u64s from portal nodes' zone pairs.

Zones array layout pinned by this pass + pass G: `Model+0x100` = NumZones (untouched here),
`Model+0x104` = `FZoneProperties Zones[64]`, elem stride 0x18 (24) — `lea ecx,[edi+edi*2]` +
`*8`. Elem: `+0 ZoneActor` (written by pass G at `Model+0x104+24i`), `+4 pad`,
`+8 Connectivity u64` (this pass, `Model+0x10c+24i`), `+0x10 Visibility u64` (by elimination —
NOT written by any pass in this assignment; presumably pass C or the light pass fills it).

```
for i in 0..63:
    Zones[i].Connectivity = 1u64 << i          ; 0x100a79be mov [eax+ecx*8+0x10c],edx / 0x100a79c5 [..+0x110],esi
for each node (0..Nodes.Num):
    if Surfs[node.iSurf].PolyFlags & PF_Portal(0x4000000):    ; 0x100a79f7 test [ecx+4], 0x4000000
        a = node.iZone[0](+0x34); b = node.iZone[1](+0x35)
        Zones[b].Connectivity |= 1u64 << a     ; 0x100a7a00 movzx from +0x35 selects elem; bts on +0x34 value; or into +0x10c/+0x110
        Zones[a].Connectivity |= 1u64 << b     ; 0x100a7a3b mirror
```
Only writes: `Zones[0..63].Connectivity` (all 64, regardless of NumZones). Requires pass D's
node iZone stamps — hence its position after D in the pipeline. Note zone 0 IS included here
(no zero-guard): a portal node with iZone {0,z} sets `Zones[0].Conn |= 1<<z` etc.

---

## 6. Pass G — 0xa7e60 `BuildZoneInfo(this)` (thiscall)

**Role:** bind actors to the new zones: claim `Zones[i].ZoneActor` from ZoneInfo actors,
recompute every actor's `Region`, set up reverb + warp-zone data. GWarn StatusUpdatef
`"Computing zones"` (0x100fe834); final log
`debugf("BuildZoneInfo: %i ZoneInfo actors, %i duplicates, %i zoneless", nClaimed, nDup, nZoneless)`
(0x100fe870, `0x100a87df push 0x100fe870`).

```
for i in 0..63: Zones[i].ZoneActor = 0            ; 0x100a7ecf mov [eax+ecx*8+0x104], edi(0)
# reset every actor's Region:
for each Level.Actors[i] != 0:                    ; Actors.Data @Level+0x2c, Num @+0x30
    actor.Region(+0x88) = FPointRegion{ Zone = Level->GetLevelInfo(),  ; import 0x100cecf8
                                        iLeaf = -1, ZoneNumber = 0 }
    ; 0x100a7f1c movq [ecx+0x88],xmm0 ({LevelInfo,-1}) ; 0x100a7f2a mov [ecx+0x90],0
# per-ZoneInfo work:
for each actor in Level.Actors:
    zi = Cast<AZoneInfo>(actor)                   ; 0xa6930: IsA walk vs AZoneInfo::StaticClass [0x100ceaa0];
    if !zi: continue                              ;   class @obj+0x24, super chain via [class+0x28]
    if zi->IsA(ALevelInfo::StaticClass [0x100cee00]): continue     # skip the LevelInfo itself
    zi.Region = Model->PointRegion(LevelInfo, zi.Location(+0xd0))  ; import 0x100ceaa4; result -> +0x88/+0x8c/+0x90
    if zi.Region.ZoneNumber(+0x90 byte) == 0: nZoneless++; continue
    if Zones[Z].ZoneActor != 0:                   ; 0x100a8002 cmp [ecx+eax*8+0x104], 0
        nDup++; continue
    nClaimed++; Zones[Z].ZoneActor = zi           ; 0x100a801f mov [ecx+eax*8+0x104], edi
    if (zi+0x2b0 & 3) == 3:                       ; 0x100a802c and eax,3 / cmp al,3 — two bools (bReverbZone|bRaytraceReverb, low-conf names)
        <reverb raytrace block — see below>
    if zi->IsA(AWarpZoneInfo::StaticClass [0x100cea9c]):
        <warp-zone setup — see below>
# finally:
for each actor != 0: actor->vtbl[+0xac](1, 1)     ; 0x100a87ca — re-links the actor into its zone
                                                  ;   (AActor vtable slot; SetZone-like, not chased)
debugf("BuildZoneInfo: ...", nClaimed, nDup, nZoneless)
```

**Reverb block** (0x100a8037..0x100a8407; writes ACTOR properties only): fires 256 rays
(`0x100a8048 cmp esi,0x100`) from `zi.Location` in directions from 0xaac50 (VRand-like) scaled
by 16384 (`0x100a80bb movss xmm3,[0x100feef0] ; f32=16384`), each through
`Model->vtbl[+0x58]` (a LineCheck-style trace), logging `"   dist=%f"` (0x100fe854); collects
`{hitTime*16384 / zi+0x2b4 (f32, SpeedOfSound-like), 1.0, 0}` triples into a TArray
(0x10003650 add), then greedily merges the closest pair until ≤ 6 entries
(`0x100a81a4 cmp edx,6`; weighted average `(d1*w1+d2*w2)/(w1+w2)`, RemoveItem 0x10045c40),
sorts descending by first component, and stores clamped BYTE values to
`zi+0x2c0[i]` (from the merged distance value) and `zi+0x2c6[i]` (from `weight * <consts>`),
i = 0..count-1 (`0x100a83ba mov [esi+edi+0x2c0],al`, `0x100a83e8 mov [esi+edi+0x2c6],al`).
These are the AZoneInfo `Delay[6]` / `Gain[6]` reverb arrays (📖 names inferred from the UT
AZoneInfo property set; offsets are the hard data). Irrelevant to Model state.

**Warp-zone block** (0x100a8431..0x100a879d; writes ACTOR properties only):
```
iLeaf = zi.Region.iLeaf(+0x8c); if -1: skip
rec = this+0x10050[iLeaf]                          ; 0x100a8440 — the leaf's FPortal list head
if !rec or rec.iZoneSurf(+0x1fc) == -1: skip       ; 0x100a8454
FBox box(0) [0x100ce4dc]
for every node with node.iSurf == rec.iZoneSurf:   ; 0x100a8487/0x100a848e
    for v in node verts (iVertPool +0x18, NumVertices +0x36):
        box += Points[Verts[v].iVertex]            ; FBox::operator+= [0x100ce4d8]
mid = (box.Min + box.Max) * 0.5                    ; 0x100a84f5 f32=0.5
origin = mid - rec.Normal(+0xc) * dot(rec.Normal, mid - rec.Vertex[0](+0x30))   # project onto portal plane
surf = Surfs[rec.iZoneSurf]
zi+0x37c        = Leaves[ rec.GetNeighborLeaf(iLeaf) /0xa96a0/ ].iZone   # the OTHER side's zone
zi+0x380..0x388 = origin                                    # FCoords.Origin
zi+0x38c..0x394 = Vectors[surf.vTextureU(+0x10)].SafeNormal()   # XAxis  [0x100ce4ac]
zi+0x398..0x3a0 = Vectors[surf.vTextureV(+0x14)].SafeNormal()   # YAxis
zi+0x3a4..0x3ac = Vectors[surf.vNormal(+0x0c)].SafeNormal()     # ZAxis
```
(AWarpZoneInfo: int-then-FCoords at +0x37c/+0x380 — WarpCoords + the destination zone index;
📖 field names inferred, offsets hard.)

**Pass G summary of persistent state produced:** `Model.Zones[0..63].ZoneActor`
(zeroed then claimed; `Model+0x104+24i`); every actor's `Region` (+0x88 Zone ptr, +0x8c iLeaf,
+0x90 ZoneNumber — via PointRegion for ZoneInfos, default {LevelInfo,-1,0} reset for all, then
the per-actor vtbl+0xac(1,1) call re-registers each actor); ZoneInfo reverb bytes
(+0x2c0[6]/+0x2c6[6]); WarpZoneInfo warp frame (+0x37c..+0x3ac). It does NOT write NumZones,
Connectivity, Visibility, nodes, or leaves.

---

## 7. Open questions / low-confidence

1. **`Zones[i].Visibility` (Model+0x114+24i) is written by NONE of B/D/E/F/G** — must come from
   pass C (0xa93c0) or the per-light pass 0xa6d00. Same for `NumZones` (Model+0x100). Flagging
   for whoever owns those decodes.
2. `this+0x10018/+0x10020..+0x10030/+0x10048` and record`+0x1f4/+0x1f8`: untouched in this
   cluster; presumed pass-C/light-pass scratch. Not needed for B/D/E/F/G ports.
3. Pass D's `Outside` parameter is computed and propagated but never consumed inside this
   function — either it's vestigial or consumed via a side effect I did not see (I saw none).
   Low risk; port faithfully anyway.
4. Reverb-block names (`SpeedOfSound`@+0x2b4, `Delay/Gain`@+0x2c0/+0x2c6, gate bools @+0x2b0
   bits 0..1) and `Location`@actor+0xd0 are 📖 inferred from the UT property set; the offsets
   and arithmetic are hard. The exact byte-quantization constants of the Gain path
   (`[0x100feee8]/[0x100fe190]/[0x100de948]` doubles) were not chased — irrelevant to Model
   output parity (they only shape sound properties on the ZoneInfo actor).
5. `actor->vtbl[+0xac](1,1)` (pass G final loop) not chased into Engine.dll; behavior
   (re-linking actor into zone lists / setting Region for non-ZoneInfo actors) inferred from
   context.
6. In 0xa9030 the coplanar case (`r==0`) discards the fragment mid-descent and returns from
   the WHOLE call (not just that branch) — quoted at `0x100a918b..0x100a9196` (`cmp ebx,2/je;
   cmp ebx,3/jne EXIT`). Faithful, but worth a differential check on a map with coplanar
   portal planes.
