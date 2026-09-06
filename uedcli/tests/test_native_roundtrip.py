"""Offline native-writer round-trip: a synthesized trunk `Level` written by
`native.unbuilt.assemble_unbuilt` (pure Python, NO editor/Docker), decoded straight back with the
same offline path the post-verify uses, and asserted equal via `verify.verify_dx_matches`.

This is the fast, deterministic guard for WRITER/DECODER fidelity. Shapes exercised: a nested
struct (`MainScale`), static-array struct props (a mover's `KeyPos`/`KeyRot` with `NumKeys`>2), an
enum byte (`CsgOper`), a `None` object ref (`Skin`), an over-range `FRotator`, a non-zero
`PrePivot`, grouped (3-part) and 2-part poly textures, and two CSG brushes in a defined order plus
the editor-session objects the writer synthesizes (viewport cameras, dropped by the decode). Editor-side behaviour is out of scope (that
needs the live editor container); dynamic-array serialization is covered by
`test_native_props.test_dynamic_array_is_count_then_elements` (no editable dynamic array exists in
the committed schema to drive one here).

Schema, class index and defaults come from the git-tracked `uned/UED22/*.u`; skip-gated on
`Engine.u` so a stripped checkout skips cleanly rather than failing.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from uedcli import mapimport, model
from uedcli.classdefaults import ClassDefaults
from uedcli.classindex import ClassIndex
from uedcli.native.unbuilt import assemble_unbuilt, substrate_schema
from uedcli.normalize import level_order, normalize_level
from uedcli.verify import decode_dx_level_offline, verify_dx_matches

_UED22 = Path(__file__).resolve().parents[2] / "uned" / "UED22"

pytestmark = pytest.mark.skipif(
    not (_UED22 / "Engine.u").is_file(),
    reason="committed UED22/Engine.u not present (writer schema + decode need class schemas)")


def _resolver(name: str) -> str | None:
    p = _UED22 / f"{name}.u"
    return str(p) if p.is_file() else None


def _index() -> ClassIndex:
    paths = {p.stem.casefold(): str(p) for p in _UED22.glob("*.u")}
    return ClassIndex(_paths=paths, _stems={k: Path(v).stem for k, v in paths.items()})


def _quad(texture: str, *, item: str = "Base", flags: int = 0) -> str:
    """A readable, non-degenerate (4-vertex, planar) polygon block."""
    return (f"         Begin Polygon Item={item} Texture={texture} Flags={flags}\n"
            "            Origin   +00000.000000,+00000.000000,+00000.000000\n"
            "            Normal   +00000.000000,+00000.000000,+00001.000000\n"
            "            TextureU +00001.000000,+00000.000000,+00000.000000\n"
            "            TextureV +00000.000000,+00001.000000,+00000.000000\n"
            "            Vertex   +00000.000000,+00000.000000,+00000.000000\n"
            "            Vertex   +00128.000000,+00000.000000,+00000.000000\n"
            "            Vertex   +00128.000000,+00128.000000,+00000.000000\n"
            "            Vertex   +00000.000000,+00128.000000,+00000.000000\n"
            "         End Polygon\n")


def _brush(name: str, model_name: str, csg: str, poly: str, extra: str = "") -> str:
    return (f"Begin Actor Class=Engine.Brush Name={name}\n"
            f"    CsgOper={csg}\n"
            f"{extra}"
            f"    Begin Brush Name={model_name}\n       Begin PolyList\n"
            f"{poly}"
            f"       End PolyList\n    End Brush\n"
            f"    Brush=Model'MyLevel.{model_name}'\n    Name=\"{name}\"\nEnd Actor\n")


def _synthesize_t3d() -> str:
    # Order matters: LevelInfo first (the writer forces it), then the two CSG brushes in a defined
    # order, then the point actors. One brush carries a GROUPED texture (`Pkg.Group.Name`), the other
    # a 2-part (`Pkg.Name`), to confirm each SURVIVES the write->decode round-trip; the group-vs-2-part
    # compare canonicalization itself is exercised by the unit tests in test_normalize/test_verify.
    return (
        "Begin Map\n"
        "Begin Actor Class=Engine.LevelInfo Name=LevelInfo0\n    Name=\"LevelInfo0\"\nEnd Actor\n"
        # The native writer names each CSG brush's private shape UModel `Model_<actor>`
        # (`native.assemble`), so the trunk carries the same name for a faithful round-trip.
        # B_add also carries a nested struct (`MainScale`: an FVector inside a Scale struct).
        + _brush("B_add", "Model_B_add", "CSG_Add", _quad("LUM_CoreTex.Tile.grey_stone_tile"),
                 extra="    MainScale=(Scale=(X=2.000000,Y=1.000000,Z=1.000000),"
                       "SheerRate=0.000000,SheerAxis=SHEER_ZX)\n")
        + _brush("B_sub", "Model_B_sub", "CSG_Subtract", _quad("CoreTexMetal.Area51Wall_A"))
        # A Light: enum byte carried by the brushes' CsgOper; here a None object ref (Skin), a
        # non-zero PrePivot (special-editor authored), and an over-range FRotator (Yaw wraps).
        + "Begin Actor Class=Engine.Light Name=L1\n"
          "    LightBrightness=200\n"
          "    Skin=None\n"
          "    PrePivot=(X=16.000000,Y=0.000000,Z=0.000000)\n"
          "    Rotation=(Yaw=-81920)\n"
          "    Location=(X=64.000000,Y=64.000000,Z=128.000000)\n"
          "    Name=\"L1\"\nEnd Actor\n"
        # A Mover with NumKeys>2 carrying BOTH KeyPos and KeyRot offsets (static arrays of structs).
        + "Begin Actor Class=Engine.Mover Name=M1\n"
          "    NumKeys=3\n"
          "    KeyPos(1)=(X=0.000000,Y=0.000000,Z=64.000000)\n"
          "    KeyPos(2)=(X=0.000000,Y=0.000000,Z=128.000000)\n"
          "    KeyRot(1)=(Pitch=0,Yaw=16384,Roll=0)\n"
          "    KeyRot(2)=(Pitch=0,Yaw=32768,Roll=0)\n"
          "    Location=(X=256.000000,Y=0.000000,Z=0.000000)\n"
          "    Name=\"M1\"\nEnd Actor\n"
        "End Map\n")


def _synthesize_level() -> model.Level:
    lv = model.parse_t3d(_synthesize_t3d())
    lv.order = level_order(lv)
    normalize_level(lv)
    return lv


def _write_and_decode(level, tmp_path):
    pkg_dirs = [str(_UED22)]
    dx_bytes, warnings = assemble_unbuilt(level, schema=substrate_schema(*pkg_dirs), pkg_dirs=pkg_dirs)
    dx = tmp_path / "Map.dx"
    dx.write_bytes(dx_bytes)
    return dx, warnings


def test_native_writer_roundtrip_matches_intended(tmp_path):
    from uedcli.materialize import levelinfo_first_order
    level = _synthesize_level()
    dx, _warns = _write_and_decode(level, tmp_path)
    # predict the saved Actors array the way production does: import order (LevelInfo, points,
    # brushes); the synthesized builder brush and cameras are dropped by the decode
    has_brush = {n: level.actors[n].brush is not None for n in level.order}
    classes = {n: level.actors[n].cls for n in level.order}
    level.order = levelinfo_first_order(level.order, classes, has_brush)
    result = verify_dx_matches(dx_path=str(dx), expected=level, defaults=ClassDefaults(_resolver),
                               index=_index(), schema=mapimport.ImportSchema(resolver=_resolver))
    assert result.ok, result.message


def test_native_writer_roundtrip_preserves_each_shape(tmp_path):
    """The equality check above already fails on any dropped/mangled shape, but decode the built map
    directly so a regression names the exact shape rather than a compare-view diff. Guards the
    'LOSSY, drops nested-struct/array props' failure mode."""
    dx, warnings = _write_and_decode(_synthesize_level(), tmp_path)
    got = decode_dx_level_offline(str(dx), index=_index(),
                                  schema=mapimport.ImportSchema(resolver=_resolver))
    assert warnings == []
    # the six editor viewport cameras are level content in a UED22-identical save
    assert sorted(got.actors) == ["B_add", "B_sub", "Camera10", "Camera11", "Camera6", "Camera7",
                                  "Camera8", "Camera9", "L1", "LevelInfo0", "M1"]
    # Grouped (3-part) and 2-part poly textures both survive the writer/decoder.
    assert got.actors["B_add"].brush.polys[0].texture == "LUM_CoreTex.Tile.grey_stone_tile"
    assert got.actors["B_sub"].brush.polys[0].texture == "CoreTexMetal.Area51Wall_A"
    l1 = dict(got.actors["L1"].props)
    assert l1["Skin"] == "None"                       # None object ref
    assert l1["PrePivot"] == "(X=16.000000)"          # non-zero special-editor prop
    assert l1["Rotation"] == "(Yaw=-81920)"           # over-range FRotator preserved verbatim
    m1 = dict(got.actors["M1"].props)
    assert m1["NumKeys"] == "3"                        # static-array struct props survive
    assert {"KeyPos(1)", "KeyPos(2)", "KeyRot(1)", "KeyRot(2)"} <= set(m1)
    # Nested struct: MainScale parses into the typed `main_scale` field (X=2, sheer axis kept).
    ms = got.actors["B_add"].main_scale
    assert ms is not None and float(ms.scale[0]) == 2.0 and ms.sheer_axis == "SHEER_ZX"


def test_native_world_model_ships_in_the_package_with_real_refs():
    """`assemble_unbuilt(world_model=...)` writes the NATIVELY built world BSP into the package's
    world Model export -- the editor-free build path (`materialize.build_world_model`). Pins the
    two things assembly must add on top of the raw build, which the CSG core cannot know: every
    surf's `iActor` becomes the owning brush's EXPORT ref and its `texture_ref` the source poly's
    texture IMPORT. A regression here ships a map whose surfaces are ownerless and untextured."""
    pytest.importorskip("uedcli_native")
    from uedcli.bsp.builtmodel import load_model_from_dx
    from uedcli.native.materialize import build_world_model, resolve_zone_actors

    level = _synthesize_level()
    built, csg_brushes = build_world_model(level, index=_index())
    # Movers are never carved into the world (the editor keeps a mover's brush as its own model).
    assert [n for n, _ in csg_brushes] == ["B_add", "B_sub"]
    assert built.nodes, "the native CSG core produced no BSP nodes"

    pkg_dirs = [str(_UED22)]
    dx_bytes, _warnings = assemble_unbuilt(
        level, schema=substrate_schema(*pkg_dirs), pkg_dirs=pkg_dirs, world_model=built,
        csg_brushes=csg_brushes, zone_actors=resolve_zone_actors(level, built))
    saved = load_model_from_dx(dx_bytes)

    assert (len(saved.nodes), len(saved.surfs), len(saved.points), len(saved.verts)) == \
           (len(built.nodes), len(built.surfs), len(built.points), len(built.verts))
    assert all(s.i_actor > 0 for s in saved.surfs), "a surf kept a raw brush index as its iActor"
    assert all(s.texture_ref < 0 for s in saved.surfs), "a surf did not resolve a texture import"


def test_built_path_tables_are_savepackage_count_descending():
    """The BUILT path (`world_model` given) runs the SAME two-pass as the unbuilt path, so its
    import table comes out in the editor's `SavePackage` count-DESCENDING order (the `appQsort`
    pass), not insertion order. Regression: the built branch used to emit insertion-order tables,
    diverging from every editor `MAP SAVE`. Verified by recomputing the tag-pass ref counts off the
    saved package and asserting the on-disk import order is non-increasing by count."""
    pytest.importorskip("uedcli_native")
    from uedcli.native import saveorder
    from uedcli.native.materialize import build_world_model, resolve_zone_actors
    from uedcli.upackage import _parse_package

    level = _synthesize_level()
    built, csg_brushes = build_world_model(level, index=_index())
    pkg_dirs = [str(_UED22)]
    dx_bytes, _w = assemble_unbuilt(
        level, schema=substrate_schema(*pkg_dirs), pkg_dirs=pkg_dirs, world_model=built,
        csg_brushes=csg_brushes, zone_actors=resolve_zone_actors(level, built))
    p = _parse_package(dx_bytes, "built.dx", None)
    totals = saveorder.import_totals(p, saveorder.collect(p))
    assert totals == sorted(totals, reverse=True), \
        f"built-path import table is not count-descending: {totals}"


def test_brushless_level_builds_empty_world_and_valid_package(tmp_path):
    """A brushless subset (LevelInfo-only -- the lockstep ladder's N=1) builds instead of raising.
    `build_world_model` returns an EMPTY world Model (0 nodes/surfs, NumSharedSides=4) and
    `assemble_unbuilt` ships a valid package that still reserves LevelSummary (the LevelInfo body
    refs it) -- not a `NativeBuildError` or a KeyError."""
    pytest.importorskip("uedcli_native")
    from uedcli.bsp.builtmodel import load_model_from_dx
    from uedcli.native.materialize import build_world_model, resolve_zone_actors
    from uedcli.native.pkg_write import parse_package

    t3d = ("Begin Map\n"
           "Begin Actor Class=Engine.LevelInfo Name=LevelInfo0\n    Name=\"LevelInfo0\"\nEnd Actor\n"
           "End Map\n")
    level = model.parse_t3d(t3d)
    level.order = level_order(level)
    normalize_level(level)

    built, csg_brushes = build_world_model(level, index=_index())
    assert csg_brushes == []
    assert not built.nodes and not built.surfs and not built.verts
    assert built.num_shared_sides == 4
    # The editor's empty MAP REBUILD leaves the zones array EMPTY (UNATCO N=1, Model2 = 70 bytes).
    # `build_geometry_bspcsg([])` would instead synthesize one default zone -- a native artifact we
    # must not ship; the empty world Model is a bare model, not the CSG core's output.
    assert built.zones == [] and not built.root_outside and not built.linked

    pkg_dirs = [str(_UED22)]
    dx_bytes, _warnings = assemble_unbuilt(
        level, schema=substrate_schema(*pkg_dirs), pkg_dirs=pkg_dirs, world_model=built,
        csg_brushes=csg_brushes, zone_actors=resolve_zone_actors(level, built))
    p = parse_package(dx_bytes)
    assert "LevelSummary" in {p.names[e["nm"]] for e in p.exports}
    assert load_model_from_dx(dx_bytes).nodes == []


def _room_t3d(half=(256, 256, 128)) -> str:
    """A closed subtracted box with a Light at its centre — the smallest level whose bake produces
    LIT records, so the whole lighting chain (gather -> bake -> `Model.Lights` export refs) is
    exercised offline."""
    hx, hy, hz = half
    faces = [                                            # (normal, 4 verts) — outward, CCW outside
        ((1, 0, 0), [(hx, -hy, -hz), (hx, hy, -hz), (hx, hy, hz), (hx, -hy, hz)]),
        ((-1, 0, 0), [(-hx, hy, -hz), (-hx, -hy, -hz), (-hx, -hy, hz), (-hx, hy, hz)]),
        ((0, 1, 0), [(hx, hy, -hz), (-hx, hy, -hz), (-hx, hy, hz), (hx, hy, hz)]),
        ((0, -1, 0), [(-hx, -hy, -hz), (hx, -hy, -hz), (hx, -hy, hz), (-hx, -hy, hz)]),
        ((0, 0, 1), [(-hx, -hy, hz), (hx, -hy, hz), (hx, hy, hz), (-hx, hy, hz)]),
        ((0, 0, -1), [(-hx, hy, -hz), (hx, hy, -hz), (hx, -hy, -hz), (-hx, -hy, -hz)]),
    ]
    polys = ""
    for n, verts in faces:
        # Each face needs texture axes IN ITS OWN PLANE. Reusing one pair for all six (the obvious
        # shortcut) leaves the ±X walls with TextureU along their own normal, so their texture-space
        # extent is 0, the lumel basis is singular, and the bake has no grid to walk.
        tu, tv = ((0, 1, 0), (0, 0, 1)) if n[0] else \
                 ((1, 0, 0), (0, 0, 1)) if n[1] else ((1, 0, 0), (0, 1, 0))
        polys += ("         Begin Polygon Item=Base Texture=CoreTexMetal.Area51Wall_A Flags=0\n"
                  "            Origin   +00000.000000,+00000.000000,+00000.000000\n"
                  f"            Normal   {n[0]:+013.6f},{n[1]:+013.6f},{n[2]:+013.6f}\n"
                  f"            TextureU {tu[0]:+013.6f},{tu[1]:+013.6f},{tu[2]:+013.6f}\n"
                  f"            TextureV {tv[0]:+013.6f},{tv[1]:+013.6f},{tv[2]:+013.6f}\n")
        for v in verts:
            polys += f"            Vertex   {v[0]:+013.6f},{v[1]:+013.6f},{v[2]:+013.6f}\n"
        polys += "         End Polygon\n"
    return ("Begin Map\n"
            "Begin Actor Class=Engine.LevelInfo Name=LevelInfo0\n"
            "    Name=\"LevelInfo0\"\nEnd Actor\n"
            + _brush("Room", "Model_Room", "CSG_Subtract", polys)
            + "Begin Actor Class=Engine.Light Name=Lamp\n"
              "    LightRadius=40\n"
              "    Location=(X=0.000000,Y=0.000000,Z=0.000000)\n"
              "    Name=\"Lamp\"\nEnd Actor\n"
              "Begin Actor Class=Engine.PlayerStart Name=Start0\n"
              "    Location=(X=0.000000,Y=0.000000,Z=0.000000)\n"
              "    Name=\"Start0\"\nEnd Actor\n"
              "End Map\n")


def test_gather_lights_needs_bstatic_or_bnodelete_and_reads_effective_values():
    """The editor's gather pass accepts an actor as a light on `LightType != LT_None` AND
    `bStatic || bNoDelete` (`Editor 0x100a4cc7`/`0x100a4cd4`). Dropping the second condition is what
    made native bake 7 of UNATCO's `SecurityCamera`s as lights the editor lists nowhere.

    Every value is the EFFECTIVE one, and all three are exercised as class DEFAULTS here: the
    `Engine.Light` states none of them and must still be gathered with its default radius."""
    from uedcli.classdefaults import ClassDefaults
    from uedcli.native.materialize import LightPropError, gather_lights

    def gathered(t3d_body: str):
        lv = model.parse_t3d("Begin Map\n" + t3d_body + "End Map\n")
        lv.order = level_order(lv)
        return gather_lights(lv, defaults=ClassDefaults(_resolver))

    # A bare Engine.Light: no LightType, no bStatic, no LightRadius stated -> all defaults, and it
    # participates. Its default LightRadius is what reaches the bake.
    got = gathered("Begin Actor Class=Engine.Light Name=L\n"
                   "    Location=(X=1.000000,Y=2.000000,Z=3.000000)\n    Name=\"L\"\nEnd Actor\n")
    assert [n for n, *_ in got] == ["L"]
    assert got[0][1] == (1.0, 2.0, 3.0) and got[0][2] > 0

    # Same class with bStatic AND bNoDelete turned off: no longer a light. (`Engine.Light` defaults
    # both True, which is why the SecurityCamera case needed the class-default read to see it.)
    assert gathered("Begin Actor Class=Engine.Light Name=L\n"
                    "    bStatic=False\n    bNoDelete=False\n"
                    "    Location=(X=1.000000)\n    Name=\"L\"\nEnd Actor\n") == []
    # Either flag alone is enough — the editor's test is a single `test byte [actor+0x28], 5`.
    assert len(gathered("Begin Actor Class=Engine.Light Name=L\n"
                        "    bStatic=False\n    Location=(X=1.000000)\n"
                        "    Name=\"L\"\nEnd Actor\n")) == 1
    # LT_None is not a light even when static.
    assert gathered("Begin Actor Class=Engine.Light Name=L\n"
                    "    LightType=LT_None\n    Location=(X=1.000000)\n"
                    "    Name=\"L\"\nEnd Actor\n") == []
    # An actor class with no LightType at all is simply not a light (the type's zero, not an error).
    assert gathered("Begin Actor Class=Engine.PathNode Name=P\n"
                    "    Location=(X=1.000000)\n    Name=\"P\"\nEnd Actor\n") == []
    # An actor with NO Location line takes its CLASS DEFAULT position, and must not be dropped:
    # dropping it ships a map missing that light with no signal.
    assert [n for n, *_ in gathered("Begin Actor Class=Engine.Light Name=L\n"
                                    "    Name=\"L\"\nEnd Actor\n")] == ["L"]
    # A STATED value that cannot be decoded is an error, never "not a light".
    with pytest.raises(LightPropError, match="LightType"):
        gathered("Begin Actor Class=Engine.Light Name=L\n"
                 "    LightType=LT_NoSuchType\n    Location=(X=1.000000)\n"
                 "    Name=\"L\"\nEnd Actor\n")
    # LightRadius is a BYTE and an out-of-range trunk value WRAPS on import, as the editor's would.
    assert gathered("Begin Actor Class=Engine.Light Name=L\n"
                    "    LightRadius=300\n    Location=(X=1.000000)\n"
                    "    Name=\"L\"\nEnd Actor\n")[0][2] == 44


def test_patch_light_refs_refuses_an_index_with_no_name():
    """A baked light index that `light_names` cannot resolve must RAISE. Mapping it to 0 — the run's
    NULL terminator — truncates that surface's light run and silently pushes every later light off
    the surface, which is what forgetting `light_names=` on a caller that passes a baked
    `world_model` would do."""
    from uedcli.native import assemble as ASM
    from uedcli.native import umodel as UM

    m = UM.Model()
    m.lights = [1, -1]
    with pytest.raises(ValueError, match="light index 1 has no name"):
        ASM._patch_light_refs(ASM._Assembler(68, "MyLevel"), m, ["only-one"])
    # A name that resolves but is not an actor of this package is the same class of mistake.
    m.lights = [0, -1]
    with pytest.raises(ValueError, match="not an actor in this package"):
        ASM._patch_light_refs(ASM._Assembler(68, "MyLevel"), m, ["only-one"])


def test_native_lit_room_ships_light_export_refs(tmp_path):
    """The native bake's `Model.Lights` array must reach the package as EXPORT OBJECT REFS to the
    light actors, not as the 0-based light indices the Rust core emits. Left unrewritten, index 0 is
    indistinguishable from the NULL run terminator, so the game reads a truncated light run — and a
    non-zero index resolves to whatever export happens to sit there. Pins the whole chain:
    `gather_lights` -> `build_world_model(lights=)` -> `assemble_unbuilt(light_names=)`."""
    pytest.importorskip("uedcli_native")
    from uedcli import upackage
    from uedcli.bsp.builtmodel import load_model_from_dx
    from uedcli.classdefaults import ClassDefaults
    from uedcli.native.materialize import build_world_model, gather_lights, resolve_zone_actors

    level = model.parse_t3d(_room_t3d())
    level.order = level_order(level)
    normalize_level(level)
    lights = gather_lights(level, defaults=ClassDefaults(_resolver))
    assert [n for n, *_rest in lights] == ["Lamp"], "the Light was not gathered"
    assert lights[0][2] == 40, "the stated LightRadius did not reach the bake"

    built, csg_brushes = build_world_model(level, index=_index(), lights=lights)
    assert len(built.light_map) == 6, "one record per room wall"
    assert all(r.i_light_actors >= 0 for r in built.light_map), \
        "a wall of a room with a light at its centre baked dark"
    assert built.lights == [0, -1] * 6, "pre-assembly the runs are light INDEX + -1 terminator"

    pkg_dirs = [str(_UED22)]
    dx_bytes, _warnings = assemble_unbuilt(
        level, schema=substrate_schema(*pkg_dirs), pkg_dirs=pkg_dirs, world_model=built,
        csg_brushes=csg_brushes, zone_actors=resolve_zone_actors(level, built),
        light_names=[n for n, *_rest in lights])

    dx = tmp_path / "Room.dx"
    dx.write_bytes(dx_bytes)
    saved = load_model_from_dx(dx_bytes)
    assert saved.lights[0] > 0, "the light index was not rewritten to an export ref"
    assert saved.lights == [saved.lights[0], 0] * 6, \
        "the runs are not (one export ref, NULL) per wall"
    assert upackage.load_package(str(dx)).name_of_ref(saved.lights[0]) == "Lamp"


def test_assemble_rewrites_the_levels_own_package_refs_to_mylevel(tmp_path):
    """A trunk imported from a shipped map keeps intra-level refs qualified with the ORIGINAL map's
    package name. `assemble_unbuilt` must requalify them to `MyLevel.` itself, for EVERY caller --
    left alone they assemble as a package IMPORT and the engine aborts the whole load
    (`Can't import private object Teleporter 03_NYC_UNATCOHQ.Teleporter0`), silently shipping an
    empty map. `PathNode0` is the probe that names the package; the `Teleporter` ref rides along."""
    from uedcli import upackage
    t3d = (_synthesize_t3d().replace("End Map\n", "")
           + "Begin Actor Class=Engine.PathNode Name=PathNode0\n"
             "    Location=(X=32.000000,Y=32.000000,Z=32.000000)\n"
             "    Name=\"PathNode0\"\nEnd Actor\n"
             "Begin Actor Class=Engine.Teleporter Name=Teleporter0\n"
             "    Location=(X=96.000000,Y=32.000000,Z=32.000000)\n"
             "    Name=\"Teleporter0\"\nEnd Actor\n"
             # Two self-package refs: a nav ref (the probe that names the package) and the
             # Teleporter ref that made the game refuse the whole level.
             "Begin Actor Class=Engine.PathNode Name=PathNode1\n"
             "    Location=(X=64.000000,Y=32.000000,Z=32.000000)\n"
             "    previousPath=PathNode'03_NYC_UNATCOHQ.PathNode0'\n"
             "    Base=Teleporter'03_NYC_UNATCOHQ.Teleporter0'\n"
             "    Name=\"PathNode1\"\nEnd Actor\n"
           + "End Map\n")
    level = model.parse_t3d(t3d)
    level.order = level_order(level)
    normalize_level(level)

    dx, warnings = _write_and_decode(level, tmp_path)
    assert warnings == []                    # a dropped ref would warn "which this level does not contain"
    pkg = upackage.load_package(str(dx), name="Map")
    assert "03_nyc_unatcohq" not in {pkg.names[i[3]].casefold() for i in pkg.imports}, \
        "the level's own package leaked into the package tables as an import"
    got = decode_dx_level_offline(str(dx), index=_index(),
                                  schema=mapimport.ImportSchema(resolver=_resolver))
    # `previousPath` is dropped by the WRITER (a nav-runtime field the editor resets on import;
    # its T3D line above still exercises the NAV_SELF_REF package probe), and the decode
    # additionally drops `Base` with every non-`var()`-editable prop (CPF_EDIT unset; owner ruling
    # 2026-09-02). The `pkg.imports` check above is what pins the assemble-side fix this test is
    # about (the engine load aborting on a leaked private-object import).
    p1 = dict(got.actors["PathNode1"].props)
    assert "previousPath" not in p1 and "Base" not in p1


def test_native_materialize_builds_and_verifies_a_map_with_no_editor(tmp_path, capsys):
    """`apply._materialize_native` end to end — what `UEDCLI_NATIVE_MATERIALIZE=1` runs. Drives the
    real native CSG build, the assembly, the offline post-verify and the atomic install, with no
    editor seam stubbed and no container reachable. Pins the mover warning (M1 ships unbuilt) and
    that the note says what was and was not verified."""
    pytest.importorskip("uedcli_native")
    from uedcli import apply as applymod
    from uedcli.bsp.builtmodel import load_model_from_dx
    from uedcli.normalize import canonical_actor_t3d

    level = _synthesize_level()
    result = {n: canonical_actor_t3d(a) for n, a in level.actors.items()}
    mo = applymod._materialized_order(result, level.order)
    out = tmp_path / "Built.dx"
    r = applymod._materialize_native(
        result=result, materialized_order=mo, search_dirs=[str(_UED22)], out_path=str(out),
        state_dir=tmp_path / ".uedcli", expected=applymod._expected_level(result, mo),
        defaults=ClassDefaults(_resolver), index=_index(),
        schema=mapimport.ImportSchema(resolver=_resolver), schema_resolver=_resolver,
        path_pass=None, no_verify=False, keep_build=False, no_bsp_check=False, ignore=frozenset())

    assert r.rc == 0, r.message
    built = load_model_from_dx(out.read_bytes())
    assert built.nodes, "the installed map ships no world BSP"
    assert not list((tmp_path / ".uedcli" / "tmp").glob("*.dx")), "a staging temp was stranded"
    err = capsys.readouterr().err
    # movers build their private shape models natively now -- no "geometry unbuilt" warning
    assert "geometry unbuilt" not in err
    assert "NOT verified: the BSP tree" in err
    # The lighting bake ran and its output is INTERNALLY CONSISTENT in the installed map: the level's
    # one `Engine.Light` is gathered, and every lightmappable surf links a record. (This fixture's
    # world is two coplanar quads, so the light reaches nothing and every record is dark; a real room
    # lighting its walls is covered by the Rust `single_room_light_fully_lights_all_walls`, and the
    # export-ref rewrite by `test_native_lit_room_ships_light_export_refs`.)
    assert "1 participating light(s)" in err
    assert built.light_map, "no lightmap records -- the bake did not run"
    assert {s.i_light_map for s in built.surfs} == set(range(len(built.light_map))), \
        "surf <-> record links are not a bijection onto the record array"
    for rec in built.light_map:
        if rec.i_light_actors < 0:                        # a dark record: reached by no light
            assert rec.data_offset == 0
            continue
        run = built.lights[rec.i_light_actors:]
        n = run.index(0)                                  # the NULL that ends this surf's run
        end = rec.data_offset + n * ((rec.u_size + 7) // 8) * rec.v_size
        assert end <= len(built.light_bits), "a record's bit-planes run past LightBits"


def test_unbuilt_world_model_is_empty_without_the_native_build(tmp_path):
    """Without `world_model` the package still ships an EMPTY world BSP -- the default
    `level materialize` path, where the editor's `MAP REBUILD` builds it."""
    from uedcli.bsp.builtmodel import load_model_from_dx
    dx, _warns = _write_and_decode(_synthesize_level(), tmp_path)
    assert load_model_from_dx(dx.read_bytes()).nodes == []


def test_content_brush_shape_polys_link_coplanar_faces():
    """The editor DOES run bspValidateBrush's LINK phase on an imported content brush's own model:
    coplanar same-facing/-texture/-flags faces fuse to the group master's index; a face in no group
    keeps -1. Earlier a cube-only byte-check (UNATCO/WanChai N=2, all 6-face cubes = all singletons
    -> all -1) was read as "no link phase at all"; WanChai N=16 `Model_Brush1643` disproves it -- its
    two coplanar `Side` walls store the master index, every other face -1."""
    from uedcli.model import Brush, Polygon
    from uedcli.native.unbuilt import _builder_cube_polys, _fpolys
    quad = lambda z: Polygon(texture="Pkg.Tex", item="OUTSIDE", flags=0,
                             origin=(0.0, 0.0, z), normal=(0.0, 0.0, 1.0),
                             texture_u=(1.0, 0.0, 0.0), texture_v=(0.0, 1.0, 0.0),
                             vertices=[(0.0, 0.0, z), (8.0, 0.0, z), (8.0, 8.0, z), (0.0, 8.0, z)])
    # two coplanar same-texture faces fuse to master 0; a third on a different Z plane stays -1
    brush = Brush(model_name="Model_B", polys=[quad(0.0), quad(0.0), quad(64.0)])
    assert [fp.i_link for fp in _fpolys(brush, actor="B")] == [0, 0, -1]
    # The synthesized builder cube links with master=index even for singletons (its own convention).
    assert all(fp.i_link != -1 for fp in _builder_cube_polys())


def _actor_authors_base(dx_path: str, actor_name: str) -> bool:
    """True if the SAVED actor body carries a `Base` tagged property. Reads raw tags (the offline
    decoder drops `Base` as non-`var()`-editable), skipping the StateFrame every RF_HasStack actor
    carries: Node(ci), StateNode(ci), ProbeMask(8), LatentAction(4), Offset(ci) when Node!=0."""
    from uedcli.upackage import load_package, read_compact_index, read_property_tags
    pkg = load_package(dx_path)
    i0 = next(i for i, e in enumerate(pkg.exports)
              if pkg.names[e["nm"]].casefold() == actor_name.casefold())
    e = pkg.exports[i0]
    pos, end = e["soff"], e["soff"] + e["ssize"]
    node, pos = read_compact_index(pkg.buf, pos)
    _statenode, pos = read_compact_index(pkg.buf, pos)
    pos += 12
    if node != 0:
        _offset, pos = read_compact_index(pkg.buf, pos)
    tags, _ = read_property_tags(pkg, pos, end)
    return any(t.name.casefold() == "base" for t in tags)


@pytest.mark.skipif(not (_UED22 / "DeusEx.u").is_file(),
                    reason="committed UED22/DeusEx.u not present (Deco/Effects class defaults)")
def test_base_stamp_rule_collideworld_and_ancestry(tmp_path):
    """The editor stamps `Base=LevelInfo` at spawn iff class-default bCollideWorld AND
    IsA(Decoration|Inventory|Pawn) -- no physics/bStatic clause (spike 2026-09-04-base-stamp-rule):
    - `DeusEx.Pinball` (Decoration, bCollideWorld=True, class-default PHYS_Falling) IS stamped
      (proves no physics-must-be-None clause);
    - `DeusEx.Spark` (Effects, bCollideWorld=True) is NOT (ancestry gate excludes it despite bCW);
    - `DeusEx.SecurityCamera` (Decoration, bCollideWorld=False) is NOT;
    - an actor that AUTHORS `Base` keeps its own, never a second stamp."""
    def _actor(cls: str, name: str, extra: str = "") -> str:
        return (f"Begin Actor Class={cls} Name={name}\n"
                f"    Location=(X=64.000000,Y=64.000000,Z=64.000000)\n{extra}"
                f"    Name=\"{name}\"\nEnd Actor\n")
    t3d = ("Begin Map\n"
           "Begin Actor Class=Engine.LevelInfo Name=LevelInfo0\n    Name=\"LevelInfo0\"\nEnd Actor\n"
           + _actor("DeusEx.Pinball", "Pinball0")
           + _actor("DeusEx.Spark", "Spark0")
           + _actor("DeusEx.SecurityCamera", "SecCam0")
           + _actor("DeusEx.Pinball", "PinballBased",
                    extra="    Base=LevelInfo'MyLevel.LevelInfo0'\n")
           + "End Map\n")
    level = model.parse_t3d(t3d)
    level.order = level_order(level)
    normalize_level(level)
    pkg_dirs = [str(_UED22)]
    dx_bytes, _warnings = assemble_unbuilt(level, schema=substrate_schema(*pkg_dirs),
                                           pkg_dirs=pkg_dirs)
    dx = tmp_path / "Map.dx"
    dx.write_bytes(dx_bytes)
    assert _actor_authors_base(str(dx), "Pinball0")       # Decoration + bCollideWorld -> stamped
    assert not _actor_authors_base(str(dx), "Spark0")     # Effects: bCW True but ancestry excludes
    assert not _actor_authors_base(str(dx), "SecCam0")    # Decoration but bCollideWorld=False
    assert _actor_authors_base(str(dx), "PinballBased")   # authored Base flows through (not dropped)


def test_brush_bdynamiclight_is_dropped(tmp_path):
    """The editor resets `bDynamicLight` to the class default on a brush at MAP IMPORT and omits it
    from the save; a trunk-authored `bDynamicLight=True` on a brush must not reach the built map
    (byte-verified, UNATCO Brush74 at N=2)."""
    t3d = ("Begin Map\n"
           "Begin Actor Class=Engine.LevelInfo Name=LevelInfo0\n    Name=\"LevelInfo0\"\nEnd Actor\n"
           + _brush("B1", "Model_B1", "CSG_Add", _quad("LUM_CoreTex.Tile.grey_stone_tile"),
                    extra="    bDynamicLight=True\n")
           + "End Map\n")
    level = model.parse_t3d(t3d)
    level.order = level_order(level)
    normalize_level(level)
    dx, warnings = _write_and_decode(level, tmp_path)
    got = decode_dx_level_offline(str(dx), index=_index(),
                                  schema=mapimport.ImportSchema(resolver=_resolver))
    assert "bDynamicLight" not in dict(got.actors["B1"].props)


def _fp(normal, base, texture_ref=1, tu=(0.0, 1.0, 0.0), tv=(0.0, 0.0, 1.0), flags=0):
    from uedcli.native.actor_write import FPoly
    return FPoly(verts=[(0.0, 0.0, 0.0)], base=base, normal=normal,
                 texture_u=tu, texture_v=tv, poly_flags=flags, texture_ref=texture_ref)


def test_content_brush_ilink_link_phase_stores_editor_convention():
    """`_assign_content_ilinks` mirrors how the editor STORES `bspValidateBrush`'s link phase on an
    imported content brush's own model: coplanar same-facing/-texture/-flags faces fuse to the group
    master's index; a poly in NO group keeps -1 (not its own index). This is what made WanChai N=16
    diverge -- `Brush1643`'s two coplanar `Side` walls are the first real groups; every earlier
    brush is a 6-face cube (all singletons -> all -1)."""
    from uedcli.native.unbuilt import _assign_content_ilinks
    polys = [
        _fp((1.0, 0.0, 0.0), (0.0, 0.0, 0.0)),        # 0: master of the +X group
        _fp((0.0, 1.0, 0.0), (0.0, 0.0, 0.0)),        # 1: +Y singleton -> -1
        _fp((1.0, 0.0, 0.0), (0.0, 10.0, 0.0)),       # 2: coplanar with 0 -> links to 0
        _fp((1.0, 0.0, 0.0), (0.0, 0.0, 0.0), texture_ref=2),  # 3: coplanar but other texture -> -1
    ]
    _assign_content_ilinks(polys)
    assert [p.i_link for p in polys] == [0, -1, 0, -1]


def test_world_soup_item_defaults_to_none_not_outside():
    """A world-soup fragment inherits its SOURCE brush poly's `Item`: an authored `OUTSIDE`/`Rise`
    keeps its label, but a source poly with NO authored item -> the `None` FName, NOT `OUTSIDE`.
    Native's old hardcoded `OUTSIDE` default wrote 174x `OUTSIDE` on OceanLab N=3 where the editor
    writes 168x `None` + 6x `OUTSIDE` (the 6 from a cube brush's authored faces)."""
    from types import SimpleNamespace
    from uedcli.native.unbuilt import _world_soup_fpolys

    src = [SimpleNamespace(item="OUTSIDE", texture=None),   # authored
           SimpleNamespace(item=None, texture=None)]        # unlabeled -> None
    csg_brushes = [("Brush0", src)]

    def entry(ibp):
        return ([0.0] * 9, (0, 0, 0), (0, 0, 1), (1, 0, 0), (0, 1, 0), 0, 0, ibp, -1, (0, 0))

    wm = SimpleNamespace(world_soup=[entry(0), entry(1), entry(99)])  # 99 = out-of-range src
    asm = SimpleNamespace(eref=lambda name: 7)
    out = _world_soup_fpolys(asm, wm, csg_brushes, lambda t: 0)
    assert [fp.item for fp in out] == ["OUTSIDE", None, None]


def test_precompute_sphere_filter_marks_a_branching_tree_like_the_recursion():
    """`UModel::PrecomputeSphereFilter` recurses into the FIRST child and continues down the second
    (`Engine.dll 0x101aefb0`); the port turns that into a LIFO stack. NYC_Bar N=59's world tree is a
    6-node chain whose first child is always -1, so nothing there walks the deferred branch at all
    -- a dropped subtree would go unnoticed."""
    from uedcli.native.umodel import BspNode
    from uedcli.native.unbuilt import _precompute_sphere_filter

    def tree():
        # A straddling root over two straddling children, each with a marked leaf pair; every node
        # shares a plane the sphere straddles or clears, so both branches are walked.
        planes = [(0, 0, 1, 0), (0, 0, 1, 0), (0, 0, 1, 900), (0, 0, 1, -900), (0, 0, 1, 0),
                  (0, 0, 1, 900), (0, 0, 1, -900)]
        kids = [(1, 4), (2, 3), (-1, -1), (-1, -1), (5, 6), (-1, -1), (-1, -1)]
        return [BspNode(plane=p, i_front=f, i_back=b) for p, (f, b) in zip(planes, kids)]

    def reference(nodes, i, center, radius, seen):
        while i != -1:
            n = nodes[i]
            seen.append(i)
            n.node_flags &= 0x3F
            d = n.plane[0] * center[0] + n.plane[1] * center[1] + n.plane[2] * center[2] - n.plane[3]
            if -radius > d:
                n.node_flags |= 0x80
                i = n.i_front
            elif d > radius:
                n.node_flags |= 0x40
                i = n.i_back
            else:
                if n.i_front != -1:
                    reference(nodes, n.i_front, center, radius, seen)
                i = n.i_back

    center, radius = (0.0, 0.0, 0.0), 10.0
    want, seen = tree(), []
    reference(want, 0, center, radius, seen)
    got = tree()
    _precompute_sphere_filter(got, center, radius)
    assert seen == [0, 1, 2, 3, 4, 5, 6], "the reference must walk the front subtree first"
    assert [n.node_flags for n in want] == [0, 0, 0x80, 0x40, 0, 0x80, 0x40], \
        "the fixture must actually mark both deferred subtrees"
    assert [n.node_flags for n in got] == [n.node_flags for n in want]


def test_zone_actor_binding_follows_actor_order_not_the_name_keyed_dict():
    """Two ZoneInfos in the same zone: the EARLIER one in `Level.Actors` order owns it.

    `resolve_zone_actors` used to walk `level.actors`, a name-keyed dict, so `ZoneInfo17` sorted
    ahead of `ZoneInfo5` and won a zone UED22 gives to `ZoneInfo5` (NYC_Bar N=70: every actor's
    `Region.Zone` and the world `Model`'s `Zones[1].ZoneActor` followed the wrong one)."""
    pytest.importorskip("uedcli_native")
    from uedcli.native.materialize import build_world_model, resolve_zone_actors

    zone_infos = "".join(
        f"Begin Actor Class=Engine.ZoneInfo Name={n}\n"
        f"    Location=(X={x}.000000,Y=0.000000,Z=0.000000)\n"
        f'    Name="{n}"\nEnd Actor\n'
        for n, x in (("ZoneInfo5", 16), ("ZoneInfo17", -16)))
    level = model.parse_t3d(_room_t3d().replace("End Map\n", zone_infos + "End Map\n"))
    level.order = level_order(level)
    normalize_level(level)
    # The dict is name-keyed, so it hands out ZoneInfo17 first; the trunk order does not.
    assert list(level.actors).index("ZoneInfo17") < list(level.actors).index("ZoneInfo5")
    assert level.order.index("ZoneInfo5") < level.order.index("ZoneInfo17")

    built, _csg = build_world_model(level, index=_index())
    assert resolve_zone_actors(level, built) == {1: "ZoneInfo5"}
