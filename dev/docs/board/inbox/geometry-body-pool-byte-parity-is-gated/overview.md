+++
priority = "p2"
kind = "implement"
summary = "Geometry-body pool byte-parity is gated on `SplitPolyList` ring-vertex DISTRIBUTION, not `bspOptGeom`/pool-dedup"
+++

# Geometry-body pool byte-parity is gated on `SplitPolyList` ring-vertex DISTRIBUTION, not `bspOptGeom`/pool-dedup

Live oracle (2026-07-18, `42-bspoptgeom-decode.md`
§6a) proved: native's soup is byte-identical to the editor's (853 polys / 3315 verts), but
`bspBuild`/`SplitPolyList` turns it into ~4400 ring-verts (avg 3.8/node) where the editor makes
**10518** (avg 9.1/node). Same 1156 node planes + same point pool (all 975 editor T-junction welds
land on points+planes native already has), but native distributes vertices into rings differently —
606 of the editor's 975 welded T-corners are ALREADY in native's rings, so native's (correct)
`bspOptGeom` detector fires only 22 vs the editor's 975. Editor's on-disk **16163** verts = ~5000
live + ~11000 ORPHANS from 975 insert-and-orphan welds; native's **4543** = ~4300 live + ~240 (22
welds). To close verts→16163 / points→2035 / NumSharedSides→2739, `SplitPolyList` (`bspcsg.rs`
`split_poly_list`/`find_best_split_exact`/`bsp_add_node`) must reproduce the editor's exact per-node
ring content so the same 975 cracks exist. This is a repartition-fidelity task, NOT a
`bspoptgeom.rs` one — the detector + pass 2 + append/orphan layout are validated correct. Do NOT
loosen the detector to force inserts (over-welds, diverges from golden). Oracles committed under
`dev/docs/spikes/2026-07-15-native-materialize/harness/editor-tree-oracle/bspopt_*_oracle.py`.
