# RE decode — per-light leaf-visibility flood: `FEditorVisibility::ActorVisibility` @ Editor.dll RVA 0xa6d00

Decoded 2026-07-16 from `/home/neob91/Games/LutrisDX/drive_c/DX/LUM/Tools/uedctl/uned/UED22/Editor.dll`
(ImageBase 0x10000000; all addresses below are VAs). Function name is the binary's own: the
MSVC EH handler's __except path pushes the string `"FEditorVisibility::ActorVisibility"`
(0x100fe658, quoted at `0x100a7218 push 0x100fe658`). The helper asserts carry the source path
`"C:\GameDev\UnrealTournament\Editor\Src\UnVisi.cpp"` (0x100fe394, stored ASCII) — this is the
UnVisi.cpp lineage, ground truth from the binary.

Signature (thiscall, `ret 0xc` = 3 stack args):

```c
// ecx = FEditorVisibility* this
INT FEditorVisibility::ActorVisibility(AActor* Actor,   // [ebp+8]
                                       INT     iLeaf,   // [ebp+0xc]; -1 = seed from Actor->Location
                                       FPoly*  ClipPoly)// [ebp+0x10]; 0 at top level
// returns the number of leaves NEWLY marked for this Actor by this invocation
// (top-level return is the "%i" of "Lightsource %s: %i leaves")
```

---

## 1. TL;DR answers to the assignment questions

1. **Seeding**: yes, plain BSP descent. Starting at node 0, take `side = (PlaneDot(node.Plane,
   Actor->Location) > 0) ? 1(front) : 0(back)` and follow `iChild[side]` until -1; the seed leaf is
   the last node's `iLeaf[side]`. If that is -1 (light in solid space) → return 0. No coplanar
   (`iPlane`) walking, no radius involvement in seeding.
2. **Adjacency flooded**: the per-leaf **portal lists at `this+0x10050`** (heads of intrusive
   linked lists of 0x200-byte FPortal chunks; each chunk sits on TWO leaf lists via next-pointers
   at chunk+0x1e8/+0x1ec). `this+0x1004c` (per-node portal lists) is NOT touched by this function;
   `this+0x10054` is the per-leaf OUTPUT (light membership), not adjacency.
3. **Radius/attenuation cutoff**: `AActor::WorldLightRadius()` — a **virtual call through actor
   vtable slot +0x6c** (twice: 0x100a6eb0, 0x100a701a). Proven == Engine.dll export
   `?WorldLightRadius@AActor@@UBEMXZ` @ Engine RVA 0x116b50 = `25.0f * (BYTE at actor+0x1a1
   (LightRadius) + 1)` (see §6). Used two ways:
   - re-entry gate: some portal of the leaf must have a vertex with `distSq(vertex,
     Actor->Location) < R²`;
   - traversal gate per portal: signed plane distance `d = (Actor->Location − Poly.Base)·Poly.Normal`
     must satisfy `-R < d < 0` (poly oriented for the current leaf, see §4).
   Raw actor offsets: position `actor+0xd0/0xd4/0xd8` (Location FVector), radius byte `actor+0x1a1`
   (via the virtual).
4. **What is appended at `this+0x10054`**: a 2-dword record `{AActor* Actor /*+0*/, Node* Next /*+4*/}`,
   8 bytes allocated from `GMem` via `FMemStack::PushBytes(8, 0x10)`, PREPENDED to the leaf's list
   head `this->+0x10054[iLeaf]`. **The stored value is the raw AActor POINTER** (the `edx` compared
   at `0x100a6ef8 cmp [eax], edx` is the Actor argument itself). The pointers are only converted to
   `Model->Lights` entries later by the portalize caller (step 15) via `TArray<INT>::AddItem` — in
   memory `Model->Lights` (+0xe4) therefore holds actor pointers + a `0` terminator per leaf run;
   any index/objref form is a serialization concern, not this pass's.
5. **leaf.iExclusive (u64 at leaf+0xc)**: **NOT written by this function or any callee** — 0xa6d00
   never touches `Model->Leaves` at all (no `Model+0xd8` access; its only per-leaf state is the
   scratch arrays `this+0x10050/0x10054`). Cluster-wide evidence in §7: the field is set to
   `-1,-1` once at leaf creation (pass A) and never written again anywhere in
   0xa6970..0xaa940. In this build it is a dead, always--1 field.
6. **Call-site eligibility fields**: see §8 table (LightType/bStatic|bNoDelete/Region.Zone->bFogZone/
   VolumeBrightness/VolumeRadius, with per-field confidence and instruction quotes).

---

## 2. `FEditorVisibility::ActorVisibility` @ 0xa6d00 — pseudo-C

Role: recursive light-through-portals flood: mark every leaf the light can reach (distance- and
beam-clipped) into the per-leaf lists at `this+0x10054`, returning how many leaves were newly marked.

```c
INT FEditorVisibility::ActorVisibility(AActor* Actor, INT iLeaf, FPoly* ClipPoly)
{
    if (iLeaf == -1) {                                        // top-level: seed by BSP descent
        INT iNode = 0, iPrev = 0, Side = 0;
        while (iNode != -1) {
            iPrev = iNode;
            FLOAT Dist = Nodes[iNode].Plane.PlaneDot(Actor->Location);   // Location = actor+0xd0
            Side = (Dist > 0.0f);                             // seta: >0 → 1 (front); ==0 → back
            iNode = Nodes[iPrev].iChild[Side];                // +0x20/+0x24
        }
        iLeaf = Nodes[iPrev].iLeaf[Side];                     // +0x38/+0x3c
        if (iLeaf == -1) return 0;                            // light embedded in solid
        goto Mark;                                            // NOTE: seed leaf skips the radius gate
    }

    // ---- recursive-entry gate: is any portal of this leaf within WorldLightRadius? ----
    {
        FPortal* P = this->PortalsPerLeaf[iLeaf];             // this+0x10050
        if (!P) return 0;                                     // leaf with no portals: not marked!
        for (;;) {
            FPoly Poly;  P->GetPolyForLeaf(iLeaf, &Poly);     // 0xa96f0 (oriented copy, §4)
            FLOAT R = Actor->WorldLightRadius();              // virtual, vtbl+0x6c
            for (INT i = 0; i < Poly.NumVertices; i++)        // NumVertices = FPoly+0x1c0
                if (SizeSquared(Poly.Vertex[i] - Actor->Location) < R*R)
                    goto Mark;                                // strictly inside the sphere
            P = P->Next(iLeaf);                               // 0xa9b70
            if (!P) return 0;                                 // exhausted → leaf NOT marked
        }
    }

Mark:
    INT NewLeaves = 0;
    // dedupe walk of the per-leaf light list; value compared is the Actor POINTER
    for (Node* n = this->LightsPerLeaf[iLeaf] /*this+0x10054*/; ; n = n->Next) {
        if (!n) {                                             // not yet marked → prepend
            Node* nn = (Node*)GMem.PushBytes(8, 0x10);        // {AActor* +0, Node* +4}
            if (nn) { nn->Actor = Actor; nn->Next = this->LightsPerLeaf[iLeaf]; }
            this->LightsPerLeaf[iLeaf] = nn;
            NewLeaves = 1;
            break;
        }
        if (n->Actor == Actor) break;                         // already marked → count 0,
    }                                                         //   but STILL flood onward (re-visit
                                                              //   with a different clip beam is legal)
    // ---- flood through every portal of this leaf ----
    for (FPortal* P = this->PortalsPerLeaf[iLeaf]; P; P = P->Next(iLeaf)) {
        FPoly Poly;  P->GetPolyForLeaf(iLeaf, &Poly);         // normal points OUT of iLeaf (§4)
        FLOAT d = (Actor->Location - Poly.Base) | Poly.Normal;// Base=+0, Normal=+0xc
        if (!(d < 0.0f))               continue;              // light must be on iLeaf's side
        FLOAT R = Actor->WorldLightRadius();                  // virtual, vtbl+0x6c
        if (!(d > -R))                 continue;              // plane within radius of the light
        INT iOther = P->GetOtherLeaf(iLeaf);                  // 0xa96a0

        if (ClipPoly) {                                       // beam-clip Poly by the pyramid
            INT jPrev = ClipPoly->NumVertices - 1;            //   (Actor, ClipPoly edges)
            for (INT j = 0; j < ClipPoly->NumVertices; jPrev = j++) {
                if (Poly.NumVertices >= 14) break;            // growth guard (cmp eax,0xe)
                FPoly Front, Back;                            // ctor'd, then:
                FPlane Pl(Actor->Location,                    // FPlane(A,B,C) Core import
                          ClipPoly->Vertex[j],
                          ClipPoly->Vertex[jPrev]);
                INT r = Poly.SplitWithPlaneFast(Pl, &Front, &Back); // Engine import
                if (r == 2 /*SP_Back*/)  goto NextPortal;     // fully outside the beam
                if (r == 3 /*SP_Split*/) Poly = Front;        // keep the in-beam half
                // r==0 (coplanar) / r==1 (front): keep Poly as-is
            }
        }
        if (Poly.NumVertices > 0)
            NewLeaves += ActorVisibility(Actor, iOther, &Poly); // recurse @0x100a71c3
    NextPortal:;
    }
    return NewLeaves;
}
```

### Key instruction evidence

Seeding descent (`Location` at +0xd0, `seta` side pick, iChild/iLeaf indexing):
```
0x100a6d70  shl  ecx, 6                       ; iNode*0x40 → FBspNode stride
0x100a6d73  add  ecx, [eax+0x58]              ; + Model->Nodes.Data  → ecx=&node (=&Plane)
0x100a6d76  lea  eax, [edx+0xd0]              ; &Actor->Location
0x100a6d7d  call [0x100ce514]                 ; Core: ?PlaneDot@FPlane@@QBEMABVFVector@@@Z
0x100a6d93  comiss xmm0, [0x100dcaec]         ; vs 0.0f
0x100a6d9a  seta cl                           ; Side = Dist > 0
0x100a6da3  shl  edi, 4 / add edi, ecx
0x100a6dae  mov  edi, [eax+edi*4+0x20]        ; iNode = node.iChild[Side]
0x100a6dc8  mov  esi, [eax+esi*4+0x38]        ; iLeaf = lastNode.iLeaf[Side]
0x100a6dd2  cmp  esi, -1 / jne 0x100a6edd     ; -1 → return 0; else straight to Mark
```
Re-entry radius gate (vertex-in-sphere, virtual radius):
```
0x100a6dfc  mov  eax, [esi+0x10050]           ; per-leaf PORTAL list heads
0x100a6e02  mov  esi, [eax+edi*4]             ; head for iLeaf; 0 → return 0 (0x100a6e0d)
0x100a6e25  call 0x100a96f0                   ; GetPolyForLeaf(iLeaf, &Poly)
0x100a6e3e  movss xmm2, [ebp+eax*4-0x1bc]     ; Poly.Vertex[i]  (ebp-0x1ec + 0x30 + i*12)
0x100a6e4d  subss xmm2, [ecx+0xd0]            ; − Actor->Location   (…0xd4, 0xd8 follow)
0x100a6ea3  movss [ebp-0x5b4], xmm2           ; distSq
0x100a6eab  mov  eax, [ecx] / mov eax,[eax+0x6c] / call eax   ; Actor->WorldLightRadius()
0x100a6ec0  mulss xmm0, xmm0                  ; R²
0x100a6ec4  comiss xmm0, [ebp-0x5b4] / jbe …  ; qualify iff R² > distSq (strict)
0x100a7205  … call 0x100a9b70                 ; P = P->Next(iLeaf); loop
```
Marking (`+0x10054`, actor-pointer identity, GMem node {value,next}):
```
0x100a6eeb  mov  eax, [eax+0x10054]           ; per-leaf LIGHT list heads
0x100a6ef8  cmp  [eax], edx / je 0x100a6f4b   ; edx = Actor arg → already marked, still flood
0x100a6efc  mov  eax, [eax+4]                 ; walk ->Next
0x100a6f01  push 0x10 / push 8
0x100a6f05  mov  ecx, [0x100ce508]            ; GMem
0x100a6f0b  call [0x100ce530]                 ; FMemStack::PushBytes(8, 0x10)
0x100a6f2c  mov  [ecx], edx                   ; node.Actor = Actor  (RAW POINTER)
0x100a6f2e  mov  [ecx+4], eax                 ; node.Next  = old head
0x100a6f41  mov  [eax+esi*4], ecx             ; this+0x10054[iLeaf] = node (prepend)
0x100a6f44  inc  edi                          ; NewLeaves = 1
```
Traversal gates (side + plane-distance-within-radius):
```
0x100a6f8d  movss xmm0, [ecx+0xd0] / subss xmm0, [ebp-0x1ec]  ; Location − Poly.Base
0x100a6fd5..0x100a6ffd  (·) Poly.Normal at ebp-0x1e0 (= FPoly+0xc) → xmm3 = d
0x100a7009  xorps xmm0, xmm0 / comiss xmm0, xmm3 / jbe skip   ; require d < 0
0x100a7015  … call [eax+0x6c]                                  ; WorldLightRadius again
0x100a702a  xorps xmm0, [0x100dcb60]          ; f32 −0.0 → −R
0x100a7039  comiss xmm1, xmm0 / jbe skip      ; require d > −R
0x100a7049  call 0x100a96a0                   ; iOther = GetOtherLeaf(iLeaf)
```
Beam clip (constant 14; FPlane through light + ClipPoly edge; keep front half):
```
0x100a7067  mov  edx, [ecx+0x1c0] / dec edx   ; jPrev = ClipPoly->NumVertices − 1
0x100a7083  cmp  eax, 0xe / jge 0x100a719f    ; Poly.NumVertices ≥ 14 → stop clipping
0x100a70b7..0x100a713f  build 3 FVectors: ClipPoly->Vertex[jPrev] (+0x30+j*12),
                        ClipPoly->Vertex[j], Actor->Location(+0xd0)  (Location built last
                        → first ctor arg)
0x100a7146  call [0x100ce008]                 ; Core: ??0FPlane@@QAE@VFVector@@00@Z  (A=Light,
                                              ;  B=Vertex[j], C=Vertex[jPrev])
0x100a7152  call [0x100cee30]                 ; Engine: ?SplitWithPlaneFast@FPoly@…(FPlane,
                                              ;  FPoly* Front=&[ebp-0x3c4], FPoly* Back=&[ebp-0x59c])
0x100a7158  cmp  eax, 2 / je cull             ; SP_Back → skip portal
0x100a7161  cmp  eax, 3 / jne next-edge
0x100a7173  call [0x100cee28]                 ; ??4FPoly (operator=): Poly = Front
```
Recursion + return:
```
0x100a71a5  test eax, eax / jle skip          ; clipped poly empty → don't recurse
0x100a71a9  push &Poly / push iOther / push Actor
0x100a71c3  call 0x100a6d00                   ; ActorVisibility(Actor, iOther, &Poly)
0x100a71c8  add  edi, eax                     ; accumulate newly-marked count
0x100a71f8  mov  eax, edi                     ; return NewLeaves
```

### State written by 0xa6d00
- **`this+0x10054[iLeaf]`** — prepends `{AActor*, Next}` GMem nodes (the only mutation).
- Nothing else: no writes to Model, Nodes, Surfs, Leaves, Zones, or `this+0x1004c/0x10050`.

### Constants
- `0.0f` plane-side epsilon-free compares (`comiss` vs `[0x100dcaec]`=0.0 and `xorps`-zeroed reg);
  strict `>` for descent side, strict `<`/`>` for the gates.
- `-0.0f` mask `[0x100dcb60]` (sign-flip of R).
- `0xe` (14) — max working-poly vertices before clipping stops (`0x100a7083 cmp eax, 0xe`).
- `8, 0x10` — PushBytes size/align of a light-list node.
- SplitWithPlaneFast results tested: `2` (cull) and `3` (replace with front half); 0/1 fall through.

### Open questions / low confidence
- `SP_*` enum naming (2=Back, 3=Split) is inferred from geometry (the kept half is the one on the
  light's side of the edge plane and the cull happens on the other side); the numeric behavior
  itself is exact as quoted. If the Rust port re-implements SplitWithPlaneFast it must match
  Engine.dll's (exported) routine, including its coplanar thresholds — not decoded here.
- The re-entry gate means a leaf whose portals are all farther than R (vertices) is never marked
  even if reached; and a portal-less leaf is never marked at all except as the seed. Port must
  reproduce both asymmetries exactly.
- Recursion has NO depth guard and re-visits marked leaves (dedupe only suppresses re-marking);
  termination relies on the beam shrinking. Port must keep the re-visit semantics to match
  membership.

---

## 3. `FPortal` chunk layout (0x200 bytes, GMem) — from ctor @ 0xa6ab0 + AddPortal @ 0xa72a0

`FEditorVisibility::AddPortal` @ 0xa72a0 (EH name string 0x100fe504 `"FEditorVisibility::AddPortal"`,
pushed at 0x100a73c4) allocates `PushBytes(0x200, 0x10)` (0x100a72ee) and constructs via
0xa6ab0, then links the chunk as the new head of FOUR lists (0x100a7372..0x100a7396):
`this+0x1004c[iNode]`, `this+0x10050[iFrontLeaf]`, `this+0x10050[iBackLeaf]`, `this+0x10044`
(global head), and increments the portal counter `this+0x10014` (0x100a739c).

Ctor 0xa6ab0 (`ret 0x20`, 8 args) — layout, exact stores quoted from 0x100a6ab9..0x100a6b13:

| offset | field | evidence |
|---|---|---|
| +0x000 | embedded **FPoly** (0x1d8) | `call [0x100cee94]` = `??0FPoly@@QAE@ABV0@@Z` copy-ctor with this=chunk |
| +0x1d8 | `iFrontLeaf` | assert string `"iLeaf==iFrontLeaf \|\| iLeaf==iBackLeaf"` (0x100fe444); first compare is +0x1d8 |
| +0x1dc | `iBackLeaf` | second compare |
| +0x1e0 | `iNode` (the BSP node whose plane carries the portal) | AddPortal passes its own arg4 (node index used to index +0x1004c) |
| +0x1e4 | global next (chain of ALL portals; walked by the zone pass at 0x100a9472 `mov edi,[edi+0x1e4]`) | |
| +0x1e8 | next portal in **iFrontLeaf**'s list | `Next(iLeaf)` @0xa9b70 returns it when `iLeaf==+0x1d8` |
| +0x1ec | next portal in **iBackLeaf**'s list | returned when `iLeaf==+0x1dc` |
| +0x1f0 | next portal on the same node (old `this+0x1004c[iNode]` head) | |
| +0x1f4 | u16, init 0 | `mov word ptr [esi+0x1f4], 0` — meaning not needed here (zone-portal pass state) |
| +0x1f8 | u32, init 0 | |
| +0x1fc | i32, init -1 | zone pass treats `==-1` as "not a zone portal" (0x100a9415 `cmp [edi+0x1fc], -1`) |

---

## 4. Helpers on the portal chunk (all assert `iLeaf` ∈ {iFrontLeaf, iBackLeaf} via appError [0x100ce788], UnVisi.cpp lines 231/248/256)

### `GetOtherLeaf` @ 0xa96a0 — `ret 4`
Returns `+0x1dc` if `iLeaf==+0x1d8`, else `+0x1d8` (0x100a96d2..0x100a96e2). Pure read.

### `GetPolyForLeaf` @ 0xa96f0 — `(INT iLeaf, FPoly* Out)`, `ret 8`
```
0x100a9726  call [0x100cee28]        ; *Out = *(FPoly*)chunk          (operator=)
0x100a972c  cmp  edi, [esi+0x1d8]    ; if iLeaf == iFrontLeaf:
0x100a9739  call [0x100cee44]        ;     Out->Reverse()             (?Reverse@FPoly@@QAEXXZ)
```
So the returned poly's **normal points away from the queried leaf, toward the other leaf**,
GIVEN the stored convention "front leaf lies on the stored poly's normal side". That convention
is implied by the binary's own field names (iFrontLeaf/iBackLeaf from the assert string) plus the
engine's side=1=front convention, and is what makes ActorVisibility's `d<0` gate geometrically
sane (flood outward only when the light is inside the current leaf's side). Confidence: high for
the reverse-on-front behavior (quoted), medium-high for the phrase "normal points out of the
queried leaf" (rests on the front-side convention, not independently re-proven here).

### `Next` @ 0xa9b70 — `(INT iLeaf)`, `ret 4`
Returns `+0x1e8` if `iLeaf==iFrontLeaf` else `+0x1ec` (0x100a9baa / 0x100a9bb6). Pure read.

---

## 5. The portalize call site (inside 0xaa370) — what happens around ActorVisibility

Two-pass loop over `Level->Actors` (`this+0xc` → Data +0x2c / Num +0x30, quoted 0x100aa5c0..0x100aa5cf);
pass 0 only counts eligible lights (progress denominator), pass 1 (`cmp ecx,1` 0x100aa5e5) does
`GWarn->StatusUpdatef(cur, total, "Illumination occluding")` (0x100fea50), then

```
0x100aa60a  push 0 / push -1 / push edi(actor) / call 0x100a6d00
0x100aa619  call [0x100ce85c]        ; UObject::GetName
0x100aa631  call [0x100ce768]        ; debugf("Lightsource %s: %i leaves", name, ret)
```
then `debugf("Time = %lf msec per light", …)` via `appSecondsNew` [0x100ce994].

Per-leaf fill (0x100aa6b1..0x100aa73c) — leaf stride 0x14 (`lea edi,[ebx+ebx*4]` ×4):
- asserts `leaf.iPermeating == -1` (`cmp [eax+edi*4+4], -1`; assert string 0x100feae8
  `"Model->Leaves(i).iPermeating==INDEX_NONE"`, UnVisi.cpp line 1578);
- if `this+0x10054[iLeaf] != 0`: `leaf.iPermeating = Model->Lights.Num` (`mov ecx,[ecx+0xe8]` →
  `mov [eax+edi*4+4], ecx`), then for each list node `TArray::AddItem(&Model->Lights /*+0xe4*/,
  node.Actor)` (call 0x100123e0 walking `[edi+4]`), then `AddItem(0)` — the NULL terminator.

Volumetric repeat (0x100aa74e..): zero all of `+0x10054`, run 0xa9290 per eligible fog light,
then identical fill into `leaf.iVolumetric` (+8, assert `"…iVolumetric==INDEX_NONE"` 0x100feb14,
line 1614). **`leaf+0xc` is untouched in both fills.**

---

## 6. Radius virtual — proof of identity

- ActorVisibility calls `[vtbl+0x6c]` on the actor (0x100a6eab, 0x100a7015).
- Engine.dll exports `?WorldLightRadius@AActor@@UBEMXZ` (the `U` = virtual; WorldSoundRadius and
  WorldVolumetricRadius are `Q` = non-virtual) @ Engine RVA 0x116b50:
  ```
  0x10116b54  movzx eax, byte ptr [ecx+0x1a1]   ; LightRadius (BYTE)
  0x10116b5b  inc eax
  0x10116b63  mulss xmm0, [0x101fee34]          ; ×25.0f  → R = 25*(LightRadius+1)
  ```
- RTTI walk: scanning Engine.dll for pointers to 0x10116b50 and treating each hit as `vtbl+0x6c`
  gives complete-object locators naming `.?AVAActor@@`, `.?AVAPawn@@`, `.?AVAPlayerPawn@@`,
  `.?AVAMover@@` — i.e. **slot +0x6c of the AActor vtable family IS WorldLightRadius**. Proven.
- Twin check: `?WorldVolumetricRadius@…` @ Engine 0x116bb0 reads `byte [ecx+0x1a6]` (VolumeRadius),
  `?WorldSoundRadius@…` @ 0x116b80 reads `byte [ecx+0x184]` (SoundRadius). The volumetric flood
  0xa9290 inlines exactly `25.0f * (byte[actor+0x1a6]+1)` (0x100a92cf..0x100a92e6, constants
  f32=−25 @0x100feef8 / f32=25 @0x100de9d4) — consistent (it can inline because the volumetric
  getter is non-virtual).

Matches the previously-documented fact in `sections/20-lighting-bake.md` (WorldLightRadius @
0x116b50, LightRadius byte +0x1a1).

---

## 7. leaf.iExclusive (u64 at leaf+0xc) — where its value actually comes from

FBspLeaf in-memory stride 0x14: iZone +0, iPermeating +4, iVolumetric +8, iExclusive +0xc (u64).

- The ONLY write in the whole FEditorVisibility cluster (0xa6970..0xaa940 disassembled in full;
  grep for `+0xc],`/`+0x10],` stores audited one by one) is the leaf-creation template in pass A
  (`0xa7760`), just before appending the leaf via the 0x14-byte-append helper 0xa7260:
  ```
  0x100a77db  mov  eax, [ecx+0xdc]             ; template.iZone = Leaves.Num (its own index)
  0x100a77e4  mov  dword [ebp-0x30], -1        ; iPermeating
  0x100a77eb  mov  dword [ebp-0x2c], -1        ; iVolumetric
  0x100a77f2  mov  dword [ebp-0x28], -1        ; iExclusive.lo
  0x100a77f9  mov  dword [ebp-0x24], -1        ; iExclusive.hi
  0x100a780a  call 0x100a7260                  ; FArray::Add(1,0x14) + 0x14-byte memcpy of template
  ```
  (Helper 0xa7260: `push 0x14 / push 1 / call [0x100ce5ec]` = `?Add@FArray@@QAEHHH@Z`, then
  `movups`+dword copy of the 20-byte record; returns the new leaf's index.)
- Other passes touch leaves only at +0 (iZone): the zone-merge/renumber in 0xa93c0 (quoted
  0x100a9469 / 0x100a94d0 / 0x100a94db / 0x100a9533 — including the final `idiv` by 0x3f and
  `+1` → zones 1..63) and reads for node.iZone bytes (0x100aa2dd/0x100aa304). Node ZoneMask u64
  writes at 0x100a8947 are `node+0x10/+0x14`, not leaves.

**Conclusion: in this build `iExclusive` is initialized to 0xFFFFFFFF_FFFFFFFF at leaf creation
and never modified — a dead/reserved field as far as zoning+light flood is concerned.** (Whether
some other subsystem writes it outside the Editor.dll zoning cluster was not searched; nothing in
0xa6d00 or its callees does.)

---

## 8. Actor-eligibility fields at the call sites (quoted from 0xaa370)

Light pass (both instructions byte-width — quoted at 0x100aa5d6/0x100aa5df):
```
cmp byte ptr [edi+0x19c], 0   ; je skip
test byte ptr [edi+0x28], 5   ; je skip
```
Volumetric pass (0x100aa785..0x100aa7b7):
```
mov  ecx, [eax+0x88] ; test ecx,ecx ; je skip
test byte ptr [ecx+0x27c], 2  ; je skip
cmp  byte ptr [eax+0x19c], 0  ; je skip
cmp  byte ptr [eax+0x1a6], 0  ; je skip
cmp  byte ptr [eax+0x1a5], 0  ; je skip
test byte ptr [eax+0x28], 5   ; je skip
```

| offset | identification | confidence / evidence |
|---|---|---|
| actor+0xd0 (12 B) | **Location** (FVector) | ✅ high — used as world position for PlaneDot/dist everywhere; already documented in `sections/20-lighting-bake.md` |
| actor+0x19c (byte) | **LightType** (`!=0` = `!=LT_None`) | high — byte enum gating all static lighting; anchors below land exactly on the classic Lighting-group declaration order from +0x19c: +0x1a1 LightRadius (proven §6), +0x1a6 VolumeRadius (proven §6) ⇒ +0x19d LightEffect, +0x19e LightBrightness, +0x19f LightHue, +0x1a0 LightSaturation, +0x1a2 LightPeriod, +0x1a3 LightPhase, +0x1a4 LightCone, +0x1a7 VolumeFog |
| actor+0x1a1 (byte) | **LightRadius** | ✅ proven (WorldLightRadius disasm, §6) |
| actor+0x1a5 (byte) | **VolumeBrightness** (`!=0`) | medium-high — the byte immediately before proven VolumeRadius in the declaration-order lattice; the classic volumetric gate is `VolumeBrightness && VolumeRadius` |
| actor+0x1a6 (byte) | **VolumeRadius** | ✅ proven (WorldVolumetricRadius disasm, §6) |
| actor+0x28 (byte) | first AActor bitfield byte; `&5` = **bStatic \| bNoDelete** (bit0=bStatic, bit1=bHidden, bit2=bNoDelete) | medium-high — `&5` is exactly the canonical "static light source" test (bStatic OR bNoDelete); bit names from classic Actor declaration order, not independently re-proven; the two-bit mask semantics are exact as quoted |
| actor+0x88 (ptr) | **Region.Zone** (`FPointRegion Region` at +0x88: Zone ptr +0x88, iLeaf +0x8c, ZoneNumber +0x90) | medium-high — deref'd as an object whose +0x27c bitfield gates fog; corroborated by pass F/G pushing `[edi+0x8c]` as a leaf index into GetOtherLeaf (0x100a8780) |
| zoneinfo+0x27c (byte) | AZoneInfo first bitfield byte; `&2` = **bFogZone** (bit0=bWaterZone, bit1=bFogZone) | medium — gating volumetric fog lighting is exactly bFogZone's job; bit position from classic ZoneInfo declaration order |
| actor vtbl+0x6c | **AActor::WorldLightRadius()** (virtual) | ✅ proven via RTTI (§6) |

---

## 9. Callee index (RVA → role)

| RVA (Editor.dll) | role |
|---|---|
| 0xa6d00 | `FEditorVisibility::ActorVisibility(Actor, iLeaf, ClipPoly)` — this decode; recursive |
| 0xa96f0 | `FPortal::GetPolyForLeaf(iLeaf, FPoly* Out)` — copy embedded FPoly, `Reverse()` if iLeaf is iFrontLeaf |
| 0xa96a0 | `FPortal::GetOtherLeaf(iLeaf)` — the +0x1d8/+0x1dc pair |
| 0xa9b70 | `FPortal::Next(iLeaf)` — per-leaf chain +0x1e8/+0x1ec |
| 0xa6ab0 | `FPortal::FPortal(FPoly&, iFrontLeaf, iBackLeaf, iNode, GlobalNext, NodeNext, FrontNext, BackNext)` — chunk layout §3 |
| 0xa72a0 | `FEditorVisibility::AddPortal` — alloc 0x200 chunk, link into +0x1004c/+0x10050(×2)/+0x10044, `+0x10014`++ (registered as a callback: `push 0x100a72a0` at 0x100a97ac inside pass B 0xa9750) |
| 0xa7260 | leaf-append helper: `FArray::Add(1, 0x14)` on `Model->Leaves` + 20-byte template copy; returns new index |
| 0xa9290 | volumetric leaf flood (sibling pass; node-space recursion with inline `25*(VolumeRadius+1)`, fills the same `+0x10054`) — internals out of this assignment's scope |
| Core [0x100ce514] | `FPlane::PlaneDot(FVector&)` |
| Core [0x100ce530] | `FMemStack::PushBytes(int, int)`; [0x100ce508] = `GMem` |
| Core [0x100ce008] | `FPlane::FPlane(FVector A, FVector B, FVector C)` |
| Core [0x100ce5ec] | `FArray::Add(int, int)` |
| Core [0x100ce85c] | `UObject::GetName()` |
| Core [0x100ce994] | `appSecondsNew()` |
| Engine [0x100ceea4] | `FPoly::FPoly()` |
| Engine [0x100cee94] | `FPoly::FPoly(const FPoly&)` |
| Engine [0x100cee28] | `FPoly::operator=(const FPoly&)` |
| Engine [0x100cee30] | `FPoly::SplitWithPlaneFast(FPlane, FPoly*, FPoly*) const` |
| Engine [0x100cee44] | `FPoly::Reverse()` |
| Engine 0x116b50 | `AActor::WorldLightRadius()` = `25.0f*(byte[this+0x1a1]+1)` (virtual, vtbl slot +0x6c) |
