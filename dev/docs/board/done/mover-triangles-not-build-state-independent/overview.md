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

## Done (2026-09-18) — mirrored the mesh-actor fix

`preview_native.py`'s mover-triangle resolution is extracted the same way `_mesh_actor_polys` was:
`resolve_mover_actor_polys(level, index, *, textures, hidden_prop=None)` reuses `_mover_world_polys`
(no CSG/BSP dependency, unchanged) and produces the same 8-tuple `resolve_mesh_actor_polys` does,
using each poly's OWN authored `Texture`/`TextureU`/`TextureV` (`texframe.world_uv_frame` +
`textures.index_for`) — confirmed simpler than the mesh path exactly as this item guessed: no
`MultiSkins`/material-index resolution at all. `resolve_mover_scene_polys(level, index,
search_files, hidden_prop="bhiddened")` is the GUI's own Load-owned entry point, mirroring
`resolve_mesh_scene_polys` (private `_TextureTable`, `([], [], [])` on empty `search_files`).
`_mover_world_polys` gained an optional `skip` callback (called once per Mover actor before its
polys are transformed) so a hidden Mover can be dropped wholesale — `build_scene`'s own call
passes none, so `level photo --native` is byte-for-byte unaffected.

`build_scene` gained `include_movers: bool = True` (mirrors `include_meshes`), folded into
`geom_hash` the same way; its own mover loop now calls `resolve_mover_actor_polys` instead of
inlining the transform+flags+UV+texture logic — verified equivalent field-for-field against the
original `add_poly` call site (same flags computation, same PF_INVISIBLE drop order, same
`i_surf=None`/owner tuple shape).

`serve/scene.py`'s `_LoadedTrunk` grew `mover_polys`/`mover_owners`/`mover_texture_table`;
`_wrap_mover_scene_polys` mirrors `_wrap_mesh_scene_polys` exactly and is called from BOTH
`build_wireframe_payload` (Mover polys now render pre-Rebuild, appended after mesh in the tail) and
`build_scene_payload` (appended after mesh, which is appended after the filtered world/BSP prefix —
`/lightmap`'s positional-index invariant into that prefix is unaffected, since Movers were never lit
and the prefix's own content/order doesn't change). `serve/app.py`'s `_get_trunk`/`/load` now also
call `resolve_mover_scene_polys`; `_build_and_publish_geometry` passes `include_movers=False`
alongside `include_meshes=False`; `/atlas` appends `mover_texture_table` after
`mesh_texture_table`.

**The one real wrinkle mesh actors didn't have — hidden-actor filtering — is real and handled.**
Before this fix, a hidden Mover's surfaces rode inside `geometry.polys` and were dropped
post-hoc by `filtered_geometry_polys`'s `hidden_add_owners` (which treats a Mover as CSG_Add-like,
since it has no `CsgOper` — always safe to drop whole, per that function's own docstring). Once
Mover polys move to the independent, Load-owned path, that downstream filter no longer sees them at
all, so `resolve_mover_actor_polys`'s own `hidden_prop` check (same instance-else-class-default
convention `_mesh_actor_polys` uses) replaces it — `resolve_mover_scene_polys` passes
`"bhiddened"`, so a hidden Mover contributes zero triangles from the GUI's own Load, exactly
matching the old downstream-drop's outcome. No other wrinkle was found: the wireframe outline
(`BrushHighlight`/`SceneActor.brush`) and its CSG-classification colour are computed straight from
`actor.brush.polys` (authored, local-space) independent of both CSG state and this fix — untouched;
`ScenePoly.owner`/`i_brush_poly` keep the exact same `(actor.name, i_brush_poly)` addressing a real
CSG-solved Mover surface used to carry, so click-to-select/highlighting is unaffected; Movers never
had a lightmap either way (`i_surf` was already always `None` for a mover poly, pre- and
post-fix).

**Frontend needs no change.** `web/src/scene/SceneResourcesContext.tsx` already groups
`ScenePayload.polys` into mover/mesh/world buckets by `owner` membership against
`scene.actors.filter(a => a.is_mover)` — a pure attribution lookup, not a positional/array-order
assumption — so moving Mover polys to a different position in the wire array (now appended after
mesh, in both payloads) changes nothing client-side. Verified by reading
`SceneResourcesContext.tsx`'s `moverNames`/grouping logic; no frontend file touched.

**Verification.** This sandbox's docker daemon cannot bind-mount `/workspace` (blocks building
`uedcli_native`, the exact limitation the mesh-actor fix's own board item hit) — worse here than for
meshes, since even an OFFLINE `movers.is_mover`/hidden-actor check against a REAL `ClassIndex` needs
the native extension to parse `.u` package bytes. A standalone script
(`_scratch/verify_mover_independence.py`, not committed) exercises everything that doesn't need a
real class index: `resolve_mover_actor_polys` reproduces `_mover_world_polys`'s own world-vertex
output exactly (a rotated/pre-pivoted mover); a REAL fixture texture
(`uedcli/tests/fixtures/LUM_InfoPortraits.utx`) decodes through a Mover's own authored `Texture` ref
via the shared `_TextureTable`; `resolve_mover_scene_polys` degrades to `([], [], [])` on empty
`search_files`; `build_wireframe_payload` — fed a hand-built `_LoadedTrunk` for a level with ONLY a
Mover (no CSG brush at all) — returns the Mover's real textured triangles with correct
`tex_index`/`owner`/`i_brush_poly` and `lightmap=None`, proving the pre-Rebuild path needs no CSG
model; `_mover_world_polys`'s new `skip` callback wiring drops/keeps the whole actor correctly. NOT
exercised (needs `uedcli_native`, genuinely blocked, not skipped for convenience):
`resolve_mover_actor_polys`'s own `hidden_prop="bhiddened"` check against a REAL, schema-resolvable
class index, and the pytest suite's native-gated tests
(`test_serve_scene.py`/`test_serve_app.py`/`test_preview_native.py`/`test_serve_textures.py` — ran
offline, 10 passed / 17 skipped, all skips are the same pre-existing `pytest.importorskip
("uedcli_native")`/corpus gates, no new failures). Whoever next has a working native-ext build
should run `bin/test -k "test_serve_scene or test_serve_app or test_preview_native or
test_serve_textures"` once to confirm the native-gated paths, same ask the mesh fix's own writeup
left open.

No GUI-PARITY.md update: this is an architectural/backend fix, not a UED22-fidelity RE question.
