# RE output — FEditorVisibility ctor/dtor + allocator + field map (Editor.dll, UED22)

Agent: ctor-decode. Binary: `uned/UED22/Editor.dll`, ImageBase 0x10000000. All claims anchored
to quoted instructions; disassembly via `adis.py`.

## Headline corrections to the brief

1. **The ctor does NOT extend to 0xa6c70.** It ends at 0xa6a6b (`ret 0xc`). The space up to the
   dtor holds EH funclets plus THREE separate helper functions:
   - **0xa6ab0 — FPortal ctor** (thiscall, 8 args, `ret 0x20`) — see below. FPortal = FPoly +
     0x28-byte tail = **0x200 bytes**.
   - **0xa6b30 — bit-array ctor** (vtable `0x100d0a1c`; TArray at +0x28 zeroed, `+0x34 = NumBits`,
     then `AddZeroed((NumBits+31)>>5)` via imports `[0x100ce618]`/`[0x100ce5ec]`).
   - **0xa6c00 — triangular/symmetric bit-matrix ctor** (vtable `0x100d0a74`): calls 0xa6b30 with
     `n*(n+1)/2` bits (`lea eax,[esi+1]; imul eax,esi; shr eax,1` @0xa6c2d), stores side `n` at
     +0x38. (Likely the zone-connectivity scratch used elsewhere; not referenced by the ctor.)
2. **sizeof(FEditorVisibility) = 0x10058** (not ~0x10060). Proof: `UEditorEngine::TestVisibility`
   @0xaa940 stack-probes `mov eax,0x10064; call 0x100ac880` (@0xaa952) and constructs at
   `lea ecx,[ebp-0x1006c]` (@0xaa98d); locals occupy `[ebp-0x14..ebp-4]`, so the object spans
   exactly `ebp-0x1006c .. ebp-0x14` = 0x10058 bytes. No code anywhere in .text references
   offsets 0x10058/0x1005c/0x10060 (byte-scan of the section).
3. **TestVisibility takes 4 args (`ret 0x10`) but drops the 4th**: it forwards only
   `(Level=[ebp+8], Model=[ebp+0xc], A=[ebp+0x10])` to the ctor (@0xaa986–0xaa993). And the ctor
   stores A at +0x1003c, which is **never read again anywhere in .text** (only other disp-scan
   hits 0x8a3d5/0x8a504/0xa251d are unrelated structs — checked 0xa251d: it is
   `test dword ptr [eax+0x3c], 0x100` on a different object). So both trailing TestVisibility
   params are dead in this build.

---

## 1) FEditorVisibility::FEditorVisibility @ RVA 0xa6970 (ends 0xa6a6b, `ret 0xc`, thiscall, 3 args)

**Role:** captures an FMemMark on the global editor memory stack `GMem`, stores the
Level/Model pointers, and zeroes the counters/list-heads. It does **NOT** touch the 64 KB middle
region (left uninitialized — it is a stack, valid only up to its depth counter) and does
**NOT write anything to the Model** (only stores the pointer).

Pseudo-C (args: `this=ecx`, `[ebp+8]=Level`, `[ebp+0xc]=Model`, `[ebp+0x10]=A`):

```c
FEditorVisibility::FEditorVisibility(ULevel* Level, UModel* Model, INT A /*dead*/)
{
    // inline FMemMark on GMem (Core.dll data export ?GMem@@3VFMemStack@@A at IAT [0x100ce508])
    Mark.Mem      = &GMem;          // this+0x00
    Mark.saved0   = GMem.field_0;   // this+0x04  = *(GMem+0x00)
    Mark.saved0c  = GMem.field_0c;  // this+0x08  = *(GMem+0x0c)
    this->Level   = Level;          // this+0x0c
    this->Model   = Model;          // this+0x10
    // NodeStack[0x4000] at +0x14 .. +0x10013: NOT initialized
    this->NumPortals      = 0;      // +0x10014
    // +0x10018: never written or read by ANY code — alignment hole
    this->StackDepth      = 0;      // +0x1001c   (zeroed here; heavy use in pass B)
    this->dead20 = dead24 = dead28 = dead2c = dead30 = 0;  // +0x10020..+0x10030: zeroed, never used again
    this->NumZonePortals  = 0;      // +0x10034
    this->NumFragments    = 0;      // +0x10038
    // +0x1003c = A (stored @0xa6a19-0xa6a1c, never read)
    // +0x10040: NOT initialized (scratch: current zone-portal iSurf, written before first read in pass B)
    this->FirstPortal     = 0;      // +0x10044   global FPortal* list head
    this->dead48          = 0;      // +0x10048   zeroed, never used again
    this->NodePortals     = 0;      // +0x1004c   FPortal** (per-node heads), alloc'd in portalize
    this->LeafPortals     = 0;      // +0x10050   FPortal** (per-leaf heads), alloc'd in portalize
    // +0x10054: NOT initialized in ctor (per-leaf INT-list array; portalize allocs it)
}
```

Evidence (every write, verbatim):
```
0x100a699b  mov eax, [0x100ce508]           ; &GMem (IAT ?GMem@@3VFMemStack@@A)
0x100a69a0  mov [ecx], eax                  ; +0x00 Mark.Mem
0x100a69a2  mov edx, [0x100ce508]
0x100a69a8  mov eax, [edx]                  ; GMem+0
0x100a69aa  mov [ecx+4], eax                ; +0x04
0x100a69ad  mov eax, [edx+0xc]              ; GMem+0xc
0x100a69b0  mov [ecx+8], eax                ; +0x08
0x100a69b3  mov eax, [ebp+8]  ; Level
0x100a69b6  mov [ecx+0xc], eax
0x100a69b9  mov eax, [ebp+0xc] ; Model
0x100a69bc  mov [ecx+0x10], eax
0x100a69bf..0x100a6a0f  mov dword [ecx+0x10014/1001c/10020/10024/10028/1002c/10030/10034/10038], 0
0x100a6a19  mov eax, [ebp+0x10]
0x100a6a1c  mov [ecx+0x1003c], eax          ; A (dead)
0x100a6a22..0x100a6a40  mov dword [ecx+0x10044/10048/1004c/10050], 0
0x100a6a58  mov eax, ecx                    ; returns this
0x100a6a6b  ret 0xc
```
No other memory writes; nothing written through `[ecx+0x10]` → **Model untouched by ctor**.

## 2) dtor @ RVA 0xa6c70 (ends 0xa6cc0)

**Role:** single action — `FMemMark::Pop()` on the inline mark at offset 0, releasing every
FMemStack allocation made during the visibility build (all FPortals, all three pointer arrays).

```
0x100a6c9b  mov dword ptr [ebp-4], 0
0x100a6ca2  call dword ptr [0x100ce52c]     ; IAT = Core.dll ?Pop@FMemMark@@QAEXXZ, ecx = this (mark at +0)
```
ecx is untouched between entry and the call (EH prologue only clobbers eax), so `this` == `&Mark`.
No Model/Level writes. Nothing else.

## 3) Allocator @ RVA 0x31450 (cdecl, 5 args, plain `ret`)

**Role:** zero-initializing FMemStack array allocator — `New<T>(Mem, Count)` with memset.

```
0x10031453  mov ecx, [ebp+0xc]              ; arg2 = FMemStack*  (callers pass [0x100ce508] = &GMem)
0x10031458  mov edi, [ebp+8]                ; arg1 = element size
0x1003145b  imul edi, [ebp+0x14]            ; arg4 = count  → edi = bytes
0x1003145f  push [ebp+0x18]                 ; arg5 = alignment (callers pass 0x10)
0x10031462  push edi
0x10031463  call dword ptr [0x100ce530]     ; Core.dll ?PushBytes@FMemStack@@QAEPAEHH@Z (thiscall, ecx=Mem)
0x1003146c  push 0 / push esi / call 0x100ae140 ; memset(ptr, 0, bytes)  (0xae140 = classic SSE memset: imul eax,eax,0x1010101)
0x10031477  mov eax, esi                    ; returns pointer
```
- Signature: `void* MemZeroedArray(INT ElemSize, FMemStack* Mem, INT unused, INT Count, INT Align)`.
- **arg3 (`[ebp+0x10]`, the literal `1` at call sites) is never read** — vestigial.
- **YES zero-init** (memset to 0 after PushBytes).
- Allocates from whatever FMemStack is passed; all three visibility call sites pass `&GMem`
  (`push dword ptr [0x100ce508]` @0xaa492/0xaa4b2/0xaa4d7) — hence the dtor's single
  `FMemMark::Pop` frees them.
- NOTE: raw portal allocation does NOT go through this helper: AddPortal calls `PushBytes(0x200,
  0x10)` directly (@0xa72ec–0xa72f9) — **portal memory is NOT zeroed**; the FPortal ctor
  initializes every field it has.

---

## 4) PRIMARY DELIVERABLE — complete FEditorVisibility field map (sizeof 0x10058)

| offset | type | meaning | evidence |
|---|---|---|---|
| +0x00 | `FMemStack*` | FMemMark.Mem = `&GMem` | ctor 0xa699b–0xa69a0 |
| +0x04 | ptr | FMemMark saved `*(GMem+0)` | ctor 0xa69a8–0xa69aa |
| +0x08 | ptr | FMemMark saved `*(GMem+0xc)` | ctor 0xa69ad–0xa69b0; dtor `FMemMark::Pop` with ecx=this |
| +0x0c | `ULevel*` | Level | ctor 0xa69b3 |
| +0x10 | `UModel*` | Model | ctor 0xa69b9 |
| **+0x14 .. +0x10013** | **`INT NodeStack[0x4000]`** (16384 × 4 B = exactly 0x10000, ends flush at +0x10014) | **explicit root→current-node path stack** used by the recursive portal pass B (0xa9750). Entry = `iNode`, with **bit 0x40000000 OR'd in when descending the BACK child (iChild[0], +0x20)**; plain when descending FRONT (iChild[1], +0x24). Uninitialized by ctor; valid only up to StackDepth. | 0xa97e8 `mov eax,[ebx+0x1001c]`; 0xa97ee `mov [ebx+eax*4+0x14], esi`; 0xa97f2 `inc [ebx+0x1001c]` … recurse front; 0xa981c–0xa982a `or ecx,0x40000000; mov [ebx+eax*4+0x14],ecx` … recurse back; 0xa9809/0xa9845 `dec [ebx+0x1001c]` |
| +0x10014 | INT | **NumPortals** (the "%i portals" of the Portalized log). Incremented once per AddPortal even when the FMemStack returns NULL (alloc-fail path still counts, @0xa7353→0xa739c). | inc @0xa739c–0xa73a3; pushed for debugf @0xaa577 |
| +0x10018 | — | **hole/padding — no instruction in .text references it** (byte-scan) | scan |
| +0x1001c | INT | **StackDepth** for NodeStack (push/pop counter) | see NodeStack row |
| +0x10020..+0x10030 | 5×INT | **dead** — zeroed by ctor, never referenced again anywhere in .text (byte-scan; the stray 0x55f1b hit on 0x10028 is another function/struct) | ctor only |
| +0x10034 | INT | **NumZonePortals** — ++ in pass B when the current node's surf has `PF_Portal` (`test dword ptr [eax+4], 0x4000000` @0xa9870 on `Surfs.Data + iSurf*0x40`) and `GEditor->bspNodeToFPoly` (vtbl +0x1f8, @0xa9890) returns nonzero | 0xa989a–0xa98a1 |
| +0x10038 | INT | **NumFragments** — ++ in matcher 0xa7870 per existing portal whose leaf pair equals the zone-portal's leaf pair | 0xa78ee–0xa78f5 |
| +0x1003c | INT | ctor's 3rd arg (TestVisibility arg A) — **stored, never read** (dead) | ctor 0xa6a19; .text scan |
| +0x10040 | INT | scratch: **iSurf of the zone-portal currently being matched** (set in pass B @0xa98a7-0xa98aa from `node+0x1c`, read in matcher 0xa7870 @0xa78e2). NOT ctor-initialized (written before first read). | quoted in §5/§6 |
| +0x10044 | `FPortal*` | **global portal list head** (chained via portal+0x1e4). Consumers: AddPortal prepends; matcher 0xa7870 walks it; pass C 0xa93c0 walks it to flood zones (@0xa940b). | 0xa7396; 0xa78b4; 0xa940b |
| +0x10048 | INT | **dead** — zeroed by ctor, never referenced again (byte-scan; 0x65b28 hit is another struct) | ctor only |
| +0x1004c | `FPortal**` | **per-NODE portal list heads**, `MemZeroedArray(4, GMem, 1, Nodes.Num*2+0x100, 0x10)` — over-sized because portal filtering splits nodes during pass B. Chained via portal+0x1f0. | alloc @0xaa4c5–0xaa4e7 (`lea eax,[eax*2+0x100]` on `[Model+0x5c]`); AddPortal head-update @0xa7372–0xa737b |
| +0x10050 | `FPortal**` | **per-LEAF portal list heads**, `MemZeroedArray(4, GMem, 1, Leaves.Num, 0x10)`. One shared array: AddPortal writes the new portal into BOTH its leaves' slots (chain via portal+0x1e8 for leaf-arg1, +0x1ec for leaf-arg2). Read by pass G (0xa8440). | alloc @0xaa485–0xaa49f (`push [eax+0xdc]` = Leaves.Num); AddPortal @0xa737e–0xa7393 |
| +0x10054 | `INT*` (per-leaf) | second per-leaf array, same size/alloc (@0xaa4a5–0xaa4bf): per-leaf singly-linked light/actor index lists built by the per-light pass 0xa6d00 and the volumetric pass 0xa9290, drained into `Model.Lights` by portalize steps 15–16. NOT ctor-initialized (portalize allocates before use). | alloc quoted; reads @0xa9380/0xa93a1/0xaa6ee… |

**sizeof = 0x10058** (see Headline correction 2).

### The FPortal record (allocated per portal, 0x200 bytes on GMem, ctor 0xa6ab0)

`FPoly` copy at +0 (via Engine.dll import `??0FPoly@@QAE@ABV0@@Z` @0xa6ab9), then tail:

| off | meaning | evidence |
|---|---|---|
| +0x1d8 | iLeaf (AddPortal arg2; leaf on one side) | 0xa6abf–0xa6ac2; matcher compares @0xa78c4 |
| +0x1dc | iLeaf (AddPortal arg3; other side) | 0xa6ac8–0xa6acb |
| +0x1e0 | iNode the portal lies on | 0xa6ad1–0xa6ad4 (arg4) |
| +0x1e4 | next in GLOBAL list (old this+0x10044) | 0xa6ada–0xa6add; walk @0xa78fb `mov ecx,[ecx+0x1e4]` |
| +0x1e8 | next in leaf-list of iLeaf@+0x1d8 (old +0x10050[leaf1]) | 0xa6ae3–0xa6ae6 (arg pushed from `[ecx+edi*4]` @0xa732b) |
| +0x1ec | next in leaf-list of iLeaf@+0x1dc (old +0x10050[leaf2]) | 0xa6aec–0xa6aef (arg from `[ecx+ebx*4]` @0xa7328) |
| +0x1f0 | next in node-list (old +0x1004c[iNode]) | 0xa6af5–0xa6af8 |
| +0x1f4 | WORD, zeroed — no user found in the cluster (open) | 0xa6b00 |
| +0x1f8 | DWORD, zeroed — no user found in the cluster (open) | 0xa6b09 |
| +0x1fc | **iZonePortalSurf**: init -1; matcher 0xa7870 sets it to this+0x10040 (the PF_Portal surf's iSurf) when the portal's leaf pair matches a zone portal. Pass C treats `== -1` as "floodable" (@0xa9415); pass G reads it (@0xa8454/0xa848e/0xa84de). | 0xa6b13; 0xa78e2–0xa78e8 |

### AddPortal callback @0xa72a0 (thiscall, 5 args `ret 0x14`: FPoly*, iLeafA, iLeafB, iNode, +1 unverified)

If either leaf == -1 → no-op. Else `FMemStack::PushBytes(0x200, 0x10)` on GMem
(@0xa72ec–0xa72f9), construct FPortal via 0xa6ab0 chaining all three lists + global list, then
prepend it to all four heads (`+0x1004c[iNode]`, `+0x10050[iLeafA]`, `+0x10050[iLeafB]`,
`+0x10044`) and `++NumPortals` (+0x10014). On PushBytes returning NULL the heads are all set to
NULL and NumPortals is still incremented (@0xa7353–0xa73a3) — alloc-fail truncates the lists.

### Matcher callback @0xa7870 (thiscall, 5 args `ret 0x14`; args at +0xc/+0x10 = leaf pair)

Walks the global portal list; for every portal whose `{+0x1d8,+0x1dc}` equals the given pair in
either order: `portal+0x1fc = this+0x10040; ++this->NumFragments(+0x10038)`. (Called from pass B
via 0xa9030 with fn-ptr 0x100a7870 pushed @0xa98be, after bumping NumZonePortals.)

## 5) What the ctor/dtor do to the Model

**Nothing.** The ctor stores the `UModel*` at +0x10 and performs no write through it; the dtor
only pops the mem mark. All Model mutation happens in the passes (out of scope here; note in
passing, verified: pass F 0xa7960 writes `Model+0x104 + iZone*0x18` zone entries — stride 0x18,
u64 Connectivity at entry+8, i.e. `[Model + zone*24 + 0x10c/0x110]` @0xa79be–0xa79c5 with
`eax=[ebx+0x10]` = Model — confirming the brief's `FZoneProperties Zones[64]` guess with
ZoneActor at entry+0, Model+0x104 = Zones[0]).

## 6) Open questions / low confidence

- FPortal +0x1f4 (WORD) and +0x1f8 (DWORD): zero-initialized, no reader/writer found inside the
  visibility cluster dumps; possibly used by callees I did not fully walk (0xa9030 filter
  internals). LOW PRIORITY — flag to the pass-B/G agents.
- Which of AddPortal's leaf args is "front" vs "back" is decided by the caller 0xa9030 (pass-B
  agent's scope); I label them arg-order only.
- The 5th arg of 0xa72a0/0xa7870 (`ret 0x14` = 5 dwords but only 4 read): consistent with the
  dead-arg pattern seen elsewhere; unverified.
- FMemMark field names (+4/+8 = which FMemStack members): raw offsets `GMem+0`/`GMem+0xc`
  captured; exact Core.dll FMemStack layout not needed since Pop is an import.
- The bit-array classes 0xa6b30/0xa6c00 sit in this function cluster but are not referenced by
  ctor/dtor/portalize-top; they may be used by pass C for zone connectivity — pass-C agent
  should check.
