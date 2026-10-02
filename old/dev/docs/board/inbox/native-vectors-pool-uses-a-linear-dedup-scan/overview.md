+++
priority = "p2"
kind = "implement"
summary = "native Vectors pool uses a linear dedup scan same as the filed Points item"
+++

# native Vectors pool uses a linear dedup scan same as the filed Points item

`bsp_add_vector` (`uedcli-native/src/bspcsg.rs:490-503`) scans `model.vectors` linearly on every
call. `alloc_surf` (`bspcsg.rs:562-600`) calls it 3x per surf (normal + two texture axes), and
`alloc_surf` fires from `bsp_add_node` (`bspcsg.rs:650`) for nearly every world-tree node created
during incremental CSG — the mainline build path, not just a repartition fallback. `model.vectors`
grows monotonically across a build, so total cost is O(V²) in distinct normal/texture-axis vectors.

This is the same shape of bug as the already-filed
`repartition-point-dedup-still-uses-a-linear` (which covers only the Points pool, via `nearest()` at
`bspcsg.rs:510`), but on a busier pool that runs unconditionally, not only on the acknowledged
repartition fallback. `ladder_run.py` rebuilds native from scratch per N by design, so this cost
compounds across the whole N=1..NX ladder sweep on levels with NX in the hundreds.

Fix: same fix class as the filed Points item — bucket vectors into a coordinate-quantized hash grid,
scan only neighboring buckets. Per `NATIVE-MATERIALIZE.md`'s prime directive, any fix here needs to
preserve UED22's own point-pool-lookup order/behavior for byte parity, not just go faster.

Found by: 2026-09-12 performance audit (subagent-driven, native-materialize scope).
