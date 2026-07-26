from decimal import Decimal

import pytest

from uedcli.model import Actor, Brush, CoordinateError, Polygon, parse_t3d
from uedcli.emit import emit_actor, emit_actor_t3d, emit_brush_block, emit_map, snap, clean, fmt_vertex, fmt_loc, quote_group
from uedcli.tests.conftest import read_fixture


def test_snap_rounds_to_grid():
    assert snap(511.999969) == 512
    assert snap(192.000031) == 192
    assert snap(-384.000031) == -384
    assert snap(0.0) == 0


def test_clean_snaps_editor_noise_but_preserves_real_fractions():
    # Editor float-noise (within EPS=0.001 of an integer) snaps to the integer.
    assert clean(Decimal("511.999969")) == Decimal("512")
    assert clean(Decimal("192.000031")) == Decimal("192")
    assert clean(0.0) == Decimal("0")
    # Genuine fractions further than EPS from an integer are preserved exactly.
    assert clean(Decimal("0.99")) == Decimal("0.99")
    assert clean(Decimal("32.5")) == Decimal("32.5")
    # A computed float (e.g. radius*cos) is carried at 6-dp precision, no binary drift.
    assert clean(70.710678) == Decimal("70.710678")


def test_clean_always_returns_decimal():
    assert isinstance(clean(512.0), Decimal)
    assert isinstance(clean(Decimal("32.5")), Decimal)


def test_fmt_vertex_zero_padded_signed():
    assert fmt_vertex(512.0) == "+00512.000000"
    assert fmt_vertex(-128.0) == "-00128.000000"


def test_fmt_vertex_preserves_fractional_coord():
    assert fmt_vertex(Decimal("32.5")) == "+00032.500000"
    assert fmt_vertex(Decimal("70.710678")) == "+00070.710678"
    assert fmt_vertex(Decimal("-16.25")) == "-00016.250000"


def test_fmt_loc_preserves_fractional_coord():
    assert fmt_loc(Decimal("32.5")) == "32.500000"
    assert fmt_loc(Decimal("-384")) == "-384.000000"


def test_quote_group_always_quotes():
    assert quote_group("club_entrance") == '"club_entrance"'
    assert quote_group("A,B,C") == '"A,B,C"'


def test_emit_light_round_trips_through_model():
    level = parse_t3d(read_fixture("add_light.t3d"))
    a = level.actors["SpikeProbeLight999"]
    out = emit_actor(a)
    re_level = parse_t3d("Begin Map\n" + out + "\nEnd Map")
    b = re_level.actors["SpikeProbeLight999"]
    assert b.cls == "Light"
    assert b.location == (12345.0, 6789.0, 4242.0)


def test_emit_brush_preserves_vertex_winding_and_count():
    level = parse_t3d(read_fixture("brush_subtract.t3d"))
    a = level.actors["Brush938"]
    original_verts = [(snap(x), snap(y), snap(z)) for x, y, z in a.brush.polys[0].vertices]
    out = emit_actor(a)
    re_level = parse_t3d("Begin Map\n" + out + "\nEnd Map")
    rb = re_level.actors["Brush938"].brush
    assert len(rb.polys) == 6
    # Winding order preserved: re-parsed (snapped) vertices match original snapped vertices
    re_verts = [(snap(x), snap(y), snap(z)) for x, y, z in rb.polys[0].vertices]
    assert re_verts == original_verts


def test_emit_map_wraps_in_begin_end_map():
    level = parse_t3d(read_fixture("add_light.t3d"))
    actors = list(level.actors.values())
    out = emit_map(actors)
    assert out.startswith("Begin Map\n")
    assert out.strip().endswith("End Map")


def test_group_prop_is_always_quoted():
    level = parse_t3d(read_fixture("brush_subtract.t3d"))
    a = level.actors["Brush938"]
    out = emit_actor(a)
    # Group value must be quoted in output
    assert 'Group="club_entrance"' in out


def test_emit_actor_t3d_produces_valid_actor_block():
    level = parse_t3d(read_fixture("brush_subtract.t3d"))
    a = level.actors["Brush938"]
    out = emit_actor_t3d(a)
    re_level = parse_t3d(out)
    b = re_level.actors["Brush938"]
    assert b.cls == a.cls
    assert len(b.brush.polys) == len(a.brush.polys)


def test_emit_actor_t3d_brush_ref_follows_end_brush():
    a = Actor(
        name="B1", cls="Engine.Brush",
        props=[("CsgOper", "CSG_Add"), ("Brush", "Model'MyLevel.Model_B1'")],
        location=(0.0, 0.0, 0.0),
        brush=Brush(model_name="Model_B1",
                    polys=[Polygon(flags=0, vertices=[(0, 0, 0), (1, 0, 0), (1, 1, 0)])]),
    )
    out = emit_actor_t3d(a)
    assert out.index("End Brush") < out.index("Brush=Model'MyLevel.Model_B1'")


def test_emit_brush_block_format():
    from uedcli.builders import cube
    b = cube(128, 128, 128)
    out = emit_brush_block(b)
    lines = out.strip().splitlines()
    assert lines[0].strip() == "Begin PolyList"
    assert lines[-1].strip() == "End PolyList"
    assert "Begin Actor" not in out
    assert "Begin Brush" not in out


def test_emit_brush_block_roundtrip():
    from uedcli.builders import cube
    b = cube(128, 128, 128)
    out = emit_brush_block(b)
    # Wrap in Begin Brush to use _parse_brush via parse_t3d actor path.
    wrapped = (
        "Begin Actor Class=Engine.Brush Name=TestBrush\n"
        "   Begin Brush Name=Model_TestBrush\n"
        + out +
        "   End Brush\n"
        "End Actor\n"
    )
    level = parse_t3d(wrapped)
    rb = level.actors["TestBrush"].brush
    assert len(rb.polys) == len(b.polys)


def test_brush_model_ref_emitted_after_brush_block():
    """The actor's Brush=Model'..' reference MUST be emitted after End Brush.

    Emitted before the Begin Brush block (its natural prop order), the imported
    brush binds to a not-yet-defined model and has no usable bound: it renders
    but ACTOR SELECT INSIDE skips it (verified live against the editor). Matches
    the editor's own EDIT COPY ordering.
    """
    from uedcli.model import Actor, Brush, Polygon

    a = Actor(
        name="B1", cls="Brush",
        props=[("CsgOper", "CSG_Add"), ("Brush", "Model'MyLevel.Brush'")],
        location=(0.0, 0.0, 0.0),
        brush=Brush(model_name="Brush",
                    polys=[Polygon(flags=0, vertices=[(0, 0, 0), (1, 0, 0), (1, 1, 0)])]),
    )
    out = emit_actor(a)
    assert out.count("Brush=Model'MyLevel.Brush'") == 1          # not duplicated
    assert out.index("End Brush") < out.index("Brush=Model'MyLevel.Brush'")  # after the block
    # round-trips: the reference survives re-parse as a prop
    rb = parse_t3d("Begin Map\n" + out + "\nEnd Map").actors["B1"]
    assert ("Brush", "Model'MyLevel.Brush'") in rb.props


def test_it_round_trips_indexed_array_props_through_emit():
    t3d = (
        "Begin Map\nBegin Actor Class=Mover Name=Door1\n"
        "    KeyPos(1)=(Z=256.000000)\n"
        "    KeyRot(1)=(Yaw=16384)\n"
        "    MultiSkins(2)=Texture'Pkg.Skin'\n"
        '    Name="Door1"\nEnd Actor\nEnd Map\n'
    )
    actor = parse_t3d(t3d).actors["Door1"]
    out = emit_actor(actor)
    assert "KeyPos(1)=(Z=256.000000)" in out
    assert "KeyRot(1)=(Yaw=16384)" in out
    assert "MultiSkins(2)=Texture'Pkg.Skin'" in out
    again = parse_t3d("Begin Map\n" + out + "\nEnd Map\n").actors["Door1"]
    assert dict(again.props) == dict(actor.props)


# --- unrepresentable coordinates fail as a NAMED error, never a traceback ------------------------


@pytest.mark.parametrize("value", [float("inf"), float("nan"), Decimal("NaN")])
def test_a_non_finite_coordinate_is_rejected_at_the_front_door(value):
    # Non-finite is the ONLY thing `clean` rejects on magnitude grounds, because it is the only
    # thing neither emitter can write. Anything else is decided per-emitter, below.
    with pytest.raises(CoordinateError) as exc:
        clean(value)
    assert "finite" in str(exc.value)


@pytest.mark.parametrize("value", [float("inf"), float("-inf"), float("nan"), Decimal("Infinity"),
                                   Decimal("NaN")])
def test_fmt_coord_rejects_a_non_finite_instead_of_tracebacking(value):
    # `cli.parse_coord` builds coordinates with `Decimal(p)`, which ACCEPTS inf/nan, and
    # `int(Decimal("Infinity"))` raises OverflowError — which `dispatch()` does not catch, so
    # `brush scale --to inf,1,1` printed a traceback. `fmt_coord` guards like every sibling emitter.
    from uedcli.emit import fmt_coord
    with pytest.raises(CoordinateError) as exc:
        fmt_coord(value)
    assert "finite" in str(exc.value)


@pytest.mark.parametrize("value", [1e200, Decimal("5e24"), Decimal("-1e22"), Decimal("1e22")])
def test_a_vertex_too_precise_to_round_is_a_named_error_not_a_traceback(value):
    # `fmt_vertex` rounds through `quantize(_SIX_DP)`, which under Decimal's 28-digit precision
    # allows 22 integer digits — so 1e22 is the wall. Before the guard these raised a bare
    # `decimal.InvalidOperation`, the failure class CLAUDE.md forbids.
    with pytest.raises(CoordinateError) as exc:
        fmt_vertex(value)
    assert str(value).lower() in str(exc.value).lower() or "precision" in str(exc.value)


@pytest.mark.parametrize("value", [Decimal("1e22"), Decimal("1e30"), Decimal("1e200")])
def test_a_location_beyond_the_vertex_wall_still_emits(value):
    # THE REGRESSION GUARD. `fmt_loc` formats with f"{d:.6f}" and has no precision wall, so its
    # range has always been wider than `fmt_vertex`'s. A guard placed in the shared front door
    # instead of at the quantize made these exit 2 — which made an existing trunk carrying such a
    # Location unreadable to `actor show`/`level doctor`. Master emits every one of them.
    assert fmt_loc(value).endswith(".000000")
    clean(value)          # and the shared path must not reject it either
    snap(value)


@pytest.mark.parametrize("value", [32768, -32768, 1e15, Decimal("9999999999999999999999.5")])
def test_a_representable_vertex_is_not_rejected(value):
    # The engine's own world is ±32768; the rest are absurd but genuinely emittable, and the
    # guard must not narrow what already round-tripped.
    fmt_vertex(value)
    clean(value)


@pytest.mark.parametrize("value", [float("inf"), float("nan")])
def test_snap_rejects_a_non_finite_coordinate(value):
    # `snap` bypasses `clean`'s rounding, so without the shared `_guard` a non-finite input raises
    # OverflowError/ValueError — neither caught by dispatch, i.e. a traceback.
    with pytest.raises(CoordinateError):
        snap(value)


def test_a_zero_pan_emits_no_pan_line_at_all():
    # A polygon's `Pan U=<u> V=<v>` is the texture offset added by the UV formula
    # `U = (Vertex − Origin)·TextureU + PanU` (unrealed/t3d.md "The UV convention"). The line is
    # OPTIONAL and an absent one means zero — there is no class default behind it, so `Pan U=0 V=0`
    # and no Pan line at all are the SAME surface. UnrealEd's own exporter writes only the
    # non-default spelling: it never emits a zero Pan (no `Pan U=0 V=0` occurs anywhere in this
    # repo's real editor exports, and a live 2026-07-26 `level materialize` proved the editor drops
    # one uedcli had imported). Since the H3 post-verify compares the two sides' brush text LINE BY
    # LINE, emitting the redundant line shifted every following line and aborted the build with
    # nothing written. So emit is the ONE place both spellings collapse: a zero pan is never
    # written, exactly as `Flags=0` is never written.
    p = Polygon(pan=(0, 0), vertices=[(Decimal(0), Decimal(0), Decimal(0))])
    assert "Pan" not in emit_brush_block(Brush(model_name="Model0", polys=[p]))


@pytest.mark.parametrize("pan", [(0, 16), (16, 0), (-1, 0), (7, 3)])
def test_a_pan_with_any_non_zero_component_is_emitted(pan):
    # Only the all-zero pan is the default spelling; a half-zero one is real content.
    p = Polygon(pan=pan, vertices=[(Decimal(0), Decimal(0), Decimal(0))])
    body = emit_brush_block(Brush(model_name="Model0", polys=[p]))
    assert f"Pan      U={pan[0]} V={pan[1]}" in body


def test_a_zero_pan_parsed_back_is_the_same_surface_as_one_never_panned():
    # Round-trip: the emitted trunk for a zero-panned poly re-parses with `pan is None`, which every
    # reader (the renderer, `--pan-by`'s base, the compare) already treats as zero.
    p = Polygon(pan=(0, 0), origin=(Decimal(0), Decimal(0), Decimal(0)),
                vertices=[(Decimal(0), Decimal(0), Decimal(0))])
    a = Actor(name="B", cls="Engine.Brush")
    a.brush = Brush(model_name="Model0", polys=[p])
    back = parse_t3d(emit_map([a]))
    assert back.actors["B"].brush.polys[0].pan is None
