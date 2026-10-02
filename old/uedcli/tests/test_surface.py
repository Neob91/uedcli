import pytest

from uedcli.geometry import GeometryError
from uedcli.model import Actor, Brush, Level, Polygon
from uedcli.query import PF_NAMES, decode_flags
from uedcli.surface import (apply_pan, apply_rotate, apply_scale, apply_surface_edit, encode_flags,
                            parse_poly_selector, parse_texture_ref, resolve_polys,
                            resolve_targets)


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


@pytest.mark.parametrize("name,bit", [
    ("bigwavy", 0x1000), ("smallwavy", 0x2000), ("lowshadowdetail", 0x8000),
    ("brightcorners", 0x80000), ("highshadowdetail", 0x800000),
])
def test_encode_flags_maps_the_new_names_to_their_bits(name, bit):
    assert encode_flags([name]) == bit


@pytest.mark.parametrize("bit,name", PF_NAMES)
def test_single_flag_round_trips_name_to_bit_to_name(bit, name):
    # Every settable name encodes to a single bit that decodes back to exactly that name — so the
    # five newly-added flags decode as a name, not a hex tail. Each bit is a distinct power of two.
    assert bin(bit).count("1") == 1
    assert encode_flags([name]) == bit
    assert decode_flags(bit) == [name]


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


def test_resolve_polys_rejects_a_doubly_signed_index():
    # `--3` used to slip past the guard (`.lstrip("-")` strips every leading `-`) and reach
    # `int()` raw, escaping as a bare ValueError naming neither the brush nor the verb.
    actor = _brush_actor("B1", [_quad()])
    with pytest.raises(ValueError, match=r"'B1': bad poly index '--3'"):
        resolve_polys("--3", actor, brush_name="B1")


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


def test_apply_surface_edit_requires_at_least_one_attribute_and_names_the_three():
    # Pan left this verb, so the "at least one of" message names three flags, not five.
    lvl = _level_with(_brush_actor("B1", [_quad()]))
    with pytest.raises(ValueError, match="at least one of") as exc:
        apply_surface_edit(lvl, ["B1:all"])
    msg = str(exc.value)
    assert "--texture/--add-flag/--remove-flag is required" in msg
    assert "pan" not in msg.lower()


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


# --- resolve_targets (the shared per-face resolution behind stdout's BRUSH:idx lines) ----------

def test_resolve_targets_expands_all_and_sorts_by_brush_then_index():
    lvl = _level_with(_brush_actor("BrushB", [_quad(), _quad()]),
                      _brush_actor("BrushA", [_quad(), _quad(), _quad()]))
    assert resolve_targets(lvl, ["BrushB:all", "BrushA:2,0"]) == [
        ("BrushA", 0), ("BrushA", 2), ("BrushB", 0), ("BrushB", 1)]


def test_resolve_targets_canonicalizes_the_brush_name_and_dedupes():
    lvl = _level_with(_brush_actor("Wall", [_quad(), _quad()]))
    # A case-folded spelling and an overlapping selector collapse onto the canonical pair set —
    # which is why the CLI cannot just echo the caller's tokens back on stdout.
    assert resolve_targets(lvl, ["wall:all", "WALL:1"]) == [("Wall", 0), ("Wall", 1)]


def test_resolve_targets_rejects_a_bare_brush_name():
    # The per-face verbs take BRUSH:SELECTOR only; a bare name is `align`'s grammar, not theirs.
    lvl = _level_with(_brush_actor("Wall", [_quad()]))
    with pytest.raises(ValueError, match="BRUSH:SELECTOR"):
        resolve_targets(lvl, ["Wall"])


def test_resolve_targets_rejects_an_unknown_brush():
    lvl = _level_with(_brush_actor("Wall", [_quad()]))
    with pytest.raises(ValueError, match="unknown brush 'NoSuch'"):
        resolve_targets(lvl, ["NoSuch:all"])


# --- apply_pan -----------------------------------------------------------------

def test_apply_pan_requires_exactly_one_of_to_or_by():
    lvl = _level_with(_brush_actor("B1", [_quad()]))
    for kwargs in ({}, {"pan_to": (1, 1), "pan_by": (1, 1)}):
        with pytest.raises(ValueError, match="exactly one of --to/--by"):
            apply_pan(lvl, ["B1:all"], **kwargs)


def test_apply_pan_to_sets_absolute_pan():
    p = _quad()
    lvl = _level_with(_brush_actor("B1", [p]))
    assert apply_pan(lvl, ["B1:all"], pan_to=(10, 20)) == ["B1"]
    assert p.pan == (10, 20)


def test_apply_pan_by_is_relative_to_zero_when_pan_absent():
    p = _quad()
    lvl = _level_with(_brush_actor("B1", [p]))
    apply_pan(lvl, ["B1:all"], pan_by=(5, -3))
    assert p.pan == (5, -3)


def test_apply_pan_by_accumulates_on_existing_pan():
    p = _quad(pan=(10, 10))
    lvl = _level_with(_brush_actor("B1", [p]))
    apply_pan(lvl, ["B1:all"], pan_by=(5, -3))
    assert p.pan == (15, 7)


def test_apply_pan_overlapping_targets_edit_each_surface_once():
    p = _quad()
    lvl = _level_with(_brush_actor("B1", [p]))
    apply_pan(lvl, ["B1:all", "B1:0"], pan_by=(1, 1))
    assert p.pan == (1, 1)             # not (2, 2) -- the dup target didn't double-apply


def test_apply_pan_to_zero_emits_no_pan_line_at_all():
    # Asserted at the EMITTED-TEXT level, not on the model: `emit_polygon` skips a (0,0) pan and
    # `brush poly list` keys off `pan is None`, so only the round trip proves the two agree that a
    # cleared pan is a face that was never panned. (unrealed/t3d.md "A poly sub-field has NO class
    # default" — a redundant `Pan U=0 V=0` aborts `level materialize`.)
    from uedcli.normalize import canonical_actor_t3d
    a = _brush_actor("B1", [_quad(pan=(7, 3))])
    lvl = _level_with(a)
    apply_pan(lvl, ["B1:all"], pan_to=(0, 0))
    assert "Pan" not in canonical_actor_t3d(a)


def test_apply_pan_to_a_non_zero_value_reaches_the_trunk():
    # The counterpart: a dialled-in pan is real content and must be serialized. `pan` is now the
    # only verb that writes a non-zero pan, so this is what guards `emit_polygon`'s non-zero half.
    from uedcli.normalize import canonical_actor_t3d
    a = _brush_actor("B1", [_quad()])
    lvl = _level_with(a)
    apply_pan(lvl, ["B1:all"], pan_to=(7, 3))
    assert "Pan      U=7 V=3" in canonical_actor_t3d(a)


def test_apply_pan_leaves_the_texture_frame_alone():
    p = _quad(origin=(1.0, 2.0, 3.0), texture_u=(1.0, 0.0, 0.0), texture_v=(0.0, 1.0, 0.0))
    lvl = _level_with(_brush_actor("B1", [p]))
    apply_pan(lvl, ["B1:all"], pan_by=(4, 4))
    assert p.origin == (1.0, 2.0, 3.0)
    assert p.texture_u == (1.0, 0.0, 0.0) and p.texture_v == (0.0, 1.0, 0.0)


# --- apply_rotate / apply_scale: shared fixtures --------------------------------
#
# A `+Z` face wound CCW seen from above, so its Newell normal is exactly +Z. The frame is stored in
# the brush's LOCAL space, which is where both verbs work.

_PLUS_Z = [_D(0, 0, 0), _D(10, 0, 0), _D(10, 10, 0), _D(0, 10, 0)]
_PLUS_Z_CENTROID = (5.0, 5.0, 0.0)

# A 60-degree SKEWED frame: TextureV is not perpendicular to TextureU. T3D permits this, and it is
# the case the centroid re-anchor's Gram solve exists for.
_SKEW_V = (0.5, 0.8660254037844386, 0.0)


def _face(**kwargs):
    kwargs.setdefault("origin", (0.0, 0.0, 0.0))
    kwargs.setdefault("texture_u", (1.0, 0.0, 0.0))
    kwargs.setdefault("texture_v", (0.0, 1.0, 0.0))
    return Polygon(vertices=list(_PLUS_Z), **kwargs)


_ALL_ZERO = "+00000.000000,+00000.000000,+00000.000000"


def _written_axes(actor) -> list[str]:
    """The `TextureU`/`TextureV` lines of `actor` as the trunk actually serializes them.

    Scoped to those two fields deliberately: a face's first VERTEX is legitimately at the origin, so
    searching the whole actor for an all-zero triple matches a perfectly healthy brush."""
    from uedcli.normalize import canonical_actor_t3d
    return [ln for ln in canonical_actor_t3d(actor).splitlines()
            if "TextureU" in ln or "TextureV" in ln]


def _cross(a, b):
    return (a[1] * b[2] - a[2] * b[1], a[2] * b[0] - a[0] * b[2], a[0] * b[1] - a[1] * b[0])


def _uv(poly, point):
    """The face's own UV convention: U = (P - Origin)*TextureU + PanU."""
    o, tu, tv = poly.origin, poly.texture_u, poly.texture_v
    d = tuple(float(point[i]) - float(o[i]) for i in range(3))
    pan = poly.pan or (0, 0)
    return (sum(d[i] * float(tu[i]) for i in range(3)) + pan[0],
            sum(d[i] * float(tv[i]) for i in range(3)) + pan[1])


# --- apply_rotate ----------------------------------------------------------------

def _csg_brush_actor(name: str, polys, oper: str | None):
    """A brush actor carrying an explicit `CsgOper` prop (or none at all when `oper is None`)."""
    a = _brush_actor(name, polys)
    if oper is not None:
        a.props.append(("CsgOper", oper))
    return a


@pytest.mark.parametrize("oper,visible_sign", [
    ("CSG_Add", +1.0),          # the surface an author sees is the outside of the solid
    ("CSG_Subtract", -1.0),     # a room: the surface an author sees is the inside
    (None, +1.0),               # absent reads as CSG_Add, as everywhere else in the codebase
])
def test_apply_rotate_turns_against_the_VISIBLE_surface_normal(oper, visible_sign):
    """The owner ruling's own acceptance test (2026-07-27), stated as the ruling states it.

    The same `--by 16384` must turn the texture **the same way as seen from outside each face** on an
    additive and on a subtractive brush. Both brushes here have IDENTICAL geometry, so they share one
    winding normal `+Z`; what differs is which side an author is looking from — the outside of the
    solid on an add, the inside of the room on a subtract.

    So the expectation is computed from the VISIBLE normal rather than restated as a literal: a
    quarter turn takes each axis to `v̂ × axis`, and `v̂` is `+Z` for the add and `−Z` for the
    subtract. That is one rule in the viewer's frame, which is exactly the ruling's claim; before the
    ruling the subtractive case turned the other way.
    """
    p = _face()
    lvl = _level_with(_csg_brush_actor("B1", [p], oper))
    apply_rotate(lvl, ["B1:all"], by_uu=16384)
    visible = (0.0, 0.0, visible_sign)
    assert p.texture_u == pytest.approx(_cross(visible, (1.0, 0.0, 0.0)))
    assert p.texture_v == pytest.approx(_cross(visible, (0.0, 1.0, 0.0)))


def test_apply_rotate_add_and_subtract_turn_in_OPPOSITE_world_directions():
    """The same statement read the other way round, because it is the half that can regress silently.

    Turning "the same way as seen from outside" means turning the OPPOSITE way in world coordinates,
    since the two viewers stand on opposite sides of the face. An implementation that dropped the
    flip would make these two equal, and the test above alone would still pass for the add case.
    """
    added, carved = _face(), _face()
    apply_rotate(_level_with(_csg_brush_actor("B1", [added], "CSG_Add")), ["B1:all"], by_uu=16384)
    apply_rotate(_level_with(_csg_brush_actor("B1", [carved], "CSG_Subtract")), ["B1:all"],
                 by_uu=16384)
    assert added.texture_u == pytest.approx(tuple(-c for c in carved.texture_u))
    assert added.texture_v == pytest.approx(tuple(-c for c in carved.texture_v))


def test_apply_rotate_on_a_subtractive_brush_stays_exact_at_a_quarter_turn():
    # The flip must not cost the exact path its exactness: negating an exact unit normal is exact,
    # so the cross products still land on clean components rather than float dust.
    p = _face()
    lvl = _level_with(_csg_brush_actor("B1", [p], "CSG_Subtract"))
    apply_rotate(lvl, ["B1:all"], by_uu=16384)
    assert p.texture_u == (0.0, -1.0, 0.0)
    assert p.texture_v == (1.0, 0.0, 0.0)


@pytest.mark.parametrize("oper", ["CSG_Intersect", "CSG_Deintersect", "CSG_Active", "nonsense"])
def test_apply_rotate_refuses_a_csgoper_that_is_neither_add_nor_subtract(oper):
    # The turn direction is defined against the VISIBLE surface normal, and these ops have no
    # defined inside or outside for that to mean anything. Guessing a sign is the worst option
    # available: a wrong turn is silent and reads as the author's own mistake.
    p = _face()
    lvl = _level_with(_csg_brush_actor("B1", [p], oper))
    with pytest.raises(ValueError, match=f"CsgOper={oper!r}"):
        apply_rotate(lvl, ["B1:all"], by_uu=16384)
    assert p.texture_u == (1.0, 0.0, 0.0)               # nothing was written


def test_apply_rotate_quarter_turn_is_exact_on_an_axis_aligned_face():
    # The spec's authoritative sign rule, stated at the AXIS level so a test can assert it:
    # on a +Z face with TextureU=+X, TextureV=+Y, --by 16384 yields TextureU=+Y, TextureV=-X
    # (Z x X = +Y, Z x Y = -X). EXACT -- no float dust, or every quarter turn pollutes the trunk.
    p = _face()
    lvl = _level_with(_brush_actor("B1", [p]))
    assert apply_rotate(lvl, ["B1:all"], by_uu=16384) == ["B1"]
    assert p.texture_u == (0.0, 1.0, 0.0)
    assert p.texture_v == (-1.0, 0.0, 0.0)


@pytest.mark.parametrize("by_uu,tu,tv", [
    (32768, (-1.0, 0.0, 0.0), (0.0, -1.0, 0.0)),        # 180 degrees: k = 2
    (49152, (0.0, -1.0, 0.0), (1.0, 0.0, 0.0)),         # 270 degrees: k = 3
])
def test_apply_rotate_half_and_three_quarter_turns_are_the_quarter_turn_repeated(by_uu, tu, tv):
    p = _face()
    lvl = _level_with(_brush_actor("B1", [p]))
    apply_rotate(lvl, ["B1:all"], by_uu=by_uu)
    assert p.texture_u == tu and p.texture_v == tv


def test_apply_rotate_a_negative_angle_equals_its_positive_complement():
    # Python's floor division and modulo already give the right non-negative k for a negative
    # angle; this pins that -16384 and 49152 are the same turn rather than differing by a sign slip.
    neg, pos = _face(), _face()
    apply_rotate(_level_with(_brush_actor("B1", [neg])), ["B1:all"], by_uu=-16384)
    apply_rotate(_level_with(_brush_actor("B1", [pos])), ["B1:all"], by_uu=49152)
    assert neg.texture_u == pos.texture_u and neg.texture_v == pos.texture_v


def test_apply_rotate_preserves_the_centroids_uv_on_an_orthogonal_frame():
    p = _face(origin=(3.0, -2.0, 0.0), texture_u=(0.25, 0.0, 0.0), texture_v=(0.0, 0.5, 0.0))
    lvl = _level_with(_brush_actor("B1", [p]))
    before = _uv(p, _PLUS_Z_CENTROID)
    apply_rotate(lvl, ["B1:all"], by_uu=16384)
    after = _uv(p, _PLUS_Z_CENTROID)
    assert after == pytest.approx(before, abs=1e-9)


def test_apply_rotate_preserves_the_centroids_uv_on_a_skewed_frame():
    # The re-anchor is `Origin' = C - R(C - Origin)`, which holds identically whether or not the
    # frame is orthogonal -- decomposing onto the axes by projection would not.
    p = _face(origin=(3.0, -2.0, 0.0), texture_v=_SKEW_V)
    lvl = _level_with(_brush_actor("B1", [p]))
    before = _uv(p, _PLUS_Z_CENTROID)
    apply_rotate(lvl, ["B1:all"], by_uu=16384)
    after = _uv(p, _PLUS_Z_CENTROID)
    assert after == pytest.approx(before, abs=1e-9)


def test_apply_rotate_at_a_non_quarter_angle_preserves_the_centroids_uv_and_the_magnitudes():
    import math
    p = _face(origin=(3.0, -2.0, 0.0), texture_u=(0.25, 0.0, 0.0), texture_v=(0.0, 0.5, 0.0))
    lvl = _level_with(_brush_actor("B1", [p]))
    before = _uv(p, _PLUS_Z_CENTROID)
    apply_rotate(lvl, ["B1:all"], by_uu=8192)              # 45 degrees: the Rodrigues path
    assert _uv(p, _PLUS_Z_CENTROID) == pytest.approx(before, abs=1e-9)
    assert math.dist(p.texture_u, (0, 0, 0)) == pytest.approx(0.25)
    assert math.dist(p.texture_v, (0, 0, 0)) == pytest.approx(0.5)
    assert p.texture_u[0] == pytest.approx(0.25 * math.cos(math.pi / 4))


def test_apply_rotate_leaves_pan_untouched():
    p = _face(pan=(7, 3))
    lvl = _level_with(_brush_actor("B1", [p]))
    apply_rotate(lvl, ["B1:all"], by_uu=16384)
    assert p.pan == (7, 3)


def test_apply_rotate_by_a_whole_turn_leaves_the_frame_byte_identical():
    # A whole number of turns is the identity, and re-anchoring it would write back
    # `C - (C - Origin)` -- arithmetically Origin, but not bit-for-bit in float, so it would churn
    # the trunk for no change.
    p = _face(origin=(0.1, 0.3, 0.0))
    lvl = _level_with(_brush_actor("B1", [p]))
    apply_rotate(lvl, ["B1:all"], by_uu=65536)
    assert p.origin == (0.1, 0.3, 0.0)
    assert p.texture_u == (1.0, 0.0, 0.0) and p.texture_v == (0.0, 1.0, 0.0)


def test_apply_rotate_by_an_enormous_angle_does_not_overflow():
    # `--by` is `type=int`, so it is arbitrary precision, and `by_uu * 2.0` on a value past ~1e308
    # raised `OverflowError: int too large to convert to float` — an UNCAUGHT traceback, since the
    # dispatch guard catches ValueError. Reducing modulo a full turn removes the class outright, and
    # it is exact: a rotation is periodic. The value must not be a whole number of quarter turns,
    # or the trig-free path sidesteps the conversion and the test proves nothing.
    huge = 10 ** 402 + 1
    assert huge % 16384 != 0
    ref, spun = _face(), _face()
    apply_rotate(_level_with(_brush_actor("B1", [ref])), ["B1:all"], by_uu=huge % 65536)
    apply_rotate(_level_with(_brush_actor("B1", [spun])), ["B1:all"], by_uu=huge)
    assert spun.texture_u == ref.texture_u and spun.texture_v == ref.texture_v


def test_apply_rotate_the_two_paths_diverge_on_an_out_of_plane_origin():
    """PIN: the exact and Rodrigues paths deliberately write a DIFFERENT `Origin` when `Origin` has
    a component along the face normal, and both are correct.

    The exact path re-anchors with `n̂ ×`, which annihilates that component; Rodrigues keeps it. The
    step-1 plan sanctions this explicitly — "a normal component of `Origin` cannot affect `(U,V)` at
    all (`TextureU ⊥ n̂`) … Do not 'fix' this" — and the assertion below shows why: the centroid's
    `(U,V)` is preserved to the same precision either way. Without this pin a later "unification" of
    the two paths would look like a tidy-up.
    """
    exact, rodrigues = _face(origin=(3.0, -2.0, 7.0)), _face(origin=(3.0, -2.0, 7.0))
    before = _uv(exact, _PLUS_Z_CENTROID)
    apply_rotate(_level_with(_brush_actor("B1", [exact])), ["B1:all"], by_uu=16384)
    apply_rotate(_level_with(_brush_actor("B1", [rodrigues])), ["B1:all"], by_uu=16385)
    assert exact.origin[2] == 0.0                       # the exact path drops the normal component
    assert rodrigues.origin[2] == pytest.approx(7.0)    # Rodrigues keeps it
    # ...and it makes no difference to what either verb promises:
    assert _uv(exact, _PLUS_Z_CENTROID) == pytest.approx(before, abs=1e-9)
    assert _uv(rodrigues, _PLUS_Z_CENTROID) == pytest.approx(before, abs=1e-9)


def test_apply_rotate_dedupes_an_overlapping_target_set():
    # Relative, so a face named twice would turn twice.
    p = _face()
    lvl = _level_with(_brush_actor("B1", [p]))
    apply_rotate(lvl, ["B1:all", "B1:0"], by_uu=16384)
    assert p.texture_u == (0.0, 1.0, 0.0)            # one quarter turn, not two


def test_apply_rotate_accepts_serializer_noise_in_the_axis():
    # `emit.clean` snaps each component independently within CLEAN_EPS = 0.001, so an axis uedcli
    # itself wrote can carry up to ~1.4e-3 of absolute out-of-plane displacement. The gate must sit
    # ABOVE that or it rejects the tool's own output.
    p = _face(texture_u=(1.0, 0.0, 1.4e-3))
    lvl = _level_with(_brush_actor("B1", [p]))
    apply_rotate(lvl, ["B1:all"], by_uu=16384)       # no raise


def test_apply_rotate_rejects_a_genuinely_out_of_plane_axis():
    # ~3 degrees of tilt on a unit axis: 5e-2 relative, far above the 1e-2 relative branch.
    p = _face(texture_u=(1.0, 0.0, 5e-2))
    lvl = _level_with(_brush_actor("B1", [p]))
    with pytest.raises(ValueError, match="out of the face plane"):
        apply_rotate(lvl, ["B1:all"], by_uu=16384)


@pytest.mark.parametrize("out_of_plane,rejected", [
    (1.4e-3, False),        # the serializer's own noise: under the 3e-3 absolute floor, accepted
    (5e-3, True),           # genuinely out of plane: over it, rejected
])
def test_apply_rotate_absolute_branch_brackets_a_short_axis_after_scale_by_8(out_of_plane, rejected):
    """THE CROSSOVER a relative-only gate gets wrong, bracketed from BOTH sides.

    After `scale --by 8,8` a unit axis is 0.125 long, so the relative term is `1e-2 x 0.125 =
    1.25e-3` and the absolute floor of `3e-3` governs. `1.4e-3` is the serializer's own noise
    (`emit.clean` snaps each component independently within `CLEAN_EPS`) and must be ACCEPTED even
    though it reads as 1.13e-2 relative -- over a 1e-2 relative-only gate, which is the whole reason
    the rule is absolute-OR-relative. `5e-3` is genuinely out of plane and must still be REJECTED.

    Both halves are needed: with only the acceptance half, an implementation with `_OOP_ABS = 1e-2`
    passes the entire suite.
    """
    p = _face()
    lvl = _level_with(_brush_actor("B1", [p]))
    apply_scale(lvl, ["B1:all"], by=(8.0, 8.0))
    assert p.texture_u[0] == pytest.approx(0.125)
    p.texture_u = (p.texture_u[0], p.texture_u[1], out_of_plane)   # re-added post-scale
    assert abs(out_of_plane / 0.125) > 1e-2                        # a relative-only gate: both reject
    if rejected:
        with pytest.raises(ValueError, match="out of the face plane"):
            apply_rotate(lvl, ["B1:all"], by_uu=16384)
    else:
        apply_rotate(lvl, ["B1:all"], by_uu=16384)                 # no raise


def test_apply_rotate_relative_branch_rejects_a_tilted_long_axis():
    # The mirror case: on a LONG axis the relative branch governs, so an absolute displacement well
    # above 3e-3 is still fine while a 5% tilt is not.
    ok = _face(texture_u=(8.0, 0.0, 6e-2))          # 7.5e-3 relative: under 1e-2
    apply_rotate(_level_with(_brush_actor("B1", [ok])), ["B1:all"], by_uu=16384)
    bad = _face(texture_u=(8.0, 0.0, 0.4))          # 5e-2 relative
    with pytest.raises(ValueError, match="out of the face plane"):
        apply_rotate(_level_with(_brush_actor("B1", [bad])), ["B1:all"], by_uu=16384)


def test_apply_rotate_out_of_plane_check_is_a_pre_pass_that_names_every_offender():
    # A batch is all-or-nothing (direction/conventions.md): a bad face 7 of 12 must leave faces
    # 0..6 unmutated, and the message must collect every offender rather than stopping at the first.
    polys = [_face() for _ in range(12)]
    polys[7].texture_u = (1.0, 0.0, 5e-2)
    polys[9].texture_v = (0.0, 1.0, 5e-2)
    lvl = _level_with(_brush_actor("B1", polys))
    with pytest.raises(ValueError) as exc:
        apply_rotate(lvl, ["B1:all"], by_uu=16384)
    msg = str(exc.value)
    assert "B1:7 TextureU" in msg and "B1:9 TextureV" in msg
    assert all(p.texture_v == (0.0, 1.0, 0.0) for p in polys[:7])   # nothing was written


def test_apply_rotate_names_a_face_missing_its_origin():
    p = _face(origin=None)
    lvl = _level_with(_brush_actor("B1", [p]))
    with pytest.raises(ValueError, match="B1:0 has no Origin"):
        apply_rotate(lvl, ["B1:all"], by_uu=16384)


@pytest.mark.parametrize("missing", ["texture_u", "texture_v"])
def test_apply_rotate_names_a_face_missing_a_texture_axis(missing):
    p = _face(**{missing: None})
    lvl = _level_with(_brush_actor("B1", [p]))
    with pytest.raises(ValueError, match="B1:0 has no TextureU/TextureV"):
        apply_rotate(lvl, ["B1:all"], by_uu=16384)


def test_apply_rotate_names_a_face_with_a_zero_length_axis():
    p = _face(texture_v=(0.0, 0.0, 0.0))
    lvl = _level_with(_brush_actor("B1", [p]))
    with pytest.raises(ValueError, match="B1:0 has a zero-length TextureV"):
        apply_rotate(lvl, ["B1:all"], by_uu=16384)


def test_apply_rotate_names_a_degenerate_zero_area_face():
    p = Polygon(vertices=[_D(0, 0, 0)] * 4, origin=(0.0, 0.0, 0.0),
                texture_u=(1.0, 0.0, 0.0), texture_v=(0.0, 1.0, 0.0))
    lvl = _level_with(_brush_actor("B1", [p]))
    with pytest.raises(ValueError, match="B1:0 is degenerate"):
        apply_rotate(lvl, ["B1:all"], by_uu=16384)


# --- apply_scale -----------------------------------------------------------------

def test_apply_scale_by_two_halves_the_stored_magnitudes():
    # --by names the APPARENT SIZE: twice as big on screen is half the stored magnitude, because
    # T3D density is texels per world unit.
    p = _face()
    lvl = _level_with(_brush_actor("B1", [p]))
    assert apply_scale(lvl, ["B1:all"], by=(2.0, 2.0)) == ["B1"]
    assert p.texture_u == pytest.approx((0.5, 0.0, 0.0))
    assert p.texture_v == pytest.approx((0.0, 0.5, 0.0))


def test_apply_scale_is_independent_per_axis():
    p = _face()
    lvl = _level_with(_brush_actor("B1", [p]))
    apply_scale(lvl, ["B1:all"], by=(2.0, 0.5))
    assert p.texture_u == pytest.approx((0.5, 0.0, 0.0))
    assert p.texture_v == pytest.approx((0.0, 2.0, 0.0))


def test_apply_scale_preserves_the_centroids_uv_on_an_orthogonal_frame():
    p = _face(origin=(3.0, -2.0, 0.0), texture_u=(0.25, 0.0, 0.0), texture_v=(0.0, 0.5, 0.0))
    lvl = _level_with(_brush_actor("B1", [p]))
    before = _uv(p, _PLUS_Z_CENTROID)
    apply_scale(lvl, ["B1:all"], by=(2.0, 3.0))
    assert _uv(p, _PLUS_Z_CENTROID) == pytest.approx(before, abs=1e-9)


def test_apply_scale_preserves_the_centroids_uv_on_a_skewed_frame_scaled_non_uniformly():
    # THE case the 2x2 Gram solve exists for. Scaling the covectors TextureU/TextureV by 1/fu,1/fv
    # scales POSITION by the inverse transpose, so decomposing the offset onto the direct basis and
    # scaling those components is silently wrong exactly here -- skew AND a non-uniform factor. It
    # is right for an orthogonal frame or a uniform factor, so only this case catches it.
    p = _face(origin=(3.0, -2.0, 0.0), texture_v=_SKEW_V)
    lvl = _level_with(_brush_actor("B1", [p]))
    before = _uv(p, _PLUS_Z_CENTROID)
    apply_scale(lvl, ["B1:all"], by=(2.0, 1.0))
    assert _uv(p, _PLUS_Z_CENTROID) == pytest.approx(before, abs=1e-9)


def test_apply_scale_reprojects_origin_onto_the_face_plane():
    """PIN: the re-anchor drops any component `Origin` had along the face NORMAL.

    `Origin' = C − (a·TU' + b·TV')` lies in the span of the two texture axes by construction, so an
    off-plane `Origin` comes back on-plane. Rendering-neutral — both axes are perpendicular to the
    normal, so that component cannot affect `(U,V)`, and the assertion below shows the centroid's
    `(U,V)` surviving — but the trunk records the change, so it is pinned rather than left to be
    discovered. `rotate`'s exact path does the same thing and is pinned separately.
    """
    p = _face(origin=(3.0, -2.0, 7.0))
    lvl = _level_with(_brush_actor("B1", [p]))
    before = _uv(p, _PLUS_Z_CENTROID)
    apply_scale(lvl, ["B1:all"], by=(2.0, 2.0))
    assert p.origin[2] == 0.0                                       # the +Z component is gone
    assert _uv(p, _PLUS_Z_CENTROID) == pytest.approx(before, abs=1e-9)


def test_apply_scale_by_one_writes_nothing_at_all():
    """`--by 1,1` is the identity the author asked for, so it must not reproject `Origin` either.

    Without the short-circuit an off-plane `Origin` is silently rewritten by a call that changes
    nothing anyone can see, churning the trunk's git diff. This matches `rotate --by 0`, whose
    whole-turn skip exists for the same reason — the two verbs would otherwise disagree about
    whether a no-op is a write.
    """
    p = _face(origin=(3.0, -2.0, 7.0))
    lvl = _level_with(_brush_actor("B1", [p]))
    apply_scale(lvl, ["B1:all"], by=(1.0, 1.0))
    assert p.origin == (3.0, -2.0, 7.0)
    assert p.texture_u == (1.0, 0.0, 0.0) and p.texture_v == (0.0, 1.0, 0.0)


def test_apply_scale_by_one_still_validates_before_skipping():
    # The skip is a WRITE skip, not a validation skip: a malformed frame is still refused, exactly
    # as `rotate --by 0` still rejects an out-of-plane axis.
    p = _face(origin=None)
    lvl = _level_with(_brush_actor("B1", [p]))
    with pytest.raises(ValueError, match="B1:0 has no Origin"):
        apply_scale(lvl, ["B1:all"], by=(1.0, 1.0))


def test_apply_scale_leaves_pan_untouched():
    p = _face(pan=(7, 3))
    lvl = _level_with(_brush_actor("B1", [p]))
    apply_scale(lvl, ["B1:all"], by=(2.0, 2.0))
    assert p.pan == (7, 3)


def test_apply_scale_dedupes_an_overlapping_target_set():
    p = _face()
    lvl = _level_with(_brush_actor("B1", [p]))
    apply_scale(lvl, ["B1:all", "B1:0"], by=(2.0, 2.0))
    assert p.texture_u == pytest.approx((0.5, 0.0, 0.0))     # halved once, not quartered


@pytest.mark.parametrize("by", [(0.0, 1.0), (1.0, 0.0), (-2.0, 1.0), (1.0, -2.0)])
def test_apply_scale_rejects_a_zero_or_negative_factor(by):
    # A zero-length texture vector crashes the CSG rebuild (builders._tex_basis).
    p = _face()
    lvl = _level_with(_brush_actor("B1", [p]))
    with pytest.raises(ValueError, match="must be a positive number"):
        apply_scale(lvl, ["B1:all"], by=by)
    assert p.texture_u == (1.0, 0.0, 0.0)                    # nothing was written


def test_apply_scale_rejects_a_degenerate_frame():
    # Parallel axes: the Gram determinant is zero, so the re-anchor has no solution.
    p = _face(texture_v=(2.0, 0.0, 0.0))
    lvl = _level_with(_brush_actor("B1", [p]))
    with pytest.raises(ValueError, match="B1:0 has a degenerate texture frame"):
        apply_scale(lvl, ["B1:all"], by=(2.0, 2.0))


@pytest.mark.parametrize("by", [
    (1000.0, 1.0),          # SHRINK past CLEAN_EPS: the axis would snap to exactly zero
    (1e-22, 1.0),           # GROW past what fmt_vertex can quantize -- the band `clean` let through
    (1e-200, 1.0),          # GROW absurdly: caught wherever the bound sits
])
def test_apply_scale_blames_the_FACTOR_not_the_frame_when_a_factor_is_absurd(by):
    # An extreme factor drives the axis past what the trunk can store. That used to surface as "this
    # face has a degenerate texture frame (TextureU and TextureV are parallel or zero-length)" -- a
    # clean exit naming the WRONG offender, on a perfectly ordinary ORTHOGONAL frame.
    #
    # The 1e-22 case is the one an earlier version of this test MISSED: it used 1e-200 only, whose
    # square is inf, so it exercised an overflow branch and never the serializer bound. 1e-22 is
    # finite in every intermediate, and `emit.clean` accepts it (>=1e22 is exactly integral in
    # Decimal terms, so `clean` returns it unharmed) -- only `fmt_vertex` refuses it.
    p = _face()
    lvl = _level_with(_brush_actor("B1", [p]))
    with pytest.raises(ValueError, match=r"--by FU=.* is too extreme") as exc:
        apply_scale(lvl, ["B1:all"], by=by)
    assert "degenerate" not in str(exc.value)
    assert p.texture_u == (1.0, 0.0, 0.0)               # nothing was written


def test_apply_scale_to_names_the_to_flag_not_by_when_a_target_is_absurd():
    # The offender-naming message must reflect how the caller actually spelled the request: a
    # face scaled via --to must not be told it was --by that went wrong.
    p = _face(texture="Pkg.Tex")
    lvl = _level_with(_brush_actor("B1", [p]))
    with pytest.raises(ValueError, match=r"--to U=.* is too extreme") as exc:
        apply_scale(lvl, ["B1:all"], to=(1e22, 128.0), resolve_dims=lambda ref: (256, 256))
    assert "--by" not in str(exc.value)
    assert p.texture_u == (1.0, 0.0, 0.0)               # nothing was written


@pytest.mark.parametrize("by", [(999.0, 999.0), (100.0, 100.0), (1e-21, 1.0), (0.001, 0.001)])
def test_apply_scale_accepts_a_factor_whose_result_the_trunk_CAN_carry(by):
    """The counterpart bound: the guard must not reject a factor the trunk can hold.

    Asserted through the REAL serializer, not on the in-memory floats. The in-memory check is what
    let the bug through: the previous version of this test passed `--by 1000` on a unit axis and
    asserted `max(abs(c)) >= 5e-7`, certifying as "storable" an axis that `emit` writes as
    `+00000.000000,+00000.000000,+00000.000000`.
    """
    a = _brush_actor("B1", [_face()])
    apply_scale(_level_with(a), ["B1:all"], by=by)
    written = _written_axes(a)
    assert len(written) == 2 and not any(_ALL_ZERO in ln for ln in written), written


def test_apply_scale_never_writes_an_all_zero_axis_however_often_it_is_repeated():
    """REGRESSION: `scale --by` silently destroyed a texture axis, exit 0, clean stdout.

    The guard's floor was written as `emit`'s six decimal places, but the real floor is
    `emit.CLEAN_EPS = 1e-3` -- `clean` snaps any component within `CLEAN_EPS` of an INTEGER to that
    integer, and zero is an integer. So three ordinary `--by 10,10` invocations walked a unit axis
    `0.1 -> 0.01 -> 0.0` and wrote a zero-length TextureU into the trunk, which crashes the CSG
    rebuild (`builders._tex_basis`); the failure was only reported on the FOURTH call, blaming the
    frame. Reachable on real content: the cliff is at `|axis|/1e-3`, i.e. 667 on the `0.6667` axes
    the editor-exported fixtures actually contain.

    Asserted on the EMITTED TEXT after every step, because that is where the corruption lived -- the
    in-memory float was a perfectly ordinary `1e-3` at the moment it was written as zero.
    """
    a = _brush_actor("B1", [_face()])
    lvl = _level_with(a)
    refused = 0
    for _ in range(6):
        try:
            apply_scale(lvl, ["B1:all"], by=(10.0, 10.0))
        except ValueError as e:
            refused += 1
            assert "too extreme" in str(e)
        assert not any(_ALL_ZERO in ln for ln in _written_axes(a)), _written_axes(a)
    assert refused, "the run never hit the floor, so it did not exercise the guard"


def test_apply_scale_blames_the_FRAME_when_the_FRAME_is_the_unstorable_one():
    # The mirror of the finding above: an innocent factor must not be blamed for an axis that
    # arrived unstorable. `--by 1.0` changes nothing, so the frame is the only possible offender.
    p = _face(texture_u=(1e200, 0.0, 0.0))
    lvl = _level_with(_brush_actor("B1", [p]))
    with pytest.raises(ValueError, match="B1:0 already has a TextureU the trunk cannot store"):
        apply_scale(lvl, ["B1:all"], by=(1.0, 1.0))


def test_apply_scale_still_blames_the_FRAME_when_the_frame_really_is_degenerate():
    # The other side of the same fork: an ordinary factor on genuinely parallel axes must keep
    # naming the frame, not the factor.
    p = _face(texture_v=(2.0, 0.0, 0.0))
    lvl = _level_with(_brush_actor("B1", [p]))
    with pytest.raises(ValueError, match="B1:0 has a degenerate texture frame"):
        apply_scale(lvl, ["B1:all"], by=(2.0, 2.0))


def test_apply_scale_names_a_face_missing_its_origin():
    p = _face(origin=None)
    lvl = _level_with(_brush_actor("B1", [p]))
    with pytest.raises(ValueError, match="B1:0 has no Origin"):
        apply_scale(lvl, ["B1:all"], by=(2.0, 2.0))


def test_apply_scale_is_all_or_nothing_across_faces():
    good, bad = _face(), _face(origin=None)
    lvl = _level_with(_brush_actor("B1", [good, bad]))
    with pytest.raises(ValueError, match="B1:1 has no Origin"):
        apply_scale(lvl, ["B1:all"], by=(2.0, 2.0))
    assert good.texture_u == (1.0, 0.0, 0.0)


def test_apply_scale_tolerates_an_out_of_plane_axis():
    # Unlike `rotate`, scaling preserves direction, so an out-of-plane component is harmless and
    # there is deliberately no in-plane guard here. Do not "unify" the two verbs' validation.
    p = _face(texture_u=(1.0, 0.0, 0.5))
    lvl = _level_with(_brush_actor("B1", [p]))
    apply_scale(lvl, ["B1:all"], by=(2.0, 2.0))
    assert p.texture_u == pytest.approx((0.5, 0.0, 0.25))


# --- apply_scale --to (step 5) -----------------------------------------------------

def _mag(v):
    return (v[0] ** 2 + v[1] ** 2 + v[2] ** 2) ** 0.5


def test_apply_scale_to_sets_absolute_world_units_per_tile():
    # --to 128,128 on a 256x256 texture: |TextureU| = W/U = 256/128 = 2.0.
    p = _face(texture="Pkg.Tex")
    lvl = _level_with(_brush_actor("B1", [p]))
    apply_scale(lvl, ["B1:all"], to=(128.0, 128.0), resolve_dims=lambda ref: (256, 256))
    assert _mag(p.texture_u) == pytest.approx(2.0)
    assert _mag(p.texture_v) == pytest.approx(2.0)


def test_apply_scale_to_uses_each_faces_own_bound_texture_independently():
    a = _face(texture="Pkg.A")
    b = _face(texture="Pkg.B")
    lvl = _level_with(_brush_actor("B1", [a, b]))

    def resolve_dims(ref):
        return {"Pkg.A": (256, 256), "Pkg.B": (512, 512)}[ref]

    apply_scale(lvl, ["B1:0", "B1:1"], to=(128.0, 128.0), resolve_dims=resolve_dims)
    assert _mag(a.texture_u) == pytest.approx(2.0)
    assert _mag(b.texture_u) == pytest.approx(4.0)


def test_apply_scale_to_batches_every_untextured_and_unresolved_face():
    ok = _face(texture="Pkg.Good")
    none_tex = _face(texture=None)
    bad_ref = _face(texture="Pkg.Bad")
    lvl = _level_with(_brush_actor("B1", [ok, none_tex, bad_ref]))

    def resolve_dims(ref):
        if ref == "Pkg.Good":
            return (256, 256)
        raise ValueError(f"texture not found: {ref}")

    with pytest.raises(ValueError) as exc:
        apply_scale(lvl, ["B1:0", "B1:1", "B1:2"], to=(128.0, 128.0), resolve_dims=resolve_dims)
    msg = str(exc.value)
    assert "B1:1" in msg and "carry no texture" in msg
    assert "Pkg.Bad" in msg
    assert ok.texture_u == (1.0, 0.0, 0.0)                # nothing written — all-or-nothing


def test_apply_scale_to_rejects_a_zero_or_negative_target():
    p = _face(texture="Pkg.Tex")
    lvl = _level_with(_brush_actor("B1", [p]))
    with pytest.raises(ValueError, match="must be a positive number"):
        apply_scale(lvl, ["B1:all"], to=(0.0, 128.0), resolve_dims=lambda ref: (256, 256))


def test_apply_scale_to_never_calls_resolve_dims_for_by():
    p = _face(texture="Pkg.Tex")
    lvl = _level_with(_brush_actor("B1", [p]))
    calls = []
    apply_scale(lvl, ["B1:all"], by=(2.0, 2.0), resolve_dims=lambda ref: calls.append(ref) or (1, 1))
    assert not calls
