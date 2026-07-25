# Pass C — the ZONE SETTER (`Editor.dll` RVA 0xa93c0, "Found %i zones")

Decoded 2026-07-16 from `/home/neob91/Games/LutrisDX/drive_c/DX/LUM/Tools/uedctl/uned/UED22/Editor.dll`
(ImageBase 0x10000000) with `adis.py`. `this` (ecx) = `FEditorVisibility`; `this+0x10` = `UModel*`.

**Headline correction to the task brief:** pass C does **NOT** write node `iZone[0/1]`, node
`ZoneMask`, or walk the node graph. It is a pure **union-find-by-relabeling over the LEAF array**,
driven by the portal-fragment list built by pass B. Its only outputs are `Leaves[i].iZone` and
`Model->NumZones` (UModel **+0x100**, confirmed by instruction quote below). Node `iZone` bytes are
written by pass D (0xa7400 via callback 0xaa220), node `ZoneMask` by pass E (0xa8850),
`Zones[].Connectivity` by pass F (0xa7960), `Zones[].ZoneActor` by pass G (0xa7e60). All are
evidenced below because the Rust port needs the full chain.

---

## 0. The data structure pass C consumes: the portal-fragment record

Created during pass B (0xa9750) for **every leaf-boundary polygon fragment whose BOTH sides are
empty leaves**, allocated 0x200 bytes from GMem, linked into a global singly-linked list headed at
`this+0x10044`. Layout (from ctor `0xa6ab0` + producer `0xa72a0`):

| off | field | evidence |
|---|---|---|
| +0x000 | FPoly copy (0x1d8 bytes) | `0x100a6ab4 push [ebp+8]` / `0x100a6ab9 call [0x100cee94]` (FPoly copy) |
| +0x1d8 | `iLeaf[0]` — leaf index on the fragment's FRONT side | `0x100a6ac2 mov [esi+0x1d8], eax` (arg = edi from 0xa72a0 = param@+0xc) |
| +0x1dc | `iLeaf[1]` — leaf index on the BACK side | `0x100a6acb mov [esi+0x1dc], eax` |
| +0x1e0 | `iNode` the fragment came from | `0x100a6ad4 mov [esi+0x1e0], eax` |
| +0x1e4 | next in GLOBAL list (`this+0x10044`) | `0x100a6add mov [esi+0x1e4], eax` |
| +0x1e8 / +0x1ec | next in per-leaf lists (`this+0x10050[iLeaf]`) | `0x100a6ae6` / `0x100a6aef` |
| +0x1f0 | next in per-node list (`this+0x1004c[iNode]`) | `0x100a6af8 mov [esi+0x1f0], eax` |
| +0x1f4 | u16 = 0 | `0x100a6b00 mov word ptr [esi+0x1f4], 0` |
| +0x1f8 | u32 = 0 | `0x100a6b09 mov dword ptr [esi+0x1f8], 0` |
| **+0x1fc** | **`iZonePortalSurf`: init `-1`; set to the surf index of a PF_Portal face claiming this fragment** | init: `0x100a6b13 mov dword ptr [esi+0x1fc], 0xffffffff`; set: `0x100a78e8 mov [ecx+0x1fc], eax` |

### 0.1 Producer `0xa72a0` (pass-B leaf-pair callback) — one record per boundary fragment
Args `(FPoly* poly, INT iLeafFront, INT iLeafBack, INT iNode)` (`ret 0x14`, ecx=this).
- Bails if **either** leaf is -1 (a fragment against solid gets no record):
  `0x100a72da cmp edi, -1 / je` and `0x100a72e3 cmp ebx, -1 / je`.
- Allocates 0x200 bytes, align 0x10, from GMem:
  `0x100a72ec push 0x10 / 0x100a72ee push 0x200 / 0x100a72f3 mov ecx,[0x100ce508] / call [0x100ce530]`.
- Constructs via `0xa6ab0`, passing the four current list heads; then stores the new record ptr into
  all four heads: `0x100a737b mov [edx+eax],ecx` (per-node `this+0x1004c[iNode]`),
  `0x100a7387`/`0x100a7393` (per-leaf `this+0x10050[iLeafBack]` / `[iLeafFront]`),
  `0x100a7396 mov [esi+0x10044], ecx` (global head).
- Increments the **portal count** `this+0x10014`: `0x100a739c..0x100a73a3 inc eax; mov [esi+0x10014],eax`
  (this is the "%i portals" of the final Portalized log).

### 0.2 Marker `0xa7870` (pass-B PF_Portal callback) — claims fragments as ZONE portals
Pass B walks the tree; for every node in a coplanar chain whose **surf** has `PF_Portal`
(`0x100a9870 test dword ptr [eax+4], 0x4000000` — PolyFlags is at **surf+0x04** in memory), it
stores that node's surf index into `this+0x10040` (`0x100a98a7 mov eax,[edi+0x1c]` /
`0x100a98aa mov [ebx+0x10040], eax`), bumps the zone-portal count `this+0x10034`
(`0x100a989a..0x100a98a1`), re-derives the portal node's polygon
(`0x100a9890 call [eax+0x1f8]` = GEditor->bspNodeToFPoly), and filters it through the tree with
callback `0xa7870`. The callback, for each leaf pair `(A,B)` the filter reports:
```
0x100a78b4  mov ecx, [edx+0x10044]          ; walk the GLOBAL fragment list
0x100a78c4  mov eax, [ecx+0x1d8]
0x100a78ca  cmp eax, esi / jne +             ; rec.iLeaf == (A,B) ...
0x100a78ce  cmp [ecx+0x1dc], edi / je hit
0x100a78d6  cmp eax, edi / jne next          ; ... or (B,A)  (UNORDERED pair match)
0x100a78da  cmp [ecx+0x1dc], esi / jne next
hit:
0x100a78e2  mov eax, [edx+0x10040]           ; the PF_Portal surf index
0x100a78e8  mov [ecx+0x1fc], eax             ; CLAIM: fragment is a zone portal
0x100a78ee  ...inc [edx+0x10038]             ; fragment count ("%i fragments")
0x100a78fb  mov ecx, [ecx+0x1e4] / jmp       ; continue: EVERY matching record is claimed
```
**So the portal test pass C uses is: "was this leaf-boundary fragment geometrically overlapped by a
PF_Portal (0x04000000) surface's polygon"** — recorded as `rec+0x1fc != -1`. It is keyed on the
unordered leaf pair, not on node flags.

### 0.3 Initial leaf labels (pass A, `0xa7760`) — leaf.iZone starts as the leaf's OWN INDEX
Pass A recursively propagates "outside" down the tree (`0x100a77ba call 0x100a89a0` per side) and,
at an empty terminal side, appends a new `FBspLeaf`:
```
0x100a77db  mov eax, [ecx+0xdc]              ; Leaves.Num  (BEFORE the append)
0x100a77e1  mov [ebp-0x34], eax              ; leaf.iZone     = Leaves.Num == its own index
0x100a77e4  mov dword ptr [ebp-0x30], -1     ; leaf.iPermeating = -1
0x100a77eb  mov dword ptr [ebp-0x2c], -1     ; leaf.iVolumetric = -1
0x100a77f2  mov dword ptr [ebp-0x28], -1     ; leaf.iExclusive  = 0xffffffff_ffffffff (u64)
0x100a77f9  mov dword ptr [ebp-0x24], -1
0x100a7804  add ecx, 0xd8 / call 0x100a7260  ; Model.Leaves.AddItem(leaf) -> index
0x100a780f  mov [edi+esi*4+0x38], eax        ; node.iLeaf[side] = new index
```
This "label = own index" invariant is what makes pass C's renumbering correct (see §2 analysis).
`FBspLeaf` stride is 0x14 (5 dwords); `iZone` is dword +0 (indexing everywhere is `lea r,[i+i*4]`,
`[Data + r*4]`).

---

## 1. `0xa93c0` — the zone setter itself (full decode)

**Role:** merge leaf zone-labels across every NON-portal boundary fragment, compact the surviving
labels to 0..N-1, log "Found %i zones", remap labels to engine zone numbers `1..63` (mod-63 wrap),
and write `Model->NumZones = clamp(N+1, 1, 64)` at UModel+0x100.

Signature: `void FEditorVisibility::AssignZones()` — thiscall, no params, no recursion.
Callees: only the debugf import `[0x100ce768]` and FMemMark boilerplate
(`[0x100ce508]` GMem mark at entry `0x100a93f7-0x100a9408`, pop `[0x100ce52c]` at `0x100a955b`;
the function allocates nothing itself — pure RAII noise).

### Pseudo-C (faithful)
```c
void AssignZones() {                             // this = FEditorVisibility, ebx
  FMemMark mark(GMem);                           // boilerplate

  // ---- PHASE 1: union — merge across every NON-portal fragment -------------
  for (FPortalRec* p = this->PortalList /*+0x10044*/; p; p = p->NextGlobal /*+0x1e4*/) {
      if (p->iZonePortalSurf /*+0x1fc*/ != -1) continue;    // portal fragment: leaves stay split
      INT A = Model->Leaves[p->iLeaf[0] /*+0x1d8*/].iZone;  // current label, front side
      INT B = Model->Leaves[p->iLeaf[1] /*+0x1dc*/].iZone;  // current label, back side
      for (INT j = 0; j < Model->Leaves.Num; j++)           // relabel WHOLE class A -> B
          if (Model->Leaves[j].iZone == A)
              Model->Leaves[j].iZone = B;
  }

  // ---- PHASE 2: compact labels to dense 0..NumClasses-1 --------------------
  INT n = 0;                                                // edi
  for (INT i = 0; i < Model->Leaves.Num; /* i advances below */) {
      INT next = i + 1;
      if (Model->Leaves[i].iZone < n) { i = next; continue; }  // already renumbered (final ids < n)
      for (INT j = next; j < Model->Leaves.Num; j++)           // rewrite the rest of the class
          if (Model->Leaves[j].iZone == Model->Leaves[i].iZone)
              Model->Leaves[j].iZone = n;
      Model->Leaves[i].iZone = n;                              // NOTE: rep written AFTER the scan
      n++;  i = next;
  }

  debugf(..., 0x2f8, L"Found %i zones", n);                    // n = class count, zone 0 excluded

  // ---- PHASE 3: map to engine zone numbers 1..63 ----------------------------
  for (INT i = 0; i < Model->Leaves.Num; i++)
      Model->Leaves[i].iZone = (Model->Leaves[i].iZone % 63) + 1;   // idiv by 0x3f, +1

  Model->NumZones /* UModel+0x100 */ = Min(Max(n + 1, 1), 64);
}
```

### Instruction evidence, phase by phase

**Phase 1 — the merge loop (`0x100a940b`–`0x100a9478`):**
```
0x100a940b  mov edi, [ebx+0x10044]           ; p = global fragment list head
0x100a9411  test edi, edi / je phase2
0x100a9415  cmp dword ptr [edi+0x1fc], -1    ; iZonePortalSurf
0x100a941c  jne next_rec                     ; != -1  =>  ZONE PORTAL: do NOT merge
0x100a941e  mov esi, [ebx+0x10]              ; Model
0x100a9421  mov ecx, [esi+0xd8]              ; Leaves.Data
0x100a9427  mov eax, [edi+0x1d8]             ; p->iLeaf[0]
0x100a942d  lea eax, [eax+eax*4]             ; *5  (leaf stride 0x14)
0x100a9430  mov eax, [ecx+eax*4]             ; A = Leaves[iLeaf0].iZone   (leaf +0)
0x100a9433  mov [ebp-0x18], eax
0x100a9436  mov eax, [edi+0x1dc]             ; p->iLeaf[1]
0x100a943f  mov eax, [ecx+eax*4]             ; B = Leaves[iLeaf1].iZone
0x100a9442  mov [ebp-0x1c], eax
0x100a9445  xor edx, edx                     ; j = 0
0x100a944a  cmp edx, [esi+0xdc] / jge next_rec   ; j < Leaves.Num
0x100a945e  cmp [eax+ecx*4], ebx             ; Leaves[j].iZone == A ?   (ebx=A here)
0x100a9464  jne skip
0x100a9469  mov [eax+ecx*4], esi             ; Leaves[j].iZone = B      (esi=B here)
0x100a946f  inc edx / jmp
0x100a9472  mov edi, [edi+0x1e4]             ; p = p->NextGlobal
0x100a9478  jmp 0x100a9411
```
Merge direction: **class-label A (front-leaf side) is renamed to B (back-leaf side)**, scanning the
entire Leaves array each time (O(portals × leaves), no union-find ranks). A and B are read ONCE per
record, before the scan.

**Phase 2 — compaction (`0x100a947a`–`0x100a94ec`):**
```
0x100a947a  xor edi, edi                     ; n = 0 (new-zone counter)
0x100a9481  ... ecx = i                      ; leaf cursor
0x100a948a  cmp ecx, [esi+0xdc] / jge phase_log
0x100a949e  cmp [eax+ecx*4], edi             ; Leaves[i].iZone < n ?  (signed jl)
0x100a94a1  jl  0x100a94ea                   ;   -> already final-numbered, i++
0x100a94a9  eax = i*5                        ; class label address Leaves[i].iZone
0x100a94b5  cmp edx, [esi+0xdc] / jge done_scan  ; j = i+1 .. Num
0x100a94c6  mov ecx, [ecx]                   ; Leaves[j].iZone
0x100a94c8  cmp ecx, [ebx+eax*4]             ; == Leaves[i].iZone ?
0x100a94cb  jne skip
0x100a94d0  mov [eax], edi                   ; Leaves[j].iZone = n
0x100a94d8  inc edx / jmp
0x100a94db  mov [ebx+eax*4], edi             ; Leaves[i].iZone = n   (AFTER the j-scan)
0x100a94de  inc edi                          ; n++
0x100a94e8  jmp 0x100a9481                   ; resume at i+1
```
*Correctness analysis (not an instruction — flagged as reasoning):* the `jl n` skip is only sound
because an unprocessed class's label always equals the index of one of its OWN members that still
carries it (labels start as own-index per §0.3, and merges copy a member's label), and that member
index is ≥ i ≥ n. If pass B ever seeded different labels this phase would mis-merge — a Rust port
must keep the own-index seeding.

**The log (`0x100a94ee`–`0x100a9506`):**
```
0x100a94ee  push edi                         ; n = compacted class count
0x100a94ef  push 0x100fe6f0                  ; L"Found %i zones"   (read from .rdata, verified)
0x100a94f4  push 0x2f8                       ; log-category/name id (same 0x2f8 as other zoning logs)
0x100a94f9  mov eax,[0x100ce71c] / push [eax]
0x100a9500  call dword ptr [0x100ce768]      ; debugf
```
**The printed counter is the compacted class count `n` — BEFORE the +1 for zone 0 and BEFORE the
mod-63 wrap.** `NumZones` stored below is `n+1` (clamped), not the printed value.

**Phase 3 — remap to 1..63 (`0x100a9509`–`0x100a9539`):**
```
0x100a950e  mov dword ptr [ebp-0x2c], 0x3f   ; divisor = 63
0x100a9515  mov eax, [ebx+0x10]              ; Model
0x100a9518  cmp esi, [eax+0xdc] / jge store_numzones
0x100a952c  mov eax, [ecx]                   ; Leaves[i].iZone (compacted id)
0x100a952e  cdq
0x100a952f  idiv dword ptr [ebp-0x2c]        ; edx = id % 63
0x100a9532  inc edx                          ; +1  -> 1..63
0x100a9533  mov [ecx], edx                   ; Leaves[i].iZone = final zone number
```
Zone number **0 is reserved** (solid/outside — a `-1` leaf side reads as zone 0 downstream, §3.1);
if more than 63 classes exist, classes 63,126,… **alias back onto zones 1..63** (silent wrap, no
error).

**NumZones (`0x100a953b`–`0x100a9552`):**
```
0x100a953b  inc edi                          ; n+1  (zone 0 counts)
0x100a953c  cmp edi, 1 / jge +
0x100a9541  mov ecx, 1                       ;   floor 1 (dead: edi>=1 always)
0x100a9548  mov ecx, 0x40
0x100a954d  cmp edi, ecx / cmovl ecx, edi    ; min(n+1, 64)
0x100a9552  mov [eax+0x100], ecx             ; Model->NumZones   == UModel+0x100  (CONFIRMED)
```

### Complete write-set of pass C
| target | value | where |
|---|---|---|
| `Leaves[j].iZone` (every leaf, multiple times) | merged label → compact id → `(id%63)+1` | 0x100a9469, 0x100a94d0/0x100a94db, 0x100a9533 |
| `Model+0x100` (`NumZones`) | `min(max(classCount+1,1),64)` | 0x100a9552 |

Nothing else. No node, surf, ZoneMask, Zones[], or FEditorVisibility field is written.

---

## 2. Where the REST of the zone state is written (for the port's full chain)

### 2.1 Node `iZone[0]/iZone[1]` — pass D `0xa7400` + callback `0xaa220`
Pass D recurses the tree (front `+0x24` then back `+0x20`; outside propagated with
`node->IsCsg(4)`-style test `0x100a746b call 0x10033b80` — outside_front = Outside || IsCsg,
outside_back = Outside && !IsCsg, `0x100a74b5-0x100a74cd`). For every node in each coplanar chain
that is NOT `NF_IsNew` (`0x100a7512 test byte ptr [eax+esi+0x37], 0x20 / jne skip`), it re-derives
the node polygon (`0x100a752e call [eax+0x1f8]` bspNodeToFPoly) and re-filters it through the tree
(`0x100a7582 call 0x100a9030`, callback `0x100aa220`). The callback:
```
0x100aa27a  push 2                            ; ENodePlace = NODE_PLANE
0x100aa276  or eax, 0x20                      ; NodeFlags | NF_IsNew
0x100aa27e  call dword ptr [edx+0x224]        ; GEditor vtbl+0x224 = bspAddNode (inferred from
                                              ;   arg shape (Model,iNode,2,NF,poly) — 📖 medium conf.)
0x100aa298..0x100aa2bc  dot = OrigNode.Plane.xyz · poly.Normal   (SSE, plane at node+0, N at poly+0xc)
0x100aa2c5  comiss xmm0, xmm1 / seta dl       ; side = (0.0 > dot)  i.e. 1 if poly faces AGAINST plane
0x100aa2ce  cmp eax,-1  -> ecx = 0            ; solid side (iLeaf==-1) => zone 0
0x100aa2dd  mov eax,[eax+0xd8] ... mov ecx,[eax+ecx*4]   ; else ecx = Leaves[iLeaf].iZone  (pass C's result!)
0x100aa2ee  mov [eax+edx+0x34], cl            ; newNode.iZone[side]   = zone of one side
0x100aa310  xor edx,1
0x100aa316  mov [edx+esi+0x34], cl            ; newNode.iZone[side^1] = zone of the other side
```
Then back in `0xa7400`: if fragments were created (`0x100a7590 cmp [ebx+0x5c], edi / jle`), it
gathers the nonzero iZone bytes across the new fragment nodes (`0x100a75da mov al,[eax+ecx+0x34]`),
checks they are all consistent (`0x100a7629 cmp eax,[ebp+ecx*4-0x204] / cmovne edx,0`); if
consistent it ZEROES the fragments' NumVertices (`0x100a7663 mov byte ptr [eax+ecx+0x36], 0`) and
copies the pair onto the ORIGINAL node (`0x100a7693 mov [eax+edx+0x34], cl` — **the durable node
iZone write**); if inconsistent it zeroes the ORIGINAL node's NumVertices (`0x100a76a3`) and keeps
only fragments bordering a real zone (`0x100a76c4/0x100a76cb` both-zero check → `0x100a76d2` zero
NumVertices). I.e. a portal face spanning several zones is replaced by its per-zone fragments.

### 2.2 Node `ZoneMask` (u64 @ node+0x10) — pass E `0xa8850` (cdecl `(UModel*, INT iNode)`)
Pure recursive OR-accumulate:
```
0x100a8896  mov al, [ebx+0x34]  / test al,al / je    ; iZone[0]==0 contributes NO bit
0x100a88a4  bts esi, eax  (+0x100a88a7..0x100a88b2 64-bit shift emul)   ; mask |= 1<<iZone[0]
0x100a88c3  mov al, [ebx+0x35]  ...                  ; mask |= 1<<iZone[1]  (if nonzero)
0x100a88ef  mov eax,[ebx+0x24] / call self           ; mask |= recurse(iChild[1]) (front)
0x100a890b  mov eax,[ebx+0x20] / call self           ; mask |= recurse(iChild[0]) (back)
0x100a8929  mov eax,[ebx+0x28] / call self           ; mask |= recurse(iPlane chain)
0x100a8947  mov [ebx+0x10], esi / mov [ebx+0x14], edi   ; node.ZoneMask = mask  (u64)
```
Note: **zone 0 sets no ZoneMask bit** — bit k means "zone k is at/below this node", k=1..63.

### 2.3 `Zones[].Connectivity` — pass F `0xa7960`
`FZoneProperties` stride **0x18**; array base UModel+0x104 (`ZoneActor` +0, pad +4,
`Connectivity` u64 +8 → Model+0x10c+i*0x18, `Visibility` u64 +0x10 → Model+0x114+i*0x18).
- init `Connectivity[i] = 1<<i` for i in 0..64: `0x100a79be mov [eax+ecx*8+0x10c], edx` /
  `0x100a79c5 mov [eax+ecx*8+0x110], esi` (ecx = i*3, so *8 → i*0x18).
- for every node whose surf has PF_Portal (`0x100a79f7 test dword ptr [ecx+4], 0x4000000`):
  `Connectivity[iZone[1]] |= 1<<iZone[0]` (`0x100a7a00..0x100a7a35`) and
  `Connectivity[iZone[0]] |= 1<<iZone[1]` (`0x100a7a3b..0x100a7a76`). Symmetric, zone 0 included
  here (no zero-test on the byte — solid-side 0 just ORs bit0 into zone0's row and vice versa).

### 2.4 `Zones[].ZoneActor` — pass G `0xa7e60`
Clears `Zones[i].ZoneActor = 0` for i in 0..64 (`0x100a7ecf mov [eax+ecx*8+0x104], edi`), then for
each Level actor passing `0xa6930` (ZoneInfo-class test) computes its point-region (call through
`[0x100ceaa4]`), writes the actor's Region struct (actor+0x88, zone byte +0x90,
`0x100a7fd5/0x100a7fe0`), and if that zone's slot is empty binds it:
`0x100a801f mov [ecx+eax*8+0x104], edi` (first ZoneInfo in a zone wins; also counts dups/unbound at
ebp-0x14/-0x38/-0x34). Remainder of the function is ambient-zone scaling (16384-uu ray probing,
`0x100aac50`), not zone membership. `Visibility` u64s were not seen written in the ranges read —
LOW CONFIDENCE where/if they are filled (possibly later in 0xa7e60's unread tail or left =
Connectivity by another pass); does not affect zone membership.

---

## 3. Algorithm summary for the Rust port (membership-exact)

1. **Pass A** creates one `FBspLeaf` per empty terminal side, `iZone = own index`,
   `iPermeating/iVolumetric = -1`, `iExclusive = ~0`; `node.iLeaf[side]` = index.
2. **Pass B** emits one fragment record per boundary polygon piece with leaves on BOTH sides
   (`iLeaf[0]`=front, `iLeaf[1]`=back, `+0x1fc = -1`), and for every PF_Portal-surf node polygon,
   claims every record matching that polygon's traversed (unordered) leaf pairs:
   `+0x1fc = portal surf index`.
3. **Pass C (this function)**:
   a. For each record with `+0x1fc == -1` (non-portal boundary): rewrite every leaf whose label ==
      `label(front leaf)` to `label(back leaf)`. (Portal-claimed records are skipped → leaves on
      opposite sides of a claimed portal stay in different classes *unless* connected elsewhere.)
   b. Compact labels to dense 0..n-1 by first-member order over the Leaves array.
   c. `debugf("Found %i zones", n)`.
   d. `leaf.iZone = (compactId % 63) + 1` — zones are 1-based, wrap silently past 63.
   e. `Model.NumZones (UModel+0x100) = min(n+1, 64)`.
4. **Pass D** stamps node `iZone[0/1]` bytes by re-filtering each pre-portalization node's polygon:
   fragment side facing WITH the node plane gets the front-leaf's zone, AGAINST gets flipped
   (`side = dot(nodePlane.N, fragN) < 0`), solid (-1) side = zone 0; multi-zone portal faces get
   split into per-zone fragment nodes (originals zeroed out via NumVertices=0).
5. **Pass E** fills node `ZoneMask` = OR of `1<<iZone[k]` (k where iZone[k]≠0) over self + both
   children + coplanar chain.
6. **Pass F** fills `Zones[i].Connectivity = 1<<i` then symmetric OR per PF_Portal node's iZone pair.
7. **Pass G** binds `Zones[z].ZoneActor` = first ZoneInfo actor whose point-region is zone z.

### Port-critical gotchas
- Zone numbers are **(compactId mod 63) + 1**, NOT compactId — a >63-zone map aliases, it doesn't clamp.
- The **"Found %i zones" number ≠ NumZones**: log prints n (classes), stored NumZones = min(n+1,64).
- Merge/renumber order-sensitivity: final numbering depends on (a) the global fragment-list ORDER
  (records are pushed at the HEAD in 0xa72a0, so the list is reverse creation order of pass B's
  recursion: front subtree first at each node — see 0xa97e1 front recursed before 0xa9815 back) and
  (b) the A→B merge direction. Membership is order-independent; the zone NUMBERS are not. For
  number-exact parity reproduce pass B's traversal order (front child, then back child, then the
  node's own coplanar chain).
- A fragment with a solid side (either leaf -1) creates NO record — solid never merges anything.
- Portal claiming (0xa7870) requires the portal polygon to actually reach the same leaf-PAIR via the
  filter; a PF_Portal face flush against solid claims nothing.

## 4. Open questions / low confidence
- `vtbl+0x224` = bspAddNode is inferred from the argument shape (Model, iParent, NODE_PLANE=2,
  NodeFlags|0x20, FPoly*) and the known neighboring slots; not cross-verified against an export name.
- `Zones[].Visibility` (Model+0x114+i*0x18) writer not located in the ranges disassembled (pass F
  writes only Connectivity; pass G's tail beyond ~0x100a81a1 was not fully read). Membership-neutral.
- `0x2f8` pushed to debugf assumed to be a log-category/name index (same constant at the 0x100a8148
  debugf) — not semantically load-bearing.
- The filter drivers `0xa9970` (pass B stage 1) and `0xa9030` (portal/zone-face refilter) were not
  decoded to instruction level here (they are pass-B assignment territory); their contract used
  above — "clip a polygon down the tree, invoke callback with (poly-fragment, iLeafFront, iLeafBack,
  iNode)" — is inferred from both callbacks' signatures and the pass-B call sites. The leaf-pair
  ARG ORDER (which of +0xc/+0x10 is front) is consistent between producer and consumer either way
  for membership (merge is symmetric in the classes), but matters for exact zone NUMBERING; verify
  against the pass-B decode.
