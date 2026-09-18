+++
priority = "p1"
kind = "feature"
summary = "mesh actors should render before a geometry rebuild, same as UnrealEd -- the capability already exists in preview_native.py, just isn't wired into the GUI's pre-build path"
+++

# Mesh actors should render independent of geometry build

Owner report (2026-09-18): "UnrealEd renders meshes without geometry rebuild. We should too. That
should be distinct and separate. Log to queue, let me know if there are decisions - this is
important."

## Why mesh actors currently render as white spots before a Rebuild

Confirmed by code read (`uedcli/serve/scene.py`):

- `build_wireframe_payload` (the cold-open / no-Rebuild-yet payload) sets `tex_offset=0` and calls
  `_build_actors(..., tex_offset=0, ...)`. Its own doc comment: `/atlas` (`app.py`'s atlas route)
  builds its atlas from ONLY `trunk.sprite_table` when no geometry is pinned -- it skips
  `geometry.texture_table` entirely.
- `_build_actors` resolves a POINT actor's billboard icon from `trunk.actor_sprites` (`Load`-owned,
  no CSG involved) -- this already works pre-build, which is why point-actor icons render fine
  before a Rebuild.
- A MESH actor's actual triangles never go through `_build_actors` at all. They ride in
  `ScenePayload.polys`, built by `build_scene_payload` from `geometry.polys` -- and `geometry` is
  `_BuiltGeometry`, the CSG/BSP solve's output. `build_wireframe_payload` returns `polys=[]`
  unconditionally (no geometry pinned yet), so a mesh actor has no triangles and no resolvable
  texture (an unresolved `THREE.Texture` falls back to a solid white 1x1) until the first Rebuild.

## The capability already exists -- it's a wiring gap, not a missing mechanism

`uedcli/preview_native.py::_mesh_actor_polys` (used by `level photo`/`class preview`, i.e. the
offline raster tools) resolves one DT_Mesh actor's frame-0 triangles + skins + mesh asset ref
**from the actor and its class defaults alone** -- no CSG, no BSP, no `_BuiltGeometry` of any kind.
`uedcli/meshworld.py` then world-transforms those triangles using only the actor's own
Location/PrePivot/Rotation/Scale (all authored T3D data, present in `trunk` before any build).

This is structurally the same shape as `trunk.sprite_table`'s existing independence from CSG for
point-actor icons -- the pattern the GUI's own pre-build path already relies on. Static mesh actors
just never got the equivalent treatment: `uedcli/serve/scene.py` only ever pulls mesh triangles out
of the CSG-solved `geometry.polys`, never out of `_mesh_actor_polys` directly.

## The real design decision (not decided here -- see below)

**Fixing the pre-build path is a contained, mechanical change**: give `build_wireframe_payload` its
own mesh-actor triangle+texture resolution, mirroring `trunk.sprite_table`'s existing atlas slot
(each mesh actor's own skin(s) resolved into a THIRD atlas source, alongside sprites and
`geometry.texture_table`, via `_mesh_actor_polys` + `meshworld.py`).

The open fork is what happens to the ALREADY-BUILT (post-Rebuild) path once that exists:

- **Option A -- one mesh pipeline, always.** `build_scene_payload` stops sourcing mesh-actor
  triangles from `geometry.polys` too, and uses the same independent per-actor resolution in both
  the pre- and post-build payloads. Matches the owner's framing ("distinct and separate") most
  literally -- mesh rendering never depends on build state, matching real UnrealEd (meshes are never
  part of BSP/CSG). Larger change: touches `build_scene_payload`/`filtered_geometry_polys`'s
  poly-owner-attribution logic, which currently assumes a mesh actor's triangles can ride in the
  same `ScenePayload.polys` list as world-BSP surfaces.
- **Option B -- two mesh pipelines.** The new independent resolution only feeds
  `build_wireframe_payload` (pre-build preview); `build_scene_payload` keeps sourcing mesh triangles
  from `geometry.polys` exactly as today, post-Rebuild. Smaller, safer change -- but leaves two
  separate mesh-rendering code paths that could drift (e.g. a mesh actor's texture atlas index means
  something different pre- vs. post-build), and a mesh actor could visibly change appearance the
  moment a Rebuild finishes even though nothing about the mesh itself changed.

**Decided (owner, 2026-09-18): Option A.** One mesh pipeline, always -- mesh-actor rendering never
depends on build state, pre- or post-Rebuild. `build_scene_payload` is to stop sourcing mesh-actor
triangles from `geometry.polys`; both payloads resolve mesh actors the same way, via the independent
per-actor path (`_mesh_actor_polys` + `meshworld.py`), same as `trunk.sprite_table` already does for
point-actor icons. `geometry.polys`/`filtered_geometry_polys` become scoped to true world/BSP-solved
surfaces only -- a Mover's own brush polys (not part of world CSG either, per the existing
`_mover_world_polys` comment in `preview_native.py`) may already need the same treatment; check
whether it already gets it or is a separate, pre-existing case.

## Where to look

`uedcli/serve/scene.py` (`build_wireframe_payload`, `build_scene_payload`, `_build_actors`,
`filtered_geometry_polys`), `uedcli/preview_native.py` (`_mesh_actor_polys`), `uedcli/meshworld.py`
(world-space placement), `uedcli/serve/app.py` (the `/atlas` route's texture-table assembly).
