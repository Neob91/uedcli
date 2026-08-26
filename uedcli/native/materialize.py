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

from .actor_write import Prop, PT_STRUCT, struct_vector, struct_pointregion
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


def _trunk_to_actorspecs(level, schema):
    """Convert trunk Actors to `ActorSpec`s carrying TYPED `FPropertyTag`s: each raw T3D
    `(key,value)` prop is typed via `props.convert_actor_props` against `schema` (an `ImportSchema`
    or a bare `schema_lookup` callback); `Location` is routed from the actor's typed field.
    Returns `(point_actors, brush_actors, warnings)`."""
    actors, brush_actors, warnings = [], [], []
    for name, a in level.actors.items():
        cls = a.cls or "Engine.Actor"
        short = cls.split(".")[-1]
        props = []
        if a.location is not None:
            x, y, z = (float(c) for c in a.location)
            if (x, y, z) != (0.0, 0.0, 0.0):
                props.append(Prop("Location", PT_STRUCT, struct_vector(x, y, z),
                                  struct_name="Vector"))
        # Every PLACED actor carries a `Region` (PointRegion); the engine RECOMPUTES it on load, so
        # a placeholder (Zone=None, iLeaf=-1, ZoneNumber=0) is correct.
        props.append(Prop("Region", PT_STRUCT, struct_pointregion(0, -1, 0),
                          struct_name="PointRegion"))
        raw_props = a.props
        if a.brush is not None:
            # DROP the trunk's `Brush=Model'MyLevel.<shape>'` string prop: `assemble._brush_body`
            # re-synthesizes the shape link as a LOCAL export ref. Left in, `convert_prop` would
            # resolve `MyLevel.<shape>` to a bogus package import that collides with the ULevel export.
            raw_props = [(k, v) for (k, v) in raw_props if k != "Brush"]
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


def build_world_model(level, *, index):
    """Carve the world BSP with the native CSG core (`uedcli_native.build_geometry_bspcsg`) and
    return `(model, csg_brushes)`: the built `umodel.Model` and the CSG-ordered
    `(brush_actor_name, polys)` list that the built surfs' `iActor` tag indexes (what
    `unbuilt.assemble_unbuilt` needs to rewrite each surf's owner + texture to real object refs).

    Movers and the transient builder brush stay out of world CSG, exactly as `csgRebuild` keeps them
    out; `index` is the `classindex.ClassIndex` that decides mover-ness against the real class
    hierarchy. Raises `NativeBuildError` on any failure -- never a partial model."""
    from ..normalize import is_builder_brush
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
        if is_builder_brush(actor) or not _in_world_csg(actor, index):
            continue
        try:
            brushes.append(_build_brush_input(name, actor))
        except BuildError as e:
            raise NativeBuildError(str(e)) from e
        csg_brushes.append((name, actor.brush.polys))
    if not brushes:
        raise NativeBuildError("the trunk has no world-CSG brush actors -- nothing to build")
    try:
        body = uedcli_native.serialize_model(uedcli_native.build_geometry_bspcsg(brushes))
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
