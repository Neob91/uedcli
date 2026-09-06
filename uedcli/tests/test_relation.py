from decimal import Decimal
import pytest
from uedcli import relation
from uedcli.builders import cube, make_brush_actor
from uedcli.preview import _poly_centroid_2d


def _brush(name, brush, loc=(0, 0, 0)):
    return make_brush_actor(name, brush, location=tuple(Decimal(str(c)) for c in loc))


def _face_by_normal(brush, normal):
    # cube()'s faces all carry item="OUTSIDE" (confirmed against uedcli/tests/test_model.py:76) --
    # there's no Top/Bottom/North ItemName to select by, so select by the builder's own advisory
    # `p.normal` instead (unrotated actors here, so local normal == world direction).
    return next(p for p in brush.polys if p.normal == normal)


def test_coplanar_opposite_normals():
    # Two 64x64x8 slabs stacked with zero gap: A's top face (Z=8) touches B's bottom face (Z=8).
    a = _brush("A", cube(64, 64, 8), loc=(0, 0, 0))
    b = _brush("B", cube(64, 64, 8), loc=(0, 0, 8))
    top_a = _face_by_normal(a.brush, (0.0, 0.0, 1.0))
    bottom_b = _face_by_normal(b.brush, (0.0, 0.0, -1.0))
    rel = relation.plane_relationship(a, top_a, b, bottom_b)
    assert rel is not None
    assert rel.plane == "coplanar"
    assert rel.distance == pytest.approx(0.0, abs=1e-3)
    assert rel.normal_a[2] == pytest.approx(1.0, abs=1e-6)
    assert rel.normal_b[2] == pytest.approx(-1.0, abs=1e-6)


def test_parallel_separated_positive_distance():
    # Same as above but B is 4uu higher: a real gap, not touching.
    a = _brush("A", cube(64, 64, 8), loc=(0, 0, 0))
    b = _brush("B", cube(64, 64, 8), loc=(0, 0, 12))
    top_a = _face_by_normal(a.brush, (0.0, 0.0, 1.0))
    bottom_b = _face_by_normal(b.brush, (0.0, 0.0, -1.0))
    rel = relation.plane_relationship(a, top_a, b, bottom_b)
    assert rel is not None
    assert rel.plane == "parallel"
    assert rel.distance == pytest.approx(4.0, abs=1e-3)


def test_parallel_interpenetrating_negative_distance():
    # B is only 4uu above A's top (A is 8 tall): B's bottom is 4uu INSIDE A's solid.
    a = _brush("A", cube(64, 64, 8), loc=(0, 0, 0))
    b = _brush("B", cube(64, 64, 8), loc=(0, 0, 4))
    top_a = _face_by_normal(a.brush, (0.0, 0.0, 1.0))
    bottom_b = _face_by_normal(b.brush, (0.0, 0.0, -1.0))
    rel = relation.plane_relationship(a, top_a, b, bottom_b)
    assert rel is not None
    assert rel.plane == "parallel"
    assert rel.distance == pytest.approx(-4.0, abs=1e-3)


def test_non_parallel_faces_are_neither():
    a = _brush("A", cube(64, 64, 8), loc=(0, 0, 0))
    b = _brush("B", cube(64, 64, 8), loc=(0, 0, 8))
    top_a = _face_by_normal(a.brush, (0.0, 0.0, 1.0))
    side_b = _face_by_normal(b.brush, (0.0, 1.0, 0.0))
    assert relation.plane_relationship(a, top_a, b, side_b) is None


def test_project_to_plane_z_normal_is_xy():
    pts = [(0.0, 0.0, 5.0), (10.0, 0.0, 5.0), (10.0, 20.0, 5.0)]
    uv = relation.project_to_plane(pts, (0.0, 0.0, 1.0))
    assert uv[0] == pytest.approx((0.0, 0.0))
    # second point is 10 world-units from the first, purely in-plane -> distance preserved
    du = uv[1][0] - uv[0][0]
    dv = uv[1][1] - uv[0][1]
    assert (du**2 + dv**2) ** 0.5 == pytest.approx(10.0, abs=1e-6)


def test_project_to_plane_preserves_relative_distances():
    # Any normal: projecting shouldn't change in-plane distances between points already on the plane.
    pts = [(0.0, 0.0, 0.0), (3.0, 4.0, 0.0)]  # 3-4-5 triangle leg in the XY plane
    uv = relation.project_to_plane(pts, (0.0, 0.0, 1.0))
    du, dv = uv[1][0] - uv[0][0], uv[1][1] - uv[0][1]
    assert (du**2 + dv**2) ** 0.5 == pytest.approx(5.0, abs=1e-6)


SQUARE = [(0.0, 0.0), (10.0, 0.0), (10.0, 10.0), (0.0, 10.0)]  # CCW, 10x10 at origin


def _shifted(poly, du, dv):
    return [(x + du, y + dv) for x, y in poly]


def test_footprint_none():
    b = _shifted(SQUARE, 100.0, 0.0)  # far away, no contact at all
    assert relation.classify_footprint_2d(SQUARE, b) == "none"


def test_footprint_vertex():
    b = _shifted(SQUARE, 10.0, 10.0)  # touches SQUARE only at corner (10, 10)
    assert relation.classify_footprint_2d(SQUARE, b) == "vertex"


def test_footprint_vertex_on_t_junction():
    # A diamond whose corner (10, 5) sits exactly on the MIDPOINT of SQUARE's x=10 edge -- no
    # shared vertex between the two polys, zero area overlap. Still a single-point touch.
    diamond = [(10.0, 5.0), (14.0, 9.0), (18.0, 5.0), (14.0, 1.0)]
    assert relation.classify_footprint_2d(SQUARE, diamond) == "vertex"


def test_footprint_edge():
    b = _shifted(SQUARE, 10.0, 0.0)  # butted end-to-end, shares the x=10 edge fully
    assert relation.classify_footprint_2d(SQUARE, b) == "edge"


def test_footprint_partial():
    b = _shifted(SQUARE, 5.0, 5.0)  # overlapping quadrant, neither contains the other
    assert relation.classify_footprint_2d(SQUARE, b) == "partial"


def test_footprint_contains_a_in_b():
    small = [(4.0, 4.0), (6.0, 4.0), (6.0, 6.0), (4.0, 6.0)]  # fully inside SQUARE
    assert relation.classify_footprint_2d(small, SQUARE) == "contains_a_in_b"
    assert relation.classify_footprint_2d(SQUARE, small) == "contains_b_in_a"


def test_footprint_coincident():
    assert relation.classify_footprint_2d(SQUARE, list(SQUARE)) == "coincident"


def test_deltas_centroid_matches_shoelace_centroid():
    a = [(0.0, 0.0), (10.0, 0.0), (10.0, 10.0), (0.0, 10.0)]
    b = [(20.0, 5.0), (30.0, 5.0), (30.0, 15.0), (20.0, 15.0)]
    d = relation.compute_deltas(a, b)
    ca = _poly_centroid_2d(a)
    cb = _poly_centroid_2d(b)
    assert d.centroid_u == pytest.approx(cb[0] - ca[0])
    assert d.centroid_v == pytest.approx(cb[1] - ca[1])


def test_deltas_edge_picks_closer_of_min_or_max():
    a = [(0.0, 0.0), (10.0, 0.0), (10.0, 10.0), (0.0, 10.0)]
    # b's U range [1, 11]: |min-min|=1, |max-max|=1 -> tie -> prefer U-min
    b = [(1.0, 0.0), (11.0, 0.0), (11.0, 10.0), (1.0, 10.0)]
    d = relation.compute_deltas(a, b)
    assert d.edge_u_label == "U-min"
    assert d.edge_u == pytest.approx(1.0)


def test_deltas_edge_picks_max_when_closer():
    a = [(0.0, 0.0), (100.0, 0.0), (100.0, 10.0), (0.0, 10.0)]
    b = [(90.0, 0.0), (98.0, 0.0), (98.0, 10.0), (90.0, 10.0)]  # b's max (98) is 2 from a's max (100)
    d = relation.compute_deltas(a, b)
    assert d.edge_u_label == "U-max"
    assert d.edge_u == pytest.approx(-2.0)


def _level(*actors):
    from uedcli.model import Level
    lv = Level()
    for a in actors:
        lv.actors[a.name] = a
    lv.order = [a.name for a in actors]
    return lv


def test_compute_reports_coplanar_pair_and_disjoint_brush():
    # cube() centers on the origin (half-height=32/4), so Leg's Z range is loc.z +/- 32 and
    # Floor's top is at -8+4=-4; loc.z=28 puts Leg's bottom (28-32=-4) flush on Floor's top --
    # loc=(0,0,0) (the plan's original number) leaves a 28uu gap, which is `parallel`, not
    # `coplanar` as this test asserts.
    a = _brush("Leg", cube(16, 16, 64), loc=(0, 0, 28))
    b = _brush("Floor", cube(200, 200, 8), loc=(-100, -100, -8))
    c = _brush("Lamp", cube(8, 8, 8), loc=(500, 500, 500))
    # An off-angle tilt, not just distance: an axis-aligned cube (even far away) would still have
    # SOME face normal parallel to Leg/Floor's (both are cardinal-aligned too), so it would never
    # actually land in `disjoint`. Tilting Lamp off every cardinal axis is what makes it genuinely
    # share no plane relationship with anything else named.
    c.props.insert(0, ("Rotation", "(Pitch=5000,Yaw=7000,Roll=3000)"))
    level = _level(a, b, c)
    report = relation.compute(level, ["Leg", "Floor", "Lamp"])
    assert report.brush_count == 3
    assert report.pair_count == 3  # C(3,2)
    assert report.disjoint == ["Lamp"]
    assert len(report.groups) == 1
    group = report.groups[0]
    assert {group.brush_a, group.brush_b} == {"Leg", "Floor"}
    assert len(group.shown) == 1  # default top=1
    assert group.shown[0].plane.plane == "coplanar"


def test_compute_unknown_name_raises():
    a = _brush("Leg", cube(16, 16, 64))
    level = _level(a)
    with pytest.raises(relation.RelationError):
        relation.compute(level, ["Leg", "NoSuchBrush"])


def test_compute_point_actor_raises():
    from uedcli.model import Actor
    a = _brush("Leg", cube(16, 16, 64))
    light = Actor(name="Light0", cls="Engine.Light", location=(0, 0, 0))
    level = _level(a, light)
    with pytest.raises(relation.RelationError):
        relation.compute(level, ["Leg", "Light0"])


def test_compute_ranks_footprint_quality_over_distance():
    # Two axis-aligned cubes of the same size, touching flush on one axis (Z: contains/coincident,
    # distance 0) and ALSO coincidentally sharing an X-facing plane far along X with zero overlap
    # (footprint: none) -- the "none" candidate must NOT win just because nothing beats distance=0
    # on ties; footprint quality is checked first, and only within the winning quality tier does
    # distance matter.
    a = _brush("A", cube(32, 32, 32), loc=(0, 0, 0))
    b = _brush("B", cube(32, 32, 32), loc=(0, 0, 32))  # flush on top of A
    level = _level(a, b)
    report = relation.compute(level, ["A", "B"], top=None)  # see every candidate for this assertion
    group = report.groups[0]
    assert group.candidate_count > 1  # more than one axis is parallel between two same-size cubes
    best = group.shown[0]
    assert best.footprint_2d in ("coincident", "contains_a_in_b", "contains_b_in_a")


def test_compute_top_caps_shown_but_not_candidate_count():
    a = _brush("A", cube(32, 32, 32), loc=(0, 0, 0))
    b = _brush("B", cube(32, 32, 32), loc=(0, 0, 32))
    level = _level(a, b)
    capped = relation.compute(level, ["A", "B"], top=1)
    full = relation.compute(level, ["A", "B"], top=None)
    assert len(capped.groups[0].shown) == 1
    assert capped.groups[0].candidate_count == full.groups[0].candidate_count
    assert len(full.groups[0].shown) == full.groups[0].candidate_count


def test_compute_rejects_invalid_top():
    a = _brush("A", cube(16, 16, 16))
    b = _brush("B", cube(16, 16, 16), loc=(0, 0, 16))
    level = _level(a, b)
    with pytest.raises(relation.RelationError):
        relation.compute(level, ["A", "B"], top=0)


def test_format_report_matches_expected_shape():
    # FloorPad is CENTERED at the origin (`--at`/`location` is a box's CENTER, not a corner --
    # confirmed against uedcli/cli/commands/brush/build.py:275, `location=at` passed straight to
    # make_brush_actor), so its [-100,100]x[-100,100] footprint fully contains LegFoot's
    # [-8,8]x[-8,8]. loc=(-100,-100,-8) (the plan's original number) would off-center it to
    # [-200,0]x[-200,0], only corner-overlapping LegFoot instead of containing it.
    a = _brush("LegFoot", cube(16, 16, 4), loc=(0, 0, 4))
    b = _brush("FloorPad", cube(200, 200, 8), loc=(0, 0, -8))
    level = _level(a, b)
    report = relation.compute(level, ["LegFoot", "FloorPad"])
    text = relation.format_report(report)
    assert "LegFoot <-> FloorPad" in text
    assert "plane: parallel" in text
    assert "footprint_2d: contains" in text
    assert "checked: 2 brushes, 1 pairs, every face" in text
    assert "disjoint:" not in text  # both brushes are involved, nothing left over


def test_format_report_never_prints_negative_zero():
    # Two same-size cubes stacked exactly flush: the coplanar pair's `distance` is computed as a
    # tiny float residual of 0.0 that can come out as -0.0 -- must never print as "-0.000uu", which
    # would misread as a hairline interpenetration instead of an exact match.
    a = _brush("A", cube(32, 32, 32), loc=(0, 0, 0))
    b = _brush("B", cube(32, 32, 32), loc=(0, 0, 32))
    level = _level(a, b)
    report = relation.compute(level, ["A", "B"], top=None)
    text = relation.format_report(report)
    assert "-0.000" not in text


def test_format_report_lists_disjoint_brushes():
    a = _brush("LegFoot", cube(16, 16, 4), loc=(0, 0, 4))
    b = _brush("FloorPad", cube(200, 200, 8), loc=(0, 0, -8))
    c = _brush("Lamp", cube(8, 8, 8), loc=(500, 500, 500))
    # Off-axis tilt: an axis-aligned Lamp (even far away) always shares SOME parallel face normal
    # with two other axis-aligned cubes, so it would never land in `disjoint` (see the identical
    # fix + comment on test_compute_reports_coplanar_pair_and_disjoint_brush above).
    c.props.insert(0, ("Rotation", "(Pitch=5000,Yaw=7000,Roll=3000)"))
    level = _level(a, b, c)
    report = relation.compute(level, ["LegFoot", "FloorPad", "Lamp"])
    text = relation.format_report(report)
    assert "disjoint: {Lamp}" in text
    assert "checked: 3 brushes, 3 pairs, every face" in text


def test_format_report_states_shown_of_candidates_when_capped():
    a = _brush("A", cube(32, 32, 32), loc=(0, 0, 0))
    b = _brush("B", cube(32, 32, 32), loc=(0, 0, 32))
    level = _level(a, b)
    report = relation.compute(level, ["A", "B"], top=1)  # default cap
    text = relation.format_report(report)
    total = report.groups[0].candidate_count
    assert total > 1
    assert f"(1 of {total} candidates shown)" in text


def test_format_report_collapses_all_none_group_to_one_line():
    # Two cubes far enough apart on every axis that every candidate is footprint_2d "none".
    a = _brush("Far1", cube(16, 16, 16), loc=(0, 0, 0))
    b = _brush("Far2", cube(16, 16, 16), loc=(1000, 1000, 0))
    level = _level(a, b)
    report = relation.compute(level, ["Far1", "Far2"], top=None)
    assert all(p.footprint_2d == "none" for p in report.groups[0].shown)
    text = relation.format_report(report)
    assert "Far1 <-> Far2: no overlapping face pairs" in text
    assert "plane:" not in text  # collapsed -- no full block fields printed


def test_compute_pairs_pins_to_exact_selectors():
    a = _brush("A", cube(32, 32, 32), loc=(0, 0, 0))
    b = _brush("B", cube(32, 32, 32), loc=(0, 0, 32))
    level = _level(a, b)
    top_a = next(i for i, p in enumerate(a.brush.polys) if p.normal == (0.0, 0.0, 1.0))
    bottom_b = next(i for i, p in enumerate(b.brush.polys) if p.normal == (0.0, 0.0, -1.0))
    report = relation.compute_pairs(level, f"A:{top_a}", [f"B:{bottom_b}"])
    assert len(report.groups) == 1
    assert len(report.groups[0].shown) == 1  # pinned to one pair, no ranking needed
    assert report.groups[0].shown[0].plane.plane == "coincident" or report.groups[0].shown[0].plane.plane == "coplanar"


def test_compute_pairs_bare_names_ranks_like_compute():
    a = _brush("A", cube(32, 32, 32), loc=(0, 0, 0))
    b = _brush("B", cube(32, 32, 32), loc=(0, 0, 32))
    level = _level(a, b)
    pair_report = relation.compute_pairs(level, "A", ["B"], top=None)
    full_report = relation.compute(level, ["A", "B"], top=None)
    assert pair_report.groups[0].candidate_count == full_report.groups[0].candidate_count


def test_compute_pairs_mixed_bare_and_pinned_selectors():
    # REF bare (ranks all its polys) against TARGET pinned to one exact poly.
    a = _brush("A", cube(32, 32, 32), loc=(0, 0, 0))
    b = _brush("B", cube(32, 32, 32), loc=(0, 0, 32))
    level = _level(a, b)
    bottom_b = next(i for i, p in enumerate(b.brush.polys) if p.normal == (0.0, 0.0, -1.0))
    report = relation.compute_pairs(level, "A", [f"B:{bottom_b}"], top=None)
    assert report.groups
    assert all(p.poly_b == bottom_b for p in report.groups[0].shown)


def test_compute_pairs_same_brush_rejected_by_default():
    a = _brush("A", cube(32, 32, 32))
    level = _level(a)
    with pytest.raises(relation.RelationError, match="allow-self"):
        relation.compute_pairs(level, "A:0", ["A:1"])


def test_compute_pairs_allow_self_permits_same_brush():
    a = _brush("A", cube(32, 32, 32))
    level = _level(a)
    report = relation.compute_pairs(level, "A", ["A"], top=None, allow_self=True)
    assert report.brush_count == 1
    # every shown pair excludes the trivial (idx, idx) self-match
    assert all(not (p.poly_a == p.poly_b) for p in report.groups[0].shown) if report.groups else True


def test_compute_pairs_single_target_disjoint_never_reports_exactly_one():
    # With exactly ONE target, disjoint is {ref_name, target_name} (both or neither) -- this
    # invariant is specific to the single-target case; with multiple targets a length-1 disjoint
    # set is legitimate (see test_compute_pairs_partial_disjoint_with_multiple_targets).
    a = _brush("A", cube(16, 16, 16), loc=(0, 0, 0))
    b = _brush("B", cube(16, 16, 16), loc=(500, 500, 500))
    b.props.insert(0, ("Rotation", "(Pitch=5000,Yaw=7000,Roll=3000)"))
    level = _level(a, b)
    report = relation.compute_pairs(level, "A", ["B"])
    assert len(report.disjoint) in (0, 2)


def test_compute_pairs_partial_disjoint_with_multiple_targets():
    # ref relates to Near but NOT Far -- only Far should be disjoint (a length-1 disjoint set,
    # which the single-target invariant above says can't happen there, but is normal here since
    # `measure` never compares targets against each other, only each against ref).
    ref = _brush("Wall", cube(64, 64, 8), loc=(0, 0, 0))
    near = _brush("Near", cube(64, 64, 8), loc=(0, 0, 8))          # flush on top -- relates
    far = _brush("Far", cube(16, 16, 16), loc=(500, 500, 500))
    far.props.insert(0, ("Rotation", "(Pitch=5000,Yaw=7000,Roll=3000)"))  # no face stays parallel
    level = _level(ref, near, far)
    report = relation.compute_pairs(level, "Wall", ["Near", "Far"])
    assert report.disjoint == ["Far"]
    assert {g.brush_b for g in report.groups} == {"Near"}


def test_compute_pairs_unknown_selector_raises():
    a = _brush("A", cube(16, 16, 16))
    level = _level(a)
    with pytest.raises(relation.RelationError):
        relation.compute_pairs(level, "A", ["NoSuchBrush"])


def test_compute_pairs_multiple_distinct_targets_get_one_group_each():
    ref = _brush("Wall", cube(64, 64, 8), loc=(0, 0, 0))
    near = _brush("Near", cube(64, 64, 8), loc=(0, 0, 8))
    far = _brush("Far", cube(64, 64, 8), loc=(0, 0, 100))
    level = _level(ref, near, far)
    report = relation.compute_pairs(level, "Wall", ["Near", "Far"])
    assert {g.brush_b for g in report.groups} == {"Near", "Far"}


def test_compute_pairs_three_repeated_target_tokens_union_into_one_group():
    a = _brush("A", cube(32, 32, 32), loc=(0, 0, 0))
    b = _brush("B", cube(32, 32, 32), loc=(0, 0, 32))
    level = _level(a, b)
    top_a = next(i for i, p in enumerate(a.brush.polys) if p.normal == (0.0, 0.0, 1.0))
    plus_x_a = next(i for i, p in enumerate(a.brush.polys) if p.normal == (1.0, 0.0, 0.0))
    minus_x_a = next(i for i, p in enumerate(a.brush.polys) if p.normal == (-1.0, 0.0, 0.0))
    report = relation.compute_pairs(
        level, "B", [f"A:{top_a}", f"A:{plus_x_a}", f"A:{minus_x_a}"], top=None)
    assert len(report.groups) == 1
    assert report.groups[0].brush_b == "A"
    seen = {p.poly_b for p in report.groups[0].shown}
    assert seen == {top_a, plus_x_a, minus_x_a}


def test_compute_pairs_repeated_target_brush_unions_poly_selectors():
    # Two tokens naming the SAME brush with different pinned polys (as two rows of a `find --top
    # all` result would) must fold into ONE group covering BOTH polys, not two groups/duplicates.
    a = _brush("A", cube(32, 32, 32), loc=(0, 0, 0))
    b = _brush("B", cube(32, 32, 32), loc=(0, 0, 32))
    level = _level(a, b)
    top_a = next(i for i, p in enumerate(a.brush.polys) if p.normal == (0.0, 0.0, 1.0))
    side_a = next(i for i, p in enumerate(a.brush.polys) if p.normal == (1.0, 0.0, 0.0))
    report = relation.compute_pairs(level, "B", [f"A:{top_a}", f"A:{side_a}"], top=None)
    assert len(report.groups) == 1
    assert report.groups[0].brush_b == "A"
    seen_a_polys = {p.poly_b for p in report.groups[0].shown}
    assert seen_a_polys == {top_a, side_a}   # BOTH indices present -- proves the union, not a drop


def test_find_candidates_ranks_and_caps_per_candidate():
    ref = _brush("Wall", cube(64, 64, 8), loc=(0, 0, 0))
    near = _brush("Near", cube(64, 64, 8), loc=(0, 0, 8))     # flush on top
    far = _brush("Far", cube(64, 64, 8), loc=(0, 0, 100))     # same axis, far gap
    level = _level(ref, near, far)
    matches = relation.find_candidates(level, "Wall", ["Near", "Far"], top=1).matches
    assert {m.candidate for m in matches} <= {"Near", "Far"}
    near_matches = [m for m in matches if m.candidate == "Near"]
    assert len(near_matches) == 1
    assert near_matches[0].pair.plane.plane == "coplanar"


def test_find_candidates_max_gap_filters_out_far():
    ref = _brush("Wall", cube(64, 64, 8), loc=(0, 0, 0))
    near = _brush("Near", cube(64, 64, 8), loc=(0, 0, 8))
    far = _brush("Far", cube(64, 64, 8), loc=(0, 0, 100))
    level = _level(ref, near, far)
    matches = relation.find_candidates(level, "Wall", ["Near", "Far"], max_gap=1.0).matches
    assert {m.candidate for m in matches} == {"Near"}


def test_find_candidates_min_gap_filters_out_near():
    ref = _brush("Wall", cube(64, 64, 8), loc=(0, 0, 0))
    near = _brush("Near", cube(64, 64, 8), loc=(0, 0, 8))
    far = _brush("Far", cube(64, 64, 8), loc=(0, 0, 100))
    level = _level(ref, near, far)
    matches = relation.find_candidates(level, "Wall", ["Near", "Far"], min_gap=70.0).matches
    assert {m.candidate for m in matches} == {"Far"}


def test_find_candidates_footprint_filter():
    ref = _brush("Wall", cube(64, 64, 8), loc=(0, 0, 0))
    small = _brush("Small", cube(8, 8, 8), loc=(0, 0, 8))     # small footprint, contained
    level = _level(ref, small)
    contained = relation.find_candidates(level, "Wall", ["Small"], footprint={"contains"}).matches
    assert len(contained) == 1
    none_only = relation.find_candidates(level, "Wall", ["Small"], footprint={"none"}).matches
    assert none_only == []


def test_find_candidates_plane_filter():
    ref = _brush("Wall", cube(64, 64, 8), loc=(0, 0, 0))
    coplanar = _brush("Coplanar", cube(64, 64, 8), loc=(0, 0, 8))
    parallel = _brush("Parallel", cube(64, 64, 8), loc=(0, 0, 20))
    level = _level(ref, coplanar, parallel)
    coplanar_only = relation.find_candidates(
        level, "Wall", ["Coplanar", "Parallel"], plane="coplanar").matches
    assert {m.candidate for m in coplanar_only} == {"Coplanar"}


def test_find_candidates_min_gap_exceeds_max_gap_raises():
    a = _brush("Wall", cube(16, 16, 16))
    level = _level(a)
    with pytest.raises(relation.RelationError):
        relation.find_candidates(level, "Wall", [], min_gap=10.0, max_gap=1.0)


def test_find_candidates_near_miss_count_surfaces_hidden_footprint_none_pairs():
    # Near is offset diagonally (both X and Y) from Wall -- every parallel-face pair has
    # footprint_2d "none" (their projected footprints genuinely don't overlap on either axis),
    # and the true in-plane gap on the closest pairs is well within --max-gap. The implicit
    # footprint=none exclusion hides these from `matches`, but they must be counted in
    # near_miss_count so a caller isn't left thinking nothing is nearby at all.
    ref = _brush("Wall", cube(64, 64, 8), loc=(0, 0, 0))
    near = _brush("Near", cube(64, 64, 8), loc=(100, 100, 0))
    level = _level(ref, near)
    result = relation.find_candidates(level, "Wall", ["Near"], max_gap=200.0)
    assert result.matches == []
    assert result.near_miss_count > 0


def test_find_candidates_near_miss_count_is_distinct_candidate_faces_not_pairs():
    # Regression: near_miss_count must count DISTINCT (candidate, poly_b) faces, not raw
    # ref-vs-candidate PAIRS -- a single candidate face can pair with more than one ref face
    # (e.g. a cube's own +X face is "parallel" to a ref's own +X AND -X faces), which would
    # otherwise double- (or worse) count the same near candidate face. Each of Near's 6 faces
    # pairs with 2 of Wall's (same axis, either direction) -- 12 raw qualifying pairs total --
    # but the count must read exactly 6 distinct Near faces, not 12 raw pairs.
    ref = _brush("Wall", cube(64, 64, 8), loc=(0, 0, 0))
    near = _brush("Near", cube(64, 64, 8), loc=(100, 100, 0))
    level = _level(ref, near)
    result = relation.find_candidates(level, "Wall", ["Near"], max_gap=200.0)
    assert result.near_miss_count == 6


def test_find_candidates_near_miss_count_zero_when_footprint_explicit():
    # Once the caller explicitly names a --footprint set (even one that includes "none"), the
    # implicit rule isn't "hiding" anything -- near_miss_count must read 0, not double-count.
    ref = _brush("Wall", cube(64, 64, 8), loc=(0, 0, 0))
    near = _brush("Near", cube(64, 64, 8), loc=(100, 0, 0))
    level = _level(ref, near)
    result = relation.find_candidates(level, "Wall", ["Near"], max_gap=200.0, footprint={"none"})
    assert len(result.matches) == 1
    assert result.near_miss_count == 0


def test_find_candidates_near_miss_count_ignores_perpendicular_only_alignment():
    # Regression for a real false-positive: Far is 1000uu away from Wall along X only, so its
    # Y/Z-normal faces sit at the SAME Y/Z position as Wall's (only X differs) -- those pairs'
    # `plane.distance` (measured along THEIR OWN normal, Y or Z) reads near 0, even though the
    # true in-plane (X) separation is ~1000uu. A near-miss check that only looked at
    # `plane.distance` would wrongly call this "nearby"; it must also require the actual
    # footprint gap to be within --max-gap.
    ref = _brush("Wall", cube(64, 64, 8), loc=(0, 0, 0))
    far = _brush("Far", cube(64, 64, 8), loc=(1000, 0, 0))
    level = _level(ref, far)
    result = relation.find_candidates(level, "Wall", ["Far"], max_gap=1.0)
    assert result.matches == []
    assert result.near_miss_count == 0


def test_passes_gap_and_plane_max_gap_zero_tolerates_float_dust():
    # A pair whose true gap is exactly 0 but carries float residual (e.g. from a rotated
    # placement) must still pass --max-gap 0 -- this is the exact false-negative a real subagent
    # hit: measure reported "-0.000uu" (genuinely flush) but find --max-gap 0 found nothing.
    ref = _brush("Wall", cube(64, 64, 8), loc=(0, 0, 0))
    top_a = _face_by_normal(ref.brush, (0.0, 0.0, 1.0))
    near = _brush("Near", cube(64, 64, 8), loc=(0, 0, 8))
    bottom_b = _face_by_normal(near.brush, (0.0, 0.0, -1.0))
    rel = relation.plane_relationship(ref, top_a, near, bottom_b)
    dusty = relation.PlaneRelation(
        plane=rel.plane, normal_a=rel.normal_a, normal_b=rel.normal_b,
        distance=-1e-9)   # true zero, with float dust
    pair = relation.PairFace(brush_a="Wall", poly_a=0, brush_b="Near", poly_b=0,
                              plane=dusty, footprint_2d="contains_a_in_b",
                              deltas=relation.Deltas(centroid_u=0, centroid_v=0,
                                                      edge_u_label="U-min", edge_u=0,
                                                      edge_v_label="V-min", edge_v=0),
                              footprint_gap=0.0)
    assert relation._passes_gap_and_plane(pair, max_gap=0.0, min_gap=None, plane=None)


def test_footprint_bbox_gap_zero_when_overlapping():
    assert relation._footprint_bbox_gap([(0, 0), (10, 0), (10, 10), (0, 10)],
                                         [(5, 5), (15, 5), (15, 15), (5, 15)]) == 0.0


def test_footprint_bbox_gap_single_axis_separation():
    # Same V range, U ranges separated by exactly 4 (10 to 14).
    a = [(0, 0), (10, 0), (10, 10), (0, 10)]
    b = [(14, 0), (24, 0), (24, 10), (14, 10)]
    assert relation._footprint_bbox_gap(a, b) == 4.0


def test_find_candidates_near_miss_disabled_without_max_gap():
    # With no --max-gap given at all, there's no bound to judge "near" against -- near_miss_count
    # must stay 0 rather than treating every footprint=none pair (however far apart) as a miss.
    ref = _brush("Wall", cube(64, 64, 8), loc=(0, 0, 0))
    near = _brush("Near", cube(64, 64, 8), loc=(100, 100, 0))    # the genuinely-near case
    level = _level(ref, near)
    result = relation.find_candidates(level, "Wall", ["Near"])   # max_gap omitted
    assert result.matches == []
    assert result.near_miss_count == 0


def test_find_candidates_near_miss_respects_min_gap():
    # Of Near's 6 faces, 2 (poly_b 4 and 5) only pair with ref faces at near-zero perpendicular
    # distance (0 and -8) -- --min-gap 10 must exclude those two from near_miss_count (they fail
    # a real predicate, not just the implicit footprint rule), while the other 4 faces (whose
    # best pairing distance is >= 10) still qualify.
    ref = _brush("Wall", cube(64, 64, 8), loc=(0, 0, 0))
    near = _brush("Near", cube(64, 64, 8), loc=(100, 100, 0))
    level = _level(ref, near)
    unbounded = relation.find_candidates(level, "Wall", ["Near"], max_gap=200.0)
    assert unbounded.near_miss_count == 6
    with_min_gap = relation.find_candidates(level, "Wall", ["Near"], max_gap=200.0, min_gap=10.0)
    assert with_min_gap.near_miss_count == 4


def test_footprint_bbox_gap_diagonal_separation():
    # U ranges separated by 3, V ranges separated by 4 -> hypot(3,4) = 5.
    a = [(0, 0), (10, 0), (10, 10), (0, 10)]
    b = [(13, 14), (23, 14), (23, 24), (13, 24)]
    assert relation._footprint_bbox_gap(a, b) == 5.0


def test_compute_set_translation_gap_only():
    ref = _brush("Ref", cube(64, 64, 8), loc=(0, 0, 0))
    tgt = _brush("Tgt", cube(64, 64, 8), loc=(0, 0, 8))   # flush, gap=0 today
    level = _level(ref, tgt)
    top_ref = next(i for i, p in enumerate(ref.brush.polys) if p.normal == (0.0, 0.0, 1.0))
    bottom_tgt = next(i for i, p in enumerate(tgt.brush.polys) if p.normal == (0.0, 0.0, -1.0))
    name, ref_name, move = relation.compute_set_translation(
        level, f"Tgt:{bottom_tgt}", f"Ref:{top_ref}", gap=10.0)
    assert name == "Tgt"
    assert ref_name == "Ref"
    assert move == pytest.approx((0.0, 0.0, 10.0), abs=1e-6)  # was 0 gap, now 10 along +Z normal


def test_compute_set_translation_centroid_only_leaves_gap():
    ref = _brush("Ref", cube(64, 64, 8), loc=(0, 0, 0))
    tgt = _brush("Tgt", cube(64, 64, 8), loc=(20, 0, 8))  # offset 20uu in X (world U or V)
    level = _level(ref, tgt)
    top_ref = next(i for i, p in enumerate(ref.brush.polys) if p.normal == (0.0, 0.0, 1.0))
    bottom_tgt = next(i for i, p in enumerate(tgt.brush.polys) if p.normal == (0.0, 0.0, -1.0))
    name, ref_name, move = relation.compute_set_translation(
        level, f"Tgt:{bottom_tgt}", f"Ref:{top_ref}", centroid_v=0.0)
    # gap (Z) untouched: the move has zero Z component
    assert move[2] == pytest.approx(0.0, abs=1e-6)
    # some in-plane component is non-zero (the 20uu offset gets nulled on whichever axis U mapped to)
    assert abs(move[0]) + abs(move[1]) > 1.0


def test_compute_set_translation_no_flags_raises():
    ref = _brush("Ref", cube(16, 16, 16), loc=(0, 0, 0))
    tgt = _brush("Tgt", cube(16, 16, 16), loc=(0, 0, 16))
    level = _level(ref, tgt)
    with pytest.raises(relation.RelationError, match="at least one"):
        relation.compute_set_translation(level, "Tgt:0", "Ref:0")


def test_compute_set_translation_non_planar_pair_raises():
    ref = _brush("Ref", cube(64, 64, 8), loc=(0, 0, 0))
    tgt = _brush("Tgt", cube(64, 64, 8), loc=(0, 0, 8))
    level = _level(ref, tgt)
    top_ref = next(i for i, p in enumerate(ref.brush.polys) if p.normal == (0.0, 0.0, 1.0))
    side_tgt = next(i for i, p in enumerate(tgt.brush.polys) if p.normal == (1.0, 0.0, 0.0))
    with pytest.raises(relation.RelationError):
        relation.compute_set_translation(level, f"Tgt:{side_tgt}", f"Ref:{top_ref}", gap=0.0)


def test_compute_set_translation_bare_name_rejected():
    ref = _brush("Ref", cube(16, 16, 16), loc=(0, 0, 0))
    tgt = _brush("Tgt", cube(16, 16, 16), loc=(0, 0, 16))
    level = _level(ref, tgt)
    with pytest.raises(relation.RelationError):
        relation.compute_set_translation(level, "Tgt", "Ref:0", gap=0.0)  # TARGET must be BRUSH:idx


def test_compute_set_translation_same_brush_rejected():
    a = _brush("A", cube(16, 16, 16))
    level = _level(a)
    with pytest.raises(relation.RelationError):
        relation.compute_set_translation(level, "A:0", "A:1", gap=0.0)


def test_compute_set_translation_edge_u_min_explicit():
    ref = _brush("Ref", cube(64, 64, 8), loc=(0, 0, 0))
    tgt = _brush("Tgt", cube(64, 64, 8), loc=(0, 0, 8))
    level = _level(ref, tgt)
    top_ref = next(i for i, p in enumerate(ref.brush.polys) if p.normal == (0.0, 0.0, 1.0))
    bottom_tgt = next(i for i, p in enumerate(tgt.brush.polys) if p.normal == (0.0, 0.0, -1.0))
    name, ref_name, move = relation.compute_set_translation(
        level, f"Tgt:{bottom_tgt}", f"Ref:{top_ref}", edge_u=("min", 5.0))
    assert move[2] == pytest.approx(0.0, abs=1e-6)  # gap untouched
