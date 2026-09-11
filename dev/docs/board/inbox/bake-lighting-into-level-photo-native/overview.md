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

## Findings 2026-09-11 — checked as a "quick wire", is NOT one. Not implemented.

Investigated whether this is a same-session wire-up, per the framing this item and
`level-preview-lit` both carry. Half of it is; the other half is a real gap. Not implemented —
flagging per instruction to stop rather than push through.

**Confirmed cheap:**
- `build_scene` (`uedcli/preview_native.py`) already holds the `Built` object from
  `uedcli_native.build_geometry_bspcsg` before calling `serialize_model` on it — zones/leaves/portals
  are already finalized inside it (`bspcsg.rs`'s finalize section calls
  `zones::assign_leaves_and_zones`), exactly what `light::bake`/`permeating_lights` need. No extra
  building required.
- `bake_lighting(built, lights)` is already a `#[pyfunction]` (`uedcli-native/src/lib.rs:475`),
  callable on that same `Built` object, one line.
- Gathering participating lights is already implemented and reusable verbatim:
  `uedcli/native/materialize.py`'s `gather_lights(level, *, defaults)` returns
  `(name, location, radius, special_lit)` per the editor's real gather predicate — exactly the
  `LightInput` shape `bake_lighting` takes. `build_scene` already has everything it needs
  (`level`, and `defaults` via the `classdefaults.ClassDefaults` `index` already carries).

**The real blocker — `light::bake`'s output is a shadow mask, not a lit color.**

`Model.light_map`/`light_bits`/`lights` are a purely GEOMETRIC per-lumel visibility bitmask per
participating light (line-of-sight + radius cutoff). `light.rs`'s own docstring: "Brightness, hue and
attenuation are applied by the GAME at render time from the light actors... the bake is purely
geometric." Turning that into a rendered pixel color needs two things that don't exist in uedcli
today:

1. **A lightmap-space UV frame per polygon**, distinct from the frame `render.rs`/
   `preview_native.py` already carry. `RenderPoly.uv_base/uv_axis_u/uv_axis_v` is the Python-derived
   AUTHORED-texture-alignment frame (`preview_native.py`'s own docstring: "the built surf's texture
   vectors are NEVER read"). The lumel grid `light::bake` computes lives in the BUILT model's own
   synthesized texture space (`Model.Vectors` `pBase`/`vTextureU`/`vTextureV`) — a different frame
   the renderer doesn't track per polygon at all. Sampling a lumel per pixel means threading a
   second frame (plus the surf's `i_light_map` index) through the FFI (`RenderPolyTuple`) and adding
   a lumel-lookup path to `render.rs` — mechanically similar to code already in `light.rs`, but not
   exposed to or reusable by the rasterizer as it stands.
2. **An actual illumination model.** Even with lumel visibility in hand, a lit pixel needs each
   contributing light's brightness/hue/saturation/color and a radius falloff combined with the
   visibility bit. None of that exists anywhere in uedcli: `LightBrightness`/`LightHue`/
   `LightSaturation` are never read by any code path (checked). `gather_lights` deliberately extracts
   only the three geometric fields `bake` needs and documents that brightness/hue/attenuation are
   the game's job. Building this is a new RE effort (UE1's real light-color/falloff formula), not
   reuse of the native-materialize campaign's work.

`level-preview-lit`'s summary cites a prior design decision that would have pinned exactly this math
("native-preview spec §8, decision 2026-07-16 12:13: ...raw dot-product lumel frame, NOT the panned
texel frame"). That spec file no longer exists — specs are ephemeral per project convention, and
commit `9c0f7874` ("Move every spec and plan into the board item that owns it") is where the
standalone doc left the tree; no surviving copy of §8's content was found in the current board tree.
The one place this might already have been designed is gone — closing this needs a fresh design
pass, not a lookup.

**Net:** the CSG/zone/light-gathering plumbing is already-paid-for, as hypothesized. But visible
"real lighting" (lit surfaces with actual brightness/color, not just a shadow mask) needs (a) a
second lightmap-UV-frame threaded through the renderer FFI and rasterizer, and (b) new RE/design
work for light color+brightness+falloff with no prior art here. Realistic scope: closer to a
multi-day RE+implementation effort than a same-session wire-up. Not sized further — recommend an
owner ruling on acceptable v1 shading fidelity (e.g. a crude "reachable-light count" intensity with
no color, sidestepping the falloff RE) before scoping real work, since that choice changes what
needs building.
