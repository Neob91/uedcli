+++
priority = "p?"
kind = "debug"
summary = "Movers, like mesh actors, don't need CSG -- but still only get real triangles post-Rebuild"
+++

# Mover triangles not build-state independent like mesh actors

Found while building `mesh-actors-should-render-independent-of-geometry-build` (item 5 of that
task's brief asked to check this).

## The finding

A Mover's real triangle geometry is resolved by `preview_native._mover_world_polys`/
`_mover_actor_world_polys` -- a pure per-actor world transform (`actor_linear`, `PrePivot`, the
authored `brush.polys`) with **no BSP/CSG dependency at all**, same shape as `_mesh_actor_polys`.
But it is only ever called from inside `preview_native.build_scene`'s one combined pipeline, which
`uedcli/serve/app.py` only runs at `POST /rebuild` (`_build_and_publish_geometry`). So:

- **Before a Rebuild**: `build_wireframe_payload` has no geometry to source Mover triangles from.
  A Mover still gets a wireframe OUTLINE (`SceneActor.brush`/`BrushHighlight` -- every brush actor,
  Mover included, gets this), but no real textured triangles, same as a mesh actor had before this
  change.
- **After a Rebuild**: Mover triangles ride in `geometry.polys` (added by `build_scene`'s
  `_mover_world_polys` loop), textured and real.

This is the SAME architectural gap mesh actors had, for the same reason (no CSG dependency, yet
gated behind build state) -- just never reported by the owner.

## Why not fixed in the mesh-actor change

Out of scope for that item: the owner's brief and board item (`mesh-actors-should-render-
independent-of/overview.md`) scoped the fix to mesh actors specifically ("Option A" ruling names
`_mesh_actor_polys` + `meshworld.py`); Movers were flagged only as a "determine and note" side
question, not asked to be fixed. Movers are also a more visible/architecturally different actor
kind (BOTH a brush -- with wireframe/selection/CSG-classification -- AND (per this finding) an
independent-of-CSG solid), so folding them into the same fix would have widened the change well past
what was asked.

## What a fix would look like (not attempted)

Mirror the mesh-actor fix: extract Mover-triangle resolution into an independent, `_LoadedTrunk`-
owned resolver (reusing `_mover_world_polys`/`_mover_actor_world_polys`, which already need no BSP
model) called from BOTH `build_wireframe_payload` and `build_scene_payload`, and pass
`build_scene`'s own CSG-integrated Mover loop an `include_movers=False` flag mirroring
`include_meshes`, the same way `geometry.polys` was made to stop carrying mesh triangles. Movers
need their OWN texture-atlas slot too (real `poly.texture` refs via `texframe.world_uv_frame`, not
skins -- simpler than the mesh path, no `MultiSkins`/material-index resolution needed).

Not measured for cost; flagging for the owner/next agent to scope and prioritize.
