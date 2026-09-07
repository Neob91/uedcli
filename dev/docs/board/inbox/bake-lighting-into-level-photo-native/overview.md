+++
priority = "p3"
kind = "unknown"
summary = "level photo --native is flat-shaded; bake real lighting into the preview"
+++

# Bake lighting into level photo --native

`level photo --native` currently renders unlit: `render.rs`'s `RenderPoly` carries one texture +
UV frame and a synthetic per-face brightness hack (not real light), purely so adjacent same-texture
faces read as distinct 3-D shapes. `--game` is the only backend that shows real lighting today.

## What's already there

`uedcli_native.bake_lighting` already exists — the native-materialize campaign's lightmap engine,
already UE1-faithful (byte-parity-tested against UED22 in that campaign). `build_scene`
(`preview_native.py`) already calls the same CSG/BSP core (`build_geometry_bspcsg`) that
`bake_lighting` operates on — the world model is already in hand at the point a lightmap bake
would need to run.

## Two separate problems, not one

- **World BSP surfaces**: baked lightmaps, sampled per-texel. Wiring `bake_lighting`'s output into
  the scene build is mostly Python glue (similar in kind to the mesh-rendering work,
  `native-mesh-rendering-in-level-photo-native`). But unlike that work, this DOES need a
  `render.rs` change: the rasterizer has no path today to sample a second (lightmap) texture per
  poly and multiply it into the base color — a real, new rasterizer feature, not just Python
  plumbing keeping the existing `RenderPoly` shape.
- **Mesh/mover actors**: real UE1 lights them differently — per-vertex lighting computed from
  nearby lights at the actor's position, no lightmap involved. This is a separate mechanism from
  world lightmapping and needs its own RE + implementation if meshes/movers are to read as lit
  too, not just the world.

## Scope options (not yet decided)

- World-only lighting (BSP surfaces lit, meshes/movers stay flat) — smaller, still needs the
  `render.rs` lightmap-sample feature.
  vertex-lit meshes/movers on top — bigger, a second RE effort.

Not scoped/sized yet. Raised as a follow-on from
`native-mesh-rendering-in-level-photo-native` while discussing what `--native` shares with native
materialize.
