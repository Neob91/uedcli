+++
priority = "p2"
kind = "unknown"
summary = "Native full-castle node-for-node prefix still 0 after the §8.3 fix — next divergence is the REPARTITION ROOT + under-fragmentation"
+++

# Native full-castle node-for-node prefix still 0 after the §8.3 fix — next divergence is the REPARTITION ROOT + under-fragmentation

p2. Post-fix the ordered prefix is still 0: `node[0]`
repartition root is native `(-1,0,0,-72)` vs editor `(-1,0,0,48)` (parallel, different offset) because
the pre-repartition soup still differs — dominated by (a) the split-and-re-add UNDER-fragmenting
(verts 4560 vs ed 16163, num_shared_sides 1152 vs 2739; only-in-editor planes are repeated
axis-aligned floor/wall planes e.g. `(0,0,1,0)×25`), and (b) missing zone/visibility (`i_zone (1,1)`
vs `(0,2)`, `node_flags 0` vs `8`). Needs the §6/§8.1 fragmentation pinned + zones/TestVisibility +
`bspOptGeom` (out of scope) before the ordered prefix can move off 0.
