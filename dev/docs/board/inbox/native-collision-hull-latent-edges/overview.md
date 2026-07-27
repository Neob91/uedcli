+++
priority = "p3"
kind = "debug"
summary = "Native collision-hull latent edges (flagged by post-build review, 2026-07-16)"
+++

# Native collision-hull latent edges (flagged by post-build review, 2026-07-16)

p3. All
LOW / not-yet-reproduced, native build is live-verified playable. (a) `model_write.rs`/`umodel.py`
hardcode the serialized trailing `RootOutside` INT to `0` instead of deriving from
`model.root_outside`; the hull descent seeds from `model.root_outside` (false today), so they only
*coincidentally* agree — an additive/`root_outside=true` build would seed one way and serialize the
other. Wire the flag from `model.root_outside` (keep the Rust↔Python gate-5 byte pin). (b)
`passes::bsp_build_bounds` keeps only the FIRST hull when a node has two solid terminal children
(only possible for a non-CSG node embedded in solid — shouldn't occur for carved rooms); add an
assert/guard if one ever appears. (c) Pin the 64-plane cap boundary (63/64/65) once a map can
produce it — culling keeps the castle at max 10 planes/hull (editor max 10), so it's currently
unreachable; the cap now `eprintln!`s + truncates (keeps the hull) instead of silently dropping.
(d) Consider non-parallel redundant-plane culling for exact editor parity (editor mean 5.6
planes/hull; ours 7.9 after parallel-dedup) — harmless (extra planes only tighten the convex cell),
purely a size/parity nicety.
