"""Trunk → scene payload for `uedcli serve`. `_LoadedTrunk`/`_BuiltGeometry` (shared-cache spec,
Task 1) are the two independently-cached slots `app.py`'s `_get_trunk`/`_read_geometry`/
`_build_and_publish_geometry` populate — `build_scene_payload` (Task 3) is pure: it assembles a
`ScenePayload` from two already-built pieces instead of loading/building anything itself.
`build_wireframe_payload` (gui-explicit-rebuild plan, Task 2) is its no-geometry-pinned sibling."""
from __future__ import annotations

import sys
from dataclasses import dataclass
from decimal import Decimal

from .. import typedprops, uprops
from ..model import Level
from ..movers import is_mover
from ..preview import _CSG_PALETTE, classify_brush
from ..preview_native import poly_blend, poly_two_sided
from ..rotation import actor_linear, actor_prepivot, actor_rotation_uu, local_offset
from ..writes import actor_bounds

_ZERO3 = (Decimal(0), Decimal(0), Decimal(0))
_FALLBACK_CATEGORY = "Uncategorized"    # uedcli's own catch-all bucket -- not a real UnrealEd category


@dataclass(frozen=True, kw_only=True)
class LightmapFrame:
    """A lit surf's world-space lumel-sampling frame: a lumel's world position is
    `origin + u_step*u + v_step*v`, `u`/`v` in `[0, u_size)`/`[0, v_size)`. The baked lumel RGB
    does NOT ride here — it ships packed in the lightmap atlas (`/api/level/{level}/lightmap`),
    keyed by poly index. The client turns each vertex into a lumel UV from this frame (`lu =
    (pos-origin)·u_step / (u_step·u_step)`, same for `lv` — matching `render.rs`'s own convention)
    and nearest-samples the atlas."""
    origin: list[float]
    u_step: list[float]
    v_step: list[float]
    u_size: int
    v_size: int


@dataclass(frozen=True, kw_only=True)
class ScenePoly:
    """One render-ready polygon, mirroring `build_scene`'s own per-poly tuple field-for-field (see
    its module docstring): world verts (flat x,y,z triples), the base-UV frame, the texture-table
    index, the alpha-test gate, `two_sided`/`blend` (resolved cull + composite mode, below), the raw
    merged `PolyFlags`, and the lit surf's `LightmapFrame` (the baked lumel RGB itself is stripped
    here and packed in the lightmap atlas instead — the frame is all the client needs to compute
    per-vertex lumel UVs). `owner` is NOT part of `build_scene`'s per-poly tuple — it's
    `build_scene`'s separate, parallel `actor_names_by_poly` return, joined in here so the client can
    raycast the real geometry and resolve a hit triangle back to its actor (None for a poly joined to
    no source actor, an out-of-range CSG join)."""
    verts: list[float]
    base: list[float]
    tu: list[float]
    tv: list[float]
    pan: list[float]
    tex_index: int
    masked: bool
    # `two_sided`/`blend` are the render decisions resolved once from the merged `PolyFlags` by
    # `preview_native.poly_two_sided`/`poly_blend` -- the same flags render.rs culls and composites
    # on -- so the web sets three.js state from them and derives no flag logic. `flags` still rides
    # for now (Phase 2 drops it once the web reads only the resolved attrs).
    two_sided: bool
    blend: str
    flags: int
    lightmap: LightmapFrame | None
    owner: str | None


@dataclass(frozen=True, kw_only=True)
class BrushHighlight:
    """A brush actor's own AUTHORED polygons — pre-CSG, local-space, transformed to world exactly
    like `preview.py`'s `_scene_geometry` (`Location + L·(v − PrePivot)`, `L = actor_linear`) — for
    the selection outline. Deliberately NOT `ScenePayload.polys` (the CSG-SOLVED result): the point
    is to show the brush's own authored shape, matching `actor diagram --mode wire --highlight`.
    `color` is that classification's vivid front hue (`preview._CSG_PALETTE[csg_class][0]`), so a
    highlighted brush always draws in its OWN CSG colour, never a fixed selection colour."""
    csg_class: str
    color: tuple[int, int, int]
    polys: list[list[float]]   # one entry per poly: flat world verts (x0,y0,z0, x1,y1,z1, ...)


@dataclass(frozen=True, kw_only=True)
class ActorSprite:
    """A point actor's resolved `DT_Sprite` billboard — the actual class-defined icon texture (a
    light's bulb, a trigger's flag, ...) at its natural size scaled by `DrawScale`
    (`preview_native.resolve_actor_sprites`, reusing `cli/rendering.py::_resolve_point_render`'s
    resolution logic and `preview.sprite_footprint`'s math for this NEW, 3D-marker call site) — what
    the client draws instead of the fallback grey dot. `tex_index` indexes the SAME
    `/api/level/{level}/atlas` table every world/mesh poly already uses; `width`/`height` are the
    billboard's world-space (UU) footprint."""
    tex_index: int
    width: float
    height: float


@dataclass(frozen=True, kw_only=True)
class SceneActor:
    """One actor's metadata for the inspector/organization panel — NOT its geometry (a brush
    actor's polys already ride in `ScenePayload.polys`, joined by CSG, not by actor). `props` is
    the actor's raw stored T3D property list (`Actor.props`, `list[(key, raw-text-value)]`) — the
    read-only inspector's "full raw T3D property set" (spec, "Selection & inspector"). `categories`
    is `props`' parallel UnrealEd category array (`categories[i]` groups `props[i]`; `_actor_categories`)
    — `_FALLBACK_CATEGORY` ("Uncategorized") for an unresolvable class or an unmatched/schema-`None`
    prop. `brush` is the selection-highlight geometry (None for a non-brush actor — a separate task's
    concern).
    `sprite` is None for a brush actor, and for a point actor whose `DT_Sprite` billboard didn't
    resolve — the client then falls back to a generic marker (`markers.ts`)."""
    name: str
    cls: str
    bbox_lo: tuple[float, float, float]
    bbox_hi: tuple[float, float, float]
    location: tuple[float, float, float]
    rotation: tuple[int, int, int]
    folder: str | None
    labels: list[str]
    order_value: str
    props: list[tuple[str, str]]
    categories: list[str]
    brush: BrushHighlight | None
    sprite: ActorSprite | None


@dataclass(frozen=True, kw_only=True)
class ScenePayload:
    polys: list[ScenePoly]
    actors: list[SceneActor]


@dataclass(frozen=True, kw_only=True)
class _LoadedTrunk:
    """Load-owned data: trunk/actor content, no solve involved (shared-cache spec's Design
    section). `sprite_table`/`actor_sprites` are `resolve_actor_sprites`'s own raw return —
    `actor_sprites` is DELIBERATELY `dict[str, tuple[int, float, float]]`, not `dict[str,
    ActorSprite]`: wrapping needs `tex_offset = len(geometry.texture_table)`, a GEOMETRY-slot value
    not known while only the trunk slot is being built. The wrap into `ActorSprite` still happens
    in `build_scene_payload` below, exactly like before this split, once both slots are available."""
    level: Level
    ranks: dict[str, str]
    folders: dict[str, str | None]
    sprite_table: list[tuple[int, int, bytes, bytes]]
    actor_sprites: dict[str, tuple[int, float, float]]


@dataclass(frozen=True, kw_only=True)
class _BuiltGeometry:
    """Rebuild-owned data: CSG + lighting output (shared-cache spec's Design section). `geom_hash`/
    `light_hash` are `None` for now — `build_scene` computes them internally but doesn't return
    them yet (plan's OQ1, deferred: widening its return tuple touches ~30+ call sites elsewhere and
    no route here reads these fields either way)."""
    geom_hash: str | None
    light_hash: str | None
    polys: list[tuple]
    texture_table: list[tuple]
    owners: list[str | None]


def _lightmap_frame(lightmap: tuple | None) -> LightmapFrame | None:
    """`build_scene`'s per-poly lightmap tuple `(origin, u_step, v_step, u_size, v_size, rgb)` →
    the frame the client needs (RGB dropped — it goes in the atlas), or None for an unlit poly."""
    if lightmap is None:
        return None
    origin, u_step, v_step, u_size, v_size, _rgb = lightmap
    return LightmapFrame(origin=list(origin), u_step=list(u_step), v_step=list(v_step),
                         u_size=u_size, v_size=v_size)


def _brush_highlight(actor, index) -> BrushHighlight | None:
    """`actor`'s own authored polys, world-transformed, plus its CSG classification/colour — or
    None for a non-brush actor. `is_mover` is the AUTHORITATIVE `movers.is_mover` answer (not the
    name-guess `classify_brush` falls back to with `is_mover=None`), matching every OTHER filled
    render's own disposition (`preview.py`'s `_scene_geometry` docstring)."""
    if actor.brush is None:
        return None
    csg_class = classify_brush(actor, is_mover=is_mover(actor, index))
    color = _CSG_PALETTE[csg_class][0]
    R = actor_linear(actor)
    prepivot = actor_prepivot(actor)
    loc = actor.location or _ZERO3
    polys = []
    for poly in actor.brush.polys:
        verts: list[float] = []
        for v in poly.vertices:
            off = local_offset(R, prepivot, v)
            verts += [float(loc[0] + off[0]), float(loc[1] + off[1]), float(loc[2] + off[2])]
        polys.append(verts)
    return BrushHighlight(csg_class=csg_class, color=color, polys=polys)


def _is_hidden_ed(actor, defaults) -> tuple[bool, str | None]:
    """`actor`'s effective `bHiddenEd` (instance override else class default), plus a stderr note
    when the class default couldn't be resolved — same instance-else-class-default convention and
    degrade-to-visible-on-unresolvable-schema disposition as `cli/rendering.py::_is_hidden_ed` (a
    different call site, for `actor diagram`), reused here rather than reinvented. `defaults` is the
    caller's shared `classdefaults.ClassDefaults` memo, NOT a fresh per-actor
    `uprops.resolve_class_defaults` call — a level has hundreds of actors across a handful of
    distinct classes, and re-resolving the whole schema chain per actor (a package load + Super-chain
    walk + defaults decode, ~0.1-0.3s cold) was the O(actors) cost this fix removes.

    Owner ruling 2026-09-14: the GUI hides a `bHiddenEd` actor from `ScenePayload.actors` outright —
    the actor-list entry, its selection highlight, and its fallback marker (`build_scene_payload`
    below gates all three off this one result). A `bHiddenEd` BRUSH additionally has its own rendered
    CSG surfaces dropped, but only when it's a `CSG_Add` — see `build_scene_payload`'s docstring for
    why a `CSG_Subtract`'s own surfaces can't be dropped the same way.

    This try/except only protects THIS function's own resolution — it does NOT make a whole
    `/scene` request resilient to an unresolvable actor class. `build_scene_payload` calls
    `build_scene` (which calls `gather_lights`, unguarded, pre-existing) BEFORE it ever calls this
    function, and `gather_lights` resolves every actor's class through the same `defaults` memo
    first — so a level with one actor whose class can't be resolved at all still fails the whole
    request there, never reaching this fail-open path. See `build_scene_payload`'s docstring."""
    instance = {k.casefold(): v for k, v in actor.props}
    if "bhiddened" in instance:
        return instance["bhiddened"].strip() == "True", None
    try:
        info = defaults.for_class(actor.cls)
    except uprops.SchemaError as e:
        return False, (f"actor {actor.name!r}: schema unavailable ({actor.cls}) — cannot check its "
                       f"class-default bHiddenEd, assuming visible ({e})")
    return str(info.defaults.get(("bhiddened", 0), "False")).strip() == "True", None


def _resolve_hidden_ed(level: Level, defaults) -> dict[str, bool]:
    """Each actor's effective `bHiddenEd` (`_is_hidden_ed`), gathered once per `level.order` walk --
    shared by `build_scene_payload` (which additionally uses it to drop a hidden CSG_Add brush's own
    surfaces) and `build_wireframe_payload` (which has no surfaces to drop, only actors to filter)."""
    hidden_ed: dict[str, bool] = {}
    notes: list[str] = []
    for name in level.order:
        actor = level.actors.get(name)
        if actor is None:
            continue
        is_hidden, note = _is_hidden_ed(actor, defaults)
        hidden_ed[name] = is_hidden
        if note:
            notes.append(note)
    for line in notes:
        print(line, file=sys.stderr)
    return hidden_ed


def _class_category_map(fqcn: str, index) -> dict[str, str] | None:
    """`casefold(prop name) -> UnrealEd category` for `fqcn`'s full (own+inherited) schema, or None
    if the class's schema can't be resolved at all (offline index / missing package) — caller falls
    back to `_FALLBACK_CATEGORY` for every one of that actor's props rather than failing the payload.
    `resolve_class_properties` already keeps the most-derived prop on a name collision, matching
    `class show`'s own convention."""
    resolver = getattr(index, "resolver", None)
    if resolver is None:
        return None
    try:
        props = uprops.resolve_class_properties(fqcn, resolver=resolver())
    except uprops.SchemaError:
        return None
    return {p.name.casefold(): (p.category or _FALLBACK_CATEGORY) for p in props}


def _actor_categories(props: list[tuple[str, str]],
                      category_map: dict[str, str] | None) -> list[str]:
    """`categories[i]` for `props[i]`: `_FALLBACK_CATEGORY` if `category_map` is None (unresolvable
    class) or the prop's name (index-stripped, `KeyPos(1)` and `KeyPos` share one category) isn't in
    it."""
    if category_map is None:
        return [_FALLBACK_CATEGORY for _ in props]
    return [category_map.get(typedprops.split_index(key)[0].casefold(), _FALLBACK_CATEGORY)
            for key, _ in props]


def _build_actors(trunk: _LoadedTrunk, hidden_ed: dict[str, bool], *, tex_offset: int,
                  index) -> list[SceneActor]:
    """The actor-metadata list (inspector/organization panel + selection highlight + sprite), built
    from `trunk` alone -- shared by both `build_scene_payload` (geometry pinned, `tex_offset =
    len(geometry.texture_table)`) and `build_wireframe_payload` (no geometry, `tex_offset = 0`).
    `category_maps` memoizes `_class_category_map` per class for this call -- a level can have many
    actors of one class, so this avoids re-walking the Super chain per actor."""
    level = trunk.level
    ranks = trunk.ranks
    actor_sprites = trunk.actor_sprites
    category_maps: dict[str, dict[str, str] | None] = {}
    actors = []
    for name in level.order:
        actor = level.actors.get(name)
        if actor is None or hidden_ed.get(name):
            continue                                     # editor-hidden: no metadata, no marker
        lo, hi = actor_bounds(actor)
        loc = actor.location or _ZERO3
        sprite = None
        if (raw := actor_sprites.get(name)) is not None:
            local_idx, width, height = raw
            sprite = ActorSprite(tex_index=tex_offset + local_idx, width=width, height=height)
        cls = actor.cls or ""
        if cls not in category_maps:
            category_maps[cls] = _class_category_map(cls, index)
        actors.append(SceneActor(
            name=name, cls=cls,
            bbox_lo=tuple(float(c) for c in lo), bbox_hi=tuple(float(c) for c in hi),
            location=tuple(float(c) for c in loc), rotation=actor_rotation_uu(actor),
            folder=actor.folder, labels=sorted(actor.labels), order_value=ranks.get(name, ""),
            props=list(actor.props), categories=_actor_categories(actor.props, category_maps[cls]),
            brush=_brush_highlight(actor, index), sprite=sprite))
    return actors


def build_scene_payload(trunk: _LoadedTrunk, geometry: _BuiltGeometry, index, defaults
                        ) -> ScenePayload:
    """Assemble a `ScenePayload` from two ALREADY-BUILT pieces — `trunk` (`_LoadedTrunk`: the level,
    its per-actor ranks, and `resolve_actor_sprites`' raw output) and `geometry` (`_BuiltGeometry`:
    `build_scene`'s solved polys/texture table/owners) — instead of loading or building anything
    itself (shared-cache spec's Design section; `app.py`'s `_get_trunk`/`_read_geometry`/
    `_build_and_publish_geometry` own the caching, this function is now pure). `index`/`defaults`
    are still needed HERE, independent of either cached slot: `_is_hidden_ed(actor, defaults)` and
    `_brush_highlight(actor, index)` both
    resolve per-actor state (a `bHiddenEd` class default, a brush's CSG classification) on every
    call. Real parameters this function needs regardless of the plan's illustrative signature (which
    dropped `defaults` entirely — `_is_hidden_ed` cannot run without it; flagged in the build report).

    **This function's own per-actor loop is NOT the bottleneck** (an earlier version of this
    docstring claimed the per-actor cost was "cheap enough... caching isn't worth it" — that was
    only checked at toy scale; measured wrong at real-level scale, see below, though for a different
    reason than "per-actor cost"). `_is_hidden_ed`'s `defaults.for_class(actor.cls)` already
    amortizes to one real resolution per DISTINCT class within a single call to this function (the
    `ClassDefaults` memo persists across the loop) — a `test_build_scene_payload_amortizes_class_
    resolution_over_repeated_classes` regression pins exactly that. The actual live bug (a real
    WanChai-scale `uedcli serve` request staying ~28s even on a WARM trunk/geometry cache) was one
    level UP: `app.py`'s `scene()` route built a brand-new `defaults`/`index` via `_scene_inputs()`
    on EVERY HTTP request, so the memo THIS function relies on was thrown away and rebuilt from
    scratch (a package load + Super-chain walk + defaults decode per distinct class, ~0.1-0.3s cold
    each) on every single request, warm cache or not — this function's own amortization only ever
    helped WITHIN one already-doomed call. Fixed by caching this function's OUTPUT in `app.py`
    (`_payload_ref`/`_get_payload`, generation-guarded like `_get_trunk`/`_get_geometry`), so a warm
    request never calls this function at all. Profiled fix (`_scratch/profile_scene.py`, a synthetic
    2288-actor/19-distinct-class level): ~1.8s on every repeat call before the fix, ~1.8s once then
    ~0.06s every call after.

    A `bHiddenEd` actor is dropped from `ScenePayload.actors` entirely (`_is_hidden_ed` above) —
    owner ruling 2026-09-14: the GUI hides editor-hidden actors and ignores `bHidden` (the opposite
    of `level photo --native`). `build_scene` itself already excludes such a mesh actor's triangles
    (`visibility="editor"`, applied when `geometry` was built), so this actor-list drop is what
    additionally hides its selection highlight and its `markers.ts` fallback marker — one filter for
    meshes, brushes, and bare point actors alike, rather than three.

    A `bHiddenEd` BRUSH additionally drops its own rendered CSG surfaces from `ScenePayload.polys`
    (owner-attributed via `geometry.owners` / `ScenePoly.owner`) — but ONLY when the brush is a
    `CSG_Add`: its own surfaces are its solid contribution, safe to omit like any other hidden
    actor's geometry. A `CSG_Subtract` (or other non-Add) brush's own surfaces are the WALLS of the
    volume it carved, not a separate solid to hide — omitting them would open a real hole in the
    built geometry (no other brush supplies that face), so they stay rendered regardless of
    `bHiddenEd`. A Mover carries no `CsgOper` prop at all (it never participates in world CSG), so
    `hidden_add_owners`'s `CsgOper` lookup below defaults it to `"CSG_Add"` — correctly: a Mover's own
    surfaces are its own solid contribution (like a CSG_Add brush's), never another actor's wall, so
    dropping them when it's hidden is safe the same way.

    A class-resolution failure IN `_is_hidden_ed` ITSELF degrades to "not hidden" — both the actor
    and its surfaces stay — with one stderr note per affected actor, rather than a raised exception
    from this one call. (`build_scene`'s own class resolution — `gather_lights` et al., run when
    `geometry` was built, before this function ever sees the result — is a separate, unguarded path:
    a level with an actor whose class can't be resolved at all fails there, same as `level
    materialize`'s own no-fallback-default rule; this fix narrows what `_is_hidden_ed` itself can
    break, it doesn't change that other, pre-existing behavior.)"""
    level = trunk.level
    hidden_ed = _resolve_hidden_ed(level, defaults)
    polys, texture_table, owners = geometry.polys, geometry.texture_table, geometry.owners
    # Only a hidden CSG_Add brush's own surfaces are safe to drop -- see this function's docstring.
    hidden_add_owners = {
        name for name, hidden in hidden_ed.items()
        if hidden and (a := level.actors.get(name)) is not None and a.brush is not None
        and dict(a.props).get("CsgOper", "CSG_Add") == "CSG_Add"
    }
    scene_polys = [
        ScenePoly(verts=verts, base=list(base), tu=list(tu), tv=list(tv), pan=list(pan),
                 tex_index=tex_index, masked=masked, two_sided=poly_two_sided(flags),
                 blend=poly_blend(flags), flags=flags, lightmap=_lightmap_frame(lightmap),
                 owner=owner)
        for (verts, base, tu, tv, pan, tex_index, masked, flags, lightmap), owner
        in zip(polys, owners)
        if owner not in hidden_add_owners
    ]
    # Point-actor sprite billboards ride in trunk.sprite_table/actor_sprites (Load-owned, no CSG
    # involved) -- `/api/level/{level}/atlas` (`app.py`'s `atlas` route) appends that SAME
    # `resolve_actor_sprites` result onto `geometry.texture_table` in the same order, so
    # `tex_offset + local_index` names the same atlas rect on both endpoints.
    actors = _build_actors(trunk, hidden_ed, tex_offset=len(texture_table), index=index)
    return ScenePayload(polys=scene_polys, actors=actors)


def build_wireframe_payload(trunk: _LoadedTrunk, index, defaults) -> ScenePayload:
    """The cold-open / no-Rebuild-yet payload (gui-explicit-rebuild spec §4): no solved geometry is
    pinned, so `polys` is genuinely empty (never an error) and every brush actor's own AUTHORED
    `SceneActor.brush` shape is all the client can draw -- exactly what lets wireframe mode render
    with zero dependency on `_BuiltGeometry`. `tex_offset` is 0: `/atlas` builds its atlas from ONLY
    `trunk.sprite_table` in this case (`app.py`'s `atlas` route skips `geometry.texture_table`
    entirely when no geometry is pinned), so a sprite's `tex_index` names a rect in THAT atlas, at
    the sprite's own position with no offset."""
    hidden_ed = _resolve_hidden_ed(trunk.level, defaults)
    actors = _build_actors(trunk, hidden_ed, tex_offset=0, index=index)
    return ScenePayload(polys=[], actors=actors)
