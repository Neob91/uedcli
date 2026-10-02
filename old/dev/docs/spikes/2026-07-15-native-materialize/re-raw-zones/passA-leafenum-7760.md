# Pass A decode — RVA 0xa7760 (Editor.dll, UED22) — leaf enumeration ("AssignLeaves")

Decoded 2026-07-16 from the binary (capstone via `adis.py`). All addresses are VAs
(ImageBase 0x10000000). Called from portalize @0xaa370 step 5 as
`0xa7760(this=FEditorVisibility, iNode=0, Outside=Model->+0xf0 /*RootOutside*/)`,
immediately after every node's `iLeaf[0..1]` was set to -1 and `Model.Leaves`/`Model.Lights`
were emptied.

---

## Function 0xa7760 — recursive leaf assignment over the BSP front/back tree

**Role (1 sentence):** Depth-first walk of the BSP tree via `iChild[0]` (back) then
`iChild[1]` (front) that, at every NULL child slot whose subspace is *outside* (empty),
appends one new `FBspLeaf` to `Model.Leaves` and stores its index in `node.iLeaf[side]`;
solid NULL-child subspaces get no leaf (iLeaf stays -1).

**Signature (observed):** `void __thiscall FEditorVisibility::PassA(INT iNode, UBOOL Outside)`
— `ecx = this`, `[ebp+8] = iNode`, `[ebp+0xc] = Outside`, `ret 8`. Function body ends at
the `ret 8` @0x100a782e; bytes 0xa7830–0xa785c are its MSVC EH funclets (not code reached
normally), then int3 padding. (The next real function, 0x100a7870, is a separate helper that
walks a linked list at `this+0x10044` and bumps `this+0x10038` — it is NOT called from pass A;
it belongs to the later zone-portal machinery.)

### Pseudo-C (faithful)

```c
void FEditorVisibility::PassA(INT iNode, UBOOL Outside)   // 0xa7760
{
    FBspNode* Node = &Model->Nodes(iNode);        // edi = Model(+0x10)->Nodes.Data(+0x58) + iNode*0x40
    for (INT side = 0; side < 2; side++)          // esi = 0 (BACK/iChild[0]) then 1 (FRONT/iChild[1])
    {
        INT   iChild       = Node->iChild[side];              // [edi + side*4 + 0x20]
        UBOOL ChildOutside = Node->ChildOutside_a89a0(side, Outside, /*ExtraFlags=*/4);
        if (iChild != -1)
        {
            PassA(iChild, ChildOutside);                      // recurse, same this
        }
        else if (ChildOutside)                                // NULL child AND empty space
        {
            FBspLeaf Leaf;                                    // local @ ebp-0x34, 0x14 bytes
            Leaf.iZone       = Model->Leaves.Num;             // == the index it will get
            Leaf.iPermeating = -1;
            Leaf.iVolumetric = -1;
            Leaf.iExclusive  = 0xFFFFFFFFFFFFFFFFull;         // two dwords of -1
            Node->iLeaf[side] = TArray_FBspLeaf_AddItem_a7260(&Model->Leaves, &Leaf);
            // returns Leaves.Num - 1 after the append == the pre-append Num
        }
        // NULL child + solid: nothing (iLeaf[side] stays -1 from portalize step 2)
    }
}
```

### Evidence (key instruction runs)

Node pointer + loop:
```
0x100a7797  mov edi, [ebp+8]          ; iNode
0x100a779a  shl edi, 6                ; *0x40 (FBspNode size)
0x100a779d  mov eax, [eax+0x10]       ; this->Model
0x100a77a0  add edi, [eax+0x58]       ; + Nodes.Data
0x100a77a5  mov eax, [ebp+0xc]        ; Outside          (loop head)
0x100a77ab  cmp esi, 2 / jge done     ; side = 0..1
0x100a77b0  mov ebx, [edi+esi*4+0x20] ; iChild[side]
0x100a77b4  push 4 / mov ecx,edi / push eax / push esi
0x100a77ba  call 0x100a89a0           ; eax = ChildOutside(side, Outside, 4), ecx=Node
```

Recursion (child exists):
```
0x100a77bf  cmp ebx, -1 / je leafcase
0x100a77c4  push eax                  ; new Outside
0x100a77c5  push ebx                  ; iChild
0x100a77c6  mov ecx, [ebp-0x14]       ; this
0x100a77c9  call 0x100a7760           ; self-recursion
```

Leaf creation (NULL child, ChildOutside != 0):
```
0x100a77d1  test eax, eax / je skip           ; only if ChildOutside
0x100a77d8  mov ecx, [eax+0x10]               ; Model
0x100a77db  mov eax, [ecx+0xdc]               ; Leaves.Num (PRE-append)
0x100a77e1  mov [ebp-0x34], eax               ; leaf.iZone   = Leaves.Num
0x100a77e4  mov dword [ebp-0x30], -1          ; leaf.iPermeating = -1
0x100a77eb  mov dword [ebp-0x2c], -1          ; leaf.iVolumetric = -1
0x100a77f2  mov dword [ebp-0x28], -1          ; leaf.iExclusive lo = -1
0x100a77f9  mov dword [ebp-0x24], -1          ; leaf.iExclusive hi = -1
0x100a7800  lea eax, [ebp-0x34] / push eax
0x100a7804  add ecx, 0xd8                     ; &Model->Leaves (TArray @ Model+0xd8)
0x100a780a  call 0x100a7260                   ; AddItem → returns new index
0x100a780f  mov [edi+esi*4+0x38], eax         ; node.iLeaf[side] = index
```

### What this pass PRODUCES (writes to Model/node/leaf state)

1. **`Model.Leaves` append** — one `FBspLeaf` (0x14 B) per *(node, side)* pair where
   `iChild[side] == -1` **and** the propagated `Outside` for that side is nonzero (empty
   space). Contents at creation: `iZone = <its own index>`, `iPermeating = -1`,
   `iVolumetric = -1`, `iExclusive = -1/-1` (u64). So after pass A each empty convex
   subspace of the tree is a leaf, and `iZone` seeds a per-leaf unique id — union-find /
   flood fodder for pass C ("Found %i zones"), which will rewrite it into real zone numbers.
2. **`node.iLeaf[side]` (node+0x38/+0x3c)** — set to the new leaf's index for every empty
   NULL-child slot. Solid NULL-child slots and all interior (non-NULL) child slots keep the
   -1 written by portalize step 2. Note the pairing: `iLeaf[k]` ↔ `iChild[k]` (side 0 = back,
   side 1 = front), matching the brief's FBspNode table.
3. Nothing else: no writes to iZone[0..1] bytes, ZoneMask, NodeFlags, surfs, or Lights here.

**Leaf-index determinism (matters for the Rust port):** indices are assigned in DFS
pre-order with side 0 (BACK) processed before side 1 (FRONT) at each node, starting at the
root (iNode 0). The coplanar chain (`node.iPlane`, +0x28) is **never traversed** — only
iChild[0]/iChild[1] are recursed — so nodes reachable solely through iPlane links are never
visited by pass A and keep `iLeaf = -1`.

---

## Callee 0xa89a0 — `FBspNode::ChildOutside(side, Outside, ExtraFlags)` (thiscall on the NODE)

**Role:** computes the empty/solid ("Outside") status of the subspace on `side` of this
node given the parent subspace's status, treating the node as an occluder only if it is a
*real CSG node*; called here with `ExtraFlags = 4`.

**Signature:** `UBOOL __thiscall FBspNode::ChildOutside(INT side, UBOOL Outside, DWORD ExtraFlags)`
— ecx = &FBspNode, `ret 0xc`, spans 0x100a89a0–0x100a89e1.

### Pseudo-C

```c
UBOOL FBspNode::ChildOutside(INT side, UBOOL Outside, DWORD ExtraFlags) // 0xa89a0
{
    // "real CSG occluder" = has polygon area AND none of (ExtraFlags|NF_IsNew|NF_NotCsg)
    // NumVertices @ node+0x36 (byte), NodeFlags @ node+0x37 (byte)
    BOOL IsCsg = (NumVertices > 0) && !(NodeFlags & (ExtraFlags | 0x21));
    if (side)  return Outside || IsCsg ? ... ;   // see exact truth table below
    ...
}
// Exact per-branch semantics (verbatim from the two branch bodies):
// side == 1 (FRONT):
//   if (Outside != 0)                     return 1;   // stays outside
//   if (NumVertices == 0)                 return 0;   // transparent node: Outside unchanged (0)
//   if (NodeFlags & (ExtraFlags | 0x21))  return 0;   // non-CSG node: unchanged (0)
//   return 1;                                          // real CSG surf: FRONT becomes OUTSIDE
// side == 0 (BACK):
//   if (Outside == 0)                     return 0;   // stays inside
//   if (NumVertices == 0)                 return 1;   // transparent: unchanged (1)
//   if (NodeFlags & (ExtraFlags | 0x21))  return 1;   // non-CSG: unchanged (1)
//   return 0;                                          // real CSG surf: BACK becomes SOLID
// Net: NewOutside = IsCsg(node, ExtraFlags) ? (side == 1) : Outside;
```

### Evidence

```
0x100a89a3  cmp dword [ebp+8], 0      ; side
0x100a89a7  je  0x100a89c8            ; → BACK branch
; FRONT branch:
0x100a89a9  cmp dword [ebp+0xc], 0    ; Outside
0x100a89ad  jne 0x100a89bf            ; Outside → return 1
0x100a89af  cmp byte [ecx+0x36], 0    ; NumVertices
0x100a89b3  jbe 0x100a89de            ; ==0 → return 0
0x100a89b5  mov eax, [ebp+0x10]       ; ExtraFlags
0x100a89b8  or  al, 0x21              ; | NF_IsNew(0x20) | NF_NotCsg(0x01)
0x100a89ba  test byte [ecx+0x37], al  ; NodeFlags
0x100a89bd  jne 0x100a89de            ; any set → return 0
0x100a89bf  mov eax, 1 / ret 0xc      ; return 1
; BACK branch:
0x100a89c8  cmp dword [ebp+0xc], 0
0x100a89cc  je  0x100a89de            ; !Outside → return 0
0x100a89ce  cmp byte [ecx+0x36], 0
0x100a89d2  jbe 0x100a89bf            ; ==0 → return 1
0x100a89d4  mov eax, [ebp+0x10] / or al, 0x21
0x100a89d9  test byte [ecx+0x37], al
0x100a89dc  jne 0x100a89bf            ; any set → return 1
0x100a89de  xor eax, eax / ret 0xc    ; return 0
```

### Constants / flags

- **`or al, 0x21`** (@0x100a89b8 and @0x100a89d7): the caller-independent non-CSG mask is
  **NF_NotCsg (0x01) | NF_IsNew (0x20)**.
- **Pass A passes `ExtraFlags = 4`** (`push 4` @0x100a77b4): effective mask **0x25**. So the
  0x04 NodeFlags bit (the portal/invisible-derived bit per the brief) makes a node
  *transparent to solidity* during leaf assignment — **a portal plane does not flip
  Outside**; the space on both of its sides inherits the parent's status. This is exactly
  how portals split zones without creating solid boundaries.
- **`NumVertices == 0`** (byte @node+0x36) also makes the node transparent (degenerate/
  zero-area node — no occluding polygon).
- Solidity convention confirmed against the CSG convention in the brief: for a real CSG
  node, **FRONT (side 1, positive PlaneDot) → Outside=1 (empty)**, **BACK (side 0) →
  Outside=0 (solid)** — i.e. the surf normal points solid→empty.

---

## Callee 0xa7260 — `TArray<FBspLeaf>::AddItem(const FBspLeaf&)`

**Role:** grows the leaves TArray by one 0x14-byte element via Core's `FArray::Add`, copies
the caller's leaf into the new slot, and returns the new element's index (`Num - 1`).

**Signature:** `INT __thiscall TArray<FBspLeaf>::AddItem(const FBspLeaf* Item)` — ecx =
&TArray (here `Model+0xd8` = Leaves), `ret 4`.

### Pseudo-C + evidence

```c
INT TArray_FBspLeaf::AddItem(const FBspLeaf* Item)   // 0xa7260
{
    INT Index = FArray::Add(this, 1, 0x14);          // Core.dll import
    FBspLeaf* Slot = Data ? &((FBspLeaf*)Data)[Index] : NULL;  // Data + Index*0x14
    if (Slot) { memcpy16(Slot, Item); Slot->+0x10 = Item->+0x10; }  // movups + 1 dword = 0x14 B
    return Num - 1;
}
```

```
0x100a7264  push 0x14 / push 1
0x100a726a  call dword ptr [0x100ce5ec]   ; Core.dll ?Add@FArray@@QAEHHH@Z  (Count=1, Size=0x14)
0x100a7270  lea edx, [eax + eax*4]        ; Index*5
0x100a7273  mov eax, [esi]                ; Data
0x100a7275  lea ecx, [eax + edx*4]        ; Data + Index*0x14
0x100a727f  movups xmm0, [eax] / movups [ecx], xmm0   ; copy 16 B
0x100a7285  mov eax,[eax+0x10] / mov [ecx+0x10], eax  ; copy last dword
0x100a728b  mov eax, [esi+4] / dec eax    ; return Num - 1
```

The IAT slot `[0x100ce5ec]` resolves (pefile, import table) to Core.dll
**`?Add@FArray@@QAEHHH@Z` = `FArray::Add(INT Count, INT ElementSize)`**, returning the index
of the first added element. Element size 0x14 independently confirms `FBspLeaf` = 0x14 bytes
in memory, matching the brief's layout (iZone +0, iPermeating +4, iVolumetric +8,
iExclusive u64 +0xc).

---

## Answers to the assignment's exact questions

- **How leaves are created (one per what?):** one `FBspLeaf` per *empty NULL-child slot* of
  the front/back BSP tree — i.e. per convex outside/empty subspace at the tree's fringe.
  Solid subspaces produce no leaf.
- **What is written:** `Model.Leaves` gains `{iZone = own index, iPermeating = -1,
  iVolumetric = -1, iExclusive = -1}` per leaf; `node.iLeaf[side]` (+0x38/+0x3c) gets the
  index; nothing else is touched.
- **Recursion descent:** strictly `iChild[0]` (back) then `iChild[1]` (front), DFS pre-order
  from node 0; the coplanar `iPlane` chain is never followed.
- **Outside propagation:** `NewOutside = IsCsg ? (side == 1) : Outside`, where
  `IsCsg = NumVertices > 0 && !(NodeFlags & 0x25)` (0x25 = ExtraFlags 0x04 | NF_IsNew 0x20 |
  NF_NotCsg 0x01). Matches the CSG convention (front of a solid surf = empty).
- **NodeFlags/PolyFlags role:** only NodeFlags is consulted (byte +0x37): bits 0x01, 0x20,
  and the pass-supplied 0x04 (portal-derived) make a node non-occluding. PolyFlags is never
  read in this pass.

## Open questions / low-confidence spots

- `Model->+0xf0` as `RootOutside`: pass A's usage is *consistent* with that reading (it is
  the root call's Outside seed) but this pass does not itself prove the field's producer.
- The 0x04 NodeFlags bit's exact producer (which pass/CSG step sets it, and from which
  PolyFlags) is outside this function; here it is only *tested*. The brief's
  "portal/invisible-derived" label is adopted, not re-verified.
- `leaf.iZone = own index`: the *use* of this seeding (union-find vs. plain placeholder)
  belongs to passes B/C; only the initialization is proven here.
- `[ebp-0x18] = esi` @0x100a77a8 is a dead store (side saved to a stack slot never read) —
  no semantic content, noted for completeness.
