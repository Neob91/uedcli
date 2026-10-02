+++
priority = "p2"
kind = "unknown"
summary = "§10.8's node-4 coplanar-chain-head/dead-node root cause is DECODED + FIXED; the soup is now byte-exact"
+++

# §10.8's node-4 coplanar-chain-head/dead-node root cause is DECODED + FIXED; the soup is now byte-exact

The mechanism (`sections/82 §10.9`): `NodeCleanup`
(`0x34020`) is notify-only — the relink is **`bspCleanup` (`0x36160` → `CleanupNodes 0x32100`), run
at the TAIL of `bspBrushCSG` PER-BRUSH** (`0x35de1`, unconditional for Add/Subtract), so each brush
filters through the prior brush's CLEANED tree. `CleanupNodes` splices dead (`nv==0`) nodes:
promote the `iPlane` successor, inheriting front/back children SWAPPED iff it faces opposite
(`Normal·Normal < 0`, `FPlane::operator|`, threshold 0.0) — this IS the §10.8 `(+1,0,0)`-dead-vs-
`(−1,0,0)`-alive orientation flip. Also `bspBuildFPolys`→`MakeEdPolys` (`0x33bb0`) is a **tree-walk**
(self,front,back,plane), not an index scan, so the repartition-input soup ORDER is tree-structural.
Ported to `bspcsg.rs` (`bsp_cleanup`/`cleanup_nodes` per-brush; `bsp_build_fpolys`→`make_ed_polys`).
**Verified:** node 4 now identical (`tree_struct_diff.py 33` residual diffs are unreachable dead
nodes only); merlon splitter region node-for-node identical; **`soup_cmp.py` 0/0 byte-exact** (was
24/17); `compare_trees.py 32` identical; `bin/test` 1363 green. Decode harness: `dll_disasm.py`/
`dll_exports.py`/`dll_vtable.py`/`cleanup_proto.py` in `harness/editor-tree-oracle/`.
