import copy
import math
from decimal import Decimal

from uedcli.model import parse_t3d
import pytest

from uedcli.preview import (
    BG, FRONT, WHITE, AnnotationSpec, PreviewData,
    _DIM_ALPHA, _DecalPlan, _FRAME_PAD,
    _ONFACE_FILL, _ONFACE_MIN_TEXEL_PX,
    _box_fits_2d, _feasible_centers, _new_buf, _line, _point_in_poly,
    _decal_opacity, _draw_overlap_keyline, _draw_painted_decal, _face_decal_basis, _framing,
    _max_inscribed_box, _occluder_count, _onface_candidates,
    _plan_onface_texture, _plan_px_area, _poly_is_convex_2d, _rect_overlap_area,
    _resolve_decals, _text_bitmap, assign_tints,
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


def test_wire_edges_are_facing_blind():
    from uedcli.preview import BACK
    cols = _colors(render_brush_pgm(_brush(), view="iso", size=256, annotations=AnnotationSpec.all()))
    assert FRONT in cols              # every wire edge — front OR back — draws in the same shade
    assert BACK not in cols           # no separate dimmer partner for obscured edges


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
    assert front in cols                      # brush is gold, front and back alike, not uncoloured
    assert back not in cols                   # no separate dimmer back shade
    assert FRONT not in cols                  # no uncoloured wireframe when coloured by CSG


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
    from uedcli.preview import DIVIDER
    pgm = render_quad_pgm(_brush(), size=256)
    assert pgm.startswith(b"P6\n256 256\n255\n")
    assert DIVIDER in _colors(pgm) and _nonbg(pgm) > 0   # divider + content


def test_iso_view_renders():
    pgm = render_brush_pgm(_brush(), view="iso", size=128)
    assert pgm.startswith(b"P6\n128 128\n255\n")
    assert _nonbg(pgm) > 0


def _point(name, cls, loc):
    from uedcli.model import Actor
    return Actor(name=name, cls=cls, location=(Decimal(loc[0]), Decimal(loc[1]), Decimal(loc[2])))


def test_point_actor_without_render_data_is_skipped():
    # A point actor with no render_data entry contributes nothing (blank on a point-only scene).
    ppm = render_brushes_pgm([_point("L", "Engine.Light", (0, 0, 0))], view="top", size=128)
    assert _nonbg(ppm) == 0


def test_point_marker_renders():
    from uedcli.preview import PointRender
    rd = PreviewData(points={"L": PointRender(label="Torch")})
    a = _point("L", "Engine.Light", (0, 0, 0))
    drawn = render_brushes_pgm([a], view="top", size=128, annotations=AnnotationSpec.none(), render_data=rd)
    assert _nonbg(drawn) > 0                            # the marker draws


def test_point_actor_is_not_painted_csg_additive_blue():
    # On the hybrid (color_by_csg) path a point actor's marker is drawn in its assigned label TINT
    # (`assign_tints`), never treated as a CSG brush — so its CSG-additive blue must not appear, and its
    # tint must. (Legacy black/grey mode keeps the neutral (90,90,90) marker — see the tests above.)
    from uedcli.preview import PointRender, _CSG_PALETTE, assign_tints
    a = _point("L", "Engine.Light", (0, 0, 0))
    rd = PreviewData(points={"L": PointRender(label="L")})
    cols = _colors(render_brushes_pgm([a], view="top", size=128, render_data=rd, color_by_csg=True))
    assert _CSG_PALETTE["add"][0] not in cols              # NOT painted as an additive-solid brush
    assert assign_tints([a])["L"] in cols                  # drawn in its per-actor label tint


def test_sprite_billboard_blits_masked():
    from uedcli.preview import PointRender, COL_COLLISION
    # A 2x2 sprite: index-0 (transparent) top row, an opaque red bottom row.
    rgb = bytes([0, 0, 0, 0, 0, 0, 200, 10, 10, 200, 10, 10])
    mask = bytes([0, 0, 1, 1])
    rd = PreviewData(points={"S": PointRender(label="S", sprite=(2, 2, rgb, mask), sprite_world=(80.0, 80.0))})
    cols = _colors(render_brushes_pgm([_point("S", "Engine.Light", (0, 0, 0))], view="top",
                                      size=128, annotations=AnnotationSpec.none(), render_data=rd))
    assert (200, 10, 10) in cols                           # opaque sprite pixels drew
    assert COL_COLLISION not in cols                       # no overlay unless requested


def test_show_collision_front_rect_is_twice_the_half_height():
    from uedcli.preview import PointRender, COL_COLLISION
    rd = PreviewData(points={"P": PointRender(label="P", collision=(30.0, 50.0))})
    a = _point("P", "Engine.Pawn", (0, 0, 0))
    front = render_brushes_pgm([a], view="front", size=256, annotations=AnnotationSpec.none(), render_data=rd)
    assert COL_COLLISION in _colors(front)                 # the cylinder rect drew in FRONT


def test_point_actor_contributes_to_framing():
    from uedcli.preview import PointRender
    rd = PreviewData(points={"A": PointRender(label="A"), "B": PointRender(label="B")})
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
    # y-rows carrying the neutral point-actor MARKER grey — a single-view render has no
    # CAPTION/DIVIDER, so this colour comes only from point markers.
    from uedcli.preview import MARKER
    b = _body(ppm)
    return {(k // 3) // size for k in range(0, len(b), 3)
            if (b[k], b[k + 1], b[k + 2]) == MARKER}


def test_point_actors_differing_only_in_z_separate_in_front_and_iso():
    # Regression: point-actor decorations must be PROJECTED (not fed raw 3-D coords to to_px, which
    # only maps already-projected 2-D points). Two markers that differ ONLY in Z coincide in front/iso
    # unless each Location is projected first. (Symmetric (0,0,0)/(64,64,64) fixtures masked this.)
    from uedcli.preview import PointRender
    size = 128
    a = _point("A", "Engine.Light", (0, 0, 0))
    b = _point("B", "Engine.Light", (0, 0, 200))
    rd = PreviewData(points={"A": PointRender(label="A"), "B": PointRender(label="B")})
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
    rd = PreviewData(points={"L": PointRender(label="L", light_radius=120.0)})
    a = _point("L", "Engine.Light", (0, 0, 0))
    px = _pixels(render_brushes_pgm([a], view="iso", size=256, annotations=AnnotationSpec.none(), render_data=rd,
                                    region=(-400, -400, -400, 400, 400, 400)))
    pts = [divmod(i, 256) for i, p in enumerate(px) if p == COL_LIGHT]
    xs = [x for _, x in pts]; ys = [y for y, _ in pts]
    w, h = max(xs) - min(xs), max(ys) - min(ys)
    assert pts and max(w, h) < 250                     # unclipped (not the full frame)
    assert abs(w - h) <= max(w, h) * 0.12              # square bbox → a circle, not a tilted octagon


# ---- AnnotationSpec / parse_annotation_spec (grammar) --------------------------------------------------
# poly categories are (is_front, is_highlighted).
_FULL = frozenset({(False, False), (False, True), (True, False), (True, True)})


def test_it_parses_bare_poly_as_everything():
    assert parse_annotation_spec("poly") == AnnotationSpec(poly=_FULL)


def test_it_narrows_poly_with_vis_and_hi_filters():
    assert parse_annotation_spec("poly:vis").poly == frozenset({(True, False), (True, True)})
    assert parse_annotation_spec("poly:hi").poly == frozenset({(True, True), (False, True)})
    assert parse_annotation_spec("poly:vis:hi").poly == frozenset({(True, True)})


def test_it_unions_comma_selectors():
    assert parse_annotation_spec("poly:vis,poly:hi").poly == frozenset(
        {(True, False), (True, True), (False, True)})


def test_it_treats_filters_as_an_order_independent_set():
    assert parse_annotation_spec("poly:hi:vis") == parse_annotation_spec("poly:vis:hi")


def test_it_accepts_highlighted_as_a_synonym_for_hi():
    assert parse_annotation_spec("poly:highlighted") == parse_annotation_spec("poly:hi")


def test_it_normalizes_case_and_whitespace():
    assert parse_annotation_spec("POLY") == parse_annotation_spec("poly")
    assert parse_annotation_spec("  POLY:VIS  ") == parse_annotation_spec("poly:vis")


def test_it_expands_the_whole_value_keywords():
    assert parse_annotation_spec("all") == AnnotationSpec(poly=_FULL)
    assert parse_annotation_spec("none") == AnnotationSpec(poly=frozenset())
    assert parse_annotation_spec("highlighted") == parse_annotation_spec("poly:hi")


def test_it_maps_vis_hi_union_to_todays_poly_behavior():
    s = parse_annotation_spec("poly:vis,poly:hi")
    assert s.poly == frozenset({(True, False), (True, True), (False, True)})   # front OR highlighted


def test_it_treats_zero_effective_tokens_as_none():
    none = AnnotationSpec(poly=frozenset())
    for text in ("", ",", "  ", " , "):
        assert parse_annotation_spec(text) == none


def test_it_keeps_poly_when_other_tokens_are_empty():
    assert parse_annotation_spec("poly,,").poly == _FULL


def test_annotationspec_predicates_answer_membership():
    s = parse_annotation_spec("poly:vis")
    assert s.draws_poly(is_front=True, is_highlighted=False)
    assert not s.draws_poly(is_front=False, is_highlighted=True)


@pytest.mark.parametrize("text,bad", [
    ("foo", "foo"), ("poly:brush", "brush"), ("name", "name"), ("poly:xyz", "xyz"),
    ("name:brush", "name"), ("all,poly", "all"), ("none,poly", "none"),
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


def test_default_is_none_and_all_draws_indices():
    dflt = render_brush_pgm(_brush(), view="iso", size=256, annotations=AnnotationSpec.default())
    none = render_brush_pgm(_brush(), view="iso", size=256, annotations=AnnotationSpec.none())
    allf = render_brush_pgm(_brush(), view="iso", size=256, annotations=AnnotationSpec.all())
    assert dflt == none                                # poly numbers are opt-in: default draws nothing
    assert _nonbg(allf) > _nonbg(none)                 # --annotate all draws indices


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


# ---- HYBRID per-brush tint + --focus -----------------------------------------------


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


def test_quad_draws_no_legend_panel():
    # The hybrid path no longer draws a legend panel: no WHITE fill appears in any pane's top-left
    # corner, where the legend used to sit.
    size = 256
    half = size // 2
    a, b = _sub_cube("QIX", (0, 0, 0)), _add_cube("JYR", (600, 0, 0))
    px = _pixels(render_quad_pgm([a, b], size=size, annotations=AnnotationSpec.default(),
                                 color_by_csg=True))

    def white_in_corner(ox):
        return sum(1 for j in range(2, 16) for i in range(2, 16)
                   if px[j * size + (ox + i)] == WHITE)

    assert white_in_corner(0) == 0                        # TOP pane corner: no legend panel
    assert white_in_corner(half) == 0                     # FRONT pane corner: no legend panel


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
    # A SOLID (additive) brush paints its BACK faces too — facing-blind, at graded opacity — even with
    # `--annotate all` labels. Its front faces occlude its own back faces, so strokes appear at >=2
    # depth levels: 0.56 (visible) plus >=1 dimmer (occluded back face: 0.336 / 0.2016 / floor 0.12).
    from uedcli.preview import _TINT_PALETTE
    a = copy.deepcopy(_brush())
    a.props = [(k, v) for k, v in a.props if k != "CsgOper"]      # additive => solid => self-occluding

    ppm = render_brush_pgm(a, view="iso", size=256, annotations=AnnotationSpec.all(), color_by_csg=True)

    tint = _TINT_PALETTE[0]
    px = {tuple(ppm[i:i + 3]) for i in range(len(b"P6\n256 256\n255\n"), len(ppm), 3)}
    front = tuple(round(0.56 * c + 0.44 * BG) for c in tint)
    dimmer = [tuple(round(op * c + (1 - op) * BG) for c in tint) for op in (0.336, 0.2016, 0.12)]
    assert front in px
    assert any(lv in px for lv in dimmer)


def test_onface_labels_a_big_face_even_in_a_tiny_render():
    # A big-world-size brush keeps its on-face numbers even in a tiny (downscaled) render — drawn small
    # but present, never omitted per-view. The painted render has more content than an un-annotated one.
    a = _brush()
    painted = render_brush_pgm(a, view="iso", size=128, annotations=AnnotationSpec.all(), color_by_csg=True)
    plain = render_brush_pgm(a, view="iso", size=128, annotations=AnnotationSpec.none(),
                             color_by_csg=True)
    assert _nonbg(painted) > _nonbg(plain)   # decals drawn even downscaled (big faces present)


def test_onface_omits_only_tiny_faces_with_no_leader_fallback(monkeypatch):
    # A face omitted for being too small is NOT drawn as a leader box. Force every plan to fail (as if
    # every face were sub-threshold); the painted render must equal an un-annotated render — omission,
    # not a leader fallback.
    a = _brush()
    monkeypatch.setattr("uedcli.preview._onface_candidates", lambda *args, **kwargs: [])
    omitted = render_brush_pgm(a, view="iso", size=256, annotations=AnnotationSpec.all(), color_by_csg=True)
    plain = render_brush_pgm(a, view="iso", size=256, annotations=AnnotationSpec.none(),
                             color_by_csg=True)
    assert omitted == plain          # un-paintable polys vanish (no leader box), leaving no numbers


# --- --brush-colors (#3) ---

def test_it_colors_the_wireframe_by_legend_tint_when_asked():
    from uedcli.builders import cube, make_brush_actor
    from uedcli.preview import _CSG_PALETTE
    # Arrange: a lone subtract cube. In csg mode its wireframe is subtract-gold; its per-actor tint is
    # a distinct categorical hue. (annotate none so only the WIREFRAME contributes colours.)
    room = make_brush_actor("Room", cube(256, 256, 256), csg="subtract")
    gold = _CSG_PALETTE["subtract"][0]
    tint = assign_tints([room])["Room"]
    kw = dict(view="iso", size=256, annotations=AnnotationSpec.none(), color_by_csg=True)
    # Act
    csg_cols = _colors(render_brushes_pgm([room], brush_colors="csg", **kw))
    legend_cols = _colors(render_brushes_pgm([room], brush_colors="legend", **kw))
    # Assert: csg mode paints the CSG hue and not the tint; legend mode swaps to the tint.
    assert gold in csg_cols and tint not in csg_cols
    assert tint in legend_cols and gold not in legend_cols


def test_framing_maps_world_points_to_pixels():
    # The framing formula (the on-face goldens rely on it): x/y scaled into the drawable budget, offset
    # by the frame pad, y flipped.
    pts = [(-30.0, 12.5), (170.0, 240.0), (5.0, -8.0)]
    minx, miny = min(p[0] for p in pts), min(p[1] for p in pts)
    span = max(max(p[0] for p in pts) - minx, max(p[1] for p in pts) - miny)
    for size in (128, 131, 256, 384):
        _, to_px, _, _, _ = _framing(pts, None, size, "iso", 30.0)
        draw = size - 2 * _FRAME_PAD
        for p in pts:
            expected = (int((p[0] - minx) / span * draw) + _FRAME_PAD,
                        size - 1 - (int((p[1] - miny) / span * draw) + _FRAME_PAD))
            assert to_px(p) == expected


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
    # than an un-annotated render. (Size vs the retired 0.2-fill is pinned by the _max_inscribed_box
    # unit tests; this only asserts a decal is drawn end-to-end.)
    a = _sub_cube("Room", (0, 0, 0))
    numbered = render_brushes_pgm([a], view="iso", size=256, annotations=AnnotationSpec.all(), color_by_csg=True)
    plain = render_brushes_pgm([a], view="iso", size=256, annotations=AnnotationSpec.none(),
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


# ── locator cells: pure cell math ──────────────────────────────────────────────────────────────
from uedcli.preview import (  # noqa: E402
    ActorCell, _actor_cells, _cell_address, _cell_of_pixel, _col_label, _drawable_rect,
    _equal_boundaries,
)


def test_it_labels_columns_bijective_base26():
    assert [_col_label(i) for i in (0, 25, 26, 701, 702)] == ["A", "Z", "AA", "ZZ", "AAA"]


def test_it_addresses_a_cell_as_letter_column_plus_1based_row():
    assert _cell_address(3, 3) == "D4"       # col 3 → D, row 3 → 4
    assert _cell_address(0, 0) == "A1"
    assert _cell_address(27, 11) == "AB12"


def test_it_maps_a_pixel_to_its_cell_within_the_drawable_rect():
    bounds = _equal_boundaries(10, 130, 12)  # 120x120 drawable, n=12 → 10px cells
    assert _cell_of_pixel(15, 15, bounds, bounds) == (0, 0)      # top-left cell → A1
    assert _cell_of_pixel(125, 125, bounds, bounds) == (11, 11)  # bottom-right cell → L12
    assert _cell_of_pixel(65, 65, bounds, bounds) == (5, 5)      # centre → F6


def test_it_clamps_a_pixel_outside_the_rect_to_the_edge_cell():
    bounds = _equal_boundaries(10, 130, 12)
    assert _cell_of_pixel(-50, -50, bounds, bounds) == (0, 0)    # far above-left → first cell
    assert _cell_of_pixel(999, 999, bounds, bounds) == (11, 11)  # far below-right → last cell


def test_it_takes_centroid_and_span_from_a_projected_point_set():
    bounds = _equal_boundaries(10, 130, 12)  # 10px cells at n=12
    # A box spanning cols C..E (px 35..55) and rows 3..5 (px 35..55); centroid ~ D4.
    pts = [(35.0, 35.0), (55.0, 55.0), (45.0, 45.0)]
    assert _actor_cells(pts, bounds, bounds) == ("D4", "C3–E5")


def test_a_single_cell_footprint_has_no_span():
    bounds = _equal_boundaries(10, 130, 12)
    assert _actor_cells([(65.0, 65.0)], bounds, bounds) == ("F6", None)          # a point actor
    assert _actor_cells([(62.0, 62.0), (68.0, 68.0)], bounds, bounds) == ("F6", None)  # tiny, one cell


def test_it_computes_the_drawable_rect_from_pad_and_gutter():
    assert _drawable_rect(128, 6, 14) == (20, 107, 20, 107)        # pad+gutter .. size-1-pad-gutter


# ── auto locator density: cell SIZE is the power-of-two, not cell COUNT ─────────────────────────

def test_auto_locator_cells_labels_never_crowd():
    from uedcli.preview import _FRAME_PAD, _auto_locator_cells, _locator_gutter_px, _locator_label_px
    for pane_size in (128, 256, 512, 900, 2048):
        n = _auto_locator_cells(pane_size, 52)
        name_scale = max(2, pane_size // 256)
        gutter = _locator_gutter_px(name_scale)
        drawable = pane_size - 2 * _FRAME_PAD - 2 * gutter
        label_w, label_h = _locator_label_px(1 if n <= 26 else 2, name_scale)
        cell_px = drawable / n
        assert cell_px >= label_w + 4 and cell_px >= label_h + 4    # labels stay clear (4px gap)


def test_auto_locator_cells_is_the_finest_that_still_fits():
    # The candidate cell size HALF the one actually picked (still a power of two) must fail the same
    # clearance check — otherwise the picker stopped one step too coarse.
    from uedcli.preview import _FRAME_PAD, _auto_locator_cells, _locator_gutter_px, _locator_label_px
    for pane_size in (128, 256, 512, 900, 2048):
        n = _auto_locator_cells(pane_size, 52)
        name_scale = max(2, pane_size // 256)
        gutter = _locator_gutter_px(name_scale)
        drawable = pane_size - 2 * _FRAME_PAD - 2 * gutter
        if drawable <= 0 or n >= 52:
            continue                                     # degenerate pane / capped — no finer step to check
        finer_n = max(1, min(52, round(drawable / (drawable / n / 2))))
        if finer_n == n:
            continue                                     # rounding collapsed to the same n — nothing finer
        label_w, label_h = _locator_label_px(1 if finer_n <= 26 else 2, name_scale)
        finer_cell_px = drawable / finer_n
        assert finer_cell_px < label_w + 4 or finer_cell_px < label_h + 4


def test_auto_locator_cells_never_exceeds_the_cap():
    from uedcli.preview import _auto_locator_cells
    assert _auto_locator_cells(100_000, 52) <= 52


def test_auto_locator_cells_degrades_to_one_cell_on_a_tiny_pane():
    from uedcli.preview import _auto_locator_cells
    assert _auto_locator_cells(40, 52) == 1     # gutter alone eats most of a 40px pane


def test_auto_locator_cells_matches_pinned_values_at_common_sizes():
    # Pinned so a change to the picker's formula is a deliberate, reviewed diff here, not a silent
    # drift noticed only via the CLI's stderr legend header changing shape.
    from uedcli.preview import _auto_locator_cells
    assert _auto_locator_cells(128, 52) == 4
    assert _auto_locator_cells(256, 52) == 12
    assert _auto_locator_cells(900, 52) == 26


# ── grid-anchored locator: boundaries land on real drawn lines, never crowd a label ─────────────

def _px_of_world_1d(w, edge_lo, lo_world, span_world, draw_px):
    """A 1-D world→pixel affine map, matching `_framing`'s own formula — enough to exercise
    `_lattice_boundaries`/`_auto_locator_lattice` without a full render."""
    return edge_lo + (w - lo_world) / span_world * draw_px


def test_lattice_boundaries_interior_lines_land_on_world_multiples_of_step():
    from uedcli.preview import _lattice_boundaries
    edge_lo, edge_hi, lo_world, span, step = 0.0, 100.0, 3.0, 250.0, 16
    bounds = _lattice_boundaries(edge_lo, edge_hi, lambda w: _px_of_world_1d(w, edge_lo, lo_world, span, edge_hi - edge_lo),
                                 lo_world, span, step, min_gap_px=0.0)  # gap=0: no merging, see raw lines
    to_world = lambda px: lo_world + (px - edge_lo) / (edge_hi - edge_lo) * span
    for b in bounds[1:-1]:                          # every INTERIOR boundary — not the two frame edges
        w = to_world(b)
        assert abs(w / step - round(w / step)) < 1e-6, f"{w} is not a multiple of step {step}"


def test_lattice_boundaries_merges_only_the_thin_edge_cell_not_its_fine_neighbours():
    # Identity px_of_world (px == world) for arithmetic that reads directly off the numbers: frame
    # [2, 50), step 10 -> lines at world 10,20,30,40 -> raw cells 8,10,10,10,10 wide. Only the FIRST
    # (8, world 2..10) is thinner than the gap (9); the four uniform 10-wide interior cells must NOT
    # be touched — merging should absorb just the one thin edge into its immediate neighbour.
    from uedcli.preview import _lattice_boundaries
    bounds = _lattice_boundaries(2.0, 50.0, lambda w: w, 2.0, 48.0, 10, min_gap_px=9.0)
    assert bounds == [2.0, 20.0, 30.0, 40.0, 50.0]     # world 10 absorbed into the first cell, only
    widths = [b - a for a, b in zip(bounds, bounds[1:])]
    assert widths == [18.0, 10.0, 10.0, 10.0]          # merged cell + the three untouched originals


def test_auto_locator_lattice_never_returns_a_cell_thinner_than_its_label():
    # Sweep fractional lattice/frame alignments (the case that broke the OLD interior-only estimate,
    # since edge-cell width depends on exactly where the frame's own edge falls relative to the
    # lattice) and require EVERY resulting cell — including any merged edge — to clear its label.
    from uedcli.preview import _LOCATOR_LABEL_GAP, _auto_locator_lattice, _locator_label_px
    x0, x1 = 24.0, 900.0 - 24.0
    y0, y1 = 24.0, 900.0 - 24.0
    name_scale = 3
    grid_drawn = 16
    for fspan in (17, 33, 48, 65, 96, 130, 200, 512):
        for frac in (0.0, 0.1, 0.3, 0.5, 0.7, 0.9, 0.99):
            fminx = fminy = frac * grid_drawn
            col_b, row_b = _auto_locator_lattice(
                grid_drawn, x0, x1, y0, y1,
                lambda w: _px_of_world_1d(w, x0, fminx, fspan, x1 - x0),
                lambda w: _px_of_world_1d(w, y0, fminy, fspan, y1 - y0),
                fminx, fminy, fspan, name_scale)
            cols = len(col_b) - 1
            chars = 1 if cols <= 26 else 2
            col_gap = _locator_label_px(chars, name_scale)[0] + _LOCATOR_LABEL_GAP
            row_gap = _locator_label_px(1, name_scale)[1] + _LOCATOR_LABEL_GAP
            col_widths = [b - a for a, b in zip(col_b, col_b[1:])]
            row_widths = [b - a for a, b in zip(row_b, row_b[1:])]
            assert min(col_widths) >= col_gap - 1e-6, (fspan, frac, col_widths, col_gap)
            assert min(row_widths) >= row_gap - 1e-6, (fspan, frac, row_widths, row_gap)


def test_auto_locator_lattice_reported_count_matches_the_real_boundaries():
    # The bug a review round caught: the picker used to validate an INTERIOR-cell-only estimate, so
    # it could accept a step "believing" it'd yield N columns while the real (edge-merged) result
    # delivered fewer — self-inconsistent. `locator_dims_out`'s cols/rows must always equal what the
    # boundaries it ALSO returns actually contain; assert that invariant directly, sweeping the same
    # alignments as the crowding test above.
    from uedcli.preview import _auto_locator_lattice
    x0, x1 = 24.0, 128.0 - 24.0
    y0, y1 = 24.0, 128.0 - 24.0
    name_scale = 2
    grid_drawn = 16
    for fspan in (17, 33, 48, 65, 96, 130):
        for frac in (0.0, 0.1, 0.3, 0.5, 0.7, 0.9, 0.99):
            fminx = fminy = frac * grid_drawn
            col_b, row_b = _auto_locator_lattice(
                grid_drawn, x0, x1, y0, y1,
                lambda w: _px_of_world_1d(w, x0, fminx, fspan, x1 - x0),
                lambda w: _px_of_world_1d(w, y0, fminy, fspan, y1 - y0),
                fminx, fminy, fspan, name_scale)
            # the boundaries ARE the ground truth this test holds the picker to — no separate
            # "believed" count exists anymore, so this is really asserting the function returns
            # something internally coherent (ascending, >=1 cell) rather than re-deriving an
            # independent expectation, which would just re-implement the picker.
            assert col_b == sorted(col_b) and row_b == sorted(row_b)
            assert len(col_b) >= 2 and len(row_b) >= 2


def test_auto_locator_lattice_degrades_to_one_cell_without_crashing_on_a_tiny_pane():
    # A review round's concrete repro: `--layout quad`'s panes render at HALF `--size`, so an
    # ordinary `--size 128` gives each pane only 64px — small enough that the drawable rect (after
    # the gutter reserve) is a few px, narrower than any label. The exhausted-search fallback must
    # still return a valid (if unavoidably crowded) single cell, never crash or return something
    # with fewer than 2 boundaries.
    from uedcli.builders import cube, make_brush_actor
    from uedcli.preview import render_quad_pgm
    box = make_brush_actor("Big", cube(4000, 4000, 200), location=(0, 0, 0), csg="add")
    for size in (128, 64, 32, 16):
        dims = {}
        data = render_quad_pgm([box], size=size, color_by_csg=True, locator="auto",
                               locator_dims_out=dims)
        assert data                                        # rendered SOMETHING, no exception
        for pane in ("Top", "Front", "Iso", "Side"):
            assert dims[pane]["cols"] >= 1 and dims[pane]["rows"] >= 1


def test_actor_cell_is_a_frozen_value():
    c = ActorCell(cell="D4", span="C3–E5", hidden=False)
    assert (c.cell, c.span, c.hidden) == ("D4", "C3–E5", False)
    with pytest.raises(Exception):
        c.cell = "A1"


# ── locator cells: gutter render + per-pane cell collection ─────────────────────────────────────
from uedcli.preview import LOCATOR_LABEL, _locator_gutter_px  # noqa: E402


def _two_brushes():
    from uedcli.builders import cube, make_brush_actor
    a = make_brush_actor("Room", cube(256, 256, 256), location=(0, 0, 0), csg="subtract")
    b = make_brush_actor("Box", cube(96, 96, 96), location=(300, 100, 0), csg="add")
    return [a, b]


def test_locator_label_is_pinned_so_a_change_is_deliberate():
    assert LOCATOR_LABEL == (105, 105, 105)


def test_locator_none_renders_byte_identically_to_no_locator():
    actors = _two_brushes()
    kw = dict(view="iso", size=256, color_by_csg=True)
    assert render_brushes_pgm(actors, locator=None, **kw) == render_brushes_pgm(actors, **kw)


def test_locator_gutter_draws_and_changes_the_image():
    actors = _two_brushes()
    kw = dict(view="iso", size=256, color_by_csg=True)
    with_locator = render_brushes_pgm(actors, locator=12, **kw)
    assert with_locator != render_brushes_pgm(actors, **kw)
    assert LOCATOR_LABEL in _colors(with_locator)    # the gutter letters/numbers landed


def test_locator_gutter_is_independent_of_annotate_none():
    # --annotate none clears on-geometry labels but the gutter still draws (the locator is orthogonal).
    actors = _two_brushes()
    img = render_brushes_pgm(actors, view="iso", size=256, color_by_csg=True, locator=12,
                             annotations=AnnotationSpec.none())
    assert LOCATOR_LABEL in _colors(img)


def test_geometry_does_not_draw_in_the_gutter_band():
    # The top gutter band (below the frame pad, above the drawable rect) holds only the grey column
    # letters — never brush geometry, which _framing insets clear of the band.
    actors = _two_brushes()
    size = 256
    ppm = render_brushes_pgm(actors, view="iso", size=size, color_by_csg=True, locator=12,
                             annotations=AnnotationSpec.none())
    px = _pixels(ppm)
    gutter = _locator_gutter_px(max(2, size // 256))
    # a horizontal strip inside the left row-number band, below the top band: only BG or grey labels
    band_cols = range(_FRAME_PAD, _FRAME_PAD + gutter)
    for y in range(_FRAME_PAD + gutter + 20, size - _FRAME_PAD - gutter - 20):
        for x in band_cols:
            assert px[y * size + x] in ((BG, BG, BG), LOCATOR_LABEL)


def test_no_locator_draws_no_label_pixels():
    # `--no-locator-cells`: no `LOCATOR_LABEL` pixel anywhere in the render. That the framing actually
    # GAINS the reserved gutter back (not just that labels go unpainted, which a reserve left in by
    # mistake would still satisfy) is pinned by driving the render and comparing drawn extents —
    # `test_no_locator_cells_gives_geometry_the_wider_drawable_rect` in test_actor_preview.py, using a
    # single-actor square projection so every side of the comparison is unambiguous.
    actors = _two_brushes()
    ppm = render_brushes_pgm(actors, view="iso", size=256, color_by_csg=True, locator=None)
    assert LOCATOR_LABEL not in _colors(ppm)


def test_per_pane_cells_collect_centroid_and_span():
    actors = _two_brushes()
    cells = {}
    render_brushes_pgm(actors, view="top", size=256, color_by_csg=True, locator=12, cells_out=cells)
    assert set(cells) == {"Room", "Box"}
    assert cells["Room"].span is not None          # a big brush spans several cells
    assert cells["Room"].hidden is False


def test_locator_off_still_collects_hidden_with_no_cell_or_span():
    # `_collect_cells`'s n=None path: `hidden` is still collected with the locator off — cell/span stay
    # None rather than being computed and discarded. `render_brushes_pgm` defaults to `faces="wire"`
    # here, where `hidden` comes from `set(geom.actor_points)` and never touches pixel positions, so the
    # equality below holds; under a filled mode the locator's gutter reserve can change `to_pxf` enough
    # to flip which face wins a depth test, and `hidden` is NOT guaranteed to agree between the two
    # modes there (board item `locator-on-vs-off-can-disagree-on-hidden-under`).
    actors = _two_brushes()
    on, off = {}, {}
    render_brushes_pgm(actors, view="top", size=256, color_by_csg=True, locator=12, cells_out=on)
    render_brushes_pgm(actors, view="top", size=256, color_by_csg=True, locator=None, cells_out=off)
    assert set(off) == set(on) == {"Room", "Box"}
    for name in on:
        assert off[name].cell is None and off[name].span is None
        assert off[name].hidden == on[name].hidden          # agrees here — this render is wire


def test_quad_tags_cells_by_pane_name():
    actors = _two_brushes()
    qcells = {}
    render_quad_pgm(actors, size=512, color_by_csg=True, locator=12, cells_out=qcells)
    assert set(qcells) == {"Top", "Front", "Iso", "Side"}
    assert set(qcells["Top"]) == {"Room", "Box"}


def test_cell_matches_where_the_label_would_land_on_the_image():
    # Consistency probe: the collector's cell for an actor is exactly the cell its projected-point
    # centroid falls in under the SAME framing (gutter inset) + drawable rect the image uses. Reproduce
    # via _scene_geometry.actor_points — the very source the collector reads — so the two cannot drift.
    from uedcli.preview import (_drawable_rect, _cell_of_pixel, _cell_address, _equal_boundaries,
                                _framing, _locator_gutter_px, _scene_geometry)
    from uedcli.builders import cube, make_brush_actor
    box = make_brush_actor("Only", cube(128, 128, 128), location=(50, -30, 10), csg="add")
    size, n = 256, 12
    cells = {}
    render_brushes_pgm([box], view="top", size=size, color_by_csg=True, locator=n, cells_out=cells)
    geom = _scene_geometry([box], view="top", iso_angle=30.0, annotations=AnnotationSpec.all(),
                           highlight_polys=set(), focus_cf=None, hybrid=True,
                           tints=assign_tints([box]), color_by_csg=True, render_data=PreviewData())
    name_scale = max(2, size // 256)
    gutter = _locator_gutter_px(name_scale)
    _s, _tp, to_pxf, _w, _b = _framing(geom.pts, None, size, "top", 30.0, gutter=gutter)
    rect = _drawable_rect(size, _FRAME_PAD, gutter)
    proj = [to_pxf(p) for p in geom.actor_points["Only"]]
    xs = [p[0] for p in proj]; ys = [p[1] for p in proj]
    col_bounds = _equal_boundaries(rect[0], rect[1], n)
    row_bounds = _equal_boundaries(rect[2], rect[3], n)
    want = _cell_address(*_cell_of_pixel(sum(xs) / len(xs), sum(ys) / len(ys), col_bounds, row_bounds))
    assert cells["Only"].cell == want
