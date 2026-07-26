# RE decode: zone-setter pass 0xa93c0 + volumetric sphere-flood 0xa9290 (Editor.dll, UED22)

Decoded 2026-07-16 from `/home/neob91/Games/LutrisDX/drive_c/DX/LUM/Tools/uedcli/uned/UED22/Editor.dll`
(ImageBase 0x10000000; addresses below are VAs, RVA = VA − 0x10000000). All claims anchored to
quoted instructions. Supporting context (portal-record layout, iZone seed) was chased into
0xa7760 / 0xa72a0 / 0xa6ab0 / 0xa7870 / 0xa9750 — quoted where load-bearing.

---

## 0. Prerequisite: the FPortal record and the leaf-iZone seed (chased context)

The zone-setter walks a **global singly-linked list of portal records at `this+0x10044`**.
Those records are created during pass A/B by the fragment callback **0xa72a0**, which allocates
**0x200 bytes** from `GMem` and calls the record constructor **0xa6ab0**:

```
0x100a72ec  push 0x10            ; align
0x100a72ee  push 0x200           ; size — FPortal record is 0x200 bytes
0x100a72f3  mov  ecx, [0x100ce508]        ; GMem
0x100a72f9  call [0x100ce530]             ; FMemStack::PushBytes(0x200, 0x10)
...
0x100a734a  call 0x100a6ab0               ; record ctor (below)
...
0x100a7372..96  ; stitch: this+0x1004c[iNode]=rec; this+0x10050[leafB]=rec;
                ;         this+0x10050[leafA]=rec; this+0x10044=rec
0x100a739c..a3  ; this+0x10014++            (the "%i portals" counter)
```

**FPortal layout** (from ctor 0xa6ab0, `ret 0x20` = 8 args, ecx = record):

```
0x100a6ab4  push [ebp+8]                  ; source FPoly*
0x100a6ab9  call [0x100cee94]             ; FPoly::FPoly(const FPoly&)  → rec+0x000..0x1d7
0x100a6ac2  mov [esi+0x1d8], eax          ; iLeaf side A   (arg2)
0x100a6acb  mov [esi+0x1dc], eax          ; iLeaf side B   (arg3)
0x100a6ad4  mov [esi+0x1e0], eax          ; iNode          (arg4)
0x100a6add  mov [esi+0x1e4], eax          ; next in GLOBAL list (old this+0x10044 head)
0x100a6ae6  mov [esi+0x1e8], eax          ; next in per-leaf list of leafA (old this+0x10050[leafA])
0x100a6aef  mov [esi+0x1ec], eax          ; next in per-leaf list of leafB (old this+0x10050[leafB])
0x100a6af8  mov [esi+0x1f0], eax          ; next in per-node list (old this+0x1004c[iNode])
0x100a6b00  mov word  [esi+0x1f4], 0
0x100a6b09  mov dword [esi+0x1f8], 0
0x100a6b13  mov dword [esi+0x1fc], 0xffffffff   ; iZonePortalSurf — INIT -1 = "not a zone portal"
```

So: `rec+0x1d8/+0x1dc` = the two leaf indices the portal separates, `rec+0x1e4` = global next,
`rec+0x1fc` = **zone-portal marker, -1 unless stamped**.

**Who stamps +0x1fc:** pass B (0xa9750). For each node whose surf has `PF_Portal`
(`0x100a9870  test dword [eax+4], 0x4000000` — PolyFlags is at **FBspSurf+0x4**), it calls
`GEditor->bspNodeToFPoly` (vtbl+0x1f8), sets `this+0x10040 = node.iSurf`
(`0x100a98aa  mov [ebx+0x10040], eax` after `mov eax,[edi+0x1c]`), bumps `this+0x10034`
(zone-portal count), and clips the portal poly down the tree via 0xa9030 with callback
**0xa7870**. 0xa7870 then walks the global list and stamps every portal record whose
unordered leaf pair `{+0x1d8,+0x1dc}` equals the fragment's leaf pair:

```
0x100a78c4  mov eax, [ecx+0x1d8]
0x100a78ca  cmp eax, esi / 0x100a78ce cmp [ecx+0x1dc], edi   ; (A,B) match
0x100a78d6  cmp eax, edi / 0x100a78da cmp [ecx+0x1dc], esi   ; (B,A) match
0x100a78e2  mov eax, [edx+0x10040]        ; iSurf of the PF_Portal node
0x100a78e8  mov [ecx+0x1fc], eax          ; STAMP: rec.iZonePortalSurf = iSurf
0x100a78ee..f5  inc this+0x10038          ; fragment count ("%i fragments")
0x100a78fb  mov ecx, [ecx+0x1e4]          ; next global record
```

**Leaf iZone seed:** leaves are created in pass A (0xa7760). Each new leaf is built on the
stack as `{iZone = Leaves.Num, iPermeating=-1, iVolumetric=-1, iExclusive=-1,-1}` and appended
(0xa7260 = TArray add of a 0x14-byte element), i.e. **every leaf is seeded with
`iZone = its own leaf index`**:

```
0x100a77db  mov eax, [ecx+0xdc]           ; Leaves.Num (the index the new leaf WILL get)
0x100a77e1  mov [ebp-0x34], eax           ; leaf.iZone   = Leaves.Num
0x100a77e4  mov dword [ebp-0x30], -1      ; leaf.iPermeating = -1
0x100a77eb  mov dword [ebp-0x2c], -1      ; leaf.iVolumetric = -1
0x100a77f2/f9 mov dword [ebp-0x28/-0x24], -1  ; leaf.iExclusive (u64) = -1
0x100a7804  add ecx, 0xd8                 ; &Model->Leaves TArray
0x100a780a  call 0x100a7260               ; add, returns new index
0x100a780f  mov [edi+esi*4+0x38], eax     ; node.iLeaf[side] = new leaf index
```

---

## 1. Function 0xa93c0 — "AssignUniqueZones": zone flood + renumber + `Model->NumZones`

**(1) Role.** Merges leaf zone tags across every **non-zone-portal** portal record, compacts
the surviving tags to dense ids, writes each leaf's final `iZone = (denseId % 63) + 1`, logs
"Found %i zones", and writes `Model+0x100 = Clamp(numZones+1, 1, 64)`. **It writes NOTHING
else** — no ZoneInfo lookup, no `Zones[]`, no node fields.

Signature: `thiscall(this = FEditorVisibility)`, no stack args (`ret`). ebx = this throughout;
esi/eax reload `Model = this+0x10` (+0x10).

**(2) Pseudo-C.**

```c
void FEditorVisibility::AssignUniqueZones()   // @0x100a93c0
{
    FMemMark Mark(GMem);                      // 0xa93f7..0xa9408 (inline ctor), popped at end

    // Phase 1: union zones across all NON-zone-portal portals.
    // Adjacency = the global portal list this+0x10044 (every leaf/leaf portal
    // produced by passes A/B); zone portals (rec->iZonePortalSurf != -1,
    // stamped by 0xa7870 from PF_Portal surfs) do NOT merge.
    for (FPortal* P = *(FPortal**)((BYTE*)this + 0x10044); P; P = P->GlobalNext /*+0x1e4*/)
    {
        if (P->iZonePortalSurf /*+0x1fc*/ == -1)
        {
            INT ZoneA = Model->Leaves(P->iLeafA /*+0x1d8*/).iZone;
            INT ZoneB = Model->Leaves(P->iLeafB /*+0x1dc*/).iZone;
            for (INT i = 0; i < Model->Leaves.Num(); i++)      // full-array relabel, O(P*L)
                if (Model->Leaves(i).iZone == ZoneA)
                    Model->Leaves(i).iZone = ZoneB;
        }
    }

    // Phase 2: compact surviving tags (leaf indices) to dense 0..numZones-1,
    // in order of first appearance. (Sound because an unrenumbered group's tag v
    // is always still carried by leaf v itself, and numZones<=i at leaf i.)
    INT NumZones = 0;
    for (INT i = 0; i < Model->Leaves.Num(); /*advance below*/)
    {
        if (Model->Leaves(i).iZone < NumZones) { i++; continue; }  // already renumbered
        for (INT j = i + 1; j < Model->Leaves.Num(); j++)
            if (Model->Leaves(j).iZone == Model->Leaves(i).iZone)
                Model->Leaves(j).iZone = NumZones;
        Model->Leaves(i).iZone = NumZones++;
        i++;                                   // outer resumes at i+1
    }

    debugf(/*EName*/ 0x2f8, L"Found %i zones", NumZones);   // GLog->Logf

    // Phase 3: fold dense ids into engine zone bytes 1..63 (zone 0 reserved).
    // NOTE: MODULO WRAP, not clamp — zones beyond 63 alias back onto 1..63.
    for (INT i = 0; i < Model->Leaves.Num(); i++)
        Model->Leaves(i).iZone = (Model->Leaves(i).iZone % 63) + 1;

    // Phase 4: Model->NumZones = Clamp(NumZones+1, 1, 64)  (the +1 counts zone 0).
    *(INT*)((BYTE*)Model + 0x100) = Clamp(NumZones + 1, 1, 64);

    Mark.Pop();
}
```

**(3) Constants / thresholds (evidence).**

- Merge condition — only portals NOT stamped as zone portals:
  ```
  0x100a9415  cmp dword ptr [edi + 0x1fc], -1
  0x100a941c  jne 0x100a9472                 ; stamped => skip (no merge)
  ```
- Leaf record stride 0x14 (index*5 then *4) and iZone at leaf+0:
  ```
  0x100a9427  mov eax, [edi + 0x1d8]         ; P->iLeafA
  0x100a942d  lea eax, [eax + eax*4]
  0x100a9430  mov eax, [ecx + eax*4]         ; Leaves.Data[iLeafA*0x14].iZone
  ```
- Relabel `ZoneA -> ZoneB` over the whole leaf array:
  ```
  0x100a945e  cmp dword ptr [eax + ecx*4], ebx   ; Leaves[i].iZone == ZoneA ?
  0x100a9469  mov dword ptr [eax + ecx*4], esi   ; Leaves[i].iZone = ZoneB
  ```
- Compaction skip test (signed):
  ```
  0x100a949e  cmp dword ptr [eax + ecx*4], edi   ; Leaves[i].iZone vs NumZones
  0x100a94a1  jl  0x100a94ea                     ; < NumZones => already renumbered
  ```
  inner relabel `0x100a94d0 mov [eax], edi`, then representative
  `0x100a94db mov [ebx + eax*4], edi` / `0x100a94de inc edi`.
- Log:
  ```
  0x100a94ee  push edi                       ; NumZones
  0x100a94ef  push 0x100fe6f0                ; L"Found %i zones"   (verified UTF-16 literal)
  0x100a94f4  push 0x2f8                     ; EName log-category value 760
  0x100a94f9  mov eax, [0x100ce71c]          ; GLog
  0x100a9500  call [0x100ce768]              ; FOutputDevice::Logf(EName, fmt, ...)
  ```
- **The 63 modulo** (divisor is 0x3f = 63, then +1 → final iZone range **1..63**):
  ```
  0x100a950e  mov dword ptr [ebp - 0x2c], 0x3f
  0x100a952e  cdq
  0x100a952f  idiv dword ptr [ebp - 0x2c]        ; edx = iZone % 63
  0x100a9532  inc edx
  0x100a9533  mov dword ptr [ecx], edx           ; leaf.iZone = (iZone % 63) + 1
  ```
- **The NumZones clamp to [1, 64]** (0x40 = 64), written to **UModel+0x100**:
  ```
  0x100a953b  inc edi                            ; NumZones + 1  (zone 0 included)
  0x100a953c  cmp edi, 1
  0x100a953f  jge 0x100a9548
  0x100a9541  mov ecx, 1                         ; floor 1
  0x100a9548  mov ecx, 0x40
  0x100a954d  cmp edi, ecx
  0x100a954f  cmovl ecx, edi                     ; min(NumZones+1, 64)
  0x100a9552  mov dword ptr [eax + 0x100], ecx   ; eax = Model (loaded 0xa9515) => Model->NumZones
  ```

**(4) State written (the deliverable).**

| target | write |
|---|---|
| `Model->Leaves[i].iZone` (leaf+0, stride 0x14) | phase 1: relabel ZoneA→ZoneB per unstamped portal; phase 2: dense 0..numZones-1; phase 3 (final): `(dense % 63) + 1` → **1..63** |
| `Model+0x100` (**confirms** brief's guess: this is `NumZones`) | `Clamp(numZones+1, 1, 64)` — includes implicit zone 0 |
| nothing else | **no** node `iZone[0/1]` (+0x34/+0x35), **no** `ZoneMask` (+0x10), **no** `Zones[]` at Model ≥+0x104, **no** surf writes, **no** `Level.Actors` walk |

**ZoneInfo actors: NOT located or assigned here.** There is no Level access at all in this
function (`this+0xc` is never read), no PointRegion-style descent, no actor-class check, and
no write anywhere in Model beyond +0x100. `FZoneProperties Zones[64]`
(ZoneActor/Connectivity/Visibility, presumably Model+0x104..) is untouched by both functions
in this assignment — that work must live in pass D (0xa7400, which by signature mirrors the
node-walking pass A and is the natural place for propagating leaf iZone into node
iZone[0/1]/ZoneMask) and passes F/G (0xa7960/0xa7e60) for Connectivity/Visibility, and/or in
Engine-side `ULevel::SetActorZones`-style code outside FEditorVisibility. Flagged for the
agents decoding those functions — see Open questions.

**(5) Callees.**

| callee | role |
|---|---|
| `[0x100ce768]` = `?Logf@FOutputDevice@@QAAXW4EName@@PBGZZ` (Core.dll) | the "Found %i zones" log, on `GLog` (`[0x100ce71c]`) |
| `[0x100ce52c]` = `?Pop@FMemMark@@QAEXXZ` (Core.dll) | pops the FMemMark taken at entry (0xa93f7..0xa9408 is the inline mark ctor over `GMem` `[0x100ce508]`); nothing is allocated between mark and pop in this function — pure RAII boilerplate |
| `0x100ac127` | security-cookie check (boilerplate, not present here beyond EH frame) |

**(6) Open questions / low-confidence.**

- `0x2f8` (760) is the raw EName value pushed to Logf; which name index it maps to (NAME_Log?)
  was not resolved — cosmetic only.
- The zone-merge is directional (A's tag replaced by B's) but symmetric in effect; the final
  dense numbering depends on leaf order, and the %63 wrap means maps with >63 flood groups get
  **aliased** zones (groups 63,126,… share iZone 1, etc.), not an error. A Rust port must
  reproduce the wrap, the first-seen compaction order, AND the portal-list order (records are
  **prepended** to `this+0x10044`, so phase 1 processes portals in reverse creation order —
  irrelevant for final membership since union is order-independent, but dense-id assignment
  order in phase 2 depends only on leaf order, so zone numbering is reproducible from leaf
  order alone).
- Where node `iZone[0/1]`/`ZoneMask` and `Zones[]`/ZoneActor get written: outside my two
  functions; cross-check pass D (0xa7400) / F (0xa7960) / G (0xa7e60) decodes.

---

## 2. Function 0xa9290 — volumetric-light sphere-vs-BSP leaf tagger

**(1) Role.** Recursively descends the BSP from `iNode`, visiting every leaf whose region
intersects the sphere centered at `actor+0xd0` (Location) with radius
`25.0 * (byte(actor+0x1a6) + 1)`, and **prepends `{actor, next}` (8 bytes from GMem) onto the
per-leaf singly-linked list at `this+0x10054[iLeaf]`**. No occlusion, no portal use — a pure
sphere/BSP overlap enumeration. (Portalize step 16 then drains these lists into
`leaf.iVolumetric` + `Model.Lights`.)

Signature: `thiscall`, `ret 0x10` = 4 stack args:
`(AActor* Actor /*ebp+8*/, INT iNode /*ebp+0xc*/, INT iPrevNode /*ebp+0x10*/, INT PrevSide /*ebp+0x14*/)`.
Top-level call from portalize: `(actor, 0, 0, 0)`. The iNode and PrevSide slots are reused as
locals (float dist, node byte-offset) inside the loop.

**(2) Pseudo-C.**

```c
void FEditorVisibility::TagVolumetricLeaves(AActor* Actor, INT iNode, INT iPrev, INT PrevSide)
// @0x100a9290
{
    INT UseNode, UseSide;
    if (iNode == -1) { UseNode = iPrev; UseSide = PrevSide; goto WriteLeaf; } // came from a -1 front child
    for (;;)
    {
        FBspNode& Node = Model->Nodes(iNode);                      // Model = this+0x10
        FLOAT Dist = Node.Plane.PlaneDot(Actor->Location /*+0xd0*/); // Core FPlane::PlaneDot
        FLOAT R = 25.f * (FLOAT)(BYTE(Actor->byte_0x1a6) + 1);     // world radius

        if (Dist > -R)                                             // sphere reaches FRONT halfspace
            TagVolumetricLeaves(Actor, Node.iChild[1] /*+0x24*/, iNode, 1);  // recursion; child==-1
                                                                              // resolves to iLeaf[1]
        if (!(R > Dist))                                           // sphere does NOT reach BACK
            return;
        if (Node.iChild[0] /*+0x20*/ != -1) { iNode = Node.iChild[0]; continue; } // iterate back
        UseNode = iNode; UseSide = 0;                              // back child -1 => back leaf here
        break;
    }
WriteLeaf:
    INT iLeaf = Model->Nodes(UseNode).iLeaf[UseSide];              // +0x38 + 4*side
    if (iLeaf == -1) return;
    struct { AActor* Actor; void* Next; }* Link =
        GMem.PushBytes(8, /*align*/16);                            // FMemStack::PushBytes
    if (Link) { Link->Actor = Actor;
                Link->Next  = ((void**)(this+0x10054 array))[iLeaf]; }
    ((void**)(this+0x10054 array))[iLeaf] = Link;                  // prepend (NULL if alloc failed)
}
```

**(3) Constants / thresholds (evidence).**

- Plane distance of the actor location (`actor+0xd0`) against the node plane (node+0):
  ```
  0x100a92bd  mov ecx, [eax + 0x58]          ; Nodes.Data
  0x100a92c6  add ecx, edx                   ; + iNode*0x40 => &Node (Plane at +0)
  0x100a92c0  lea eax, [ebx + 0xd0]          ; &Actor->Location
  0x100a92c9  call [0x100ce514]              ; FPlane::PlaneDot(const FVector&)
  ```
- **Radius formula `25*(byte+1)`** — the classic UE1 `World*Radius` scaling; radius byte at
  **actor+0x1a6**:
  ```
  0x100a92cf  movzx eax, byte ptr [ebx + 0x1a6]
  0x100a92d6  inc eax
  0x100a92e6  mulss xmm0, dword ptr [0x100feef8]   ; f32 = -25.0
  0x100a92ee  comiss xmm1, xmm0                    ; Dist > -R ?
  0x100a92f1  jbe skip_front
  ```
  and the back side:
  ```
  0x100a931f  mulss xmm0, dword ptr [0x100de9d4]   ; f32 = +25.0
  0x100a9327  comiss xmm0, xmm1                    ; R > Dist ?
  0x100a932a  jbe return
  ```
  Both tests strict (`jbe` skips on ==): a location exactly R away on either side is excluded.
- Front recursion carries `(iPrev=current, PrevSide=1)` so a `-1` front child resolves to the
  parent's `iLeaf[1]`:
  ```
  0x100a92f8  push 1                         ; PrevSide = 1 (front)
  0x100a92fa  push esi                       ; iPrev = current node
  0x100a92fe  push dword ptr [eax + ecx + 0x24]  ; iNode = Node.iChild[1] (FRONT)
  0x100a9305  push ebx                       ; Actor
  0x100a9306  call 0x100a9290                ; recurse
  ```
  Back side iterates in-place (`0x100a9338 mov esi, [eax + ecx + 0x20]`; loop while != -1),
  falling out with `UseSide=0` (`0x100a9333 xor edx, edx`).
- Leaf lookup `Nodes[UseNode].iLeaf[UseSide]`:
  ```
  0x100a934f  shl ebx, 4                     ; UseNode*16
  0x100a9352  add ebx, edx                   ; + UseSide     (=> *4 later: node*0x40 + side*4)
  0x100a9357  cmp dword ptr [eax + ebx*4 + 0x38], -1   ; iLeaf[side] @ node+0x38/+0x3c
  ```
- The 8-byte link node from GMem:
  ```
  0x100a935e  mov ecx, [0x100ce508]          ; GMem
  0x100a9364  push 0x10                      ; align 16
  0x100a9366  push 8                         ; size 8
  0x100a9368  call [0x100ce530]              ; FMemStack::PushBytes
  ```

**(4) State written.**

| target | write |
|---|---|
| `this+0x10054[iLeaf]` (the per-leaf pointer array, one slot per leaf, alloc'd in portalize step 6 and zeroed before step 16) | prepend a **GMem-allocated 8-byte link `{AActor* at +0, next* at +4}`** for every leaf intersecting the sphere. This is exactly the structure portalize step 16 drains: `leaf.iVolumetric = Model.Lights.Num()`, then the chain's actors + a 0 terminator are appended to `Model.Lights`. |
| nothing else | no Model/node/leaf/surf writes at all — leaves' `iZone/iPermeating/iVolumetric` untouched here |

Note the alloc-failure path (`0x100a9372 je` → `0x100a9393 xor esi, esi` →
`0x100a93a7 mov [eax + ecx*4], esi`): if PushBytes ever returned NULL the leaf's **whole list
head is overwritten with NULL** (drops previously-tagged actors for that leaf). GMem PushBytes
doesn't fail in practice; a port should just prepend.

**(5) Callees.**

| callee | role |
|---|---|
| `[0x100ce514]` = `?PlaneDot@FPlane@@QBEMABVFVector@@@Z` (Core.dll) | signed point/plane distance driving the descent |
| `[0x100ce530]` = `?PushBytes@FMemStack@@QAEPAEHH@Z` (Core.dll) on `GMem` `[0x100ce508]` | the 8-byte list link |
| `0x100a9290` (self) | front-child recursion |

**(6) Open questions / low-confidence.**

- **Naming** of `actor+0x1a6`: portalize step 16 gates on both `+0x1a5 != 0` and `+0x1a6 != 0`
  before calling this; given UE1's `WorldVolumetricRadius = 25*(VolumeRadius+1)` idiom the
  byte at +0x1a6 used here is most plausibly `VolumeRadius` (and +0x1a5 `LightRadius`), but
  the names are inferred — the raw offset is the ground truth. Cross-check the 0xa6d00
  (light-occlusion) decode: whichever byte THAT pass scales by 25 is `LightRadius`.
- `actor+0xd0` = Location is inferred from PlaneDot usage (consistent with the actor-layout
  used elsewhere in these passes), not independently re-verified.
- Degenerate top-level call with `Nodes.Num == 0`: `iNode=0` would index a missing node —
  portalize only runs when `Nodes.Num != 0` (TestVisibility gate), so unreachable.
