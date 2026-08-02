"""`actor preview --faces` behaviour: the `wire` byte-identity golden, and `flat`'s cull, fill,
edge rule and refusals.

**The golden pair is the primary regression guard for the whole `--faces` feature.** It was captured
from the tree BEFORE any `--faces` code existed, so it pins the pre-existing wireframe rather than the
rewrite; every later slice re-asserts it. Re-bless only after deciding the wireframe itself should
change: `UEDCLI_BLESS_GOLDEN=1 bin/test -k wire_golden`.
"""
import os
from decimal import Decimal
from pathlib import Path
from types import SimpleNamespace

import pytest

from uedcli import preview
from uedcli.cli import main as cli, dispatch
from uedcli.cli import resources
from uedcli.builders import cube, make_brush_actor, sheet
from uedcli.model import Actor, Brush, Polygon
from uedcli.preview import (
    BACK, BG, DEFAULT_ANNOTATIONS, DEFAULT_GREY, FRONT, _CSG_PALETTE, _FRAME_PAD, AnnotationSpec,
    FaceData, PointRender, PreviewAbort, PreviewData, TextureData, _decal_opacity, _fade, _framing,
    _occluder_count, _scene_geometry, assign_tints, render_brushes_pgm,
)
from uedcli.tests.conftest import StubClassIndex

FIXTURES = Path(__file__).parent / "fixtures"

ADD_F, ADD_B = _CSG_PALETTE["add"]
SUB_F, SUB_B = _CSG_PALETTE["subtract"]
MOVER_F = _CSG_PALETTE["mover"][0]
SEMI_F = _CSG_PALETTE["semisolid"][0]
NON_F = _CSG_PALETTE["nonsolid"][0]

# `level_small.t3d` is a real 13-brush editor export (adds, subtracts, a rotated brush, fractional
# vertices) plus two point actors — so one scene covers the CSG palette, the legend's `+N MORE` tail,
# on-face decals and the point layer. Its LevelInfo0 carries no Location and so sits at the world
# origin, thousands of units from the geometry; the explicit `--frame` AABB (the brushes' own extent)
# keeps the framing on the brushes instead of collapsing them to a corner.
GOLDEN_SCENE = FIXTURES / "level_small.t3d"
GOLDEN_REGION = "5184,4896,-2688,7713,7169,-1728"
GOLDEN_ISO = FIXTURES / "preview_wire_golden_iso.png"
GOLDEN_QUAD = FIXTURES / "preview_wire_golden_quad.png"
GOLDEN_FLAT = FIXTURES / "preview_flat_golden_iso.png"


def _preview_args(out, **kw):
    """A `actor preview --from-t3d` arg namespace. `brush_colors=None` is what a run with no
    `--brush-colors` flag now parses to, and `faces` is left ABSENT unless a test sets it."""
    base = dict(cmd="actor", sub="preview", project=None, names=[], from_t3d=None,
                view="iso", layout="single", annotate=DEFAULT_ANNOTATIONS, iso_angle=30.0,
                frame=None, frame_tightness=0.8, highlight=None, focus=None, show="", size=256,
                out=str(out), brush_colors=None)
    base.update(kw)
    return SimpleNamespace(**base)


def _rgb(path) -> bytes:
    from PIL import Image
    with Image.open(path) as im:
        return im.convert("RGB").tobytes()


@pytest.mark.parametrize("layout,golden", [("single", GOLDEN_ISO), ("quad", GOLDEN_QUAD)])
@pytest.mark.parametrize("faces", [None, "wire"])
def test_wire_golden_is_byte_identical(tmp_path, layout, golden, faces):
    """`--faces wire` — and no `--faces` at all — render EXACTLY the pre-`--faces` wireframe. This is
    the whole feature's primary regression guard: the golden predates the rasterizer, so a fill,
    depth-test or cull leaking into `wire` fails here."""
    out = tmp_path / "g.png"
    kw = {} if faces is None else {"faces": faces}
    assert dispatch.dispatch(_preview_args(out, layout=layout, from_t3d=[str(GOLDEN_SCENE)],
                                           frame=GOLDEN_REGION, **kw)) == 0
    got = _rgb(out)
    if os.environ.get("UEDCLI_BLESS_GOLDEN"):
        from PIL import Image
        Image.open(out).convert("RGB").save(golden)
        pytest.skip(f"golden blessed → {golden}")
    assert golden.is_file(), f"golden fixture missing: {golden}"
    want = _rgb(golden)
    if got != want:
        diff = sum(1 for a, b in zip(got, want) if a != b) + abs(len(got) - len(want))
        pytest.fail(f"--faces wire ({layout}) diverged from the pre-slice golden: {diff} bytes")


def test_flat_golden_over_real_editor_content(tmp_path):
    """`--faces flat` over the SAME real 13-brush editor export the `wire` goldens come from.

    Its value is what it contains: **three MIRRORED brushes** — `Brush2` (`MainScale.X=-1`, a subtract)
    and `Brush8`/`Brush10` (`Scale.Y=-1`, adds). While `flat` refused a mirror, this scene refused
    outright, so nothing in the suite rendered a filled view over real editor content at all — no
    fractional vertices, no rotated brush, no authored `PolyFlags`, thirteen brushes overlapping. Bless
    with `UEDCLI_BLESS_GOLDEN=1 bin/test -k flat_golden`, and only after looking at the image.

    **Re-blessed three times, all three about ONE question: when does a face draw its outline?** Read as
    an arc, not a stack — each round corrected the previous one's overshoot, and the answer converged on
    "wherever the face is visible".

    1. **Outlines became unconditional** (spec §4.6's front-facing condition dropped, owner ruling).
       **55 of 65,536 px, 0.084 %** — each a boundary pixel where an ADD brush's newly-drawn back-face
       edge extended its silhouette one pixel over the subtracted room behind it, in the add's own blue.
       Too FEW outlines before: an away-facing single-sided sheet had none at all.
    2. **Narrowed to VISIBLE faces** — a solid brush is opaque (owner ruling). **208 px, 0.317 %**, with
       **0 px to or from background**, so no silhouette moved: what vanished is interior line art that was
       lying over another brush's fill. Too MANY outlines before: a brush sealed inside a solid showed its
       whole wireframe through it.
    3. **"Not visible" separated from "hidden by DEPTH".** **1 px, 0.002 %**, again 0 to or from
       background. Round 2's one condition treated three things alike — occluded, edge-on, and covering no
       pixel centre — so a face nothing was in front of lost its outline along with its fill. It is now two
       independent tests (`plane is not None` and `_face_is_occluded`'s `covered` result), each pinned on
       its own. One face in this scene is such a sliver, and its outline is back.

    Net across all three, the rule is: an outline draws iff its face is not hidden by depth — never a
    facing test (round 1 deleted that), and never a coverage test (round 3 separated that out)."""
    out = tmp_path / "flat.png"
    assert dispatch.dispatch(_preview_args(out, layout="single", from_t3d=[str(GOLDEN_SCENE)],
                                           frame=GOLDEN_REGION, faces="flat")) == 0
    got = _rgb(out)
    if os.environ.get("UEDCLI_BLESS_GOLDEN"):
        from PIL import Image
        Image.open(out).convert("RGB").save(GOLDEN_FLAT)
        pytest.skip(f"golden blessed → {GOLDEN_FLAT}")
    assert GOLDEN_FLAT.is_file(), f"golden fixture missing: {GOLDEN_FLAT}"
    want = _rgb(GOLDEN_FLAT)
    if got != want:
        diff = sum(1 for a, b in zip(got, want) if a != b) + abs(len(got) - len(want))
        pytest.fail(f"--faces flat diverged from its golden: {diff} bytes")


# ── scene helpers ─────────────────────────────────────────────────────────────────────────────
# Every renderer-level test below drives `render_brushes_pgm` directly with a hand-built
# `PreviewData`, so the CULL and the RASTERIZER are asserted without a project, a games config or a
# class index. The dispatch-level section further down covers what dispatch resolves.

def _flat(movers=()) -> PreviewData:
    """The seam a `flat` render needs: no points, and the mover set dispatch would have resolved."""
    return PreviewData(faces=FaceData(movers=frozenset(movers)))


def _room(name="Room", size=512.0, height=256.0):
    return make_brush_actor(name, cube(size, size, height), csg="subtract")


def _box(name, size=128.0, height=128.0, at=(0.0, 0.0, 0.0), csg="add", poly_flags=0):
    return make_brush_actor(name, cube(size, size, height), location=at, csg=csg,
                            poly_flags=poly_flags)


def _body(ppm):
    i = 0
    for _ in range(3):
        i = ppm.index(b"\n", i) + 1
    return ppm[i:]


def _pixels(ppm):
    b = _body(ppm)
    return [tuple(b[k:k + 3]) for k in range(0, len(b), 3)]


def _colors(ppm):
    return set(_pixels(ppm))


def _count_nonbg(ppm, size) -> int:
    return sum(1 for px in _pixels(ppm) if px != (BG, BG, BG))


def _count(ppm, rgb) -> int:
    return _pixels(ppm).count(tuple(rgb))


def _at(ppm, size, x, y):
    b = _body(ppm)
    i = (y * size + x) * 3
    return (b[i], b[i + 1], b[i + 2])


def _geom(actors, *, faces="flat", view="iso", color_by_csg=True, brush_colors="csg",
          highlight_polys=(), annotations=None, movers=(), focus=None):
    """`_SceneGeom` for these actors — the seam the cull, the edge rule, the colour roles and the
    `--focus` pass split are all decided at, so a claim about WHICH faces survive is asserted there
    rather than inferred from pixels."""
    data = _flat(movers) if faces != "wire" else PreviewData()
    return _scene_geometry(actors, view=view, iso_angle=30.0,
                           annotations=annotations or AnnotationSpec.none(),
                           highlight_polys=set(highlight_polys),
                           focus_cf=focus.casefold() if focus else None,
                           hybrid=color_by_csg, tints=assign_tints(actors),
                           color_by_csg=color_by_csg, render_data=data, brush_colors=brush_colors,
                           faces=faces)


def _legacy_to_px(actors, size, view="top", iso_angle=30.0, faces="flat"):
    """The world→pixel map a `color_by_csg=False` render of these actors uses, so a test can probe an
    exact world point. That path draws no legend, so `inset_top` is 0 and the framing is reproducible
    from `_scene_geometry`'s own `pts` — the same input the renderer frames from."""
    geom = _scene_geometry(actors, view=view, iso_angle=iso_angle, annotations=AnnotationSpec.none(),
                           highlight_polys=set(), focus_cf=None, hybrid=False, tints={},
                           color_by_csg=False, render_data=_flat(), faces=faces)
    _scale, to_px, _to_pxf, _w = _framing(geom.pts, None, size, view, iso_angle, 0, pad=_FRAME_PAD)
    return lambda p3: to_px(preview._project(p3, view, iso_angle))


# ── the flag surface ──────────────────────────────────────────────────────────────────────────

@pytest.mark.parametrize("argv", [
    ["actor", "preview", "A"],
    ["stash", "preview", "someid"],
    ["prefab", "preview", "somename"],
])
def test_faces_parses_on_all_three_preview_verbs(argv):
    """One flag, added once to the shared `_preview_opts`, so all three preview verbs carry it."""
    p = cli.build_parser()
    assert p.parse_args(argv).faces == "wire"                      # default
    assert p.parse_args(argv + ["--faces", "flat"]).faces == "flat"
    assert p.parse_args(argv + ["--faces", "textured"]).faces == "textured"


def test_an_unknown_faces_value_is_a_clean_exit_2_naming_it(capsys):
    """The three choices are `wire`/`flat`/`textured`; anything else is argparse's own choice error,
    exit 2 naming the bad value — no bespoke refusal branch."""
    with pytest.raises(SystemExit) as e:
        cli.build_parser().parse_args(["actor", "preview", "A", "--faces", "shaded"])
    assert e.value.code == 2
    assert "shaded" in capsys.readouterr().err


def test_faces_help_describes_textured():
    """`-h` and the docs must agree the moment `textured` is a choice."""
    actions = {a.dest: (a.help or "") for a in cli.build_parser()._subparsers._group_actions[0]
               .choices["actor"]._subparsers._group_actions[0].choices["preview"]._actions}
    assert "textured" in actions["faces"] and "UV frame" in actions["faces"]


def test_corrected_help_strings_say_what_the_flags_now_do():
    """`--brush-colors` also colours fills, `--focus` fades fills and not just lines, and `--show`'s
    schema-free promise is scoped to `wire` — help that still said "the wireframe" would be false the
    moment `flat` shipped.

    **`--layout` is checked too because it was MISSED.** This test covered four flags, so `--layout`'s
    help went on announcing a refusal of `--faces flat` that had been deleted. `-h` describing a refusal
    that no longer exists is the failure mode, so the last loop asserts no `--faces`-sensitive flag still
    claims one."""
    actions = {a.dest: (a.help or "") for a in cli.build_parser()._subparsers._group_actions[0]
               .choices["actor"]._subparsers._group_actions[0].choices["preview"]._actions}
    assert "flat" in actions["brush_colors"] and "fill" in actions["brush_colors"]
    assert "--faces flat" in actions["focus"] and "fills" in actions["focus"]
    assert "--faces wire" in actions["show"] and "schema-free" in actions["show"]
    assert "class hierarchy" in actions["faces"]
    assert "--focus" in actions["layout"] and "breakdown" in actions["layout"]
    for dest in ("faces", "focus", "layout", "brush_colors"):
        assert "refus" not in actions[dest], f"--{dest} help still claims a refusal that was removed"
    # No help string may promise the x-ray the owner deleted: an outline that "draws over everything" or
    # reads "even where" something hides it. `--focus`'s help carried exactly that for a whole round, and
    # this test could not see it because it only looked for `refus`.
    for dest in ("focus", "highlight", "faces"):
        for stale in ("draws over everything", "even where"):
            assert stale not in actions[dest], f"--{dest} help still promises the deleted x-ray outline"
    assert "x-ray" in actions["focus"] or "not visible" in actions["focus"] 


# ── the subtract cull, and what escapes it ────────────────────────────────────────────────────

def test_flat_fills_every_face_of_a_non_subtract_brush():
    """Nothing but a subtract is back-face culled, so an add brush contributes ALL six faces and the depth
    buffer decides what shows. Asserted at the `fills` list, because a pixel count cannot tell "the back
    face was culled" from "the back face lost the depth test"."""
    box = _box("Add")
    geom = _geom([box], faces="flat")
    assert len(geom.fills) == len(box.brush.polys) == 6
    assert {rgb for _v3, _vs, rgb, _d in geom.fills} == {ADD_F, ADD_B}      # three of each facing
    ppm = render_brushes_pgm([box], view="iso", size=96, annotations=AnnotationSpec.none(),
                             color_by_csg=True, render_data=_flat(), faces="flat")
    # The FRONT hue is the fill; the BACK hue survives only as the outline pass, so it must be
    # perimeter-sized, not area-sized — a back face leaking through the depth test would be thousands.
    assert _count(ppm, ADD_F) > 500
    assert 0 < _count(ppm, ADD_B) < _count(ppm, ADD_F) / 4


def test_flat_draws_a_subtracts_far_faces_and_culls_its_camera_facing_ones():
    """A subtract's polys seen from OUTSIDE the carved volume render neither in UnrealEd nor in game, so
    the camera-facing set is culled and only the far/interior surfaces draw — which is what makes a
    subtracted room show its INSIDE instead of the outside of a solid box."""
    room = _room()
    geom = _geom([room], faces="flat")
    assert len(geom.fills) == 3 and len(room.brush.polys) == 6          # exactly half, the far half
    assert {rgb for _v3, _vs, rgb, _d in geom.fills} == {SUB_B}             # only the BACK member is left
    flat = render_brushes_pgm([room], view="iso", size=96, annotations=AnnotationSpec.none(),
                              color_by_csg=True, render_data=_flat(), faces="flat")
    assert _count(flat, SUB_B) > 500                                     # the far (interior) faces
    assert _count(flat, SUB_F) < _count(flat, SUB_B) / 4                 # outlines only, never a fill
    wire = render_brushes_pgm([room], view="iso", size=96, annotations=AnnotationSpec.none(),
                              color_by_csg=True, render_data=PreviewData(), faces="wire")
    assert _count(wire, SUB_F) > 0            # `wire` still draws them — it culls nothing


def test_flat_shows_an_add_brush_inside_a_subtracted_room():
    """The point of the cull: without it the room's near walls would fill over everything inside it."""
    ppm = render_brushes_pgm([_room(), _box("Crate", 128.0, 128.0)], view="iso", size=96,
                             annotations=AnnotationSpec.none(), color_by_csg=True,
                             render_data=_flat(), faces="flat")
    assert _count(ppm, ADD_F) > 100


def test_a_mover_carrying_csg_subtract_is_not_culled_and_fills_in_mover_colour():
    """The case BOTH index-free rules get wrong. A `CEDoor` is a real Mover whose class name does not
    end in `Mover`, so `classify_brush`'s name guess calls it a subtraction; the raw `CsgOper` marker
    agrees. A mover is never carved into the world, so it must show every face — and in mover magenta,
    because one render may not use two different mover answers."""
    door = _room("Door", 256.0, 256.0)                       # CsgOper=CSG_Subtract
    door.cls = "CaroneElevatorSet.CEDoor"
    ppm = render_brushes_pgm([door], view="iso", size=96, annotations=AnnotationSpec.none(),
                             color_by_csg=True, render_data=_flat(movers=["Door"]), faces="flat")
    assert _count(ppm, MOVER_F) > 500                        # camera-facing faces, mover hue
    assert _count(ppm, SUB_B) == 0 and _count(ppm, SUB_F) == 0
    naive = render_brushes_pgm([door], view="iso", size=96, annotations=AnnotationSpec.none(),
                               color_by_csg=True, render_data=_flat(), faces="flat")
    assert _count(naive, MOVER_F) == 0                       # the same brush, culled, when NOT a mover


def test_the_mover_answer_also_drives_is_solid_and_so_the_occluders_set():
    """`is_solid` feeds `occluders`, which grades every decal's opacity, so leaving it on the name guess
    would satisfy a narrow reading of "use the real predicate" and still mis-grade the picture."""
    door = _room("Door", 256.0, 256.0)
    door.cls = "CaroneElevatorSet.CEDoor"
    kw = dict(view="iso", iso_angle=30.0, annotations=AnnotationSpec.none(), highlight_polys=set(),
              focus_cf=None, hybrid=False, tints={}, color_by_csg=False, faces="flat")
    as_mover = _scene_geometry([door], render_data=_flat(movers=["Door"]), **kw)
    assert {o[3] for o in as_mover.occluders} == {True}       # mover ⇒ solid ⇒ occludes across brushes


def test_a_nonsolid_sheet_renders_from_both_sides():
    """The cull is subtract-only, so a single-face `nonsolid` sheet must fill whichever way it faces —
    the from-behind case "fills every face of a non-subtract brush" does not pin."""
    front = make_brush_actor("S", sheet(256.0, 256.0, plane="xy"), csg="add", poly_flags=preview.PF_NOTSOLID)
    back = make_brush_actor("S", sheet(256.0, 256.0, plane="xy"), csg="add", poly_flags=preview.PF_NOTSOLID)
    for p in back.brush.polys:
        p.vertices = list(reversed(p.vertices))              # the same sheet, wound the other way
    kw = dict(view="top", size=96, annotations=AnnotationSpec.none(), color_by_csg=True,
              render_data=_flat(), faces="flat")
    assert _count(render_brushes_pgm([front], **kw), NON_F) > 500
    assert _count(render_brushes_pgm([back], **kw), _CSG_PALETTE["nonsolid"][1]) > 500


# ── the edge rule, and the decal grading it changes ───────────────────────────────────────────

def test_every_surviving_face_EMITS_its_edges():
    """Every face that survives the cull EMITS an edge pair — no facing test (owner ruling, superseding
    spec §4.6's front-facing condition, which left an away-facing single-sided sheet unoutlined).

    **Emission is not drawing.** A later ruling narrowed what actually PAINTS to faces depth left visible,
    so a face emitted here may still be dropped by `render_brushes_pgm` — that is
    `test_a_solid_brush_is_OPAQUE_in_both_the_fill_and_the_edge_pass`. This test is deliberately at the
    `_scene_geometry` seam, where the rule really is unconditional; do not read it as a claim about pixels."""
    kw = dict(view="iso", iso_angle=30.0, annotations=AnnotationSpec.none(), highlight_polys=set(),
              focus_cf=None, hybrid=False, tints={}, color_by_csg=True, brush_colors="csg")
    add = _scene_geometry([_box("Add")], render_data=_flat(), faces="flat", **kw)
    assert {e[0] for e in add.edges} == {True, False}         # every one of the six faces, not three
    assert len(add.edges) == 6 * 4
    sub = _scene_geometry([_room()], render_data=_flat(), faces="flat", **kw)
    assert {e[0] for e in sub.edges} == {False}               # only the far faces SURVIVED to draw
    assert len(sub.edges) == 3 * 4
    wire = _scene_geometry([_room()], render_data=PreviewData(), faces="wire", **kw)
    assert {e[0] for e in wire.edges} == {True, False}        # `wire` emits an edge for every face


def test_two_away_facing_sheets_get_outlines_and_a_boundary():
    """The case a front-facing edge condition could not cover, and the reason the ruling drops it. Two
    abutting single-sided `nonsolid` sheets wound AWAY from the camera have no front face anywhere, so a
    facing test gave them a fill and no line art at all: one undifferentiated 17,672-px block of
    `nonsolid` back-green, **zero** edge pixels, and no boundary between the two brushes — verbatim the
    symptom the edge ruling exists to eliminate."""
    def away(name, at):
        a = make_brush_actor(name, sheet(256.0, 256.0, plane="xy"), location=at, csg="add",
                             poly_flags=preview.PF_NOTSOLID)
        for poly in a.brush.polys:
            poly.vertices = list(reversed(poly.vertices))     # wound to face away from the camera
        return a
    ppm = render_brushes_pgm([away("S1", (0.0, 0.0, 0.0)), away("S2", (256.0, 0.0, 0.0))],
                             view="top", size=200, annotations=AnnotationSpec.none(),
                             color_by_csg=True, render_data=_flat(), faces="flat")
    fill, edge = _CSG_PALETTE["nonsolid"][1], NON_F        # back-facing ⇒ fill BACK, outline its partner
    assert _count(ppm, fill) > 15000                        # still filled, as before
    assert _count(ppm, edge) > 200, "an away-facing single-sided face must still be outlined"
    # ...and the two brushes are separated: a vertical run of edge pixels sits at the shared boundary.
    at = _legacy_to_px([away("S1", (0.0, 0.0, 0.0)), away("S2", (256.0, 0.0, 0.0))], 200)
    bx, by = at((128.0, 0.0, 0.0))                          # the abutting edge, mid-height
    assert any(_at(ppm, 200, bx + dx, by) == edge for dx in (-2, -1, 0, 1, 2))


def test_a_closed_brush_gains_no_visible_interior_from_the_new_edge_rule():
    """A closed brush never shows its hidden interior, and TWO separate rules now guarantee that — which is
    why the property is pinned even though it looks obvious.

    Historically it held only by COLOUR: a back face's edge was drawn, but in the same member the front-face
    fill covering it already used, so it was invisible. Since edges of depth-hidden faces are not drawn at
    all, those edges no longer reach the canvas in the first place. The visible result is the same, and a
    cube stays byte-identical to the pre-ruling render — but a reader must not conclude from this test that
    hidden edges are still being painted-and-camouflaged, because they are not."""
    box = _box("Add")
    geom = _scene_geometry([box], view="iso", iso_angle=30.0, annotations=AnnotationSpec.none(),
                           highlight_polys=set(), focus_cf=None, hybrid=False, tints={},
                           color_by_csg=True, render_data=_flat(), faces="flat")
    drawn = {tuple(sorted(e[1])) for e in geom.edges}
    assert len(drawn) == 12                                  # all twelve, incl. the hidden far corner
    ppm = render_brushes_pgm([box], view="iso", size=200, annotations=AnnotationSpec.none(),
                             color_by_csg=True, render_data=_flat(), faces="flat")
    # The far-corner edges land inside the front faces' fill, in that fill's own colour, so the render
    # carries exactly the two hues it did before: fill ADD_F, outline ADD_B. No third, no interior lines.
    assert _colors(ppm) == {(BG, BG, BG), ADD_F, ADD_B}


def test_a_culled_face_draws_no_edge_no_highlight_and_no_decal():
    """The cull removes the face ENTIRELY, not merely its fill."""
    room = _room()
    hi = {(room.name, i) for i in range(len(room.brush.polys))}
    kw = dict(view="iso", iso_angle=30.0, annotations=AnnotationSpec.all(), focus_cf=None,
              hybrid=True, tints=assign_tints([room]), color_by_csg=True, brush_colors="csg")
    wire = _scene_geometry([room], highlight_polys=hi, render_data=PreviewData(), faces="wire", **kw)
    flat = _scene_geometry([room], highlight_polys=hi, render_data=_flat(), faces="flat", **kw)
    assert len(wire.poly_labels) == 6                          # every face of the cube is numbered
    assert len(flat.poly_labels) == 3                           # its 3 camera-facing ones are gone
    assert len(flat.hi_edges) * 2 == len(wire.hi_edges)       # half the faces, so half the outlines
    assert flat.occluders == []                               # every front face of a subtract is gone


def test_flats_decal_opacity_differs_from_wires_where_the_cull_emptied_occluders():
    """The sole OBSERVABLE of "a culled face is excluded from `occluders`". `wire` culls nothing, so a
    room's near walls dim its own far walls (the self-or-solid rule's same-brush arm); under `flat` those
    near walls draw nothing, and a face that draws nothing must not dim a decal on a face that does — so
    the far walls' numbers come up brighter. That difference is intended, and this is its pin."""
    room = _room()
    kw = dict(view="iso", iso_angle=30.0, annotations=AnnotationSpec.all(), highlight_polys=set(),
              focus_cf=None, hybrid=True, tints=assign_tints([room]), color_by_csg=True,
              brush_colors="csg")
    wire = _scene_geometry([room], render_data=PreviewData(), faces="wire", **kw)
    flat = _scene_geometry([room], render_data=_flat(), faces="flat", **kw)
    deepest = max(_occluder_count(c, d, wire.occluders, own_brush=b) for c, _t, _a, d, _v, b in
                  wire.poly_labels)
    assert deepest > 0
    assert all(_occluder_count(c, d, flat.occluders, own_brush=b) == 0
               for c, _t, _a, d, _v, b in flat.poly_labels)
    assert _decal_opacity(deepest) < _decal_opacity(0)


# ── the rasterizer ────────────────────────────────────────────────────────────────────────────

def _u_shape(name="Ell"):
    """A single CONCAVE face (a U in the XY plane, wound CCW seen from +Z), whose notch a triangle-fan
    rasterizer fills and an even-odd scanline one does not. The ring starts at a vertex the notch is NOT
    visible from, which is what makes a fan bleed."""
    ring = [(0, 0), (300, 0), (300, 300), (200, 300), (200, 100), (100, 100), (100, 300), (0, 300)]
    poly = Polygon(vertices=[(Decimal(x), Decimal(y), Decimal(0)) for x, y in ring])
    return Actor(name=name, cls="Engine.Brush", brush=Brush(model_name="M", polys=[poly]),
                 location=(Decimal(0), Decimal(0), Decimal(0)))


def test_a_concave_face_fills_only_inside_its_boundary():
    """Even-odd scanline, not a triangle fan: 0.1-0.6 % of faces in real exported maps are concave and a
    fan fills OUTSIDE those. The U's notch is 2/9 of its bounding box, so a fan is measurably wrong."""
    size = 128
    actors = [_u_shape()]
    ppm = render_brushes_pgm(actors, view="top", size=size, annotations=AnnotationSpec.none(),
                             color_by_csg=False, render_data=_flat(), faces="flat")
    to_px = _legacy_to_px(actors, size)
    assert _at(ppm, size, *to_px((150.0, 200.0, 0.0))) == (BG, BG, BG)      # inside the notch
    for inside in ((50.0, 200.0, 0.0), (250.0, 200.0, 0.0), (150.0, 50.0, 0.0)):
        assert _at(ppm, size, *to_px(inside)) == FRONT
    filled = _count(ppm, FRONT)
    box_px = (size - 2 * _FRAME_PAD) ** 2
    assert 0.70 < filled / box_px < 0.82                      # the U is 7/9 of its box; a fan is 9/9


def test_two_overlapping_brushes_the_nearer_face_wins_per_pixel():
    """Depth is `dot(P, view direction)`, smaller = nearer, affine under an orthographic camera."""
    low = _box("Low", 256.0, 64.0, at=(0.0, 0.0, 0.0), poly_flags=preview.PF_SEMISOLID)
    high = _box("High", 128.0, 64.0, at=(0.0, 0.0, 256.0), poly_flags=preview.PF_NOTSOLID)
    ppm = render_brushes_pgm([low, high], view="top", size=96, annotations=AnnotationSpec.none(),
                             color_by_csg=True, render_data=_flat(), faces="flat")
    size, to_px = 96, _legacy_to_px([low, high], 96)
    assert _at(ppm, size, *to_px((0.0, 0.0, 256.0))) == NON_F      # the higher cube is nearer in TOP
    assert _at(ppm, size, *to_px((110.0, 0.0, 0.0))) == SEMI_F     # beyond it, the lower one shows


@pytest.mark.parametrize("focus", [None, "A", "B"])
def test_a_coplanar_tie_goes_to_scene_order_whatever_is_focused(focus):
    """The depth test is strictly `<`, so the FIRST face drawn wins and iteration is scene order. No
    epsilon bias: a flush add/subtract pair is common pre-CSG, and a bias would only relocate the
    arbitrariness.

    **Parametrized over `--focus` because that is how S3 broke it.** `--focus` may change brightness and
    nothing else, but resolving the de-emphasised faces in a pass of their own rasterized them FIRST, so
    the tie went to whichever pass a face was in — focusing a brush made its own flush surface disappear
    and the other brush's show through at context brightness. The winner below must be the same actor in
    all three cases; only its brightness may differ."""
    a = _box("A", 256.0, 64.0, poly_flags=preview.PF_SEMISOLID)
    b = _box("B", 256.0, 64.0, poly_flags=preview.PF_NOTSOLID)
    kw = dict(view="top", size=96, annotations=AnnotationSpec.none(), color_by_csg=True,
              render_data=_flat(), faces="flat", focus=focus)
    at = _legacy_to_px([a, b], 96)((0.0, 0.0, 32.0))
    # `A` first ⇒ `A` wins, full strength unless A is the one de-emphasised; never `B` at any brightness.
    assert _at(render_brushes_pgm([a, b], **kw), 96, *at) == (_dim(SEMI_F) if focus == "B" else SEMI_F)
    assert _at(render_brushes_pgm([b, a], **kw), 96, *at) == (_dim(NON_F) if focus == "A" else NON_F)


def test_focus_never_changes_which_flush_surface_is_visible_through_the_cli(tmp_path, capsys):
    """The structural defect, end to end: a subtracted room `z∈[-128,128]` with an added slab whose top cap
    is flush at `z=-128`. Focusing the ROOM used to lose the room's own floor and show the slab instead, at
    context brightness — `--focus` deciding what is visible, the one thing it may never do. `--layout
    breakdown` made it the common case, since it focuses every brush pane in turn."""
    room = make_brush_actor("CopRoom", cube(1024.0, 1024.0, 256.0), csg="subtract")
    slab = make_brush_actor("CopSlab", cube(1024.0, 1024.0, 128.0), location=(0.0, 0.0, -192.0),
                            csg="add")
    seen = {}
    for focus in (None, "CopRoom", "CopSlab"):
        out = tmp_path / f"{focus}.png"
        assert dispatch.dispatch(_preview_args(out, from_t3d=[_snippet(tmp_path, [room, slab])],
                                               view="top", size=200, faces="flat", focus=focus,
                                               annotate="none")) == 0
        capsys.readouterr()
        px = _rgb(out)
        i = ((200 // 2) * 200 + 200 // 2) * 3
        seen[focus] = tuple(px[i:i + 3])
    # The room is first in scene order, so its floor wins every time — dimmed only when the slab is focused.
    assert seen[None] == SUB_B
    assert seen["CopRoom"] == SUB_B, f"focusing the room lost its own floor: got {seen['CopRoom']}"
    assert seen["CopSlab"] == _dim(SUB_B)


def test_pf_invisible_faces_neither_fill_nor_write_depth_nor_draw_line_art():
    """The flag is read ACTOR-OR'd, as the engine reads it: a brush authored `PolyFlags=1` is invisible
    even though its polys carry no flag. "Writes no depth" is the half a fill test alone would miss — a
    face behind an invisible one must show through."""
    ghost = _box("Ghost", 256.0, 64.0, at=(0.0, 0.0, 256.0), poly_flags=preview.PF_INVISIBLE)
    solid = _box("Solid", 128.0, 64.0, at=(0.0, 0.0, 0.0), poly_flags=preview.PF_SEMISOLID)
    kw = dict(view="top", size=96, annotations=AnnotationSpec.none(), color_by_csg=True,
              render_data=_flat(), faces="flat")
    alone = render_brushes_pgm([ghost], **kw)
    assert _colors(alone) == {(BG, BG, BG)}                   # no fill and no line art at all
    both = render_brushes_pgm([ghost, solid], **kw)
    at = _legacy_to_px([ghost, solid], 96)((0.0, 0.0, 0.0))
    assert _at(both, 96, *at) == SEMI_F                       # the nearer ghost wrote no depth


def test_the_depth_buffer_is_a_float_array_and_an_absurd_size_refuses_cleanly():
    """`--size` is uncapped, so a `list[float]` depth buffer would be ~0.5 GB at `--size 4096` against
    ~67 MB for `array("f")`. An allocation that genuinely fails is a clean refusal naming the size."""
    _buf, zbuf = preview._alloc_buffers(8, depth=True)
    assert zbuf.typecode == "f" and len(zbuf) == 64 and zbuf[0] == float("inf")
    assert preview._alloc_buffers(8, depth=False)[1] is None
    # Three magnitudes, because the allocation raises a DIFFERENT exception at each and only the first
    # is a `MemoryError`: past `3·size² > sys.maxsize` it is an `OverflowError` ("repeated bytes are too
    # long"), and further out a different `OverflowError` ("cannot fit 'int' into an index-sized
    # integer"). `1 << 30` alone — the size this test used to check — is the one that lands on
    # `MemoryError`, so it passed while the two larger ones tracebacked.
    for size in (1 << 30, 2_000_000_000, 5_000_000_000):
        with pytest.raises(PreviewAbort) as e:
            preview._alloc_buffers(size, depth=True)
        assert str(size) in str(e.value)


# ── the three fill-colour cases ───────────────────────────────────────────────────────────────

def test_flat_fills_from_the_csg_palette_by_default():
    ppm = render_brushes_pgm([_box("Add")], view="iso", size=96, annotations=AnnotationSpec.none(),
                             color_by_csg=True, render_data=_flat(), faces="flat")
    assert _count(ppm, ADD_F) > 500


def test_flat_fills_from_the_per_actor_tint_under_brush_colors_legend():
    box = _box("Add")
    tint = assign_tints([box])["Add"]
    ppm = render_brushes_pgm([box], view="iso", size=96, annotations=AnnotationSpec.none(),
                             color_by_csg=True, render_data=_flat(), faces="flat",
                             brush_colors="legend")
    assert _count(ppm, tint) > 500 and _count(ppm, ADD_F) == 0
    assert _fade(tint) != tint                                # the back member of the legend pair


def test_flat_fills_black_grey_on_the_legacy_color_by_csg_path():
    """`render_brushes_pgm`'s own default, which the existing suite drives constantly — the third of the
    three colour cases, and the one no CLI flag reaches. Its pair is `(FRONT, BACK)` = black/grey, so the
    same fill/edge role split applies: an add fills black and outlines grey, a subtract the reverse."""
    add = _geom([_box("Add")], faces="flat", color_by_csg=False)
    assert {rgb for _v, _s, rgb, _d in add.fills} == {FRONT, BACK}
    ppm = render_brushes_pgm([_box("Add")], view="iso", size=96, annotations=AnnotationSpec.none(),
                             color_by_csg=False, render_data=_flat(), faces="flat")
    assert _count(ppm, FRONT) > 500 and 0 < _count(ppm, BACK) < _count(ppm, FRONT) / 4
    sub = render_brushes_pgm([_room()], view="iso", size=96, annotations=AnnotationSpec.none(),
                             color_by_csg=False, render_data=_flat(), faces="flat")
    assert _count(sub, BACK) > 500 and 0 < _count(sub, FRONT) < _count(sub, BACK) / 4


# ── the point layer survives an opaque fill ───────────────────────────────────────────────────

def test_point_sprites_and_every_show_overlay_survive_an_opaque_fill():
    """Fills are brush geometry and draw at step 2, AHEAD of the point layer. Drawn later they would
    paint over every sprite and every `--show` overlay."""
    rgb, mask = bytes([255, 0, 255] * 4), bytes([1] * 4)
    pr = PointRender(label="P", sprite=(2, 2, rgb, mask), sprite_world=(64.0, 64.0),
                     collision=(48.0, 48.0), light_radius=120.0, sound_radius=160.0)
    light = Actor(name="P", cls="Engine.Light", location=(Decimal(0), Decimal(0), Decimal(0)))
    data = PreviewData(points={"P": pr}, faces=FaceData(movers=frozenset()))
    ppm = render_brushes_pgm([_room(), light], view="top", size=192,
                             annotations=AnnotationSpec.none(), color_by_csg=True,
                             render_data=data, faces="flat")
    got = _colors(ppm)
    assert (255, 0, 255) in got                               # the sprite, over the room's fill
    for overlay in (preview.COL_COLLISION, preview.COL_LIGHT, preview.COL_SOUND):
        assert overlay in got


# ── what dispatch resolves, and what it refuses ────────────────────────────────────────────────
# These drive the real CLI path: `dispatch.dispatch` over a `--from-t3d` snippet, so exit codes and
# messages are the ones a user sees. `conftest` autouse-stubs `resources.mover_index` with a
# `StubClassIndex`, which models all four ways the real index fails to answer.

def _snippet(tmp_path, actors, name="scene.t3d") -> str:
    from uedcli.emit import emit_map
    path = tmp_path / name
    path.write_text(emit_map(actors), encoding="latin1")
    return str(path)


def _run(tmp_path, actors, **kw) -> int:
    return dispatch.dispatch(_preview_args(tmp_path / "o.png", from_t3d=[_snippet(tmp_path, actors)],
                                           **kw))


def test_flat_renders_through_the_cli_over_from_t3d(tmp_path):
    assert _run(tmp_path, [_room(), _box("Crate")], faces="flat") == 0
    assert (tmp_path / "o.png").is_file()


@pytest.mark.parametrize("layout", ["single", "quad", "breakdown"])
@pytest.mark.parametrize("focus", [None, "Crate"])
def test_every_layout_renders_under_flat_with_and_without_focus(tmp_path, layout, focus, capsys):
    """`breakdown` is here for both `focus` values because it focuses every per-brush pane BY
    CONSTRUCTION (`focus=a.name` into `_pane`, rendered at the same `--faces`) — it reaches the filled
    focus path with no `--focus` on the command line at all."""
    assert _run(tmp_path, [_room(), _box("Crate")], faces="flat", layout=layout, focus=focus,
                size=96) == 0
    capsys.readouterr()


# ── mirrored brushes RENDER, correctly (owner ruling) ──────────────────────────────────────────
# A reflection reverses every ring's handedness, so each transformed face's Newell normal comes out as
# the NEGATIVE of its true outward normal and `_is_front` answers the opposite of the truth. Filled
# modes correct that one boolean, which is what puts the cull, the three colour roles, the edge rule and
# `occluders` all right at once. `wire` is deliberately NOT corrected — it has always shipped the
# inversion and the owner did not ask for it to change (the byte-identity golden also depends on that).

def _mirror(actor, scale, *, post=False):
    from uedcli.transform import FScale
    f = FScale(scale=tuple(Decimal(str(c)) for c in scale))
    setattr(actor, "post_scale" if post else "main_scale", f)
    return actor


def test_a_mirrored_subtract_still_shows_its_interior(tmp_path):
    """THE case that rendered wrong. Uncorrected, the cull keeps a mirrored room's NEAR faces and drops
    its far ones, so it fills as a solid box and hides everything inside it — inside-out, and silent."""
    plain, mirrored = _room("Room"), _mirror(_room("Room"), (-1, 1, 1))
    a, b = _geom([plain], faces="flat"), _geom([mirrored], faces="flat")
    assert len(a.fills) == len(b.fills) == 3               # half the faces survive either way...
    assert {rgb for _v, _s, rgb, _d in b.fills} == {SUB_B}     # ...and they are the FAR half, as for plain
    # The surviving faces are the same three PLACES in world space, mirrored — never the opposite three.
    def centroid_z(g):
        return sorted(round(sum(p[2] for p in v3) / len(v3), 3) for v3, _s, _c, _d in g.fills)
    assert centroid_z(a) == centroid_z(b)
    assert _run(tmp_path, [mirrored, _box("Crate", 128.0, 128.0)], faces="flat") == 0


def test_a_mirrored_add_keeps_its_front_hue(tmp_path):
    """A mirrored add is never culled, so the only thing the inversion cost it was the front/back hue —
    it filled in the OBSCURED shade while facing the camera."""
    got = _geom([_mirror(_box("Add"), (1, -1, 1))], faces="flat")
    fills = [rgb for _v, _s, rgb, _d in got.fills]
    assert fills.count(ADD_F) == 3 and fills.count(ADD_B) == 3
    assert _run(tmp_path, [_mirror(_box("Add"), (1, -1, 1))], faces="flat") == 0


def test_a_double_mirror_is_a_rotation_and_must_not_be_flipped():
    """`Scale=(X=-1,Y=-1)` has determinant +1 — a 180° rotation, not a reflection — so its normals are
    already correct and "has a negative component" would flip it wrongly. The discriminator is the SIGN
    OF THE DETERMINANT."""
    from uedcli.transform import det3
    from uedcli import rotation
    twice = _mirror(_room("Room"), (-1, -1, 1))
    assert det3(rotation.actor_linear(twice)) > 0
    plain = _geom([_room("Room")], faces="flat")
    got = _geom([twice], faces="flat")
    assert {rgb for _v, _s, rgb, _d in got.fills} == {SUB_B} == {rgb for _v, _s, rgb, _d in plain.fills}
    assert len(got.fills) == len(plain.fills) == 3


@pytest.mark.parametrize("scale,post,rot", [
    ((-1, 1, 1), False, None),                 # MainScale (pre-rotation)
    ((-1, 1, 1), True, None),                  # PostScale (post-rotation) — same determinant sign
    ((1, 1, -1), False, "16384"),              # a mirror combined with a 90° yaw
    ((-2, 3, 1), False, None),                 # mirrored AND non-uniformly scaled
])
def test_every_route_to_a_negative_determinant_is_corrected(scale, post, rot):
    """The determinant is the product of the scale components (a rotation contributes +1 and a sheer
    leaves it alone), so MainScale, PostScale, a rotated mirror and a mirror-plus-scale all reach the same
    predicate — and all four must land on the FAR faces of a subtract, exactly as an unmirrored one does."""
    room = _mirror(_room("Room"), scale, post=post)
    if rot:
        room.props = room.props + [("Rotation", f"(Yaw={rot})")]
    got = _geom([room], faces="flat")
    assert len(got.fills) == 3
    assert {rgb for _v, _s, rgb, _d in got.fills} == {SUB_B}


def test_a_mirrored_mover_is_not_culled_and_keeps_mover_colour():
    """A mover escapes the cull entirely, so a mirror can only cost it the hue pair — and it still must
    not be culled once the facing answer is corrected."""
    door = _mirror(_room("Door"), (-1, 1, 1))
    door.cls = "CaroneElevatorSet.CEDoor"
    got = _geom([door], faces="flat", movers=["Door"])
    assert len(got.fills) == 6                                  # nothing culled
    assert {rgb for _v, _s, rgb, _d in got.fills} == {MOVER_F, _CSG_PALETTE["mover"][1]}


def test_wire_is_deliberately_left_uncorrected_on_a_mirror(tmp_path):
    """`wire` culls nothing, so the inversion costs it only the front/back SHADE — and it has shipped that
    way from the start. Correcting it would change bytes the golden pins, and the owner ruled only on the
    filled modes, so the difference is recorded here rather than quietly fixed."""
    # ONE face, so the two modes' facing answers are directly comparable: a mirrored sheet in the XY
    # plane, viewed from TOP, genuinely faces the camera.
    sheet_actor = _mirror(make_brush_actor("S", sheet(256.0, 256.0, plane="xy"), csg="add"),
                          (-1, 1, 1))
    w = _geom([sheet_actor], faces="wire", view="top")
    f = _geom([sheet_actor], faces="flat", view="top")
    assert [e[0] for e in w.edges] == [False] * 4                # wire: uncorrected ⇒ reads as BACK
    assert [rgb for _v, _s, rgb, _d in f.fills] == [ADD_F]           # flat: corrected ⇒ fills as FRONT
    assert _run(tmp_path, [sheet_actor], faces="wire") == 0


def test_an_unscaled_brush_does_not_crash_the_mirror_predicate(tmp_path):
    """`rotation.actor_linear` returns None as its IDENTITY sentinel — the common case — so a bare
    `det(actor_linear(a)) < 0` would raise `TypeError` on nearly every brush in existence."""
    from uedcli import rotation
    assert rotation.actor_linear(_box("Plain")) is None
    assert _geom([_box("Plain")], faces="flat").fills
    assert _run(tmp_path, [_box("Plain")], faces="flat") == 0


def test_non_mirroring_scaled_and_sheared_brushes_still_render_under_flat(tmp_path):
    """`flat` reads no UV frame — its fill is the projected polygon, which `actor_linear` already builds
    correctly — so only the MIRRORED case is refused, not scale in general."""
    from uedcli.transform import FScale
    scaled = _box("Scaled")
    scaled.main_scale = FScale(scale=(Decimal(2), Decimal(3), Decimal(1)))
    sheared = _box("Sheared", at=(600.0, 0.0, 0.0))
    sheared.post_scale = FScale(scale=(Decimal(1), Decimal(1), Decimal(1)),
                                sheer_rate=Decimal("0.5"), sheer_axis="SHEER_ZX")
    assert _run(tmp_path, [scaled, sheared], faces="flat") == 0


@pytest.mark.parametrize("stub,offenders", [
    (dict(resolves=False), ["Room", "Crate"]),                    # cause 1: no Engine.Mover at all
    (dict(unknown=("Engine.Brush",)), ["Room", "Crate"]),         # cause 2: the actor's own class
    (dict(truncated=("Engine.Brush",)), ["Room", "Crate"]),       # cause 3: a truncated chain
])
def test_flat_refuses_when_mover_ness_cannot_be_resolved(tmp_path, monkeypatch, capsys, stub,
                                                         offenders):
    """`movers.is_mover` ANSWERS OR RAISES: reporting an unresolvable class as "not a mover" would render
    a real mover inside-out with nothing downstream to re-check. Every offender is named."""
    monkeypatch.setattr(resources, "mover_index",
                        lambda args, verb, project=None: StubClassIndex(**stub))
    assert _run(tmp_path, [_room(), _box("Crate")], faces="flat") == 2
    err = capsys.readouterr().err
    assert all(name in err for name in offenders)
    assert "--faces wire" in err


def test_a_bare_class_whose_candidates_disagree_names_that_cause(tmp_path, monkeypatch, capsys):
    """Cause 4: a cross-package bare-name collision where one candidate is a mover and one is not."""
    monkeypatch.setattr(resources, "mover_index", lambda args, verb, project=None: StubClassIndex(
        ambiguous={"Brush": ("Engine.Brush", "CaroneElevatorSet.CEDoor")}))
    box = _box("Ambiguous")
    box.cls = "Brush"                                            # unqualified, as MAP EXPORT writes it
    assert _run(tmp_path, [box], faces="flat") == 2
    err = capsys.readouterr().err
    assert "Ambiguous" in err and "disagree" in err


def test_wire_still_renders_when_the_class_hierarchy_cannot_load(tmp_path, capsys):
    """Decision 2.13's cost, in BOTH directions: the filled modes need the game's class hierarchy and
    refuse without it, and `wire` — the default — needs nothing and is untouched. With no per-user games
    config there is no resolver at all, which is the real seam, not the stub."""
    scene = [_room(), _box("Crate")]
    assert _run(tmp_path, scene, faces="wire") == 0
    capsys.readouterr()


@pytest.mark.real_mover_index
def test_flat_refuses_with_no_games_config_while_wire_renders(tmp_path, capsys, tmp_project):
    """The same pair against the GENUINE `_mover_index` seam (the autouse stub opted out), so the
    refusal is the one a user with no games config actually gets."""
    scene = [_room(), _box("Crate")]
    assert _run(tmp_path, scene, faces="flat", project=str(tmp_project)) == 2
    err = capsys.readouterr().err
    assert "games config" in err and "actor preview --faces flat" in err
    assert _run(tmp_path, scene, faces="wire", project=str(tmp_project)) == 0


def test_prefab_dir_inside_a_project_succeeds_under_flat(tmp_path, tmp_project):
    """`--prefab-dir` overrides only the prefab LIBRARY ROOT. It implies neither "no project" nor "no
    resolver", so it must not turn a filled render into a refusal — an inverted claim an earlier review
    round made and this pins the right way round."""
    from uedcli import stashlib
    from uedcli.normalize import canonical_actor_t3d
    lib = tmp_path / "prefabs"
    stashlib.write_prefab(lib, "Box", full_level={"Crate": canonical_actor_t3d(_box("Crate"))},
                          order=["Crate"], packages=[], meta={})
    args = _preview_args(tmp_path / "o.png", cmd="prefab", sub="preview", name="Box",
                         prefab_dir=str(lib), project=str(tmp_project), faces="flat", size=96)
    assert dispatch.dispatch(args) == 0


def test_a_mover_reaches_preview_as_a_mover_through_the_whole_dispatch_path(tmp_path):
    """**Decision 2.13's ENTIRE point, end to end.** Every other mover test hands a `FaceData(movers=…)`
    straight to `render_brushes_pgm`, so the resolved set could stop reaching `preview` and stay green:
    replacing the resolved set with `frozenset()` while leaving all four refusals in place breaks nothing
    the rest of this file asserts. Then a real `CsgOper=CSG_Subtract` mover in a real level renders
    inside-out AND gold under `--faces flat` — the exact defect 2.13 exists to prevent.

    So this drives `dispatch.dispatch` over a snippet, with a class that IS a mover in conftest's modelled
    substrate but whose name does not end in `Mover`, and reads the mover hue off the written PNG."""
    glass = _room("Glass", 512.0, 256.0)                     # CsgOper=CSG_Subtract
    glass.cls = "DeusEx.BreakableGlass"                      # a REAL mover, name not ending in "Mover"
    out = tmp_path / "mover.png"
    assert dispatch.dispatch(_preview_args(out, layout="single", size=200, annotate="none",
                                           from_t3d=[_snippet(tmp_path, [glass])], faces="flat")) == 0
    b = _rgb(out)
    got = {b[i:i + 3] for i in range(0, len(b), 3)}
    # Mover magenta, from `movers.is_mover` — NOT subtract gold, which both the raw `CsgOper` marker and
    # `classify_brush`'s name guess would have produced, and which would also have culled every
    # camera-facing face.
    assert bytes(MOVER_F) in got, "the resolved mover set did not reach preview"
    assert bytes(SUB_B) not in got and bytes(SUB_F) not in got


# ── the `--brush-colors default=None` plumbing, asserted AT THE SEAM ───────────────────────────

def test_every_brush_colors_consumer_hands_preview_a_non_none_value(tmp_path, monkeypatch):
    """`--brush-colors` parses with `default=None` so an EXPLICIT value stays distinguishable from a
    defaulted one. `getattr(args, "brush_colors", "csg")` does NOT fire its default for an
    existing-but-None attribute, so each consumer needs its own `or "csg"`.

    **No picture test can catch a missing one.** `brush_colors` is compared in exactly one place, so
    `None` and `"csg"` are behaviourally identical through everything this slice renders — a rendered
    comparison passes with all three fixups absent. So assert the SEAM: every dispatch consumer hands
    `preview` a real value. All three layouts are driven, because they are the three consumers."""
    seen: list = []
    for fn in ("render_brushes_pgm", "render_quad_pgm"):
        real = getattr(preview, fn)

        def spy(*a, _real=real, **kw):
            seen.append(kw.get("brush_colors"))
            return _real(*a, **kw)
        monkeypatch.setattr(preview, fn, spy)
    for layout in ("single", "quad", "breakdown"):
        assert _run(tmp_path, [_box("Crate")], layout=layout, size=64, brush_colors=None) == 0
    assert seen and None not in seen
    assert set(seen) == {"csg"}


def test_an_explicit_brush_colors_legend_still_reaches_preview(tmp_path, monkeypatch):
    """The `or "csg"` must default None, not overwrite a real choice."""
    seen: list = []
    real = preview.render_brushes_pgm
    monkeypatch.setattr(preview, "render_brushes_pgm",
                        lambda *a, **kw: (seen.append(kw.get("brush_colors")), real(*a, **kw))[1])
    assert _run(tmp_path, [_box("Crate")], layout="single", size=64, brush_colors="legend") == 0
    assert seen == ["legend"]


def test_the_seam_refuses_a_filled_render_with_no_face_data():
    """`faces` is a PARAMETER, not something read off the seam — `render_data.faces is None` would be
    both `wire` and a filled mode. A filled render handed no `FaceData` has lost the mover set, which is
    the failure the movers/textures split exists to prevent, so it refuses instead of guessing."""
    with pytest.raises(PreviewAbort) as e:
        render_brushes_pgm([_box("Add")], size=32, render_data=PreviewData(), faces="flat")
    assert "mover set" in str(e.value)


def test_an_unrenderable_size_becomes_a_clean_exit_2_through_dispatch(tmp_path, monkeypatch, capsys):
    """`preview.py` raises `PreviewAbort` for what it can only discover mid-render; dispatch maps it to
    exit 2. Never a `MemoryError` traceback out of the CLI."""
    def boom(size):
        raise MemoryError
    monkeypatch.setattr(preview, "_new_buf", boom)
    assert _run(tmp_path, [_box("Crate")], faces="flat", layout="single", size=4096) == 2
    assert "--size 4096" in capsys.readouterr().err


# ── the three colour ROLES under a filled mode (owner ruling) ───────────────────────────────────
# A filled render has three things to colour — fill, ordinary edge, `--highlight` outline — and one
# two-member pair to colour them from. The first shipped assignment gave fill and edge the SAME member,
# which made both the wireframe and the highlight invisible. Both are pinned here by MEASURING colour
# counts, because "something changed" was true of the broken version too.

@pytest.mark.parametrize("actor_fn,facing_fill,facing_edge", [
    (lambda: _box("Add"), ADD_F, ADD_B),           # a non-subtract keeps its `_is_front` faces
    (lambda: _room("Room"), SUB_B, SUB_F),         # a subtract keeps its FAR faces
])
def test_a_filled_edge_draws_in_the_other_member_of_its_brushs_pair(actor_fn, facing_fill, facing_edge):
    """The owner's ruling: an edge drawn in the member its own fill already uses is invisible by
    construction, so a surviving face's edges take the PARTNER member. `wire` is untouched."""
    actor = actor_fn()
    ppm = render_brushes_pgm([actor], view="iso", size=200, annotations=AnnotationSpec.none(),
                             color_by_csg=True, render_data=_flat(), faces="flat")
    got = _colors(ppm)
    assert facing_fill in got and facing_edge in got      # BOTH members present: the outline reads
    # ...and the outline is perimeter-sized, so it is line art and not a second fill.
    assert 0 < _count(ppm, facing_edge) < _count(ppm, facing_fill) / 4


def test_flat_renders_more_than_the_three_colours_the_first_assignment_gave():
    """The regression this ruling exists for, measured the way it was found: the room + two adds scene
    rendered in EXACTLY three colours (background + one fill per CSG op) with no interior creases on the
    room and no boundary at all between the two abutting adds."""
    scene = [_room(), _box("Pillar", 128.0, 256.0, at=(-128.0, -128.0, 0.0)),
             _box("Crate", 128.0, 96.0, at=(64.0, 32.0, -80.0))]
    got = _colors(render_brushes_pgm(scene, view="iso", size=200, annotations=AnnotationSpec.none(),
                                     color_by_csg=True, render_data=_flat(), faces="flat"))
    assert len(got) >= 5                     # bg + both members of each of the two pairs in play
    assert {(BG, BG, BG), SUB_B, SUB_F, ADD_F, ADD_B} <= got


@pytest.mark.parametrize("brush_colors", ["csg", "legend"])
def test_highlight_is_observable_on_a_filled_non_subtract_face(brush_colors):
    """The SECOND observable of the same root cause: `vivid` is the pair's front member, which is also
    what a surviving non-subtract face fills with, so the outline used to paint in exactly the fill beneath
    it (worse under `--brush-colors legend`, where `vivid` IS the tint IS the fill). A highlighted face now
    swaps its FILL to the partner member and outlines in its own."""
    box = _box("Add")
    kw = dict(view="iso", size=200, annotations=AnnotationSpec.none(), color_by_csg=True,
              render_data=_flat(), faces="flat", brush_colors=brush_colors)
    plain = render_brushes_pgm([box], **kw)
    one = render_brushes_pgm([box], highlight_polys={("Add", 1)}, **kw)
    changed = sum(1 for a, b in zip(_pixels(plain), _pixels(one)) if a != b)
    # ~138 px before, and every one of them the bolder stroke on the SILHOUETTE. A highlight has to
    # repaint the face's own AREA, so the count is thousands, not a stroke's worth.
    assert changed > 1000, "a highlighted face must repaint its own area, not just thicken a stroke"
    # ...and highlighting MORE faces must keep changing the picture — the broken version was flat at
    # two colours and ~138 px whether one face or all six were highlighted.
    every = render_brushes_pgm([box], highlight_polys={("Add", i) for i in range(6)}, **kw)
    assert sum(1 for a, b in zip(_pixels(one), _pixels(every)) if a != b) > 500


def test_a_highlighted_face_swaps_its_fill_and_outlines_in_its_own_member():
    """The mechanism, at the seam: three roles off one pair, with no third colour invented. Both brush
    kinds are checked, because on a NON-subtract `own` and `vivid` happen to coincide — so a subtract is
    the only place that distinguishes "outline in the face's own member" from "outline in `vivid`", and
    on a subtract `vivid` is exactly the inverted fill, i.e. invisible again."""
    box = _box("Add")
    geom = _geom([box], faces="flat", highlight_polys={("Add", 1)})
    fills = [rgb for _v, _s, rgb, _d in geom.fills]
    assert fills.count(ADD_B) == 4 and fills.count(ADD_F) == 2    # one front face inverted to BACK
    assert {rgb for _e, rgb, _k in geom.hi_edges} == {ADD_F}          # ...and outlines in FRONT over it

    room = _room("Room")
    sub = _geom([room], faces="flat", highlight_polys={("Room", i) for i in range(6)})
    assert {rgb for _v, _s, rgb, _d in sub.fills} == {SUB_F}          # every far face inverted to FRONT
    assert {rgb for _e, rgb, _k in sub.hi_edges} == {SUB_B}           # outline in BACK, NOT in vivid=FRONT


def test_a_highlighted_subtract_face_is_visible_over_its_own_inverted_fill():
    """The measurement behind the arm above: `vivid` for a subtract IS the colour its highlighted face
    now fills with, so an outline drawn in `vivid` would be invisible exactly as the first assignment was."""
    room = _room("Room")
    kw = dict(view="iso", size=200, annotations=AnnotationSpec.none(), color_by_csg=True,
              render_data=_flat(), faces="flat")
    plain = render_brushes_pgm([room], **kw)
    lit = render_brushes_pgm([room], highlight_polys={("Room", i) for i in range(6)}, **kw)
    assert sum(1 for a, b in zip(_pixels(plain), _pixels(lit)) if a != b) > 1000
    assert SUB_B in _colors(lit)                                  # the outline hue is still on screen


def test_wire_keeps_the_vivid_highlight_hue_untouched():
    """`wire` fills nothing, so none of the reassignment above applies to it — its highlight is still the
    brush's vivid CSG hue, which is what the byte-identity golden also guards."""
    geom = _geom([_box("Add")], faces="wire", highlight_polys={("Add", 1)})
    assert {rgb for _e, rgb, _k in geom.hi_edges} == {ADD_F}
    assert geom.fills == []
    assert {(e[2], e[3]) for e in geom.edges} == {(ADD_F, ADD_B)}  # edge pair NOT swapped under wire


# ── a filled render only needs a class index when there is something to classify ────────────────

@pytest.mark.real_mover_index
def test_a_brushless_set_needs_no_class_index_under_flat(tmp_path, capsys):
    """"Needs" is literal, as decision 2.6 already ruled it for textures. A set with no brush actors has a
    trivially known mover answer — the empty set — so demanding a project/class index for it is an
    over-refusal, and on an EMPTY set it converts `wire`'s clean no-op into exit 2.

    Needs the GENUINE `_mover_index` seam: under conftest's autouse `StubClassIndex` a class index is
    always available, so this passes with or without the short-circuit and pins nothing."""
    light = Actor(name="Lamp", cls="Engine.Light",
                  location=(Decimal(0), Decimal(0), Decimal(0)))
    assert _run(tmp_path, [light], faces="flat") == 0
    assert _run(tmp_path, [], faces="flat") == 0
    assert "nothing to render" in capsys.readouterr().err


@pytest.mark.real_mover_index
def test_no_project_under_flat_names_the_flag_and_the_cause(tmp_path, capsys):
    """`--from-t3d` outside a project is ordinary and `wire` works fully there, so the bare house "not in
    a uedcli project" is not an adequate message for a `--faces` refusal: it names neither the flag nor
    why a preview would want a project. The games-config route was already covered; this is the other
    one, and it needs the GENUINE `_mover_index` seam (the autouse stub opted out)."""
    scene = [_room(), _box("Crate")]
    assert _run(tmp_path, scene, faces="wire") == 0
    capsys.readouterr()
    assert _run(tmp_path, scene, faces="flat") == 2
    err = capsys.readouterr().err
    assert "actor preview --faces flat" in err
    assert "not in a uedcli project" in err and "Engine.Mover" in err
    assert "--faces wire" in err


# ── the stderr note for a highlight that lands on nothing visible ──────────────────────────────
# A highlight can now legitimately do nothing (a hidden face draws nothing at all), so the CLI says so —
# on stderr, never stdout, and never as a refusal: the render is correct.

def _hi_note(capsys) -> str:
    out = capsys.readouterr()
    assert "note: --highlight" not in out.out, "the note must never reach stdout — it would enter a pipe"
    return "".join(ln for ln in out.err.splitlines(keepends=True) if ln.startswith("note: --highlight"))


def test_a_highlight_on_a_hidden_face_says_so_on_stderr_and_still_exits_0(tmp_path, capsys):
    """`Core` is sealed inside the solid add `Shell`, so highlighting one of its faces draws nothing. The
    render is CORRECT, so this is a note and not a refusal — exit 0, image written. Without it the user
    cannot tell a hidden face from a mistyped index or a flag that did not take."""
    shell, core = _box("Shell", size=600.0, height=600.0), _box("Core", size=120.0, height=120.0)
    assert _run(tmp_path, [shell, core], faces="flat", size=200, highlight=["Core:0"]) == 0
    note = _hi_note(capsys)
    assert "Core:0" in note and "not visible" in note             # names the selector, house style
    # It must NOT name a cause. Several different things make a face draw nothing — depth, the subtract
    # cull (which no view will ever reveal), `PF_Invisible`, a vertexless poly — and they are not
    # distinguishable here, so an earlier "hidden behind other geometry at this --view" was wrong for
    # three of the four.
    assert "behind" not in note and "--view" not in note


def _sheet(name, at=(0.0, 0.0, 0.0)):
    """A ONE-face brush. Used wherever a test needs a face that is visible for certain: a closed cube
    self-occludes, so three of its six faces are hidden in any view and `Cube:0` is not reliably visible."""
    from uedcli.builders import sheet
    return make_brush_actor(name, sheet(256.0, 256.0, plane="xy"), location=at, csg="add",
                            poly_flags=preview.PF_NOTSOLID)


def test_the_note_does_not_claim_NOTHING_was_drawn_when_an_index_still_is(tmp_path, capsys):
    """The note is a factual claim about the render, so it must be true in the common case. With the DEFAULT
    `--annotate`, a hidden face keeps the index the spec asked for — 349 px of it on the measured scene — so
    "nothing was drawn for it" was false whenever anyone ran `--highlight` without `--annotate none`. It
    says no HIGHLIGHT was drawn."""
    shell, core = _box("Shell", size=600.0, height=600.0), _box("Core", size=120.0, height=120.0)
    assert _run(tmp_path, [shell, core], faces="flat", size=400, highlight=["Core:0"],
                annotate=DEFAULT_ANNOTATIONS) == 0
    note = _hi_note(capsys)
    assert "Core:0" in note and "no highlight was drawn" in note
    assert "nothing was drawn" not in note


def test_the_note_fires_when_FRAMING_and_not_depth_drew_nothing(tmp_path, capsys):
    """A highlight clipped entirely outside the frame draws nothing, and the note is about "did my flag
    take?", not about depth — so it must fire here too. `--frame <one brush> --highlight <another>` is an
    ordinary workflow.

    This was silent because `shown_highlights` recorded the `_line` CALL rather than a landed pixel;
    `_line` now returns how many it plotted. Asserted under BOTH modes, since framing clips in `wire` too
    and nothing about it is depth-related."""
    near = _box("Near", size=256.0, height=256.0)
    far = _box("Far", size=256.0, height=256.0, at=(20000.0, 20000.0, 0.0))
    for faces in ("flat", "wire"):
        assert _run(tmp_path, [near, far], faces=faces, view="top", size=200,
                    frame="Near", highlight=["Far:0"]) == 0
        note = _hi_note(capsys)
        assert "Far:0" in note, f"{faces}: a highlight clipped outside the frame went unreported"
    # ...and a highlight INSIDE the frame is still silent, so the new test is not just always-on.
    assert _run(tmp_path, [near, far], faces="flat", view="top", size=200,
                frame="Near", highlight=["Near:0"]) == 0
    assert _hi_note(capsys) == ""


def test_a_repeated_highlight_token_is_named_once(tmp_path, capsys):
    """`--highlight` is repeatable and case-insensitive, so the same face can arrive three times; the note
    must not list it three times."""
    shell, core = _box("Shell", size=600.0, height=600.0), _box("Core", size=120.0, height=120.0)
    assert _run(tmp_path, [shell, core], faces="flat", size=200,
                highlight=["Core:0", "Core:0", "core:0"]) == 0
    assert _hi_note(capsys).count("Core:0") == 1


def test_a_highlight_that_lands_says_nothing(tmp_path, capsys):
    """The negative case, which is what makes the note worth anything: a visible highlighted face must not
    produce a note, or the note becomes noise the reader learns to skip."""
    assert _run(tmp_path, [_sheet("Solo")], faces="flat", size=200, highlight=["Solo:0"]) == 0
    assert _hi_note(capsys) == ""


def test_a_whole_brush_highlight_is_silent_even_though_its_back_faces_are_hidden(tmp_path, capsys):
    """**Granularity follows the TOKEN FORM.** A closed brush ALWAYS has hidden back faces, so reporting
    per-face for a whole-brush token would fire on every `--highlight <brush>` ever run. A bare name and
    `:all` mean "this brush" and are reported only if the WHOLE brush came out invisible; an explicit
    index list names faces and is reported per face, even where it happens to cover them all — the form
    is what says which granularity the user was thinking in."""
    box = _box("Solo")
    for token in ("Solo", "Solo:all"):
        assert _run(tmp_path, [box], faces="flat", size=200, highlight=[token]) == 0
        assert _hi_note(capsys) == "", f"{token} should be silent: some of the brush IS visible"
    # An enumerated list is per-face, so a closed cube's self-occluded half IS reported.
    assert _run(tmp_path, [box], faces="flat", size=200,
                highlight=["Solo:0,1,2,3,4,5"]) == 0
    assert "Solo:" in _hi_note(capsys)
    # ...and it DOES fire when the whole brush is invisible, named as the brush rather than six faces.
    shell, core = _box("Shell", size=600.0, height=600.0), _box("Core", size=120.0, height=120.0)
    assert _run(tmp_path, [shell, core], faces="flat", size=200, highlight=["Core"]) == 0
    note = _hi_note(capsys)
    assert "Core" in note and "Core:0" not in note


def test_the_note_does_not_fire_under_wire_for_an_OCCLUDED_face(tmp_path, capsys):
    """`wire` hides nothing by depth — `vis_faces` is empty there, so no face is ever in the hidden set —
    so a highlight that `flat` would report as invisible is silent under `wire`.

    **Deliberately not named "cannot fire".** It is not structurally unreachable: a poly with no
    projectable vertices is dropped before the edge loop in EITHER mode, so a degenerate `--from-t3d` poly
    trips the note under `wire` too. Reporting that is correct — what was wrong was claiming exemption."""
    shell, core = _box("Shell", size=600.0, height=600.0), _box("Core", size=120.0, height=120.0)
    assert _run(tmp_path, [shell, core], faces="wire", size=200, highlight=["Core:0"]) == 0
    assert _hi_note(capsys) == ""


def test_the_note_is_emitted_ONCE_per_command_and_counts_every_pane(tmp_path, capsys):
    """Multi-pane layouts share ONE `shown_highlights` set, so a face hidden in one pane and visible in
    another is a highlight that LANDED. `Target` sits behind `Wall` under `iso` but nowhere near it in
    `top`, so `quad` must stay silent while `single --view iso` reports it — and report it once."""
    target = _sheet("Target")                    # one face, so nothing of its own can hide it
    wall = _box("Wall", size=300.0, height=300.0, at=(-400.0, -400.0, 400.0),
                poly_flags=preview.PF_SEMISOLID)
    scene = [target, wall]
    assert _run(tmp_path, scene, faces="flat", layout="single", size=200, highlight=["Target:0"]) == 0
    single = _hi_note(capsys)
    assert single.count("note:") == 1 and "Target:0" in single
    assert _run(tmp_path, scene, faces="flat", layout="quad", size=200, highlight=["Target:0"]) == 0
    assert _hi_note(capsys) == "", "hidden in the iso pane but visible in the others — it landed"


# ── --focus over a filled mode: ONE scene-order pass, ONE fade per pixel ───────────────────────
# Dimming lines does nothing to a fill, so `--focus` needed a mechanism of its own. Every filled face goes
# through ONE rasterizing loop in scene order against ONE depth buffer — so nothing about what is VISIBLE
# depends on what is focused, coplanar ties included — and a per-pixel mask records whether a de-emphasised
# face won each pixel, which `_fade_dimmed` then fades exactly once.

_FOCUS_KW = dict(view="iso", size=200, annotations=AnnotationSpec.none(), color_by_csg=True,
                 faces="flat")


def _dim(rgb):
    """The colour a `--focus` CONTEXT fill must land at: exactly ONE blend of the resolved colour over
    `BG`, matching `_fade_dimmed`."""
    a = preview._DIM_FILL_ALPHA
    return tuple(round(a * c + (1 - a) * BG) for c in rgb)


def _no_legend_to_px(actors, size, view="top", brush_colors="csg"):
    """World→pixel for a render that draws and reserves NO legend, so `inset_top` is 0 and the framing is
    reproducible from `_scene_geometry`'s own `pts` — the same input the renderer frames from."""
    geom = _geom(actors, faces="flat", view=view, brush_colors=brush_colors)
    _s, to_px, _f, _w = _framing(geom.pts, None, size, view, 30.0, 0, pad=_FRAME_PAD)
    return lambda p3: to_px(preview._project(p3, view, 30.0))


def _a_surviving_face(actor) -> int:
    """A face index of `actor` that survives the cull, identified by the fact that HIGHLIGHTING it
    inverts a fill to the pair's other member. Found rather than hardcoded — which face of a cube
    survives depends on the view."""
    for i in range(len(actor.brush.polys)):
        before = {rgb for _v, _s, rgb, _d in _geom([actor], faces="flat").fills}
        after = {rgb for _v, _s, rgb, _d in
                 _geom([actor], faces="flat", highlight_polys={(actor.name, i)}).fills}
        if after - before:
            return i
    raise AssertionError(f"{actor.name} has no surviving face to highlight")


def test_the_dim_fill_alpha_is_its_own_constant_and_is_pinned():
    """PINNED so it cannot drift unexamined — it is the owner's value, chosen from real renders rather
    than arithmetic (decision 2.12). It is deliberately NOT `_DIM_ALPHA`: 0.15 was tuned for thin LINES,
    where a faint stroke still reads as a stroke, while a large flat area at that strength lands a
    mid-grey ~14 levels off `BG` — near-uniform."""
    assert preview._DIM_FILL_ALPHA == 0.35
    assert preview._DIM_ALPHA == 0.15                    # the EDGE value, unchanged — `wire` included


def test_a_context_fill_fades_by_exactly_one_blend_and_the_focus_stays_opaque():
    """The measurement that made this slice necessary, now inverted. Before it, `--focus` left a
    non-focused brush's opaque fill byte-for-byte unchanged — 17,969 px either way on this very scene —
    so over a fill the cue was not faint but ABSENT. Now every one of those pixels is one blend of the
    colour it had, and the focused brush's own fill is untouched."""
    room, crate = _room(), _box("Crate")
    plain = render_brushes_pgm([room, crate], focus=None, render_data=_flat(), **_FOCUS_KW)
    focused = render_brushes_pgm([room, crate], focus="Crate", render_data=_flat(), **_FOCUS_KW)
    assert _count(plain, SUB_B) > 1000
    assert _count(focused, SUB_B) == 0                            # no opaque room fill survives...
    assert _count(focused, _dim(SUB_B)) == _count(plain, SUB_B)   # ...each px is ONE blend of it
    assert _count(focused, ADD_F) > 100                           # the focused crate fills as always
    assert _count(focused, _dim(ADD_F)) == 0                      # and none of it is dimmed


def test_the_dim_fade_lands_once_per_pixel_not_once_per_face():
    """Several de-emphasised faces cover the probe pixel and EVERY ONE of them wins it in turn (the
    replay below counts exactly the blends a per-face composite would have made), yet the finished pixel
    is a SINGLE fade of the one colour that survived.

    **Not asserted by shuffling actor order:** `assign_tints` is cycled by scene position and a coplanar
    depth tie goes to scene order, so a shuffle legitimately changes the bytes. What must be
    order-independent is the blend, not the scene."""
    size, view = 300, "top"
    # Concentric caps stacked in Z, all covering the world origin. `top` depth is −Z, so each cube is
    # NEARER than the last and every one of their caps passes the strictly-`<` depth test in turn.
    stack = [_box(f"Ctx{i}", size=400.0 - 40 * i, height=64.0, at=(0.0, 0.0, 200.0 * i))
             for i in range(3)]
    actors = stack + [_box("Focus", size=200.0, height=64.0, at=(600.0, 0.0, 0.0))]
    geom = _geom(actors, faces="flat", view=view, color_by_csg=False, focus="Focus")
    _s, to_px, to_pxf, world_to_pxf = _framing(geom.pts, None, size, view, 30.0, 0, pad=_FRAME_PAD)
    px, py = to_px(preview._project((0.0, 0.0, 0.0), view, 30.0))
    # Replay the rasterizing loop face by face, counting how many times a DE-EMPHASISED face wins this
    # pixel — i.e. how many blends a per-face composite would have made here.
    scratch, zs = preview._alloc_buffers(size, depth=True)
    mask = preview._alloc_dim_mask(size)
    d_vec = preview._view_depth(30.0, view)
    writes = 0
    for v3, vs, rgb, dimmed in geom.fills:
        plane = preview._face_depth_affine(v3, world_to_pxf, d_vec)
        if plane is None:
            continue
        before = zs[py * size + px]
        preview._fill_face(scratch, zs, size, [to_pxf(p) for p in vs], plane, rgb, mask, dimmed)
        writes += dimmed and zs[py * size + px] != before
    assert writes >= 3, f"the probe pixel must be contested by several context faces, got {writes}"
    i = (py * size + px) * 3
    assert mask[py * size + px], "the probe pixel must end up owned by a de-emphasised face"
    resolved = tuple(scratch[i:i + 3])
    ppm = render_brushes_pgm(actors, view=view, size=size, annotations=AnnotationSpec.none(),
                             color_by_csg=False, render_data=_flat(), faces="flat", focus="Focus")
    assert _at(ppm, size, px, py) == _dim(resolved)


def test_a_focused_brush_inside_a_SOLID_ADD_stays_hidden_because_focus_is_not_x_ray():
    """**`--focus` is a brightness filter, never x-ray vision** (owner ruling). `Inner` sits wholly inside
    the solid add `Outer`, so a solid body hides it — focusing it does NOT bring it back, and the pixel
    stays `Outer`'s, only dimmed because `Outer` is now context.

    This test INVERTS an earlier promise rather than dropping it: plan §3/S3 asked for "a focused brush
    fully enclosed by another brush is visible", and the ruling superseded that. The scenario is kept
    precisely so the reversal is visible to anyone comparing the plan against the code. Contrast
    `test_a_focused_brush_inside_a_SUBTRACT_room_is_not_hidden_by_it` — a void is not a solid."""
    outer, inner = _box("Outer", size=512.0, height=512.0), _box("Inner", size=128.0, height=128.0)
    tints = assign_tints([outer, inner])
    size = 120
    at = _no_legend_to_px([outer, inner], size, brush_colors="legend")
    kw = dict(size=size, view="top", annotations=AnnotationSpec.none(), color_by_csg=True,
              render_data=_flat(), faces="flat", brush_colors="legend",
              draw_legend=False, reserve_legend=False)
    plain = render_brushes_pgm([outer, inner], focus=None, **kw)
    focused = render_brushes_pgm([outer, inner], focus="Inner", **kw)
    assert _at(plain, size, *at((0.0, 0.0, 0.0))) == tints["Outer"]            # hidden, unfocused...
    assert _at(focused, size, *at((0.0, 0.0, 0.0))) == _dim(tints["Outer"])    # ...and hidden, focused
    assert _at(focused, size, *at((200.0, 0.0, 0.0))) == _dim(tints["Outer"])  # all of it is context now


def test_a_focused_brush_inside_a_SUBTRACT_room_is_not_hidden_by_it():
    """The other half of the ruling, and the case that was broken: a subtract's kept faces are the FAR
    walls of a void, so a box in the room is nearer than them and physics puts it in front — with or
    without `--focus`. Its failure mode is the render that prompted the ruling, where focusing the room
    painted its far walls over everything inside and left the contents all but gone."""
    room, crate = _room(), _box("Crate")
    kw = dict(view="iso", size=200, annotations=AnnotationSpec.none(), color_by_csg=True,
              render_data=_flat(), faces="flat")
    unfocused = _count(render_brushes_pgm([room, crate], focus=None, **kw), ADD_F)
    assert unfocused > 500
    # Focused on the ROOM the crate is context, so it reads at the DIMMED value — but it READS. The
    # failure mode is near-total loss (the render that prompted the ruling kept 9 px of 14,612), so the
    # bar is "essentially all of it", not an exact match: dimmed edges composite rather than overwrite,
    # which legitimately moves a few dozen boundary pixels off the exact fill value.
    on_room = _count(render_brushes_pgm([room, crate], focus="Room", **kw), _dim(ADD_F))
    assert on_room > unfocused * 0.9, f"the room's far walls swallowed the crate: {on_room}/{unfocused}"
    # Focused on the CRATE it is full strength, and unchanged from the unfocused render.
    assert _count(render_brushes_pgm([room, crate], focus="Crate", **kw), ADD_F) == unfocused


def test_a_brush_between_the_camera_and_the_focus_occludes_it():
    """Focus is not x-ray vision in the other direction either: a nearer brush that does not contain the
    focused one still covers it. Physically correct, and the case a containment predicate would have got
    wrong. The camera looks along -x,-y,+z, so `Wall` sits in front of `Target`."""
    target = _box("Target", size=200.0, height=200.0)
    wall = _box("Wall", size=300.0, height=300.0, at=(-400.0, -400.0, 400.0),
                poly_flags=preview.PF_SEMISOLID)
    kw = dict(view="iso", size=200, annotations=AnnotationSpec.none(), color_by_csg=True,
              render_data=_flat(), faces="flat", focus="Target")
    alone = _count(render_brushes_pgm([target], **kw), ADD_F)
    behind_wall = _count(render_brushes_pgm([target, wall], **kw), ADD_F)
    assert alone > 5000
    assert behind_wall < alone / 100, f"the wall failed to occlude the focused brush: {behind_wall}"


def _one_poly(name, w, h, plane, csg="add"):
    """A ONE-face brush. Single-poly on purpose: a cube's faces project onto each other in an axis view, so
    a sibling redraws the outline and hides whichever half of the visibility rule is broken."""
    from uedcli.builders import sheet
    return make_brush_actor(name, sheet(w, h, plane=plane), csg=csg,
                            poly_flags=preview.PF_NOTSOLID)


def _flat_vs_wire(actors, size, view="top"):
    kw = dict(view=view, size=size, annotations=AnnotationSpec.none(), color_by_csg=True,
              render_data=_flat(), draw_legend=False, reserve_legend=False)
    return (_count_nonbg(render_brushes_pgm(actors, faces="flat", **kw), size),
            _count_nonbg(render_brushes_pgm(actors, faces="wire", **kw), size))


@pytest.mark.parametrize("size", [64, 128, 256])
def test_a_face_that_covers_NO_PIXEL_keeps_its_outline(size):
    """Half one of the visibility rule: `_face_is_occluded` must answer "not occluded" for a face that
    covers nothing, because nothing is in front of it. 4096 × 4 UU is ordinary trim; 4 UU is sub-pixel at
    these sizes, so its fill claims no centre.

    **One poly, deliberately.** The measured symptom was on a 4096 × 4 × 4 box, where the coverage-losing
    caps and the edge-on sides project to the SAME 2-D lines — so the sides redraw the outline and the
    brush still appears even with this half broken. A single-face brush has no sibling to hide behind, so
    this test fails if and only if `_face_is_occluded` returns `True` for zero coverage."""
    flat, wire = _flat_vs_wire([_one_poly("Blade", 4096.0, 4.0, "xy")], size)
    assert wire > 0 and flat == wire, f"flat drew {flat} px where wire drew {wire}"


@pytest.mark.parametrize("size", [64, 128, 256])
def test_an_EDGE_ON_face_keeps_its_outline(size):
    """Half two: the caller's `plane is not None` guard. A face seen exactly edge-on has no screen area, so
    `_face_depth_affine` returns None and it fills nothing — but again nothing is in front of it, so it
    must still be outlined. A vertical sheet under `--view top` projects to a line and is that case.

    Also one poly, for the same reason as above. Fails if and only if edge-on is folded into `hidden`."""
    flat, wire = _flat_vs_wire([_one_poly("EdgeOn", 256.0, 256.0, "xz")], size)
    assert wire > 0 and flat == wire, f"flat drew {flat} px where wire drew {wire}"


def test_face_is_occluded_says_NO_for_a_polygon_that_covers_nothing():
    """The unit half of the same rule, asserted directly on `_face_is_occluded` so the verdict is not read
    through a whole render. A sub-pixel quad over a `zbuf` that is already full everywhere: it is behind
    that surface AND covers no pixel centre, and "covers nothing" must win — otherwise the caller strips an
    outline from a face nothing occludes."""
    from array import array
    size = 64
    zbuf = array("f", [1.0]) * (size * size)          # every pixel already owned, at depth 1.0
    subpixel = [(10.2, 10.2), (10.4, 10.2), (10.4, 10.4), (10.2, 10.4)]
    assert not preview._face_is_occluded(zbuf, size, subpixel, (0.0, 0.0, 5.0))
    # ...and a face that DOES cover pixels while sitting behind that surface is occluded, so the test above
    # is not passing for want of any occlusion at all.
    covering = [(10.0, 10.0), (30.0, 10.0), (30.0, 30.0), (10.0, 30.0)]
    assert preview._face_is_occluded(zbuf, size, covering, (0.0, 0.0, 5.0))


def test_a_tiny_brush_beside_a_huge_one_is_not_swallowed_under_flat():
    """The user-facing shape of the same defect: a 16-UU cube is sub-pixel against an 8192-UU neighbour's
    framing, but it sits 2000 UU ABOVE the slab with nothing in front of it, so it must still be outlined.
    This is the "does this detail brush poke through the wall" case `docs/leveldesign/general/design-craft.md`
    sells `flat` for. A cube, so it does NOT discriminate the two halves — the tests above do that; this one
    guards the reported symptom."""
    big = _box("Big", size=8192.0, height=64.0, poly_flags=preview.PF_SEMISOLID)
    small = _box("Small", size=16.0, height=16.0, at=(0.0, 0.0, 2000.0))
    kw = dict(view="top", size=128, annotations=AnnotationSpec.none(), color_by_csg=True,
              render_data=_flat(), faces="flat", draw_legend=False, reserve_legend=False)
    own = {ADD_F, ADD_B}                                  # the small cube's own hues; Big is semisolid
    wire = sum(_count(render_brushes_pgm([big, small], **{**kw, "faces": "wire"}), c) for c in own)
    flat = sum(_count(render_brushes_pgm([big, small], **kw), c) for c in own)
    assert wire > 0 and flat == wire, f"flat drew {flat} px of the small cube where wire drew {wire}"


def test_highlighting_a_hidden_face_never_DELETES_an_index_annotate_asked_for():
    """The complementary half of "a hidden highlight contributes nothing": it must not contribute a
    NEGATIVE either. `--annotate all` numbers every face, facing-blind by design, grading hidden ones down
    rather than dropping them — so highlighting a sealed brush must leave those numbers exactly where they
    were. Only an index the highlight ALONE asked for (`--annotate poly:hi`, or a highlight outside the
    focused brush) goes with it, which is what `hi_only_labels`' `and not plain_idx` guard expresses.

    **Pinned on a scene where the numbers actually paint.** Removing that guard leaves the whole suite
    green otherwise — the sealed brush's own indices are omitted as unreadable if the frame is any wider,
    so a scene with a distant third brush cannot see this. Here it is 0 bytes shipped, 3994 under the
    mutation."""
    shell, core = _box("Shell", size=600.0, height=600.0), _box("Core", size=120.0, height=120.0)
    kw = dict(view="iso", size=400, annotations=AnnotationSpec.all(), color_by_csg=True,
              render_data=_flat(), faces="flat", draw_legend=False, reserve_legend=False)
    hi = {("Core", i) for i in range(len(core.brush.polys))}
    plain = render_brushes_pgm([shell, core], **kw)
    lit = render_brushes_pgm([shell, core], highlight_polys=hi, **kw)
    assert lit == plain, "highlighting a sealed brush deleted indices --annotate had asked for"
    # Sanity: the scene really does paint indices, or the equality above would be vacuous.
    assert plain != render_brushes_pgm([shell, core], **{**kw, "annotations": AnnotationSpec.none()})


def test_hidden_edges_do_not_seed_the_label_density_grid(monkeypatch):
    """A hidden edge paints nothing, so it must not pull a label away from a region that reads as EMPTY.

    **This is observable**, contrary to a review finding that could not reproduce it: the density grid
    places labels only on the LEGACY on-geometry-name path (`color_by_csg=False`) — on the hybrid path
    brush names live in the legend and `items` is empty, so the grid is never consulted and the filter
    looks inert. Measured on the legacy path with names drawn, removing the filter changes the render.

    Asserted by counting what reaches the grid rather than by pixel, so the failure message says WHY."""
    seeded: list = []
    original = preview.DensityGrid.add_segment

    def spy(self, a, b):
        seeded.append((a, b))
        return original(self, a, b)

    monkeypatch.setattr(preview.DensityGrid, "add_segment", spy)
    kw = dict(view="iso", size=200, annotations=AnnotationSpec.all(), color_by_csg=False,
              render_data=_flat(), faces="flat")
    sealed = [_box("Shell", size=600.0, height=600.0), _box("Core", size=120.0, height=120.0)]
    render_brushes_pgm(sealed, **kw)
    hidden_scene = len(seeded)
    emitted = len(_geom(sealed, faces="flat", color_by_csg=False).edges)
    assert 0 < hidden_scene < emitted, (
        f"the sealed brush's hidden edges still seeded the grid: {hidden_scene} of {emitted} emitted")
    # ...and with nothing hidden, every emitted edge DOES seed it — so the filter is not over-broad.
    seeded.clear()
    lone = [_sheet("Solo")]
    render_brushes_pgm(lone, **kw)
    assert len(seeded) == len(_geom(lone, faces="flat", color_by_csg=False).edges)


def test_a_solid_brush_is_OPAQUE_in_both_the_fill_and_the_edge_pass():
    """**A 120³ add cube sealed inside a 600³ add cube must be invisible.** It once showed 421 px of its
    own wireframe through the solid, and this pins both halves of why, because they were two different
    candidate causes with one symptom:

    * **The FILL rasterizer was never the problem.** Replaying the fill pass alone, the inner brush
      contributes zero pixels — `_fill_face`'s even-odd PIXEL-CENTRE rule leaves no unclaimed gap where two
      faces of one brush meet. Measured while diagnosing: the outer brush's 97,776-px silhouette is
      claimed in full. **If this half ever fails, coverage really did break.**
    * **The EDGE pass was.** `_line` has no depth parameter, so an outline used to draw whether or not its
      face was visible. Owner ruling: an edge draws only where its face is frontmost somewhere. **If this
      half fails, the 421-px picture is back** — hidden line art over an opaque solid.

    The guard against over-correcting is `test_two_away_facing_sheets_get_outlines_and_a_boundary`: the
    ruling this narrows exists so a single-sided face is never filled-but-unoutlined, and that case still
    draws its 657 px because such a face IS frontmost where it sits. Both tests must fail if the
    visibility condition is removed — one for each direction."""
    shell = _box("Shell", size=600.0, height=600.0)
    core = _box("Core", size=120.0, height=120.0)
    actors, size = [shell, core], 400
    tints = assign_tints(actors)
    core_cols = {tints["Core"], _fade(tints["Core"])}
    geom = _geom(actors, faces="flat", view="iso", brush_colors="legend")
    _s, _to_px, to_pxf, world_to_pxf = _framing(geom.pts, None, size, "iso", 30.0, 0, pad=_FRAME_PAD)
    d_vec = preview._view_depth(30.0, "iso")
    # Replay ONLY the fill pass — the same calls `render_brushes_pgm` makes, with no edge pass after it.
    buf, zbuf = preview._alloc_buffers(size, depth=True)
    for v3, vs, rgb, _d in geom.fills:
        plane = preview._face_depth_affine(v3, world_to_pxf, d_vec)
        if plane is not None:
            preview._fill_face(buf, zbuf, size, [to_pxf(q) for q in vs], plane, rgb)
    leaked = sum(1 for k in range(0, len(buf), 3) if tuple(buf[k:k + 3]) in core_cols)
    assert leaked == 0, f"the FILL rasterizer leaked {leaked} px of a sealed brush — coverage is broken"
    # ...and the finished render, edge pass included, shows nothing of it either.
    full = render_brushes_pgm(actors, view="iso", size=size, annotations=AnnotationSpec.none(),
                              color_by_csg=True, render_data=_flat(), faces="flat",
                              brush_colors="legend", draw_legend=False, reserve_legend=False)
    through = sum(_count(full, c) for c in core_cols)
    assert through == 0, f"{through} px of a sealed brush show through it (hidden edges are drawing)"


def test_wire_is_structurally_exempt_from_the_visibility_test():
    """`wire` cannot be affected by the hidden-edge rule, and not by luck: `vis_faces` — the list
    `render_brushes_pgm` resolves visibility from — is populated only under a FILLED mode, so the hidden
    set is empty under `wire` and no edge can ever be dropped. Asserted at the seam because the byte-
    identity goldens would also catch it, but would not say WHY it is safe."""
    assert _geom([_box("A"), _room()], faces="wire").vis_faces == []
    assert _geom([_box("A"), _room()], faces="flat").vis_faces != []


def test_a_buried_highlighted_face_contributes_NOTHING_because_highlight_is_not_x_ray():
    """**`--highlight` re-colours what is VISIBLE and is never an x-ray** (owner ruling): a highlighted
    face that depth hides contributes no fill, no outline and no index — highlighting it changes the
    render **not at all**. `Behind` is sealed inside the solid add `Around`.

    This scenario has been inverted TWICE and kept both times, because each earlier reading is one a
    reader could expect to find: first the highlighted FILL punched through the nearer brush, then only
    its outline did, and now neither does. `--highlight` still beats `--focus`'s DIMMING — a highlighted
    face is full strength wherever its brush is — it simply does not beat depth."""
    # Colours come from the CSG palette, NOT from `--brush-colors legend`: `assign_tints` is cycled by
    # scene position, so dropping a brush to build a comparison render would silently re-colour the one
    # under test. A semisolid shell and an add core keep their hues whatever the scene holds.
    around = _box("Around", size=512.0, height=512.0, poly_flags=preview.PF_SEMISOLID)
    behind = _box("Behind", size=128.0, height=128.0)
    focus_target = _box("Elsewhere", size=200.0, height=200.0, at=(1200.0, 0.0, 0.0), csg="subtract")
    actors = [around, behind, focus_target]
    # ISO, not TOP: under a top view every face of a cube projects onto the SAME square, so the last
    # outline drawn wins every pixel and the front face's hue is not separable.
    kw = dict(size=300, view="iso", annotations=preview.parse_annotation_spec("poly:hi"),
              color_by_csg=True, render_data=_flat(), faces="flat", focus="Elsewhere",
              draw_legend=False, reserve_legend=False)
    hi = {("Behind", i) for i in range(len(behind.brush.polys))}
    plain = render_brushes_pgm(actors, **kw)
    lit = render_brushes_pgm(actors, highlight_polys=hi, **kw)
    # THE assertion: the highlight is a no-op on a face nothing can see. `--annotate poly:hi` is used so
    # the index is owed solely to the highlight, which puts the fill, the outline AND the number in scope.
    assert lit == plain
    # ...and it is a no-op because the face is HIDDEN, not because the highlight is broken: exposed, the
    # same highlight on the same brush paints plenty.
    exposed_plain = render_brushes_pgm([behind, focus_target], **kw)
    exposed_lit = render_brushes_pgm([behind, focus_target], highlight_polys=hi, **kw)
    assert exposed_lit != exposed_plain
    assert _count(exposed_lit, ADD_B) > 500 and _count(exposed_lit, ADD_F) > 100



def test_highlight_overrides_focus_over_a_dimmed_context():
    """`--highlight` re-lights ON TOP of the dimming, the FILL included: a highlighted face keeps the
    inverted fill S2 gave it (the pair's other member) at full strength, while the rest of its own brush
    stays context. Dimming it would have made the highlight one more invisible cue of exactly the kind S2
    had to fix."""
    room, crate = _room(), _box("Crate")
    idx = _a_surviving_face(room)
    base = render_brushes_pgm([room, crate], focus="Crate", render_data=_flat(), **_FOCUS_KW)
    lit = render_brushes_pgm([room, crate], focus="Crate", render_data=_flat(),
                             highlight_polys={("Room", idx)}, **_FOCUS_KW)
    assert _count(base, SUB_F) == 0            # nothing of the room reads at full strength...
    assert _count(lit, SUB_F) > 200            # ...until one face is highlighted; its fill inverts, lit
    assert _count(lit, _dim(SUB_B)) > 200      # and the REST of the room is still dimmed context
    # The face is UNDIMMED, not dimmed — the claim, at the seam.
    geom = _geom([room, crate], faces="flat", focus="Crate", highlight_polys={("Room", idx)})
    assert SUB_F in {rgb for _v, _s, rgb, _d in geom.fills}
    assert SUB_F not in {rgb for _v, _s, rgb, d in geom.fills if d}


@pytest.mark.parametrize("spec", ["none", "all", "poly:hi"])
@pytest.mark.parametrize("n_hi", [0, 1, 6])
def test_a_numbered_face_is_always_full_strength_but_not_the_reverse(spec, n_hi):
    """The two tests share only their FOCUS half, and the implication runs ONE WAY. Both ask "focused
    brush or highlighted face", but a face's index additionally passes `--annotate`, so:

    * **numbered ⇒ full strength** — a number never lands on a dimmed fill. Asserted across every
      `--annotate` value and with the highlight inside the CONTEXT brush, since that is the combination
      that could put one there.
    * **full strength ⇏ numbered** — `--annotate none` leaves a focused brush fully lit and unnumbered.

    Pinned because the code once claimed these were one predicate, which invites collapsing `lit` into
    `show_idx`; the second assertion is the counter-example that claim missed."""
    room, crate = _room(), _box("Crate")
    geom = _geom([room, crate], faces="flat", focus="Crate",
                 annotations=preview.parse_annotation_spec(spec),
                 highlight_polys={("Room", i) for i in range(n_hi)})
    dimmed = {id(v3) for v3, _s, _c, d in geom.fills if d}
    assert not [t for _c, t, _a, _d, v3, _b in geom.poly_labels if id(v3) in dimmed]
    # The highlight MOVES faces between the passes; it never creates or drops one. 9 = the crate's 6 +
    # the 3 room faces that survive the subtract cull, of which `n_hi` indices highlight at most 3.
    assert len(geom.fills) == 9
    assert sum(1 for *_r, d in geom.fills if not d) == 6 + min(n_hi, 3)
    if spec == "none":
        assert geom.fills and not geom.poly_labels   # lit but unnumbered — the converse fails


def test_only_the_focused_brush_carries_face_indices_and_they_are_in_its_tint():
    room, crate = _room(), _box("Crate")
    geom = _geom([room, crate], faces="flat", focus="Crate", annotations=AnnotationSpec.all())
    assert {name for *_rest, name in geom.poly_labels} == {"Crate"}
    assert {accent for _c, _t, accent, *_r in geom.poly_labels} == {assign_tints([room, crate])["Crate"]}


def test_focus_does_not_shift_decal_grading():
    """`occluders` is what `_occluder_count`/`_decal_opacity` grade each remaining decal against, and it
    still spans EVERY brush — de-emphasising a brush must not change how deeply a focused brush's face is
    buried."""
    scene = [_room(), _box("Crate")]
    assert _geom(scene, faces="flat", focus="Crate").occluders == _geom(scene, faces="flat").occluders


def test_point_sprites_and_show_overlays_survive_a_focused_fill():
    """The dim fade runs at step 2 with the fills, so the point layer still draws over it."""
    rgb, mask = bytes([255, 0, 255] * 4), bytes([1] * 4)
    pr = PointRender(label="P", sprite=(2, 2, rgb, mask), sprite_world=(64.0, 64.0),
                     collision=(48.0, 48.0), light_radius=120.0, sound_radius=160.0)
    light = Actor(name="P", cls="Engine.Light", location=(Decimal(0), Decimal(0), Decimal(0)))
    data = PreviewData(points={"P": pr}, faces=FaceData(movers=frozenset()))
    ppm = render_brushes_pgm([_room(), _box("Crate"), light], view="top", size=192,
                             annotations=AnnotationSpec.none(), color_by_csg=True,
                             render_data=data, faces="flat", focus="Crate")
    got = _colors(ppm)
    assert (255, 0, 255) in got and _dim(SUB_B) in got        # the sprite, over the faded room
    for overlay in (preview.COL_COLLISION, preview.COL_LIGHT, preview.COL_SOUND):
        assert overlay in got


def test_wire_keeps_dimming_edges_only_and_fills_nothing_under_focus():
    """`wire` shares the `--focus` path this slice restructured. It must still reach the renderer with no
    fills at all, and its non-focused edges still composited at `_DIM_ALPHA`."""
    geom = _geom([_room(), _box("Crate")], faces="wire", focus="Crate")
    assert geom.fills == []
    assert {e[4] for e in _geom([_box("Crate")], faces="wire", focus="Crate").edges} == {1.0}
    assert {e[4] for e in _geom([_room()], faces="wire", focus="Crate").edges} == {preview._DIM_ALPHA}


# ── the coverage rule ──────────────────────────────────────────────────────────────────────────

def test_fill_coverage_and_depth_sample_the_pixel_centre():
    """`_fill_face` samples at (`x+0.5`, `y+0.5`) — the rule `render.rs` also uses, so it becomes an
    agreement question the moment a second renderer reads it. Dropping the half-pixel on x, on y, or on
    both is invisible to every other test in this suite, so it is pinned directly: the polygon's edges
    sit ON half-integer coordinates, where the two conventions differ by a whole row and column."""
    from array import array
    size = 8
    buf = bytearray(bytes((BG, BG, BG)) * size * size)
    zbuf = array("f", [float("inf")]) * (size * size)
    square = [(2.2, 2.2), (5.8, 2.2), (5.8, 5.8), (2.2, 5.8)]
    preview._fill_face(buf, zbuf, size, square, (1.0, 10.0, 0.0), (7, 8, 9))
    lit = {(i // 3 % size, i // 3 // size) for i in range(0, len(buf), 3)
           if buf[i:i + 3] == bytes((7, 8, 9))}
    # Centre sampling covers 2..5 on both axes; sampling at the pixel ORIGIN starts at 3 on that axis.
    assert lit == {(x, y) for x in range(2, 6) for y in range(2, 6)}
    # ...and DEPTH is evaluated at the same centre: 1*(2+0.5) + 10*(2+0.5) = 27.5 — 27.0 if x lost its
    # half-pixel, 22.5 if y did.
    assert zbuf[2 * size + 2] == 27.5


def test_a_mirrored_brushs_on_face_digits_are_not_mirrored():
    """The on-face decal basis fixes `Uw`'s sign from the SCREEN projection precisely so a glyph is never
    mirror-imaged, and a reflected brush is the case that would break a winding-derived basis. Checked by
    eye on a 1024-UU mirrored room (the digits read `2` and `1`, not their mirror images) and pinned here
    at the basis: the projected `(Uw, Vw)` frame must stay right-reading (screen cross < 0, pixel-y down)
    on every face of a mirrored brush, exactly as on an unmirrored one."""
    from uedcli import rotation
    from uedcli.preview import _face_decal_basis, _project
    for scale in (None, (-1, 1, 1), (1, -1, 1)):
        room = _room("Room") if scale is None else _mirror(_room("Room"), scale)
        R, pp = rotation.actor_linear(room), rotation.actor_prepivot(room)
        loc = room.location or (Decimal(0), Decimal(0), Decimal(0))
        for poly in room.brush.polys:
            v3 = [(float(loc[0] + w[0]), float(loc[1] + w[1]), float(loc[2] + w[2]))
                  for w in (rotation.local_offset(R, pp, v) for v in poly.vertices)]
            basis = _face_decal_basis(v3, lambda p: _project(p, "iso", 30.0))
            assert basis is not None
            _cw, uw, vw = basis
            o = v3[0]
            s0 = _project(o, "iso", 30.0)

            def d(w):
                q = _project((o[0] + w[0], o[1] + w[1], o[2] + w[2]), "iso", 30.0)
                return (q[0] - s0[0], q[1] - s0[1])
            a, b = d(uw), d(vw)
            assert a[0] * b[1] - a[1] * b[0] < 0, f"mirrored glyph frame for scale={scale}"


# ── `_face_depth_affine`: every documented choice, pinned ───────────────────────────────────────
# Four decisions are stated in its docstring and in `architecture.md`, and each was invisible to the
# whole suite: the singular-solve skip, the degenerate-normal skip, the face-sized probe step, and the
# `verts[0]` plane anchor. The behaviour was already right; only the pins were missing.

_D_TOP = (0.0, 0.0, -1.0)          # `_view_depth(30, "top")` — depth = −z, smaller = nearer


def _px_identity(p3):
    """A world→pixel map that is the identity on (x, y), so a probe's screen offset is its world one."""
    return (p3[0], p3[1])


def test_an_edge_on_face_gives_no_depth_plane_and_is_skipped():
    """A face whose PROJECTION has zero area gives a singular gradient solve. It is detected up front and
    skipped — returning a zero plane instead would fill it at a constant, meaningless depth."""
    # A unit square standing in the XZ plane, viewed from TOP: it projects to a line.
    edge_on = [(0.0, 0.0, 0.0), (100.0, 0.0, 0.0), (100.0, 0.0, 100.0), (0.0, 0.0, 100.0)]
    assert preview._face_depth_affine(edge_on, _px_identity, _D_TOP) is None
    # ...while the same square laid flat solves fine, so the None is about projection, not the face.
    flat_sq = [(0.0, 0.0, 0.0), (100.0, 0.0, 0.0), (100.0, 100.0, 0.0), (0.0, 100.0, 0.0)]
    assert preview._face_depth_affine(flat_sq, _px_identity, _D_TOP) is not None


@pytest.mark.parametrize("degenerate", [
    [(0.0, 0.0, 0.0), (100.0, 0.0, 0.0), (200.0, 0.0, 0.0)],          # collinear ⇒ zero-length normal
    [(5.0, 5.0, 5.0), (5.0, 5.0, 5.0), (5.0, 5.0, 5.0)],              # all three vertices coincident
])
def test_a_degenerate_face_gives_no_depth_plane(degenerate):
    """The `nl` guard on the Newell normal earns its place by the EXACT-zero case: delete it and a
    collinear face raises `ZeroDivisionError` normalising the normal (verified). Its THRESHOLD value is
    not separately observable — any face small enough to trip `nl < 1e-12` also has a screen determinant
    below `1e-9`, and float64 cannot represent a sliver thin enough to trip one without the other — so
    there is no test that distinguishes `1e-12` from any smaller bound, and none is missing."""
    assert preview._face_depth_affine(degenerate, _px_identity, _D_TOP) is None


@pytest.mark.parametrize("size", [4.0, 4096.0])
def test_the_depth_plane_is_exact_on_a_detail_brush_and_on_a_room(size):
    """Depth is affine in screen space under an orthographic camera, so the solve is EXACT — not merely
    close — at any face size. Checked by solving a tilted plane and reading the depth back at its own
    vertices."""
    # A 45° ramp: z rises with x across the face, so depth (= −z) varies linearly in screen x.
    ramp = [(0.0, 0.0, 0.0), (size, 0.0, size), (size, size, size), (0.0, size, 0.0)]
    plane = preview._face_depth_affine(ramp, _px_identity, _D_TOP)
    assert plane is not None
    a, b, c = plane
    for x, y, z in ramp:
        assert a * x + b * y + c == pytest.approx(-z, rel=1e-9, abs=1e-6 * size)


@pytest.mark.parametrize("px_per_uu", [1.0, 1e-3, 1e-5])
def test_the_singular_test_is_about_the_face_not_the_probe_length(px_per_uu):
    """WHY the probes step out by the face's own size. The singular test is `abs(det) < 1e-9` on a
    determinant measured in PIXELS, so with a fixed probe step it would scale with the current framing:
    at 1e-5 px per world unit a 1-UU step gives det ~1e-10 and a perfectly good 4096-UU floor would be
    skipped as edge-on. Stepping out by the face's own size makes the test mean "this FACE has no screen
    area", independently of zoom.

    It buys no float precision — measured identical either way up to 1e15-scale faces — and the docstring
    used to claim it did; that claim was wrong and is corrected."""
    floor = [(0.0, 0.0, 0.0), (4096.0, 0.0, 0.0), (4096.0, 4096.0, 0.0), (0.0, 4096.0, 0.0)]
    assert preview._face_depth_affine(
        floor, lambda p: (p[0] * px_per_uu, p[1] * px_per_uu), _D_TOP) is not None


def test_the_depth_plane_is_anchored_at_verts_0_not_the_centroid():
    """Faces are NOT guaranteed planar — `--from-t3d` reads arbitrary editor T3D — so which plane the
    depth comes from is observable. It is the face's own Newell normal through `verts[0]`, so `verts[0]`'s
    depth is reproduced EXACTLY while a non-planar vertex off that plane is not. Anchoring at the centroid
    instead shifts the whole plane and stops reproducing any vertex exactly."""
    bent = [(0.0, 0.0, 0.0), (100.0, 0.0, 0.0), (100.0, 100.0, 60.0), (0.0, 100.0, 0.0)]
    a, b, c = preview._face_depth_affine(bent, _px_identity, _D_TOP)

    def at(p, offset=c):
        return a * p[0] + b * p[1] + offset

    assert at(bent[0]) == pytest.approx(-bent[0][2], abs=1e-9)       # the ANCHOR, reproduced exactly
    assert at(bent[1]) != pytest.approx(-bent[1][2], abs=1.0)        # a vertex off that plane: -30 vs 0
    # The same normal anchored at the CENTROID is a different plane, and it no longer reproduces
    # `verts[0]` — which is what makes the anchor choice observable rather than cosmetic.
    cx, cy, cz = (sum(v[k] for v in bent) / len(bent) for k in range(3))
    c_centroid = -cz - a * cx - b * cy
    assert at(bent[0], c_centroid) != pytest.approx(-bent[0][2], abs=1.0)


# ── `--faces textured`: the texel path (renderer level) ─────────────────────────────────────────
# These drive `render_brushes_pgm`/the fill helpers directly with a hand-built `TextureData`, so the
# shade, mip pick, texel addressing and masking are pinned with NO project, games config or real
# content. What dispatch RESOLVES (ref resolution, the scaled/brush-colors refusals, the actor-OR'd
# mask flag, the bMasked fixture arm) is covered in the dispatch section further down.

def _solid_mip(w, h, rgb, *, hole=()):
    """One `(w, h, rgb, mask)` mip filled with `rgb`; `hole` indices get mask 0 (a masked hole)."""
    holes = set(hole)
    return (w, h, bytes(rgb) * (w * h),
            bytes(0 if i in holes else 1 for i in range(w * h)))


def _cols_mip(colors):
    """A `len(colors)`×1 mip whose i-th texel is `colors[i]` — so a rendered pixel names the texel it
    sampled, which is how the wrap + `/2**level` addressing is read back."""
    w = len(colors)
    return (w, 1, b"".join(bytes(c) for c in colors), bytes([1]) * w)


def _tex(by_ref=None, masked=None, movers=()):
    return PreviewData(faces=FaceData(movers=frozenset(movers),
                                      textures=TextureData(by_ref=by_ref or {}, masked=masked or {})))


def _tbox(name="Box", ref="Fix.T", **kw):
    """An add cube whose every face carries `ref` (or None for a no-texture face)."""
    return make_brush_actor(name, cube(128.0, 128.0, 128.0, texture=ref), **kw)


# -- shade (§4.1) --------------------------------------------------------------------------------

def test_shade_matches_the_native_formula_and_skips_degenerate_faces():
    """`0.55 + 0.45*|N·L|/|N|` with the world Newell normal (§4.1), matching `render.rs`. A face with
    fewer than 3 vertices or a zero-length normal is skipped (None), exactly as `render.rs` skips it —
    a golden PNG cannot separate a shade error from a UV error, so the formula is pinned on its own."""
    from uedcli.preview import _face_shade, _KEY_LIGHT, newell
    wall = [(0.0, 0.0, 0.0), (0.0, 100.0, 0.0), (0.0, 100.0, 100.0), (0.0, 0.0, 100.0)]  # +X normal
    n = newell(wall)
    nl = sum(c * c for c in n) ** 0.5
    dot = sum(a * b for a, b in zip(n, _KEY_LIGHT))
    assert _face_shade(wall) == pytest.approx(0.55 + 0.45 * abs(dot) / nl)
    assert _face_shade(wall[:2]) is None                                  # < 3 vertices
    assert _face_shade([(0.0, 0.0, 0.0)] * 3) is None                     # zero-length normal


# -- texel addressing: wrap + the /2**level rescale (§4.3) ---------------------------------------

def test_texel_fetch_wraps_and_the_mip_level_rescales_the_uv():
    """`tx = floor(u / 2**level) % mip_w`. The `/2**level` is load-bearing: `u` is in MIP-0 units, so a
    level-1 (half-size) mip must map the SAME world span once, not tile twice. A test of level SELECTION
    alone passes the buggy version, so this pins the sampling arithmetic directly."""
    from uedcli.preview import _fill_face_textured
    cols = [(10, 0, 0), (20, 0, 0), (30, 0, 0), (40, 0, 0)]              # 4 texels, distinct
    mip = _cols_mip(cols)
    size = 8
    # u = x (au=1), depth 0 everywhere; a one-row strip over x∈[0,8).
    poly = [(0.0, 0.0), (8.0, 0.0), (8.0, 1.0), (0.0, 1.0)]
    uv = ((1.0, 0.0, 0.0), (0.0, 0.0, 0.0))

    def render(inv):
        buf = bytearray((BG, BG, BG) * (size * size))
        zbuf = __import__("array").array("f", [float("inf")]) * (size * size)
        _fill_face_textured(buf, zbuf, size, poly, (0.0, 0.0, 0.0), uv, mip, False, 1.0, inv)
        return [tuple(buf[(x) * 3:(x) * 3 + 3]) for x in range(size)]

    lvl0 = render(1.0)                                          # mip-0 units: tx = floor(x+0.5) % 4
    assert lvl0[4] == (10, 0, 0)                                # x=4 WRAPS to texel 0
    lvl1 = render(0.5)                                          # a level-1 sample: tx = floor((x+0.5)/2) % 4
    assert lvl1[4] == (30, 0, 0)                                # x=4 → texel 2, NOT the wrapped texel 0
    assert lvl0[4] != lvl1[4], "the /2**level rescale had no effect — u was not in mip-0 units"


def test_the_shade_multiply_truncates_and_clamps_like_render_rs():
    """`(texel*shade).min(255) as u8` — truncation (`int`), not rounding, and a hard 255 clamp."""
    from uedcli.preview import _fill_face_textured
    mip = (1, 1, bytes((100, 200, 200)), bytes([1]))
    size = 2
    poly = [(0.0, 0.0), (2.0, 0.0), (2.0, 1.0), (0.0, 1.0)]
    uv = ((0.0, 0.0, 0.0), (0.0, 0.0, 0.0))
    buf = bytearray((BG, BG, BG) * (size * size))
    zbuf = __import__("array").array("f", [float("inf")]) * (size * size)
    _fill_face_textured(buf, zbuf, size, poly, (0.0, 0.0, 0.0), uv, mip, False, 1.5, 1.0)
    assert tuple(buf[0:3]) == (150, 255, 255)                  # 100*1.5=150; 200*1.5=300 → clamp 255


# -- masking (§4.3, decision 2.3) ----------------------------------------------------------------

def test_a_masked_hole_writes_neither_colour_nor_depth_and_index0_draws_when_unmasked():
    """Decision 2.3, both directions AND the depth half. On a MASKED face a `mask==0` texel leaves the
    pixel at `BG` and does NOT write depth, so a face behind shows through; on an UNMASKED face the same
    index-0 texel is an ordinary colour and draws normally (the 464/2669 flat-swatch case the spike
    measured)."""
    from uedcli.preview import _fill_face_textured
    import array as _arr
    mip = (2, 1, bytes((50, 50, 50, 200, 200, 200)), bytes((0, 1)))     # texel 0 hole, texel 1 opaque
    size = 8
    poly = [(0.0, 0.0), (8.0, 0.0), (8.0, 1.0), (0.0, 1.0)]
    uv = ((1.0, 0.0, 0.0), (0.0, 0.0, 0.0))                    # u=x → even x → texel 0, odd x → texel 1

    def render(masked):
        buf = bytearray((BG, BG, BG) * (size * size))
        zbuf = _arr.array("f", [float("inf")]) * (size * size)
        _fill_face_textured(buf, zbuf, size, poly, (0.0, 0.0, 5.0), uv, mip, masked, 1.0, 1.0)
        return buf, zbuf

    buf, zbuf = render(True)
    assert tuple(buf[0:3]) == (BG, BG, BG) and zbuf[0] == float("inf")    # hole: no colour, no depth
    assert tuple(buf[3:6]) == (200, 200, 200) and zbuf[1] == 5.0          # opaque texel drew + wrote depth
    buf, zbuf = render(False)
    assert tuple(buf[0:3]) == (50, 50, 50) and zbuf[0] == 5.0             # unmasked: index 0 draws


def test_a_masked_hole_lets_a_face_behind_show_through_end_to_end():
    """The point of skipping the depth write: a hole is see-through. A front sheet textured with a
    half-hole texture over a solid back sheet shows the back where the front is holed."""
    front = make_brush_actor("Front", sheet(256.0, 256.0, plane="xy", texture="Fix.Hole"),
                             location=(0.0, 0.0, 128.0), csg="add")
    back = make_brush_actor("Back", sheet(256.0, 256.0, plane="xy", texture="Fix.Solid"),
                            location=(0.0, 0.0, 0.0), csg="add")
    by_ref = {"fix.hole": [(2, 1, bytes((90, 0, 0, 0, 90, 0)), bytes((0, 1)))],   # texel0 hole
              "fix.solid": [_solid_mip(1, 1, (0, 0, 200))]}
    masked = {("Front", 0): True, ("Back", 0): False}
    ppm = render_brushes_pgm([front, back], view="top", size=96, annotations=AnnotationSpec.none(),
                             color_by_csg=True, render_data=_tex(by_ref, masked), faces="textured")
    got = _colors(ppm)                                        # texture colours come out × per-face shade
    assert any(r == 0 and g == 0 and b > 0 for r, g, b in got), "the back (blue) did not show through"
    assert any(r == 0 and g > 0 and b == 0 for r, g, b in got), "the front's opaque (green) half is gone"


# -- no texture, and non-finite frames (§4.3) ----------------------------------------------------

def test_a_poly_with_no_texture_renders_default_grey_times_shade():
    """A generated brush (no `Texture` on any face) is the most common `textured` render in practice. It
    is NOT an error — each face fills `DEFAULT_GREY × shade`, a neutral grey, matching `render.rs`'s
    `tex_index < 0` path."""
    box = _tbox("Plain", ref=None)
    ppm = render_brushes_pgm([box], view="iso", size=96, annotations=AnnotationSpec.none(),
                             color_by_csg=True, render_data=_tex(), faces="textured")
    fills = [px for px in _pixels(ppm) if px != (BG, BG, BG)]
    assert fills, "the untextured box drew nothing"
    for r, g, b in fills:
        assert r == g == b, f"a grey fill must have equal channels, got {(r, g, b)}"
        assert 0 < r <= DEFAULT_GREY[0]                       # 128 × shade, shade ≤ 1


@pytest.mark.parametrize("bad", [float("inf"), float("nan")])
def test_a_non_finite_uv_frame_refuses_naming_the_actor_and_poly(bad):
    """A corrupt authored frame (`inf`/`nan`, reachable via `--from-t3d`) is a clean `PreviewAbort`
    naming the actor and poly — NEVER a `DEFAULT_GREY` fallback, which would be pixel-identical to the
    legitimate no-`Texture` face above, i.e. a half-answer that looks like a full one."""
    box = _tbox("Bad")
    box.brush.polys[2].texture_u = (bad, 0.0, 0.0)           # a corrupt authored TextureU on poly 2
    with pytest.raises(PreviewAbort) as e:
        render_brushes_pgm([box], view="iso", size=48, annotations=AnnotationSpec.none(),
                           color_by_csg=True, faces="textured",
                           render_data=_tex({"fix.t": [_solid_mip(1, 1, (200, 0, 0))]},
                                            {("Bad", i): False for i in range(6)}))
    assert "Bad" in str(e.value) and "poly 2" in str(e.value)


# -- mip selection is per face from its own gradients (§4.4) -------------------------------------

def test_mip_level_is_clamped_log2_of_the_max_axis_gradient():
    from uedcli.preview import _mip_level
    assert _mip_level(1.0, 0.0, 0.0, 1.0, 8) == 0             # tpp=1 → floor(log2 1)=0
    assert _mip_level(4.0, 0.0, 0.0, 1.0, 8) == 2             # tpp=4 → 2
    assert _mip_level(0.1, 0.0, 0.0, 0.1, 8) == 0             # tpp<1 clamps up to 1.0 → 0
    assert _mip_level(9999.0, 0.0, 0.0, 0.0, 3) == 2          # clamped to len-1


def test_the_mip_pick_uses_the_faces_own_screen_gradients_not_a_view_global_gain():
    """§4.4 at a NON-default `--iso-angle 80`. The quantity is the least screen gain WITHIN the face's
    own plane, which a view-global projection number cannot see: a +X wall and a +Z floor of the SAME
    texel scale project with different in-plane gain, so they take DIFFERENT mip levels — a global gain
    would tie them, and a test that only checked "iso differs from ortho" would pass the buggy version."""
    from uedcli.preview import _face_uv_affine, _mip_level
    wall = [(0.0, 0.0, 0.0), (0.0, 512.0, 0.0), (0.0, 512.0, 512.0), (0.0, 0.0, 512.0)]  # +X
    floor = [(0.0, 0.0, 0.0), (512.0, 0.0, 0.0), (512.0, 512.0, 0.0), (0.0, 512.0, 0.0)]  # +Z
    wall_frame = ((0.0, 0.0, 0.0), (0.0, 1.0, 0.0), (0.0, 0.0, 1.0), (0.0, 0.0))
    floor_frame = ((0.0, 0.0, 0.0), (1.0, 0.0, 0.0), (0.0, 1.0, 0.0), (0.0, 0.0))
    # A framing at iso 80 over both faces, shared scale (so any level difference is the in-plane gain).
    geom = _scene_geometry([_u_shape()], view="iso", iso_angle=80.0, annotations=AnnotationSpec.none(),
                           highlight_polys=set(), focus_cf=None, hybrid=False, tints={},
                           color_by_csg=False, render_data=_flat(), faces="flat")
    pts = [preview._project(p, "iso", 80.0) for f in (wall, floor) for p in f]
    _s, _tp, _to, w2p = _framing(pts, None, 256, "iso", 80.0, 0, pad=_FRAME_PAD)

    def level(v3, frame):
        (au, bu, _c1), (av, bv, _c2) = _face_uv_affine(v3, frame, w2p)
        return _mip_level(au, bu, av, bv, 10)

    assert level(wall, wall_frame) != level(floor, floor_frame)


# -- textured draws NO wireframe (decision 2.5) -------------------------------------------------

def test_textured_emits_no_wireframe_pixels_while_flat_does():
    """Decision 2.5's most visible observable. Under `color_by_csg`, `flat` outlines every visible face
    in a CSG hue; `textured` draws none of that line art (only `--highlight`, absent here). The texture
    is pure green, so ANY blue/violet CSG-hue pixel would be a leaked wireframe edge."""
    box = _tbox("Add")
    by_ref = {"fix.t": [_solid_mip(1, 1, (0, 200, 0))]}
    masked = {("Add", i): False for i in range(6)}
    kw = dict(view="iso", size=96, annotations=AnnotationSpec.none(), color_by_csg=True)
    tex = render_brushes_pgm([box], render_data=_tex(by_ref, masked), faces="textured", **kw)
    flat = render_brushes_pgm([box], render_data=_flat(), faces="flat", **kw)
    assert _count(flat, ADD_B) > 0, "flat must keep its wireframe (the control)"
    assert _count(tex, ADD_F) == 0 and _count(tex, ADD_B) == 0, "textured leaked a CSG wireframe edge"
    for r, g, b in (px for px in _pixels(tex) if px != (BG, BG, BG)):
        assert r == 0 and b == 0, f"a non-green pixel means line art leaked: {(r, g, b)}"


def test_a_highlight_outline_is_the_only_line_art_textured_keeps():
    """§4.6/§5: `textured` keeps the `--highlight` vivid outline, and the highlighted face still shows
    its TEXTURE (its fill is not inverted). So the render carries the texture colour AND the vivid hue."""
    box = _tbox("Add")
    by_ref = {"fix.t": [_solid_mip(1, 1, (0, 200, 0))]}
    masked = {("Add", i): False for i in range(6)}
    hi = {("Add", 0), ("Add", 1), ("Add", 2), ("Add", 3), ("Add", 4), ("Add", 5)}
    ppm = render_brushes_pgm([box], view="iso", size=96, annotations=AnnotationSpec.none(),
                             color_by_csg=True, render_data=_tex(by_ref, masked), faces="textured",
                             highlight_polys=hi)
    got = _colors(ppm)
    assert any(g > 0 and r == 0 and b == 0 for r, g, b in got), "the texture is gone"
    assert ADD_F in got, "the highlight outline (vivid CSG hue) is missing"


# -- the golden ----------------------------------------------------------------------------------

GOLDEN_TEXTURED = FIXTURES / "preview_textured_golden_iso.png"


def _checker_mip(w, h):
    """A 2-colour checker mip so the golden shows tiling, UV orientation and per-face shade at once."""
    px = bytearray()
    for y in range(h):
        for x in range(w):
            px += bytes((200, 60, 60) if (x // 2 + y // 2) % 2 else (60, 60, 200))
    return (w, h, bytes(px), bytes([1]) * (w * h))


def test_textured_golden_cube(tmp_path):
    """End-to-end pixel stability of a textured cube. Offline: a synthesized checker texture over the
    shared render path. Bless with `UEDCLI_BLESS_GOLDEN=1 bin/test -k textured_golden`."""
    box = _tbox("Cube")
    by_ref = {"fix.t": [_checker_mip(16, 16)]}
    masked = {("Cube", i): False for i in range(6)}
    ppm = render_brushes_pgm([box], view="iso", size=128, annotations=AnnotationSpec.none(),
                             color_by_csg=True, render_data=_tex(by_ref, masked), faces="textured")
    from PIL import Image
    from io import BytesIO
    out = tmp_path / "textured.png"
    Image.open(BytesIO(ppm)).convert("RGB").save(out)
    got = _rgb(out)
    if os.environ.get("UEDCLI_BLESS_GOLDEN"):
        Image.open(out).convert("RGB").save(GOLDEN_TEXTURED)
        pytest.skip(f"golden blessed → {GOLDEN_TEXTURED}")
    assert GOLDEN_TEXTURED.is_file(), f"golden fixture missing: {GOLDEN_TEXTURED}"
    want = _rgb(GOLDEN_TEXTURED)
    if got != want:
        diff = sum(1 for a, b in zip(got, want) if a != b) + abs(len(got) - len(want))
        pytest.fail(f"--faces textured cube diverged from its golden: {diff} bytes")


# ── `--faces textured`: what dispatch resolves and refuses ─────────────────────────────────────
# The real CLI path over `--from-t3d`, so exit codes and messages are the ones a user sees. The
# texture resolver is the mockable `resources.texture_resolver` seam; the mover index is autouse-stubbed.

def _utx(tmp_path, stem="Fix", name="T", **kw):
    """A synthesized `<stem>.utx` with an 8x8 texture named `name` — the STEM is the ref stem."""
    from uedcli.tests import pkgfixture
    p = tmp_path / f"{stem}.utx"
    p.write_bytes(pkgfixture.texture_package(name=name, mips=pkgfixture.linear_chain(8, 8), **kw))
    return str(p)


def _patch_resolver(monkeypatch, *paths):
    from uedcli import utexture
    monkeypatch.setattr(resources, "texture_resolver",
                        lambda project: utexture.TextureResolver(list(paths)))


def test_textured_renders_through_the_cli_over_from_t3d(tmp_path, monkeypatch):
    _patch_resolver(monkeypatch, _utx(tmp_path))
    assert _run(tmp_path, [_tbox("Box", ref="Fix.T")], faces="textured", size=96) == 0
    assert (tmp_path / "o.png").is_file()


@pytest.mark.parametrize("layout", ["single", "quad", "breakdown"])
def test_every_layout_renders_under_textured(tmp_path, monkeypatch, layout, capsys):
    _patch_resolver(monkeypatch, _utx(tmp_path))
    assert _run(tmp_path, [_tbox("Box", ref="Fix.T")], faces="textured", layout=layout, size=96) == 0
    capsys.readouterr()


def test_textured_with_explicit_brush_colors_exits_2(tmp_path, monkeypatch, capsys):
    """Decision 2.7. Bare `--faces textured` succeeds; passing `--brush-colors` is a clean exit 2 —
    the flag colours the wireframe/flat fills, and textured draws neither."""
    _patch_resolver(monkeypatch, _utx(tmp_path))
    assert _run(tmp_path, [_tbox("Box", ref="Fix.T")], faces="textured", brush_colors=None,
                size=96) == 0
    capsys.readouterr()
    assert _run(tmp_path, [_tbox("Box", ref="Fix.T")], faces="textured", brush_colors="csg") == 2
    assert "--brush-colors" in capsys.readouterr().err


def test_textured_rejects_scaled_and_sheared_brushes_listing_every_offender(tmp_path, monkeypatch,
                                                                           capsys):
    """§4.2/§8: a positive-determinant scale, a shear and a mirror are ALL refused under textured (the
    UV frame is rotation-only), naming every offender with its field — while `wire` and `flat` render
    them (that scope is pinned elsewhere)."""
    from uedcli.transform import FScale
    _patch_resolver(monkeypatch, _utx(tmp_path))
    scaled = _tbox("Scaled", ref="Fix.T")
    scaled.main_scale = FScale(scale=(Decimal(2), Decimal(3), Decimal(1)))
    sheared = _tbox("Sheared", ref="Fix.T", location=(600.0, 0.0, 0.0))
    sheared.post_scale = FScale(scale=(Decimal(1), Decimal(1), Decimal(1)),
                                sheer_rate=Decimal("0.5"), sheer_axis="SHEER_ZX")
    assert _run(tmp_path, [scaled, sheared], faces="textured") == 2
    err = capsys.readouterr().err
    assert "Scaled" in err and "Sheared" in err and "MainScale" in err and "SheerRate" in err
    # ...but wire and flat still render the same scaled/sheared set.
    assert _run(tmp_path, [scaled, sheared], faces="wire") == 0
    capsys.readouterr()


def test_textured_renders_a_scene_that_references_no_texture(tmp_path, monkeypatch, capsys):
    """Decision 2.6's literal "needs": a generated brush with no `Texture` on any face needs no texture
    source, so it renders (as DEFAULT_GREY) even with NO resolver at all. The class index is still
    required (that is the mover gate, stubbed here)."""
    # No _patch_resolver: the real seam returns None with no games config — and must not be consulted.
    monkeypatch.setattr(resources, "texture_resolver",
                        lambda project: pytest.fail("resolver consulted for a no-texture scene"))
    assert _run(tmp_path, [_tbox("Plain", ref=None)], faces="textured", size=96) == 0
    capsys.readouterr()


def test_textured_refuses_when_a_referenced_texture_has_no_resolver(tmp_path, capsys, tmp_project):
    """A scene that DOES reference a texture and has no resolver exits 2 naming the cause — here, no
    per-user games config (conftest isolates `UEDCLI_HOME`, so the genuine seam returns None)."""
    assert _run(tmp_path, [_tbox("Box", ref="Fix.T")], faces="textured",
                project=str(tmp_project)) == 2
    err = capsys.readouterr().err
    assert "games config" in err and "actor preview --faces textured" in err


def test_the_three_no_resolver_causes_name_distinct_reasons(monkeypatch, tmp_path):
    """§8: no games config, a broken games config, and an empty composed file list are DISTINCT
    messages — all three are reachable WITH a valid project, so a generic "no project" would misname
    two of them."""
    from uedcli import config
    from uedcli.cli import rendering
    verb = "actor preview --faces textured"
    monkeypatch.setattr(config, "load_user_config", lambda: None)
    assert "no per-user games config" in rendering._texture_resolver_cause(object(), verb)

    def boom():
        raise config.ConfigError("bad toml")
    monkeypatch.setattr(config, "load_user_config", boom)
    assert "games config is broken" in rendering._texture_resolver_cause(object(), verb)

    monkeypatch.setattr(config, "load_user_config", lambda: {"games": {}})
    monkeypatch.setattr(config, "composed_search_files", lambda project, uc: [])
    assert "resolves no game packages" in rendering._texture_resolver_cause(object(), verb)


def test_textured_lists_every_unreadable_ref_with_its_case(tmp_path, monkeypatch, capsys):
    """§8: unreadable/bare/undecodable refs exit 2 listing EVERY offender (not just the first) with the
    decoder's case, and a BARE ref's message says to qualify it as `Package.Name`."""
    _patch_resolver(monkeypatch)                               # an EMPTY search path: every ref misses
    good = _tbox("A", ref="NoSuchPackage.Tex")                 # a qualified miss → unknown-package
    bare = _tbox("B", ref="BareName")                          # unqualified → the qualify hint
    assert _run(tmp_path, [good, bare], faces="textured") == 2
    err = capsys.readouterr().err
    assert "NoSuchPackage.Tex" in err and "BareName" in err
    assert "unknown-package" in err and "unqualified-ref" in err
    assert "Package.Name" in err


# -- masking is resolved in dispatch (§4.3a) -----------------------------------------------------

def _preview_textures(actors, monkeypatch, tmp_path, *paths):
    from uedcli.cli import rendering
    _patch_resolver(monkeypatch, *paths)
    args = _preview_args(tmp_path / "o.png", faces="textured")
    return rendering.preview_textures(actors, args)


def test_actor_level_polyflags_2_masks_even_when_the_polys_are_clean(tmp_path, monkeypatch):
    """§4.3a's actor OR: a brush authored `PolyFlags=2` masks in the engine and in --native, so it must
    here too, even though its polys carry no flag and the texture is untagged."""
    box = make_brush_actor("Masked", cube(128.0, 128.0, 128.0, texture="Fix.T"), csg="add",
                           poly_flags=preview.PF_MASKED)
    td = _preview_textures([box], monkeypatch, tmp_path, _utx(tmp_path))
    assert all(td.masked[("Masked", i)] for i in range(6))


def test_a_clean_brush_over_an_untagged_texture_is_not_masked(tmp_path, monkeypatch):
    """The control for the row above and for bMasked below: no poly flag, no actor flag, no tag ⇒ not
    masked, so index 0 draws as an ordinary colour."""
    box = _tbox("Clean", ref="Fix.T")
    td = _preview_textures([box], monkeypatch, tmp_path, _utx(tmp_path))
    assert not any(td.masked[("Clean", i)] for i in range(6))


def test_a_bmasked_fixture_texture_masks_via_the_decoder(tmp_path, monkeypatch):
    """§4.3a's texture arm: a synthesized package carrying `bMasked` masks the face through the
    decoder's typed result, with clean polys and no actor flag — the arm neither committed fixture nor
    the gitignored corpus can otherwise exercise."""
    box = _tbox("Deco", ref="MaskFix.T")
    td = _preview_textures([box], monkeypatch, tmp_path,
                           _utx(tmp_path, stem="MaskFix", bmasked=True))
    assert all(td.masked[("Deco", i)] for i in range(6))


# ── addressable grid: the hidden-actor flag (drew-nothing per pane) ─────────────────────────────

def test_grid_flags_a_fully_occluded_actor_hidden_but_wire_never_does():
    # A tiny add sealed inside a big solid add draws NO pixel under flat (every face depth-hidden) →
    # the grid flags it hidden, yet still gives it a cell from its projected centroid. Under wire
    # nothing is ever culled or depth-hidden, so the same actor is never hidden.
    from uedcli.builders import cube, make_brush_actor
    big = make_brush_actor("Big", cube(256, 256, 256), location=(0, 0, 0), csg="add")
    tiny = make_brush_actor("Tiny", cube(24, 24, 24), location=(0, 0, 0), csg="add")
    flat_cells: dict = {}
    render_brushes_pgm([big, tiny], view="iso", size=256, color_by_csg=True,
                       render_data=_flat(), faces="flat", grid=12, cells_out=flat_cells)
    assert flat_cells["Tiny"].hidden is True
    assert flat_cells["Big"].hidden is False
    assert flat_cells["Tiny"].cell                      # a cell regardless of drawing nothing
    wire_cells: dict = {}
    render_brushes_pgm([big, tiny], view="iso", size=256, color_by_csg=True, grid=12,
                       cells_out=wire_cells)
    assert wire_cells["Tiny"].hidden is False
    assert wire_cells["Big"].hidden is False
