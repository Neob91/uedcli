+++
priority = "p2"
kind = "debug"
summary = "native's bsp_add_node never seeds a node's iZone/iLeaf from its parent; the editor's inherits them for a NODE_Plane placement (decode included), so the 3330 UNATCO nodes the detail-brush layer appends after TestVisibility ship iZone (0,0)"
+++

# `bsp_add_node` does not seed `iZone`/`iLeaf` from the parent

Surfaced by `csgrebuild-runs-testvisibility-between-the`, which moved native's zone pass to its real
place mid-`csgRebuild`. The editor does the same and never re-runs it, so a node created afterwards —
the whole detail-brush layer — has to get its zone from `bspAddNode` itself. For a `NODE_Plane`
placement the editor's does exactly that (decode below); native's `bsp_add_node`
(`uedcli-native/src/bspcsg.rs`) writes no node `iZone`/`iLeaf` at all, so on UNATCO 3330 of 6314 nodes
now carry `iZone = (0,0)` where the golden has real zones. What a FRONT/BACK-placed node inherits is
NOT established — that branch of `bspAddNode` is undecoded, and it is the placement most brush faces
get, so the decode below does not by itself explain the whole 3330.

`ZoneMask` is separately repaired: `passes::bsp_build_bounds` now re-runs Pass E, per spec §8 step 1,
so no node ships the all-ones sentinel. But a mask computed off `iZone = (0,0)` is still missing that
node's own bits.

## The editor's rule

**[DISASM Editor.dll `0x1003524a`–`0x100352c7`]**, folded into spec §5.1. `FBspNode`: `ZoneMask` +0x10,
`iZone[2]` bytes +0x34/+0x35, `iLeaf[2]` +0x38/+0x3c. Every new node starts `ZoneMask` all-ones, then
by `ENodePlace`:

- `NODE_Root` (3): `iLeaf = {-1,-1}`, `iZone = {0,0}`.
- `NODE_Front` (1) / `NODE_Back` (0): nothing here — the branch jumps to `0x1003535b`, **undecoded**.
- `NODE_Plane` (2): helper `[0x100ce510]` (new node as `this`, parent as arg) returns a float;
  `k = (0.0 > result) ? 1 : 0`; then `new.iLeaf[0]=parent.iLeaf[k]`, `new.iLeaf[1]=parent.iLeaf[1-k]`,
  `new.iZone[0]=parent.iZone[k]`, `new.iZone[1]=parent.iZone[1-k]`, `parent.iPlane = new index`.

The helper is presumed a plane/normal comparison (so the swap is "the two faces point opposite ways")
but was **not** disassembled — that is the one unverified step and must be confirmed before porting.

## Scope note

Zone-VALUE parity is a bigger job than this one rule: native's own zone NUMBERING already differed
from the editor's before any of this (UNATCO `iZone` mismatches 5541/6314, and the two
distributions differ in shape, not just labels — the editor has many `(z,z)` nodes native lacks).
Porting the inheritance is necessary but not sufficient. Zone COUNT and the `Leaves` array are
exact (7/7 zones, 762/762 leaves).
