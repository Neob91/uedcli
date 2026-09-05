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
</content>
