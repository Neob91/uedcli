"""Offline native-writer round-trip: a synthesized trunk `Level` written by
`native.unbuilt.assemble_unbuilt` (pure Python, NO editor/Docker), decoded straight back with the
same offline path the post-verify uses, and asserted equal via `verify.verify_dx_matches`.

This is the fast, deterministic guard for WRITER/DECODER fidelity. Shapes exercised: a nested
struct (`MainScale`), static-array struct props (a mover's `KeyPos`/`KeyRot` with `NumKeys`>2), an
enum byte (`CsgOper`), a `None` object ref (`Skin`), an over-range `FRotator`, a non-zero
`PrePivot`, grouped (3-part) and 2-part poly textures, and two CSG brushes in a defined order plus
the writer's own builder brush (dropped by the decode). Editor-side behaviour is out of scope (that
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
    level = _synthesize_level()
    dx, _warns = _write_and_decode(level, tmp_path)
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
    assert sorted(got.actors) == ["B_add", "B_sub", "L1", "LevelInfo0", "M1"]
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
    # Both refs came back as EXPORT refs -- the decode qualifies them with the package's own name,
    # which is the `.dx`'s stem (`Map`), not the trunk's `03_NYC_UNATCOHQ`.
    p1 = dict(got.actors["PathNode1"].props)
    assert p1["previousPath"] == "PathNode'Map.PathNode0'"
    assert p1["Base"] == "Teleporter'Map.Teleporter0'"


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
        schema=mapimport.ImportSchema(resolver=_resolver),
        no_verify=False, keep_build=False, no_bsp_check=False, ignore=frozenset())

    assert r.rc == 0, r.message
    assert load_model_from_dx(out.read_bytes()).nodes, "the installed map ships no world BSP"
    assert not list((tmp_path / ".uedcli" / "tmp").glob("*.dx")), "a staging temp was stranded"
    err = capsys.readouterr().err
    assert "1 mover(s) present, geometry unbuilt" in err and "M1" in err
    assert "NOT verified: the BSP tree" in err


def test_unbuilt_world_model_is_empty_without_the_native_build(tmp_path):
    """Without `world_model` the package still ships an EMPTY world BSP -- the default
    `level materialize` path, where the editor's `MAP REBUILD` builds it."""
    from uedcli.bsp.builtmodel import load_model_from_dx
    dx, _warns = _write_and_decode(_synthesize_level(), tmp_path)
    assert load_model_from_dx(dx.read_bytes()).nodes == []
