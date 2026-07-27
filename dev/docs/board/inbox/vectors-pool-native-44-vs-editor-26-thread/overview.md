+++
priority = "p2"
kind = "implement"
summary = "`Vectors` pool (native 44 vs editor 26): thread authored `TextureU/TextureV`"
+++

# `Vectors` pool (native 44 vs editor 26): thread authored `TextureU/TextureV`

Oracle: editor has 26 vectors already at `bspOptGeom` entry; native's 18 extras are face-local
`default_texture_axes` bases (`bspcsg::alloc_surf`) that no `bspAddVector` threshold can merge. The
trunk brush polys DO carry authored `TextureU/TextureV` (world/45°-aligned → dedup into the
26-normal pool), but `materialize._build_brush_input` never parses/threads them. Fix spans
`materialize.py` → Rust `BrushInput`/`FPoly` → `alloc_surf` (build.rs/csg.rs/lib.rs), OUTSIDE the
`bspoptgeom.rs`/`bspcsg.rs` dedup scope. Details `42-bspoptgeom-decode.md` §8.
