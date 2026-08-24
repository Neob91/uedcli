"""Assemble an UNBUILT `.dx`/`.unr` from a T3D trunk -- every authored actor with REAL brush polys,
no CSG, no lighting -- for the editor to `MAP LOAD` and build (`MAP REBUILD`/`LIGHT APPLY`/`PATHS
BUILD`), then `MAP SAVE`.

Why this shape. Driving the build with console verbs loses things the console cannot express:
`EDIT PASTE` GPFs building the brush model of complex retail geometry (`02_NYC_Warehouse`), there is
no verb to set a mover's keyframes, and none for `PrePivot`. If instead we WRITE the package
ourselves and let the editor only *build* it, every authored value is our bytes and none of those
verbs are needed.

The one thing that has to hold: a brush that arrives via `MAP LOAD` must participate in CSG.
`MAP IMPORTADD` brushes do not, and a save/reload of one does not repair it -- the add path prepares
something T3D does not carry. The prime suspect is the brush's own `Polys`: `assemble._brush_body`
writes a CSG brush's shape UModel with an EMPTY poly array (the removed native build baked the world
model itself and never needed them); here we write the REAL ones so `MAP LOAD` + `MAP REBUILD` carves.

It reuses `assemble.py`'s low-level helpers rather than `assemble_level`, which emits no brush polys.
"""
from __future__ import annotations

from pathlib import Path

from uedcli.native import actor_write as AW
from uedcli.native import assemble as ASM
from uedcli.native import umodel as UM
from uedcli.native.actor_write import FPoly, Prop
from uedcli.native.props import ImportRef
from uedcli.native.level_write import URL, write_level_body
from uedcli.native.materialize import _trunk_to_actorspecs


def substrate_schema(*pkg_dirs: str | None):
    """An `ImportSchema` over the `.u` files in each dir (class schema + struct member layouts +
    defaults), for full typed-property serialization. Without a real schema every prop is dropped as
    untyped -- including `CsgOper`, which would leave a brush that carves nothing -- so this is not
    optional. Earlier dirs win, so the substrate's engine classes shadow a game copy of the same
    package."""
    from uedcli import mapimport
    paths: dict[str, str] = {}
    for d in (x for x in pkg_dirs if x):
        for f in Path(d).glob("*.u"):
            paths.setdefault(f.stem.casefold(), str(f))
    return mapimport.ImportSchema(resolver=lambda pkg: paths.get(pkg.casefold()))


class DegeneratePoly(ValueError):
    """A polygon the editor would silently discard, leaving a hole in the level."""


def _internal_ref(prop, present: set[str], owner: str, warnings: list):
    """Rewrite an intra-level object ref into an EXPORT ref, not a package import.

    A `MAP EXPORT` writes links between actors as `LevelInfo'MyLevel.LevelInfo0'`, `Base=`,
    `Target=` ... Left as-is, the assembler resolves `MyLevel.X` as an import of a package called
    `MyLevel`, and the engine refuses the load: `Can't import private object`. The target is in this
    very package, so it is an `ObjRef` -- resolved by name at body-build time. Recurses into a
    struct/array value so an internal ref INSIDE one (e.g. a struct member pointing at another actor)
    is rewritten too -- else it leaks a bogus `MyLevel` package import that silently empties the load."""
    prop.value = _rewrite_internal(prop.value, present, owner, prop.name, warnings)
    return prop


def _rewrite_internal(value, present: set[str], owner: str, where: str, warnings: list):
    if isinstance(value, ImportRef) and value.qualified.casefold().startswith("mylevel."):
        target = value.qualified.split(".", 1)[1]
        if target not in present:
            warnings.append(f"{owner}.{where}: refers to {value.qualified}, which this level does "
                            f"not contain -- dropped")
            return 0
        return ASM.ObjRef(target)
    if isinstance(value, AW.StructValue):
        for m in value.members:
            m.value = _rewrite_internal(m.value, present, owner, f"{where}.{m.name}", warnings)
    elif isinstance(value, AW.ArrayValue):
        for e in value.elements:
            e.value = _rewrite_internal(e.value, present, owner, where, warnings)
    return value


# A surface is not always a plain `Texture`: `02_NYC_Bar` binds `drtywater_a` as a `Fire.WetTexture`
# and `09_NYC_ShipFan` binds `Virus_SFX` as a `FireTexture`. Import one under the wrong class and the
# engine does not bind it -- the face ships untextured, with nothing in the log.
_TEXTURE_KINDS = ("Texture", "WetTexture", "WaterTexture", "FireTexture", "IceTexture",
                  "ScriptedTexture", "FractalTexture")


def _texture_kind_index(pkg_dirs) -> dict:
    """`(package stem, object name) -> the object's real class`, over the same `.utx` scan
    `build_texture_group_index` does (which returns only the group)."""
    from uedcli.native.pkg_write import parse_package
    out = {}
    for d in pkg_dirs or ():
        for utx in sorted(Path(d).glob("*.utx")):
            try:
                p = parse_package(utx.read_bytes())
            except Exception:
                continue
            for i, e in enumerate(p.exports):
                kind = p.class_of_export(i)
                if kind in _TEXTURE_KINDS:
                    out.setdefault((utx.stem.casefold(), p.names[e["nm"]].casefold()), kind)
    return out


def _texture_names(level) -> set[str]:
    """Every texture a level's brush polys name."""
    return {p.texture for a in level.actors.values() if getattr(a, "brush", None)
            for p in a.brush.polys if p.texture and p.texture.casefold() != "none"}


def _fpolys(brush, texture_ref=None, *, actor: str = "?") -> list[FPoly]:
    """Trunk `Polygon`s -> `FPoly`s, in the brush's own LOCAL space (the editor transforms by the
    actor's Location/Rotation/scale at build time, exactly as it does for a brush it built).

    `texture_ref(name) -> int` resolves a poly's stored `Package.Name` texture to an import ref.
    Without it every poly comes out untextured."""
    for i, p in enumerate(brush.polys):
        # The T3D importer drops a <3-vertex face without a word -- the level then ships with a hole
        # (measured: surfs 10 -> 9, nothing in the log). Catch it here, where we can name it.
        if len(p.vertices) < 3:
            raise DegeneratePoly(f"actor {actor!r} polygon {i} has {len(p.vertices)} vertices; "
                                 f"the editor would discard it and leave a hole")
    return [FPoly(verts=[tuple(v) for v in p.vertices],
                  base=tuple(p.origin), normal=tuple(p.normal),
                  texture_u=tuple(p.texture_u), texture_v=tuple(p.texture_v),
                  poly_flags=p.flags or 0, item=p.item,
                  texture_ref=(texture_ref(p.texture) if texture_ref and p.texture else 0),
                  # PanU/PanV serialize as u16; a real level's pans are signed and wrap, so mask
                  # rather than let struct.pack reject them.
                  pan_u=(p.pan or (0, 0))[0] & 0xFFFF, pan_v=(p.pan or (0, 0))[1] & 0xFFFF)
            for p in brush.polys]


def assemble_unbuilt(level, *, version: int = 68, level_name: str = "MyLevel",
                     schema=None, pkg_dirs=None):
    """`assemble_level` with an EMPTY world Model and REAL per-brush polys.

    `schema` is the `ImportSchema` (or bare `schema_lookup` callback) that types every actor prop
    (`substrate_schema`). `pkg_dirs` are the package search dirs; they carry two indexes a real level
    cannot do without: the class -> defining-package map (so `DeusExMover` imports from `DeusEx`, not
    `Engine`) and the texture group map (so a poly's 2-part `Package.Name` becomes the
    `Package.Group.Name` the game requires). Omit them only for an engine-classes-only probe level.
    Returns `(package_bytes, warnings)`."""
    actors, brush_actors, warnings = _trunk_to_actorspecs(level, schema or (lambda fqcn: {}))
    present = {a.name for a in actors + brush_actors}
    for spec in actors + brush_actors:
        spec.props = [_internal_ref(pr, present, spec.name, warnings) for pr in spec.props]

    class_packages, texture_groups, texture_kinds = {}, {}, {}
    if pkg_dirs:
        from uedcli.native.pkgref import build_class_package_index, build_texture_group_index
        class_packages = build_class_package_index(pkg_dirs)
        # `Texture` alone misses the animated subclasses a real level uses (`WetTexture`,
        # `FireTexture`, ...), which then look unresolvable and fail the build.
        texture_groups = build_texture_group_index(pkg_dirs, kinds=_TEXTURE_KINDS)
        texture_kinds = _texture_kind_index(pkg_dirs)
    asm = ASM._Assembler(version, level_name, texture_groups=texture_groups,
                         class_packages=class_packages)

    # A T3D export stores textures UNQUALIFIED, and 49 of Deus Ex's 2389 texture names live in two or
    # more packages. Resolve the level's own package set first, from the names that are unambiguous,
    # then use it to settle the rest -- so the choice is made from packages this level demonstrably
    # uses, never an arbitrary first-match.
    by_name: dict[str, set[str]] = {}
    for (pkg_stem, obj), _group in texture_groups.items():
        by_name.setdefault(obj, set()).add(pkg_stem)
    used = {next(iter(c)) for name, c in
            ((n, by_name.get(n.casefold(), set())) for n in _texture_names(level)) if len(c) == 1}

    def tex_ref(name: str) -> int:
        if name.casefold() in ("none", ""):        # T3D's spelling for "no texture"
            return 0
        if "." in name:
            head = name.split(".")[0].casefold()
            return asm.resolver.object_ref(
                texture_kinds.get((head, name.split(".")[-1].casefold()), "Texture"), name)
        candidates = by_name.get(name.casefold(), set())
        if not candidates:
            raise ValueError(f"texture {name!r} is not in any package on the search path -- a "
                             f"substituted default is not acceptable, fix the search path")
        if len(candidates) > 1:
            narrowed = candidates & used
            if len(narrowed) != 1:
                raise ValueError(
                    f"texture {name!r} is ambiguous -- defined by {', '.join(sorted(candidates))}"
                    + (f", and this level uses {', '.join(sorted(narrowed))}" if narrowed else
                       ", none of which this level otherwise uses")
                    + "; qualify it in the trunk")
            candidates = narrowed
        pkg_stem = next(iter(candidates))
        return asm.resolver.object_ref(texture_kinds.get((pkg_stem, name.casefold()), "Texture"),
                                       f"{pkg_stem}.{name}")

    url = URL(map=("Index.unr" if version >= 69 else "Index.dx"))

    li = next((a for a in actors if a.is_level_info), None)
    li_name = li.name if li else "LevelInfo0"
    asm.levelinfo_name = li_name
    ASM._reserve_actor(asm, li_name, "Engine.LevelInfo",
                       lambda: ASM._levelinfo_body(asm, li_name, li.props if li else []),
                       flags=ASM._FLAGS_ACTOR)

    # Actors[1] is always the builder brush (the editor's red brush); it is not authored. Its inner
    # shape MUST be the reserved unnumbered model name `Brush` (`normalize.BUILDER_BRUSH_MODEL_NAME`)
    # so the post-verify's `is_builder_brush` recognises and drops it -- a `Model_*` name would read as
    # a content brush and surface as a spurious extra actor.
    dshape, dbrush = "Brush", "DefaultBrush"
    asm._reserve(dshape + "Polys", "Engine.Polys", ASM._FLAGS_LOAD,
                 lambda: AW.write_upolys_body(asm.name_index, ASM._builder_cube_polys()))
    asm._reserve(dshape, "Engine.Model", ASM._FLAGS_BRUSH,
                 lambda: ASM._empty_model_body(asm, polys_name=dshape + "Polys"))
    ASM._reserve_actor(asm, dbrush, "Engine.Brush",
                       lambda: ASM._brush_body(asm, dbrush, ASM.ObjRef(dshape),
                                               csg_oper=None, extra=[]),
                       flags=ASM._FLAGS_BRUSH_ACTOR)

    for b in [x for x in brush_actors if x.name != dbrush]:
        shape = f"Model_{b.name}"
        src = level.actors.get(b.name)
        polys = _fpolys(src.brush, tex_ref, actor=b.name) if src is not None and src.brush else []
        asm._reserve(f"{shape}Polys", "Engine.Polys", ASM._FLAGS_BRUSH_POLYS,
                     (lambda p=polys: AW.write_upolys_body(asm.name_index, p)))
        asm._reserve(shape, "Engine.Model", ASM._FLAGS_BRUSH,
                     (lambda s=shape: ASM._empty_model_body(asm, polys_name=s + "Polys")))
        ASM._reserve_actor(asm, b.name, b.qualified_class,
                           (lambda b=b, shape=shape: ASM._brush_body(
                               asm, b.name, ASM.ObjRef(shape), csg_oper=None,
                               extra=[asm._resolve_prop_value(p) for p in b.props])),
                           flags=ASM._FLAGS_BRUSH_ACTOR)

    others = [a for a in actors if not a.is_level_info]
    for a in others:
        def _body(a=a):
            authored = list(a.props)
            has_level = any(getattr(p, "name", "").casefold() == "level" for p in authored)
            props = authored if has_level else \
                [Prop("Level", AW.PT_OBJECT, ASM.ObjRef(li_name))] + authored
            return (AW.state_frame(asm.exports[asm.index_of[a.name]].cls)
                    + AW.write_props(asm.name_index,
                                     [asm._resolve_prop_value(p) for p in props]))
        ASM._reserve_actor(asm, a.name, a.qualified_class, _body)

    lm = "Model_Level"
    empty = UM.Model()
    empty.none_index = 0
    asm._reserve(lm, "Engine.Model", ASM._FLAGS_LOAD, lambda: UM.write_model_body(empty))

    def _level_body():
        # The `Actors` array is the level's actor order and must be FAITHFUL to the trunk (UnrealEd
        # interleaves brushes and non-brushes by CSG order; grouping brushes-first would reorder every
        # non-brush actor). `LevelInfo` is always Actors[0] and the builder brush always Actors[1];
        # every other actor follows in trunk order. (`reserve` order above is the separate export-table
        # order, which the editor reshuffles harmlessly.)
        rest = [n for n in (level.order or list(level.actors))
                if n not in (li_name, dbrush)]
        refs = [asm.eref(li_name), asm.eref(dbrush)] + [asm.eref(n) for n in rest]
        return write_level_body(none_index=0, actor_refs=refs, model_ref=asm.eref(lm),
                                url=url, reach_specs=None)
    asm._reserve(level_name, "Engine.Level", ASM._FLAGS_LEVEL, _level_body)
    return asm.build(), warnings
