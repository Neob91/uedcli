"""The world gridline overlay (`--grid-size`) — a port of UnrealEd's `DrawGridSection`. Spec
`dev/docs/board/to-plan/add-visual-grid-for-2d-views-in-level-actor/spec.md` §9 lists the cases;
this file follows that list section by section."""
import os
from decimal import Decimal
from io import BytesIO
from pathlib import Path
from types import SimpleNamespace

import pytest

from uedcli import trunk
from uedcli.builders import cube, make_brush_actor
from uedcli.cli import dispatch
from uedcli.cli import main as cli
from uedcli.model import Actor, Level
from uedcli.preview import (
    BG, CAPTION, _FRAME_PAD, _GRID_BASE, _GRID_TARGET, _GRID_WORLD_CLAMP,
    AnnotationSpec, FaceData, PointRender, PreviewData, TextureData,
    _auto_grid_step, _framing, _fmt_grid_num, _grid_caption_text, _grid_escalation,
    _grid_indices, _grid_line_color,
    render_brush_pgm, render_brushes_pgm, render_quad_pgm,
)
from uedcli.tests.conftest import StubClassIndex

FIXTURES = Path(__file__).parent / "fixtures"
GOLDEN_GRID = FIXTURES / "preview_grid_golden.png"

_GRID_MINOR = tuple(round(_GRID_BASE[k] + (_GRID_TARGET[k] - _GRID_BASE[k]) * 0.5) for k in range(3))
_GRID_MAJOR = _GRID_TARGET
_GRID_COLORS = (_GRID_MINOR, _GRID_MAJOR)


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


def _brush(name="B", size=512.0, at=(0.0, 0.0, 0.0), csg="add"):
    return make_brush_actor(name, cube(size, size, size), location=at, csg=csg)


def _room(name="Room", size=512.0, height=256.0):
    return make_brush_actor(name, cube(size, size, height), csg="subtract")


def _solved(actors):
    from uedcli import preview_native as pn
    return PreviewData(faces=FaceData(movers=frozenset(),
                                      textures=TextureData(by_ref={}, masked={}),
                                      solved=pn.solve_world_surfaces(actors, StubClassIndex())))


# ── §3.1 — the escalation arithmetic, hand-verified against the pseudocode ──────────────────────

@pytest.mark.parametrize("width_px,world_per_px,step,expect", [
    (100, 1.0, 50, (0, 50, 1.0)),        # 2*count(4) < limit(25): the density gate never opens
    (100, 1.0, 5,  (0, 5, 0.4)),         # gate opens but no escalation needed (count already < limit)
    (130, 1.0, 1,  (3, 8, 0.984375)),    # gate opens AND escalates; a non-trivial fade
    (1000, 1.0, 1, (3, 8, 1.0)),         # gate opens AND escalates; fade lands exactly on 1.0
])
def test_grid_escalation_matches_the_ported_arithmetic(width_px, world_per_px, step, expect):
    shift, drawn, fade = _grid_escalation(width_px, world_per_px, step)
    exp_shift, exp_drawn, exp_fade = expect
    assert (shift, drawn) == (exp_shift, exp_drawn)
    assert fade == pytest.approx(exp_fade)


def test_escalation_guards_a_pane_narrower_than_the_4px_threshold():
    # `limit = width_px // 4` would be 0 below 4px, and the ported loop's own exit condition
    # (`(count >> shift) >= limit`) can then never fire (0 >= 0 forever) — guarded, not escalated.
    # No real render reaches this (`_framing`'s `draw = max(1, ...)`), but the arithmetic must not hang.
    assert _grid_escalation(3, 1.0, 1) == (0, 1, 1.0)


# ── §3.2 — the fade touches only ODD lines ───────────────────────────────────────────────────

def test_fade_touches_only_odd_lines():
    # shift=0 keeps the major/minor split clean (major <=> `i` a multiple of 8, so always EVEN — the
    # "majors never fade" claim only reads simply there; §3.2 note below) and the density gate open
    # with a big fade delta, so a rounded odd-line colour is visibly different from its unfaded tier.
    shift, drawn, fade = _grid_escalation(100, 1.0, 5)      # (0, 5, 0.4)
    assert fade != 1.0
    for i in range(-4, 20):
        tier = 0.5 if ((i << shift) & 7) else 1.0
        unfaded = tuple(round(_GRID_BASE[k] + (_GRID_TARGET[k] - _GRID_BASE[k]) * tier) for k in range(3))
        got = _grid_line_color(i, shift, fade)
        if i % 2 == 0:
            assert got == unfaded, f"even line {i} must not fade"
        else:
            faded = tuple(round(_GRID_BASE[k] + (unfaded[k] - _GRID_BASE[k]) * fade) for k in range(3))
            assert got == faded, f"odd line {i} must fade toward BASE by `fade`"
            assert got != unfaded, f"odd line {i} faded to the same colour — fade had no effect"


def test_fade_is_exactly_1_when_the_density_gate_is_not_crossed():
    shift, drawn, fade = _grid_escalation(100, 1.0, 50)     # 2*count < limit: gate never opens
    assert fade == 1.0
    for i in (1, 3, 5):                                     # odd lines: fade=1.0 is a no-op
        tier = 0.5 if ((i << shift) & 7) else 1.0
        unfaded = tuple(round(_GRID_BASE[k] + (_GRID_TARGET[k] - _GRID_BASE[k]) * tier) for k in range(3))
        assert _grid_line_color(i, shift, fade) == unfaded


# ── §3.2 — tier assignment, and majors pinned across two zooms ──────────────────────────────────

def test_tier_selects_the_lerp_endpoint():
    shift, fade = 0, 1.0
    for i in (0, 8, -8, 16):                                # every 8th (unescalated) line is major
        assert _grid_line_color(i, shift, fade) == _GRID_TARGET
    for i in (1, 2, 3, 4, 5, 6, 7):
        assert _grid_line_color(i, shift, fade) == _GRID_MINOR


def test_majors_are_pinned_to_multiples_of_8x_drawn_across_two_zooms():
    """`((i << shift) & 7) == 0` lines are major, and — the property the `<< shift` in the ported
    formula exists to preserve — that is exactly the world multiples of `8 * drawn`, independently of
    which (unescalated) zoom `drawn` came from."""
    for step in (4, 64):                                    # two zooms; world_per_px small enough
        shift, drawn, _fade = _grid_escalation(2000, 0.1, step)     # that neither escalates
        assert (shift, drawn) == (0, step)
        for i in range(-20, 20):
            world = (i << shift) * step
            is_major = ((i << shift) & 7) == 0
            assert is_major == (world % (8 * drawn) == 0)


# ── §3.1 — the world clamp ───────────────────────────────────────────────────────────────────

def test_world_clamp_bounds_the_index_range_regardless_of_the_visible_span():
    r = _grid_indices(1, 0, -1_000_000.0, 1_000_000.0)
    assert r.start == -_GRID_WORLD_CLAMP and r.stop == _GRID_WORLD_CLAMP
    for i in (r.start, r.stop - 1):
        assert -_GRID_WORLD_CLAMP <= i * 1 < _GRID_WORLD_CLAMP


def test_world_clamp_scales_down_by_shift():
    step = 4
    shift, drawn, _fade = _grid_escalation(4000, 1.0, step)         # forces heavy escalation
    r = _grid_indices(step, shift, -1_000_000.0, 1_000_000.0)
    # every drawn world coordinate stays inside +/- the clamp
    for i in (r.start, r.stop - 1):
        world = (i << shift) * step
        assert -_GRID_WORLD_CLAMP <= world < _GRID_WORLD_CLAMP + drawn


# ── §3.3 — the auto step (largest power of two <= span/16, 16-32 divisions at any zoom) ────────
# Superseded the earlier "coarsest power of two that still yields >= 1 line" rule: measured on a
# 7712-uu pane it picked 4096 and drew TWO lines — "at least one line" optimises for the wrong end
# of the range. Spec `add-visual-grid-for-2d-views-in-level-actor.md` §3.3, owner-updated 2026-08-30.

@pytest.mark.parametrize("span,want", [
    (0.5, 1), (15.0, 1),           # sub-16-uu span: floored at 1 (division count can drop below 16)
    (16.0, 1), (64.0, 4), (100.0, 4), (512.0, 32), (7712.0, 256), (65536.0, 4096), (100000.0, 4096),
])
def test_auto_grid_step_is_the_largest_power_of_two_le_span_over_16(span, want):
    assert _auto_grid_step(span) == want


@pytest.mark.parametrize("span", [16.0, 30.0, 64.0, 100.0, 512.0, 4096.0, 7712.0, 65536.0, 100000.0])
def test_auto_grid_step_gives_16_to_32_divisions_across_the_pane(span):
    step = _auto_grid_step(span)
    assert 16 <= span / step < 32


@pytest.mark.parametrize("size", [256, 512, 1024])              # realistic pane pixel sizes
@pytest.mark.parametrize("span", [64.0, 512.0, 4096.0, 7712.0, 100000.0])
def test_auto_step_division_count_holds_at_realistic_pane_sizes(span, size):
    """The default step is chosen from `span` alone; escalation (spec §3.1, a SEPARATE >=4px-per-
    line rule) is not supposed to perturb it on the default path (spec §3.3). Confirmed here at
    realistic `--size` values — a genuinely tiny pane (`--size` far below any real default) can
    still nudge a near-30-division pick past the 4px threshold; that is the other rule's job, not a
    defect in this one, so it is out of scope for this assertion."""
    step = _auto_grid_step(span)
    draw_px = max(1, size - 2 * _FRAME_PAD)
    shift, drawn, _fade = _grid_escalation(draw_px, span / draw_px, step)
    assert shift == 0 and drawn == step
    assert 16 <= span / drawn < 32


# ── §6 — the caption ─────────────────────────────────────────────────────────────────────────

def test_fmt_grid_num_prints_integral_values_as_integers():
    assert _fmt_grid_num(5.0) == "5"
    assert _fmt_grid_num(-1024.0) == "-1024"
    assert _fmt_grid_num(100.5) == "100.5"


def test_grid_caption_text_names_the_panes_own_two_axes():
    # "set"/"visible", never "minor"/"major" (spec §6, owner-updated 2026-08-30 -- see
    # board/inbox/grid-caption-major-8x-drawn-is-imprecise-once for why the major field was dropped).
    assert _grid_caption_text("top", -1024.0, -512.0, 3072.0, 64, 512) == \
        "X -1024..2048  Y -512..2560  grid set 64, visible 512"
    assert _grid_caption_text("front", 0.0, 0.0, 128.0, 16, 128) == \
        "X 0..128  Z 0..128  grid set 16, visible 128"
    assert _grid_caption_text("side", 0.0, 0.0, 100.5, 16, 128) == \
        "Y 0..100.5  Z 0..100.5  grid set 16, visible 128"


def test_visible_equals_set_when_nothing_escalates():
    assert _grid_caption_text("top", 0.0, 0.0, 512.0, 32, 32) == \
        "X 0..512  Y 0..512  grid set 32, visible 32"


def test_visible_differs_from_set_only_once_escalated():
    # step=32 escalating twice (shift=2) -> visible=128
    assert _grid_caption_text("top", 0.0, 0.0, 512.0, 32, 128) == \
        "X 0..512  Y 0..512  grid set 32, visible 128"


def test_too_coarse_step_is_reported_unescalated_in_the_caption():
    # No line lands (§5) -> `drawn == step`, so the caption still names the REQUESTED step, not
    # some escalated substitute (there is none: too coarse never escalates).
    shift, drawn, _fade = _grid_escalation(200, 0.1, 65536)
    assert drawn == 65536


# ── §5 / dispatch — `--grid-size` validation ────────────────────────────────────────────────

def test_grid_size_parses_on_all_three_preview_verbs():
    p = cli.build_parser()
    for argv in (["actor", "diagram", "A"], ["stash", "diagram", "id"], ["prefab", "diagram", "name"]):
        assert p.parse_args(argv).grid_size is None
        assert p.parse_args(argv + ["--grid-size", "64"]).grid_size == 64


def _project_with_brush(tmp_path, monkeypatch, *, size=512.0, name="lvl"):
    proj = tmp_path / "repo"
    (proj / "maps" / name).mkdir(parents=True)
    (proj / "uedcli.toml").write_text('game = "deusex"\n')
    a = _brush(size=size)
    lvl = Level(actors={"B": a}); lvl.order = ["B"]
    trunk.write_level(proj / "maps" / name, lvl, dict(zip(["B"], trunk.initial_ranks(1))))
    monkeypatch.setenv("UEDCLI_LEVEL", name)
    return proj


def _args(proj, out, **kw):
    # `annotate="none"` (no on-face poly-index decals) so a grid-colour presence/absence check is
    # never confused by a decal's own translucent halo blend, which can coincidentally land on the
    # exact same RGB as a grid tier.
    base = dict(cmd="actor", sub="diagram", project=str(proj), names=["B"], from_t3d=None,
                view="top", layout="single", annotate="none", iso_angle=30.0, frame=None,
                frame_tightness=0.8, highlight=None, focus=None, show="", size=128,
                out=str(out), brush_colors="csg", grid_size=None)
    base.update(kw)
    return SimpleNamespace(**base)


def test_grid_size_must_be_a_power_of_two(tmp_path, monkeypatch, capsys):
    proj = _project_with_brush(tmp_path, monkeypatch)
    out = tmp_path / "o.png"
    rc = dispatch.dispatch(_args(proj, out, grid_size=100))
    assert rc == 2
    assert "--grid-size must be a power of two, got 100" in capsys.readouterr().err


@pytest.mark.parametrize("n", [1, 2, 64, 32768])
def test_grid_size_powers_of_two_are_accepted(tmp_path, monkeypatch, n):
    proj = _project_with_brush(tmp_path, monkeypatch)
    out = tmp_path / "o.png"
    assert dispatch.dispatch(_args(proj, out, grid_size=n)) == 0


def test_grid_size_conflicts_with_view_iso_under_single(tmp_path, monkeypatch, capsys):
    proj = _project_with_brush(tmp_path, monkeypatch)
    out = tmp_path / "o.png"
    rc = dispatch.dispatch(_args(proj, out, layout="single", view="iso", grid_size=64))
    assert rc == 2
    err = capsys.readouterr().err
    assert "--grid-size" in err and "iso" in err


def test_grid_size_conflicts_with_view_iso_under_breakdown(tmp_path, monkeypatch, capsys):
    proj = _project_with_brush(tmp_path, monkeypatch)
    out = tmp_path / "o.png"
    rc = dispatch.dispatch(_args(proj, out, layout="breakdown", view="iso", grid_size=64))
    assert rc == 2
    assert "--grid-size" in capsys.readouterr().err


def test_grid_size_with_default_view_under_quad_is_not_a_conflict(tmp_path, monkeypatch):
    # 'quad' ignores --view entirely (it always renders all four panes), so the default --view
    # (iso) must not trip the iso/--grid-size refusal there.
    proj = _project_with_brush(tmp_path, monkeypatch)
    out = tmp_path / "o.png"
    assert dispatch.dispatch(_args(proj, out, layout="quad", view="iso", grid_size=64)) == 0


# ── §2 / §9 "View scoping" ───────────────────────────────────────────────────────────────────

def test_iso_view_draws_no_grid_pixels():
    # `annotations=none()` -- a decal's own translucent halo can coincidentally land on the exact
    # RGB of a grid tier, which would make a plain colour-presence check unreliable.
    a = _brush(size=512.0)
    kw = dict(color_by_csg=True, grid_size=64, locator=None, annotations=AnnotationSpec.none())
    top = render_brush_pgm(a, view="top", size=256, **kw)
    iso = render_brush_pgm(a, view="iso", size=256, **kw)
    assert any(c in _colors(top) for c in _GRID_COLORS)
    assert not any(c in _colors(iso) for c in _GRID_COLORS)


def test_iso_pane_of_quad_carries_no_bbox_caption_the_ortho_panes_do():
    a = _brush(size=512.0)
    cap: dict = {}
    quad = render_quad_pgm(a, size=2048, color_by_csg=True, grid_size=64, locator=None,
                           annotations=AnnotationSpec.none(), captions_out=cap)
    assert any(c in _colors(quad) for c in _GRID_COLORS)   # Top/Front/Side gridded
    assert set(cap) == {"Top", "Front", "Side"}             # never "Iso"


# ── §6 (owner-updated 2026-08-30 — SUPERSEDES an earlier "sometimes drawn" design) ─────────────
# Nothing is ever drawn into the image. Found+fixed: a small `--size` (`quad`'s 128-px panes at
# `--size 256`) let the earlier draft's caption both truncate horizontally AND overwrite up to 30px
# of CSG-coloured geometry with caption grey — the same defect class as a gridline painting over a
# face. The fix removes the in-image draw entirely; stderr (never size-constrained) is the sole
# channel, reporting `set` (requested) vs `visible` (`set << shift`, actually drawn) rather than the
# (measured-wrong-once-escalated) minor/major pair — see `_grid_caption_text`'s docstring.

def test_stderr_reports_set_and_visible_unqualified_under_single(tmp_path, monkeypatch, capsys):
    proj = _project_with_brush(tmp_path, monkeypatch, size=512.0)
    out = tmp_path / "o.png"
    assert dispatch.dispatch(_args(proj, out, view="top", size=1024, grid_size=32,
                                   no_locator_cells=True)) == 0     # isolate the grid report alone
    err = capsys.readouterr().err.strip()
    assert err == "X -256..256  Y -256..256  grid set 32, visible 32"


def test_stderr_reports_set_and_visible_pane_qualified_under_quad(tmp_path, monkeypatch, capsys):
    proj = _project_with_brush(tmp_path, monkeypatch, size=512.0)
    out = tmp_path / "o.png"
    assert dispatch.dispatch(_args(proj, out, layout="quad", size=1024, grid_size=32,
                                   no_locator_cells=True)) == 0
    lines = capsys.readouterr().err.strip().splitlines()
    assert lines == [
        "Top: X -256..256  Y -256..256  grid set 32, visible 32",
        "Front: X -256..256  Z -256..256  grid set 32, visible 32",
        "Side: Y -256..256  Z -256..256  grid set 32, visible 32",
    ]


def test_set_equals_visible_on_a_default_render(tmp_path, monkeypatch, capsys):
    # The auto step (spec §3.3) already clears the density threshold, so a default-path render never
    # escalates -- set == visible always, no explicit --grid-size needed.
    proj = _project_with_brush(tmp_path, monkeypatch, size=512.0)
    out = tmp_path / "o.png"
    assert dispatch.dispatch(_args(proj, out, view="top", size=1024)) == 0
    err = capsys.readouterr().err
    assert "grid set 32, visible 32" in err


def test_set_differs_from_visible_once_a_forced_escalation_happens(tmp_path, monkeypatch, capsys):
    proj = _project_with_brush(tmp_path, monkeypatch, size=512.0)
    out = tmp_path / "o.png"
    # step=1 in a 512-uu pane at only 128px (with the default locator gutter reserved) forces real
    # escalation: draw_px=88, count=int(88*(512/88)/1)=512, limit=88//4=22, escalates to shift=5.
    assert dispatch.dispatch(_args(proj, out, view="top", size=128, grid_size=1)) == 0
    err = capsys.readouterr().err.strip()
    assert err.endswith("grid set 1, visible 32")


@pytest.mark.parametrize("size", [256, 1024])
def test_no_caption_colour_ever_appears_in_a_single_layout_image(tmp_path, monkeypatch, size):
    """The regression guard for the overlap defect: `single` has no other legitimate use of
    `CAPTION`, so its total absence at ANY size proves the (now stderr-only) report never paints."""
    proj = _project_with_brush(tmp_path, monkeypatch, size=512.0)
    out = tmp_path / "o.png"
    assert dispatch.dispatch(_args(proj, out, view="top", size=size, grid_size=32)) == 0
    from PIL import Image
    assert CAPTION not in set(Image.open(out).convert("RGB").getdata())


@pytest.mark.parametrize("size", [256, 1024])
def test_caption_colour_pixels_in_quad_are_independent_of_the_grid(size):
    """`quad`'s Top/Front/Side/Iso pane-NAME labels legitimately use `CAPTION` grey (pre-existing,
    unrelated to the grid), so `quad` cannot use a bare absence check. Instead: the grid's own report
    contributes ZERO caption pixels, so the CAPTION-coloured pixel SET must be identical regardless
    of `--grid-size`/escalation state -- if the (removed) in-image draw ever came back, a differently
    escalated render would show a different caption footprint and this would catch it."""
    a = _brush(size=512.0)

    def cap_positions(grid_size):
        ppm = render_quad_pgm(a, size=size, color_by_csg=True, grid_size=grid_size, locator=None,
                              annotations=AnnotationSpec.none())
        return {i for i, c in enumerate(_pixels(ppm)) if c == CAPTION}

    assert cap_positions(1) == cap_positions(4096)


def test_breakdown_grids_every_pane_when_view_is_ortho_none_when_iso():
    # Two very differently-sized brushes -> pane 0 (whole scene) and each actor's own pane frame at
    # very different scales, so an escalated auto step on one pane and not the other is exercised too.
    a1 = _brush(name="A", size=64.0, at=(0.0, 0.0, 0.0))
    a2 = _brush(name="B", size=4096.0, at=(20000.0, 0.0, 0.0))
    from uedcli.cli.rendering import _render_breakdown_grid
    args_top = SimpleNamespace(size=128, view="top", annotate="none", iso_angle=30.0,
                               brush_colors=None, highlight=None, show="")
    img = _render_breakdown_grid([a1, a2], args_top, render_data=PreviewData(), grid_size=None)
    assert any(c in set(img.convert("RGB").getdata()) for c in _GRID_COLORS)
    args_iso = SimpleNamespace(size=128, view="iso", annotate="none", iso_angle=30.0,
                               brush_colors=None, highlight=None, show="")
    img_iso = _render_breakdown_grid([a1, a2], args_iso, render_data=PreviewData(), grid_size=None)
    assert img_iso.size == img.size                         # same layout either way
    assert not any(c in set(img_iso.convert("RGB").getdata()) for c in _GRID_COLORS)


# ── §5 "Too coarse" ──────────────────────────────────────────────────────────────────────────

def test_too_coarse_grid_size_draws_no_gridline_pixels(tmp_path, monkeypatch):
    proj = _project_with_brush(tmp_path, monkeypatch, size=64.0)
    out = tmp_path / "o.png"
    assert dispatch.dispatch(_args(proj, out, view="top", grid_size=65536)) == 0
    from PIL import Image
    colors = set(Image.open(out).convert("RGB").getdata())
    assert not any(c in colors for c in _GRID_COLORS)


# ── §9 "Empty scene" ─────────────────────────────────────────────────────────────────────────

def test_empty_scene_draws_no_gridlines():
    ppm = render_brushes_pgm([], view="top", size=128, color_by_csg=True, grid_size=64)
    assert _colors(ppm) == {(BG, BG, BG)}


# ── §9 "Line weight" ─────────────────────────────────────────────────────────────────────────

@pytest.mark.parametrize("size", [128, 512])
def test_grid_lines_are_1px_at_every_size(size):
    a = _brush(size=64.0)
    region = (-2000.0, -2000.0, -2000.0, 2000.0, 2000.0, 2000.0)   # tiny brush -> lots of open grid
    ppm = render_brush_pgm(a, view="top", size=size, color_by_csg=True, grid_size=256,
                           region=region, locator=None)
    body = _body(ppm)
    row = 10                                                # near the border, clear of the centred brush
    max_run = run = 0
    for x in range(size):
        i = (row * size + x) * 3
        px = (body[i], body[i + 1], body[i + 2])
        if px in _GRID_COLORS:
            run += 1
            max_run = max(max_run, run)
        else:
            run = 0
    assert 0 < max_run <= 1, f"size={size} max grid-pixel run={max_run} (expected exactly 1px)"


# ── §9 "Draw order" ──────────────────────────────────────────────────────────────────────────

def test_grid_is_a_backdrop_a_covering_face_wins():
    """The grid is drawn FIRST; a face covering a gridline pixel must show the face colour. World
    (0,0) is always ON a gridline (0 is a multiple of any power-of-two step); a subtract room's
    solved floor covers it under `--faces textured`."""
    region = (-256.0, -256.0, -128.0, 256.0, 256.0, 128.0)
    size = 200
    room = _room("Room", size=512.0, height=256.0)
    covered = render_brushes_pgm([room], view="top", size=size, annotations=AnnotationSpec.none(),
                                 color_by_csg=True, render_data=_solved([room]), faces="textured",
                                 region=region, grid_size=64)
    marker = Actor(name="M", cls="Engine.Actor",
                   location=(Decimal(10 ** 6), Decimal(10 ** 6), Decimal(0)))
    grid_only = render_brushes_pgm([marker], view="top", size=size, annotations=AnnotationSpec.none(),
                                   color_by_csg=True,
                                   render_data=PreviewData(points={"M": PointRender(label="M")}),
                                   faces="wire", region=region, grid_size=64)
    _scale, to_px, *_rest = _framing([(0.0, 0.0)], region, size, "top", 30.0, pad=_FRAME_PAD)
    cx, cy = to_px((0.0, 0.0))
    i = (cy * size + cx) * 3
    ref_px = tuple(_body(grid_only)[i:i + 3])
    got_px = tuple(_body(covered)[i:i + 3])
    assert ref_px in _GRID_COLORS, "reference centre pixel is not a gridline — test setup is wrong"
    assert got_px not in _GRID_COLORS, "a face covering the gridline did not win"


def test_grid_colours_are_the_same_under_wire_and_textured():
    """`--faces` never touches the grid computation (it draws before the `faces` branch), so a lone
    small room framed inside a huge region shows an IDENTICAL grid whichever mode draws its (tiny,
    off to one side) geometry -- outside a safety margin around the room's OWN screen footprint,
    where `wire`'s outline and `textured`'s (CSG-solved interior) fill legitimately cover different
    pixels of the geometry itself, not the grid."""
    region = (-4096.0, -4096.0, -128.0, 4096.0, 4096.0, 128.0)
    room = _room("Room", size=512.0, height=256.0)
    size = 200
    wire = render_brushes_pgm([room], view="top", size=size, annotations=AnnotationSpec.none(),
                              color_by_csg=True, region=region, grid_size=64, faces="wire")
    textured = render_brushes_pgm([room], view="top", size=size, annotations=AnnotationSpec.none(),
                                  color_by_csg=True, render_data=_solved([room]), region=region,
                                  grid_size=64, faces="textured")
    _scale, to_px, *_rest = _framing([(0.0, 0.0)], region, size, "top", 30.0, pad=_FRAME_PAD)
    cx, cy = to_px((0.0, 0.0))
    margin = 20                                             # comfortably past the room's own footprint

    def _far(i):
        x, y = i % size, i // size
        return abs(x - cx) > margin or abs(y - cy) > margin

    grid_wire = {i for i, c in enumerate(_pixels(wire)) if c in _GRID_COLORS and _far(i)}
    grid_textured = {i for i, c in enumerate(_pixels(textured)) if c in _GRID_COLORS and _far(i)}
    assert grid_wire and grid_wire == grid_textured


def test_grid_is_unaffected_by_focus_dimming():
    other = _brush(name="Other", size=64.0, at=(2000.0, 2000.0, 0.0))
    focused = _brush(name="Focus", size=64.0, at=(0.0, 0.0, 0.0))
    region = (-256.0, -256.0, -128.0, 256.0, 256.0, 128.0)
    no_focus = render_brushes_pgm([other, focused], view="top", size=200, color_by_csg=True,
                                  region=region, grid_size=64, faces="wire")
    with_focus = render_brushes_pgm([other, focused], view="top", size=200, color_by_csg=True,
                                    region=region, grid_size=64, faces="wire", focus="Focus")
    a, b = _pixels(no_focus), _pixels(with_focus)
    saw_grid = False
    for pa, pb in zip(a, b):
        if pa in _GRID_COLORS:
            saw_grid = True
            assert pb == pa, "a grid pixel changed colour under --focus"
    assert saw_grid, "no gridline pixel to compare — test setup is wrong"


# ── §9 "All three verbs" ─────────────────────────────────────────────────────────────────────

_ARCH_T3D = (
    "Begin Actor Class=Brush Name=Arch\n    Begin Brush Name=Model7\n"
    "       Begin PolyList\n         Begin Polygon Texture=DeusExDeco.Stone.Block\n"
    "          Vertex +0.000000,+0.000000,+0.000000\n"
    "          Vertex +512.000000,+0.000000,+0.000000\n"
    "          Vertex +512.000000,+512.000000,+0.000000\n         End Polygon\n"
    "       End PolyList\n    End Brush\n    Name=\"Arch\"\nEnd Actor\n")


def _stash_args(proj, out, **kw):
    base = dict(cmd="stash", sub="diagram", project=str(proj), container="c", id="archway",
                names=[], view="top", layout="single", annotate="all", iso_angle=30.0, frame=None,
                frame_tightness=0.8, highlight=None, focus=None, show="", size=128,
                out=str(out), brush_colors="csg", grid_size=64)
    base.update(kw)
    return SimpleNamespace(**base)


def test_grid_size_renders_through_stash_preview(tmp_path, monkeypatch):
    from uedcli import stash_register
    proj = tmp_path / "repo"
    (proj / "maps" / "lvl").mkdir(parents=True)
    (proj / "uedcli.toml").write_text('game = "deusex"\n')
    trunk.write_level(proj / "maps" / "lvl", Level(actors={}), {})
    monkeypatch.setenv("UEDCLI_LEVEL", "lvl")
    reg = stash_register.FileStashRegister(proj / ".uedcli" / "stash")
    reg.write_stash("archway", full_level={"Arch": _ARCH_T3D}, order=["Arch"], packages=[],
                    meta={"anchor": ["0", "0", "0"], "ts": 1})
    out = tmp_path / "o.png"
    assert dispatch.dispatch(_stash_args(proj, out)) == 0
    from PIL import Image
    colors = set(Image.open(out).convert("RGB").getdata())
    assert any(c in colors for c in _GRID_COLORS)


def test_grid_size_renders_through_prefab_preview(tmp_path, monkeypatch):
    from uedcli import stashlib
    proj = tmp_path / "repo"
    (proj / "maps" / "lvl").mkdir(parents=True)
    (proj / "uedcli.toml").write_text('game = "deusex"\n')
    trunk.write_level(proj / "maps" / "lvl", Level(actors={}), {})
    monkeypatch.setenv("UEDCLI_LEVEL", "lvl")
    stashlib.write_prefab(proj / "prefabs", "box", full_level={"Arch": _ARCH_T3D}, order=["Arch"],
                          packages=[], meta={"anchor": ["0", "0", "0"], "ts": 1})
    out = tmp_path / "o.png"
    args = SimpleNamespace(cmd="prefab", sub="diagram", project=str(proj), name="box", names=[],
                           prefab_dir=None, view="top", layout="single", annotate="all",
                           iso_angle=30.0, frame=None, highlight=None, focus=None,
                           frame_tightness=0.8, show="", size=128, out=str(out), brush_colors="csg",
                           grid_size=64)
    assert dispatch.dispatch(args) == 0
    from PIL import Image
    colors = set(Image.open(out).convert("RGB").getdata())
    assert any(c in colors for c in _GRID_COLORS)


# ── §9 "Golden" ──────────────────────────────────────────────────────────────────────────────

def test_grid_golden():
    """One small committed golden PNG at a fixed scene/`--size`/`--grid-size`, so a change to the
    lattice geometry or the two tier greys is visible in review (the grid report itself is
    stderr-only, spec §6, and so is not part of this image). Bless with
    `UEDCLI_BLESS_GOLDEN=1 bin/test -k grid_golden`."""
    box = make_brush_actor("Box", cube(512.0, 512.0, 256.0), location=(0.0, 0.0, 0.0), csg="add")
    ppm = render_brush_pgm(box, view="top", size=384, color_by_csg=True, grid_size=32, locator=12)
    from PIL import Image
    got_img = Image.open(BytesIO(ppm)).convert("RGB")
    if os.environ.get("UEDCLI_BLESS_GOLDEN"):
        GOLDEN_GRID.parent.mkdir(parents=True, exist_ok=True)
        got_img.save(GOLDEN_GRID)
        pytest.skip(f"golden blessed -> {GOLDEN_GRID}")
    assert GOLDEN_GRID.is_file(), f"golden fixture missing: {GOLDEN_GRID}"
    want = Image.open(GOLDEN_GRID).convert("RGB").tobytes()
    got = got_img.tobytes()
    if got != want:
        diff = sum(1 for a, b in zip(got, want) if a != b) + abs(len(got) - len(want))
        pytest.fail(f"grid golden diverged: {diff} bytes")
