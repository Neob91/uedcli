import pytest

from uedcli.geometry import GeometryError
from uedcli.model import Actor, Brush, Level, Polygon
from uedcli.surface import (apply_surface_edit, encode_flags, parse_poly_selector,
                            parse_texture_ref, resolve_polys)


def _D(*xyz):
    from decimal import Decimal
    return tuple(Decimal(str(c)) for c in xyz)


def _square(z):
    return [_D(0, 0, z), _D(10, 0, z), _D(10, 10, z), _D(0, 10, z)]


def _quad(**kwargs):
    return Polygon(vertices=_square(kwargs.pop("z", 0)), **kwargs)


def _brush_actor(name: str, polys: list[Polygon]) -> Actor:
    a = Actor(name=name, cls="Brush")
    a.brush = Brush(model_name=f"{name}Model", polys=polys)
    return a


def _level_with(*actors: Actor) -> Level:
    lvl = Level()
    for a in actors:
        lvl.actors[a.name] = a
    lvl.order = [a.name for a in actors]
    return lvl


# --- encode_flags ------------------------------------------------------------

def test_encode_flags_ors_the_named_bits():
    assert encode_flags(["translucent", "unlit"]) == 0x4 | 0x400000


def test_encode_flags_is_case_insensitive():
    # Board bug 4: the docs capitalize flag names (`Unlit`/`Masked`); those must work, not only the
    # lowercase spelling. All three spellings encode to the same bits.
    assert encode_flags(["Unlit", "Masked"]) == 0x400000 | 0x2
    assert encode_flags(["UNLIT"]) == encode_flags(["unlit"]) == 0x400000


def test_encode_flags_rejects_an_unknown_name():
    with pytest.raises(ValueError, match="unknown flag name.*bogus"):
        encode_flags(["bogus"])


def test_encode_flags_rejects_none_and_hex_literal():
    with pytest.raises(ValueError, match="unknown flag name"):
        encode_flags(["none"])
    with pytest.raises(ValueError, match="unknown flag name"):
        encode_flags(["0x4"])


# --- parse_poly_selector ------------------------------------------------------

def test_parse_poly_selector_splits_on_the_last_colon():
    assert parse_poly_selector("Wall1:3,5") == ("Wall1", "3,5")


def test_parse_poly_selector_handles_a_brush_name_containing_a_colon():
    assert parse_poly_selector("we:ird:all") == ("we:ird", "all")


def test_parse_poly_selector_rejects_a_token_with_no_colon():
    with pytest.raises(ValueError, match="BRUSH:SELECTOR"):
        parse_poly_selector("Wall1")


def test_parse_poly_selector_rejects_a_missing_brush_name():
    with pytest.raises(ValueError, match="missing a brush name"):
        parse_poly_selector(":all")


# --- resolve_polys -------------------------------------------------------------

def test_resolve_polys_all_returns_every_index():
    actor = _brush_actor("B1", [_quad(), _quad(), _quad()])
    assert resolve_polys("all", actor, brush_name="B1") == {0, 1, 2}


def test_resolve_polys_comma_list_returns_those_indices():
    actor = _brush_actor("B1", [_quad(), _quad(), _quad()])
    assert resolve_polys("0,2", actor, brush_name="B1") == {0, 2}


def test_resolve_polys_rejects_a_non_brush_actor():
    actor = Actor(name="L1", cls="Light")
    with pytest.raises(ValueError, match="'L1' is not a brush"):
        resolve_polys("all", actor, brush_name="L1")


def test_resolve_polys_rejects_an_empty_selector():
    actor = _brush_actor("B1", [_quad()])
    with pytest.raises(ValueError, match="empty selector for 'B1'"):
        resolve_polys("", actor, brush_name="B1")


def test_resolve_polys_rejects_an_out_of_range_index():
    actor = _brush_actor("B1", [_quad()])
    with pytest.raises(ValueError, match="'B1': poly index 5 out of range"):
        resolve_polys("5", actor, brush_name="B1")


def test_resolve_polys_rejects_a_non_numeric_index():
    actor = _brush_actor("B1", [_quad()])
    with pytest.raises(ValueError, match="bad poly index 'x'"):
        resolve_polys("x", actor, brush_name="B1")


def test_resolve_polys_all_on_a_brush_with_no_polys_is_an_error():
    actor = _brush_actor("B1", [])
    with pytest.raises(ValueError, match="'B1' has no polys to select"):
        resolve_polys("all", actor, brush_name="B1")


# --- parse_texture_ref ---------------------------------------------------------

def test_parse_texture_ref_returns_the_package():
    assert parse_texture_ref("Engine.DefaultTexture") == "Engine"
    assert parse_texture_ref("DeusExDeco.Textures.Wood") == "DeusExDeco"


def test_parse_texture_ref_rejects_a_bare_name():
    with pytest.raises(ValueError, match="must be qualified"):
        parse_texture_ref("Wood")


def test_parse_texture_ref_rejects_mylevel():
    with pytest.raises(ValueError, match="MyLevel"):
        parse_texture_ref("MyLevel.Wood")


# --- apply_surface_edit ---------------------------------------------------------

def test_apply_surface_edit_requires_at_least_one_attribute():
    lvl = _level_with(_brush_actor("B1", [_quad()]))
    with pytest.raises(ValueError, match="at least one of"):
        apply_surface_edit(lvl, ["B1:all"])


def test_apply_surface_edit_sets_texture_on_selected_polys_only():
    p0, p1 = _quad(), _quad()
    lvl = _level_with(_brush_actor("B1", [p0, p1]))
    touched = apply_surface_edit(lvl, ["B1:0"], texture_ref="DeusExDeco.Textures.Wood")
    assert touched == ["B1"]
    assert p0.texture == "DeusExDeco.Textures.Wood"
    assert p1.texture is None


def test_apply_surface_edit_add_and_remove_flags_preserve_other_bits():
    p = _quad(flags=0x8)                  # notsolid, untouched
    lvl = _level_with(_brush_actor("B1", [p]))
    apply_surface_edit(lvl, ["B1:all"], add_flags=["translucent"], remove_flags=["unlit"])
    assert p.flags == 0x8 | 0x4           # notsolid preserved + translucent added


def test_apply_surface_edit_pan_to_sets_absolute_pan():
    p = _quad()
    lvl = _level_with(_brush_actor("B1", [p]))
    apply_surface_edit(lvl, ["B1:all"], pan_to=(10, 20))
    assert p.pan == (10, 20)


def test_apply_surface_edit_pan_by_is_relative_to_zero_when_pan_absent():
    p = _quad()
    lvl = _level_with(_brush_actor("B1", [p]))
    apply_surface_edit(lvl, ["B1:all"], pan_by=(5, -3))
    assert p.pan == (5, -3)


def test_apply_surface_edit_pan_by_accumulates_on_existing_pan():
    p = _quad(pan=(10, 10))
    lvl = _level_with(_brush_actor("B1", [p]))
    apply_surface_edit(lvl, ["B1:all"], pan_by=(5, -3))
    assert p.pan == (15, 7)


def test_apply_surface_edit_overlapping_targets_edit_each_surface_once():
    p = _quad()
    lvl = _level_with(_brush_actor("B1", [p]))
    apply_surface_edit(lvl, ["B1:all", "B1:0"], pan_by=(1, 1))
    assert p.pan == (1, 1)             # not (2, 2) -- the dup target didn't double-apply


def test_apply_surface_edit_touches_multiple_brushes():
    pA, pB = _quad(), _quad()
    lvl = _level_with(_brush_actor("BrushA", [pA]), _brush_actor("BrushB", [pB]))
    touched = apply_surface_edit(lvl, ["BrushA:all", "BrushB:all"],
                                 texture_ref="Engine.DefaultTexture")
    assert touched == ["BrushA", "BrushB"]
    assert pA.texture == pB.texture == "Engine.DefaultTexture"


def test_apply_surface_edit_rejects_a_bare_texture_ref_before_mutating():
    p = _quad()
    lvl = _level_with(_brush_actor("B1", [p]))
    with pytest.raises(ValueError, match="must be qualified"):
        apply_surface_edit(lvl, ["B1:all"], texture_ref="Wood")
    assert p.texture is None


def test_apply_surface_edit_rejects_an_unknown_brush():
    lvl = _level_with(_brush_actor("B1", [_quad()]))
    with pytest.raises(ValueError, match="unknown brush 'NoSuch'"):
        apply_surface_edit(lvl, ["NoSuch:all"], texture_ref="Engine.DefaultTexture")


def test_apply_surface_edit_is_all_or_nothing_across_targets():
    p = _quad()
    lvl = _level_with(_brush_actor("B1", [p]))
    with pytest.raises(ValueError, match="unknown brush 'NoSuch'"):
        apply_surface_edit(lvl, ["B1:all", "NoSuch:all"], texture_ref="Engine.DefaultTexture")
    assert p.texture is None           # B1's valid target was never applied either


def test_apply_surface_edit_validates_the_touched_brush():
    # A degenerate (coincident-vertex) poly should still fail validate_brush even though
    # surface edits don't move vertices -- run for uniformity/safety per the spec.
    bad = Polygon(vertices=[_D(0, 0, 0)] * 4)
    lvl = _level_with(_brush_actor("B1", [bad]))
    with pytest.raises(GeometryError):
        apply_surface_edit(lvl, ["B1:all"], texture_ref="Engine.DefaultTexture")


# ── Case-insensitive brush-name resolution in apply_surface_edit ─────────────


def test_it_poly_set_resolves_brush_name_case_insensitively():
    p = _quad()
    lvl = _level_with(_brush_actor("Brush1", [p]))
    # Wrong-case brush name should succeed identically to the canonical form
    result = apply_surface_edit(lvl, ["brush1:0"], texture_ref="Engine.DefaultTexture")
    assert p.texture == "Engine.DefaultTexture"
    assert result == ["Brush1"]         # returned touched list uses canonical name


def test_it_poly_set_errors_on_missing_brush():
    lvl = _level_with(_brush_actor("Brush1", [_quad()]))
    with pytest.raises(ValueError) as exc_info:
        apply_surface_edit(lvl, ["NoSuch:0", "AlsoMissing:0"],
                           texture_ref="Engine.DefaultTexture")
    msg = str(exc_info.value)
    # First-offender behavior: NoSuch is reported, AlsoMissing is NOT
    assert "NoSuch" in msg
    assert "AlsoMissing" not in msg
