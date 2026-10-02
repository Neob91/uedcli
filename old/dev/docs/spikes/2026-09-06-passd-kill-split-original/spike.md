# OceanLab N=46 — Pass D must KILL the split original, not reuse it

**Result: one root cause, fixed faithfully, no mask.** `TestVisibility`'s Pass D
(`AssignAllZones`) ends a zone SPLIT by killing the original chain node and appending a fresh node
per surviving zone; the post-Pass-D `bspCleanup` then PROMOTES the dead node's coplanar successor
into its place. Native instead reused the original in place, so whenever the original was a
coplanar-chain HEAD, native shipped the chain headed by the split node and UED22 shipped it headed
by the promoted successor — with the head's children transferred, and mirrored when the two planes
face opposite ways. Board: `oceanlab-n46-world-model2-bounds-leafhulls-and`.

Not the `2026-09-06-pointregion-planedot-f32` precision family: no near-tie, no float compare.

## The divergence

`model_field_diff.py native_N46.dx ref_N46.dx` (this dir) over the world `Model2`, with the gate's
masks applied — `bounds` differed from index 19, `leafhulls` from 221, `lightmap` (and 55 surfs'
`iLightMap`) from 33, and the per-leaf permeating-light region from 0, while `points`, `vectors`,
`leaves`, `zones` and `lightbits` were byte-identical. The node array carried the actual cause:
only 13 of 573 nodes differed, in `iFront`/`iBack`/`iPlane` (6 nodes) and `iCollisionBound`/
`iRenderBound` (the rest, downstream of the bound walk).

The 6 are two coplanar chains, same node SET, different order:

| plane | native chain (by node index) | UED22 chain |
|-------------|-----------------------------|-------------------|
| `x = -64`   | 571 → 64 → 65 → 66 → 572     | 64 → 65 → 66 → 571 → 572 |
| `y = 0`     | 569 → 67 → 570               | 67 → 569 → 570 |

571/572 and 569/570 are the Pass-D split pairs (each pair shares a surf and sits at the array tail).
Native made the split OWNER the chain head; UED22 has it fourth (resp. second), i.e. appended.

The head carries the chain's real children, and that is where the signature is unambiguous:

- `x = -64`: both heads carry `iBack = 149`; native's head has `iFront = 569`, UED22's `iFront = 67`
  — each pointing at the other chain's own head.
- `y = 0`: native's head (node 569, plane `(0,1,0,0)`) has `iBack=108, iFront=68`; UED22's head
  (node 67, plane `(0,-1,0,0)`) has `iBack=68, iFront=108` — **swapped**, exactly as
  `cleanup_nodes` Case A swaps inherited children when `Node.Normal · P.Normal < 0`.

## What the decode already said

- `re-raw-zones/passD-assignzones-7400.md` §1 (`Editor.dll 0xa7400`): the split branch is
  `Nodes[i].NumVertices = 0` on the ORIGINAL, then every zone-tagged fragment is kept. The fragments
  were added by `bspAddNode(iHead, NODE_Plane, …)`, which tail-walks the chain — so they land at the
  chain tail AND at the tail of `Model->Nodes`.
- `sections/70-zones-portalization.md` §1 pass table: `bspCleanup` + `bspRefresh(1)` +
  `bspBuildBounds` run immediately after Pass D.
- `sections/82-bspbrushcsg-port-decode.md` §10.9 (`CleanupNodes`, `Editor.dll 0x32100`): a dead node
  with a coplanar successor is spliced out — the successor inherits `iFront`/`iBack` (swapped on
  opposite facing) and the parent is repointed at it.

Native's `bspcsg::bsp_cleanup` was already a faithful port of that; it just never ran after Pass D.

## The fix

`zones.rs`:

- the split branch emits `Emit::KillOwner` and then EVERY surviving landing as a `Frag` (a real new
  node on the chain tail). The `Emit::OriginalRing` retarget — and its `pending_retarget` follow-up
  — are gone.
- `assign_leaves_and_zones` ends with `bspcsg::bsp_cleanup` + `bspcsg::compact_unreachable_nodes`,
  the pass table's post-Pass-D `bspCleanup` + `bspRefresh(1)`.

`bspcsg.rs`: `reorder_nodes_to_tail` is DELETED. It existed only to fake the array layout the
editor gets for free — it moved each retained original plus its extra fragments to the tail as a
pure relabel (§82 §10.17). With the original genuinely killed and compacted away and the fragments
genuinely appended, the editor's order is now what the pipeline produces.

Vert-pool behavior is unchanged: every landing still goes through the same `fill_ring_verts`, and
the original's own base ring is orphaned by the kill exactly as its retargeted replacement orphaned
it before.

## Evidence

- `harness/test_passd_kills_the_split_original.py` (in the `2026-09-03-incremental-actor-parity`
  harness) pins the OceanLab N=46 chain shape in UED22's reference AND in native's build.
- `zones.rs` unit tests `consume_emissions_kills_the_original_and_ships_no_ringless_node` and
  `cleanup_promotes_the_coplanar_successor_of_a_killed_chain_head`.
- `parity_gate.py`: OceanLab N=46 PASS, no new mask. `model_field_diff.py` on the same pair: 0
  differing node fields, 0 bounds, 0 leafhulls, 0 lightmap, 0 live verts.
