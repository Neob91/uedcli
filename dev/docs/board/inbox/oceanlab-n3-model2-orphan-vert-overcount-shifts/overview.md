+++
priority = "p2"
kind = "bug"
summary = "OceanLab N3 world Model2 gates NO because native emits 85 more orphan FVerts than UED22 (verts 3074 vs 2989), lengthening the Verts array and shifting every live node's iVertPool. The gate masks orphan iVertex VALUES but NOT the array-length/iVertPool shift, so it is NOT absorbed."
+++

# OceanLab N3 `Model2` orphan-vert overcount shifts `iVertPool`

Found while landing the `bsp_add_vector` 4e-4 threshold fix
(`oceanlab-n3-world-model-divergence-bsp-add`). After that fix, OceanLab N3 `Vectors` and
`Model2.Polys` tu/tv are byte-exact, but the gate still fails on `Model2` for a SEPARATE,
pre-existing reason.

## Symptom

`parity_gate.py` on `_scratch/actor-parity/14_oceanlab_lab/{native,ref}_N3.dx`: `BODY model model2`
canonical bodies differ. First differing token is node 0's `iVertPool` (native 2684 vs ued 2599,
delta +85). The gate's model-tail token streams even differ in LENGTH (native 5567 vs ued 5397),
so `_bodies_equal`'s `len(ca[2]) != len(cb[2])` short-circuits to False.

## Cause

Decode (`uedcli.native.umodel.parse_model_body`, `Model2`):

- Live node rings are IDENTICAL both sides: sum `NumVertices`=1040, same per-node histogram, same
  `min` live `iVertPool`=27.
- `Verts`: native 3074 vs ued 2989 (+85). All extra are ORPHAN FVerts (slots in no live node ring):
  native 2034 orphans vs ued 1949. The orphans are interspersed through the pool, so native's live
  rings sit at HIGHER `iVertPool` indices → every live node's `iVertPool` bytes diverge.

This is present at the OLD 0.001 threshold too (A/B rebuild confirmed: verts 3074 both), so it is
independent of the vector-dedup fix.

## Why the gate does NOT absorb it

The orphan-`iVertex` exclusion (owner + two opus reviews, 2026-09-04) masks each orphan vert's
`iVertex` VALUE (`_model_tail` `mask_at`). It does NOT normalise the number of orphan SLOTS or the
resulting `iVertPool` shift. The prior finding's claim that the +85 delta is "absorbed... NOT
flagged" was wrong: differing orphan COUNT changes the Verts array length and live `iVertPool`, both
literally compared.

## Class

`verts-residual-on-structure-exact-levels`. Fixing needs native's CSG to stop minting 85 spurious
orphan FVerts (or to match UED22's orphan-vert count/placement). Out of scope for the texture-axis
dedup fix. Repro: cached `_scratch/actor-parity/14_oceanlab_lab/{native,ref}_N3.dx`.

## Diagnosis 2026-09-05 (localized; DEEP class, not a bounded fix)

Gap-walk of both `Model2` bodies (`_scratch/gapwalk.py`, decode via `umodel.parse_model_body`):

- All 271 nodes are in IDENTICAL `iVertPool` order; the delta is 0 up to rank 214 then jumps to
  +85 at ONE gap (rank 215) and stays a constant +85 to the end. So the surplus is a SINGLE
  contiguous orphan block, not many small degenerate-triangle gaps.
- The block is the orphan run between live ring `[944..947)` (node 269) and the next live ring:
  native fills slots `[947..2551)` = **1604** orphan slots, editor `[947..2466)` = **1519** = +85.
  Every slot in the run is orphan (`iSide == -1`, 0 non-orphan native-side), and the run PREFIX is
  byte-identical (slots 947-954 iVertex 174/352/166/198/... match), so native over-emits 85 orphans
  within/at the tail of this one repartition region.

Cause: this is the known repartition / point-pool-history difference — native retains ~85 discarded
reconstruction verts in one repartition orphan region (trigger Brush779, the 258-tri rotated
tessellated subtract) that UED22's build compacts/frees. Same phenomenon as the already-pinned
`WanChai +84` in `verts-residual-on-structure-exact-levels`, and the same mechanism as
`native-materialize/pass-d-orphan-ivertex-stale-index-parity`: the editor's no-clear repartition +
deferred surf compaction vs native's `bspcsg.rs` pool CLEAR at repartition (§10.16) +
`reorder_points_canonical` final renumber (§10.20). NOTE this is the orphan COUNT half (array length
+ live `iVertPool` shift, both compared), distinct from the orphan `iVertex` VALUE half that the
gate masks and those items also track.

NOT a clean bounded fix: matching the editor's orphan-vert count needs reproducing its whole
point-pool construction/GC history at repartition (no-clear repartition + deferred surf compaction
in `bspcsg.rs`), entangled with `surf.pBase`/`vert.iVertex` pool indices and the load-bearing
Points-section byte-parity guard -> high tree-regression risk, and per
`verts-residual-on-structure-exact-levels` offline diffing is exhausted (needs live gdb `bspAddNode`
ring capture). Size: multi-day RE + `bspcsg.rs` repartition rework, not in the `zones.rs`/`passes.rs`
lane. Deferred per owner "deep vert-pool-history port -> don't self-authorize" (task 2026-09-05).

## RESOLVED 2026-09-05 (owner-authorized rework, branch `worktree-agent-a05dd19140b6194f5`, `e836e6d`)

The prior "repartition vert-pool history" diagnosis was WRONG. Stage counts
(`UEDCLI_BSPCSG_STAGE_COUNTS`) prove `repartition_frontier` adds ZERO verts on OceanLab N3
(2551->2551); the whole +1601 growth — and the entire `[947..2551)` orphan run — is the ZONE PASS.
`AssignAllZones` (Pass D) re-emits every node ring's verts via `bspAddNode` per landing.

Native's `zones.rs::node_landings` filtered each node's poly through the tree with the crude
`clip_poly` (Sutherland-Hodgman, 1e-4 band), NOT the editor's `FilterThroughSubtree`
(`Editor.dll 0xa9030`, `re-raw-zones/passD-assignzones-7400.md` §3). The editor filters with
`FPoly::SplitWithNode(VeryPrecise=1)`, which `clip_poly` fails to reproduce in one load-bearing way:
the **r==0 COPLANAR-DROP** — a fragment coplanar with a deeper filter node is dropped with no
landing, whereas `clip_poly` lets it land on BOTH sides, minting the 85 spurious orphan verts. (The
`zones.rs` comment already flagged this: "unreachable on the calibration map ... port the real r==0
classification if a future map shows fragment-count drift." OceanLab N3 is that map.)

Fix: `filter_through`, a faithful `FilterThroughSubtree` port (>14 `SplitInHalf`; VeryPrecise
`split_with_plane`; r==0 drop; r==1/2 whole-poly descent; r==3 cut), used by Pass D only via
`node_landings_precise`. Pass B' barriers keep `clip_poly` (leaf-pairs only, no vert emit; already
leaf-pair-validated incl. Catacombs). Result: OceanLab N3 verts 3074->2989 = editor exact, gate
PASSES. No regression: 3 originals N1..16, Island N1..4, OceanLab N1..2 all gate-equal old vs new.
Not yet merged to master (worktree branch).
</content>
