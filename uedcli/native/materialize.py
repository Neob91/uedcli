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

from struct import Struct

from .actor_write import (Prop, PT_BYTE, PT_INT, PT_OBJECT, PT_STRUCT, StructValue,
                          struct_vector)
from . import assemble as ASM
from .props import convert_actor_props
from ..classindex import CORE_OBJECT, ClassRefError

ZONE_INFO_BASE = "Engine.ZoneInfo"      # AZoneInfo -- every spatial zone actor descends from it
LEVEL_INFO_BASE = "Engine.LevelInfo"    # an AZoneInfo the editor never spatially zones

# Engine pseudo-classes that are NOT normal UClass exports in any `.u` (so a class->package scan
# never finds them) yet are genuinely defined by `Engine`; falling back to `Engine.<X>` is correct
# and must not warn. `Level`/`LevelInfo` are the ones a trunk can name.
_ENGINE_PSEUDO_CLASSES = {"level", "levelinfo"}

_pack_f32 = Struct("<f").pack
_unpack_f32 = Struct("<f").unpack


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


def _pointregion_prop(name: str, *, zone: str, i_leaf: int = -1, zone_number: int = 0) -> Prop:
    """The editor's stamp for a placed actor's `PointRegion`. Into an UNBUILT world every point
    resolves to `iLeaf=-1, ZoneNumber=0` (solid); with a BUILT world model the editor's `SetActorZone`
    descends the BSP at the actor's point, so a point in a carved air leaf takes that leaf's index and
    zone (`_model_point_region`). The Zone late-binds to the zone actor (here the LevelInfo) via
    `ObjRef` (raw bytes cannot carry a forward ref)."""
    return Prop(name, PT_STRUCT, StructValue("PointRegion", [
        Prop("Zone", PT_OBJECT, ASM.ObjRef(zone)),
        Prop("iLeaf", PT_INT, i_leaf),
        Prop("ZoneNumber", PT_BYTE, zone_number)]), struct_name="PointRegion")


def _pawn_region_offsets(cls: str, props, class_defaults):
    """`(foot_drop, head_rise)` for a Pawn actor, or `None` when the class is not a Pawn.

    `ULevel::SetActorZone` (`Engine 0x10161e10`) recomputes, for an actor that IsA `APawn`,
    `FootRegion` at `Location - (0,0,*(float*)(pawn+0x194))` and `HeadRegion` at
    `Location + (0,0,*(float*)(pawn+0x2ec))`. Live capture over 20+ pawns at `0x1782008`: `+0x194`
    reads 39 / 43 / 47.5, each class's `CollisionHeight` default (Jock 47.5, SandraRenton 43); the
    editor holds whatever the actor carries, so an AUTHORED `CollisionHeight` wins over the default.
    `+0x2ec` read 0.0 on every pawn, which is the runtime `EyeHeight` (those classes declare
    `BaseEyeHeight` 36/38/40 and `EyeHeight` 0) -- an editor-placed pawn has never ticked, so it
    still holds its class default.
    """
    if class_defaults is None:
        return None
    info = class_defaults.for_class(cls)
    if not any(o.casefold() == "engine.pawn" for o in info.owners.values()):
        return None

    def effective(field: str) -> float:
        for k, v in props:
            if k.split("(")[0].casefold() == field:
                try:
                    return float(v)
                except ValueError:
                    break
        return float(info.typed_default((field, 0)) or 0.0)

    return effective("collisionheight"), effective("eyeheight")


def _trunk_to_actorspecs(level, schema, world_model=None, zone_actors=None, class_defaults=None):
    """Convert trunk Actors to `ActorSpec`s carrying TYPED `FPropertyTag`s: each raw T3D
    `(key,value)` prop is typed via `props.convert_actor_props` against `schema` (an `ImportSchema`
    or a bare `schema_lookup` callback); `Location` is routed from the actor's typed field.

    `world_model` (the BUILT world Model) recomputes each placed actor's `Region` from the BSP the
    editor's `SetActorZone` descends after a rebuild; without it (unbuilt world) Region stays solid
    `(iLeaf=-1, ZoneNumber=0)`. `zone_actors` (`{zone_number: actor_name}`, the same map that fills
    `Model.Zones[].ZoneActor`) supplies the Region's Zone ref.
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
        # The LevelInfo is the exception: the editor NEVER spatially zones it, so its Region stays
        # the spawn default (Zone=self, iLeaf=-1, ZoneNumber=0) even in a built world -- byte-measured
        # on OceanLab N=3, where the builder brush AND the LevelInfo both sit at the origin yet the
        # golden zones the builder to leaf 73 and leaves the LevelInfo solid.
        if not any(k.casefold() == "region" for k, _v in a.props):
            i_leaf, zone_number = (-1, 0)
            if world_model is not None and getattr(world_model, "nodes", None) and short != "LevelInfo":
                loc = tuple(float(c) for c in (a.location or (0.0, 0.0, 0.0)))
                i_leaf, zone_number = _model_point_region(world_model, loc)
            # `UModel::PointRegion` (`Engine 0x101aee60`) returns `Zones[iZone].ZoneActor` and falls
            # back to the LevelInfo only when that slot is NULL (`0x101aef3e`-`0x101aef4a`), so an
            # actor standing in a ZoneInfo's zone carries THAT actor, not the LevelInfo. Same
            # `{zone: actor}` map `_patch_zone_refs` writes into `Model.Zones[].ZoneActor`.
            props.append(_pointregion_prop("Region", zone=(zone_actors or {}).get(zone_number, li_name),
                                           i_leaf=i_leaf, zone_number=zone_number))
        # A Pawn's `FootRegion`/`HeadRegion` are recomputed by the same `SetActorZone` pass, from the
        # points below and above its collision cylinder (`_pawn_region_offsets`). The trunk carries
        # the source level's values, whose Zone refs a subset cannot resolve; the editor OVERWRITES
        # them, so drop the authored pair and stamp the descent. Only with a BUILT world: with no
        # nodes the rebuild's zoning pass does not run and the imported values stand (NYC_Bar N=58,
        # where UED22 leaves both unresolved).
        pawn_regions = None
        if world_model is not None and getattr(world_model, "nodes", None) and short != "LevelInfo":
            pawn_regions = _pawn_region_offsets(cls, a.props, class_defaults)
        if pawn_regions is not None:
            foot_drop, head_rise = pawn_regions
            x, y, z = (float(c) for c in (a.location or (0.0, 0.0, 0.0)))
            for pname, pz in (("FootRegion", z - foot_drop), ("HeadRegion", z + head_rise)):
                leaf, zone = _model_point_region(world_model, (x, y, pz))
                props.append(_pointregion_prop(pname, zone=(zone_actors or {}).get(zone, li_name),
                                               i_leaf=leaf, zone_number=zone))
        # The editor RESETS these nav-runtime fields when a level is imported (they end up equal
        # to the class default and are omitted from the save -- UNATCO import golden, 2026-09-02);
        # `PATHS BUILD` regenerates them. Serializing a trunk-carried value would diverge from any
        # editor-made map.
        dropped = {"previouspath", "visnoreachpaths", "nextordered", "prevordered"}
        if pawn_regions is not None:
            dropped |= {"footregion", "headregion"}      # stamped above from the BSP descent
        raw_props = [(k, v) for (k, v) in a.props if k.split("(")[0].casefold() not in dropped]
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
        soup = built.world_soup()
    except uedcli_native.BuildError as e:
        raise NativeBuildError(f"native CSG build failed: {e}") from e
    model = UM.parse_model_body(body, 0, len(body))
    # The editor keeps the CSG world soup in Model.Polys; carry it on the model for assembly to emit.
    model.world_soup = soup
    return model, csg_brushes


def _f32(x: float) -> float:
    return _unpack_f32(_pack_f32(x))[0]


def _plane_dot(plane, p) -> float:
    """`FPlane::PlaneDot` (`Core.dll 0x10024e60`) exactly: an SSE horizontal add in SINGLE precision,
    `(P.Z*Z + -W) + (P.Y*Y + P.X*X)`, every operation rounded to f32.

    Both the precision and the summation order are load-bearing. A brush pivot that sits ON a node
    plane can be ~1e-5 off zero in f64 and land on the wrong side of the descent: Island `Brush1359`
    at node 22 (f64 -9.6e-05 -> back, leaf 13; the editor's f32 -> exactly 0.0 -> front, leaf 18) and
    NYC_Bar `Brush69` at node 272 (f64 -7.6e-06 -> back, out of the tree; f32 -> 0.0 -> leaf 55)."""
    px, py, pz = _f32(p[0]), _f32(p[1]), _f32(p[2])
    x, y, z, w = plane
    return _f32(_f32(_f32(-1.0 * w) + _f32(pz * z)) + _f32(_f32(py * y) + _f32(px * x)))


def _model_point_region(model, p) -> tuple[int, int]:
    """PointRegion descent on a built `umodel.Model`: `(iLeaf, zone)` at point `p`. A point in solid
    space (no leaf on the terminating side) is `(-1, 0)`; a point in a carved leaf takes that leaf's
    index and zone number. Mirrors the engine's `Model::PointRegion` used by `SetActorZone`.

    `umodel` names the two children in ON-DISK order (`i_front` = the first serialized index), which
    is the engine's `iChild[0]`/`iBack` -- hence side 1 (`PlaneDot >= 0`, the engine's `IsFront`)
    takes `i_back`, matching `Engine.dll 0x101aef08`'s `iChild[IsFront]`."""
    if not model.nodes:
        return (-1, 0)
    ni = 0
    while True:
        n = model.nodes[ni]
        side = 1 if _plane_dot(n.plane, p) >= 0 else 0
        child = n.i_back if side == 1 else n.i_front
        if child == -1:
            lf = n.i_leaf[side]
            if 0 <= lf < len(model.leaves):
                return (lf, model.leaves[lf].i_zone)
            return (-1, 0)
        ni = child


def _model_point_zone(model, p) -> int:
    """The zone number at point `p` on a built model (0 = solid). See `_model_point_region`."""
    return _model_point_region(model, p)[1]


def _is_zone_actor_class(index, cls: str) -> bool:
    """`ULevel::SetActorZone`'s own test -- `IsA(AZoneInfo) && !IsA(ALevelInfo)` -- decided by the
    resolved class chain, never by how the class is SPELLED.

    The old test was `short.endswith("ZoneInfo")`, which skipped `DeusEx.WaterZone` -- a real
    `Engine.ZoneInfo` subclass. Island's zone 1 then got no zone actor and every `Region` in it fell
    back to the LevelInfo, where UED22 names `WaterZone1` (N=93).

    It answers or it raises (`ClassRefError` -> a clean exit 2): a chain that truncates before the
    `Core.Object` root means a package is off the search path, and answering `False` there would
    silently drop a real zone actor -- the bug above, again."""
    if not cls:
        return False
    if "." not in cls:
        candidates = sorted(index.bare_to_fqcn().get(cls.casefold(), ()))
        if not candidates:
            raise ClassRefError(
                f"cannot decide whether the bare class {cls} is a ZoneInfo: no class of that name "
                f"exists in any package on the composed search path")
        verdicts = {_is_zone_actor_class(index, fqcn) for fqcn in candidates}
        if len(verdicts) > 1:
            raise ClassRefError(
                f"cannot decide whether the bare class {cls} is a ZoneInfo: it resolves to "
                f"{', '.join(candidates)}, and they disagree -- qualify the actor's class")
        return verdicts.pop()
    chain = [a.casefold() for a in index.ancestry(cls)]
    if LEVEL_INFO_BASE.casefold() in chain:
        return False
    if ZONE_INFO_BASE.casefold() in chain:
        return True
    if chain[-1] != CORE_OBJECT.casefold():
        raise ClassRefError(
            f"cannot decide whether class {cls} is a ZoneInfo: its ancestor chain stops at "
            f"{chain[-1]} instead of the {CORE_OBJECT} root, so a package on the chain is missing "
            f"from the composed search path (check the project `paths` and the games config)")
    return False


def resolve_zone_actors(level, model, *, index) -> dict:
    """`zone_number -> the ZoneInfo actor` whose `Location` PointRegion-resolves into that zone.
    `index` is the `classindex.ClassIndex` `_is_zone_actor_class` decides ZoneInfo-ness against --
    by ANCESTRY, so `Engine.SkyZoneInfo`, `Engine.WarpZoneInfo` and `DeusEx.WaterZone` all count.
    `LevelInfo` (also an AZoneInfo) is excluded -- a default interior zone with no ZoneInfo keeps a
    NULL ZoneActor. First actor wins per zone, walked in TRUNK order --
    `level.actors` is keyed by name and iterates alphabetically, which put `ZoneInfo17` ahead of
    `ZoneInfo5` and bound NYC_Bar N=70's only real zone to the wrong one of the two ZoneInfos that
    share it (both resolve to zone 1; UED22 keeps the earlier actor). The built `Actors` array
    reshuffles brushes ahead of point actors (`levelinfo_first_order`), which cannot reorder
    ZoneInfos against each other -- they are all point actors.
    `assemble._patch_zone_refs` rewrites these names to export refs."""
    zone_actors: dict[int, str] = {}
    for name in level.order:
        a = level.actors[name]
        if not _is_zone_actor_class(index, (a.cls or "").strip()):
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
