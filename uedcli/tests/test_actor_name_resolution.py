"""Dispatch-layer actor-name resolution tests: case-insensitive lookup, clear errors,
canonical recording. Each test builds an in-memory fixture Level and re-points the trunk seam
(`level_sources.resolve_level_source`) at a Mock `TrunkLevelSource` whose `load()` returns it, then
invokes `dispatch._dispatch` directly with a SimpleNamespace args object.

Name resolution and canonical-name behaviour are pure model-side transforms (unchanged by the
session-store removal), so they are asserted on the captured `src.save(...)` call: the written
`level` (whose dict keys ARE the canonical actor names), the recorded `args`, and `touched`.

Fixture level: `HelperLight0` (Engine.Light point, Group=cells, Location=(100,200,300))
and `Brush1` (Engine.Brush cube, CSG_Add, Group=cells).
"""
from __future__ import annotations

from decimal import Decimal
from types import SimpleNamespace
from unittest import mock

from uedcli.cli import dispatch as dispatch_mod
from uedcli.cli import level_sources
from uedcli.builders import cube, make_brush_actor
from uedcli.emit import emit_actor_t3d
from uedcli.model import Actor, parse_t3d


# ── Fixture helpers ───────────────────────────────────────────────────────────


def _light_t3d() -> str:
    a = Actor(
        name="HelperLight0", cls="Engine.Light",
        location=(Decimal(100), Decimal(200), Decimal(300)),
        props=[("Group", "cells"), ("LightBrightness", "100")])
    return emit_actor_t3d(a)


def _brush_t3d() -> str:
    a = make_brush_actor(
        "Brush1", cube(64, 64, 64),
        location=(Decimal(0), Decimal(0), Decimal(0)),
        csg="add", group="cells")
    return emit_actor_t3d(a)


def _fixture_level():
    """The HelperLight0 + Brush1 level, built in-memory (replaces the old `_seed_store`)."""
    lv = parse_t3d("Begin Map\n" + _light_t3d() + _brush_t3d() + "End Map\n")
    lv.order = ["HelperLight0", "Brush1"]
    return lv


def _fake_src(level):
    """Stand-in `TrunkLevelSource`: `load()` returns `level`; `save()` is a Mock capturing the
    recorded call (see test_dispatch.py). Content verbs are pure model-side transforms, so mocking
    the seam asserts the transform exactly."""
    src = mock.Mock()
    src.load.return_value = level
    return src


# ── actor move ────────────────────────────────────────────────────────────────


def test_it_actor_move_resolves_case_insensitively(tmp_path, monkeypatch, capsys):
    args = SimpleNamespace(
        cmd="actor", sub="move", name="brush1",
        to=None, by=(Decimal(0), Decimal(0), Decimal(10)),
        container="dx-lum-uned")
    src = _fake_src(_fixture_level())
    with mock.patch("uedcli.cli.level_sources.resolve_level_source", return_value=src):
        rc = dispatch_mod._dispatch(args)
    assert rc == 0


def test_it_actor_move_errors_on_missing(tmp_path, monkeypatch, capsys):
    args = SimpleNamespace(
        cmd="actor", sub="move", name="NoSuch",
        to=None, by=(Decimal(0), Decimal(0), Decimal(10)),
        container="dx-lum-uned")
    src = _fake_src(_fixture_level())
    with mock.patch("uedcli.cli.level_sources.resolve_level_source", return_value=src):
        rc = dispatch_mod._dispatch(args)
    assert rc == 2
    err = capsys.readouterr().err
    assert "Actor not found: NoSuch" in err
    assert "Traceback" not in err


def test_it_actor_move_records_canonical_name(tmp_path, monkeypatch):
    args = SimpleNamespace(
        cmd="actor", sub="move", name="brush1",
        to=None, by=(Decimal(0), Decimal(0), Decimal(10)),
        container="dx-lum-uned")
    src = _fake_src(_fixture_level())
    with mock.patch("uedcli.cli.level_sources.resolve_level_source", return_value=src):
        dispatch_mod._dispatch(args)
    saved = src.save.call_args.kwargs
    assert saved["args"]["name"] == "Brush1"
    # Canonical names are the level's dict keys — the raw-case name is never a key.
    assert "Brush1" in saved["level"].actors
    assert "brush1" not in saved["level"].actors


def test_it_actor_move_records_canonical_name_in_touched(tmp_path, monkeypatch):
    """The write must record the canonical name, not the user-typed name."""
    args = SimpleNamespace(
        cmd="actor", sub="move", name="brush1",
        to=None, by=(Decimal(0), Decimal(0), Decimal(10)),
        container="dx-lum-uned")
    src = _fake_src(_fixture_level())
    with mock.patch("uedcli.cli.level_sources.resolve_level_source", return_value=src):
        dispatch_mod._dispatch(args)
    saved = src.save.call_args.kwargs
    assert saved["args"]["name"] == "Brush1"
    assert saved["touched"] == ["Brush1"]
    assert "Brush1" in saved["level"].actors
    assert "brush1" not in saved["level"].actors


# ── actor prop (name resolution; the verb's full behaviour is in test_actor_prop.py) ────────────


def _group_schema(cls=None, project=None):
    """A one-property schema (Actor.Group, a NameProperty) so `--set Group=…` validates without the
    v68 install. Patched over `resources.class_schema` (the schema seam)."""
    from uedcli.uprops import Prop
    return {"group": Prop(name="Group", kind="NameProperty", array_dim=1, property_flags=0,
                          type_ref=0, type_name=None, owner="Engine.Actor")}


def test_it_actor_prop_resolves_case_insensitively(tmp_path, monkeypatch):
    args = SimpleNamespace(cmd="actor", sub="prop", propsub="set", name="brush1",
                           tokens=["Group=walls"], kv=False)
    src = _fake_src(_fixture_level())
    with mock.patch("uedcli.cli.level_sources.resolve_level_source", return_value=src), \
            mock.patch("uedcli.cli.resources.class_schema", _group_schema):
        assert dispatch_mod._dispatch(args) == 0


def test_it_actor_prop_errors_on_missing(tmp_path, monkeypatch, capsys):
    args = SimpleNamespace(cmd="actor", sub="prop", propsub="set", name="NoSuch",
                           tokens=["Group=walls"], kv=False)
    src = _fake_src(_fixture_level())
    with mock.patch("uedcli.cli.level_sources.resolve_level_source", return_value=src), \
            mock.patch("uedcli.cli.resources.class_schema", _group_schema):
        rc = dispatch_mod._dispatch(args)
    assert rc == 2
    err = capsys.readouterr().err
    assert "Actor not found: NoSuch" in err
    assert "Traceback" not in err


def test_it_actor_prop_records_canonical_name(tmp_path, monkeypatch):
    args = SimpleNamespace(cmd="actor", sub="prop", propsub="set", name="brush1",
                           tokens=["Group=walls"], kv=False)
    src = _fake_src(_fixture_level())
    with mock.patch("uedcli.cli.level_sources.resolve_level_source", return_value=src), \
            mock.patch("uedcli.cli.resources.class_schema", _group_schema):
        dispatch_mod._dispatch(args)
    assert src.save.call_args.kwargs["args"]["name"] == "Brush1"


# ── actor delete ──────────────────────────────────────────────────────────────


def test_it_actor_delete_resolves_case_insensitively(tmp_path, monkeypatch):
    # Both wrong-case names → should still remove both actors
    args = SimpleNamespace(
        cmd="actor", sub="delete", names=["brush1", "helperlight0"],
        container="dx-lum-uned")
    src = _fake_src(_fixture_level())
    with mock.patch("uedcli.cli.level_sources.resolve_level_source", return_value=src):
        rc = dispatch_mod._dispatch(args)
    assert rc == 0
    actors = src.save.call_args.kwargs["level"].actors
    assert "Brush1" not in actors
    assert "HelperLight0" not in actors


def test_it_actor_delete_errors_on_missing(tmp_path, monkeypatch, capsys):
    args = SimpleNamespace(
        cmd="actor", sub="delete", names=["NoSuch"],
        container="dx-lum-uned")
    src = _fake_src(_fixture_level())
    with mock.patch("uedcli.cli.level_sources.resolve_level_source", return_value=src):
        rc = dispatch_mod._dispatch(args)
    assert rc == 2
    err = capsys.readouterr().err
    assert "Actors not found: NoSuch" in err
    assert "Traceback" not in err


def test_it_actor_delete_records_canonical_names(tmp_path, monkeypatch):
    args = SimpleNamespace(
        cmd="actor", sub="delete", names=["brush1", "helperlight0"],
        container="dx-lum-uned")
    src = _fake_src(_fixture_level())
    with mock.patch("uedcli.cli.level_sources.resolve_level_source", return_value=src):
        dispatch_mod._dispatch(args)
    assert src.save.call_args.kwargs["args"]["names"] == ["Brush1", "HelperLight0"]


# ── actor rotate ─────────────────────────────────────────────────────────────


def test_it_actor_rotate_resolves_case_insensitively(tmp_path, monkeypatch):
    args = SimpleNamespace(
        cmd="actor", sub="rotate", names=["brush1"],
        by=(Decimal(0), Decimal(90), Decimal(0)),
        pivot=None, pivot_actor=None,
        container="dx-lum-uned")
    src = _fake_src(_fixture_level())
    with mock.patch("uedcli.cli.level_sources.resolve_level_source", return_value=src):
        assert dispatch_mod._dispatch(args) == 0


def test_it_actor_rotate_deduplicates_mixed_case(tmp_path, monkeypatch):
    args = SimpleNamespace(
        cmd="actor", sub="rotate", names=["brush1", "BRUSH1"],
        by=(Decimal(0), Decimal(90), Decimal(0)),
        pivot=(Decimal(0), Decimal(0), Decimal(0)), pivot_actor=None,
        container="dx-lum-uned")
    src = _fake_src(_fixture_level())
    with mock.patch("uedcli.cli.level_sources.resolve_level_source", return_value=src):
        rc = dispatch_mod._dispatch(args)
    assert rc == 0
    # A 90° yaw rotation is applied exactly once — deduped to one canonical name.
    assert src.save.call_args.kwargs["args"]["names"] == ["Brush1"]


def test_it_actor_rotate_pivot_actor_resolves_case_insensitively(tmp_path, monkeypatch):
    args = SimpleNamespace(
        cmd="actor", sub="rotate", names=["brush1"],
        by=(Decimal(0), Decimal(90), Decimal(0)),
        pivot=None, pivot_actor="helperlight0",  # wrong case
        container="dx-lum-uned")
    src = _fake_src(_fixture_level())
    with mock.patch("uedcli.cli.level_sources.resolve_level_source", return_value=src):
        assert dispatch_mod._dispatch(args) == 0


def test_it_actor_rotate_errors_on_all_missing(tmp_path, monkeypatch, capsys):
    args = SimpleNamespace(
        cmd="actor", sub="rotate", names=["bad1", "bad2"],
        by=(Decimal(0), Decimal(90), Decimal(0)),
        pivot=None, pivot_actor=None,
        container="dx-lum-uned")
    src = _fake_src(_fixture_level())
    with mock.patch("uedcli.cli.level_sources.resolve_level_source", return_value=src):
        rc = dispatch_mod._dispatch(args)
    assert rc == 2
    err = capsys.readouterr().err
    assert "Actors not found: bad1, bad2" in err
    assert "Traceback" not in err


def test_it_actor_rotate_records_canonical_names(tmp_path, monkeypatch):
    args = SimpleNamespace(
        cmd="actor", sub="rotate", names=["brush1"],
        by=(Decimal(0), Decimal(90), Decimal(0)),
        pivot=None, pivot_actor=None,
        container="dx-lum-uned")
    src = _fake_src(_fixture_level())
    with mock.patch("uedcli.cli.level_sources.resolve_level_source", return_value=src):
        dispatch_mod._dispatch(args)
    saved = src.save.call_args.kwargs
    assert saved["args"]["names"] == ["Brush1"]
    assert "Brush1" in saved["level"].actors


def test_it_actor_rotate_pivot_actor_records_pivot_coords(tmp_path, monkeypatch):
    """Recorded `pivot` must be world coords of HelperLight0, NOT the actor name."""
    args = SimpleNamespace(
        cmd="actor", sub="rotate", names=["brush1"],
        by=(Decimal(0), Decimal(0), Decimal(90)),
        pivot=None, pivot_actor="helperlight0",
        container="dx-lum-uned")
    src = _fake_src(_fixture_level())
    with mock.patch("uedcli.cli.level_sources.resolve_level_source", return_value=src):
        dispatch_mod._dispatch(args)
    recorded_pivot = src.save.call_args.kwargs["args"]["pivot"]
    # HelperLight0 is at (100, 200, 300) — pivot coords must appear, not the actor name
    assert "100" in str(recorded_pivot) or "200" in str(recorded_pivot)
    assert "helperlight0" not in str(recorded_pivot)
    assert "HelperLight0" not in str(recorded_pivot)


# ── brush clip is no longer a by-name trunk edit ──────────────────────────────
# It became a stateless T3D-stdin filter (owner 2026-08-02); it resolves no actor name. Its
# behaviour, including the non-brush refusal, lives in `test_brush_clip.py`.


# ── brush vertex move ─────────────────────────────────────────────────────────


def test_it_brush_vertex_move_resolves_case_insensitively(tmp_path, monkeypatch):
    # Bypass geometry validation: we're testing name resolution, not geometry correctness.
    args = SimpleNamespace(
        cmd="brush", sub="vertex", vsub="move", name="brush1",
        at=[(Decimal(32), Decimal(-32), Decimal(-32))],
        to=None, by=(Decimal(0), Decimal(0), Decimal(0)),  # no-op move
        container="dx-lum-uned")
    src = _fake_src(_fixture_level())
    with mock.patch("uedcli.cli.level_sources.resolve_level_source", return_value=src):
        assert dispatch_mod._dispatch(args) == 0


def test_it_brush_vertex_move_errors_on_missing(tmp_path, monkeypatch, capsys):
    args = SimpleNamespace(
        cmd="brush", sub="vertex", vsub="move", name="NoSuch",
        at=[(Decimal(0), Decimal(0), Decimal(0))],
        to=None, by=(Decimal(0), Decimal(0), Decimal(10)),
        container="dx-lum-uned")
    src = _fake_src(_fixture_level())
    with mock.patch("uedcli.cli.level_sources.resolve_level_source", return_value=src):
        rc = dispatch_mod._dispatch(args)
    assert rc == 2
    err = capsys.readouterr().err
    assert "Actor not found: NoSuch" in err
    assert "Traceback" not in err


def test_it_brush_vertex_move_records_canonical_name(tmp_path, monkeypatch):
    # No-op move (by zero): still resolves the name and records it canonically.
    args = SimpleNamespace(
        cmd="brush", sub="vertex", vsub="move", name="brush1",
        at=[(Decimal(32), Decimal(-32), Decimal(-32))],
        to=None, by=(Decimal(0), Decimal(0), Decimal(0)),
        container="dx-lum-uned")
    src = _fake_src(_fixture_level())
    with mock.patch("uedcli.cli.level_sources.resolve_level_source", return_value=src):
        dispatch_mod._dispatch(args)
    assert src.save.call_args.kwargs["args"]["name"] == "Brush1"


# ── actor diagram ─────────────────────────────────────────────────────────────


def test_it_actor_preview_resolves_case_insensitively(tmp_path, monkeypatch, capsys):
    args = SimpleNamespace(
        cmd="actor", sub="diagram", names=["brush1"], from_t3d=None,
        out=None,
        container="dx-lum-uned")
    src = _fake_src(_fixture_level())
    with mock.patch("uedcli.cli.level_sources.resolve_level_source", return_value=src), \
         mock.patch("uedcli.cli.rendering.render_actors_to_out", return_value=0) as render:
        rc = dispatch_mod._dispatch(args)
    assert rc == 0
    assert render.called


def test_it_actor_preview_errors_on_missing(tmp_path, monkeypatch, capsys):
    args = SimpleNamespace(
        cmd="actor", sub="diagram", names=["NoSuch"], from_t3d=None,
        out=None,
        container="dx-lum-uned")
    src = _fake_src(_fixture_level())
    with mock.patch("uedcli.cli.level_sources.resolve_level_source", return_value=src), \
         mock.patch("uedcli.cli.rendering.render_actors_to_out", return_value=0):
        rc = dispatch_mod._dispatch(args)
    assert rc == 2
    err = capsys.readouterr().err
    assert "Actors not found: NoSuch" in err
    assert "Traceback" not in err


def test_it_actor_preview_errors_when_one_valid_one_invalid(tmp_path, monkeypatch, capsys):
    """One valid + one invalid name → still errors (not partial render)."""
    args = SimpleNamespace(
        cmd="actor", sub="diagram", names=["brush1", "NoSuch"], from_t3d=None,
        out=None,
        container="dx-lum-uned")
    src = _fake_src(_fixture_level())
    with mock.patch("uedcli.cli.level_sources.resolve_level_source", return_value=src), \
         mock.patch("uedcli.cli.rendering.render_actors_to_out", return_value=0):
        rc = dispatch_mod._dispatch(args)
    assert rc == 2


# ── poly list ─────────────────────────────────────────────────────────────────


def test_it_poly_list_resolves_case_insensitively(tmp_path, monkeypatch, capsys):
    args = SimpleNamespace(
        cmd="brush", sub="poly", polysub="list", name="brush1",
        container="dx-lum-uned")
    src = _fake_src(_fixture_level())
    with mock.patch("uedcli.cli.level_sources.resolve_level_source", return_value=src):
        assert dispatch_mod._dispatch(args) == 0
    out = capsys.readouterr().out
    assert "Brush1" in out


def test_it_poly_list_errors_on_missing(tmp_path, monkeypatch, capsys):
    args = SimpleNamespace(
        cmd="brush", sub="poly", polysub="list", name="NoSuch",
        container="dx-lum-uned")
    src = _fake_src(_fixture_level())
    with mock.patch("uedcli.cli.level_sources.resolve_level_source", return_value=src):
        rc = dispatch_mod._dispatch(args)
    assert rc == 2
    err = capsys.readouterr().err
    assert "Actor not found: NoSuch" in err
    assert "Traceback" not in err


# ── brush vertex list ─────────────────────────────────────────────────────────


def test_it_brush_vertex_list_resolves_case_insensitively(tmp_path, monkeypatch, capsys):
    args = SimpleNamespace(
        cmd="brush", sub="vertex", vsub="list", name="brush1",
        container="dx-lum-uned")
    src = _fake_src(_fixture_level())
    with mock.patch("uedcli.cli.level_sources.resolve_level_source", return_value=src):
        assert dispatch_mod._dispatch(args) == 0


def test_it_brush_vertex_list_errors_on_missing(tmp_path, monkeypatch, capsys):
    args = SimpleNamespace(
        cmd="brush", sub="vertex", vsub="list", name="NoSuch",
        container="dx-lum-uned")
    src = _fake_src(_fixture_level())
    with mock.patch("uedcli.cli.level_sources.resolve_level_source", return_value=src):
        rc = dispatch_mod._dispatch(args)
    assert rc == 2
    err = capsys.readouterr().err
    assert "Actor not found: NoSuch" in err
    assert "Traceback" not in err


# ── actor prop get ────────────────────────────────────────────────────────────────


def test_it_actor_prop_get_resolves_case_insensitively(tmp_path, monkeypatch, capsys):
    args = SimpleNamespace(
        cmd="actor", sub="prop", propsub="get", name="brush1", tokens=["Group"], kv=False,
        container="dx-lum-uned")
    src = _fake_src(_fixture_level())
    with mock.patch("uedcli.cli.level_sources.resolve_level_source", return_value=src), \
            mock.patch("uedcli.cli.resources.class_schema", _group_schema):
        rc = dispatch_mod._dispatch(args)
    assert rc == 0
    assert "cells" in capsys.readouterr().out


def test_it_actor_prop_get_errors_on_missing(tmp_path, monkeypatch, capsys):
    args = SimpleNamespace(
        cmd="actor", sub="prop", propsub="get", name="NoSuch", tokens=["Group"], kv=False,
        container="dx-lum-uned")
    src = _fake_src(_fixture_level())
    with mock.patch("uedcli.cli.level_sources.resolve_level_source", return_value=src):
        rc = dispatch_mod._dispatch(args)
    assert rc == 2
    err = capsys.readouterr().err
    assert "Actor not found: NoSuch" in err
    assert "Traceback" not in err


# ── poly set recording canonical names ───────────────────────────────────────


def test_it_poly_set_records_canonical_brush_name_in_touched(tmp_path, monkeypatch):
    """apply_surface_edit canonicalizes brush name; touched list must use canonical name."""
    args = SimpleNamespace(
        cmd="brush", sub="poly", polysub="set", targets=["brush1:all"],
        texture="Engine.DefaultTexture", add_flags=None, remove_flags=None,
        container="dx-lum-uned")
    src = _fake_src(_fixture_level())
    with mock.patch("uedcli.cli.level_sources.resolve_level_source", return_value=src):
        rc = dispatch_mod._dispatch(args)
    assert rc == 0
    saved = src.save.call_args.kwargs
    # targets in rec_args stays as the user-typed tokens (poly set exemption)
    assert "brush1:all" in saved["args"]["targets"]
    # touched carries the canonical name; the level's dict is keyed canonically.
    assert saved["touched"] == ["Brush1"]
    assert "Brush1" in saved["level"].actors
    assert "brush1" not in saved["level"].actors
