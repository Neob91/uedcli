+++
priority = "p?"
kind = "unknown"
summary = "LightMap grid-sizing rule PINNED byte-exact"
+++

# LightMap grid-sizing rule PINNED byte-exact

(`light.rs` `axis_grid`/`bake_surf`, 2026-07-18,
§20 §22). Decoded the editor's `FLightMapIndex` grid formula from the golden `Test_Castle.dx`:
grid dim = `Clamp(ceil(extent/lumel_scale), 2, 256)` (was `trunc((extent−0.25)/scale − 0.5)+1`,
under-counting 134/484 records by −1); scale = `(extent+0.25)/(size−1)` (was `extent/(size−1)`);
extent = `(vert−Base)·Tex` subtract-base-FIRST (f32-rounds differently from `v·Tex − Base·Tex`
on angled surfaces — 484/484 vs 412/484). RAW positional: `LightMap` 76.2%→**87.0%**, `LightBits`
48434 B→49701 B (was −1082 vs editor, now +185). `UClamp`/`VClamp`/`u_scale`/`Pan.x` now 484/484.
Guards unregressed (nodes 1156, surfs 485, Points 2035, LightMap 484/14528 B). New Rust regression
`axis_grid_matches_editor_ceil_rule`; harness `lightmap_grid_diff.py`. **Remnant:** `Pan.y`/`VScale`
427/484 — the 57 misses are records where native's base-point/TextureV **geometry** differs from
editor by f32 (Points/Vectors not yet byte-exact, owned outside `light.rs`); follow for free as
those reach parity. `LightBits` content gap now dominated by per-leaf permeating-light omission
(§21 A) + LOS/backface bits (§17), separate larger levers.
