"""Object-graph assembly (§30.5-6): synthesize the name/import tables, serialize every
body, splice the built level Model, and lay out the package.

Also enforces the from-scratch invariants the editor used to hide (§3):
  Actors[0] is exactly engine class `LevelInfo` (synthesized if the trunk lacks one),
  Actors[1] is a Default Brush + a builder-cube UModel (synthesized if absent),
  a PlayerStart is present (asserted — NOT synthesized: where the player starts is an
  authoring decision).

The public entry is `assemble_level`.  Inputs are plain structures (below); the trunk->
structures conversion lives in `materialize.py`.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from . import actor_write as AW
from . import umodel as UM
from .actor_write import Prop, FPoly
from .codec import ref_export
from .level_write import URL, write_level_body, ReachSpec
from .pkg_write import NameTable, ExportRec, build_package
from .pkgref import Resolver
from .props import ImportRef

RF_HasStack = 0x02000000
_FLAGS_ACTOR = 0x02070001
_FLAGS_LEVEL = 0x00070001
# Non-actor helper exports MUST carry the RF_Load* context bits or a standalone game skips
# loading them (RF_LoadForClient|Server|Edit = 0x70000); a skipped level Model makes
# MyLevel.ModelRef unresolvable and the whole ULevel load aborts ("Failed to find object
# 'Level None.MyLevel'").  Values match real DeusEx maps (e.g. DXOnly.dx), verified live:
#   level BSP Model + level/default-brush Polys -> RF_Load* (client+server+edit)
#   brush *shape* Model + CSG brush Polys       -> edit-only (RF_LoadForEdit|NotForClient|
#                                                  NotForServer) so the game skips them
_FLAGS_LOAD = 0x00070001          # RF_Transactional | LoadForClient | LoadForServer | LoadForEdit
_FLAGS_BRUSH = 0x00340001         # RF_Transactional | LoadForEdit | NotForClient | NotForServer
_FLAGS_HELPER = _FLAGS_LOAD       # default for a loadable non-actor helper (level Model/Polys)
_FLAGS_PUBLIC = 0x00000004
# Brush ACTORS (both the default builder brush and every CSG brush) carry the editor's
# edit-only-actor flag set: RF_HasStack | RF_Transactional | LoadForEdit | NotForClient |
# NotForServer.  The built world BSP is what the GAME loads; the source brush actors are
# editor-only (the engine skips them at runtime).  Matches UnrealEd byte-for-byte (every
# Brush export in Test_Castle.dx / retail `.dx` is 0x02340001) — verified 2026-07-18.
_FLAGS_BRUSH_ACTOR = 0x02340001   # RF_HasStack | Transactional | LoadForEdit | NotForClient/Server
# A CSG brush's SHAPE UPolys is written LOAD-for-all with NO Transactional/HasStack bit —
# the editor emits 0x00070000 for every CSG-brush Polys (Polys176/178/… in Test_Castle.dx),
# distinct from its parent shape Model (edit-only 0x00340001).  The DEFAULT brush's Polys
# instead carries RF_Transactional (0x00070001) — see the default-brush reservation below.
_FLAGS_BRUSH_POLYS = 0x00070000   # LoadForClient | LoadForServer | LoadForEdit (no Transactional)


class ObjRef:
    """A late-bound reference to another export, resolved by name at body-build time."""
    def __init__(self, name: str):
        self.name = name


@dataclass
class BrushShape:
    """An authored brush shape: a UModel (named) + its UPolys child."""
    model_name: str
    polys: list[FPoly] = field(default_factory=list)


@dataclass
class ActorSpec:
    name: str
    qualified_class: str
    props: list = field(default_factory=list)     # list[Prop]; Object values may be ObjRef
    is_level_info: bool = False
    is_brush: bool = False
    is_player_start: bool = False


class _Assembler:
    def __init__(self, version: int, level_name: str, texture_groups: dict | None = None,
                 class_packages: dict | None = None):
        self.version = version
        self.level_name = level_name
        self.names = NameTable()
        # "None" must be name index 0 so the UModel prefix ci(None) is a single byte.
        assert self.names.index("None") == 0
        self.resolver = Resolver(self.names, texture_groups=texture_groups,
                                 class_packages=class_packages)
        self.exports: list[ExportRec] = []
        self.index_of: dict[str, int] = {}        # object name -> 0-based export index
        self._body_fns: list = []                  # parallel to exports
        self.levelinfo_name: str = "LevelInfo0"   # the Actors[0] singleton's name

    def _reserve(self, name: str, qualified_class: str, flags: int, body_fn) -> int:
        if name in self.index_of:
            raise ValueError(f"duplicate export object name: {name!r}")
        idx0 = len(self.exports)
        self.index_of[name] = idx0
        cls_ref = self.resolver.qualified_class_ref(qualified_class)
        self.exports.append(ExportRec(cls=cls_ref, super_ref=0, outer=0,
                                      name=self.names.index(name), flags=flags, body=b""))
        self._body_fns.append(body_fn)
        return idx0

    def eref(self, name: str) -> int:
        """Object-ref of a reserved export."""
        return ref_export(self.index_of[name])

    def name_index(self, s: str) -> int:
        return self.names.index(s)

    def _resolve_prop_value(self, p: Prop) -> Prop:
        """Resolve a Prop's late-bound object refs to integer object-refs. Recurses into a
        `StructValue`/`ArrayValue` so an Object/Class member (e.g. an `InitialInventory` item's
        `Inventory=Class'...'`) resolves too."""
        v = self._resolve_value(p.ptype, p.value)
        return p if v is p.value else Prop(p.name, p.ptype, v, struct_name=p.struct_name,
                                           array_index=p.array_index)

    def _resolve_value(self, ptype, value):
        if ptype == AW.PT_OBJECT:
            if isinstance(value, ObjRef):
                return self.eref(value.name)
            if isinstance(value, ImportRef):
                return self.resolver.object_ref(value.object_class, value.qualified)
            return value
        if ptype == AW.PT_STRUCT and isinstance(value, AW.StructValue):
            return AW.StructValue(value.struct_name,
                                  [self._resolve_prop_value(m) for m in value.members])
        if ptype == AW.PT_ARRAY and isinstance(value, AW.ArrayValue):
            return AW.ArrayValue([self._resolve_prop_value(e) for e in value.elements])
        return value

    def build(self) -> bytes:
        # Body fns run AFTER all exports are reserved, so eref() resolves any forward ref.
        for i, fn in enumerate(self._body_fns):
            self.exports[i].body = fn()
        return build_package(version=self.version, licensee=0, package_flags=0x00000001,
                             names=self.names, imports=self.resolver.imports,
                             exports=self.exports)


def _builder_cube_polys() -> list[FPoly]:
    """A trivial 256-unit builder cube (the red brush shape).  Geometry doesn't matter
    for load; it only needs to be a valid UPolys."""
    h = 128.0
    faces = [
        # (base, normal, verts)
        ((0, 0, h), (0, 0, 1), [(-h, -h, h), (-h, h, h), (h, h, h), (h, -h, h)]),
        ((0, 0, -h), (0, 0, -1), [(h, -h, -h), (h, h, -h), (-h, h, -h), (-h, -h, -h)]),
    ]
    out = []
    for base, normal, verts in faces:
        out.append(FPoly(verts=verts, base=base, normal=normal,
                         texture_u=(1, 0, 0), texture_v=(0, 1, 0)))
    return out


def assemble_level(*, level_model: UM.Model, actors: list[ActorSpec],
                   brush_shapes: list[BrushShape], version: int = 68,
                   level_name: str = "MyLevel", url: URL | None = None,
                   reach_specs: list[ReachSpec] | None = None,
                   csg_brushes: list | None = None,
                   light_names: list | None = None,
                   texture_groups: dict | None = None,
                   class_packages: dict | None = None,
                   zone_actors: dict | None = None) -> bytes:
    """Assemble a full `.dx`/`.unr` package from the built level Model + actor set.

    `csg_brushes`, when given, is the CSG-ordered brush source list indexed by the built Model's
    surf `iActor` (the brush index the Rust build tags each surf with): each entry is
    `(brush_actor_name, [model.Polygon, ...])`.  It lets assembly rewrite each level-Model surf's
    `iActor` -> the brush actor's export object-ref and `texture_ref` -> the imported texture the
    source poly names (§30.6: textures are IMPORTED by ref, never embedded).

    `light_names`, when given, is the ordered list of baked light actor names (index i == the
    0-based light index the Model's `lights` array carries from the N-4 bake); it lets assembly
    rewrite that array's indices to the light actors' export object-refs (`_patch_light_refs`).

    `class_packages`, when given, is the `classname.casefold() -> defining-package-stem` index
    (`pkgref.build_class_package_index`) that resolves each actor's BARE class to its real owning
    package (`DeusExMover` -> `DeusEx`) rather than defaulting every class to `Engine` (spike
    section 88).

    Raises ValueError (naming the offending value) on any invariant violation."""
    asm = _Assembler(version, level_name, texture_groups=texture_groups,
                     class_packages=class_packages)
    url = url or URL(map=("Index.unr" if version >= 69 else "Index.dx"))

    # --- Actors[0]: LevelInfo -------------------------------------------------
    level_infos = [a for a in actors if a.is_level_info]
    other_actors = [a for a in actors if not a.is_level_info and not a.is_brush]
    brush_actors = [a for a in actors if a.is_brush]

    if not any(a.is_player_start for a in actors):
        raise ValueError("no PlayerStart actor in the level — the game cannot spawn the "
                         "player (add a PlayerStart; where it goes is an authoring decision)")

    # reserve LevelInfo (synthesize a minimal engine LevelInfo if the trunk lacks one)
    if level_infos:
        li = level_infos[0]
        li_name = li.name
        li_props = li.props
    else:
        li_name = "LevelInfo0"
        li_props = []
    asm.levelinfo_name = li_name
    _reserve_actor(asm, li_name, "Engine.LevelInfo",
                   lambda: _levelinfo_body(asm, li_name, li_props))

    # --- Actors[1]: Default Brush + its builder-cube UModel -------------------
    explicit_default = [a for a in brush_actors if a.name.lower() in ("brush0", "brush")]
    default_brush_name = "Brush0"
    default_shape_name = "Brush"
    # always synthesize the default brush shape UModel + Polys (builder cube)
    asm._reserve(default_shape_name + "Polys", "Engine.Polys", _FLAGS_LOAD,
                 lambda: AW.write_upolys_body(asm.name_index, _builder_cube_polys()))
    asm._reserve(default_shape_name, "Engine.Model", _FLAGS_BRUSH,
                 lambda: _empty_model_body(asm, polys_name=default_shape_name + "Polys"))
    db_idx = _reserve_actor(
        asm, default_brush_name, "Engine.Brush",
        lambda: _brush_body(asm, default_brush_name, ObjRef(default_shape_name),
                            csg_oper=None, extra=[]),
        flags=_FLAGS_BRUSH_ACTOR)

    # --- remaining CSG brush actors + their shapes ---------------------------
    for b in brush_actors:
        if b.name == default_brush_name:
            continue
        # each CSG brush references a shape UModel of the same base name
        shape = f"Model_{b.name}"
        asm._reserve(f"{shape}Polys", "Engine.Polys", _FLAGS_BRUSH_POLYS,
                     lambda: AW.write_upolys_body(asm.name_index, []))
        asm._reserve(shape, "Engine.Model", _FLAGS_BRUSH,
                     (lambda s=shape: _empty_model_body(asm, polys_name=s + "Polys")))
        _reserve_actor(asm, b.name, b.qualified_class,
                       (lambda b=b, shape=shape: _brush_body(
                           asm, b.name, ObjRef(shape), csg_oper=None,
                           extra=[asm._resolve_prop_value(p) for p in b.props])),
                       flags=_FLAGS_BRUSH_ACTOR)

    # --- other point actors (PlayerStart, Lights, ...) -----------------------
    # EVERY actor MUST carry `Level` -> the LevelInfo (Actors[0]).  The engine asserts
    # `GetLevel()->Actors(0)==Level` in `AActor::InitExecution` at BeginPlay and raises a
    # Critical Error otherwise ("Assertion failed: GetLevel()->Actors(0)==Level", UnScript.cpp
    # :203) — which HANGS level bring-up on the modal dialog.  The LevelInfo (Level->self) and
    # brush bodies already set it; point actors (PlayerStart, DeusExLevelInfo, Lights, ...) did
    # not.  Prepend it unless the trunk already authored a Level prop.
    for a in other_actors:
        def _point_body(a=a):
            authored = list(a.props)
            has_level = any(getattr(p, "name", p[0] if isinstance(p, tuple) else "")
                            .casefold() == "level" for p in authored)
            props = authored if has_level else \
                [Prop("Level", AW.PT_OBJECT, ObjRef(asm.levelinfo_name))] + authored
            return (AW.state_frame(asm.exports[asm.index_of[a.name]].cls)
                    + AW.write_props(asm.name_index,
                                     [asm._resolve_prop_value(p) for p in props]))
        _reserve_actor(asm, a.name, a.qualified_class, _point_body)

    # --- the built level Model -----------------------------------------------
    lm_name = "Model_Level"
    level_model.none_index = 0

    def _level_model_body():
        _patch_surf_refs(asm, level_model, csg_brushes)
        _patch_light_refs(asm, level_model, light_names)
        _patch_zone_refs(asm, level_model, zone_actors)
        return UM.write_model_body(level_model)
    asm._reserve(lm_name, "Engine.Model", _FLAGS_LOAD, _level_model_body)

    # --- the ULevel ("MyLevel") ----------------------------------------------
    def _level_body():
        refs = [asm.eref(li_name), asm.eref(default_brush_name)]
        refs += [asm.eref(b.name) for b in brush_actors if b.name != default_brush_name]
        refs += [asm.eref(a.name) for a in other_actors]
        return write_level_body(none_index=0, actor_refs=refs,
                                model_ref=asm.eref(lm_name), url=url,
                                reach_specs=reach_specs)
    asm._reserve(level_name, "Engine.Level", _FLAGS_LEVEL, _level_body)

    return asm.build()


# --- surf ref patching (§30.6: textures IMPORTED, iActor -> brush export) ---

def _patch_surf_refs(asm: _Assembler, model: UM.Model, csg_brushes) -> None:
    """Rewrite each level-Model surf's `iActor` (a raw brush index from the Rust build) to the
    brush actor's export object-ref, and its `texture_ref` to the imported texture the source
    poly names.  A no-op when `csg_brushes` is None (the M0 / Python-built path, where surfs
    already carry final refs)."""
    if not csg_brushes:
        return
    for s in model.surfs:
        bi = s.i_actor
        if not (0 <= bi < len(csg_brushes)):
            s.i_actor = 0                                # unknown owner -> none
            continue
        name, polys = csg_brushes[bi]
        s.i_actor = asm.eref(name)
        if 0 <= s.i_brush_poly < len(polys):
            tex = polys[s.i_brush_poly].texture
            if tex and "." in tex:
                s.texture_ref = asm.resolver.texture_ref(tex)


def _patch_zone_refs(asm: _Assembler, model: UM.Model, zone_actors) -> None:
    """Rewrite each zone's `ZoneActor` (Pass G) from the intermediate `{zone_number: actor_name}`
    map (built in `materialize._resolve_zone_actors` by PointRegion-resolving each ZoneInfo actor's
    Location into a zone) to the actor's export object-ref.  A zone with no ZoneInfo keeps
    `actor_ref = 0` (NULL — the engine treats it as the LevelInfo default zone).  No-op when the map
    has no ZoneInfo actors (single-zone / M0)."""
    if not zone_actors:
        return
    for z, name in zone_actors.items():
        if 0 <= z < len(model.zones) and name in asm.index_of:
            model.zones[z].actor_ref = asm.eref(name)


def _patch_light_refs(asm: _Assembler, model: UM.Model, light_names) -> None:
    """Rewrite the level-Model `lights` array (UModel+0xe4) from the bake's intermediate form
    — 0-based light INDICES + `-1` NULL terminators — to the final on-disk object-refs: a light
    index `i` -> the light actor's export ref (`asm.eref(light_names[i])`); a `-1` terminator -> 0
    (None).  A no-op when the Model carries no baked lights (unlit build).

    An index with no name RAISES rather than becoming a 0: a 0 is the run TERMINATOR, so mapping an
    unresolved index to it truncates that surface's light run and silently shifts every light after
    it off the surface. That is the failure mode of forgetting `light_names=` on a caller that passes
    a baked `world_model`, which would otherwise ship a map whose every run is one entry long."""
    if not model.lights:
        return
    names = light_names or []
    patched = []
    for r in model.lights:
        if r < 0:
            patched.append(0)                            # the run's NULL terminator
        elif r >= len(names):
            raise ValueError(
                f"baked light index {r} has no name (light_names has {len(names)}) -- the Model's "
                f"light runs and the light list are out of step")
        elif names[r] not in asm.index_of:
            raise ValueError(f"baked light {names[r]!r} is not an actor in this package")
        else:
            patched.append(asm.eref(names[r]))
    model.lights = patched


# --- body builders ---------------------------------------------------------

def _reserve_actor(asm: _Assembler, name: str, qualified_class: str, body_fn,
                   flags: int = _FLAGS_ACTOR) -> int:
    return asm._reserve(name, qualified_class, flags, body_fn)


def _levelinfo_body(asm, name, props) -> bytes:
    cls = asm.exports[asm.index_of[name]].cls
    # engine LevelInfo minimal: Level -> itself; keep any authored props too
    base = [Prop("Level", AW.PT_OBJECT, ObjRef(name))]
    resolved = [asm._resolve_prop_value(p) for p in base + list(props)]
    return AW.state_frame(cls) + AW.write_props(asm.name_index, resolved)


def _brush_body(asm, name, shape_ref: ObjRef, csg_oper, extra) -> bytes:
    cls = asm.exports[asm.index_of[name]].cls
    props = [
        Prop("Level", AW.PT_OBJECT, ObjRef(asm.levelinfo_name)),
        Prop("Brush", AW.PT_OBJECT, shape_ref),
    ]
    if csg_oper is not None:
        props.append(Prop("CsgOper", AW.PT_BYTE, csg_oper))
    props += extra
    resolved = [asm._resolve_prop_value(p) for p in props]
    return AW.state_frame(cls) + AW.write_props(asm.name_index, resolved)


def _empty_model_body(asm, polys_name: str) -> bytes:
    m = UM.Model(none_index=0)
    m.field_0x54 = asm.eref(polys_name)     # UModel.Polys ref
    return UM.write_model_body(m)
