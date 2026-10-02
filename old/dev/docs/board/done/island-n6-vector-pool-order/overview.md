+++
priority = "p2"
kind = "debug"
summary = "DONE — Island N=6's world Model2 Vector at pool index 8 was claimed by a merged-away surf's texture axis; native now keeps the incremental Vectors pool across the repartition instead of rebuilding it from the surviving surfs. Byte-exact, no mask."
spikes = ["dev/docs/spikes/2026-09-06-island-n6-vector-pool/"]
+++

# Island N=6 world-`Model2` vector-pool order

Fixed 2026-09-06. A live `bspAddVector` trace showed slot 8 is first claimed by `Brush1355`'s
bottom-face **`vTextureU`** — a surf CSG later merges away — and `Brush1353`'s oblique-face NORMAL
then dedups into it (they agree to 6e-7). The pool order is the incremental proposal order, so
`bspcsg.rs` now keeps `model.vectors` across the repartition (as it already keeps `model.points`) and
`rebuild_vector_pool` is deleted. Detail: `dev/docs/spikes/2026-09-06-island-n6-vector-pool/spike.md`.
