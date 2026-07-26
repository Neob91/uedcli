import copy
import math
from decimal import Decimal

from uedcli.model import parse_t3d
import pytest

from uedcli.preview import (
    BG, FRONT, WHITE, DensityGrid, AnnotationSpec, _DIM_ALPHA, _DecalPlan, _FRAME_PAD, _LabelItem,
    _ONFACE_FILL, _ONFACE_MIN_TEXEL_PX,
    _box_fits_2d, _feasible_centers, _new_buf, _line, _point_in_poly,
    _decal_opacity, _draw_overlap_keyline, _draw_painted_decal, _face_decal_basis, _framing,
    _label_size, _least_dense_anchor,
    _legend_reserve, _legend_rows, _max_inscribed_box, _occluder_count, _onface_candidates,
    _place_labels, _plan_onface_texture, _plan_px_area, _poly_is_convex_2d, _rect_overlap_area,
    _resolve_decals, _rects_overlap, _text_bitmap, assign_tints,
    parse_annotation_spec, render_brush_pgm, render_brushes_pgm, render_quad_pgm,
)
from uedcli.tests.conftest import read_fixture


def _body(ppm):
    i = 0
    for _ in range(3):                 # skip P6 / "w h" / maxval header lines
        i = ppm.index(b"\n", i) + 1
    return ppm[i:]


def _pixels(ppm):
    b = _body(ppm)
    return [tuple(b[k:k + 3]) for k in range(0, len(b), 3)]


def _nonbg(ppm):
    # "content" pixels = anything that is NOT the (grey) background. Must compare to BG, not white:
    # the background is light grey and the label knockout boxes are white, so a white-based count
    # would read the boxes as content-absent and invert.
    return sum(1 for p in _pixels(ppm) if p != (BG, BG, BG))


def _colors(ppm):
    return set(_pixels(ppm))


def _brush():
    return parse_t3d(read_fixture("brush_subtract.t3d")).actors["Brush938"]


def test_render_emits_color_ppm_header():
    pgm = render_brush_pgm(_brush(), view="top", size=128)
    assert pgm.startswith(b"P6\n128 128\n255\n")
    assert len(pgm) == len(b"P6\n128 128\n255\n") + 128 * 128 * 3


def test_render_draws_some_edges():
    assert _nonbg(render_brush_pgm(_brush(), view="top", size=128)) > 0


def test_front_black_back_grey():
    cols = _colors(render_brush_pgm(_brush(), view="iso", size=256, annotations=AnnotationSpec.all()))
    assert (0, 0, 0) in cols          # front-facing edges black
    assert (165, 165, 165) in cols    # obscured (back) edges light grey


def test_poly_index_labels_add_pixels():
    labeled = render_brush_pgm(_brush(), view="iso", size=256, annotations=AnnotationSpec.all())
    plain = render_brush_pgm(_brush(), view="iso", size=256, annotations=AnnotationSpec.none())
    assert _nonbg(labeled) > _nonbg(plain)


def test_highlight_poly_is_the_brushes_vivid_hue_and_bolder():
    # A highlighted poly draws in its brush's OWN vivid CSG front hue (NOT red) + a bolder line.
    # Brush938 is a subtracted brush → gold front.
    from uedcli.preview import _CSG_PALETTE
    vivid = _CSG_PALETTE["subtract"][0]
    plain = render_brush_pgm(_brush(), view="iso", size=256, annotations=AnnotationSpec.all())
    hi = render_brush_pgm(_brush(), view="iso", size=256, annotations=AnnotationSpec.all(), highlight_polys={("Brush938", 0)})
    assert hi != plain
    assert vivid in _colors(hi)               # highlighted poly in the brush's vivid hue
    assert vivid not in _colors(plain)
    assert (220, 0, 0) not in _colors(hi)     # red is retired


def test_csg_color_paints_subtracted_brush_gold():
    from uedcli.preview import _CSG_PALETTE
    front, back = _CSG_PALETTE["subtract"]
    cols = _colors(render_brush_pgm(_brush(), view="iso", size=256, annotations=AnnotationSpec.none(), color_by_csg=True))
    assert front in cols and back in cols     # facing shade pair survives; brush is gold not black
    assert (0, 0, 0) not in cols              # no black wireframe when coloured by CSG


def test_zoom_region_reframes():
    from uedcli.rotation import world_vertices
    a = _brush()
    # Frame a region around a vertex's ACTUAL rendered world position (honours
    # Location/Rotation/PrePivot — this fixture has a nonzero PrePivot), not Location+local.
    wx, wy, wz = world_vertices(a)[0]
    region = (wx - 50, wy - 50, wz - 50, wx + 50, wy + 50, wz + 50)
    full = render_brush_pgm(a, view="iso", size=256, annotations=AnnotationSpec.none())
    zoom = render_brush_pgm(a, view="iso", size=256, annotations=AnnotationSpec.none(), region=region)
    assert zoom != full and _nonbg(zoom) > 0


def test_quad_view_renders_four_panes():
    pgm = render_quad_pgm(_brush(), size=256)
    assert pgm.startswith(b"P6\n256 256\n255\n")
    assert (110, 110, 110) in _colors(pgm) and _nonbg(pgm) > 0   # divider + content


def test_iso_view_renders():
    pgm = render_brush_pgm(_brush(), view="iso", size=128)
    assert pgm.startswith(b"P6\n128 128\n255\n")
    assert _nonbg(pgm) > 0


def test_place_labels_clamps_a_near_edge_anchor_inside_the_frame():
    size, scale = 256, 2
    items = [_LabelItem(anchor=(2, 2), text="12", scale=scale, color=FRONT)]   # at the top-left corner
    [placed] = _place_labels(items, size)
    (lx, ly), text = placed.pos, placed.text
    w, h = _label_size(text, scale)
    x0, y0, x1, y1 = lx - w // 2 - 2, ly - h // 2 - 2, lx + w // 2 + 2, ly + h // 2 + 2
    assert x0 >= 0 and y0 >= 0 and x1 < size and y1 < size
    assert placed.anchor == (2, 2)               # leader still points at the TRUE centroid


def test_place_labels_clamps_a_near_far_edge_anchor_inside_the_frame():
    size, scale = 256, 2
    items = [_LabelItem(anchor=(254, 254), text="7", scale=scale, color=FRONT)]  # bottom-right corner
    [placed] = _place_labels(items, size)
    (lx, ly), text = placed.pos, placed.text
    w, h = _label_size(text, scale)
    x0, y0, x1, y1 = lx - w // 2 - 2, ly - h // 2 - 2, lx + w // 2 + 2, ly + h // 2 + 2
    assert x0 >= 0 and y0 >= 0 and x1 < size and y1 < size


def test_place_labels_avoids_overlap_for_several_close_anchors():
    size, scale = 256, 2
    items = [_LabelItem(anchor=(128, 128), text=str(i), scale=scale, color=FRONT) for i in range(5)]
    placed = _place_labels(items, size)
    rects = []
    for p in placed:
        lx, ly = p.pos
        w, h = _label_size(p.text, scale)
        rects.append((lx - w // 2 - 3, ly - h // 2 - 3, lx + w // 2 + 3, ly + h // 2 + 3))
    for i in range(len(rects)):
        for j in range(i + 1, len(rects)):
            assert not _rects_overlap(rects[i], rects[j]), (i, j, rects[i], rects[j])


def test_place_labels_keeps_a_label_off_an_occupied_marker_rect():
    size, scale = 256, 2
    marker = (120, 120, 136, 136)                          # a pre-occupied footprint at the anchor
    items = [_LabelItem(anchor=(128, 128), text="7", scale=scale, color=FRONT)]
    [placed] = _place_labels(items, size, occupied=[marker])
    lx, ly = placed.pos
    w, h = _label_size("7", scale)
    box = (lx - w // 2 - 3, ly - h // 2 - 3, lx + w // 2 + 3, ly + h // 2 + 3)
    assert not _rects_overlap(box, marker)                 # label nudged off the marker
    assert placed.pos != placed.anchor                     # so a leader/dot is drawn


def test_place_labels_saturated_cluster_still_places_all_in_frame():
    # Force the least-cost fallback: many labels at one anchor in a tiny frame → all still placed,
    # boxes clamped in-frame, no crash (pins the for-loop fallback the greedy fast path skips).
    size, scale = 40, 2
    items = [_LabelItem(anchor=(20, 20), text=str(i), scale=scale, color=FRONT) for i in range(12)]
    placed = _place_labels(items, size)
    assert len(placed) == 12
    for p in placed:
        lx, ly = p.pos
        w, h = _label_size(p.text, scale)
        assert 0 <= lx - w // 2 - 2 and lx + w // 2 + 2 < size
        assert 0 <= ly - h // 2 - 2 and ly + h // 2 + 2 < size


def _point(name, cls, loc):
    from uedcli.model import Actor
    return Actor(name=name, cls=cls, location=(Decimal(loc[0]), Decimal(loc[1]), Decimal(loc[2])))


def test_point_actor_without_render_data_is_skipped():
    # A point actor with no render_data entry contributes nothing (blank on a point-only scene).
    ppm = render_brushes_pgm([_point("L", "Engine.Light", (0, 0, 0))], view="top", size=128)
    assert _nonbg(ppm) == 0


def test_point_marker_renders_and_label_is_toggleable():
    from uedcli.preview import PointRender
    rd = {"L": PointRender(label="Torch")}
    a = _point("L", "Engine.Light", (0, 0, 0))
    labeled = render_brushes_pgm([a], view="top", size=128, annotations=AnnotationSpec.all(), render_data=rd)
    plain = render_brushes_pgm([a], view="top", size=128, annotations=AnnotationSpec.none(), render_data=rd)
    assert _nonbg(labeled) > 0                          # the marker draws
    assert _nonbg(labeled) > _nonbg(plain)           # annotations=AnnotationSpec.none() drops the label text


def test_point_actor_is_not_painted_csg_additive_blue():
    # On the hybrid (color_by_csg) path a point actor's marker is drawn in its assigned label TINT
    # (`assign_tints`), never treated as a CSG brush — so its CSG-additive blue must not appear, and its
    # tint must. (Legacy black/grey mode keeps the neutral (90,90,90) marker — see the tests above.)
    from uedcli.preview import PointRender, _CSG_PALETTE, assign_tints
    a = _point("L", "Engine.Light", (0, 0, 0))
    rd = {"L": PointRender(label="L")}
    cols = _colors(render_brushes_pgm([a], view="top", size=128, render_data=rd, color_by_csg=True))
    assert _CSG_PALETTE["add"][0] not in cols              # NOT painted as an additive-solid brush
    assert assign_tints([a])["L"] in cols                  # drawn in its per-actor label tint


def test_sprite_billboard_blits_masked():
    from uedcli.preview import PointRender, COL_COLLISION
    # A 2x2 sprite: index-0 (transparent) top row, an opaque red bottom row.
    rgb = bytes([0, 0, 0, 0, 0, 0, 200, 10, 10, 200, 10, 10])
    mask = bytes([0, 0, 1, 1])
    rd = {"S": PointRender(label="S", sprite=(2, 2, rgb, mask), sprite_world=(80.0, 80.0))}
    cols = _colors(render_brushes_pgm([_point("S", "Engine.Light", (0, 0, 0))], view="top",
                                      size=128, annotations=AnnotationSpec.none(), render_data=rd))
    assert (200, 10, 10) in cols                           # opaque sprite pixels drew
    assert COL_COLLISION not in cols                       # no overlay unless requested


def test_show_collision_front_rect_is_twice_the_half_height():
    from uedcli.preview import PointRender, COL_COLLISION
    rd = {"P": PointRender(label="P", collision=(30.0, 50.0))}
    a = _point("P", "Engine.Pawn", (0, 0, 0))
    front = render_brushes_pgm([a], view="front", size=256, annotations=AnnotationSpec.none(), render_data=rd)
    assert COL_COLLISION in _colors(front)                 # the cylinder rect drew in FRONT


def test_point_actor_contributes_to_framing():
    from uedcli.preview import PointRender
    rd = {"A": PointRender(label="A"), "B": PointRender(label="B")}
    scene = render_brushes_pgm([_point("A", "X", (0, 0, 0)), _point("B", "X", (500, 0, 0))],
                               view="top", size=128, render_data=rd)
    assert _nonbg(scene) > 0                             # a point-only scene frames + draws


def test_multi_brush_render_overlays_both():
    a = _brush()
    b = copy.deepcopy(a)
    loc = a.location or (Decimal(0), Decimal(0), Decimal(0))
    b.location = (loc[0] + Decimal(300), loc[1], loc[2])
    one = render_brushes_pgm([a], view="top", size=256, annotations=AnnotationSpec.none())
    two = render_brushes_pgm([a, b], view="top", size=256, annotations=AnnotationSpec.none())
    assert _nonbg(two) > 0 and two != one


def _marker_rows(ppm, size):
    # y-rows carrying the neutral point-actor MARKER grey (90,90,90) — a single-view render has no
    # CAPTION/DIVIDER, so this colour comes only from point markers.
    b = _body(ppm)
    return {(k // 3) // size for k in range(0, len(b), 3)
            if (b[k], b[k + 1], b[k + 2]) == (90, 90, 90)}


def test_point_actors_differing_only_in_z_separate_in_front_and_iso():
    # Regression: point-actor decorations must be PROJECTED (not fed raw 3-D coords to to_px, which
    # only maps already-projected 2-D points). Two markers that differ ONLY in Z coincide in front/iso
    # unless each Location is projected first. (Symmetric (0,0,0)/(64,64,64) fixtures masked this.)
    from uedcli.preview import PointRender
    size = 128
    a = _point("A", "Engine.Light", (0, 0, 0))
    b = _point("B", "Engine.Light", (0, 0, 200))
    rd = {"A": PointRender(label="A"), "B": PointRender(label="B")}
    for view in ("front", "iso"):
        ppm = render_brushes_pgm([a, b], view=view, size=size, annotations=AnnotationSpec.none(), render_data=rd)
        rows = _marker_rows(ppm, size)
        assert rows and max(rows) - min(rows) > 40, f"{view}: markers not Z-separated ({rows})"


def test_iso_cylinder_edges_never_share_a_screen_column():
    # No two of the iso cylinder's vertical edges may land on the same screen column, or they shadow
    # into one line. Under the iso projection screen-x ∝ (cos θ − sin θ); an EVEN facet count makes
    # that value repeat (mirror symmetry) → overlaps; an ODD count makes all N distinct. This pins the
    # ODD choice — an even count (even rotated) FAILS here. See preview._ISO_CYL_SEGMENTS.
    import math
    from uedcli import preview
    n = preview._ISO_CYL_SEGMENTS
    xs = [round(math.cos(2 * math.pi * i / n) - math.sin(2 * math.pi * i / n), 6) for i in range(n)]
    assert len(set(xs)) == n, f"{n}-sided iso cylinder has coincident edge columns: {xs}"
    assert n % 2 == 1, "must be odd — an even count always shadows under the iso projection"


def test_iso_light_range_is_a_circle_not_an_octagon():
    # A sphere silhouettes to a CIRCLE from any parallel-projection angle, so --show-*-range must be
    # circular in ISO too — the old equator-ring drew a tilted OCTAGON (bbox ~2:1). Frame with an
    # explicit region so the reach circle sits well inside (unclipped), then assert its bbox is
    # ~square (a circle) in iso.
    from uedcli.preview import PointRender, COL_LIGHT
    rd = {"L": PointRender(label="L", light_radius=120.0)}
    a = _point("L", "Engine.Light", (0, 0, 0))
    px = _pixels(render_brushes_pgm([a], view="iso", size=256, annotations=AnnotationSpec.none(), render_data=rd,
                                    region=(-400, -400, -400, 400, 400, 400)))
    pts = [divmod(i, 256) for i, p in enumerate(px) if p == COL_LIGHT]
    xs = [x for _, x in pts]; ys = [y for y, _ in pts]
    w, h = max(xs) - min(xs), max(ys) - min(ys)
    assert pts and max(w, h) < 250                     # unclipped (not the full frame)
    assert abs(w - h) <= max(w, h) * 0.12              # square bbox → a circle, not a tilted octagon


# ---- AnnotationSpec / parse_annotation_spec (grammar) --------------------------------------------------
# poly categories are (is_front, is_highlighted); name categories are (is_brush, is_highlighted).
_FULL = frozenset({(False, False), (False, True), (True, False), (True, True)})


def test_it_parses_bare_kinds_as_everything():
    s = parse_annotation_spec("poly,name")
    assert s == AnnotationSpec(poly=_FULL, name=_FULL)


def test_it_narrows_poly_with_vis_and_hi_filters():
    assert parse_annotation_spec("poly:vis").poly == frozenset({(True, False), (True, True)})
    assert parse_annotation_spec("poly:hi").poly == frozenset({(True, True), (False, True)})
    assert parse_annotation_spec("poly:vis:hi").poly == frozenset({(True, True)})


def test_it_unions_comma_selectors():
    assert parse_annotation_spec("poly:vis,poly:hi").poly == frozenset(
        {(True, False), (True, True), (False, True)})


def test_it_narrows_names_by_subkind_and_hi():
    assert parse_annotation_spec("name:brush").name == frozenset({(True, False), (True, True)})
    assert parse_annotation_spec("name:point").name == frozenset({(False, False), (False, True)})
    assert parse_annotation_spec("name:hi").name == frozenset({(True, True), (False, True)})
    assert parse_annotation_spec("name:brush:hi").name == frozenset({(True, True)})


def test_it_treats_filters_as_an_order_independent_set():
    assert parse_annotation_spec("name:hi:brush") == parse_annotation_spec("name:brush:hi")


def test_it_accepts_highlighted_as_a_synonym_for_hi():
    assert parse_annotation_spec("poly:highlighted") == parse_annotation_spec("poly:hi")
    assert parse_annotation_spec("name:brush:highlighted") == parse_annotation_spec("name:brush:hi")


def test_it_normalizes_case_and_whitespace():
    assert parse_annotation_spec("poly, NAME") == parse_annotation_spec("poly,name")
    assert parse_annotation_spec("  POLY:VIS  ") == parse_annotation_spec("poly:vis")


def test_it_expands_the_whole_value_keywords():
    assert parse_annotation_spec("all") == AnnotationSpec(poly=_FULL, name=_FULL)
    assert parse_annotation_spec("none") == AnnotationSpec(poly=frozenset(), name=frozenset())
    assert parse_annotation_spec("highlighted") == parse_annotation_spec("poly:hi,name:hi")


def test_it_maps_the_default_value_to_todays_poly_behavior():
    s = parse_annotation_spec("poly:vis,poly:hi,name")
    assert s.poly == frozenset({(True, False), (True, True), (False, True)})   # front OR highlighted
    assert s.name == _FULL


def test_it_treats_zero_effective_tokens_as_none():
    none = AnnotationSpec(poly=frozenset(), name=frozenset())
    for text in ("", ",", "  ", " , "):
        assert parse_annotation_spec(text) == none


def test_it_keeps_a_kind_when_other_tokens_are_empty():
    assert parse_annotation_spec("poly,,").poly == _FULL


def test_annotationspec_predicates_answer_membership():
    s = parse_annotation_spec("poly:vis,name:brush")
    assert s.draws_poly(is_front=True, is_highlighted=False)
    assert not s.draws_poly(is_front=False, is_highlighted=True)
    assert s.draws_name(is_brush=True, is_highlighted=True)
    assert not s.draws_name(is_brush=False, is_highlighted=True)


@pytest.mark.parametrize("text,bad", [
    ("foo", "foo"), ("poly:brush", "brush"), ("name:vis", "vis"), ("poly:xyz", "xyz"),
    ("name:brush:point", "point"), ("all,poly", "all"), ("none,name", "none"),
])
def test_it_rejects_invalid_tokens_naming_the_offender(text, bad):
    with pytest.raises(ValueError) as excinfo:
        parse_annotation_spec(text)
    assert bad in str(excinfo.value)


def test_onface_is_facing_blind_vis_paints_the_same_faces_as_bare_poly():
    # On-face painting is FACING-BLIND: a face is numbered if the spec would draw it in EITHER facing, so
    # `poly:vis` paints back faces too (front/back shown by OPACITY, not presence) — identical to bare
    # `poly`. Both still draw something over the bare wireframe.
    allf = render_brush_pgm(_brush(), view="iso", size=256, annotations=parse_annotation_spec("poly"))
    visf = render_brush_pgm(_brush(), view="iso", size=256, annotations=parse_annotation_spec("poly:vis"))
    none = render_brush_pgm(_brush(), view="iso", size=256, annotations=AnnotationSpec.none())
    assert allf == visf                                   # facing-blind: same face set
    assert _nonbg(visf) > _nonbg(none) > 0


def test_default_labels_front_facing_indices_and_none_is_blank():
    dflt = render_brush_pgm(_brush(), view="iso", size=256, annotations=AnnotationSpec.default())
    none = render_brush_pgm(_brush(), view="iso", size=256, annotations=AnnotationSpec.none())
    assert _nonbg(dflt) > _nonbg(none)                 # default draws indices; none draws no text


# ---- brush-name labels + unified placement (Task 3) ------------------------------------------

def test_it_draws_a_brush_name_label():
    named = render_brush_pgm(_brush(), view="iso", size=256, annotations=parse_annotation_spec("name:brush"))
    blank = render_brush_pgm(_brush(), view="iso", size=256, annotations=AnnotationSpec.none())
    assert _nonbg(named) > _nonbg(blank)                 # the brush NAME text adds pixels over bare wireframe


def test_name_only_labels_omit_poly_indices():
    name_only = render_brush_pgm(_brush(), view="iso", size=256, annotations=parse_annotation_spec("name:brush"))
    with_polys = render_brush_pgm(_brush(), view="iso", size=256,
                                  annotations=parse_annotation_spec("name:brush,poly:vis"))
    assert _nonbg(with_polys) > _nonbg(name_only)        # adding the index labels adds pixels


def test_brush_name_drawn_when_a_poly_is_highlighted_under_hi_filter():
    hp = {("Brush938", 2)}                               # highlight one poly → the brush is "highlighted"
    with_name = render_brush_pgm(_brush(), view="iso", size=256,
                                 annotations=parse_annotation_spec("name:brush:hi"), highlight_polys=hp)
    no_name = render_brush_pgm(_brush(), view="iso", size=256, annotations=AnnotationSpec.none(),
                               highlight_polys=hp)
    # same highlight (same bold edges) in both — the only difference is the brush name, so it must add pixels
    assert _nonbg(with_name) > _nonbg(no_name)


def test_brush_name_suppressed_when_not_highlighted_under_hi_filter():
    no_hi = render_brush_pgm(_brush(), view="iso", size=256, annotations=parse_annotation_spec("name:brush:hi"))
    blank = render_brush_pgm(_brush(), view="iso", size=256, annotations=AnnotationSpec.none())
    assert _nonbg(no_hi) == _nonbg(blank)                # brush not highlighted → name:brush:hi draws nothing


def test_density_grid_counts_geometry_and_reads_back_higher_where_edges_lie():
    g = DensityGrid.build(64, cell_px=8)                 # 8x8 cells
    g.add_segment((0, 0), (63, 0))                       # top row of cells
    assert g.avg_density_in_box((0, 0, 63, 7)) > 0       # top row got hits
    assert g.avg_density_in_box((0, 56, 63, 63)) == 0.0  # bottom row empty


def test_density_grid_avg_is_per_cell_not_a_raw_sum():
    g = DensityGrid.build(64, cell_px=8)
    g.add_segment((0, 0), (0, 63))                        # left column, one hit per row
    left_col = g.avg_density_in_box((0, 0, 7, 63))        # 8 cells, each ~1
    assert 0.5 <= left_col <= 2.0                         # a MEAN, not a growing sum


def test_name_brush_filter_omits_point_names():
    b = _brush()                                          # brush-only scene
    brush = render_brush_pgm(b, view="iso", size=256, annotations=parse_annotation_spec("name:brush"))
    point = render_brush_pgm(b, view="iso", size=256, annotations=parse_annotation_spec("name:point"))
    blank = render_brush_pgm(b, view="iso", size=256, annotations=AnnotationSpec.none())
    assert _nonbg(brush) > _nonbg(blank)                  # name:brush draws the brush name
    assert _nonbg(point) == _nonbg(blank)                 # name:point draws no brush name


def test_name_point_filter_omits_brush_names():
    from uedcli.preview import PointRender
    a = _point("Lamp", "Engine.Light", (0, 0, 0))
    rd = {"Lamp": PointRender(label="Lamp")}
    point = render_brushes_pgm([a], view="top", size=128, annotations=parse_annotation_spec("name:point"),
                               render_data=rd)
    brush = render_brushes_pgm([a], view="top", size=128, annotations=parse_annotation_spec("name:brush"),
                               render_data=rd)
    none = render_brushes_pgm([a], view="top", size=128, annotations=AnnotationSpec.none(), render_data=rd)
    assert _nonbg(point) > _nonbg(none)                   # name:point draws the point name
    assert _nonbg(brush) == _nonbg(none)                  # name:brush draws no point name


def test_place_labels_moves_a_label_out_of_a_dense_region():
    size = 128
    g = DensityGrid.build(size, cell_px=8)
    for _ in range(30):                                  # a hot blob of geometry around (64,64)
        g.add_segment((40, 64), (88, 64))
        g.add_segment((64, 40), (64, 88))
    anchor_density = g.avg_density_in_box((64 - 8, 64 - 8, 64 + 8, 64 + 8))
    [placed] = _place_labels([_LabelItem(anchor=(64, 64), text="7", scale=2, color=FRONT)],
                             size, grid=g)
    lx, ly = placed.pos
    w, h = _label_size("7", 2)
    chosen = g.avg_density_in_box((lx - w // 2, ly - h // 2, lx + w // 2, ly + h // 2))
    assert chosen < anchor_density                       # the label fled toward clearer space


def test_placement_is_order_independent_with_a_grid():
    # Feeding the SAME labels in different input orders must yield the same placement — this exercises
    # the deterministic density-sort + tie-break, which a same-order-twice test would not.
    size = 128
    g = DensityGrid.build(size)
    g.add_segment((10, 10), (110, 110))
    items = [_LabelItem(anchor=(40 + 10 * i, 40 + 10 * i), text=str(i), scale=2, color=FRONT)
             for i in range(4)]
    forward = {p.text: p.pos for p in _place_labels(items, size, grid=g)}
    reverse = {p.text: p.pos for p in _place_labels(list(reversed(items)), size, grid=g)}
    assert forward == reverse


def test_least_dense_anchor_picks_the_clear_wireframe_point():
    # A ring/hollow brush's candidates: some in a dense zone, one in a clear zone. The chosen anchor
    # must be the clear one (the Part-B win: name on a clear wall, never the crowded centre/hollow).
    size = 128
    g = DensityGrid.build(size, cell_px=8)
    for _ in range(30):
        g.add_segment((90, 20), (90, 100))                 # a dense vertical wall at x~90
    crowded, clear = (90, 60), (20, 60)                    # two wireframe candidates
    assert _least_dense_anchor(g, [crowded, clear], halfbox=8) == clear


def test_avg_density_in_box_clamps_negative_and_oversized_rects():
    g = DensityGrid.build(64, cell_px=8)
    g.add_segment((0, 0), (63, 0))
    assert g.avg_density_in_box((-20, -20, 5, 5)) >= 0.0    # negative corner clamped, no crash
    assert g.avg_density_in_box((-99, -99, 999, 999)) >= 0.0  # oversized clamped to the whole grid


def test_point_in_poly_basic():
    from uedcli.preview import _point_in_poly
    square = [(0, 0), (10, 0), (10, 10), (0, 10)]
    assert _point_in_poly((5, 5), square)
    assert not _point_in_poly((15, 5), square)


def test_occluder_count_only_nearer_covering_solid_faces():
    square = [(0, 0), (20, 0), (20, 20), (0, 20)]
    near = (square, 10.0, "WALL", True)                   # covers (10,10), depth 10 (nearer), solid
    far = (square, 30.0, "WALL", True)                    # covers (10,10), depth 30 (farther)
    assert _occluder_count((10, 10), 20.0, [near], own_brush="CUBE") == 1   # nearer solid → occludes
    assert _occluder_count((10, 10), 20.0, [far], own_brush="CUBE") == 0    # only farther → not occluded
    tiny = ([(0, 0), (2, 0), (2, 2), (0, 2)], 5.0, "WALL", True)            # nearer but does not cover
    assert _occluder_count((10, 10), 20.0, [tiny], own_brush="CUBE") == 0


def test_occluder_count_hollow_occludes_only_its_own_brush_not_a_solid_inside():
    # A subtract/hollow room's near wall (front face G, NOT solid) buries its OWN far wall (self-occlusion)
    # but must NOT dim a solid cube sitting inside the room — the self-or-solid occluder rule.
    from uedcli.preview import _occluder_count
    square = [(0, 0), (20, 0), (20, 20), (0, 20)]
    hollow_near = (square, 10.0, "ROOM", False)           # room's near wall: covers, nearer, NOT solid
    # A far face of the SAME hollow brush is occluded by its own near wall.
    assert _occluder_count((10, 10), 20.0, [hollow_near], own_brush="ROOM") == 1
    # A DIFFERENT brush's face (a cube inside) is NOT occluded by the hollow room's wall.
    assert _occluder_count((10, 10), 20.0, [hollow_near], own_brush="CUBE") == 0
    # But a SOLID brush's near face occludes across brushes as before.
    solid_near = (square, 10.0, "PILLAR", True)
    assert _occluder_count((10, 10), 20.0, [solid_near], own_brush="CUBE") == 1


# ---- HYBRID per-brush tint + legend + --focus -----------------------------------------------


def _add_cube(name, at, size=128):
    from uedcli.builders import cube, make_brush_actor
    return make_brush_actor(name, cube(size, size, size), location=at, csg="add")


def _sub_cube(name, at, size=256):
    from uedcli.builders import cube, make_brush_actor
    return make_brush_actor(name, cube(size, size, size), location=at, csg="subtract")


def test_it_assigns_a_distinct_tint_per_actor_and_cycles():
    from uedcli.preview import assign_tints, _TINT_PALETTE
    actors = [_add_cube(f"B{i}", (i * 400, 0, 0)) for i in range(len(_TINT_PALETTE) + 1)]
    tints = assign_tints(actors)
    # First N actors get N distinct palette entries; the (N+1)-th wraps back to the first.
    assert len(set(tints[a.name] for a in actors[:len(_TINT_PALETTE)])) == len(_TINT_PALETTE)
    assert tints[actors[-1].name] == tints[actors[0].name] == _TINT_PALETTE[0]


def test_hybrid_legend_draws_a_swatch_in_each_brushs_tint():
    from uedcli.preview import assign_tints
    a, b = _sub_cube("QIX", (0, 0, 0)), _add_cube("JYR", (600, 0, 0))
    tints = assign_tints([a, b])
    # name:brush ⇒ no on-geometry indices; on the hybrid path the tint appears ONLY as the legend
    # swatch, so finding both tints proves the legend maps tint→name.
    cols = _colors(render_brushes_pgm([a, b], view="iso", size=256,
                                      annotations=parse_annotation_spec("name:brush"), color_by_csg=True))
    assert tints["QIX"] in cols and tints["JYR"] in cols


def test_focus_dims_other_brushes_and_keeps_the_focused_one_vivid():
    from uedcli.preview import _CSG_PALETTE, _fade
    a, b = _sub_cube("VOK", (0, 0, 0)), _add_cube("JYR", (600, 0, 0))
    add_front = _CSG_PALETTE["add"][0]
    cols = _colors(render_brushes_pgm([a, b], view="iso", size=256, annotations=AnnotationSpec.none(),
                                      color_by_csg=True, focus="VOK"))
    assert _CSG_PALETTE["subtract"][0] in cols          # the focused brush keeps its vivid CSG hue
    assert add_front not in cols                          # the non-focused add brush is dimmed away…
    assert _fade(add_front, 0.85) in cols                 # …to its hard-faded (0.85) shade


def test_highlight_overrides_focus_and_relights_a_non_focused_poly():
    from uedcli.preview import _CSG_PALETTE
    a, b = _sub_cube("VOK", (0, 0, 0)), _add_cube("JYR", (600, 0, 0))
    add_front = _CSG_PALETTE["add"][0]
    # Focus VOK (so JYR dims) but highlight one of JYR's polys: highlight WINS — that poly re-lights
    # to JYR's vivid add hue on top of the focus-dimming.
    cols = _colors(render_brushes_pgm([a, b], view="iso", size=256, annotations=AnnotationSpec.none(),
                                      color_by_csg=True, focus="VOK",
                                      highlight_polys={("JYR", 0)}))
    assert add_front in cols                              # highlight re-lit the dimmed brush's poly


def test_focus_is_case_insensitive():
    from uedcli.preview import _CSG_PALETTE, _fade
    a, b = _sub_cube("VOK", (0, 0, 0)), _add_cube("JYR", (600, 0, 0))
    cols = _colors(render_brushes_pgm([a, b], view="iso", size=256, annotations=AnnotationSpec.none(),
                                      color_by_csg=True, focus="vok"))
    assert _fade(_CSG_PALETTE["add"][0], 0.85) in cols    # "vok" matched "VOK" → JYR still dimmed


def test_highlight_retains_its_poly_index_in_a_focused_out_brush():
    # Focus VOK, so JYR is dimmed and normally shows NO poly indices. Highlighting one of JYR's polys
    # must OVERRIDE focus and KEEP that poly's INDEX (not just re-light its edges). With annotations=poly:hi
    # only highlighted faces are indexed, so the ONLY difference from the annotations=none scene (same focus +
    # same highlight, so identical re-lit edges) is JYR:0's retained index — isolating the index path.
    a, b = _sub_cube("VOK", (0, 0, 0)), _add_cube("JYR", (600, 0, 0))
    with_idx = render_brushes_pgm([a, b], view="iso", size=256, annotations=parse_annotation_spec("poly:hi"),
                                  color_by_csg=True, focus="VOK", highlight_polys={("JYR", 0)})
    edges_only = render_brushes_pgm([a, b], view="iso", size=256, annotations=AnnotationSpec.none(),
                                    color_by_csg=True, focus="VOK", highlight_polys={("JYR", 0)})
    assert _nonbg(with_idx) > _nonbg(edges_only)          # the retained index adds content pixels


def test_quad_hybrid_legend_is_drawn_once_in_the_top_pane():
    # The hybrid legend is drawn ONCE (TOP-left pane only), never repeated per pane. With name:brush the
    # only WHITE fill anywhere is the legend panel (names live in it, no on-geometry knockout boxes), so
    # the TOP pane's corner carries a white panel while the FRONT pane's matching corner has none.
    size = 256
    half = size // 2
    a, b = _sub_cube("QIX", (0, 0, 0)), _add_cube("JYR", (600, 0, 0))
    px = _pixels(render_quad_pgm([a, b], size=size, annotations=parse_annotation_spec("name:brush"),
                                 color_by_csg=True))

    def white_in_corner(ox):
        return sum(1 for j in range(2, 16) for i in range(2, 16)
                   if px[j * size + (ox + i)] == WHITE)

    assert white_in_corner(0) > 20                        # TOP pane corner: the one legend panel
    assert white_in_corner(half) == 0                     # FRONT pane corner: no repeated legend


def test_poly_centroid_2d_is_area_weighted_center():
    from uedcli.preview import _poly_centroid_2d
    # A unit square's centroid is its center, regardless of vertex ordering/start.
    assert _poly_centroid_2d([(0, 0), (4, 0), (4, 4), (0, 4)]) == (2.0, 2.0)
    # Degenerate (collinear, ~zero area) → falls back to the vertex average, no divide-by-zero.
    assert _poly_centroid_2d([(0, 0), (2, 0), (4, 0)]) == (2.0, 0.0)


# ----- on-face CENTERED painted number texture (the SOLE poly-label renderer) ---


def _wall_face(x=100.0, lo=0.0, hi=200.0):
    """A vertical wall face in the plane X=`x` (CCW → outward normal +X), spanning Y,Z in [lo, hi]."""
    return [(x, lo, lo), (x, hi, lo), (x, hi, hi), (x, lo, hi)]


def _cap_face(z=50.0, lo=0.0, hi=200.0):
    """A horizontal cap/floor face in the plane Z=`z` (normal ±Z), spanning X,Y in [lo, hi]."""
    return [(lo, lo, z), (hi, lo, z), (hi, hi, z), (lo, hi, z)]


def _front_to_pxf(size=256):
    """A head-on 'front-ish' world→float-pixel map: screen-x = world Y, screen-y = flipped world Z."""
    return lambda p: (p[1], size - p[2])


def test_decal_opacity_keeps_front_clear_and_retains_60pct_per_occluding_layer():
    # 0.56 * 0.6 ** n_front: a VISIBLE face is 0.56; each layer in front keeps 60% of it; floored 0.12.
    assert _decal_opacity(0) == pytest.approx(0.56)
    assert _decal_opacity(1) == pytest.approx(0.336)
    assert _decal_opacity(2) == pytest.approx(0.2016)
    assert _decal_opacity(50) == 0.12           # floored so a deep number never fully vanishes


def test_text_bitmap_centres_a_short_number_in_a_two_digit_slot():
    # A single digit is sized/placed as if it were 2 digits wide (cols 7), with the glyph CENTRED and its
    # underline under the DIGIT only — so a lone `6` renders at the same scale as `12`.
    grid, cols, rows = _text_bitmap("6")
    assert (cols, rows) == (7, 7)             # a 2-DIGIT slot even for one digit
    assert grid[0] == (False, False, True, True, True, False, False)   # "6" top row "111", centred (x0=2)
    assert not any(grid[5])                   # blank separator row
    assert [c for c in range(cols) if grid[6][c]] == [2, 3, 4]         # underline under the digit, not the slot
    g2, c2, _ = _text_bitmap("12")            # a full 2-digit number fills the slot; underline spans it
    assert c2 == 4 * 2 - 1 and all(g2[6])
    _, c1, _ = _text_bitmap("6", slot_digits=1)    # opt out → raw single-glyph width
    assert c1 == 3


def test_face_decal_basis_on_a_vertical_wall_stands_text_up_the_wall():
    # A wall facing +X: text-UP = world +Z (strokes stand straight up the wall); the frame is orthonormal
    # and lies in the wall plane (no X component) — the number is painted-on, gravity-hung, not italic.
    cw, uw, vw = _face_decal_basis(_wall_face(), _front_to_pxf())
    assert vw == pytest.approx((0.0, 0.0, 1.0), abs=1e-9)
    assert uw[0] == pytest.approx(0.0, abs=1e-9)
    assert uw[0] * vw[0] + uw[1] * vw[1] + uw[2] * vw[2] == pytest.approx(0.0, abs=1e-9)
    assert math.hypot(uw[0], uw[1], uw[2]) == pytest.approx(1.0)
    assert cw == pytest.approx((100.0, 100.0, 100.0))


def test_face_decal_basis_hangs_text_up_the_wall_regardless_of_camera_yaw():
    # GRAVITY orientation: text-up = world +Z projected into the plane, so the same wall reads upright
    # (Vw ≈ +Z) under DIFFERENT projections — orientation is view-independent, not per-view "level".
    wall = _wall_face()
    for w2p in (_front_to_pxf(),                                     # screen-x = world Y
                lambda p: (p[1] - p[2], 256 - (p[1] + p[2]))):      # an oblique iso-ish map
        _, uw, vw = _face_decal_basis(wall, w2p)
        assert vw == pytest.approx((0.0, 0.0, 1.0), abs=1e-9)        # up-the-wall in BOTH views
        assert uw[0] == pytest.approx(0.0, abs=1e-9)                 # baseline stays in the wall plane


def test_face_decal_basis_aligns_a_horizontal_face_to_the_world_y_axis():
    # A FLOOR/CEILING/CAP (normal ≈ ±Z) has no in-plane gravity-up, so its basis is fixed to the WORLD
    # axes: text-up Vw = world +Y, text-right Uw = world +X — consistent, not an arbitrary roll. The
    # right-reading fix keeps a ceiling (normal −Z) un-mirrored (still Uw = +X under a top view).
    top = lambda p: (p[0], 256 - p[1])                              # noqa: E731 — top view (x, flipped y)
    floor = _cap_face(z=0.0, lo=0.0, hi=200.0)                      # CCW in XY → normal +Z
    ceiling = list(reversed(_cap_face(z=50.0, lo=0.0, hi=200.0)))   # reversed winding → normal −Z
    for face in (floor, ceiling):
        _, uw, vw = _face_decal_basis(face, top)
        assert vw == pytest.approx((0.0, 1.0, 0.0), abs=1e-9)       # text-up = world +Y
        assert uw == pytest.approx((1.0, 0.0, 0.0), abs=1e-9)       # text-right = world +X (not mirrored)


def test_plan_onface_texture_labels_a_big_wall_and_a_horizontal_cap():
    # A comfortably-sized wall AND a horizontal cap each get a centered painted number. A single digit is
    # sized in a 2-digit slot (cols 7), so it scales like a 2-digit number.
    plan = _plan_onface_texture(_wall_face(lo=0.0, hi=400.0), _front_to_pxf(), "6")
    assert plan is not None and (plan.cols, plan.rows) == (7, 7)
    cap = _cap_face(z=50.0, lo=0.0, hi=400.0)                        # normal +Z
    assert _plan_onface_texture(cap, lambda p: (p[0], 256 - p[1]), "12") is not None


def test_plan_onface_texture_omit_is_on_screen_size_based_and_view_dependent():
    # The OMIT verdict is on-SCREEN size, not world size: a big wall is labeled at full scale but
    # DROPPED when projected tiny (a small quad-pane-like view), i.e. the same face's number appears or
    # vanishes with the framing.
    big = _wall_face(lo=0.0, hi=400.0)
    full = _front_to_pxf()
    downscaled = lambda p: (p[1] * 0.02, 256 - p[2] * 0.02)         # noqa: E731 — a tiny projection
    assert _plan_onface_texture(big, full, "6") is not None         # readable at full scale → numbered
    assert _plan_onface_texture(big, downscaled, "6") is None       # unreadable when tiny on screen → omitted


def test_draw_painted_decal_is_translucent_at_the_default_front_opacity():
    # Plan a decal on a head-on wall, then paint it onto a grey buffer at the default 0.70 front opacity.
    plan = _plan_onface_texture(_wall_face(), _front_to_pxf(), "6")
    assert plan is not None
    buf = bytearray(bytes((BG, BG, BG)) * 256 * 256)
    tint = (206, 34, 44)

    _draw_painted_decal(buf, 256, plan, tint)

    blended = tuple(round(0.7 * c + 0.3 * BG) for c in tint)
    px = {tuple(buf[i:i + 3]) for i in range(0, len(buf), 3)}
    assert blended in px
    assert tint not in px                         # never opaque
    assert (255, 255, 255) not in px              # halo is translucent, not solid white


def test_draw_painted_decal_underline_uses_the_same_tint_as_the_digit():
    # The 6/9 baseline UNDERLINE belongs to the digit: it MUST paint in the SAME per-brush tint (and
    # opacity) as the digit above it — a differently-coloured underline would misdirect the colour→brush
    # match. Both come from ONE `_draw_painted_decal` pass over the whole glyph bitmap at one tint/alpha.
    plan = _plan_onface_texture(_wall_face(), _front_to_pxf(), "6")
    assert plan is not None and plan.rows == 7        # rows 0-4 digit, 5 blank, 6 underline
    buf = bytearray(bytes((BG, BG, BG)) * 256 * 256)
    tint = (0, 150, 150)                              # teal
    alpha = _decal_opacity(0)

    _draw_painted_decal(buf, 256, plan, tint, alpha=alpha)

    def _texel_center_color(col, row):
        x = int(plan.tl[0] + (col + 0.5) * plan.ex[0] + (row + 0.5) * plan.ey[0])
        y = int(plan.tl[1] + (col + 0.5) * plan.ex[1] + (row + 0.5) * plan.ey[1])
        i = (y * 256 + x) * 3
        return (buf[i], buf[i + 1], buf[i + 2])

    blended = tuple(round(alpha * c + (1 - alpha) * BG) for c in tint)
    digit = {_texel_center_color(c, r) for r in range(5) for c in range(plan.cols) if plan.bitmap[r][c]}
    underline = {_texel_center_color(c, 6) for c in range(plan.cols) if plan.bitmap[6][c]}
    assert digit == {blended}                        # digit texels are the tint
    assert underline == {blended}                    # underline texels are the SAME tint (not another hue)


def test_onface_paints_back_faces_dimmer_via_self_occlusion():
    # A SOLID (additive) brush paints its BACK faces too — facing-blind, at graded opacity — even with the
    # DEFAULT `poly:vis` labels. Its front faces occlude its own back faces, so strokes appear at >=2
    # depth levels: 0.56 (visible) plus >=1 dimmer (occluded back face: 0.336 / 0.2016 / floor 0.12).
    from uedcli.preview import _TINT_PALETTE
    a = copy.deepcopy(_brush())
    a.props = [(k, v) for k, v in a.props if k != "CsgOper"]      # additive => solid => self-occluding

    ppm = render_brush_pgm(a, view="iso", size=256, annotations=AnnotationSpec.default(), color_by_csg=True)

    tint = _TINT_PALETTE[0]
    px = {tuple(ppm[i:i + 3]) for i in range(len(b"P6\n256 256\n255\n"), len(ppm), 3)}
    front = tuple(round(0.56 * c + 0.44 * BG) for c in tint)
    dimmer = [tuple(round(op * c + (1 - op) * BG) for c in tint) for op in (0.336, 0.2016, 0.12)]
    assert front in px
    assert any(lv in px for lv in dimmer)


def test_onface_labels_a_big_face_even_in_a_tiny_render():
    # A big-world-size brush keeps its on-face numbers even in a tiny (downscaled) render — drawn small
    # but present, never omitted per-view. The painted render has more content than a names-only one.
    a = _brush()
    painted = render_brush_pgm(a, view="iso", size=128, annotations=AnnotationSpec.all(), color_by_csg=True)
    names_only = render_brush_pgm(a, view="iso", size=128, annotations=parse_annotation_spec("name"),
                                  color_by_csg=True)
    assert _nonbg(painted) > _nonbg(names_only)   # decals drawn even downscaled (big faces present)


def test_onface_omits_only_tiny_faces_with_no_leader_fallback(monkeypatch):
    # A face omitted for being too small is NOT drawn as a leader box. Force every plan to fail (as if
    # every face were sub-threshold); the painted render must equal a names-only render — omission, not
    # a leader fallback.
    a = _brush()
    monkeypatch.setattr("uedcli.preview._onface_candidates", lambda *args, **kwargs: [])
    omitted = render_brush_pgm(a, view="iso", size=256, annotations=AnnotationSpec.default(), color_by_csg=True)
    names_only = render_brush_pgm(a, view="iso", size=256, annotations=parse_annotation_spec("name"),
                                  color_by_csg=True)
    assert omitted == names_only          # un-paintable polys vanish (no leader box), leaving names/legend


# --- legend reserve (#1) + --brush-colors (#3) ---

def test_legend_reserve_is_zero_without_rows_and_positive_with_rows():
    from uedcli.preview import _LegendRow
    # Arrange: no rows vs a couple of brush rows.
    rows = [_LegendRow(kind="brush", color=(1, 2, 3), text="ALPHA"),
            _LegendRow(kind="brush", color=(4, 5, 6), text="BRAVO")]
    # Act / Assert
    assert _legend_reserve([], name_scale=2, size=256) == 0
    assert _legend_reserve(rows, name_scale=2, size=256) > 0


def test_framing_inset_top_pushes_geometry_below_the_reserved_band():
    # Arrange: one world point; frame it with no reserve and with a 40px top reserve.
    pts = [(0.0, 0.0), (100.0, 100.0)]
    _, to_px0, _, _ = _framing(pts, None, 256, "iso", 30.0, 0)
    _, to_px1, _, _ = _framing(pts, None, 256, "iso", 30.0, 40)
    # Act: the topmost world point (max y) projects nearest the top edge.
    top0 = to_px0((100.0, 100.0))[1]
    top1 = to_px1((100.0, 100.0))[1]
    # Assert: with a reserve, the top of the geometry sits LOWER (larger screen-y) — below the band.
    assert top1 > top0
    assert top1 >= 40


def test_it_colors_the_wireframe_by_legend_tint_when_asked():
    from uedcli.builders import cube, make_brush_actor
    from uedcli.preview import _CSG_PALETTE
    # Arrange: a lone subtract cube. In csg mode its wireframe is subtract-gold; its legend tint is
    # a distinct categorical hue. (draw_legend off so only the WIREFRAME contributes colours.)
    room = make_brush_actor("Room", cube(256, 256, 256), csg="subtract")
    gold = _CSG_PALETTE["subtract"][0]
    tint = assign_tints([room])["Room"]
    kw = dict(view="iso", size=256, annotations=AnnotationSpec.none(), color_by_csg=True, draw_legend=False)
    # Act
    csg_cols = _colors(render_brushes_pgm([room], brush_colors="csg", **kw))
    legend_cols = _colors(render_brushes_pgm([room], brush_colors="legend", **kw))
    # Assert: csg mode paints the CSG hue and not the tint; legend mode swaps to the tint.
    assert gold in csg_cols and tint not in csg_cols
    assert tint in legend_cols and gold not in legend_cols


def test_framing_inset_top_zero_matches_the_unreserved_formula():
    # inset_top=0 must reproduce the pre-reserve framing bit-for-bit (the on-face goldens rely on it).
    pts = [(-30.0, 12.5), (170.0, 240.0), (5.0, -8.0)]
    minx, miny = min(p[0] for p in pts), min(p[1] for p in pts)
    span = max(max(p[0] for p in pts) - minx, max(p[1] for p in pts) - miny)
    for size in (128, 131, 256, 384):
        _, to_px, _, _ = _framing(pts, None, size, "iso", 30.0, 0)
        draw = size - 2 * _FRAME_PAD
        for p in pts:
            expected = (int((p[0] - minx) / span * draw) + _FRAME_PAD,
                        size - 1 - (int((p[1] - miny) / span * draw) + _FRAME_PAD))
            assert to_px(p) == expected


def test_it_caps_the_legend_reserve_so_a_tall_legend_never_crushes_the_geometry():
    from uedcli.builders import cube, make_brush_actor
    # Arrange: 40 labelled brushes → 40 legend rows. Reserving the full panel height would eat the whole
    # frame (and at size 131 flip the scale negative); the band cap must keep the reserve bounded.
    actors = [make_brush_actor(f"B{i}", cube(64, 64, 64), location=(i * 80, 0, 0), csg="add")
              for i in range(40)]
    tints = assign_tints(actors)
    for size in (128, 131, 256, 512):                        # 131: the reviewer's negative-scale case
        rows = _legend_rows(actors, AnnotationSpec.all(), tints, highlight_polys=set(),
                            highlight_points=set(), drawn_points=set())
        reserve = _legend_reserve(rows, max(2, size // 256), size)
        # Assert: bounded well under the frame, so the geometry keeps a real budget (draw > 0).
        assert 0 < reserve <= size // 2
        assert _nonbg(render_brushes_pgm(actors, view="iso", size=size,
                                         annotations=AnnotationSpec.none(), color_by_csg=True)) > 0


# --- on-face decal placement: largest inscribed glyph-box, at the roomiest spot, ×0.75 ---

def _drawn_box_fits(center, cell, cols, rows, poly):
    # The DRAWN decal is _ONFACE_FILL (0.75) x the returned max (which is boundary-tangent by
    # construction, so testing at 1.0 would flake on _point_in_poly boundary ambiguity).
    (cu, cv) = center
    d = _ONFACE_FILL * cell
    return _box_fits_2d(cu, cv, cols * d / 2, rows * d / 2, poly)


def test_poly_is_convex_2d_distinguishes_convex_from_concave():
    square = [(-5, -5), (5, -5), (5, 5), (-5, 5)]
    l_shape = [(0, 0), (10, 0), (10, 4), (4, 4), (4, 10), (0, 10)]   # concave notch
    assert _poly_is_convex_2d(square) is True
    assert _poly_is_convex_2d(l_shape) is False


def test_max_inscribed_box_centers_in_a_square():
    # Arrange: a 100x100 square face; a 3x5-texel glyph is height-limited (5*cell <= 100 -> cell 20).
    cols, rows = 3, 5
    square = [(-50, -50), (50, -50), (50, 50), (-50, 50)]
    # Act
    (cu, cv), cell = _max_inscribed_box(square, cols, rows)
    # Assert: centred, cell = the tighter of 100/3, 100/5 = 20, and the drawn box is inside.
    assert abs(cu) < 1 and abs(cv) < 1
    assert abs(cell - 20.0) < 0.5
    assert _drawn_box_fits((cu, cv), cell, cols, rows, square)


def test_max_inscribed_box_stays_inside_a_triangle():
    # Arrange: a right triangle — its centroid sits where the shape is narrow, so the biggest box is
    # NOT centroid-centred; the drawn box must still lie fully inside (the max box is edge-tangent).
    cols, rows = 3, 5
    tri = [(0, 0), (120, 0), (0, 200)]
    # Act
    (cu, cv), cell = _max_inscribed_box(tri, cols, rows)
    # Assert
    assert cell > 0
    assert _drawn_box_fits((cu, cv), cell, cols, rows, tri)


def test_max_inscribed_box_avoids_a_concave_notch():
    # Arrange: a big L-shape; the box must sit in an arm, never crossing into the notch.
    cols, rows = 3, 5
    l_shape = [(0, 0), (200, 0), (200, 80), (80, 80), (80, 200), (0, 200)]
    # Act
    (cu, cv), cell = _max_inscribed_box(l_shape, cols, rows)
    # Assert: the drawn box fits fully inside the concave polygon.
    assert cell > 0
    assert _drawn_box_fits((cu, cv), cell, cols, rows, l_shape)


def test_box_fits_2d_rejects_a_box_overhanging_the_face():
    tri = [(0, 0), (100, 0), (0, 100)]
    assert _box_fits_2d(10, 10, 5, 5, tri) is True         # small box near the right-angle corner fits
    assert _box_fits_2d(60, 60, 20, 20, tri) is False      # a box out past the hypotenuse does not


def test_max_inscribed_box_finds_a_narrow_lobe_a_grid_would_miss():
    # A fat 60x300 lobe on a thin 20-tall neck: the only legible pocket sits between coarse grid nodes,
    # so a grid-only search would falsely omit it — vertex/edge-midpoint seeds must find it.
    cols, rows = 3, 7
    poly = [(0, 0), (1180, 0), (1180, 300), (1120, 300), (1120, 20), (0, 20)]
    # Act
    center, cell = _max_inscribed_box(poly, cols, rows)
    # Assert: a legible box is found (not None), and it fits inside the concave polygon.
    assert center is not None and cell > 4.0
    assert _drawn_box_fits(center, cell, cols, rows, poly)


# --- anti-overlap: candidate generation + greedy resolver ---
#
# `_narrow_wall` + `_front_to_pxf` give a head-on, UNFORESHORTENED wall (normal +X): world Y -> screen
# x, world Z -> screen y, 1 world unit == 1 px. So a glyph's projected texel size in px EQUALS its
# world cell, making on-screen sizes exact in tests. (The shared `_wall_face` is always square; this
# one takes independent width/height for the tall-narrow rotation case.)
def _narrow_wall(*, wide, tall):
    return [(0.0, -wide / 2, 0.0), (0.0, wide / 2, 0.0), (0.0, wide / 2, tall), (0.0, -wide / 2, tall)]


def _mk_plan(x, y, w, h):
    # A _DecalPlan whose screen bbox is exactly (x, y, x+w, y+h) and whose _plan_px_area is w*h,
    # for testing resolver mechanics without any projection.
    return _DecalPlan(tl=(float(x), float(y)), ex=(float(w), 0.0), ey=(0.0, float(h)),
                      bitmap=((True,),), cols=1, rows=1)


def test_feasible_centers_returns_fitting_centres_and_empty_when_too_big():
    # Arrange: a 100x100 square; a 10x10 box fits (many centres), a 200x200 box fits nowhere.
    square = [(-50, -50), (50, -50), (50, 50), (-50, 50)]
    # Act
    fitting = _feasible_centers(square, 5, 5)
    none_fit = _feasible_centers(square, 100, 100)
    # Assert
    assert fitting and all(_box_fits_2d(cu, cv, 5, 5, square) for cu, cv in fitting)
    assert none_fit == []


def test_onface_candidate_zero_equals_plan_onface_texture():
    # The first candidate must be byte-identical to the single-placement planner, so a zero-overlap
    # decal (kept at candidate 0 by the resolver) leaves existing renders unchanged.
    v3 = _narrow_wall(wide=160, tall=120)
    single = _plan_onface_texture(v3, _front_to_pxf(), "12", min_texel_px=0.0)
    cand0 = _onface_candidates(v3, _front_to_pxf(), "12", min_texel_px=0.0)[0]
    assert single is not None
    assert (cand0.tl, cand0.ex, cand0.ey, cand0.bitmap, cand0.cols, cand0.rows) == (
        single.tl, single.ex, single.ey, single.bitmap, single.cols, single.rows)


def test_onface_candidates_are_all_within_ten_percent_of_full_size():
    # Reshuffle is MINIMAL: candidate 0 is full size and every other candidate is at most 10% smaller
    # (linear), i.e. area >= 0.81 x candidate 0. There is no deep shrink ladder and no rotation.
    v3 = _narrow_wall(wide=160, tall=120)
    cands = _onface_candidates(v3, _front_to_pxf(), "12", min_texel_px=0.0)
    area0 = _plan_px_area(cands[0])
    assert len(cands) > 1                                    # nudge options exist
    assert all(_plan_px_area(c) >= 0.81 * area0 - 1e-6 for c in cands)


def test_onface_candidates_keep_edge_padding_and_never_sit_flush():
    # Every candidate keeps real clearance to the face edge (the 0.75 fill == 16.666%/side padding), so
    # scaling the decal parallelogram up by 1.2x about its centre still lies fully inside the face — a
    # nudged number is never drawn flush against an edge.
    v3 = _narrow_wall(wide=160, tall=120)
    w2p = _front_to_pxf()
    face_scr = [w2p(p) for p in v3]
    cands = _onface_candidates(v3, w2p, "12", min_texel_px=0.0)
    assert cands
    for c in cands:
        corners = c._corners()
        cx = sum(p[0] for p in corners) / 4
        cy = sum(p[1] for p in corners) / 4
        grown = [(cx + (px - cx) * 1.2, cy + (py - cy) * 1.2) for px, py in corners]
        assert all(_point_in_poly(pt, face_scr) for pt in grown)


def test_onface_candidates_are_empty_when_below_the_readability_floor():
    # A face too small to read gets NO number (candidate 0 gates it) — no nudge candidate rescues it.
    v3 = _narrow_wall(wide=2, tall=2)
    assert _onface_candidates(v3, _front_to_pxf(), "1", min_texel_px=_ONFACE_MIN_TEXEL_PX) == []


def test_rect_overlap_area_sums_per_obstacle_so_stacks_count_more():
    # Overlap is SUMMED per obstacle, not unioned: a patch covered by two obstacles counts twice.
    box = (0, 0, 100, 100)
    half = (0, 0, 100, 50)                                   # covers 100x50 = 5000 of box
    assert _rect_overlap_area(box, [half]) == 5000
    assert _rect_overlap_area(box, [half, half]) == 10000    # two stacked on the same patch -> 2x


def test_resolve_decals_keeps_candidate_zero_when_it_does_not_overlap():
    # No overlap -> candidate 0 kept verbatim, EVEN when a nearby alternative exists.
    cand0 = _mk_plan(10, 10, 30, 30)
    alt = _mk_plan(12, 10, 30, 30)                           # near, within budget, but unneeded
    chosen = _resolve_decals([((-_plan_px_area(cand0), "A", "1"), [cand0, alt])], obstacles=[])
    assert chosen == [cand0]


def test_resolve_decals_nudges_within_budget_to_reduce_overlap():
    # Candidate 0 overlaps a marker; a candidate within the tiny budget (<=10% move, <=10% shrink) that
    # clears it is chosen. cand0 100x100 -> diagonal ~141, move budget ~14px; the nudge moves ~9.8px.
    marker = (-40, 0, 10, 100)                               # covers cand0's left 10px column
    cand0 = _mk_plan(0, 0, 100, 100)
    nudge = _mk_plan(12, 0, 95, 95)                          # +~9.8px, 0.95 linear: within budget, clears
    chosen = _resolve_decals([((-_plan_px_area(cand0), "A", "1"), [cand0, nudge])], obstacles=[marker])
    assert chosen == [nudge]
    assert _rect_overlap_area(chosen[0].bbox(), [marker]) < _rect_overlap_area(cand0.bbox(), [marker])


def test_resolve_decals_will_not_move_beyond_the_budget():
    # Only a FAR clear alternate exists (>10% of diagonal away); the resolver refuses it and keeps the
    # overlapping candidate 0 — reshuffle never makes a big jump.
    marker = (-40, 0, 10, 100)
    cand0 = _mk_plan(0, 0, 100, 100)
    far = _mk_plan(200, 0, 100, 100)                         # ~200px away, way past the ~14px budget
    chosen = _resolve_decals([((-_plan_px_area(cand0), "A", "1"), [cand0, far])], obstacles=[marker])
    assert chosen == [cand0]


def test_resolve_decals_will_not_shrink_beyond_the_budget():
    # Only a much-smaller clear alternate exists (0.5 linear, past the 10% shrink budget); refused, so
    # candidate 0 stays at full size and accepts the overlap.
    marker = (-40, 0, 10, 100)
    cand0 = _mk_plan(0, 0, 100, 100)
    small = _mk_plan(25, 25, 50, 50)                         # centred (no move) but 0.5x — past budget
    chosen = _resolve_decals([((-_plan_px_area(cand0), "A", "1"), [cand0, small])], obstacles=[marker])
    assert chosen == [cand0]


def test_resolve_decals_is_deterministic():
    marker = (-40, 0, 10, 100)
    cand0, nudge = _mk_plan(0, 0, 100, 100), _mk_plan(12, 0, 95, 95)
    entries = [((-_plan_px_area(cand0), "A", "1"), [cand0, nudge])]
    assert _resolve_decals(entries, obstacles=[marker]) == _resolve_decals(entries, obstacles=[marker])


def _filled_square(x0, y0, x1, y1):
    return {(x, y) for x in range(x0, x1) for y in range(y0, y1)}


def _count_rgb(buf, size, rgb):
    return sum(1 for i in range(size * size) if (buf[3 * i], buf[3 * i + 1], buf[3 * i + 2]) == rgb)


def test_draw_overlap_keyline_marks_overlaps_and_leaves_clean_numbers_alone():
    # A keyline (white) appears only where two numbers overlap; non-overlapping numbers get none.
    size = 60
    overlapping = [_filled_square(10, 10, 30, 30), _filled_square(22, 10, 42, 30)]   # share x22..30
    disjoint = [_filled_square(4, 4, 14, 14), _filled_square(40, 40, 52, 52)]        # no shared pixel
    buf_ov = _new_buf(size)
    _draw_overlap_keyline(buf_ov, size, overlapping)
    buf_dj = _new_buf(size)
    _draw_overlap_keyline(buf_dj, size, disjoint)
    assert _count_rgb(buf_ov, size, (255, 255, 255)) > 0      # overlap -> keyline drawn
    assert _count_rgb(buf_dj, size, (255, 255, 255)) == 0     # no overlap -> nothing


def test_draw_overlap_keyline_is_white_and_exactly_one_pixel_wide():
    # The keyline is a 1px ring: no keyline pixel has ALL four orthogonal neighbours also keyline (a
    # >=2px-thick band would). Constant width, independent of the numbers' size/zoom.
    size = 80
    buf = _new_buf(size)
    _draw_overlap_keyline(buf, size, [_filled_square(20, 20, 55, 55), _filled_square(40, 20, 70, 55)])
    key = {(x, y) for x in range(size) for y in range(size)
           if (buf[3 * (y * size + x)], buf[3 * (y * size + x) + 1], buf[3 * (y * size + x) + 2])
           == (255, 255, 255)}
    assert key
    thick = [(x, y) for (x, y) in key
             if {(x + 1, y), (x - 1, y), (x, y + 1), (x, y - 1)} <= key]
    assert thick == []


def _floor(side):
    h = side / 2.0
    return [(-h, -h, 0.0), (h, -h, 0.0), (h, h, 0.0), (-h, h, 0.0)]


def test_onface_omits_a_number_too_small_to_read_on_screen():
    # A projected-pixel verdict: at 1:1 projection a roomy face reads and is numbered; a tiny face's
    # glyph texels fall below the min px and it is dropped.
    def w2p(p):                                            # top-down 1:1 projection (a floor cap)
        return (p[0], p[1])
    assert _plan_onface_texture(_floor(60), w2p, "5") is not None    # big on screen → numbered
    assert _plan_onface_texture(_floor(12), w2p, "5") is None        # tiny on screen → omitted


def test_onface_omit_is_view_dependent_on_projected_scale():
    # The SAME face is numbered when it projects big and omitted when it projects small — the verdict is
    # on-screen size, not world size.
    face = _floor(40)
    assert _plan_onface_texture(face, lambda p: (p[0] * 1.0, p[1] * 1.0), "5") is not None   # zoomed in
    assert _plan_onface_texture(face, lambda p: (p[0] * 0.2, p[1] * 0.2), "5") is None       # zoomed out


def test_onface_decal_paints_substantial_content():
    # A subtract cube's face numbers (now 0.75 of the largest inscribed box) paint substantially more
    # than a names-only render. (Size vs the retired 0.2-fill is pinned by the _max_inscribed_box unit
    # tests; this only asserts a decal is drawn end-to-end.)
    a = _sub_cube("Room", (0, 0, 0))
    numbered = render_brushes_pgm([a], view="iso", size=256, annotations=AnnotationSpec.all(), color_by_csg=True)
    plain = render_brushes_pgm([a], view="iso", size=256, annotations=parse_annotation_spec("name"),
                               color_by_csg=True)
    assert _nonbg(numbered) > _nonbg(plain) + 200          # substantially more painted content


def test_line_dim_alpha_composites_over_content_instead_of_overwriting():
    # A dimmed (alpha) line must COMPOSITE over whatever it crosses (so a faint --focus brush's edge
    # lets a bright edge/number show through) — not hard-overwrite it as an opaque paint would.
    buf = _new_buf(20)
    _line(buf, 20, (10, 0), (10, 19), (0, 0, 200))                 # opaque blue vertical
    _line(buf, 20, (0, 10), (19, 10), (200, 0, 0), alpha=_DIM_ALPHA)   # dim red horizontal across it

    def px(x, y):
        i = (y * 20 + x) * 3
        return (buf[i], buf[i + 1], buf[i + 2])
    over_blue = tuple(round(_DIM_ALPHA * r + (1 - _DIM_ALPHA) * b) for r, b in zip((200, 0, 0), (0, 0, 200)))
    over_bg = tuple(round(_DIM_ALPHA * r + (1 - _DIM_ALPHA) * BG) for r in (200, 0, 0))
    assert px(10, 10) == over_blue        # at the crossing: red composited OVER the blue line
    assert px(10, 10) != over_bg          # NOT a hard overwrite / not blended with the background
    assert px(5, 10) == over_bg           # away from the crossing: composited over the background
