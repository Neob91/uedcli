# Pass A — leaf enumeration ("AssignLeaves"), RVA 0xa7760 (Editor.dll, VA 0x100a7760)

Decoded 2026-07-16 from `uned/UED22/Editor.dll` via `harness/adis.py` + `pe.py`. All addresses
are VAs (ImageBase 0x10000000). Confidence: everything below is instruction-anchored 📖 unless
marked otherwise.

## Headline correction to the brief's framing

Pass A is **NOT a portal builder**. It is a pure recursive **leaf-enumeration** pass: it walks
the BSP tree by `iChild[0..1]` only, computes an "outside" (empty-space) boolean per child side,
and for every **terminal child side that is outside** it **appends one fresh FBspLeaf** to
`Model.Leaves` and writes the new index into `node.iLeaf[side]`. It contains **zero** reads of
Surfs, PolyFlags, `PF_Portal`, or `this+0x10014` (the portal count) — the full function touches
only offsets `this+0x10` (Model), `Model+0x58` (Nodes.Data), `node+0x20/+0x24` (iChild),
`node+0x38/+0x3c` (iLeaf), `Model+0xd8/+0xdc` (Leaves), and (via the helper)
`node+0x36/+0x37` (NumVertices/NodeFlags). Portal-face enumeration must live in a later pass
(B `0xa9750` or D `0xa7400`), which is consistent with the skeleton: the portal count log field
`this+0x10014` is not written here.

Portals DO influence this pass in exactly one way: the caller passes `ExtraNodeFlags = 4`
(NF bit 0x04, the flag `bspAddNode` derives from `PF_Portal|PF_Invisible`), which makes a
portal-faced node **non-blocking** in the outside computation — so a portal node subdivides
empty space and each of its two sides ends in its **own separate leaf**. That is how portals
"cut leaves" without being enumerated here.

---

## Function 1 — `0xa7760` = `FEditorVisibility::AssignLeaves(INT iNode, UBOOL Outside)` (thiscall, ret 8)

**(1) Role.** DFS over the finished BSP tree; creates one `FBspLeaf` per *terminal empty child
side* and stores its index in that side's `node.iLeaf[side]`.

**(2) Pseudo-C** (field names per the brief's offset table):

```c
// thiscall: ecx = FEditorVisibility* this; args (INT iNode, UBOOL Outside); ret 8
void AssignLeaves(INT iNode, UBOOL Outside)
{
    FBspNode* Node = &this->Model->Nodes.Data[iNode];          // Model = this+0x10, Nodes.Data = Model+0x58
    for (INT side = 0; side < 2; side++)                       // side 0 first, then side 1
    {
        INT   iChild     = Node->iChild[side];                 // [node + side*4 + 0x20]
        UBOOL NewOutside = Node->ChildOutside(side, Outside, /*ExtraNodeFlags=*/4);  // 0xa89a0
        if (iChild != -1)
        {
            AssignLeaves(iChild, NewOutside);                  // recurse; Node ptr recomputed per call
        }
        else if (NewOutside)                                   // terminal AND empty -> new leaf
        {
            FBspLeaf L;
            L.iZone       = Model->Leaves.Num;                 // provisional zone id == the leaf's own index
            L.iPermeating = -1;
            L.iVolumetric = -1;
            L.iExclusive  = 0xFFFFFFFFFFFFFFFFull;             // two -1 dwords
            Node->iLeaf[side] = Model->Leaves.AddItem(L);      // 0xa7260; returns the new index
        }
        // terminal AND !NewOutside (solid): iLeaf[side] stays -1 (portalize step 2 pre-reset it)
    }
}
```

**(3) Constants, with instructions.**
- Loop bound 2 (both child sides): `0x100a77ab cmp esi, 2 / jge 0x100a7816`.
- Terminal sentinel `-1`: `0x100a77bf cmp ebx, -1 / je 0x100a77d1` (ebx loaded at
  `0x100a77b0 mov ebx, [edi + esi*4 + 0x20]`).
- `ExtraNodeFlags = 4` passed to the helper: `0x100a77b4 push 4` (before
  `push eax /*Outside*/; push esi /*side*/; call 0x100a89a0` with `ecx = edi = node`).
- FBspLeaf init values: `0x100a77db mov eax,[ecx+0xdc]` (Leaves.Num) →
  `0x100a77e1 mov [ebp-0x34], eax` (iZone), then four `-1` dwords at
  `0x100a77e4/-0x30, 0x100a77eb/-0x2c, 0x100a77f2/-0x28, 0x100a77f9/-0x24`
  (iPermeating, iVolumetric, iExclusive lo, iExclusive hi).
- Node stride 0x40: `0x100a779a shl edi, 6` then `0x100a77a0 add edi, [eax + 0x58]`.

**(4) State writes (the deliverable).**
- **`Model.Leaves` append** — exactly one 0x14-byte `FBspLeaf {iZone = own-index, iPermeating=-1,
  iVolumetric=-1, iExclusive=~0}` per terminal-empty child side, via `0x100a780a call 0x100a7260`
  with `ecx = Model+0xd8` (`0x100a7804 add ecx, 0xd8`).
- **`node.iLeaf[side]`** — `0x100a780f mov [edi + esi*4 + 0x38], eax` (eax = index returned by
  AddItem). Written **only** on the terminal-empty branch; solid terminals and non-terminal
  sides are left at the `-1` portalize pre-reset.
- Nothing else: no zone bytes, no ZoneMask, no NodeFlags, no surf fields, no `this+0x10014`.

**(5) Callees.** `0xa89a0` (ChildOutside, below); `0xa7260` (Leaves AddItem, below); recursion
into itself `0x100a77c9 call 0x100a7760`; the epilogue `security_cookie` boilerplate only.

**(6) Traversal facts that matter for membership parity.**
- **Coplanar chain NOT walked**: no read of `node+0x28` anywhere in the function. Nodes hanging
  on an `iPlane` chain are never visited by pass A, so their `iLeaf` stays `(-1,-1)` after it
  (whether a later pass fills them is outside this assignment's scope — flag for the pass-B/D
  decoders).
- **DFS order defines leaf numbering**: at each node, side 0 (`iChild[0]` = BACK/negative per
  section 60 §2.2) is processed and fully recursed **before** side 1 (FRONT). Leaf indices are
  assigned in this exact preorder — a Rust port must reproduce the order, not just the set,
  because `iZone` is seeded with the index and `iLeaf` values are these indices.
- Note the loop structure quirk: after a recursion the code does `inc esi; jmp 0x100a77a5`
  (`0x100a77ce`), re-reading `Outside` from `[ebp+0xc]` each iteration; the node pointer `edi`
  is loop-invariant (Leaves realloc can't move Nodes.Data, so this is safe).

---

## Function 2 — `0xa89a0` = `FBspNode::ChildOutside(INT side, UBOOL Outside, DWORD ExtraNodeFlags)` (thiscall, ret 0xc)

**(1) Role.** Computes whether the space on child side `side` of this node is "outside"
(= empty/void-adjacent... precisely: NOT enclosed by solid), given the parent-region `Outside`.

**(2) Pseudo-C.**

```c
// ecx = FBspNode*; args (side, Outside, ExtraNodeFlags)
UBOOL ChildOutside(INT side, UBOOL Outside, DWORD Extra)
{
    UBOOL IsCsg = NumVertices > 0                                // byte [ecx+0x36]
               && (NodeFlags & (Extra | NF_NotCsg|NF_IsNew)) == 0;  // byte [ecx+0x37] & (Extra|0x21)
    if (side != 0)  return Outside ||  IsCsg;   // side 1 = FRONT (positive PlaneDot)
    else            return Outside && !IsCsg;   // side 0 = BACK
}
```

**(3) Constants + full instruction map** (this is the whole function; two exit stubs):

```
0x100a89a3 cmp dword ptr [ebp + 8], 0      ; side == 0 ?
0x100a89a7 je  0x100a89c8                  ; -> BACK path
; FRONT path (side != 0):
0x100a89a9 cmp dword ptr [ebp + 0xc], 0    ; Outside ?
0x100a89ad jne 0x100a89bf                  ;   Outside -> return 1
0x100a89af cmp byte ptr [ecx + 0x36], 0    ; NumVertices
0x100a89b3 jbe 0x100a89de                  ;   0 verts -> not CSG -> return 0
0x100a89b5 mov eax, dword ptr [ebp + 0x10] ; Extra
0x100a89b8 or  al, 0x21                    ; | NF_NotCsg(0x01) | NF_IsNew(0x20)
0x100a89ba test byte ptr [ecx + 0x37], al  ; NodeFlags & mask
0x100a89bd jne 0x100a89de                  ;   any set -> not CSG -> return 0
0x100a89bf mov eax, 1 ; ret 0xc            ; return 1
; BACK path (side == 0):
0x100a89c8 cmp dword ptr [ebp + 0xc], 0    ; Outside ?
0x100a89cc je  0x100a89de                  ;   !Outside -> return 0
0x100a89ce cmp byte ptr [ecx + 0x36], 0
0x100a89d2 jbe 0x100a89bf                  ;   0 verts -> not CSG -> return 1 (stays Outside)
0x100a89d4 mov eax, dword ptr [ebp + 0x10]
0x100a89d7 or  al, 0x21
0x100a89d9 test byte ptr [ecx + 0x37], al
0x100a89dc jne 0x100a89bf                  ;   flagged -> not CSG -> return 1 (stays Outside)
0x100a89de xor eax, eax ; ret 0xc          ; return 0
```

The `NumVertices>0 && (NodeFlags & (Extra|0x21))==0` predicate is **byte-identical in shape to
the game's `FBspNode::IsCsg`** (section 60 §2.1, Engine.dll 0xf68b0 — same `or al,0x21; test`).

**(4) State writes.** None — pure predicate.

**(5)/(6) Semantics** (derived, high confidence): a **solid CSG node** (has vertices; none of
NF_NotCsg 0x01 / NF_IsNew 0x20 / caller's extra bits set) is a solid face whose normal points
solid→empty, so its FRONT side is empty regardless of parent (`Outside||IsCsg`) and its BACK
side is solid regardless of parent (`Outside&&!IsCsg` = false when IsCsg). A **non-CSG node**
(zero-vert bound splitter, NF_NotCsg, NF_IsNew, or — via `Extra=4` — a portal/invisible-derived
face) passes the parent's `Outside` through unchanged to both sides. With `Extra=4`, portal
nodes therefore split an empty region into two terminals that each get their own leaf.

---

## Function 3 — `0xa7260` = `TArray<FBspLeaf>::AddItem(const FBspLeaf&)` (thiscall, ret 4)

**(1) Role.** Grows the Leaves TArray by one 0x14-byte element, copies the arg in, returns the
new element's index.

**(2) Pseudo-C / (3) evidence.**

```
0x100a7264 push 0x14                        ; ElementSize = sizeof(FBspLeaf) = 20
0x100a7266 push 1                           ; Count = 1
0x100a726a call dword ptr [0x100ce5ec]      ; Core.dll import ?Add@FArray@@QAEHHH@Z
                                            ;   = FArray::Add(int Count, int ElemSize) -> old Num (insert index)
0x100a7270 lea edx, [eax + eax*4]           ; idx*5
0x100a7273 mov eax, dword ptr [esi]         ; Data
0x100a7275 lea ecx, [eax + edx*4]           ; Data + idx*0x14
0x100a727f movups xmm0, [eax] / 0x100a7282 movups [ecx], xmm0   ; copy first 16 bytes
0x100a7285 mov eax,[eax+0x10] / 0x100a7288 mov [ecx+0x10], eax  ; copy last 4  (total 0x14)
0x100a728b mov eax, dword ptr [esi + 4]     ; Num
0x100a728e dec eax                          ; return Num-1 = index of the new leaf
```

Import resolved via the PE import table: IAT slot `0x100ce5ec` = `Core.dll
?Add@FArray@@QAEHHH@Z`. Confirms the 0x14 element size (FBspLeaf) and that the return value
written into `iLeaf[side]` is the appended leaf's index.

**(4) State writes.** `Leaves.Data[Num-1] = *arg`; `Leaves.Num += 1` (inside FArray::Add).

---

## Third argument = `Model->RootOutside` (CONFIRMED, no longer "probably")

Call site in portalize `0xaa370`:

```
0x100aa473 mov eax, dword ptr [esi + 0x10]   ; Model
0x100aa476 push dword ptr [eax + 0xf0]       ; arg2 Outside = Model+0xf0
0x100aa47c push 0                            ; arg1 iNode = 0 (root)
0x100aa47e mov ecx, esi                      ; this = FEditorVisibility
0x100aa480 call 0x100a7760                   ; AssignLeaves(0, Model->RootOutside)
```

Identity of `+0xf0`: in **Engine.dll** `??0UModel@@QAE@PAVABrush@@H@Z` (`UModel::UModel(ABrush*,
int)`, RVA 0x16e830) the ctor's **second parameter is stored verbatim at +0xf0**:

```
0x1016ea4a mov eax, dword ptr [ebp + 0xc]    ; ctor arg 2 (the int)
0x1016ea4d mov dword ptr [edi + 0xf0], eax   ; -> Model+0xf0
```

The classic `UModel(ABrush* Owner, UBOOL InRootOutside)` shape plus this store makes
`Model+0xf0 = RootOutside`, and it **seeds the walk as the root region's Outside**: if the model
root is "outside" (space not enclosed by solid — true for a normal additive world hull is 0/1
per how the level model was constructed; a subtractive DX level model is built with
RootOutside as stored), the root region starts empty. Editor.dll itself never writes +0xf0
except in two whole-struct field-by-field UModel copies (`0x1000483e`, `0x10009694`).

## The exact leaf rule (the assignment's core question)

**Each terminal child side with computed Outside != 0 gets its OWN, brand-new leaf. There is no
merging of co-region terminals in this pass — none whatsoever.** Evidence: the only leaf
creation is the straight-line run `0x100a77d1 test eax,eax / je 0x100a7813` (skip if solid) →
build local FBspLeaf → `call 0x100a7260` (unconditional append, no lookup/dedup) →
`mov [edi+esi*4+0x38], eax`. There is no search over existing leaves, no adjacency test, no
portal-connectivity test. So after pass A:

- `Leaves.Num` = number of (terminal side, Outside=1) pairs in the tree, in DFS preorder
  (per node: side 0 subtree fully, then side 1).
- `node.iLeaf[side] = -1` exactly when that side is non-terminal OR its region is solid
  (`ChildOutside` returned 0), including every side of every coplanar-chain node (never visited).
- `leaf.iZone` = the leaf's own index (a provisional per-leaf zone id — the later zone flood,
  pass C `0xa93c0`, merges these into real zones); `iPermeating/iVolumetric = -1`;
  `iExclusive = ~0ull`.

"One leaf per convex empty region" is therefore literal and structural: a *region* here is one
terminal cell of the tree (which is convex by construction), not a flood-connected volume.
Two empty terminal cells separated only by a portal node, or by a non-CSG (NF 0x01/0x20/0x04)
splitter, are **distinct leaves**.

## Open questions / low-confidence spots

- **Coplanar-chain nodes' iLeaf**: pass A leaves them `(-1,-1)`. Whether pass B/D copies the
  head node's leaf onto chain nodes (real maps show plausible values) is NOT decoded here —
  hand to the pass-B (`0xa9750`) / pass-D (`0xa7400`) decoders. (Low confidence only about the
  *later* passes; pass A's non-visit is certain.)
- **RootOutside value for the level model** (0 vs 1 for a subtractive DX world): the ctor store
  is proven, but which value the level model carries at portalize time was not chased through
  `ULevel`'s model construction. A Rust port should read it from the model being ported, not
  assume. (The classic-source name `InRootOutside` is an inference from the ctor signature +
  semantics; the *mechanics* — seed value passed as initial Outside — are instruction-proven.)
- `NF` bit 0x04's exact provenance is from the brief/section-10 (`bspAddNode` derives it from
  `PF_Portal|PF_Invisible`); not re-verified this session.
