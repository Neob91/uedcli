"""`level photo --native` — the offline draft backend (spec
board item `de-containerization-follow-on-spec-items`). Zero docker, zero editor, zero game:
the trunk is carved in-process by the faithful Rust CSG core (`uedcli_native.build_geometry_bspcsg`,
the incremental `bspBrushCSG` port that matches the editor's surviving surfaces), each
built surface is joined back to its SOURCE brush poly for texture/Pan/flags (the same
`i_actor`/`i_brush_poly` provenance `assemble._patch_surf_refs` consumes at materialize),
textures decode natively (`uedcli.utexture`), and `uedcli_native.render_frame` software-
rasterizes each SHOT pose to an RGB buffer that Pillow encodes as PNG.

Geometry marshals through the SHARED `brush_marshal._build_brush_input` (`_marshal_brush` is a
thin wrapper): a rotated/scaled/mirrored/sheared brush bakes its full linear map `L` into the CSG
world transform and renders (a degenerate/sheared-singular scale exits 2, named). Draft-validated
offline against `rotation.world_vertices`, not editor goldens. UV is SCALE-AWARE: the frame uses the
same full `L` so textures sit correctly on scaled/sheared/mirrored faces.

The per-surf UV frame is computed HERE, Python-side, from the source poly's authored
`Origin`/`TextureU`/`TextureV`/`Pan` (`base_w = Location + L·(Origin − PrePivot)`,
`axes_w = (L⁻¹)ᵀ·axes`, `L = PostScale·R·MainScale`) — the built surf's texture vectors are NEVER read
(the build synthesizes
default axes that ignore authored alignment, and Pan doesn't survive the build at all;
spec §5). The function is `texframe.world_uv_frame`, shared with the `brush poly align` verbs
(`polyalign.py`), so the two cannot disagree about where a texture sits.
Movers are out of world CSG, so they render directly as world-transformed
`extra_polys` at the base pose (`rotation.actor_linear` — the same math every measurement
verb uses)."""
from __future__ import annotations

import re
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from . import build_cache, movers
from .classindex import CORE_OBJECT, ClassRefError
from .normalize import is_builder_brush
from .preview import sprite_footprint
from .preview_shots import ResolvedShot, Shot, resolve_pose, shot_filename
from .rotation import (actor_linear, actor_prepivot, deg_to_uu, euler_to_matrix_uu, matvec)
from .texframe import poly_flags_int, world_uv_frame
from .transform import DegenerateTransformError
from .utexture import TextureError, TextureResolver, resolve_or_procedural_red

PF_INVISIBLE = 0x1
PF_MASKED = 0x2                                       # alpha-test: palette-index-0 texels cut out
PF_TRANSLUCENT = 0x4                                  # additive blend (render.rs `blend_mode`)
PF_MODULATED = 0x40                                   # modulate-2x blend
PF_TWO_SIDED = 0x100                                  # no backface cull
PF_PORTAL = 0x04000000                                # visible portal sheet; also no backface cull
# The Rust rasterizer (`render.rs`) composites both blend modes for every poly this module sends it
# -- world/mover surfaces (`add_poly`) and mesh-actor triangles alike -- via each poly's own
# `poly_flags`. The web preview reads the same decisions off `poly_two_sided`/`poly_blend` below.


def poly_two_sided(flags: int) -> bool:
    """Does this poly draw both faces (no backface cull)? True iff `PF_TwoSided` or `PF_Portal` is
    set -- render.rs's own `light_in_front` cull exemption (`URender::OccludeBsp`)."""
    return bool(flags & (PF_TWO_SIDED | PF_PORTAL))


def poly_blend(flags: int) -> str:
    """The poly's compositing mode from its merged `PolyFlags`: `"translucent"` (additive),
    `"modulated"` (modulate-2x), or `"opaque"`. Translucent wins over Modulated, matching
    render.rs's `blend_mode` precedence. Masking is orthogonal (its own resolved field). Mirror /
    FakeBackdrop are whole re-render passes the web can't do yet, so those draw opaque here (spec)."""
    if flags & PF_TRANSLUCENT:
        return "translucent"
    if flags & PF_MODULATED:
        return "modulated"
    return "opaque"


# The game's first-person default horizontal FOV: Engine.PlayerPawn defaultproperties
# `DesiredFOV=75.000000` / `DefaultFOV=75.000000` (DX install `Engine/Classes/PlayerPawn.uc:4940`,
# read 2026-07-16; DeusExPlayer does not override it). Spec §3 pins --fov's default to this.
DEFAULT_FOV = 75.0
DEFAULT_SIZE = (1280, 960)

_CSG_OPER = {"CSG_Add": 1, "CSG_Subtract": 2}


class NativePreviewError(Exception):
    """User-facing native-photo failure (→ stderr + exit 2, never a traceback)."""


# --------------------------------------------------------------------- brush inputs

def _marshal_brush(actor) -> tuple:
    """One CSG brush actor → the flat `BrushTuple` `build_geometry`/`build_geometry_bspcsg` take,
    via the shared `native.brush_marshal._build_brush_input` — the SINGLE transform-application home
    (scaled/mirrored/sheared brushes bake their linear map `L` into `rot`, unscaled take the exact
    rotation-only path). A degenerate/sheared scale the marshaller refuses surfaces as a named
    exit-2, never a traceback. The built model's surf tex axes are unused by preview (it derives UV
    frames from the join polys' authored axes separately), so passing the authored axes is harmless."""
    from .native.brush_marshal import BuildError, _build_brush_input
    try:
        return _build_brush_input(actor.name, actor)
    except BuildError as e:
        raise NativePreviewError(str(e)) from e


def _csg_oper_or_skip(name: str, raw: dict) -> int | None:
    """The `_CSG_OPER` code for a brush, or None (with a warning) for a non-world op — Intersect/
    Deintersect never appear in a trunk (live-editor verbs); anything unknown renders nothing."""
    oper = _CSG_OPER.get(raw.get("CsgOper", "CSG_Add"))
    if oper is None:
        print(f"WARNING: brush {name}: CsgOper {raw.get('CsgOper')!r} is not a world CSG op; "
              f"skipped", file=sys.stderr)
    return oper


def _brush_inputs(level, index) -> tuple[list, list[tuple[str, list]]]:
    """CSG brush actors (trunk order) → the `BrushTuple` flat buffers `build_geometry`
    takes, plus the `(actor_name, polys)` join list indexed by the surf `i_actor` tag.
    Movers and the transient builder brush are EXCLUDED from world CSG (movers render as
    extra_polys; the builder brush is editor scratch)."""
    brushes, join = [], []
    for name in level.order:
        actor = level.actors.get(name)
        if actor is None or actor.brush is None:
            continue
        if movers.is_mover(actor, index) or is_builder_brush(actor):
            continue
        if _csg_oper_or_skip(name, dict(actor.props)) is None:
            continue
        brushes.append(_marshal_brush(actor))
        join.append((name, actor.brush.polys))
    return brushes, join


# --------------------------------------------------------------------- geometry extract

def _node_polys(model) -> list[tuple[list[tuple[float, float, float]], int, int, int, int]]:
    """Each BSP node's polygon from its vert pool → (world verts, i_actor, i_brush_poly,
    poly_flags, i_surf). `poly_flags` is the surf's OWN merged actor+poly `PolyFlags` (the Rust CSG
    core ORs the brush-level flags onto it — `native/brush_marshal.py`'s marshalling docstring) —
    single source for both preview renderers' backface-cull exemption, available even when the join
    below is out of range (a BSP node always has a surf; only i_actor/i_brush_poly can miss).
    `i_surf` (= `n.i_surf`) is the surf's own index in `model.surfs` — how `build_scene` joins a
    poly to its baked `SurfRadiance` (`bake_radiance`'s output is keyed by this same index).
    Guarded like `assemble._patch_surf_refs`: an out-of-range index never raises — the surf
    joins to no source poly and renders flat grey."""
    out = []
    for n in model.nodes:
        if n.num_vertices < 3:
            continue
        if not (0 <= n.i_surf < len(model.surfs)):
            continue
        if n.i_vert_pool < 0 or n.i_vert_pool + n.num_vertices > len(model.verts):
            continue
        idx = [model.verts[n.i_vert_pool + k].i_vertex for k in range(n.num_vertices)]
        if any(not (0 <= i < len(model.points)) for i in idx):
            continue
        s = model.surfs[n.i_surf]
        out.append(
            ([model.points[i] for i in idx], s.i_actor, s.i_brush_poly, s.poly_flags, n.i_surf))
    return out


def _mover_actor_world_polys(actor) -> list[tuple[list, object, object]]:
    """One mover actor's brush polys world-transformed at the BASE pose
    (`Location + L·(v − PrePivot)`, `L = actor_linear` — the full scale/rotation map, so a scaled
    mover renders at its real size). A mirrored `L` (`det < 0`) reverses each ring — LOAD-BEARING
    now that both preview renderers backface-cull by winding: a mirrored mover without this flip
    would render inside-out (culled where it should show, and vice versa). Returns
    `(world_verts, actor, poly)` so the UV frame comes from the same authored fields.

    A degenerate (non-invertible) `MainScale`/`PostScale` exits 2 naming the actor, same as a
    world-CSG brush (`brush_marshal._build_brush_input`'s `reject_degenerate`) — movers skip world
    CSG entirely (`_in_world_csg`), so without this check here a degenerate mover would silently
    collapse to a zero-area poly instead of refusing."""
    from .rotation import actor_main_scale, actor_post_scale
    from .transform import flip_winding, reject_degenerate
    loc = tuple(float(c) for c in (actor.location or (0, 0, 0)))
    pp = tuple(float(c) for c in actor_prepivot(actor))
    L = actor_linear(actor)
    scaled = not (actor_main_scale(actor).is_identity() and actor_post_scale(actor).is_identity())
    if scaled:
        try:
            reject_degenerate(L, actor.name)
        except DegenerateTransformError as e:
            raise NativePreviewError(str(e)) from e
    flip = L is not None and flip_winding(L)
    out = []
    for poly in actor.brush.polys:
        world = []
        for v in poly.vertices:
            rel = (float(v[0]) - pp[0], float(v[1]) - pp[1], float(v[2]) - pp[2])
            if L is not None:
                rel = matvec(L, rel)
            world.append((loc[0] + rel[0], loc[1] + rel[1], loc[2] + rel[2]))
        if flip:
            world.reverse()
        out.append((world, actor, poly))
    return out


def _mover_world_polys(level, index, *, skip=None) -> list[tuple[list, object, object, int]]:
    """Movers render directly (no BSP surfs): each brush poly world-transformed at the BASE
    pose. A draft preview without doors would be actively misleading (spec §5). The 4th element
    is the poly's own index into `actor.brush.polys` -- `BRUSH:IDX` addressing (`uedcli/surface.py`),
    the same index space `_node_polys` reports as `i_brush_poly` for CSG-solved surfaces. Enumerated
    here (not inside `_mover_actor_world_polys`, whose other two callers -- `solve_world_surfaces`,
    `preview_wire.py` -- have no use for it) since its per-actor output is already poly-ordered.

    `skip`, if given, is called once per Mover actor (before transforming its polys) and drops the
    whole actor's polys when it returns True -- `resolve_mover_actor_polys`'s independent,
    build-state-free resolver uses it for hidden-actor filtering; `build_scene`'s own call passes
    none, unchanged."""
    out = []
    for name in level.order:
        actor = level.actors.get(name)
        if actor is None or actor.brush is None or not movers.is_mover(actor, index):
            continue
        if skip is not None and skip(actor):
            continue
        out += [(world, a, poly, i)
               for i, (world, a, poly) in enumerate(_mover_actor_world_polys(actor))]
    return out


def resolve_mover_actor_polys(level, index, *, textures: _TextureTable,
                              hidden_prop: str | None = None, class_defaults=None
                              ) -> list[tuple[tuple, tuple[str, int]]]:
    """Every Mover's own brush polys, world-transformed at the base pose -> `[(poly_tuple,
    (actor.name, i_brush_poly)), ...]`, `poly_tuple` the same 8-tuple `resolve_mesh_actor_polys`
    returns. Built from `_mover_world_polys` alone -- already world-space, no CSG/BSP dependency,
    unlike world-solved brush surfaces (board `mover-triangles-not-build-state-independent`,
    mirroring the mesh-actor fix's "Option A": one mover pipeline, always). Texture resolution
    reuses each poly's OWN authored `Texture`/`TextureU`/`TextureV` (`texframe.world_uv_frame` +
    `textures.index_for`) -- simpler than a mesh actor's skin-decode, since a Mover carries real
    per-poly textures already and needs no `MultiSkins`/material-index resolution.

    `hidden_prop`, when given, drops a Mover WHOLESALE when its own resolved value (instance else
    class default, the same convention `_mesh_actor_polys` uses) is `"True"` -- `uedcli serve`'s
    independent path (`resolve_mover_scene_polys`) passes `"bhiddened"`. `None` (this function's own
    default, `build_scene`'s call) skips no actor -- unchanged behavior: `build_scene`'s own callers
    rely on `serve/scene.py::filtered_geometry_polys`'s downstream hidden-owner drop instead, and
    `level photo --native` has never filtered a hidden Mover at all.

    `class_defaults`, if given, resolves a hidden Mover's class default through the shared memo
    instead of a fresh `resolve_class_defaults` call per Mover — `build_scene`'s own call passes
    none (board `load-resolves-mesh-class-defaults-and-texture`)."""
    from .uprops import resolve_class_defaults

    def _hidden(actor) -> bool:
        if hidden_prop is None:
            return False
        defaults = (class_defaults.for_class(actor.cls).defaults if class_defaults is not None
                   else resolve_class_defaults(actor.cls, resolver=index.resolver()))
        instance = {k.casefold(): v for k, v in actor.props}
        value = instance[hidden_prop] if hidden_prop in instance else defaults.get(
            (hidden_prop, 0))
        return str(value or "False").strip() == "True"

    out: list[tuple[tuple, tuple[str, int]]] = []
    for world_verts, actor, poly, i_brush_poly in _mover_world_polys(level, index, skip=_hidden):
        flags = ((poly.flags or 0) | poly_flags_int(dict(actor.props))) & 0xFFFFFFFF
        if flags & PF_INVISIBLE:
            continue                                          # dropped Python-side, matches add_poly
        try:
            base_w, tu, tv, pan = world_uv_frame(actor, poly)
        except DegenerateTransformError as e:    # degenerate-scale mover -> exit 2 (spec §7)
            raise NativePreviewError(str(e)) from e
        tex_index = textures.index_for(poly.texture)
        masked = bool(flags & PF_MASKED) or textures.is_bmasked(tex_index)
        verts_flat = [c for v in world_verts for c in (float(v[0]), float(v[1]), float(v[2]))]
        out.append(((verts_flat, list(base_w), list(tu), list(tv), list(pan), tex_index, masked,
                    flags), (actor.name, i_brush_poly)))
    return out


def resolve_mover_scene_polys(level, index, search_files, class_defaults, *,
                              hidden_prop: str = "bhiddened"
                              ) -> tuple[list[tuple], list[tuple[str, int]], list[tuple]]:
    """`uedcli serve`'s Load-owned, build-state-independent Mover resolution entry point (mirrors
    `resolve_mesh_scene_polys`): every Mover's world-space triangles + a PRIVATE texture table, from
    `level`/`index` alone -- no CSG/BSP dependency (board `mover-triangles-not-build-state-
    independent`). Returns `(polys, owners, texture_table)`: `polys`/`owners` are
    `resolve_mover_actor_polys`'s own pairs, unzipped; `texture_table` is the private
    `_TextureTable.table` this call built, for the caller to publish as its own atlas slot
    (`uedcli/serve/app.py`'s `/atlas` route) alongside `geometry.texture_table`/`sprite_table`/
    `mesh_texture_table` — never folded into any of them.

    Returns `([], [], [])` when `search_files` is empty -- matches `resolve_mesh_scene_polys`'s own
    degrade disposition for the same condition, never a crash. `hidden_prop` defaults to
    `"bhiddened"` (EDITOR visibility, owner ruling 2026-09-14) -- unconditionally drops a hidden
    Mover's own triangles, the same disposition its own surfaces got when they still rode in
    `geometry.polys` (a Mover has no `CsgOper`, defaults to `CSG_Add`, always safe to drop whole --
    see `serve/scene.py::filtered_geometry_polys`'s docstring). `class_defaults` (a `ClassDefaults`)
    is REQUIRED -- the caller's own shared memo, threaded down to `resolve_mover_actor_polys` so a
    hidden Mover's class default resolves once per distinct class, not once per Mover (board
    `load-resolves-mesh-class-defaults-and-texture`); required rather than optional so a future
    caller can't silently forget to pass it."""
    if not search_files:
        return [], [], []
    textures = _TextureTable(TextureResolver(search_files, class_index=index))
    resolved = resolve_mover_actor_polys(level, index, textures=textures, hidden_prop=hidden_prop,
                                         class_defaults=class_defaults)
    polys = [poly for poly, _owner in resolved]
    owners = [owner for _poly, owner in resolved]
    return polys, owners, textures.table


def _mesh_actor_polys(actor, index, search_files, *, hidden_prop: str = "bhidden",
                      class_defaults=None, texture_resolver=None
                      ) -> tuple[list, dict, object, tuple[str, str] | None, dict]:
    """One DT_Mesh actor's frame-0 triangles (mesh-local, NOT yet world-transformed -- the caller
    does that after computing the actor's winding/degenerate check once) plus its resolved skins,
    its decoded mesh, the mesh ASSET ref, and its resolved class defaults:
    `(triangles, skins, mesh, ref, class_defaults)` where `triangles` is `frame_triangles(mesh)`'s
    own 8-tuple list, `skins` is `{material_index: (w, h, rgb, b_masked)}`, `mesh` is the decoded
    `umesh.Mesh` the caller needs for `apply_mesh_linear`/`mesh_actor_linear`, `ref` is
    `meshfacts.parse_mesh_ref`'s `(package_stem, mesh_name)` -- returned rather than recomputed by
    the caller, and half of the skin cache key (`_TextureTable.index_for_decoded`) -- and
    `class_defaults` is this call's own `resolve_class_defaults` result, returned so the caller can
    feed it to `meshworld.mesh_actor_translation`/`mesh_vertex_to_world` (a class-default `PrePivot`
    -- e.g. `DeusEx.HKHangingPig`/`HangingChicken` -- must still apply even though no instance ever
    states it; board `hanging-mesh-actors-render-low-prepivot-class`).
    Returns `([], {}, None, None, {})` for a non-DT_Mesh actor, one hidden per `hidden_prop`, or one
    with no resolvable Mesh (not an error -- matches `class preview`'s own "not every actor has a
    mesh" disposition, `classes.py::_run_preview`). Converts `meshfacts.MeshFactError`/
    `meshrender.PreviewError` to `NativePreviewError` at this boundary -- matching how
    `classes.py::_run_preview` converts the SAME two exceptions to `CommandError` locally, and how
    `level.py`'s `--native` call site only ever catches `NativePreviewError` (no dispatch.py change
    needed, unlike an earlier draft of this plan).

    `hidden_prop` is the casefolded property `build_scene`'s caller wants checked -- `"bhidden"`
    (GAMEPLAY visibility, `render_shots`'/`level photo`'s default: it shows what the player sees) or
    `"bhiddened"` (EDITOR visibility, `uedcli serve`'s GUI: owner ruling 2026-09-14 — the GUI hides
    `bHiddenEd` actors and ignores `bHidden`). Either way the resolution itself (instance override
    else class default) is the SAME convention `cli/rendering.py::_is_hidden_ed` uses for `bHiddenEd`
    on point actors, just reused here via `field()` below rather than duplicated.

    `class_defaults`, if given (a `classdefaults.ClassDefaults`), resolves this actor's class
    defaults through its shared per-class memo instead of a fresh `resolve_class_defaults` call —
    the same substitution `resolve_actor_sprites` already makes (`preview_native.py:653`).
    `texture_resolver`, if given, is forwarded to `resolve_skins` as its own new `resolver` param —
    one `TextureResolver` shared across every actor `resolve_mesh_actor_polys` calls this for,
    instead of a fresh one per actor. Both default to `None` (today's per-actor-fresh behavior) for
    `build_scene`'s own callers, which pass neither (board
    `load-resolves-mesh-class-defaults-and-texture`)."""
    from collections import ChainMap

    from . import meshfacts, meshrender, typedprops
    from .uprops import resolve_class_defaults

    defaults = (class_defaults.for_class(actor.cls).defaults if class_defaults is not None
               else resolve_class_defaults(actor.cls, resolver=index.resolver()))
    instance = {k.casefold(): v for k, v in actor.props}
    # The actor's own MultiSkins(N)=/Skin= (if it states them) ahead of its class defaults, per
    # index -- board item `per-actor-skins-override-in-native-mesh-render`. `resolve_skins` only
    # ever reads two keys ("multiskins"/"skin") out of its `defaults` param via `.items()`, so a
    # `ChainMap` (stored-wins, first-map-wins per key) needs no signature change there.
    skin_defaults = ChainMap(typedprops.stored_prop_map(actor.props), defaults)

    def field(name: str):
        """The actor's own value for `name` (casefolded key), else its class default — the SAME
        instance-else-default resolution `cli/rendering.py::_resolve_point_render` uses for these
        very properties. A placed actor may override `DrawType` (a DT_Mesh instance of an otherwise
        non-drawing class, or a DT_None instance of a mesh class); reading only the class default
        renders the wrong set."""
        return instance[name] if name in instance else defaults.get((name, 0))

    if (field("drawtype") or "").strip() != "DT_Mesh":
        return [], {}, None, None, {}
    if str(field(hidden_prop) or "False").strip() == "True":
        # Whichever ONE flag the caller asked for (see docstring) — a hidden actor contributes
        # nothing (same disposition as a non-DT_Mesh one, not an error).
        return [], {}, None, None, {}
    mesh_prop = instance.get("mesh") or defaults.get(("mesh", 0))   # empty override → class default
    ref = meshfacts.parse_mesh_ref(mesh_prop)
    if ref is None:
        raise NativePreviewError(
            f"actor {actor.name}: DrawType is DT_Mesh but Mesh ({mesh_prop!r}) is unresolvable")
    try:
        _display, mesh, pkg = meshfacts.decode_mesh(ref, class_fqcn=actor.cls,
                                                     resolver=index.resolver())
        # Skins resolve over the FULL composed path (`search_files`), not `index.package_paths()`
        # (`.u` only): a mesh skin can live in a `.utx` (e.g. `Effects.BioCell_SFX`), which is never
        # on the `.u` set. `search_files` is a superset, so deco-`.u` skins still resolve.
        skins = meshrender.resolve_skins(mesh, pkg, skin_defaults, search_files,
                                         class_fqcn=actor.cls, class_index=index,
                                         resolver=texture_resolver)
    except meshfacts.MeshFactError as e:
        raise NativePreviewError(str(e)) from e
    except meshrender.PreviewError as e:
        raise NativePreviewError(str(e)) from e
    return meshrender.frame_triangles(mesh), skins, mesh, ref, defaults


def resolve_mesh_actor_polys(level, index, search_files, *, hidden_prop: str, textures: _TextureTable,
                             in_solid=None, class_defaults=None
                             ) -> list[tuple[tuple, tuple[str, None]]]:
    """Every non-brush actor's DT_Mesh triangles -> `[(poly_tuple, (actor.name, None)), ...]`, where
    `poly_tuple` is the 8-tuple `(verts_flat, base, axis_u, axis_v, pan, tex_index, masked,
    poly_flags)` -- the same shape `build_scene`'s own `add_poly` appends to `polys_no_light`. Built
    from `level`/`index`/`search_files` alone, via `_mesh_actor_polys` + `meshworld` -- no CSG/BSP
    dependency, unlike world/mover surfaces (board `mesh-actors-should-render-independent-of-
    geometry-build`, owner decision "Option A" 2026-09-18: one mesh pipeline, always). Extracted
    from `build_scene`'s own former inline mesh loop so BOTH that CSG-solved pipeline (`level photo
    --native`, unaffected — see its `in_solid` param below) and `uedcli serve`'s independent,
    build-state-free mesh resolution (`uedcli/serve/scene.py`'s `resolve_mesh_scene_polys` caller)
    share one implementation instead of two copies that could drift.

    `textures` is the CALLER's `_TextureTable` — `build_scene` passes its own single world+mesh
    table (unchanged behavior: one shared atlas per photo); the GUI's independent path passes a
    PRIVATE table of its own (`uedcli/serve/scene.py`), since it has no `geometry.texture_table` to
    share and must keep working before any CSG solve exists.

    `in_solid`, if given, is called with a mesh actor and skips it when it returns True — matches
    `build_scene`'s own "don't draw a mesh in solid space" gate (`_model_point_region`, board
    `meshes-in-solid-space-render-in-photo-and-gui`). Omitted (the GUI's independent path): no such
    filtering happens, because there is no CSG model to test solid-space against before a Rebuild,
    and Option A's ruling ("mesh rendering never depends on build state") means the SAME actor must
    render the same way after one too — a deliberate, noted divergence from `level photo --native`'s
    behavior, not an oversight.

    Builds ONE shared `TextureResolver` for the whole call (when `search_files` is non-empty),
    matching `resolve_actor_sprites`'s own one-resolver-per-call pattern (`preview_native.py:643`)
    instead of `resolve_skins` building a fresh one per actor — applies to EVERY caller
    unconditionally (`build_scene` included), since this needs no external dependency beyond
    `search_files`, which this function already takes. `class_defaults`, if given, forwards into
    every `_mesh_actor_polys` call — `build_scene`'s own calls pass none, keeping today's per-actor
    `resolve_class_defaults` behavior there (board
    `load-resolves-mesh-class-defaults-and-texture`)."""
    from . import meshworld, typedprops
    from .transform import DegenerateTransformError, flip_winding, reject_degenerate

    shared_resolver = (TextureResolver(list(search_files), class_index=index)
                      if search_files else None)
    out: list[tuple[tuple, tuple[str, None]]] = []
    for actor in level.actors.values():
        if actor.brush is not None:
            continue                                     # brushes/movers handled by the caller
        tris, skins, mesh, mesh_ref, mesh_class_defaults = _mesh_actor_polys(
            actor, index, search_files, hidden_prop=hidden_prop, class_defaults=class_defaults,
            texture_resolver=shared_resolver)
        if not tris:
            continue
        if in_solid is not None and in_solid(actor):
            continue
        # This actor's own skin-relevant override, once -- () for the common no-override actor
        # (keeps `index_for_decoded`'s cache hit rate), a real fingerprint only when it states one.
        actor_skin_override = tuple(sorted(
            (k, v) for k, v in typedprops.stored_prop_map(actor.props).items()
            if k[0] in ("multiskins", "skin")))
        L = meshworld.mesh_actor_linear(mesh, actor)
        translation = meshworld.mesh_actor_translation(actor, class_defaults=mesh_class_defaults)
        try:
            reject_degenerate(L, actor.name)
        except DegenerateTransformError as e:
            raise NativePreviewError(str(e)) from e
        flip = flip_winding(L)

        for (v0, v1, v2, uv0, uv1, uv2, material_index, poly_flags) in tris:
            if poly_flags & PF_INVISIBLE:
                continue                                  # dropped Python-side, matches add_poly
            if flip:
                v0, v2 = v2, v0
                uv0, uv2 = uv2, uv0
            w0 = meshworld.apply_mesh_linear(v0, mesh_origin=mesh.origin, L=L,
                                             translation=translation)
            w1 = meshworld.apply_mesh_linear(v1, mesh_origin=mesh.origin, L=L,
                                             translation=translation)
            w2 = meshworld.apply_mesh_linear(v2, mesh_origin=mesh.origin, L=L,
                                             translation=translation)
            skin = skins.get(material_index)
            if skin is None:
                tex_index = -1
                base, axis_u, axis_v = (0.0, 0.0, 0.0), (1.0, 0.0, 0.0), (0.0, 1.0, 0.0)
                pan = (0.0, 0.0)
            else:
                tw, th, rgb, b_masked, mask = skin
                tex_index = textures.index_for_decoded(actor.cls, mesh_ref, material_index,
                                                       tw, th, rgb, b_masked, mask,
                                                       actor_override=actor_skin_override)
                u0 = (uv0[0] * tw / 256.0, uv0[1] * th / 256.0)
                u1 = (uv1[0] * tw / 256.0, uv1[1] * th / 256.0)
                u2 = (uv2[0] * tw / 256.0, uv2[1] * th / 256.0)
                frame = meshworld.solve_uv_frame(w0, w1, w2, u0, u1, u2)
                if frame is None:
                    continue          # degenerate triangle, skip (matches render.rs's own skip)
                base, axis_u, axis_v, pan = frame
            masked = bool(poly_flags & PF_MASKED) or textures.is_bmasked(tex_index)
            verts_flat = [c for v in (w0, w1, w2)
                         for c in (float(v[0]), float(v[1]), float(v[2]))]
            out.append(((verts_flat, list(base), list(axis_u), list(axis_v), list(pan),
                        tex_index, masked, poly_flags), (actor.name, None)))
    return out


def resolve_mesh_scene_polys(level, index, search_files, class_defaults, *,
                             hidden_prop: str = "bhiddened"
                             ) -> tuple[list[tuple], list[tuple[str, None]], list[tuple]]:
    """`uedcli serve`'s Load-owned, build-state-independent mesh-actor resolution entry point
    (mirrors `resolve_actor_sprites`'s existing independence for point-actor icons): every DT_Mesh
    actor's world-space triangles + a PRIVATE texture table, from `level` alone -- no CSG/BSP
    dependency, no `in_solid` gate (see `resolve_mesh_actor_polys`'s docstring for why). Returns
    `(polys, owners, texture_table)`: `polys`/`owners` are `resolve_mesh_actor_polys`'s own pairs,
    unzipped; `texture_table` is the private `_TextureTable.table` this call built, for the caller
    to publish as its own atlas slot (`uedcli/serve/app.py`'s `/atlas` route) alongside
    `geometry.texture_table` and `trunk.sprite_table` — never folded into either.

    Returns `([], [], [])` when `search_files` is empty (no configured search path, so no
    `TextureResolver` is possible) -- matches `resolve_actor_sprites`'s own degrade disposition for
    the same condition, never a crash. `hidden_prop` defaults to `"bhiddened"` (EDITOR visibility —
    the GUI hides `bHiddenEd` actors and ignores `bHidden`, owner ruling 2026-09-14), matching every
    other GUI-facing resolver in this codebase (`build_scene`'s own `visibility="editor"` mode).
    `class_defaults` (a `ClassDefaults`) is REQUIRED -- the caller's own shared memo, threaded down
    to `resolve_mesh_actor_polys` so each distinct class/skin resolves once per call, not once per
    actor referencing it (board `load-resolves-mesh-class-defaults-and-texture`); required rather
    than optional so a future caller can't silently forget to pass it."""
    if not search_files:
        return [], [], []
    textures = _TextureTable(TextureResolver(search_files, class_index=index))
    resolved = resolve_mesh_actor_polys(level, index, search_files, hidden_prop=hidden_prop,
                                        textures=textures, class_defaults=class_defaults)
    polys = [poly for poly, _owner in resolved]
    owners = [owner for _poly, owner in resolved]
    return polys, owners, textures.table


# --------------------------------------------------------------------- textures

class _TextureTable:
    """Distinct texture refs → table indices. A procedural texture (`no-mip-data` — a real
    texture the engine generates at runtime, e.g. a FireTexture/WaterTexture surface like a
    water pool) substitutes `utexture.PROCEDURAL_RED`, matching mesh skins (see
    `meshrender.resolve_skins`) — the same visible "not-rendered-yet" marker either way. Any
    OTHER unresolvable ref still raises `NativePreviewError` (no placeholder, no partial image
    — spec §4.5)."""

    def __init__(self, resolver: TextureResolver) -> None:
        self._resolver = resolver
        self.table: list[tuple[int, int, bytes, bytes]] = []
        self.bmasked: list[bool] = []                    # per-index: is the texture itself bMasked
        self._by_ref: dict[str, int] = {}
        self._by_decoded: dict = {}

    def is_bmasked(self, idx: int) -> bool:
        """Does the texture at table `idx` carry `bMasked` (masks index-0 regardless of the surface
        `PF_Masked` flag)? `-1`/out-of-range (no texture) → False."""
        return 0 <= idx < len(self.bmasked) and self.bmasked[idx]

    def index_for(self, ref: str | None) -> int:
        if not ref:
            return -1                                    # no texture set → flat grey
        key = ref.casefold()
        if key in self._by_ref:
            return self._by_ref[key]
        got = resolve_or_procedural_red(self._resolver, ref)
        if isinstance(got, TextureError):
            raise NativePreviewError(
                f"texture {ref!r} did not decode [{got.case}]: {got.detail}")
        idx = len(self.table)
        self.table.append((got.width, got.height, got.rgb, got.mask))
        self.bmasked.append(bool(got.b_masked))
        self._by_ref[key] = idx
        return idx

    def index_for_decoded(self, class_fqcn: str, mesh_ref: tuple[str, str], material_index: int,
                          w: int, h: int, rgb: bytes, b_masked: bool, mask: bytes, *,
                          actor_override: tuple = ()) -> int:
        """Register an already-decoded texture (a mesh skin `resolve_skins` resolved) and return
        its table index -- deduped by (class_fqcn, mesh_ref, material_index, actor_override), NOT
        by which ACTOR triggered the resolve, so many placed instances of the same decoration/crate
        STILL share one table entry -- unless one of them overrides its own skin.

        The CLASS is part of the key because `resolve_skins` is class-dependent: a class's
        `MultiSkins`/`Skin` defaults OVERRIDE the mesh's own textures, so two classes sharing one
        mesh resolve to different skins. Measured over the committed UED22 corpus: of the 325 mesh
        assets stock DT_Mesh classes reference, 34 carry more than one distinct class skin set, and
        the body mesh `DeusExCharacters.GM_Trench` alone carries 16. Keying on the mesh alone made
        whichever class resolved second silently render the first one's skin.

        `actor_override` is the SAME failure mode reopening one layer up, now that a placed actor's
        own `MultiSkins`/`Skin` can also override its class's (board
        `per-actor-skins-override-in-native-mesh-render`): a hashable fingerprint of the actor's own
        skin-relevant stored props (`sorted((prop, idx), text)` pairs restricted to
        `multiskins`/`skin` keys), `()` when the actor states none. An actor with no override keeps
        today's exact 3-part key and cache-hit rate; only an actor that actually states an override
        gets its own table slot instead of silently inheriting another actor's.
        `mesh_ref` is `(package_stem, mesh_name)` -- the mesh ASSET identity, so two same-named
        meshes in different packages stay distinct.

        `b_masked` is the skin texture's own `bMasked` flag (`resolve_skins` carries it), so
        `is_bmasked` reports a mesh skin exactly as it reports a surface texture. `mask` is the
        real per-texel mask `resolve_skins` decoded (`DecodedTexture.mask`, `w*h` bytes,
        1=opaque/0=transparent) -- matching `index_for`'s own `got.mask`, not a synthesized
        all-opaque stand-in, so the rasterizer's `masked && mask[texel] == 0` alpha test actually
        cuts a masked mesh skin."""
        cache_key = (class_fqcn, mesh_ref, material_index, actor_override)
        if cache_key in self._by_decoded:
            return self._by_decoded[cache_key]
        idx = len(self.table)
        self.table.append((w, h, rgb, mask))
        self.bmasked.append(bool(b_masked))
        self._by_decoded[cache_key] = idx
        return idx


def _bare_sprite_texture_ref(text: str | None) -> str | None:
    """`Texture'Package.Group.Name'` -> the bare ref a `TextureResolver` expects; a plain
    `Package.Name` passes through; `None`/`"None"`/empty -> None. Same normalization as
    `cli/rendering.py::_strip_object_ref` for a DIFFERENT call site (`resolve_actor_sprites` below) —
    duplicated rather than imported, since that module is a command-layer owner this one must not
    import from."""
    if not text:
        return None
    m = re.search(r"'([^']*)'", text)
    ref = m.group(1) if m else text.strip()
    return ref or None if ref and ref != "None" else None


def _sprite_draw_scale(text) -> float:
    try:
        return float(str(text).strip())
    except (TypeError, ValueError):
        return 1.0


def resolve_actor_sprites(level, search_files, class_defaults
                          ) -> tuple[list[tuple[int, int, bytes, bytes]], dict[str, tuple[int, float, float]]]:
    """Point actors' `DT_Sprite` billboard textures for `uedcli serve`'s 3D marker — the SAME
    instance-else-class-default field resolution and `preview.sprite_footprint` math as
    `cli/rendering.py::_resolve_point_render` (a NEW call site: a 3D GUI marker, not the 2D
    actor-diagram schematic), reusing its LOGIC, not its code (that function stays CLI-diagnostic,
    with stderr notes this call site has no use for). `class_defaults` is the caller's shared
    `classdefaults.ClassDefaults` memo (the same instance `build_scene` takes) — resolving a fresh
    schema chain per ACTOR instead of once per distinct CLASS was an O(actors) cost on every request,
    even a full CSG-cache hit.

    Returns `(extra_table, actor_sprites)`: `extra_table` is a fresh `(w, h, rgb, mask)` list — same
    shape as `_TextureTable.table`'s own rows — for the caller to append onto `build_scene`'s
    `texture_table` so a resolved sprite lands in the SAME atlas (`/api/level/{level}/atlas`) as
    every world/mesh texture; `actor_sprites` maps a non-brush actor's name to `(local_tex_index,
    width_uu, height_uu)`, where `local_tex_index` indexes `extra_table` — the caller adds
    `len(texture_table)` to get the real, atlas-wide index. An actor is absent from `actor_sprites`
    whenever `_resolve_point_render` would have degraded to a plain marker: `DrawType` isn't
    `DT_Sprite`, no `Texture`, no search path configured, decode failure, or a zero footprint
    (`DrawScale` 0 / zero-size texture)."""
    resolver = TextureResolver(search_files) if search_files else None
    table: list[tuple[int, int, bytes, bytes]] = []
    by_ref: dict[str, int] = {}
    actor_sprites: dict[str, tuple[int, float, float]] = {}
    if resolver is None:
        return table, actor_sprites
    for actor in level.actors.values():
        if actor.brush is not None:
            continue
        instance = {k.casefold(): v for k, v in actor.props}
        defaults = class_defaults.for_class(actor.cls).defaults

        def field(name: str, *, _instance=instance, _defaults=defaults):
            low = name.casefold()
            return _instance[low] if low in _instance else _defaults.get((low, 0))

        if (field("DrawType") or "DT_Sprite").strip() != "DT_Sprite":
            continue
        bare = _bare_sprite_texture_ref(field("Texture"))
        if bare is None:
            continue
        key = bare.casefold()
        if key in by_ref:
            idx = by_ref[key]
        else:
            got = resolver.resolve(bare)
            if isinstance(got, TextureError):
                continue
            idx = len(table)
            table.append((got.width, got.height, got.rgb, got.mask))
            by_ref[key] = idx
        w, h, _rgb, _mask = table[idx]
        fw, fh = sprite_footprint(_sprite_draw_scale(field("DrawScale")), w, h)
        if fw <= 0 or fh <= 0:
            continue
        actor_sprites[actor.name] = (idx, fw, fh)
    return table, actor_sprites


# --------------------------------------------------------------------- camera

def camera_basis(pitch_deg: float, yaw_deg: float):
    """(forward, right, up) world basis for an FRotator pose, via the GMath-verified
    `euler_to_matrix_uu` (degrees quantize to the stored integer field first — exactly what
    the game renders). This is the SINGLE source of the camera convention: Rust receives
    the basis and never converts angles (spec §5, plan refinement 3)."""
    R = euler_to_matrix_uu(deg_to_uu(pitch_deg), deg_to_uu(yaw_deg), 0)
    return (tuple(matvec(R, (1.0, 0.0, 0.0))),           # forward (UE1 +X)
            tuple(matvec(R, (0.0, 1.0, 0.0))),           # right (+Y)
            tuple(matvec(R, (0.0, 0.0, 1.0))))           # up (+Z)


def sky_camera_basis(pitch_deg: float, yaw_deg: float,
                     sky_pitch_uu: int, sky_yaw_uu: int, sky_roll_uu: int):
    """(forward, right, up) world basis for the sky sub-render's camera: the viewer's own
    rotation divided by the sky actor's own rotation (`FCoords::operator/=(FRotator)` in the real
    engine). NOT `matmul(viewer_r, inverse(sky_r))` — that guess has both the operand order and
    the inverse placement backwards; see this task's derivation comment in the plan/spec for why
    it's `matmul(transpose(inverse(sky_r)), viewer_r)`, which reduces to `sky_r · viewer_r` for an
    orthonormal `sky_r`. Camera POSITION is handled separately by the caller (the sky actor's own
    `Location`, with no dependency on the viewer's position at all)."""
    from .rotation import euler_to_matrix_uu, matmul, inverse, transpose, matvec, deg_to_uu
    viewer_r = euler_to_matrix_uu(deg_to_uu(pitch_deg), deg_to_uu(yaw_deg), 0)
    sky_r = euler_to_matrix_uu(sky_pitch_uu, sky_yaw_uu, sky_roll_uu)
    composed = matmul(transpose(inverse(sky_r)), viewer_r)
    return (tuple(matvec(composed, (1.0, 0.0, 0.0))),
            tuple(matvec(composed, (0.0, 1.0, 0.0))),
            tuple(matvec(composed, (0.0, 0.0, 1.0))))


# --------------------------------------------------------------------- aim points

def actor_aim_point(level, name: str) -> tuple[float, float, float]:
    """The point `look:@name`/`orbit:@name` aims at: a brush actor's world-AABB centre (its
    `Location` is the pivot — the wrong target), a point actor's `Location`. Raises
    NativePreviewError naming an unknown actor (case-insensitive resolution)."""
    from .query import resolve_actor_name
    from .writes import actor_bounds
    try:
        canon = resolve_actor_name(level, name)
    except KeyError:
        raise NativePreviewError(f"actor not found: {name}") from None
    actor = level.actors[canon]
    if actor.brush is not None:
        lo, hi = actor_bounds(actor)
        return tuple((float(lo[i]) + float(hi[i])) / 2.0 for i in range(3))
    loc = actor.location or (0, 0, 0)
    return tuple(float(c) for c in loc)


# --------------------------------------------------------------------- sky actor

SKY_ZONE_INFO_BASE = "Engine.SkyZoneInfo"


def _is_sky_zone_actor_class(index, cls: str) -> bool:
    """`Engine.SkyZoneInfo` ancestry check, decided by the resolved class chain, never by how the
    class is SPELLED -- same shape as `native.materialize._is_zone_actor_class` (ancestry-based,
    not a name-suffix guess, with the same bare-class-name and undecidable-chain handling).

    It answers or it raises (`ClassRefError` -> a clean exit 2): a chain that truncates before the
    `Core.Object` root means a package is off the search path, and answering `False` there would
    silently drop a real sky actor."""
    if not cls:
        return False
    if "." not in cls:
        candidates = sorted(index.bare_to_fqcn().get(cls.casefold(), ()))
        if not candidates:
            raise ClassRefError(
                f"cannot decide whether the bare class {cls} is a SkyZoneInfo: no class of that "
                f"name exists in any package on the composed search path")
        verdicts = {_is_sky_zone_actor_class(index, fqcn) for fqcn in candidates}
        if len(verdicts) > 1:
            raise ClassRefError(
                f"cannot decide whether the bare class {cls} is a SkyZoneInfo: it resolves to "
                f"{', '.join(candidates)}, and they disagree -- qualify the actor's class")
        return verdicts.pop()
    chain = [a.casefold() for a in index.ancestry(cls)]
    if SKY_ZONE_INFO_BASE.casefold() in chain:
        return True
    if chain[-1] != CORE_OBJECT.casefold():
        raise ClassRefError(
            f"cannot decide whether class {cls} is a SkyZoneInfo: its ancestor chain stops at "
            f"{chain[-1]} instead of the {CORE_OBJECT} root, so a package on the chain is missing "
            f"from the composed search path (check the project `paths` and the games config)")
    return False


def find_sky_actor(level, index):
    """The level's sky actor (an `Engine.SkyZoneInfo` or subclass), or `None` if the level has
    none -- a port of `Engine.u`'s `ZoneInfo::LinkToSkybox()` OUTCOME (see
    `dev/docs/unrealed/rendering.md`'s `PF_FakeBackdrop` section): the real engine assigns
    `SkyZone` on every match, so the WINNER is the FIRST actor in `level.order` (the trunk order
    this codebase already uses for zone-actor resolution -- NOT `level.actors.values()`, an
    alphabetical dict that has a NAMED regression for exactly this class of bug,
    `test_native_roundtrip.py`'s NYC_Bar N=70 case) whose `bHighDetail` matches, else the FIRST
    `SkyZoneInfo` found if none states `bHighDetail=True`. There is at most one sky actor for a
    whole level (not per-zone)."""
    from .uprops import resolve_class_defaults

    best = None
    for name in level.order:
        a = level.actors[name]
        if not _is_sky_zone_actor_class(index, (a.cls or "").strip()):
            continue
        instance = {k.casefold(): v for k, v in a.props}
        defaults = resolve_class_defaults(a.cls, resolver=index.resolver())
        high_detail = instance.get("bhighdetail", defaults.get(("bhighdetail", 0)))
        if str(high_detail or "False").strip() == "True":
            return a          # a bHighDetail match wins outright, first one in trunk order
        if best is None:
            best = a           # remember the first SkyZoneInfo as the no-bHighDetail fallback
    return best


# --------------------------------------------------------------------- scene cache

def _scene_hashes(level, light_names: set[str]) -> tuple[str, str]:
    """Split `normalize.canonical_level_hash`'s construction (content hash + order hash, combined)
    into a GEOMETRY hash (every actor `build_scene`'s CSG/mesh/texture stages read) and a LIGHT
    hash (only the actors `gather_lights` accepts, given here as `light_names` so this can't
    disagree with what the bake actually treats as a light). Both fold in the FULL `level.order`,
    not just the restricted subset's relative order — reordering a light actor relative to a brush
    can't move CSG evaluation order (`_brush_inputs` filters to brush actors before reading it), so
    this is deliberately over-invalidating rather than reasoning that out: same "err strict, never
    serve stale" posture as `canonical_level_hash` itself (`build_cache` costs an extra rebuild on
    a miss, never a wrong scene).

    A BRUSH actor is excluded from `light_names` here regardless of what `gather_lights` says about
    it — `gather_lights` has no class check ("any class can be a light", its own docstring) and
    reads only stated `LightType`/`bStatic`/`bNoDelete` props, so a world-CSG brush that happens to
    also state those props would otherwise drop its own geometry out of `geom_hash` entirely,
    letting a real edit to it (a moved vertex, a changed `CsgOper`) go undetected. `_brush_inputs`
    puts every non-mover, non-builder-brush actor with `actor.brush is not None` into world CSG
    without ever checking light-ness, so this project's own CSG-participation test is the one that
    must gate the hash split, not `gather_lights`'."""
    import hashlib

    from .normalize import canonical_actor_t3d

    order_hash = hashlib.sha256("\n".join(level.order).encode("utf-8")).hexdigest()

    def _hash(names) -> str:
        content = hashlib.sha256(
            "\n".join(canonical_actor_t3d(level.actors[n]) for n in sorted(names))
            .encode("utf-8")).hexdigest()
        return hashlib.sha256(f"{content}:{order_hash}".encode("utf-8")).hexdigest()[:12]

    all_names = set(level.order or level.actors)
    light_names = {n for n in light_names if level.actors[n].brush is None}
    return _hash(all_names - light_names), _hash(light_names & all_names)


# --------------------------------------------------------------------- orchestration

def build_scene(level, search_files, index, *, defaults, project=None,
                level_name=None, visibility: Literal["gameplay", "editor"] = "gameplay",
                include_meshes: bool = True, include_movers: bool = True
                ) -> tuple[list, list, list, str | None, str | None]:
    """Trunk → (render polys, texture table, per-poly owner names, geom_hash, light_hash): CSG build
    + node-poly extraction + source-poly join + Python UV frames + mover extra_polys + native
    texture decode + world-surf lighting (board `bake-lighting-into-level-photo-native`). Raises
    NativePreviewError on every named RENDER failure path (spec §7). `index` is a
    `classindex.ClassIndex`: movers are excluded from world CSG and rendered separately, and
    mover-ness is decided schema-aware by `movers.is_mover` against the game's class hierarchy —
    an unresolvable class therefore raises `classindex.ClassRefError` (naming the class) straight
    through this function, rather than a NativePreviewError; dispatch's top-level guard turns it
    into the same clean exit 2. `defaults` is a `classdefaults.ClassDefaults`, needed to read light
    properties (their class defaults) —
    world BSP surfaces are lit; mesh/mover actors are not (a separate, un-RE'd mechanism, board
    item `mesh-mover-per-vertex-lighting-in-level-photo`).

    The third return value, `actor_names_by_poly`, is a list parallel to the render polys giving
    each poly's owning `(actor name, i_brush_poly)` — `i_brush_poly` is the poly's own index into
    the owning actor's `brush.polys` (`BRUSH:IDX` addressing, `uedcli/surface.py`), None when the
    owner has no single source poly (a mesh actor, no `.brush.polys` at all); the whole pair is None
    for a poly joined to no source actor — an out-of-range CSG join, §4.4). It rides ALONGSIDE the
    render-poly tuple rather than inside it: `render_frame` (the Rust FFI boundary, `render_shots`
    below) takes the render polys verbatim and has no use for actor identity, so extending its tuple
    shape would be a pure liability there. `uedcli serve`'s `scene.py::build_scene_payload` is the
    one consumer that needs it (real per-poly ownership for click-to-select, replacing per-actor AABB
    testing) — `i_brush_poly` lets it group a solved BSP surface's own fragments back to the ONE
    authored polygon they came from, so a click anywhere on it selects the whole authored face
    instead of one fragment (owner bug report, "brush poly selection is off").

    The fourth/fifth return values, `geom_hash`/`light_hash`, are the SAME identity strings this
    function already computes internally (below) to key its own on-disk `build_cache` entries —
    returned so a caller needing them (`uedcli serve`'s `_build_and_publish_geometry`) doesn't have
    to recompute them itself. Both are `None` whenever `project`/`level_name` aren't both given
    (the same gate that skips caching entirely).

    `project`/`level_name` are the `build_cache` identity (owner ruling 2026-09-13, board `native-
    photo-scene-cache`): given both, an unchanged level reuses its fully-lit scene outright, and a
    level whose only change is to its light actors reuses the CSG solve + texture decode and reruns
    only the (cheap) lighting bake. Neither given (every direct test call in this codebase) → always
    a fresh, uncached build — no CLI path calls this without a project.

    `visibility` picks which mesh-actor hidden flag `_mesh_actor_polys` checks (owner ruling
    2026-09-14): `"gameplay"` (the default — `render_shots`/`level photo --native`'s UNCHANGED
    behavior) reads `bHidden`, matching what the player sees; `"editor"` (`uedcli serve`'s GUI) reads
    `bHiddenEd` instead and ignores `bHidden` entirely. It changes ONLY the mesh-actor loop below —
    THIS function has no hidden-actor exclusion of its own for brush/CSG geometry (investigated, not
    invented here). That exclusion lives in `uedcli/serve/scene.py::build_scene_payload`, POST-solve,
    via this function's `owners` return: it drops a hidden `CSG_Add` brush's own rendered surfaces
    (safe — they're that brush's own solid contribution) but keeps a hidden `CSG_Subtract`'s (its own
    surfaces are the walls of the volume it carved; dropping them would open a hole nothing else
    fills — see that module's docstring), and it filters brush/mesh actor METADATA out of its own
    actor list the same way. A Mover buckets with `CSG_Add` there too (it carries no `CsgOper` prop
    at all, so that module's default-missing-to-CSG_Add lookup applies) — correctly, since a Mover's
    own surfaces are its own solid contribution, never a wall some other actor's geometry depends on.
    Bare point actors carry no geometry for `build_scene` to exclude in the first place. Folded into
    `geom_hash` below (not just passed to
    `_mesh_actor_polys`): the SAME actor content builds a DIFFERENT `polys_no_light` depending on
    this mode, so the on-disk geometry/scene cache must key on it too, or `level photo --native` and
    `uedcli serve` would silently hand each other's cached, wrongly-filtered scene back for the same
    level.

    `include_meshes=False` (`uedcli serve`'s ONLY use of this flag, board `mesh-actors-should-render-
    independent-of-geometry-build`, "Option A") skips the mesh-actor loop entirely — the GUI resolves
    mesh-actor triangles itself, independently of this CSG-solved pipeline, via
    `resolve_mesh_scene_polys` (`uedcli/serve/scene.py`), so a mesh actor renders the SAME way before
    and after a Rebuild. `level photo --native` never passes this (default `True`, unchanged
    behavior) — meshes there are genuinely part of the one-shot photo build. Folded into `geom_hash`
    below alongside `visibility`, for the same reason: the same actor content builds a DIFFERENT
    `polys_no_light` depending on this flag too.

    `include_movers=False` (`uedcli serve`'s ONLY use, board `mover-triangles-not-build-state-
    independent`, mirroring `include_meshes`) skips the mover loop entirely — the GUI resolves Mover
    triangles itself via `resolve_mover_scene_polys` (`uedcli/serve/scene.py`), independently of this
    CSG-solved pipeline, so a Mover renders the SAME way before and after a Rebuild. `level photo
    --native` never passes this (default `True`, unchanged behavior). Folded into `geom_hash` below
    too, for the same reason as `include_meshes`."""
    try:
        from uedcli.native_ext import import_native
        uedcli_native = import_native()
    except ImportError:
        raise NativePreviewError(
            "the uedcli_native extension is not built — `level photo --native` needs it "
            "(build with `maturin develop`, or run bin/test once)") from None

    # World-surf lighting inputs, gathered up front so the split-hash below can name which actors
    # are lights (`level materialize` uses `bake_lighting` alone; `level photo --native`
    # additionally needs `bake_radiance`'s lit RGB buffer, since its rasterizer has no render-time
    # light evaluation of its own).
    from .native.materialize import (_model_point_region, gather_light_colors,
                                      gather_lights)
    lights = gather_lights(level, defaults=defaults)
    lights_ffi = [(loc, radius, special) for _n, loc, radius, special in lights]
    colors_ffi = gather_light_colors(level, lights, defaults=defaults)

    cache = project is not None and level_name is not None
    geom_hash = light_hash = None
    if cache:
        geom_hash, light_hash = _scene_hashes(level, {n for n, *_ in lights})
        # `visibility`/`include_meshes`/`include_movers` change `polys_no_light`/
        # `actor_names_by_poly` for THE SAME actor content (see docstring) — tag all three onto
        # geom_hash so `render_shots` and `build_scene_payload` never share a cache entry built
        # under the other's rule.
        geom_hash += (("e" if visibility == "editor" else "g")
                     + ("" if include_meshes else "x") + ("" if include_movers else "m"))
        cached_scene = build_cache.load_scene(project, level_name, geom_hash, light_hash)
        if cached_scene is not None:
            return (*cached_scene, geom_hash, light_hash)

    geo = build_cache.load_geometry(project, level_name, geom_hash) if cache else None

    built = None
    if geo is not None:
        model_body, portals, polys_no_light, i_surf_by_poly, actor_names_by_poly, texture_table = geo
        try:
            # `leaf_portals` is the frozen portal graph `assign_leaves_and_zones` computed during
            # THIS geometry's original build — `serialize_model`'s on-disk format doesn't carry it,
            # so it rides alongside `model_body` in the cache and is restored here. Without it,
            # `bake_lighting`'s permeating-light pass falls back to a fresh recompute over the
            # reloaded model's CURRENT points — the exact stale-portal divergence fixed in
            # `dev/docs/spikes/2026-09-13-portal-graph-frozen-before-optgeom/` (board items
            # `island-n-332-...`/`unatco-n-226-...`/`wanchai-n58-...`). Reloading without it would
            # silently reintroduce that bug on every geometry-cache hit.
            built = uedcli_native.load_model(model_body, leaf_portals=portals)
        except uedcli_native.BuildError:
            built = None       # a stale/incompatible cache entry (e.g. the native model's own
                                # serialized-body layout changed since this entry was written — an
                                # internal, actively-developed format, unlike the frozen on-disk UE1
                                # format `--game`'s cache reuses) is a MISS, never a crash: same
                                # posture as `schema_cache.py`'s own corrupt/version-mismatched-entry
                                # handling. Falls through to a fresh build below.
    if built is None:
        brushes, join = _brush_inputs(level, index)
        if not brushes:
            raise NativePreviewError("nothing to render: the trunk has no CSG brush actors")
        try:
            # FAITHFUL incremental `bspBrushCSG` core, same as `solve_world_surfaces` — it
            # reproduces the editor's surviving-surface set (Wanchai ratio ~1.01), where the coarse
            # `build_geometry` convex point-in-solid dropped ~69% of surfaces (board `native-
            # preview-drops-large-geometry-on-full`). Same `BrushTuple` input and
            # `serialize_model`/`_node_polys` join path.
            built = uedcli_native.build_geometry_bspcsg(brushes)
            # Serialized PRE-lighting: `_node_polys` reads only geometry (nodes/surfs/points), so
            # this body is a valid `load_model` cache seed for a later lighting-only rerun, and
            # reordering the serialize ahead of `bake_lighting` changes nothing about this build.
            # `leaf_portals` must travel WITH it (see the cache-hit branch above) — it's frozen by
            # `build_geometry_bspcsg` itself (`bspcsg.rs::zone_pass`), not by lighting.
            model_body = uedcli_native.serialize_model(built)
            portals = uedcli_native.leaf_portals(built)
        except uedcli_native.BuildError as ex:
            raise NativePreviewError(f"native CSG build failed: {ex}") from ex
        from .native.umodel import parse_model_body
        model = parse_model_body(model_body, 0, len(model_body))

        # class_index=index widens the resolver from the exact `Texture` class to every
        # `Engine.Texture` descendant (FireTexture, WaterTexture, ...) -- without it, ANY texture
        # subclass used on a world surface is invisible to lookup entirely (`unknown-texture`, not
        # even reaching decode) rather than resolving and being recognised as procedural.
        textures = _TextureTable(TextureResolver(search_files, class_index=index))
        polys_no_light: list[tuple] = []
        i_surf_by_poly: list[int | None] = []
        # `(actor.name, i_brush_poly)` -- `i_brush_poly` is the poly's own index into the owning
        # actor's `brush.polys` (`BRUSH:IDX` addressing, `uedcli/surface.py`), None for an owned poly
        # with no single source poly (a mesh actor, which has no `.brush.polys` at all). `None`
        # (the whole pair) for a poly with no owning actor -- an out-of-range CSG join (§4.4).
        actor_names_by_poly: list[tuple[str, int | None] | None] = []

        def add_poly(world_verts, actor, poly, surf_flags=None, i_surf=None, i_brush_poly=None):
            # `surf_flags` (a CSG-solved surf's OWN `poly_flags`, always real even when the join
            # below is out of range) takes priority; a mover has no surf, so it falls back to
            # deriving the merged flags itself from its authored poly + actor PolyFlags. `poly` can
            # be None (the out-of-range-join grey filler) independently of `actor` being None, so
            # the poly half of the fallback must not assume `poly is not None` just because `actor
            # is not None`.
            if surf_flags is not None:
                flags = surf_flags
            else:
                # `poly.flags`/`poly_flags_int` decode `PolyFlags` as a SIGNED i32 (mapimport.py's
                # `decode_fpoly`, matched to the write side) — a real DWORD with the top bit(s) set
                # (an original-format Unreal map, e.g. `PF_Occlude`) comes out negative. Mask to
                # unsigned 32-bit here, same as `brush_marshal.py`'s `poly_flags_flat`:
                # `render_frame`'s Rust `poly_flags` field is `u32`, and an unmasked negative value
                # is an `OverflowError` crossing the FFI.
                flags = (((poly.flags or 0) if poly is not None else 0) | (
                    poly_flags_int(dict(actor.props)) if actor else 0)) & 0xFFFFFFFF
            if flags & PF_INVISIBLE:
                return                                       # dropped Python-side (spec §5)
            if actor is not None and poly is not None:
                try:
                    base_w, tu, tv, pan = world_uv_frame(actor, poly)
                except DegenerateTransformError as e:    # degenerate-scale mover/brush → exit 2 (spec §7)
                    raise NativePreviewError(str(e)) from e
                tex_index = textures.index_for(poly.texture)
            else:
                base_w, tu, tv, pan = (0.0, 0.0, 0.0), (1.0, 0.0, 0.0), (0.0, 1.0, 0.0), (0.0, 0.0)
                tex_index = -1                               # unknown owner → flat grey
            verts_flat = [c for v in world_verts for c in
                          (float(v[0]), float(v[1]), float(v[2]))]
            # A face masks index-0 as see-through iff the surface `PF_Masked` flag is set OR the
            # texture itself is `bMasked` — the engine ORs a texture's PolyFlags onto every surface
            # it's applied to, so a masked texture masks with NO surface flag (owner-confirmed,
            # `unrealed/quirks.md` "a face draws index 0 as a hole iff poly.flags & PF_Masked OR its
            # texture carries bMasked"). Matches `cli/rendering.py`'s `--mode` gate.
            masked = bool(flags & PF_MASKED) or textures.is_bmasked(tex_index)
            polys_no_light.append((verts_flat, list(base_w), list(tu), list(tv), list(pan),
                                   tex_index, masked, flags))
            i_surf_by_poly.append(i_surf)
            actor_names_by_poly.append((actor.name, i_brush_poly) if actor is not None else None)

        for world_verts, i_actor, i_brush_poly, poly_flags, i_surf in _node_polys(model):
            if 0 <= i_actor < len(join):
                name, source_polys = join[i_actor]
                if 0 <= i_brush_poly < len(source_polys):
                    add_poly(world_verts, level.actors[name], source_polys[i_brush_poly],
                             surf_flags=poly_flags, i_surf=i_surf, i_brush_poly=i_brush_poly)
                else:
                    add_poly(world_verts, None, None, surf_flags=poly_flags,
                             i_surf=i_surf)                   # out-of-range poly (§4.4)
            else:
                add_poly(world_verts, None, None, surf_flags=poly_flags,
                         i_surf=i_surf)                       # out-of-range owner (§4.4)

        if include_movers:
            for poly_tuple, owner in resolve_mover_actor_polys(level, index, textures=textures):
                verts_flat, base_w, tu, tv, pan, tex_index, masked, flags = poly_tuple
                polys_no_light.append((verts_flat, base_w, tu, tv, pan, tex_index, masked, flags))
                i_surf_by_poly.append(None)   # movers: no lightmap (out of scope, board
                                              # `mesh-mover-per-vertex-lighting-in-level-photo`)
                actor_names_by_poly.append(owner)

        hidden_prop = "bhiddened" if visibility == "editor" else "bhidden"
        if include_meshes:
            def _in_solid(actor) -> bool:
                # A mesh actor whose Location sits in SOLID space (a leaf carved out of nothing) is
                # not drawn — the engine never renders an actor in a solid leaf (board `meshes-in-
                # solid-space-render-in-photo-and-gui`). `_model_point_region`'s BSP descent returns
                # i_leaf -1 in solid space; a carved-open leaf always has i_leaf >= 0.
                loc = tuple(float(c) for c in (actor.location or (0.0, 0.0, 0.0)))
                return _model_point_region(model, loc)[0] < 0

            for poly_tuple, owner in resolve_mesh_actor_polys(
                    level, index, search_files, hidden_prop=hidden_prop, textures=textures,
                    in_solid=_in_solid):
                verts_flat, base, axis_u, axis_v, pan, tex_index, masked, poly_flags = poly_tuple
                polys_no_light.append((verts_flat, base, axis_u, axis_v, pan, tex_index, masked,
                                       poly_flags))
                i_surf_by_poly.append(None)   # mesh actors: no lightmap (out of scope, board
                                              # `mesh-mover-per-vertex-lighting-in-level-photo`)
                actor_names_by_poly.append(owner)   # no `.brush.polys` to index into

        texture_table = textures.table
        if cache:
            build_cache.store_geometry(project, level_name, geom_hash,
                                         (model_body, portals, polys_no_light, i_surf_by_poly,
                                          actor_names_by_poly, texture_table))

    try:
        uedcli_native.bake_lighting(built, lights_ffi)
        radiance_by_surf = {}
        for surf_index, origin, u_step, v_step, u_size, v_size, rgb in \
                uedcli_native.bake_radiance(built, lights_ffi, colors_ffi):
            radiance_by_surf[surf_index] = (origin, u_step, v_step, u_size, v_size, rgb)
    except uedcli_native.BuildError as ex:
        raise NativePreviewError(f"native lighting bake failed: {ex}") from ex

    polys = [
        (*poly, radiance_by_surf.get(i_surf) if i_surf is not None else None)
        for poly, i_surf in zip(polys_no_light, i_surf_by_poly)
    ]

    if cache:
        build_cache.store_scene(project, level_name, geom_hash, light_hash,
                                  (polys, texture_table, actor_names_by_poly))

    return polys, texture_table, actor_names_by_poly, geom_hash, light_hash


@dataclass(frozen=True)
class SolvedSurface:
    """One surviving world-space surface from the CSG solve. `actor`/`poly_index` identify the
    SOURCE brush poly (for texture/UV frame and the per-poly index decal), or both are None for a
    BSP node that joined to no source poly (renders flat grey). `world_verts` is the fragment's
    ring, already in world space — NO local→world transform is applied again downstream.
    `poly_flags` is the surf's OWN merged actor+poly `PolyFlags` (real even when actor/poly_index
    are None — a BSP node always has a surf) — the `actor diagram --mode fullbright` backface
    cull's `PF_TwoSided`/`PF_Portal` exemption reads this, single-sourced with `level photo
    --native`'s own cull."""
    actor: object | None
    poly_index: int | None
    world_verts: list
    poly_flags: int


@dataclass(frozen=True)
class SolvedWorld:
    """The CSG solve output `actor diagram --mode fullbright` draws: the surviving world surfaces
    plus the movers (excluded from world CSG, drawn as a separate overlay)."""
    world_surfaces: list  # list[SolvedSurface]
    mover_polys: list     # list[(world_verts, actor, poly)]


def solve_world_surfaces(actors, index, search_files=None) -> SolvedWorld:
    """Run the native CSG solve over an ad-hoc actor list (in the order given — the actor-set order
    IS the CSG evaluation order) through the FAITHFUL `build_geometry_bspcsg` core, and return the
    surviving world surfaces + the movers. This is the `actor diagram --mode fullbright` engine: the
    world is solved in isolation from a SOLID world, so an add not inside subtracted space leaves no
    surface. `index` is a `classindex.ClassIndex`; movers are excluded from world CSG (raising
    `classindex.ClassRefError` straight through on an unresolvable class). Raises `NativePreviewError`
    if the native extension is not built."""
    try:
        from uedcli.native_ext import import_native
        uedcli_native = import_native()
    except ImportError:
        raise NativePreviewError(
            "the uedcli_native extension is not built — `actor diagram --mode fullbright` needs it "
            "(build with `maturin develop`, or run bin/test once)") from None

    brushes, join = [], []
    for actor in actors:
        if actor.brush is None:
            continue
        if movers.is_mover(actor, index) or is_builder_brush(actor):
            continue
        if _csg_oper_or_skip(actor.name, dict(actor.props)) is None:
            continue
        brushes.append(_marshal_brush(actor))
        join.append(actor)

    world_surfaces: list[SolvedSurface] = []
    if brushes:
        try:
            built = uedcli_native.build_geometry_bspcsg(brushes)
            body = uedcli_native.serialize_model(built)
        except uedcli_native.BuildError as ex:
            raise NativePreviewError(f"native CSG solve failed: {ex}") from ex
        from .native.umodel import parse_model_body
        model = parse_model_body(body, 0, len(body))
        for world_verts, i_actor, i_brush_poly, poly_flags, _i_surf in _node_polys(model):
            if 0 <= i_actor < len(join):
                actor = join[i_actor]
                if 0 <= i_brush_poly < len(actor.brush.polys):
                    world_surfaces.append(SolvedSurface(actor, i_brush_poly, world_verts, poly_flags))
                else:                                    # out-of-range poly → grey (M5)
                    world_surfaces.append(SolvedSurface(None, None, world_verts, poly_flags))
            else:                                        # out-of-range owner → grey (M5)
                world_surfaces.append(SolvedSurface(None, None, world_verts, poly_flags))

    mover_polys = []
    for actor in actors:
        if actor.brush is not None and movers.is_mover(actor, index):
            mover_polys += _mover_actor_world_polys(actor)
    return SolvedWorld(world_surfaces=world_surfaces, mover_polys=mover_polys)


def render_shots(*, level, shots: list[Shot], out_dir: Path, index, defaults,
                 size: tuple[int, int] = DEFAULT_SIZE, fov: float = DEFAULT_FOV,
                 search_files=None, texture_use: bool = False, project=None,
                 level_name=None) -> int:
    """Render every SHOT natively into `out_dir` (created if absent). Returns the count
    written. All actor refs resolve up front (all-or-nothing) BEFORE the build. `defaults` is a
    `classdefaults.ClassDefaults`, needed by `build_scene` to light world BSP surfaces.
    `project`/`level_name` are `build_scene`'s scene-cache identity — forwarded verbatim, see its
    docstring.

    `texture_use=True` is `--mode polys`: UnrealEd's real "Texture Use" render (`REN=3`; RE'd in
    `dev/docs/spikes/2026-09-13-polys-render-mode-re/spike.md`) — a flat, unlit swatch per texture
    identity, no shading, no lighting. See `uedcli-native/src/render.rs`'s `texture_use_color`."""
    resolved: list[ResolvedShot] = []
    for shot in shots:                                   # all-or-nothing resolution
        try:
            resolved.append(resolve_pose(shot, lambda n: actor_aim_point(level, n)))
        except ValueError as e:
            raise NativePreviewError(str(e)) from None

    polys, textures, _actor_names, _geom_hash, _light_hash = build_scene(
        level, search_files or [], index, defaults=defaults,
        project=project, level_name=level_name,
        visibility="gameplay")   # unchanged: bHidden, not bHiddenEd (owner ruling 2026-09-14)
    sky_actor = find_sky_actor(level, index)              # None -> every PF_FakeBackdrop face
                                                            # falls back to its own texture

    try:
        out_dir.mkdir(parents=True, exist_ok=True)
        probe = out_dir / ".uedcli-writable"
        probe.touch()
        probe.unlink()
    except OSError as e:
        raise NativePreviewError(f"cannot write to --out-dir {out_dir}: {e}") from None

    from uedcli.native_ext import import_native
    uedcli_native = import_native()
    from PIL import Image
    taken: set[str] = set()
    written = 0
    for i, rs in enumerate(resolved):
        fwd, right, up = camera_basis(rs.pitch, rs.yaw)
        camera = (tuple(float(c) for c in rs.eye), fwd, right, up, float(fov))
        sky = None
        if sky_actor is not None:
            from .rotation import actor_rotation_uu
            sky_pitch_uu, sky_yaw_uu, sky_roll_uu = actor_rotation_uu(sky_actor)
            sky_fwd, sky_right, sky_up = sky_camera_basis(rs.pitch, rs.yaw,
                                                          sky_pitch_uu, sky_yaw_uu, sky_roll_uu)
            sky_loc = sky_actor.location or (0.0, 0.0, 0.0)   # Actor.location is Vec3 | None
            sky = (tuple(float(c) for c in sky_loc), sky_fwd, sky_right, sky_up)
        rgb = uedcli_native.render_frame(polys, textures, camera,
                                         (int(size[0]), int(size[1])), sky, texture_use)
        img = Image.frombytes("RGB", (int(size[0]), int(size[1])), rgb)
        shot_src = shots[i]
        img.save(out_dir / shot_filename(shot_src, i, taken))
        written += 1
    return written
