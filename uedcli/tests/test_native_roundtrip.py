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
