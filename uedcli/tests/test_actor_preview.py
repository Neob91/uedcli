"""`actor preview` dispatch ergonomics: the renamed verb, unified `--from-t3d`, the `BRUSH:idx`
`--frame` selector (frames only), the unified `--highlight` (a poly selector or an actor name), and `--frame-tightness`. These
drive `dispatch.dispatch` against a real trunk level (model-side, host-only — no editor/container)."""
from pathlib import Path
from types import SimpleNamespace

from uedcli import trunk, utexture
from uedcli.cli import dispatch
from uedcli.builders import cube, make_brush_actor
from uedcli.model import Level


def _project_with_two_brushes(tmp_path, monkeypatch, name="lvl"):
    proj = tmp_path / "repo"
    (proj / "maps" / name).mkdir(parents=True)
    (proj / "uedcli.toml").write_text('game = "deusex"\n')
    a = make_brush_actor("WallA", cube(128, 128, 128), location=(0, 0, 0), csg="subtract")
    b = make_brush_actor("WallB", cube(64, 64, 64), location=(400, 0, 0), csg="add")
    lvl = Level(actors={"WallA": a, "WallB": b}); lvl.order = ["WallA", "WallB"]
    trunk.write_level(proj / "maps" / name, lvl, dict(zip(["WallA", "WallB"], trunk.initial_ranks(2))))
    monkeypatch.setenv("UEDCLI_LEVEL", name)
    return proj


def _prev(proj, out, **kw):
    base = dict(cmd="actor", sub="preview", project=str(proj), names=[], from_t3d=None,
                view="iso", layout="quad", annotate="all", iso_angle=30.0, frame=None,
                frame_tightness=0.8, highlight=None, focus=None, show="", size=128,
                out=str(out) if out is not None else None, brush_colors="csg")
    base.update(kw)
    return SimpleNamespace(**base)


# ── reading a written preview ─────────────────────────────────────────────────────────────────
# A preview is ALWAYS a PNG on disk (`preview.py` renders PPM/P6 bytes in memory; the write
# boundary encodes them to PNG with Pillow). So pixel assertions decode the file with Pillow —
# uedcli's sole, REQUIRED third-party dep — rather than parsing a PPM header.

_PNG_MAGIC = b"\x89PNG\r\n\x1a\n"


def _is_png(path):
    return Path(path).read_bytes()[:8] == _PNG_MAGIC


def _img(path):
    """`(width, height, raw RGB bytes)` of a written preview PNG."""
    from PIL import Image
    with Image.open(path) as im:
        rgb = im.convert("RGB")
        return rgb.width, rgb.height, rgb.tobytes()


def _dims(path):
    w, h, _b = _img(path)
    return w, h


def _pixel(img, x, y):
    w, _h, b = img
    i = (y * w + x) * 3
    return (b[i], b[i + 1], b[i + 2])


def _colors(img):
    _w, _h, b = img
    return {tuple(b[k:k + 3]) for k in range(0, len(b), 3)}


def test_it_renames_brush_preview_to_actor_preview(tmp_path, monkeypatch):
    proj = _project_with_two_brushes(tmp_path, monkeypatch)
    out = tmp_path / "o.png"
    assert dispatch.dispatch(_prev(proj, out, names=["WallA"])) == 0
    assert _is_png(out)


def test_default_preview_paints_onface_poly_numbers(tmp_path, monkeypatch):
    # The default `actor preview` (no flag) paints on-face poly numbers: a subtract room's face decals
    # add content over a names-only render of the same actor.
    proj = _project_with_two_brushes(tmp_path, monkeypatch)
    from uedcli.preview import DEFAULT_ANNOTATIONS
    labelled, names_only = tmp_path / "l.png", tmp_path / "n.png"
    assert dispatch.dispatch(_prev(proj, labelled, names=["WallA"], annotate=DEFAULT_ANNOTATIONS)) == 0
    assert dispatch.dispatch(_prev(proj, names_only, names=["WallA"], annotate="name")) == 0
    assert _nonbg(_img(labelled)) > _nonbg(_img(names_only))


def test_names_from_stdin(tmp_path, monkeypatch):
    import io
    proj = _project_with_two_brushes(tmp_path, monkeypatch)
    monkeypatch.setattr("sys.stdin", io.StringIO("WallA\nWallB\n"))
    out = tmp_path / "o.png"
    assert dispatch.dispatch(_prev(proj, out, names=["-"])) == 0
    assert _is_png(out)


def test_empty_stdin_is_a_clean_no_op(tmp_path, monkeypatch):
    import io
    proj = _project_with_two_brushes(tmp_path, monkeypatch)
    monkeypatch.setattr("sys.stdin", io.StringIO(""))
    out = tmp_path / "o.png"
    assert dispatch.dispatch(_prev(proj, out, names=["-"])) == 0
    assert not out.exists()                                # no render on empty stdin


def test_no_target_set_at_all_is_a_clean_error(tmp_path, monkeypatch, capsys):
    # No positional names AND no `-`: nothing to render. This must ERROR (exit 2, named), not
    # silently render nothing and return 0. The empty-`-`-stdin no-op above stays exit 0.
    proj = _project_with_two_brushes(tmp_path, monkeypatch)
    out = tmp_path / "o.png"
    rc = dispatch.dispatch(_prev(proj, out, names=[]))
    assert rc == 2
    err = capsys.readouterr().err
    assert "no actors to render" in err and "Traceback" not in err
    assert not out.exists()


def test_from_t3d_does_not_require_names(tmp_path, monkeypatch):
    # `--from-t3d` is a different actor source, so the no-names guard must NOT fire for it.
    proj = _project_with_two_brushes(tmp_path, monkeypatch)
    f1 = tmp_path / "a.t3d"; f1.write_text("Begin Map\n" + _brush_t3d("Tri1", 0) + "End Map\n")
    out = tmp_path / "o.png"
    assert dispatch.dispatch(_prev(proj, out, from_t3d=[str(f1)])) == 0
    assert _is_png(out)


def _brush_t3d(name, x):
    return (f"Begin Actor Class=Engine.Brush Name={name}\n    Begin Brush Name=Model_{name}\n"
            "       Begin PolyList\n         Begin Polygon Texture=X.Y\n"
            f"          Vertex +{x}.000000,+0.000000,+0.000000\n"
            f"          Vertex +{x + 64}.000000,+0.000000,+0.000000\n"
            f"          Vertex +{x + 64}.000000,+64.000000,+0.000000\n         End Polygon\n"
            "       End PolyList\n    End Brush\n"
            f"    Location=(X=0.000000)\n    Name=\"{name}\"\nEnd Actor\n")


def test_from_t3d_files_concatenate(tmp_path, monkeypatch):
    proj = _project_with_two_brushes(tmp_path, monkeypatch)
    f1 = tmp_path / "a.t3d"; f1.write_text("Begin Map\n" + _brush_t3d("Tri1", 0) + "End Map\n")
    f2 = tmp_path / "b.t3d"; f2.write_text("Begin Map\n" + _brush_t3d("Tri2", 200) + "End Map\n")
    out = tmp_path / "o.png"
    # Two files, two brushes: the combined frame is wider than either alone (both rendered).
    assert dispatch.dispatch(_prev(proj, out, from_t3d=[str(f1), str(f2)])) == 0
    both = out.read_bytes()
    assert dispatch.dispatch(_prev(proj, out, from_t3d=[str(f1)])) == 0
    assert both != out.read_bytes()


def test_from_t3d_stdin(tmp_path, monkeypatch):
    import io
    proj = _project_with_two_brushes(tmp_path, monkeypatch)
    monkeypatch.setattr("sys.stdin", io.StringIO("Begin Map\n" + _brush_t3d("Tri", 0) + "End Map\n"))
    out = tmp_path / "o.png"
    assert dispatch.dispatch(_prev(proj, out, from_t3d=["-"])) == 0
    assert _is_png(out)


def test_from_t3d_with_names_is_mutually_exclusive(tmp_path, monkeypatch, capsys):
    proj = _project_with_two_brushes(tmp_path, monkeypatch)
    f1 = tmp_path / "a.t3d"; f1.write_text("Begin Map\n" + _brush_t3d("Tri", 0) + "End Map\n")
    rc = dispatch.dispatch(_prev(proj, tmp_path / "o.png", names=["WallA"], from_t3d=[str(f1)]))
    assert rc == 2
    err = capsys.readouterr().err
    assert "mutually exclusive" in err and "Traceback" not in err


def test_from_t3d_dash_cannot_mix_with_files(tmp_path, monkeypatch, capsys):
    proj = _project_with_two_brushes(tmp_path, monkeypatch)
    f1 = tmp_path / "a.t3d"; f1.write_text("Begin Map\nEnd Map\n")
    rc = dispatch.dispatch(_prev(proj, tmp_path / "o.png", from_t3d=["-", str(f1)]))
    assert rc == 2 and "Traceback" not in capsys.readouterr().err


def test_zoom_selector_on_a_non_first_brush(tmp_path, monkeypatch):
    proj = _project_with_two_brushes(tmp_path, monkeypatch)
    out = tmp_path / "o.png"
    # WallB is the SECOND brush — its selector must resolve (not actors[0]) and reframe.
    assert dispatch.dispatch(_prev(proj, out, names=["WallA", "WallB"], frame="WallB:0")) == 0
    zoomed = out.read_bytes()
    assert dispatch.dispatch(_prev(proj, out, names=["WallA", "WallB"], frame_tightness=0.0)) == 0
    assert zoomed != out.read_bytes()                      # zoom actually reframed


def test_zoom_does_not_highlight(tmp_path, monkeypatch):
    from uedcli.preview import _CSG_PALETTE
    proj = _project_with_two_brushes(tmp_path, monkeypatch)
    out = tmp_path / "o.png"
    assert dispatch.dispatch(_prev(proj, out, names=["WallA"], layout="single", frame="WallA:0")) == 0
    # A zoom target is NOT bolded/highlighted — no bold vivid highlight run beyond the CSG fill.
    assert _CSG_PALETTE["subtract"][0] in _colors(_img(out))   # WallA is coloured (subtract → gold)


def test_zoom_multi_index_is_a_clean_error(tmp_path, monkeypatch, capsys):
    proj = _project_with_two_brushes(tmp_path, monkeypatch)
    rc = dispatch.dispatch(_prev(proj, tmp_path / "o.png", names=["WallA"], frame="WallA:0,1"))
    assert rc == 2
    err = capsys.readouterr().err
    assert "ONE poly" in err and "Traceback" not in err


def test_frame_explicit_aabb_reframes(tmp_path, monkeypatch):
    # A six-field --frame world AABB (leading-negative) frames exactly that box → differs from the
    # un-framed whole-set render. Exercises the _parse_frame len==6 branch + explicit-region path.
    proj = _project_with_two_brushes(tmp_path, monkeypatch)
    out = tmp_path / "o.png"
    assert dispatch.dispatch(_prev(proj, out, names=["WallA", "WallB"])) == 0
    plain = out.read_bytes()
    assert dispatch.dispatch(_prev(proj, out, names=["WallA", "WallB"],
                                   frame="-64,-64,-64,64,64,64")) == 0
    assert out.read_bytes() != plain                       # the explicit AABB reframed


def test_show_unknown_member_is_a_clean_named_error(tmp_path, monkeypatch, capsys):
    # An unknown --show member errors naming it — even on a brush-only set, proving --show is validated
    # BEFORE render (not skipped when there are no point actors).
    proj = _project_with_two_brushes(tmp_path, monkeypatch)
    rc = dispatch.dispatch(_prev(proj, tmp_path / "o.png", names=["WallA"], show="collision,bogus"))
    assert rc == 2
    err = capsys.readouterr().err
    assert "bogus" in err and "Traceback" not in err


def test_out_omitted_mints_a_temp_png_and_prints_it(tmp_path, monkeypatch, capsys):
    # No --out → a uedcli-preview-*.png temp file is minted and its ABSOLUTE path printed to stdout.
    monkeypatch.setattr("tempfile.tempdir", str(tmp_path))  # keep the mint under the test's tmp
    proj = _project_with_two_brushes(tmp_path, monkeypatch)
    assert dispatch.dispatch(_prev(proj, None, names=["WallA"])) == 0
    printed = capsys.readouterr().out.strip()
    assert Path(printed).is_absolute() and Path(printed).name.startswith("uedcli-preview-")
    assert printed.endswith(".png") and _is_png(printed)


def test_out_extension_is_replaced_by_png(tmp_path, monkeypatch, capsys):
    # PNG is the ONLY on-disk preview form, so --out's extension is REPLACED, not honoured: a
    # `.ppm`-named --out writes `<stem>.png` and leaves no file at the name the caller asked for
    # (the old behaviour wrote raw PPM bytes into a misleadingly-named file). The path actually
    # written is what gets printed.
    proj = _project_with_two_brushes(tmp_path, monkeypatch)
    asked = tmp_path / "shot.ppm"
    assert dispatch.dispatch(_prev(proj, asked, names=["WallA"])) == 0
    written = tmp_path / "shot.png"
    assert _is_png(written) and not asked.exists()
    assert capsys.readouterr().out.strip() == str(written)


def test_out_naming_an_existing_directory_is_a_clean_named_error(tmp_path, monkeypatch, capsys):
    # --out is a FILE path. Naming a directory used to error only by accident (the old PPM write hit
    # IsADirectoryError); once the extension is unconditionally replaced, `--out shots/` would
    # silently become a `shots.png` SIBLING of the directory. Reject it, naming the path.
    proj = _project_with_two_brushes(tmp_path, monkeypatch)
    shots = tmp_path / "shots"
    shots.mkdir()
    rc = dispatch.dispatch(_prev(proj, shots, names=["WallA"]))
    assert rc == 2
    err = capsys.readouterr().err
    assert "must name a file" in err and str(shots) in err and "Traceback" not in err
    assert not (tmp_path / "shots.png").exists()           # nothing written beside the directory


def test_focus_changes_the_render_without_reframing(tmp_path, monkeypatch):
    proj = _project_with_two_brushes(tmp_path, monkeypatch)
    out = tmp_path / "o.png"
    # --focus is a rendering-only knob: it dims the non-focused brush (so the image DIFFERS, proving it
    # threads through) but must NOT reframe. With labels off, the difference is wire SHADE only, never
    # geometry position — so the set of non-background pixel POSITIONS (the drawn extent) is identical
    # with and without focus, which is the real no-reframe invariant.
    assert dispatch.dispatch(_prev(proj, out, names=["WallA", "WallB"], layout="single",
                                   annotate="none", focus="WallB")) == 0
    focused, focused_bytes = _img(out), out.read_bytes()
    assert dispatch.dispatch(_prev(proj, out, names=["WallA", "WallB"], layout="single", annotate="none")) == 0
    unfocused, unfocused_bytes = _img(out), out.read_bytes()
    assert _is_png(out) and focused_bytes != unfocused_bytes         # dimming changed the image
    assert _nonbg_positions(focused) == _nonbg_positions(unfocused)  # but the drawn extent is unchanged


def test_focus_unknown_name_is_a_clean_named_error(tmp_path, monkeypatch, capsys):
    proj = _project_with_two_brushes(tmp_path, monkeypatch)
    rc = dispatch.dispatch(_prev(proj, tmp_path / "o.png", names=["WallA"], focus="Ghost"))
    assert rc == 2
    err = capsys.readouterr().err
    assert "Ghost" in err and "Traceback" not in err


def test_focus_a_point_actor_is_a_clean_named_error(tmp_path, monkeypatch, capsys):
    proj = _project_with_light(tmp_path, monkeypatch)
    rc = dispatch.dispatch(_prev(proj, tmp_path / "o.png", names=["Torch"], focus="Torch"))
    assert rc == 2
    err = capsys.readouterr().err
    assert "Torch" in err and "point actor" in err and "Traceback" not in err


def test_bad_labels_value_is_a_clean_named_error(tmp_path, monkeypatch, capsys):
    proj = _project_with_two_brushes(tmp_path, monkeypatch)
    rc = dispatch.dispatch(_prev(proj, tmp_path / "o.png", names=["WallA"], annotate="poly:bogus"))
    assert rc == 2
    err = capsys.readouterr().err
    assert "bogus" in err and "Traceback" not in err     # names the offending token, no traceback


def test_zoom_out_of_range_is_a_clean_named_error(tmp_path, monkeypatch, capsys):
    proj = _project_with_two_brushes(tmp_path, monkeypatch)
    rc = dispatch.dispatch(_prev(proj, tmp_path / "o.png", names=["WallA"], frame="WallA:99"))
    assert rc == 2
    err = capsys.readouterr().err
    assert "WallA" in err and "out of range" in err and "Traceback" not in err


def test_zoom_unknown_brush_is_a_clean_named_error(tmp_path, monkeypatch, capsys):
    proj = _project_with_two_brushes(tmp_path, monkeypatch)
    rc = dispatch.dispatch(_prev(proj, tmp_path / "o.png", names=["WallA"], frame="Ghost:0"))
    assert rc == 2
    err = capsys.readouterr().err
    assert "Ghost" in err and "Traceback" not in err


def test_highlight_poly_accumulates_and_renders(tmp_path, monkeypatch):
    proj = _project_with_two_brushes(tmp_path, monkeypatch)
    out = tmp_path / "o.png"
    plain = tmp_path / "p.png"
    assert dispatch.dispatch(_prev(proj, plain, names=["WallA", "WallB"])) == 0
    # Highlight a face on the NON-first brush + one on the first → both render, image differs.
    assert dispatch.dispatch(_prev(proj, out, names=["WallA", "WallB"],
                                   highlight=["WallA:0", "WallB:1"])) == 0
    assert out.read_bytes() != plain.read_bytes()


def test_highlight_poly_set_form_draws_vivid(tmp_path, monkeypatch):
    from uedcli.preview import _CSG_PALETTE
    proj = _project_with_two_brushes(tmp_path, monkeypatch)
    out = tmp_path / "o.png"
    # WallA is subtracted → gold; a --highlight Wall:0,2 set-form token lights those polys vivid.
    assert dispatch.dispatch(_prev(proj, out, names=["WallA"], layout="single", view="top",
                                   annotate="none", highlight=["WallA:0,2"])) == 0
    assert _CSG_PALETTE["subtract"][0] in _colors(_img(out))          # vivid gold front hue drew


def test_highlight_whole_brush_by_name(tmp_path, monkeypatch):
    # A bare (colon-less) brush name highlights the WHOLE brush = all its polys → differs from plain.
    proj = _project_with_two_brushes(tmp_path, monkeypatch)
    plain = tmp_path / "p.png"
    out = tmp_path / "o.png"
    assert dispatch.dispatch(_prev(proj, plain, names=["WallA"], annotate="none")) == 0
    assert dispatch.dispatch(_prev(proj, out, names=["WallA"], annotate="none",
                                   highlight=["WallA"])) == 0
    assert out.read_bytes() != plain.read_bytes()


def test_highlight_poly_naming_unknown_brush_is_clean(tmp_path, monkeypatch, capsys):
    proj = _project_with_two_brushes(tmp_path, monkeypatch)
    rc = dispatch.dispatch(_prev(proj, tmp_path / "o.png", names=["WallA"],
                                 highlight=["Ghost:0"]))
    assert rc == 2 and "Traceback" not in capsys.readouterr().err


def test_highlight_unknown_actor_name_is_a_clean_named_error(tmp_path, monkeypatch, capsys):
    proj = _project_with_two_brushes(tmp_path, monkeypatch)
    rc = dispatch.dispatch(_prev(proj, tmp_path / "o.png", names=["WallA"], highlight=["Ghost"]))
    assert rc == 2
    err = capsys.readouterr().err
    assert "Ghost" in err and "Traceback" not in err


def test_labels_mode_gates_which_labels_draw(tmp_path, monkeypatch):
    # highlight is held CONSTANT across the three renders, so the only thing varying is the label
    # set: 'none' draws no labels, 'highlighted' draws just the one highlighted poly's label,
    # 'all' draws every viewer-facing face label → strictly increasing non-bg pixel counts.
    proj = _project_with_two_brushes(tmp_path, monkeypatch)

    def content(mode):
        out = tmp_path / f"{mode}.png"
        assert dispatch.dispatch(_prev(proj, out, names=["WallA", "WallB"],
                                       annotate=mode, highlight=["WallA:0"])) == 0
        return _nonbg(_img(out))
    assert content("none") < content("highlighted") < content("all")


def test_old_highlight_poly_flag_is_gone():
    import pytest
    from uedcli.cli import main as cli
    parser = cli.build_parser()
    with pytest.raises(SystemExit):                        # --highlight-poly was cleanly removed
        parser.parse_args(["actor", "preview", "--out", "x.png", "--highlight-poly", "WallA:0"])


def test_zoom_factor_interpolates(tmp_path, monkeypatch):
    proj = _project_with_two_brushes(tmp_path, monkeypatch)
    frames = {}
    for f in (0.0, 0.5, 1.0):
        out = tmp_path / f"z{f}.png"
        assert dispatch.dispatch(_prev(proj, out, names=["WallA", "WallB"],
                                       frame="WallB:0", frame_tightness=f)) == 0
        frames[f] = out.read_bytes()
    assert frames[0.0] != frames[0.5] != frames[1.0]       # each factor frames differently
    assert frames[0.0] != frames[1.0]


# ── Point actors + overlays (Phase 2) ─────────────────────────────────────────────────────────

from unittest import mock                                  # noqa: E402
from uedcli.model import Actor                             # noqa: E402


def _project_with_light(tmp_path, monkeypatch, name="lvl"):
    proj = tmp_path / "repo"
    (proj / "maps" / name).mkdir(parents=True)
    (proj / "uedcli.toml").write_text('game = "deusex"\n')
    light = Actor(name="Torch", cls="Engine.Light", location=(64, 64, 64))
    lvl = Level(actors={"Torch": light}); lvl.order = ["Torch"]
    trunk.write_level(proj / "maps" / name, lvl, dict(zip(["Torch"], trunk.initial_ranks(1))))
    monkeypatch.setenv("UEDCLI_LEVEL", name)
    return proj


class _FakeResolver:
    """A stand-in `TextureResolver` on the TYPED-result seam.

    `present` maps a ref → `(w, h, rgb, mask)` and yields a `DecodedTexture`; `exists_only`
    are refs that exist on the path but do not decode, and yield the `unverified-format`
    error. Everything else yields `unknown-texture`. It must never return `None`: the real
    resolver does not, and a caller written against `None` would take an error object for a
    picture (the error is deliberately truthy).
    """
    def __init__(self, present=None, exists_only=()):
        self.present = present or {}
        self.exists_only = set(exists_only)

    def resolve(self, ref):
        got = self.present.get(ref)
        if got is not None:
            w, h, rgb, mask = got
            return utexture.DecodedTexture(ref=ref, width=w, height=h, rgb=rgb, mask=mask,
                                           layout="linear1", layout_source="data",
                                           format_code=0, array="mips")
        if ref in self.exists_only:
            return utexture.TextureError(ref, "unverified-format",
                                         f"{ref}: no decoder for this layout")
        return utexture.TextureError(ref, "unknown-texture", f"{ref}: not on the path")

    def exists(self, ref):
        return ref in self.present or ref in self.exists_only


def _defaults_sprite(ref):
    return {("drawtype", 0): "DT_Sprite", ("drawscale", 0): "1.000000",
            ("texture", 0): f"Texture'{ref}'"}


def test_point_light_renders_as_sprite_from_the_trunk(tmp_path, monkeypatch):
    proj = _project_with_light(tmp_path, monkeypatch)
    rgb = bytes([200, 10, 10]) * 4
    resolver = _FakeResolver(present={"Engine.S_Light": (2, 2, rgb, bytes([1, 1, 1, 1]))})
    out = tmp_path / "o.png"
    with mock.patch("uedcli.cli.resources.class_defaults",
                    return_value=_defaults_sprite("Engine.S_Light")), \
         mock.patch("uedcli.cli.resources.texture_resolver", return_value=resolver):
        assert dispatch.dispatch(_prev(proj, out, names=["Torch"], layout="single", view="top")) == 0
    assert (200, 10, 10) in _colors(_img(out))                                 # sprite drew


def test_schema_unavailable_point_actor_degrades_to_marker(tmp_path, monkeypatch, capsys):
    from uedcli.uprops import SchemaError
    proj = _project_with_light(tmp_path, monkeypatch)
    out = tmp_path / "o.png"
    with mock.patch("uedcli.cli.resources.class_defaults", side_effect=SchemaError("no .u")), \
         mock.patch("uedcli.cli.resources.texture_resolver", return_value=None):
        assert dispatch.dispatch(_prev(proj, out, names=["Torch"])) == 0
    err = capsys.readouterr().err
    assert "schema unavailable" in err and "Traceback" not in err
    assert _is_png(out)                                    # still renders (marker)


def test_non_p8_sprite_vs_absent_are_distinguished(tmp_path, monkeypatch, capsys):
    proj = _project_with_light(tmp_path, monkeypatch)
    out = tmp_path / "o.png"
    # exists but doesn't decode → non-P8 note.
    with mock.patch("uedcli.cli.resources.class_defaults",
                    return_value=_defaults_sprite("Pkg.NonP8")), \
         mock.patch("uedcli.cli.resources.texture_resolver",
                    return_value=_FakeResolver(exists_only={"Pkg.NonP8"})):
        assert dispatch.dispatch(_prev(proj, out, names=["Torch"])) == 0
    # The decoder's own case name travels into the note, so "we cannot decode this layout"
    # reads differently from "that ref is wrong" without re-running anything.
    assert "unverified-format" in capsys.readouterr().err
    # truly absent → not-found note.
    with mock.patch("uedcli.cli.resources.class_defaults",
                    return_value=_defaults_sprite("Pkg.Gone")), \
         mock.patch("uedcli.cli.resources.texture_resolver", return_value=_FakeResolver()):
        assert dispatch.dispatch(_prev(proj, out, names=["Torch"])) == 0
    assert "unknown-texture" in capsys.readouterr().err


def test_no_search_path_at_all_is_not_reported_as_a_missing_texture(tmp_path, monkeypatch,
                                                                    capsys):
    """With `_texture_resolver` returning None — no user config, a broken games config, or an
    empty composed file list — **no package was ever opened**. Saying "not found" would tell a
    user with no games configured that their texture is missing, sending them to fix the wrong
    thing. The note has to name the real condition."""
    proj = _project_with_light(tmp_path, monkeypatch)
    out = tmp_path / "o.png"
    with mock.patch("uedcli.cli.resources.class_defaults",
                    return_value=_defaults_sprite("Pkg.Whatever")), \
         mock.patch("uedcli.cli.resources.texture_resolver", return_value=None):
        assert dispatch.dispatch(_prev(proj, out, names=["Torch"])) == 0
    err = capsys.readouterr().err
    assert "no texture search path is configured" in err
    assert "not found" not in err


def test_zoom_naming_a_point_actor_is_a_clean_error(tmp_path, monkeypatch, capsys):
    proj = _project_with_light(tmp_path, monkeypatch)
    with mock.patch("uedcli.cli.resources.class_defaults", return_value={}), \
         mock.patch("uedcli.cli.resources.texture_resolver", return_value=None):
        rc = dispatch.dispatch(_prev(proj, tmp_path / "o.png", names=["Torch"], frame="Torch:0"))
    assert rc == 2
    err = capsys.readouterr().err
    assert "point actor" in err and "Traceback" not in err


def test_show_collision_draws_for_a_colliding_point_actor(tmp_path, monkeypatch):
    from uedcli.preview import COL_COLLISION
    proj = _project_with_light(tmp_path, monkeypatch)
    defaults = {("drawtype", 0): "DT_None", ("bcollideactors", 0): "True",
                ("collisionradius", 0): "40.000000", ("collisionheight", 0): "60.000000"}
    out = tmp_path / "o.png"
    with mock.patch("uedcli.cli.resources.class_defaults", return_value=defaults), \
         mock.patch("uedcli.cli.resources.texture_resolver", return_value=None):
        assert dispatch.dispatch(_prev(proj, out, names=["Torch"], layout="single", view="front",
                                       show="collision")) == 0
    assert COL_COLLISION in _colors(_img(out))


def test_point_actor_in_a_stash_renders(tmp_path, monkeypatch):
    # Pins the `rendering.brush_actors_from` relaxation: a stash's point actor must not be dropped pre-render.
    from uedcli import stash_register
    from uedcli.normalize import canonical_actor_t3d
    proj = _project_with_light(tmp_path, monkeypatch)
    reg = stash_register.FileStashRegister(proj / ".uedcli" / "stash")
    light = Actor(name="Torch", cls="Engine.Light", location=(0, 0, 0))
    reg.write_stash("box", full_level={"Torch": canonical_actor_t3d(light)}, order=["Torch"],
                    packages=[], meta={"anchor": ["0", "0", "0"], "ts": 1})
    out = tmp_path / "o.png"
    args = SimpleNamespace(cmd="stash", sub="preview", project=str(proj), id="box", names=[],
                           view="top", layout="single", annotate="all", iso_angle=30.0, frame=None,
                           highlight=None, focus=None, frame_tightness=0.8, show="",
                           size=128, out=str(out), container="c")
    with mock.patch("uedcli.cli.resources.class_defaults", return_value={}), \
         mock.patch("uedcli.cli.resources.texture_resolver", return_value=None):
        assert dispatch.dispatch(args) == 0
    assert _nonbg(_img(out)) > 0             # the point actor drew (a marker)


def test_drawscale_zero_sprite_falls_back_to_a_marker(tmp_path, monkeypatch, capsys):
    # NIT: a resolved sprite whose footprint is zero (DrawScale 0) would blit nothing — fall back to
    # the diamond marker + a note, not a bare label.
    proj = _project_with_light(tmp_path, monkeypatch)
    rgb = bytes([200, 10, 10]) * 4
    resolver = _FakeResolver(present={"Engine.S_Light": (2, 2, rgb, bytes([1, 1, 1, 1]))})
    defaults = {("drawtype", 0): "DT_Sprite", ("drawscale", 0): "0.000000",
                ("texture", 0): "Texture'Engine.S_Light'"}
    out = tmp_path / "o.png"
    with mock.patch("uedcli.cli.resources.class_defaults", return_value=defaults), \
         mock.patch("uedcli.cli.resources.texture_resolver", return_value=resolver):
        assert dispatch.dispatch(_prev(proj, out, names=["Torch"], layout="single", view="top")) == 0
    assert "zero footprint" in capsys.readouterr().err
    cols = _colors(_img(out))
    # The real preview is the hybrid (CSG-coloured) path, so the fallback marker is drawn in the actor's
    # per-actor label tint — the first palette entry for a single actor — not the legacy neutral grey.
    from uedcli.preview import _TINT_PALETTE
    assert _TINT_PALETTE[0] in cols and (200, 10, 10) not in cols   # marker drew; sprite did NOT


def test_point_actor_in_a_prefab_renders(tmp_path, monkeypatch):
    # Pins the prefab-preview `brushes_only=False`: a prefab's point actor must not be dropped
    # pre-render (the stash path had it; prefab was missed).
    from uedcli import stashlib
    from uedcli.normalize import canonical_actor_t3d
    proj = _project_with_light(tmp_path, monkeypatch)
    stashlib.write_prefab(proj / "prefabs", "box",
                          full_level={"Torch": canonical_actor_t3d(
                              Actor(name="Torch", cls="Engine.Light", location=(0, 0, 0)))},
                          order=["Torch"], packages=[], meta={"anchor": ["0", "0", "0"], "ts": 1})
    out = tmp_path / "o.png"
    args = SimpleNamespace(cmd="prefab", sub="preview", project=str(proj), name="box", names=[],
                           prefab_dir=None, view="top", layout="single", annotate="all", iso_angle=30.0,
                           frame=None, highlight=None, focus=None, frame_tightness=0.8, show="",
                           size=128, out=str(out))
    with mock.patch("uedcli.cli.resources.class_defaults", return_value={}), \
         mock.patch("uedcli.cli.resources.texture_resolver", return_value=None):
        assert dispatch.dispatch(args) == 0
    assert _nonbg(_img(out)) > 0             # the point actor drew (a marker)


def test_from_t3d_needs_no_ambient_level(tmp_path, monkeypatch):
    # `--from-t3d` renders a snippet with a project but NO $UEDCLI_LEVEL (it must run before the
    # eager level-source resolution). Regression for the ambient-level over-requirement.
    proj = tmp_path / "repo"
    proj.mkdir()
    (proj / "uedcli.toml").write_text('game = "deusex"\n')
    monkeypatch.delenv("UEDCLI_LEVEL", raising=False)
    f1 = tmp_path / "a.t3d"; f1.write_text("Begin Map\n" + _brush_t3d("Tri", 0) + "End Map\n")
    out = tmp_path / "o.png"
    assert dispatch.dispatch(_prev(proj, out, from_t3d=[str(f1)])) == 0
    assert _is_png(out)


def test_highlight_point_actor_draws_selection_brackets(tmp_path, monkeypatch):
    # A bare (colon-less) name that resolves to a POINT actor gets corner brackets (a selection
    # reticle) framing it — NOT a circle/disc (circles mean radius/collision here). Rendered with
    # annotate="none" and no sprite (resolver mocked None → grey MARKER), so the brackets' FRONT hue
    # (the uncoloured light default, distinct from MARKER and the WHITE halo) can ONLY come from them.
    from uedcli.preview import FRONT
    proj = _project_with_light(tmp_path, monkeypatch)
    plain = tmp_path / "p.png"
    out = tmp_path / "o.png"

    def has_brackets(path):
        return FRONT in _colors(_img(path))
    with mock.patch("uedcli.cli.resources.class_defaults", return_value={}), \
         mock.patch("uedcli.cli.resources.texture_resolver", return_value=None):
        assert dispatch.dispatch(_prev(proj, plain, names=["Torch"], layout="single", view="top",
                                       annotate="none")) == 0
        assert dispatch.dispatch(_prev(proj, out, names=["Torch"], layout="single", view="top",
                                       annotate="none", highlight=["Torch"])) == 0
    assert not has_brackets(plain)                         # no brackets without --highlight
    assert has_brackets(out)                               # brackets framed the point actor


def _nonbg(img):
    # "content" = pixels that are NOT the grey background (compare to preview.BG, not white — the
    # background is grey and the label boxes are white, so a white-based count would be vacuous).
    from uedcli.preview import BG
    _w, _h, b = img
    return sum(1 for k in range(0, len(b), 3) if tuple(b[k:k + 3]) != (BG, BG, BG))


def _nonbg_positions(img):
    # The SET of pixel indices that are non-background — the drawn extent, independent of colour. Two
    # renders with the same geometry/framing but different shading share this set exactly.
    from uedcli.preview import BG
    _w, _h, b = img
    return {k // 3 for k in range(0, len(b), 3) if tuple(b[k:k + 3]) != (BG, BG, BG)}


# --- shared filmstrip helpers (room+pillar scene) ---

def _project_room_pillar(tmp_path, monkeypatch, name="rp"):
    # A subtract room + a concentric add pillar — two brushes, so --layout breakdown yields 3 panes
    # (SCENE + one per brush).
    proj = tmp_path / "repo"
    (proj / "maps" / name).mkdir(parents=True)
    (proj / "uedcli.toml").write_text('game = "deusex"\n')
    room = make_brush_actor("Room", cube(512, 512, 384), location=(0, 0, 0), csg="subtract")
    pillar = make_brush_actor("Pillar", cube(96, 96, 384), location=(0, 0, 0), csg="add")
    lvl = Level(actors={"Room": room, "Pillar": pillar}); lvl.order = ["Room", "Pillar"]
    trunk.write_level(proj / "maps" / name, lvl, dict(zip(["Room", "Pillar"], trunk.initial_ranks(2))))
    monkeypatch.setenv("UEDCLI_LEVEL", name)
    return proj


# --- --layout breakdown (overview + per-brush focus/zoom panes) and --brush-colors ---

def test_it_renders_one_breakdown_pane_per_brush_plus_an_overview(tmp_path, monkeypatch):
    # Arrange: room+pillar → SCENE + 2 brush panes = 3 panes → a 2x2 grid (last cell empty).
    proj = _project_room_pillar(tmp_path, monkeypatch)
    out = tmp_path / "b.png"
    size = 256
    # Act
    assert dispatch.dispatch(_prev(proj, out, names=["Room", "Pillar"], layout="breakdown", size=size)) == 0
    # Assert: 2 cols x 2 rows; width = 2 cells + 1 gap, height = 2 (caption band + pane) + 1 gap.
    assert _dims(out) == (2 * size + 8, 2 * (size + 16) + 8)


def test_it_draws_no_legend_panel_in_any_breakdown_pane(tmp_path, monkeypatch):
    # The breakdown ditched the legend entirely — the SCENE pane self-labels with on-face names — so no
    # solid WHITE legend panel is drawn in any cell's top-left corner (where the legend used to sit).
    from uedcli.preview import WHITE
    proj = _project_room_pillar(tmp_path, monkeypatch)
    out = tmp_path / "b.png"
    size = 256
    assert dispatch.dispatch(_prev(proj, out, names=["Room", "Pillar"], layout="breakdown", size=size)) == 0
    img = _img(out)
    cell_h = size + 16

    def has_white(cx, cy):                              # white legend-panel pixel in this cell's corner
        x0, y0 = cx * (size + 8), cy * (cell_h + 8) + 16
        return any(_pixel(img, x, y) == WHITE
                   for x in range(x0 + 2, x0 + 40) for y in range(y0 + 1, y0 + 30))
    assert not has_white(0, 0)                          # overview: no legend anymore
    assert not has_white(1, 0)                          # Room pane
    assert not has_white(0, 1)                          # Pillar pane


def test_it_breakdown_overrides_the_default_quad(tmp_path, monkeypatch):
    # Arrange: --layout breakdown instead of the default quad.
    proj = _project_room_pillar(tmp_path, monkeypatch)
    out = tmp_path / "b.png"
    # Act
    assert dispatch.dispatch(_prev(proj, out, names=["Room", "Pillar"],
                                   layout="breakdown", size=256)) == 0
    # Assert: the breakdown grid (2x2 for 3 panes), not the square quad (256x256).
    w, h = _dims(out)
    assert (w, h) == (2 * 256 + 8, 2 * (256 + 16) + 8) and (w, h) != (256, 256)


def test_it_reports_breakdown_brush_count_to_stderr(tmp_path, monkeypatch, capsys):
    # Arrange / Act
    proj = _project_room_pillar(tmp_path, monkeypatch)
    out = tmp_path / "b.png"
    assert dispatch.dispatch(_prev(proj, out, names=["Room", "Pillar"], layout="breakdown", size=256)) == 0
    # Assert: the brush + point-actor count summary goes to stderr; stdout stays the written path.
    err = capsys.readouterr()
    assert "breakdown: 2 brushes, 0 point actors" in err.err
    assert str(out) in err.out


def test_it_zooms_by_brush_name(tmp_path, monkeypatch):
    # Arrange: --frame NAME (no colon) frames that whole brush; differs from the un-zoomed whole-set frame.
    proj = _project_with_two_brushes(tmp_path, monkeypatch)
    out = tmp_path / "o.png"
    # Act
    assert dispatch.dispatch(_prev(proj, out, names=["WallA", "WallB"], layout="single",
                                   frame="WallB")) == 0
    zoomed = out.read_bytes()
    assert dispatch.dispatch(_prev(proj, out, names=["WallA", "WallB"], layout="single",
                                   frame_tightness=0.0)) == 0
    # Assert: framing by the WallB name actually reframed vs the whole-set frame.
    assert zoomed != out.read_bytes()


def test_it_zooms_by_point_actor_name(tmp_path, monkeypatch):
    # A bare --frame NAME on a POINT actor frames its Location ± extent (no polys) — a clean render.
    proj = _project_with_light(tmp_path, monkeypatch)
    out = tmp_path / "o.png"
    with mock.patch("uedcli.cli.resources.class_defaults", return_value={}), \
         mock.patch("uedcli.cli.resources.texture_resolver", return_value=None):
        assert dispatch.dispatch(_prev(proj, out, names=["Torch"], layout="single", frame="Torch")) == 0
    assert _is_png(out)


def test_it_gives_each_point_actor_a_breakdown_pane(tmp_path, monkeypatch):
    # A point actor now gets its OWN captioned pane (marker/sprite; no faces to number) alongside the
    # SCENE overview — actors are identified by pane, not a legend. One point → SCENE + 1 pane = 2
    # panes → a 2x1 grid (2 cells wide, 1 caption+pane tall).
    proj = _project_with_light(tmp_path, monkeypatch)
    out = tmp_path / "b.png"
    size = 256
    with mock.patch("uedcli.cli.resources.class_defaults", return_value={}), \
         mock.patch("uedcli.cli.resources.texture_resolver", return_value=None):
        assert dispatch.dispatch(_prev(proj, out, names=["Torch"], layout="breakdown", size=size)) == 0
    assert _dims(out) == (2 * size + 8, size + 16)     # SCENE + the Torch point pane


def test_a_lone_point_breakdown_pane_centers_its_marker(tmp_path, monkeypatch):
    # Regression (cold-review finding): a marker-only point has a ZERO-size world AABB; framing its pane
    # via `_world_aabb([point])` would collapse `_framing` to a 1-unit window and jam the marker into the
    # pane's bottom-left corner. `_point_pane_region` synthesizes a real Location±margin box, so the
    # marker sits CENTERED. Without the fix this fails: centre empty, corner filled.
    from uedcli.preview import BG
    proj = _project_with_light(tmp_path, monkeypatch)
    out = tmp_path / "b.png"
    size = 256
    with mock.patch("uedcli.cli.resources.class_defaults", return_value={}), \
         mock.patch("uedcli.cli.resources.texture_resolver", return_value=None):
        assert dispatch.dispatch(_prev(proj, out, names=["Torch"], layout="breakdown", size=size)) == 0
    img = _img(out)
    px0, py0 = size + 8, 16                                 # the point pane is the 2nd cell (col 1, row 0)
    cx, cy = px0 + size // 2, py0 + size // 2

    def nonbg(x, y):
        return _pixel(img, x, y) != (BG, BG, BG)
    assert any(nonbg(x, y) for x in range(cx - 12, cx + 12) for y in range(cy - 12, cy + 12))
    assert not any(nonbg(x, y) for x in range(px0 + 2, px0 + 14)
                   for y in range(py0 + size - 14, py0 + size - 2))


def test_it_renders_brush_colors_legend_differently_from_csg(tmp_path, monkeypatch):
    # Arrange
    proj = _project_with_two_brushes(tmp_path, monkeypatch)
    csg_out, legend_out = tmp_path / "csg.png", tmp_path / "legend.png"
    # Act
    assert dispatch.dispatch(_prev(proj, csg_out, names=["WallA"], layout="single",
                                   brush_colors="csg", size=256)) == 0
    assert dispatch.dispatch(_prev(proj, legend_out, names=["WallA"], layout="single",
                                   brush_colors="legend", size=256)) == 0
    # Assert: recolouring the wireframe by tint yields a different image (and still a valid PNG).
    assert legend_out.read_bytes() != csg_out.read_bytes()
    assert _is_png(legend_out)


# ── addressable coordinate grid (always on): stderr legend, --json, --grid ──────────────────────
import json as _json
import re as _re


def test_it_always_prints_the_grid_legend_to_stderr_single(tmp_path, monkeypatch, capsys):
    proj = _project_with_two_brushes(tmp_path, monkeypatch)
    out = tmp_path / "o.png"
    assert dispatch.dispatch(_prev(proj, out, names=["WallA", "WallB"], layout="single")) == 0
    cap = capsys.readouterr()
    assert cap.out.strip() == str(out.with_suffix(".png"))          # stdout stays the bare path
    assert "grid: 12×12 columns A–L, rows 1–12" in cap.err          # density header
    # each actor gets an unqualified letter+number cell (single view)
    assert _re.search(r"^WallA  [A-Z]+\d+", cap.err, _re.M)
    assert _re.search(r"^WallB  [A-Z]+\d+", cap.err, _re.M)


def test_it_pane_qualifies_the_legend_under_quad(tmp_path, monkeypatch, capsys):
    proj = _project_with_two_brushes(tmp_path, monkeypatch)
    out = tmp_path / "o.png"
    assert dispatch.dispatch(_prev(proj, out, names=["WallA", "WallB"], layout="quad")) == 0
    err = capsys.readouterr().err
    line = next(ln for ln in err.splitlines() if ln.startswith("WallA"))
    assert _re.search(r"Top:[A-Z]+\d+ Front:[A-Z]+\d+ Side:[A-Z]+\d+ Iso:[A-Z]+\d+", line)


def test_json_emits_the_grid_object_to_stdout(tmp_path, monkeypatch, capsys):
    proj = _project_with_two_brushes(tmp_path, monkeypatch)
    out = tmp_path / "o.png"
    assert dispatch.dispatch(_prev(proj, out, names=["WallA", "WallB"], layout="single",
                                   view="top", json=True)) == 0
    cap = capsys.readouterr()
    obj = _json.loads(cap.out)                                       # stdout is the JSON, not the path
    assert obj["image"] == str(out.with_suffix(".png"))
    assert obj["grid"] == {"cols": 12, "rows": 12}
    assert set(obj["actors"]) == {"WallA", "WallB"}
    wa = obj["actors"]["WallA"]
    assert set(wa["panes"]) == {"Top"}                              # single view keyed by --view
    assert _re.fullmatch(r"[A-Z]+\d+", wa["panes"]["Top"]["cell"])
    assert wa["hidden"] is False
    assert "grid: 12×12" in cap.err                                 # legend still on stderr


def test_without_json_stdout_is_the_bare_path(tmp_path, monkeypatch, capsys):
    proj = _project_with_two_brushes(tmp_path, monkeypatch)
    out = tmp_path / "o.png"
    assert dispatch.dispatch(_prev(proj, out, names=["WallA"], layout="single")) == 0
    assert capsys.readouterr().out.strip() == str(out.with_suffix(".png"))


def test_grid_density_override_changes_the_addresses(tmp_path, monkeypatch, capsys):
    proj = _project_with_two_brushes(tmp_path, monkeypatch)
    out = tmp_path / "o.png"
    assert dispatch.dispatch(_prev(proj, out, names=["WallA", "WallB"], layout="single", grid=4)) == 0
    err4 = capsys.readouterr().err
    assert "grid: 4×4 columns A–D, rows 1–4" in err4
    assert dispatch.dispatch(_prev(proj, out, names=["WallA", "WallB"], layout="single", grid=12)) == 0
    err12 = capsys.readouterr().err
    assert err4 != err12                                            # different density → different cells


def test_grid_zero_is_a_clean_named_error(tmp_path, monkeypatch, capsys):
    proj = _project_with_two_brushes(tmp_path, monkeypatch)
    rc = dispatch.dispatch(_prev(proj, tmp_path / "o.png", names=["WallA"], grid=0))
    err = capsys.readouterr().err
    assert rc == 2 and "--grid must be in [1, 52], got 0" in err and "Traceback" not in err


def test_grid_too_large_is_a_clean_named_error(tmp_path, monkeypatch, capsys):
    proj = _project_with_two_brushes(tmp_path, monkeypatch)
    rc = dispatch.dispatch(_prev(proj, tmp_path / "o.png", names=["WallA"], grid=999))
    err = capsys.readouterr().err
    assert rc == 2 and "--grid must be in [1, 52], got 999" in err and "Traceback" not in err


def test_same_cell_collision_co_lists_both_actors(tmp_path, monkeypatch, capsys):
    # --grid 1 collapses the whole image to one cell (A1): both actors land there and each keeps its
    # own legend line (a collision is not an error).
    proj = _project_with_two_brushes(tmp_path, monkeypatch)
    out = tmp_path / "o.png"
    assert dispatch.dispatch(_prev(proj, out, names=["WallA", "WallB"], layout="single", grid=1)) == 0
    err = capsys.readouterr().err
    assert _re.search(r"^WallA  A1", err, _re.M) and _re.search(r"^WallB  A1", err, _re.M)


def test_empty_actor_set_is_exit_0_with_no_cells(tmp_path, monkeypatch, capsys):
    from uedcli.cli import rendering
    proj = _project_with_two_brushes(tmp_path, monkeypatch)
    out = tmp_path / "o.png"
    rc = rendering.render_actors_to_out([], _prev(proj, out, layout="single", json=True))
    assert rc == 0
    obj = _json.loads(capsys.readouterr().out)
    assert obj["actors"] == {}


def test_breakdown_emits_the_pane0_legend_single_view_unqualified(tmp_path, monkeypatch, capsys):
    # Under --layout breakdown the gutter + legend ride pane 0 only; the legend reads off that single
    # whole-scene view, so it is unqualified (no Top:/Front: prefixes) like a `single` render.
    proj = _project_room_pillar(tmp_path, monkeypatch)
    out = tmp_path / "b.png"
    assert dispatch.dispatch(_prev(proj, out, names=["Room", "Pillar"], layout="breakdown",
                                   size=256)) == 0
    err = capsys.readouterr().err
    assert "grid: 12×12 columns A–L, rows 1–12" in err
    assert _re.search(r"^Room  [A-Z]+\d+", err, _re.M)
    assert "Top:" not in err and "Iso:" not in err                 # single-view, not pane-qualified
