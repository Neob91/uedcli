"""`actor preview --faces` behaviour: the `wire` byte-identity golden, the texel rasterizer, and the
`textured` = CSG-solved-world path (backface cull, decal-once, guards, the parity golden).

**The wire golden pair is the primary regression guard for the wireframe.** Re-bless only after
deciding the wireframe itself should change: `UEDCLI_BLESS_GOLDEN=1 bin/test -k wire_golden`.
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
# vertices) plus two point actors — so one scene covers the CSG palette,
# on-face decals and the point layer. Its LevelInfo0 carries no Location and so sits at the world
# origin, thousands of units from the geometry; the explicit `--frame` AABB (the brushes' own extent)
# keeps the framing on the brushes instead of collapsing them to a corner.
GOLDEN_SCENE = FIXTURES / "level_small.t3d"
GOLDEN_REGION = "5184,4896,-2688,7713,7169,-1728"
GOLDEN_ISO = FIXTURES / "preview_wire_golden_iso.png"
GOLDEN_QUAD = FIXTURES / "preview_wire_golden_quad.png"


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


# ── scene helpers ─────────────────────────────────────────────────────────────────────────────
# Every renderer-level test below drives `render_brushes_pgm` directly with a hand-built
# `PreviewData`, so the CULL and the RASTERIZER are asserted without a project, a games config or a
# class index. The dispatch-level section further down covers what dispatch resolves.

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


def _solved(actors, by_ref=None, masked=None, movers=(), index=None):
    """`PreviewData` for a `--faces textured` render: the REAL CSG solve over `actors` (so an add not
    inside subtracted space leaves no surface), plus the decoded texture payload dispatch would resolve."""
    from uedcli import preview_native as pn
    idx = index or StubClassIndex()
    return PreviewData(faces=FaceData(movers=frozenset(movers),
                                      textures=TextureData(by_ref=by_ref or {}, masked=masked or {}),
                                      solved=pn.solve_world_surfaces(actors, idx)))


def _geom(actors, *, faces="wire", view="iso", color_by_csg=True, brush_colors="csg",
          highlight_polys=(), annotations=None, focus=None, movers=(), by_ref=None, masked=None):
    """`_SceneGeom` for these actors — the seam the backface cull, the fill/texture roles and the decal
    grouping are decided at, so a claim about WHICH surfaces survive is asserted there, not inferred."""
    data = (_solved(actors, by_ref, masked, movers) if faces == "textured" else PreviewData())
    return _scene_geometry(actors, view=view, iso_angle=30.0,
                           annotations=annotations or AnnotationSpec.none(),
                           highlight_polys=set(highlight_polys),
                           focus_cf=focus.casefold() if focus else None,
                           hybrid=color_by_csg, tints=assign_tints(actors),
                           color_by_csg=color_by_csg, render_data=data, brush_colors=brush_colors,
                           faces=faces)


# ── the flag surface ──────────────────────────────────────────────────────────────────────────

@pytest.mark.parametrize("argv", [
    ["actor", "preview", "A"],
    ["stash", "preview", "someid"],
    ["prefab", "preview", "somename"],
])
def test_faces_parses_on_all_three_preview_verbs(argv):
    """One flag, added once to the shared `_preview_opts`, so all three preview verbs carry it. Two
    choices only — `wire` (default) and `textured`; `flat` is gone (no back-compat alias)."""
    p = cli.build_parser()
    assert p.parse_args(argv).faces == "wire"                      # default
    assert p.parse_args(argv + ["--faces", "textured"]).faces == "textured"
    with pytest.raises(SystemExit):
        p.parse_args(argv + ["--faces", "flat"])                   # deleted outright


def test_an_unknown_faces_value_is_a_clean_exit_2_naming_it(capsys):
    """The two choices are `wire`/`textured`; anything else is argparse's own choice error, exit 2
    naming the bad value — no bespoke refusal branch."""
    with pytest.raises(SystemExit) as e:
        cli.build_parser().parse_args(["actor", "preview", "A", "--faces", "shaded"])
    assert e.value.code == 2
    assert "shaded" in capsys.readouterr().err


def test_faces_help_describes_textured():
    """`-h` and the docs must agree the moment `textured` is a choice."""
    actions = {a.dest: (a.help or "") for a in cli.build_parser()._subparsers._group_actions[0]
               .choices["actor"]._subparsers._group_actions[0].choices["preview"]._actions}
    assert "textured" in actions["faces"] and "UV frame" in actions["faces"]


# ── the subtract cull, and what escapes it ────────────────────────────────────────────────────

# ── the edge rule, and the decal grading it changes ───────────────────────────────────────────

# ── the rasterizer ────────────────────────────────────────────────────────────────────────────

def _u_shape(name="Ell"):
    """A single CONCAVE face (a U in the XY plane, wound CCW seen from +Z), whose notch a triangle-fan
    rasterizer fills and an even-odd scanline one does not. The ring starts at a vertex the notch is NOT
    visible from, which is what makes a fan bleed."""
    ring = [(0, 0), (300, 0), (300, 300), (200, 300), (200, 100), (100, 100), (100, 300), (0, 300)]
    poly = Polygon(vertices=[(Decimal(x), Decimal(y), Decimal(0)) for x, y in ring])
    return Actor(name=name, cls="Engine.Brush", brush=Brush(model_name="M", polys=[poly]),
                 location=(Decimal(0), Decimal(0), Decimal(0)))


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

# ── the point layer survives an opaque fill ───────────────────────────────────────────────────

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


# ── mirrored brushes RENDER, correctly (owner ruling) ──────────────────────────────────────────
def test_wire_still_renders_when_the_class_hierarchy_cannot_load(tmp_path, capsys):
    """Decision 2.13's cost, in BOTH directions: the filled modes need the game's class hierarchy and
    refuse without it, and `wire` — the default — needs nothing and is untouched. With no per-user games
    config there is no resolver at all, which is the real seam, not the stub."""
    scene = [_room(), _box("Crate")]
    assert _run(tmp_path, scene, faces="wire") == 0
    capsys.readouterr()


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
        render_brushes_pgm([_box("Add")], size=32, render_data=PreviewData(), faces="textured")
    assert "mover set" in str(e.value)


def test_an_unrenderable_size_becomes_a_clean_exit_2_through_dispatch(tmp_path, monkeypatch, capsys):
    """`preview.py` raises `PreviewAbort` for what it can only discover mid-render; dispatch maps it to
    exit 2. Never a `MemoryError` traceback out of the CLI."""
    def boom(size):
        raise MemoryError
    monkeypatch.setattr(preview, "_new_buf", boom)
    assert _run(tmp_path, [_box("Crate")], faces="wire", layout="single", size=4096) == 2
    assert "--size 4096" in capsys.readouterr().err


def test_wire_keeps_the_vivid_highlight_hue_untouched():
    """`wire` fills nothing; its highlight is the brush's vivid CSG hue, and its edge pair is the
    (front, back) shade — both guarded by the byte-identity golden too."""
    geom = _geom([_box("Add")], faces="wire", highlight_polys={("Add", 1)})
    assert {rgb for _e, rgb, _k in geom.hi_edges} == {ADD_F}
    assert geom.fills == []
    assert {(e[2], e[3]) for e in geom.edges} == {(ADD_F, ADD_B)}


# ── a filled render only needs a class index when there is something to classify ────────────────

# ── the stderr note for a highlight that lands on nothing visible ──────────────────────────────
# A highlight can now legitimately do nothing (a hidden face draws nothing at all), so the CLI says so —
# on stderr, never stdout, and never as a refusal: the render is correct.

def _hi_note(capsys) -> str:
    out = capsys.readouterr()
    assert "note: --highlight" not in out.out, "the note must never reach stdout — it would enter a pipe"
    return "".join(ln for ln in out.err.splitlines(keepends=True) if ln.startswith("note: --highlight"))


def _sheet(name, at=(0.0, 0.0, 0.0)):
    """A ONE-face brush. Used wherever a test needs a face that is visible for certain: a closed cube
    self-occludes, so three of its six faces are hidden in any view and `Cube:0` is not reliably visible."""
    from uedcli.builders import sheet
    return make_brush_actor(name, sheet(256.0, 256.0, plane="xy"), location=at, csg="add",
                            poly_flags=preview.PF_NOTSOLID)


def test_the_note_fires_when_FRAMING_and_not_depth_drew_nothing(tmp_path, capsys):
    """A highlight clipped entirely outside the frame draws nothing, and the note is about "did my flag
    take?", not about depth — so it must fire here too. `--frame <one brush> --highlight <another>` is an
    ordinary workflow.

    This was silent because `shown_highlights` recorded the `_line` CALL rather than a landed pixel;
    `_line` now returns how many it plotted. Asserted under BOTH modes, since framing clips in `wire` too
    and nothing about it is depth-related."""
    near = _box("Near", size=256.0, height=256.0)
    far = _box("Far", size=256.0, height=256.0, at=(20000.0, 20000.0, 0.0))
    for faces in ("wire",):
        assert _run(tmp_path, [near, far], faces=faces, view="top", size=200,
                    frame="Near", highlight=["Far:0"]) == 0
        note = _hi_note(capsys)
        assert "Far:0" in note, f"{faces}: a highlight clipped outside the frame went unreported"
    # ...and a highlight INSIDE the frame is still silent, so the new test is not just always-on.
    assert _run(tmp_path, [near, far], faces="wire", view="top", size=200,
                frame="Near", highlight=["Near:0"]) == 0
    assert _hi_note(capsys) == ""


def test_a_highlight_that_lands_says_nothing(tmp_path, capsys):
    """The negative case, which is what makes the note worth anything: a visible highlighted face must not
    produce a note, or the note becomes noise the reader learns to skip."""
    assert _run(tmp_path, [_sheet("Solo")], faces="wire", size=200, highlight=["Solo:0"]) == 0
    assert _hi_note(capsys) == ""


def test_the_note_does_not_fire_under_wire_for_an_OCCLUDED_face(tmp_path, capsys):
    """`wire` hides nothing by depth — `vis_faces` is empty there, so no face is ever in the hidden set —
    so a highlight that `flat` would report as invisible is silent under `wire`.

    **Deliberately not named "cannot fire".** It is not structurally unreachable: a poly with no
    projectable vertices is dropped before the edge loop in EITHER mode, so a degenerate `--from-t3d` poly
    trips the note under `wire` too. Reporting that is correct — what was wrong was claiming exemption."""
    shell, core = _box("Shell", size=600.0, height=600.0), _box("Core", size=120.0, height=120.0)
    assert _run(tmp_path, [shell, core], faces="wire", size=200, highlight=["Core:0"]) == 0
    assert _hi_note(capsys) == ""


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


# ── the coverage rule ──────────────────────────────────────────────────────────────────────────

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


def _tbox(name="Room", ref="Fix.T", **kw):
    """A SUBTRACT room whose every interior face carries `ref` (None = no texture). The CSG solve keeps
    its interior walls, so `--faces textured` has surviving textured surfaces to draw — an isolated ADD
    would leave none."""
    kw.setdefault("csg", "subtract")
    return make_brush_actor(name, cube(512.0, 512.0, 512.0, texture=ref), **kw)


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


# -- no texture, and non-finite frames (§4.3) ----------------------------------------------------

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
    pts = [preview._project(p, "iso", 80.0) for f in (wall, floor) for p in f]
    _s, _tp, _to, w2p, _b = _framing(pts, None, 256, "iso", 80.0, pad=_FRAME_PAD)

    def level(v3, frame):
        (au, bu, _c1), (av, bv, _c2) = _face_uv_affine(v3, frame, w2p)
        return _mip_level(au, bu, av, bv, 10)

    assert level(wall, wall_frame) != level(floor, floor_frame)


# -- textured draws NO wireframe (decision 2.5) -------------------------------------------------

# -- the golden ----------------------------------------------------------------------------------



def _checker_mip(w, h):
    """A 2-colour checker mip so the golden shows tiling, UV orientation and per-face shade at once."""
    px = bytearray()
    for y in range(h):
        for x in range(w):
            px += bytes((200, 60, 60) if (x // 2 + y // 2) % 2 else (60, 60, 200))
    return (w, h, bytes(px), bytes([1]) * (w * h))


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
    bare = _tbox("B", ref="BareName", location=(4000.0, 0.0, 0.0))  # apart, so both rooms survive
    assert _run(tmp_path, [good, bare], faces="textured") == 2
    err = capsys.readouterr().err
    assert "NoSuchPackage.Tex" in err and "BareName" in err
    assert "unknown-package" in err and "unqualified-ref" in err
    assert "Package.Name" in err


# -- masking is resolved in dispatch (§4.3a) -----------------------------------------------------

def _preview_textures(actors, monkeypatch, tmp_path, *paths):
    from uedcli.cli import rendering
    from uedcli import preview_native as pn
    _patch_resolver(monkeypatch, *paths)
    args = _preview_args(tmp_path / "o.png", faces="textured")
    solved = pn.solve_world_surfaces(actors, StubClassIndex())
    return rendering.preview_textures(actors, args, solved)


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


# ── locator cells: the hidden-actor flag (drew-nothing per pane) ────────────────────────────────



# ── `--faces textured` = the CSG-solved world (the parity path) ─────────────────────────────────
# `textured` no longer draws each brush's own faces; it runs the native CSG solve and draws only the
# surfaces that SURVIVE, with a per-view backface cull. These pin the parity claims: a room shows its
# interior (not a solid box), a buried add is invisible, a split poly is one texture and one label.

from uedcli.preview_native import solve_world_surfaces        # noqa: E402
from uedcli.texframe import world_uv_frame                    # noqa: E402

_IDX = StubClassIndex()


def _solve(actors):
    return solve_world_surfaces(actors, _IDX)


def test_backface_cull_keeps_far_interior_walls_and_drops_the_near_ones():
    """The core parity result. A subtracted 6-wall room solves to 6 interior surfaces; the per-view
    backface cull keeps the 3 whose post-CSG normal faces the camera (the FAR interior walls) and drops
    the 3 near ones — so the render shows the room INTERIOR, not a solid box. Zero would be a black hole;
    six would be the solid box."""
    geom = _geom([_room("Room")], faces="textured", view="iso")
    assert len(geom.fills) == 3          # 3 far walls kept, 3 camera-facing-away near walls culled
    assert geom.tex_faces and len(geom.tex_faces) == len(geom.fills)   # index-aligned


def test_a_buried_add_contributes_no_surface_while_the_room_interior_does():
    """Containment, not a per-brush rule: an add INSIDE the subtracted room survives where it borders
    empty; an add BURIED in solid space (outside any subtraction) leaves nothing at all."""
    room = _room("Room", size=1024.0, height=1024.0)
    inside = _box("Inside", size=256.0, at=(0.0, 0.0, -256.0))
    buried = _box("Buried", size=128.0, at=(4000.0, 0.0, 0.0))
    names = {s.actor.name for s in _solve([room, inside, buried]).world_surfaces if s.actor}
    assert names == {"Room", "Inside"}          # Buried absent


def test_one_source_poly_split_into_many_fragments_gets_ONE_index_label():
    """CSG splits one wall into several fragments (an alcove poking through it); the index decal draws
    ONCE per (actor, source poly), on the largest fragment — not once per fragment."""
    room = _room("Room", size=1024.0, height=1024.0)
    alcove = make_brush_actor("Alcove", cube(400.0, 400.0, 400.0), location=(700.0, 0.0, 0.0),
                              csg="subtract")
    frags = [s for s in _solve([room, alcove]).world_surfaces if s.actor and s.actor.name == "Room"
             and s.poly_index == 0]
    assert len(frags) > 1, "the wall did not split — pick a scene that splits it"
    geom = _geom([room, alcove], faces="textured", annotations=AnnotationSpec.all())
    labels = [t for _c, t, _a, _d, _v, n in geom.poly_labels if n == "Room" and t == "0"]
    assert labels == ["0"]               # exactly one label for the split poly


def test_a_split_wall_keeps_one_authored_uv_frame_across_every_fragment():
    """Texture alignment survives a BSP split: every fragment of one source poly draws through that
    poly's SINGLE authored UV frame, so the texture stays continuous across the cut."""
    room = _room("Room", size=1024.0, height=1024.0)
    alcove = make_brush_actor("Alcove", cube(400.0, 400.0, 400.0), location=(700.0, 0.0, 0.0),
                              csg="subtract")
    frags = [s for s in _solve([room, alcove]).world_surfaces if s.actor and s.actor.name == "Room"
             and s.poly_index == 0]
    frames = {world_uv_frame(s.actor, s.actor.brush.polys[s.poly_index]) for s in frags}
    assert len(frags) > 1 and len(frames) == 1    # many fragments, ONE shared frame


def test_a_surviving_surface_with_no_texture_renders_grey():
    """A solved surface whose source poly has no `Texture` fills DEFAULT_GREY × shade — a neutral grey,
    not an error (the most common textured render in practice)."""
    room = _room("Room")
    ppm = render_brushes_pgm([room], view="iso", size=96, annotations=AnnotationSpec.none(),
                             color_by_csg=True, render_data=_solved([room]), faces="textured")
    fills = [px for px in _pixels(ppm) if px != (BG, BG, BG)]
    assert fills, "the room interior drew nothing"
    assert all(r == g == b and 0 < r <= DEFAULT_GREY[0] for r, g, b in fills)


def test_textured_draws_no_wireframe():
    """Decision 2.5: `textured` keeps NO CSG wireframe — only fills (and `--highlight` outlines). A
    subtract room's gold CSG wire hue must not appear."""
    room = _room("Room")
    ppm = render_brushes_pgm([room], view="iso", size=96, annotations=AnnotationSpec.none(),
                             color_by_csg=True, render_data=_solved([room]), faces="textured")
    cols = _colors(ppm)
    assert SUB_F not in cols and SUB_B not in cols, "a CSG wireframe edge leaked into textured"


def test_a_highlight_outline_is_the_only_line_art_textured_keeps():
    """§5: a highlighted surviving face keeps its (grey) fill AND takes the vivid CSG outline — the only
    line art `textured` draws."""
    room = _room("Room")
    hi = {("Room", i) for i in range(6)}
    ppm = render_brushes_pgm([room], view="iso", size=96, annotations=AnnotationSpec.none(),
                             color_by_csg=True, render_data=_solved([room]), faces="textured",
                             highlight_polys=hi)
    cols = _colors(ppm)
    assert SUB_F in cols                                # the vivid highlight outline drew
    assert any(r == g == b and 0 < r for r, g, b in cols)   # ...and the grey fill is still there


@pytest.mark.parametrize("bad", [float("inf"), float("nan")])
def test_a_non_finite_uv_frame_on_a_surviving_surface_refuses(bad):
    """A corrupt authored frame (`inf`/`nan`, reachable via `--from-t3d`) on a SURVIVING surface is a
    clean `PreviewAbort` naming the actor and poly — never a silent grey fallback."""
    room = _room("Room")
    for poly in room.brush.polys:
        poly.texture_u = (bad, 0.0, 0.0)
    with pytest.raises(PreviewAbort) as e:
        render_brushes_pgm([room], view="iso", size=48, annotations=AnnotationSpec.none(),
                           color_by_csg=True, render_data=_solved([room]), faces="textured")
    assert "Room" in str(e.value) and "poly" in str(e.value)


def test_a_mover_draws_as_a_filled_magenta_overlay():
    """A mover is excluded from world CSG and drawn filled in the mover hue against the shared depth
    buffer (no wireframe)."""
    room = _room("Room", size=1024.0, height=1024.0)
    door = make_brush_actor("Door", cube(128.0, 400.0, 400.0), location=(0.0, 0.0, -300.0),
                            mover_class="Engine.Mover")
    geom = _geom([room, door], faces="textured", movers=["Door"])
    assert any(rgb == MOVER_F for _v3, _vs, rgb, _d in geom.fills)   # mover magenta fill present


# -- the pre-solve guards (§B4) + texture-after-solve (§M2) --------------------------------------

def test_a_real_brush_set_that_solves_to_zero_surfaces_exits_2(tmp_path, capsys):
    """A set of world brushes that leaves NO surviving surface — here a subtract fully filled back by an
    add of the same size and place — exits 2 naming the cause rather than writing a blank frame. (The
    `build_geometry_bspcsg` core starts from an EMPTY world, so an adds-only set renders instead; see
    board item `actor-preview-bspcsg-starts-from-an-empty-world`.)"""
    room = make_brush_actor("Room", cube(512.0, 512.0, 512.0), csg="subtract")
    fill = make_brush_actor("Fill", cube(512.0, 512.0, 512.0), csg="add")
    assert not _solve([room, fill]).world_surfaces          # precondition: zero surviving surfaces
    assert _run(tmp_path, [room, fill], faces="textured") == 2
    assert "nothing survives" in capsys.readouterr().err


def test_a_mover_only_set_draws_its_overlay_over_black_at_exit_0(tmp_path, capsys):
    """No WORLD-CSG brush (only a mover) is NOT the zero-surface error: the solved world is legitimately
    empty and the mover overlay draws over black at exit 0."""
    door = make_brush_actor("Door", cube(128.0, 128.0, 256.0), mover_class="Engine.Mover")
    assert _run(tmp_path, [door], faces="textured") == 0
    assert (tmp_path / "o.png").is_file()
    capsys.readouterr()


def test_an_unreadable_texture_on_a_CULLED_face_does_not_refuse_but_on_a_SURVIVING_one_does(
        tmp_path, monkeypatch, capsys):
    """§M2: texture resolution follows the solve. A buried add's unreadable texture is never drawn, so it
    must NOT block the render; the same unreadable ref on a surviving room wall DOES refuse."""
    _patch_resolver(monkeypatch, _utx(tmp_path))               # only Fix.T resolves
    room = _tbox("Room", ref="Fix.T")                          # subtract room, surviving, readable
    buried = _box("Buried", at=(6000.0, 0.0, 0.0))             # add, buried → no surface
    for p in buried.brush.polys:
        p.texture = "NoSuchPackage.Missing"                    # unreadable, but never drawn
    assert _run(tmp_path, [room, buried], faces="textured", size=96) == 0
    capsys.readouterr()
    # ...but the same unreadable ref on the SURVIVING room refuses.
    bad_room = _tbox("BadRoom", ref="NoSuchPackage.Missing")
    assert _run(tmp_path, [bad_room], faces="textured") == 2
    assert "NoSuchPackage.Missing" in capsys.readouterr().err


# -- the overlapping-subtract doorway (proves the bspcsg core) -----------------------------------

def test_two_overlapping_subtracts_merge_into_one_open_cavity():
    """Two overlapping subtract rooms share an opening: the internal facing walls between them are
    removed (fewer than two separate rooms' 12 surfaces), so the doorway shows through — the geometry the
    DEFAULT core mis-renders and the bspcsg core (which the solve routes through) gets right."""
    r1 = make_brush_actor("R1", cube(512.0, 512.0, 512.0), location=(0.0, 0.0, 0.0), csg="subtract")
    r2 = make_brush_actor("R2", cube(512.0, 512.0, 512.0), location=(384.0, 0.0, 0.0), csg="subtract")
    surfaces = _solve([r1, r2]).world_surfaces
    assert 0 < len(surfaces) < 12          # merged: the shared opening carries no wall


# -- the parity world golden --------------------------------------------------------------------

GOLDEN_WORLD = FIXTURES / "preview_textured_world_golden_iso.png"


def test_textured_world_golden(tmp_path):
    """End-to-end pixel stability of the SOLVED textured world: a checker-textured room with an add
    inside, so the golden shows the interior (near walls culled), the add bordering empty, texture
    alignment and per-face shade at once. Bless with `UEDCLI_BLESS_GOLDEN=1 bin/test -k world_golden`."""
    room = _room("Room", size=1024.0, height=1024.0)
    add = _box("Add", size=256.0, at=(0.0, 0.0, -320.0))
    for a in (room, add):
        for p in a.brush.polys:
            p.texture = "Fix.T"
    by_ref = {"fix.t": [_checker_mip(16, 16)]}
    solved = _solved([room, add], by_ref=by_ref,
                     masked={(a.name, i): False for a in (room, add) for i in range(6)})
    ppm = render_brushes_pgm([room, add], view="iso", size=160, annotations=AnnotationSpec.none(),
                             color_by_csg=True, render_data=solved, faces="textured")
    from io import BytesIO
    from PIL import Image
    out = tmp_path / "world.png"
    Image.open(BytesIO(ppm)).convert("RGB").save(out)
    got = _rgb(out)
    if os.environ.get("UEDCLI_BLESS_GOLDEN"):
        Image.open(out).convert("RGB").save(GOLDEN_WORLD)
        pytest.skip(f"golden blessed → {GOLDEN_WORLD}")
    assert GOLDEN_WORLD.is_file(), f"golden fixture missing: {GOLDEN_WORLD}"
    want = _rgb(GOLDEN_WORLD)
    if got != want:
        diff = sum(1 for a, b in zip(got, want) if a != b) + abs(len(got) - len(want))
        pytest.fail(f"--faces textured world diverged from its golden: {diff} bytes")
