from decimal import Decimal

import pytest

from uedctl.builders import cube, make_brush_actor
from uedctl.model import Actor, Level, parse_t3d
from uedctl.query import (list_actors, show_actor, describe,
                          decode_flags, list_polys, format_polys,
                          list_vertices, format_vertices,
                          _class_matches, resolve_actor_name, resolve_actor_names)
from uedctl.tests.conftest import read_fixture


# ── Step 1: _class_matches helper ─────────────────────────────────────────────


def test_class_matches_bare_name_matches_leaf():
    # bare query matches the last-dot-component of the stored class
    assert _class_matches("Light", "Engine.Light")


def test_class_matches_bare_name_does_not_match_wrong_leaf():
    assert not _class_matches("Light", "Engine.Brush")


def test_class_matches_qualified_exact():
    assert _class_matches("Engine.Light", "Engine.Light")


def test_class_matches_qualified_different_package():
    # Foo.Light does NOT match Engine.Light (different package)
    assert not _class_matches("Foo.Light", "Engine.Light")


def test_class_matches_case_insensitive():
    assert _class_matches("light", "Engine.Light")
    assert _class_matches("engine.light", "Engine.Light")
    assert _class_matches("LIGHT", "Engine.Light")


# ── Step 1: list_actors case-fold (name_glob, cls) ────────────────────────────


def _make_level_with_actors():
    """Small level: HelperLight0 (Engine.Light), Brush1 (Engine.Brush with group cells)."""
    lv = Level()
    lv.actors["HelperLight0"] = Actor(
        name="HelperLight0", cls="Engine.Light",
        props=[("Group", "cells"), ("bHidden", "True")],
    )
    lv.actors["Brush1"] = Actor(
        name="Brush1", cls="Engine.Brush",
        props=[("Group", "vents"), ("CsgOper", "CSG_Subtract")],
        brush=cube(64, 64, 64),
    )
    lv.order = ["HelperLight0", "Brush1"]
    return lv


def test_list_actors_name_glob_case_insensitive():
    lv = _make_level_with_actors()
    assert list_actors(lv, name_glob="helperlight0") == ["HelperLight0"]
    assert list_actors(lv, name_glob="HELPERLIGHT0") == ["HelperLight0"]
    assert list_actors(lv, name_glob="helperlight*") == ["HelperLight0"]


def test_list_actors_cls_case_insensitive():
    lv = _make_level_with_actors()
    assert list_actors(lv, cls="light") == ["HelperLight0"]
    assert list_actors(lv, cls="LIGHT") == ["HelperLight0"]
    assert list_actors(lv, cls="engine.light") == ["HelperLight0"]


def test_list_actors_names_list_or_match():
    lv = _make_level_with_actors()
    # names list: OR — either pattern matches
    result = list_actors(lv, names=["helperlight0", "Brush1"])
    assert set(result) == {"HelperLight0", "Brush1"}


def test_list_actors_names_list_case_insensitive():
    lv = _make_level_with_actors()
    result = list_actors(lv, names=["HELPERLIGHT0"])
    assert result == ["HelperLight0"]


def test_list_actors_classes_list_or_match():
    lv = _make_level_with_actors()
    result = list_actors(lv, classes=["Light", "Brush"])
    assert set(result) == {"HelperLight0", "Brush1"}


def test_list_actors_classes_list_case_insensitive():
    lv = _make_level_with_actors()
    assert list_actors(lv, classes=["LIGHT"]) == ["HelperLight0"]


# ── Step 1: groups filter ─────────────────────────────────────────────────────


def _make_level_with_groups():
    """Level with multi-group actor and single-group actor."""
    lv = Level()
    lv.actors["Multi"] = Actor(
        name="Multi", cls="Engine.Light",
        props=[("Group", "cells,vents")],
    )
    lv.actors["Single"] = Actor(
        name="Single", cls="Engine.Light",
        props=[("Group", "cells")],
    )
    lv.actors["Spaced"] = Actor(
        name="Spaced", cls="Engine.Light",
        props=[("Group", "cells, vents")],  # space after comma
    )
    lv.actors["NoGroup"] = Actor(
        name="NoGroup", cls="Engine.Brush",
        props=[],
    )
    lv.order = ["Multi", "Single", "Spaced", "NoGroup"]
    return lv


def test_list_actors_group_membership():
    lv = _make_level_with_groups()
    result = list_actors(lv, groups=["cells"])
    assert set(result) == {"Multi", "Single", "Spaced"}


def test_list_actors_group_multi_group_actor_matched_by_either_group():
    lv = _make_level_with_groups()
    assert "Multi" in list_actors(lv, groups=["cells"])
    assert "Multi" in list_actors(lv, groups=["vents"])


def test_list_actors_group_or_across_groups():
    lv = _make_level_with_groups()
    # OR: cells OR vents — should include all that have either
    result = list_actors(lv, groups=["cells", "vents"])
    assert set(result) == {"Multi", "Single", "Spaced"}


def test_list_actors_group_membership_strips_spaces():
    lv = _make_level_with_groups()
    # "cells, vents" (with space) — strip each element
    result = list_actors(lv, groups=["vents"])
    assert "Spaced" in result


def test_list_actors_group_case_insensitive():
    lv = _make_level_with_groups()
    assert list_actors(lv, groups=["CELLS"]) == list_actors(lv, groups=["cells"])


def test_list_actors_no_group_actor_excluded():
    lv = _make_level_with_groups()
    assert "NoGroup" not in list_actors(lv, groups=["cells"])


# ── Step 1: props filter — REMOVED 2026-07-18: `--prop` matching moved out of
# query.list_actors to the dispatch find handler (EFFECTIVE-value matching over the
# class schema/defaults — spec 2026-07-18-actor-prop-subcommands.md §7); covered by
# test_dispatch.py's test_actor_find_prop_* tests.


# ── Step 1: kind filter ────────────────────────────────────────────────────────


def test_list_actors_kind_point():
    lv = _make_level_with_actors()
    # HelperLight0 is a point actor (no brush), Brush1 has a brush
    result = list_actors(lv, kind="point")
    assert result == ["HelperLight0"]


def test_list_actors_kind_brush():
    lv = _make_level_with_actors()
    result = list_actors(lv, kind="brush")
    assert result == ["Brush1"]


def test_list_actors_kind_none_matches_all():
    lv = _make_level_with_actors()
    result = list_actors(lv, kind=None)
    assert set(result) == {"HelperLight0", "Brush1"}


# ── Step 1: list_actors follows level.order, not dict insertion order ─────────


def test_list_actors_follows_level_order_not_dict_insertion_order():
    """Output order is driven by level.order, not actors dict insertion order."""
    lv = Level()
    # Insert actors in reverse order relative to how level.order will sequence them.
    lv.actors["ZZZLast"] = Actor(name="ZZZLast", cls="Engine.Light", props=[])
    lv.actors["AAAFirst"] = Actor(name="AAAFirst", cls="Engine.Light", props=[])
    lv.actors["MMMMiddle"] = Actor(name="MMMMiddle", cls="Engine.Light", props=[])
    lv.order = ["AAAFirst", "MMMMiddle", "ZZZLast"]
    assert list_actors(lv) == ["AAAFirst", "MMMMiddle", "ZZZLast"]


def test_list_actors_emits_remainder_not_in_order_after_ordered_actors():
    """Actors absent from level.order appear after ordered actors rather than being dropped."""
    lv = Level()
    lv.actors["Ordered"] = Actor(name="Ordered", cls="Engine.Light", props=[])
    lv.actors["Orphan"] = Actor(name="Orphan", cls="Engine.Light", props=[])
    lv.order = ["Ordered"]
    result = list_actors(lv)
    assert result[0] == "Ordered"
    assert "Orphan" in result


# ── Step 1: show_actor case-insensitive ────────────────────────────────────────


def test_show_actor_case_insensitive():
    lv = _make_level_with_actors()
    # lower-case name should resolve HelperLight0
    out = show_actor(lv, "helperlight0")
    assert "HelperLight0" in out


# ── Step 1: existing tests remain green (regression guard) ────────────────────


def test_list_vertices_returns_world_corners_with_their_polys():
    a = make_brush_actor("B1", cube(64, 64, 64),
                         location=(Decimal(100), Decimal(200), Decimal(300)))
    rows = list_vertices(a)
    assert len(rows) == 8
    r = next(x for x in rows if x["coord"] == (Decimal(132), Decimal(232), Decimal(332)))
    assert r["nrefs"] == 3 and len(r["polys"]) == 3


def test_list_vertices_handles_brush_without_location():
    # A brush parsed with no Location line has location=None; world coords must still
    # compute (Decimal-default origin), not crash on Decimal-vs-float arithmetic.
    a = make_brush_actor("B1", cube(8, 8, 8))
    a.location = None
    assert len(list_vertices(a)) == 8


def test_format_vertices_renders_count_and_a_corner():
    a = make_brush_actor("B1", cube(64, 64, 64))
    out = format_vertices(a, "B1")
    assert "B1: 8 vertices" in out
    assert "(32,32,32)" in out


def test_decode_flags_to_names():
    assert decode_flags(0) == ["none"]
    assert decode_flags(2) == ["masked"]
    assert decode_flags(4) == ["translucent"]
    assert decode_flags(2 | 256) == ["masked", "twosided"]
    assert "0x10000" in decode_flags(0x10000)        # unknown bit → hex tail


def test_list_polys_cube_metadata():
    a = parse_t3d(read_fixture("brush_subtract.t3d")).actors["Brush938"]
    rows = list_polys(a)
    assert len(rows) == len(a.brush.polys)
    facings = {r["facing"] for r in rows}
    assert facings & {"+X", "-X", "+Y", "-Y", "+Z", "-Z"}     # axis-aligned faces named
    r0 = rows[0]
    assert set(r0) == {"idx", "facing", "texture", "flags", "pan", "centroid", "area", "nverts"}
    assert r0["area"] > 0 and r0["nverts"] >= 3
    table = format_polys(a, "Brush938")
    assert "Brush938:" in table and "facing" in table
    assert r0["pan"] is None       # unset on this fixture; format_polys prints '-'
    assert " - " in table


def test_list_by_class():
    level = parse_t3d(read_fixture("level_small.t3d"))
    brushes = list_actors(level, cls="Brush")
    assert all(level.actors[n].cls == "Brush" for n in brushes)


def test_list_by_class_matches_a_qualified_actor_by_its_bare_suffix():
    # session start qualifies every actor's class (Engine.Brush, Engine.Light, ...) -- a bare
    # --class filter (the only form a user would type) must still find them (2026-06-21).
    from uedctl.model import Actor, Level
    level = Level()
    level.actors["B1"] = Actor(name="B1", cls="Engine.Brush")
    level.actors["L1"] = Actor(name="L1", cls="Engine.Light")
    level.order = ["B1", "L1"]
    assert list_actors(level, cls="Brush") == ["B1"]
    assert list_actors(level, cls="Engine.Brush") == ["B1"]      # exact qualified form still works


def test_list_by_name_glob():
    level = parse_t3d(read_fixture("level_small.t3d"))
    names = list_actors(level, name_glob="Brush*")
    assert all(n.startswith("Brush") for n in names)


def test_show_actor_returns_canonical_t3d():
    level = parse_t3d(read_fixture("add_light.t3d"))
    out = show_actor(level, "SpikeProbeLight999")
    assert "Begin Actor Class=Light Name=SpikeProbeLight999" in out


def test_describe_counts_classes():
    level = parse_t3d(read_fixture("level_small.t3d"))
    d = describe(level)
    assert d["total"] == len(level.actors)
    assert sum(d["by_class"].values()) == d["total"]


def _yawed_brush_t3d(name="B"):
    # A thin slab extending +X (a long face faces +Y), yawed 90°.
    return parse_t3d(
        "Begin Map\nBegin Actor Class=Brush Name=" + name + "\n"
        "    Location=(X=0,Y=0,Z=0)\n    Rotation=(Yaw=16384)\n"
        "    Begin Brush Name=M\n       Begin PolyList\n"
        "         Begin Polygon\n"
        "          Vertex +0.000000,+0.000000,+0.000000\n"
        "          Vertex +64.000000,+0.000000,+0.000000\n"
        "          Vertex +64.000000,+0.000000,+16.000000\n"
        "          Vertex +0.000000,+0.000000,+16.000000\n         End Polygon\n"
        "       End PolyList\n    End Brush\n    Name=\"" + name + "\"\nEnd Actor\nEnd Map"
    ).actors[name]


def test_list_polys_applies_actor_rotation_to_facing_and_centroid():
    # The single -Y-facing poly, yawed 90° about Z, faces +X in world space (-Y → +X under
    # (x,y)->(-y,x)). Its local centroid (32,0,8) orbits to world (0,32,8).
    rows = list_polys(_yawed_brush_t3d())
    assert rows[0]["facing"] == "+X"
    assert rows[0]["centroid"] == (0, 32, 8)


def test_list_polys_unrotated_brush_is_unchanged():
    a = make_brush_actor("B1", cube(64, 64, 64),
                         location=(Decimal(100), Decimal(200), Decimal(300)))
    rows = list_polys(a)
    # cube centered on origin → world centroids at Location ± 32 on each face axis
    facings = sorted(r["facing"] for r in rows)
    assert facings == ["+X", "+Y", "+Z", "-X", "-Y", "-Z"]


def test_list_vertices_applies_rotation_and_keeps_decimal_for_unrotated():
    # Unrotated: exact Decimal corners preserved (the existing contract).
    a = make_brush_actor("B1", cube(64, 64, 64),
                         location=(Decimal(100), Decimal(200), Decimal(300)))
    coords = {r["coord"] for r in list_vertices(a)}
    assert (Decimal(132), Decimal(232), Decimal(332)) in coords
    # Rotated: a +X corner orbits into +Y.
    rows = list_vertices(_yawed_brush_t3d())
    world = {(round(float(c[0])), round(float(c[1])), round(float(c[2]))) for c in
             (r["coord"] for r in rows)}
    assert (0, 64, 0) in world          # local (64,0,0) → world (0,64,0)


# ── resolve_actor_name / resolve_actor_names (Step 1 of name resolution) ─────


def _resolver_level():
    """Level with HelperLight0 (point) and Brush1 (brush, Group=cells)."""
    from uedctl.builders import cube
    lv = Level()
    lv.actors["HelperLight0"] = Actor(
        name="HelperLight0", cls="Engine.Light",
        props=[("Group", "cells")],
    )
    lv.actors["Brush1"] = Actor(
        name="Brush1", cls="Engine.Brush",
        props=[("Group", "cells")],
        brush=cube(64, 64, 64),
    )
    lv.order = ["HelperLight0", "Brush1"]
    return lv


def test_it_resolves_actor_name_exact():
    lv = _resolver_level()
    assert resolve_actor_name(lv, "Brush1") == "Brush1"


def test_it_resolves_actor_name_case_insensitively():
    lv = _resolver_level()
    assert resolve_actor_name(lv, "brush1") == "Brush1"
    assert resolve_actor_name(lv, "HELPERLIGHT0") == "HelperLight0"


def test_it_raises_on_missing_actor():
    lv = _resolver_level()
    try:
        resolve_actor_name(lv, "NoSuch")
        assert False, "expected KeyError"
    except KeyError as e:
        # e.args[0] must NOT have the extra quotes Python adds to str(KeyError)
        assert e.args[0] == "Actor not found: NoSuch"
        # Confirm the str() trap: str(e) adds surrounding quotes, args[0] does not.
        assert str(e) != "Actor not found: NoSuch"


def test_it_resolves_actor_names_case_insensitively():
    lv = _resolver_level()
    result = resolve_actor_names(lv, ["brush1", "helperlight0"])
    assert result == ["Brush1", "HelperLight0"]


def test_it_reports_all_missing_names():
    lv = _resolver_level()
    try:
        resolve_actor_names(lv, ["Brush1", "bad1", "bad2"])
        assert False, "expected KeyError"
    except KeyError as e:
        assert "bad1" in e.args[0]
        assert "bad2" in e.args[0]
        # Brush1 is valid; should NOT appear in the error message
        assert "Brush1" not in e.args[0]


def test_it_show_actor_fallback_resolves_case_insensitively():
    lv = _resolver_level()
    # show_actor with a plain name (no glob chars) falls through list_actors → fallback path
    out_lower = show_actor(lv, "brush1")
    out_canonical = show_actor(lv, "Brush1")
    assert out_lower == out_canonical
    assert "Brush1" in out_lower


def test_it_show_actor_fallback_raises_on_missing_exact_name():
    # Pinned the old silent-empty behavior; since the 2026-07-18 chore fix an exact-name miss
    # raises the named KeyError (globs still return "" — see the glob-miss test above).
    lv = _resolver_level()
    with pytest.raises(KeyError):
        show_actor(lv, "NoSuch")


def test_format_mover_keys_columns():
    from decimal import Decimal
    from uedctl.model import Actor
    from uedctl.query import format_mover_keys
    a = Actor(name="Lift", cls="Engine.Mover",
              props=[("KeyPos(1)", "(Z=256.000000)"), ("KeyRot(1)", "(Yaw=16384)"),
                     ("NumKeys", "2")],
              location=(Decimal(0), Decimal(0), Decimal("100")))
    out = format_mover_keys(a)
    lines = out.splitlines()
    assert lines[0].split() == ["idx", "world_pos", "world_rot", "off_pos", "off_rot"]
    assert lines[1].startswith("0") and "(base)" in lines[1]
    assert "0,0,100" in lines[1]
    assert "0,0,356" in lines[2] and "0,16384,0" in lines[2] and "0,0,256" in lines[2]


def test_show_actor_exact_miss_raises_named_keyerror():
    """A NO-glob name that matches nothing raises the named KeyError (dispatch → 'Actor not
    found: …', exit 2) — it used to return "" silently, rc 0 (board chore, fixed 2026-07-18)."""
    lv = _make_level_with_actors()
    with pytest.raises(KeyError) as ei:
        show_actor(lv, "NoSuchActor")
    assert "Actor not found: NoSuchActor" in ei.value.args[0]


def test_show_actor_glob_miss_stays_empty_and_silent():
    """A GLOB with zero matches stays grep-like: empty string, no exception — an empty match set
    is legitimate pipeline data (deliberately unchanged by the exact-miss fix)."""
    lv = _make_level_with_actors()
    assert show_actor(lv, "NoSuch*") == ""
