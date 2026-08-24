"""Trunk `Level` -> `ActorSpec`s for the unbuilt-`.dx` assembly (`native/unbuilt.py`).

This is the small trunk->structures seam that `assemble_unbuilt` consumes: each trunk actor becomes
an `assemble.ActorSpec` carrying TYPED `FPropertyTag`s (`props.convert_actor_props`), with `Location`
routed from the actor's typed field. The NATIVE build path (Rust CSG/BSP/lighting) that used to live
here was removed with the editor-less materialize (`fbccd70`); the editor now does the BSP/light/paths
build after `MAP LOAD` of the assembled package.
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


def _parse_vec3(raw: str | None, default=(0.0, 0.0, 0.0)) -> tuple:
    if not raw:
        return default
    from .props import _parse_struct_fields, _f
    f = _parse_struct_fields(raw)
    d = {k: (default[i] if k not in f else 0.0) for i, k in enumerate("XYZ")}
    return tuple(_f(f.get(ax, ""), d[ax]) for ax in "XYZ")
