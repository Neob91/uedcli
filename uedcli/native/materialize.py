"""Trunk `Level` -> `ActorSpec`s for the unbuilt-`.dx` assembly (`native/unbuilt.py`).

This is the small trunk->structures seam that `assemble_unbuilt` consumes: each trunk actor becomes
an `assemble.ActorSpec` carrying TYPED `FPropertyTag`s (`props.convert_actor_props`), with `Location`
routed from the actor's typed field. The editor does the light/paths build after `MAP LOAD` of the
assembled package.

`build_world_model` is the world-BSP half of the editor-free build (`apply._materialize_native`,
gated on `UEDCLI_NATIVE_MATERIALIZE=1`): the Rust `bspBrushCSG` port carves the world instead of the
editor's `MAP REBUILD`, and the built `Model` is written straight into the package's world Model
export.
"""
from __future__ import annotations

from .actor_write import (Prop, PT_BYTE, PT_INT, PT_OBJECT, PT_STRUCT, StructValue,
                          struct_vector)
from . import assemble as ASM
from .props import convert_actor_props

# Engine pseudo-classes that are NOT normal UClass exports in any `.u` (so a class->package scan
# never finds them) yet are genuinely defined by `Engine`; falling back to `Engine.<X>` is correct
# and must not warn. `Level`/`LevelInfo` are the ones a trunk can name.
_ENGINE_PSEUDO_CLASSES = {"level", "levelinfo"}


def default_schema(level=None):
    """An `ImportSchema` over the resolved project's real game `.u` files (class schema + struct
    member layouts + defaults), for full typed-property serialization. Returns a schema whose
    resolver yields None for every package when no project/game is resolvable (tests / harness with
    no config) -- then non-atomic structs skip with a warning."""
    import os
    from .. import config, packages
    from .. import mapimport
    try:
        project = config.resolve_project(
            env_project=os.environ.get("UEDCLI_PROJECT"), cwd=os.getcwd())
        user_config = config.load_user_config()
        resolver = packages.schema_resolver(project, user_config)
    except Exception:
        resolver = lambda _pkg: None                     # no project -> empty schema (skip structs)
    return mapimport.ImportSchema(resolver=resolver)


def default_class_packages():
    """The `classname.casefold() -> defining-package-stem` index over the resolved project's real
    game `.u` code packages (the SAME composed search path `default_schema` uses), so a bare actor
    class resolves to its true owning package (`DeusExMover` -> `DeusEx`) instead of defaulting to
    `Engine`. Returns `{}` when no project/game is resolvable (tests / harness) -- then every class
    falls back to `Engine`."""
    import os
    from .. import config, packages
    from .pkgref import build_class_package_index
    try:
        project = config.resolve_project(
            env_project=os.environ.get("UEDCLI_PROJECT"), cwd=os.getcwd())
        user_config = config.load_user_config()
    except Exception:
        return {}
    # NB the scan itself is deliberately NOT swallowed -- a genuine failure here (vs. the legitimate
    # "no game configured" empty case) must not silently degrade every class back to `Engine.<X>`.
    return build_class_package_index(packages.schema_search_dirs(project, user_config))


def _pointregion_prop(name: str, *, zone: str) -> Prop:
    """The editor's stamp for a placed actor's `PointRegion` in an UNBUILT world:
    Zone=<the LevelInfo>, iLeaf=-1, ZoneNumber=0 (UNATCO import golden, 2026-09-02). The Zone
    late-binds to the LevelInfo export via `ObjRef` (raw bytes cannot carry a forward ref)."""
    return Prop(name, PT_STRUCT, StructValue("PointRegion", [
        Prop("Zone", PT_OBJECT, ASM.ObjRef(zone)),
        Prop("iLeaf", PT_INT, -1),
        Prop("ZoneNumber", PT_BYTE, 0)]), struct_name="PointRegion")


def _trunk_to_actorspecs(level, schema):
    """Convert trunk Actors to `ActorSpec`s carrying TYPED `FPropertyTag`s: each raw T3D
    `(key,value)` prop is typed via `props.convert_actor_props` against `schema` (an `ImportSchema`
    or a bare `schema_lookup` callback); `Location` is routed from the actor's typed field.
    Returns `(point_actors, brush_actors, warnings)`."""
    actors, brush_actors, warnings = [], [], []
    li_name = next((n for n, a in level.actors.items()
                    if (a.cls or "").split(".")[-1] == "LevelInfo"), "LevelInfo0")
    # Spec order = `level.order` (the import order the caller established, e.g.
    # `levelinfo_first_order`) -- the Actors array and export layout are both built from it, so
    # the dict's insertion order must not leak in when the two differ.
    ordered = [(n, level.actors[n]) for n in (level.order or list(level.actors))
               if n in level.actors]
    for name, a in ordered:
        cls = a.cls or "Engine.Actor"
        short = cls.split(".")[-1]
        props = []
        if a.location is not None:
            x, y, z = (float(c) for c in a.location)
            if (x, y, z) != (0.0, 0.0, 0.0):
                props.append(Prop("Location", PT_STRUCT, struct_vector(x, y, z),
                                  struct_name="Vector"))
        # Every PLACED actor carries a `Region` (PointRegion). The editor stamps
        # Zone=<the LevelInfo> (iLeaf=-1, ZoneNumber=0) on import into an unbuilt world -- verified
        # on the UNATCO import golden, 2026-09-02 -- so the Zone late-binds to the LevelInfo export
        # via an ObjRef member (raw bytes cannot carry a forward ref). Skip when the trunk authors
        # `Region` itself (then the typed path serializes the authored value).
        if not any(k.casefold() == "region" for k, _v in a.props):
            props.append(_pointregion_prop("Region", zone=li_name))
        # The editor RESETS these nav-runtime fields when a level is imported (they end up equal
        # to the class default and are omitted from the save -- UNATCO import golden, 2026-09-02);
        # `PATHS BUILD` regenerates them. Serializing a trunk-carried value would diverge from any
        # editor-made map.
        raw_props = [(k, v) for (k, v) in a.props
                     if k.split("(")[0].casefold() not in
                     ("previouspath", "visnoreachpaths", "nextordered", "prevordered")]
        if a.brush is not None:
            # DROP the trunk's `Brush=Model'MyLevel.<shape>'` string prop: `assemble._brush_body`
            # re-synthesizes the shape link as a LOCAL export ref. Left in, `convert_prop` would
            # resolve `MyLevel.<shape>` to a bogus package import that collides with the ULevel export.
            # Also DROP `bDynamicLight`: the editor resets it to the class default (False) on a brush
            # at MAP IMPORT and omits it from the save, so a trunk-authored `bDynamicLight=True`
            # diverges from any editor build (byte-verified, UNATCO Brush74 at N=2).
            raw_props = [(k, v) for (k, v) in raw_props
                         if k != "Brush" and k.split("(")[0].casefold() != "bdynamiclight"]
        # MainScale/PostScale are typed model fields now, not props -- re-inject them as T3D strings
        # so they still serialize into the object's FPropertyTags (a Scale struct via convert_prop).
        from ..transform import emit_fscale
        for _key, _fs in (("MainScale", a.main_scale), ("PostScale", a.post_scale)):
            if _fs is not None:
                raw_props = list(raw_props) + [(_key, emit_fscale(_fs))]
        typed, w = convert_actor_props(cls, raw_props, schema)
        props += typed
        warnings += w
        spec = ASM.ActorSpec(
            name=name, qualified_class=cls, props=props,
            is_level_info=(short == "LevelInfo"),
            is_brush=(a.brush is not None),
            is_player_start=(short == "PlayerStart"))
        (brush_actors if spec.is_brush else actors).append(spec)
    return actors, brush_actors, warnings


class NativeBuildError(ValueError):
    """A native world-BSP build failure, naming the offending value. A `ValueError` so
    `apply.run_materialize`'s guard already turns it into a clean exit 2, like `uprops.SchemaError`."""


def gather_lights(level, *, defaults):
    """The level's participating lights for the native `LIGHT APPLY` bake, in trunk-actor order:
    `[(actor_name, (x, y, z), light_radius_byte, b_special_lit), ...]`.

    The editor's gather pass walks `Level->Actors` in array order and accepts an actor on exactly
    two conditions (`Editor.dll 0x100a4cc7` / `0x100a4cd4`, disassembled 2026-08-27):

        LightType != LT_None    and    (bStatic or bNoDelete)

    There is NO class check -- any class can be a light -- and no facing, zone or brightness test
    here. The second condition is what the first native cut got wrong: it accepted every actor with
    a light type, which on UNATCO pulled in 7 `DeusEx.SecurityCamera`s the editor's bake lists
    nowhere. A `SecurityCamera` does default `LightType=LT_Steady`, but `DeusEx.DeusExDecoration`
    overrides `bStatic` back to False and nothing in its chain sets `bNoDelete`, so the editor drops
    it; `Engine.Light` defaults both True.

    Every value is the EFFECTIVE one -- stated, else the class default from `defaults` (a
    `classdefaults.ClassDefaults`) -- because a bare `Engine.Light` states none of the three.

    The bake itself reads Location, `LightRadius` (a BYTE; world radius `(LightRadius + 1) * 25`,
    `AActor::WorldLightRadius`, `Engine 0x10116b50`) and `bSpecialLit`, which partitions lights and
    surfaces into two disjoint sets (see `light.rs`'s `LightInput`). Brightness, hue and attenuation
    are the game's job at render time."""
    from .. import typedprops
    out = []
    for name in (level.order or list(level.actors)):
        a = level.actors.get(name)
        if a is None:
            continue
        info = defaults.for_class(a.cls or "Engine.Actor")
        if _effective_int(a, info, name, "lighttype", typedprops) == 0:
            continue                                   # LT_None -> not a light
        if not (_effective_bool(a, info, name, "bstatic", typedprops)
                or _effective_bool(a, info, name, "bnodelete", typedprops)):
            continue                                   # a transient actor never bakes
        radius = _effective_int(a, info, name, "lightradius", typedprops)
        out.append((name, _effective_location(a, info),
                    # `LightRadius` is a BYTE, and a `MAP IMPORT` of an out-of-range value WRAPS, so
                    # a trunk saying 300 must bake as 44 -- clamping to 255 instead would give a
                    # different radius from the editor's and the typed post-verify cannot see it.
                    radius % 256,
                    _effective_bool(a, info, name, "bspeciallit", typedprops)))
    return out


def _effective_location(actor, info) -> tuple:
    """The actor's effective world `Location` as floats.

    An actor with NO `Location` line at all parses to `location is None` (the trunk reader is
    schema-free), and the effective value is then the CLASS DEFAULT -- which is not always the
    origin: `Engine.Camera` defaults `Z=300`. Skipping such an actor would silently drop a light
    sitting at its class's default position."""
    if actor.location is not None:
        return tuple(float(c) for c in actor.location)
    return _parse_vec3(info.defaults.get(("location", 0)))


class LightPropError(ValueError):
    """A light property that cannot be decoded -- surfaced rather than read as "not a light", which
    would ship a map missing that light's contribution with no signal. A `ValueError`, so
    `apply.run_materialize`'s guard turns it into a clean exit 2."""


def _effective_value(actor, info, actor_name: str, key: str, typedprops):
    """The actor's effective value for property `key` (casefolded): the value it states, decoded
    through the property's declared `Field`, else the class default.

    A STATED value that does not decode raises `LightPropError` naming the actor, the property and
    the text. It cannot be read as absent: silently treating an undecodable `LightType` as `LT_None`
    drops the light from the bake, and the built map is then wrong with nothing to show for it. An
    actor that simply does not HAVE the property is a different case and resolves to the type's zero
    through `typed_default`, which is how every non-light actor is rejected."""
    stated = next(((k, v) for k, v in actor.props if k.casefold() == key), None)
    if stated is None:
        return info.typed_default((key, 0))
    spelled, text = stated
    value = typedprops.typed_value(text, info.field(key))
    if not isinstance(value, (int, float, bool)):
        raise LightPropError(
            f"{actor_name}: cannot decode {spelled}={text!r} against the class schema for "
            f"{actor.cls!r} -- a light property must resolve to a number or a bool")
    return value


def _effective_int(actor, info, actor_name: str, key: str, typedprops) -> int:
    """`_effective_value` as an int; `0` for a value the type has no number for (the type's zero for
    a property the class does not declare)."""
    v = _effective_value(actor, info, actor_name, key, typedprops)
    return int(v) if isinstance(v, (int, float)) and not isinstance(v, bool) else 0


def _effective_bool(actor, info, actor_name: str, key: str, typedprops) -> bool:
    """`_effective_value` as a bool. A `BoolProperty` decodes to a real `bool`; a class that does not
    declare the property yields the type's zero, which is `False` -- the engine's own default for
    both flags this is used for."""
    return _effective_value(actor, info, actor_name, key, typedprops) is True


def build_world_model(level, *, index, lights=()):
    """Carve the world BSP with the native CSG core (`uedcli_native.build_geometry_bspcsg`), bake the
    lighting into it (`uedcli_native.bake_lighting`), and return `(model, csg_brushes)`: the built
    `umodel.Model` and the CSG-ordered `(brush_actor_name, polys)` list that the built surfs'
    `iActor` tag indexes (what `unbuilt.assemble_unbuilt` needs to rewrite each surf's owner +
    texture to real object refs).

    `lights` is `gather_lights`'s output; the Model's `lights` array comes back holding 0-based
    indexes into it, which `assemble._patch_light_refs` rewrites to export refs using the same
    ordered name list. Empty `lights` still bakes: every lightmappable surf gets a DARK record, which
    is what the editor writes for a level with no lights (§2) and what the game's mesh-actor lighting
    path needs to exist at all.

    Movers stay out of world CSG, exactly as `csgRebuild` keeps them out; `index` is the
    `classindex.ClassIndex` that decides mover-ness against the real class hierarchy. Raises
    `NativeBuildError` on any failure -- never a partial model."""
    from . import umodel as UM
    from .brush_marshal import BuildError, _build_brush_input, _in_world_csg
    try:
        import uedcli_native
    except ImportError:
        raise NativeBuildError(
            "the uedcli_native extension is not built -- the native world-BSP build needs it "
            "(run bin/test once, or build with `maturin develop`)") from None
    brushes, csg_brushes = [], []
    for name in level.order:
        actor = level.actors.get(name)
        if actor is None or actor.brush is None:
            continue
        # No is_builder_brush skip: UED22 excludes Actors[1] by POSITION, and native's synthesized
        # dummy builder (unbuilt.py `_BUILDER`) already occupies that slot and is never a CSG input.
        # Content trunks carry no builder brush (0 is_builder_brush hits on UNATCO), so the heuristic
        # was dead here -- dropping it keeps the two builds symmetric (board:
        # ued22-world-bsp-differs-per-ingest-verb-paste).
        if not _in_world_csg(actor, index):
            continue
        try:
            brushes.append(_build_brush_input(name, actor))
        except BuildError as e:
            raise NativeBuildError(str(e)) from e
        csg_brushes.append((name, actor.brush.polys))
    if not brushes:
        # A brushless subset (e.g. an early actor-prefix that is all point actors -- the lockstep
        # ladder starts at N=1 = LevelInfo only) builds an EMPTY world Model instead of raising.
        # It is the editor's own empty-rebuild output: NumSharedSides=4, RootOutside=Linked=0, and
        # crucially an EMPTY zones array -- `MAP REBUILD` with only the excluded Actors[1] builder
        # brush leaves zones untouched (live-measured on UNATCO N=1, Model2 = 70 bytes, zones=0).
        # NB `build_geometry_bspcsg([])` does NOT match: its finalize synthesizes one default zone
        # (zones=1, +17 bytes), a native artifact the editor never writes for an empty world.
        empty = UM.Model()
        empty.num_shared_sides = 4
        return empty, csg_brushes
    try:
        built = uedcli_native.build_geometry_bspcsg(brushes)
        uedcli_native.bake_lighting(built, [(loc, radius, special) for _n, loc, radius, special in lights])
        body = uedcli_native.serialize_model(built)
    except uedcli_native.BuildError as e:
        raise NativeBuildError(f"native CSG build failed: {e}") from e
    return UM.parse_model_body(body, 0, len(body)), csg_brushes


def _model_point_zone(model, p) -> int:
    """PointRegion descent on a built `umodel.Model`: the zone number at point `p` (0 = solid)."""
    if not model.nodes:
        return 0
    ni = 0
    while True:
        n = model.nodes[ni]
        nx, ny, nz, w = n.plane
        pd = nx * p[0] + ny * p[1] + nz * p[2] - w
        side = 1 if pd >= 0 else 0
        child = n.i_back if side == 1 else n.i_front
        if child == -1:
            lf = n.i_leaf[side]
            return model.leaves[lf].i_zone if 0 <= lf < len(model.leaves) else 0
        ni = child


def resolve_zone_actors(level, model) -> dict:
    """`zone_number -> the ZoneInfo/SkyZoneInfo/WarpZoneInfo actor` whose `Location` PointRegion-
    resolves into that zone. `LevelInfo` (also an AZoneInfo) is excluded -- a default interior zone
    with no ZoneInfo keeps a NULL ZoneActor. First actor wins per zone.
    `assemble._patch_zone_refs` rewrites these names to export refs."""
    zone_actors: dict[int, str] = {}
    for name, a in level.actors.items():
        short = (a.cls or "").split(".")[-1]
        if short == "LevelInfo" or not short.endswith("ZoneInfo"):
            continue
        if a.location is None:
            continue
        z = _model_point_zone(model, tuple(float(c) for c in a.location))
        if z > 0 and z not in zone_actors:
            zone_actors[z] = name
    return zone_actors


def _parse_vec3(raw: str | None, default=(0.0, 0.0, 0.0)) -> tuple:
    if not raw:
        return default
    from .props import _parse_struct_fields, _f
    f = _parse_struct_fields(raw)
    d = {k: (default[i] if k not in f else 0.0) for i, k in enumerate("XYZ")}
    return tuple(_f(f.get(ax, ""), d[ax]) for ax in "XYZ")
