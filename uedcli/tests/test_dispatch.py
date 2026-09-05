import pytest

from argparse import Namespace
from decimal import Decimal
from types import SimpleNamespace
from unittest import mock

from uedcli.cli import dispatch as dispatch_mod
from uedcli.cli import resources
from uedcli.builders import cube, make_brush_actor
from uedcli.cli.dispatch import dispatch
from uedcli.model import Actor, Level, parse_t3d
from uedcli.uprops import Prop
from uedcli.vertex import weld_vertices


def _fake_class_index(hierarchy):
    """Minimal `ClassIndex` stand-in for `actor find --subclass-of`. `hierarchy`: {fqcn: [self,
    …ancestors]}; a bare name resolves by matching the leaf case-insensitively."""
    idx = mock.Mock()
    idx.empty = False                                     # a property on the real ClassIndex, not a call
    idx._qualify_bare.side_effect = lambda bare: next(
        (fq for fq in hierarchy if fq.split(".")[-1].casefold() == bare.casefold()), None)
    idx.class_exists.side_effect = lambda fq: fq in hierarchy
    idx.descends_from.side_effect = lambda fq, base: base.casefold() in {
        a.casefold() for a in hierarchy.get(fq, [])}
    return idx


_LIGHT_H = {"Engine.Light": ["Engine.Light"],
            "Engine.Spotlight": ["Engine.Spotlight", "Engine.Light"],
            "Engine.Brush": ["Engine.Brush"]}


def _scfind_args(**kw):
    base = dict(cmd="actor", sub="find", name=[], cls=[], subclass_of=[], group=[],
                folder=[], no_folder=False, kind=None, prop=[], json=False)
    base.update(kw)
    return SimpleNamespace(**base)


def _light_level():
    lv = Level()
    lv.actors["L"] = Actor(name="L", cls="Engine.Light")
    lv.actors["S"] = Actor(name="S", cls="Engine.Spotlight")   # descends from Light
    lv.actors["B"] = Actor(name="B", cls="Engine.Brush")
    lv.order = ["L", "S", "B"]
    return lv


def _run_find(args, level, hierarchy=_LIGHT_H):
    with mock.patch("uedcli.cli.level_sources.resolve_level_source", return_value=_fake_src(level)), \
            mock.patch("uedcli.cli.resources.class_index", return_value=_fake_class_index(hierarchy)), \
            mock.patch("uedcli.cli.resources.resolve_project", return_value=object()):
        return dispatch(args)


def test_find_subclass_of_matches_descendants_not_just_exact(capsys):
    # --subclass-of Light matches Light AND its Spotlight subclass, but not Brush (the footgun fix)
    assert _run_find(_scfind_args(subclass_of=["Engine.Light"]), _light_level()) == 0
    assert capsys.readouterr().out.splitlines() == ["L", "S"]


def test_find_exact_class_is_exact_only(capsys):
    # --exact-class Light matches ONLY Light — NOT the Spotlight subclass (the old --class behaviour)
    assert _run_find(_scfind_args(cls=["Engine.Light"]), _light_level()) == 0
    assert capsys.readouterr().out.splitlines() == ["L"]


def test_find_exact_class_ors_with_subclass_of(capsys):
    # the two class flags OR within the class dimension
    assert _run_find(_scfind_args(cls=["Engine.Brush"], subclass_of=["Engine.Light"]),
                     _light_level()) == 0
    assert capsys.readouterr().out.splitlines() == ["L", "S", "B"]


def test_find_subclass_of_unknown_base_exits_2(capsys):
    assert _run_find(_scfind_args(subclass_of=["Engine.Nope"]), _light_level()) == 2
    assert "unknown class" in capsys.readouterr().err


def _brush_level():
    a = make_brush_actor("B1", cube(64, 64, 64),
                         location=(Decimal(0), Decimal(0), Decimal(0)))
    lv = Level()
    lv.actors["B1"] = a
    return lv


def _fake_src(level):
    """Stand-in `TrunkLevelSource` (git-native trunk seam): `load()` returns `level`; `save()` is a
    Mock capturing the recorded call. Content verbs are pure model-side transforms, so mocking the
    seam asserts the transform exactly (the on-disk trunk round-trip is covered by
    test_trunk_verbs.py). Replaces the deleted `_load_main`/`_resolve_store`/`record_mutation` mocks."""
    src = mock.Mock()
    src.load.return_value = level
    return src


def test_dispatch_vertex_list_prints_table(capsys):
    args = SimpleNamespace(cmd="brush", sub="vertex", vsub="list", name="B1", container="c")
    with mock.patch("uedcli.cli.level_sources.resolve_level_source", return_value=_fake_src(_brush_level())):
        rc = dispatch(args)
    assert rc == 0
    assert "B1: 8 vertices" in capsys.readouterr().out


def test_dispatch_vertex_move_by_converts_world_to_local_model_side():
    """vertex move is a pure model-side transform: no editor, the moved brush
    lands in the level written back through the trunk seam's `save`."""
    args = SimpleNamespace(
        cmd="brush", sub="vertex", vsub="move", name="B1", container="c",
        at=[(Decimal(-32), Decimal(-32), Decimal(32)),
            (Decimal(32), Decimal(-32), Decimal(32))],
        to=None, by=(Decimal(0), Decimal(0), Decimal(16)))
    src = _fake_src(_brush_level())
    with mock.patch("uedcli.cli.level_sources.resolve_level_source", return_value=src):
        rc = dispatch(args)
    assert rc == 0
    moved = src.save.call_args.kwargs["level"].actors["B1"]
    coords = {w.coord for w in weld_vertices(moved.brush)}
    assert (Decimal(-32), Decimal(-32), Decimal(48)) in coords


# The `record_mutation` unit tests were removed with the function in the session-store un-wire
# (slice 4): the trunk records nothing of its own — git is the history, so there is no
# CommandRecord / commit_command / level_hash side effect to assert. The model-side transforms
# those tests exercised are covered by the per-verb tests here (re-pointed to the trunk seam) and
# the on-disk round-trip by test_trunk_verbs.py.


# ── M5: builder-brush exact-match heuristic ───────────────────────────────────


_BUILDER_BRUSH_BLOCK = (
    "Begin Actor Class=Brush Name=Brush0\n"
    "    Begin Brush Name=Brush\n"
    "        Begin PolyList\n"
    "            Begin Polygon\n"
    "                Vertex   -00128.000000,-00128.000000,-00128.000000\n"
    "                Vertex   -00128.000000,+00128.000000,-00128.000000\n"
    "                Vertex   -00128.000000,+00128.000000,+00128.000000\n"
    "            End Polygon\n"
    "        End PolyList\n"
    "    End Brush\n"
    "    Name=\"Brush0\"\n"
    "End Actor\n"
)
_CONTENT_BRUSH_BLOCK = (
    "Begin Actor Class=Brush Name=Brush0123\n"
    "     CsgOper=CSG_Add\n"
    "    Begin Brush Name=Model5\n"
    "        Begin PolyList\n"
    "            Begin Polygon\n"
    "                Vertex   -00128.000000,-00128.000000,-00128.000000\n"
    "                Vertex   -00128.000000,+00128.000000,-00128.000000\n"
    "                Vertex   -00128.000000,+00128.000000,+00128.000000\n"
    "            End Polygon\n"
    "        End PolyList\n"
    "    End Brush\n"
    "    Name=\"Brush0123\"\n"
    "End Actor\n"
)


def _added_with_stem(level, stem, before=frozenset()):
    """The single newly-added actor whose git-native random-suffix name is `<stem>_<6 chars>`
    (decisions 2026-07-05 15:11). `actor add` on the trunk mints these, so tests can't assert a
    fixed name — they assert the stem + suffix shape and that pre-existing actors survive."""
    added = [n for n in level.actors if n not in before]
    matches = [n for n in added
               if n.rpartition("_")[0] == stem and len(n.rpartition("_")[2]) == 6]
    assert len(matches) == 1, f"expected one {stem}_<suffix> among added {added}"
    return matches[0]


def test_add_skips_the_builder_brush_via_is_builder_brush(tmp_path):
    """The transient red builder brush (inner model `Brush`, no CsgOper) must be
    skipped; a content brush (inner `Model<N>` + CsgOper) must NOT be."""
    snippet = (
        "Begin Map\n"
        + _BUILDER_BRUSH_BLOCK
        + _CONTENT_BRUSH_BLOCK
        + "Begin Actor Class=Light Name=Light1\n    Name=\"Light1\"\nEnd Actor\n"
        "End Map\n"
    )
    snippet_file = tmp_path / "actors.t3d"
    snippet_file.write_text(snippet)

    src = _fake_src(parse_t3d("Begin Map\nEnd Map"))

    args = Namespace(cmd="actor", sub="add", file=str(snippet_file), container="dx-lum-uned")

    with mock.patch("uedcli.cli.level_sources.resolve_level_source", return_value=src):
        dispatch(args)

    actors = src.save.call_args.kwargs["level"].actors
    # Builder brush (model_name=Brush, no CsgOper) skipped; content brush Brush0123
    # (model_name=Model5, CsgOper=CSG_Add) + Light1 are added (2 actors, not 3). Trailing digits in
    # the authored Name are KEPT as the stem (Brush0123 → Brush0123_<suffix>), not stripped.
    assert len(actors) == 2, f"builder brush should be skipped, got {sorted(actors)}"
    brush_name = _added_with_stem(src.save.call_args.kwargs["level"], "Brush0123")
    assert actors[brush_name].brush.model_name == f"Model_{brush_name}"   # renamed with the actor
    _added_with_stem(src.save.call_args.kwargs["level"], "Light1")        # Light1 → Light1_<suffix>


# ── actor add - stdin + name allocation ──────────────────────────────────────


def _actor_add_dispatch(src, t3d_text, monkeypatch):
    """Drive `actor add -` with `t3d_text` supplied as fake stdin. `src` is the trunk seam whose
    `load()` returns the initial level; the written level is captured on `src.save`."""
    import io
    monkeypatch.setattr("sys.stdin", io.StringIO(t3d_text))
    args = Namespace(cmd="actor", sub="add", file="-", container="dx-lum-uned")
    with mock.patch("uedcli.cli.level_sources.resolve_level_source", return_value=src):
        rc = dispatch(args)
    return rc, src


def _light_t3d(name="Light1"):
    return f"Begin Actor Class=Light Name={name}\n    Name=\"{name}\"\nEnd Actor\n"


def _brush_t3d(name="Brush", model="Model_Brush"):
    return (
        f"Begin Actor Class=Engine.Brush Name={name}\n"
        f"    CsgOper=CSG_Add\n"
        f"    Begin Brush Name={model}\n"
        f"       Begin PolyList\n"
        f"       End PolyList\n"
        f"    End Brush\n"
        f"    Brush=Model'MyLevel.{model}'\n"
        f"    Name=\"{name}\"\n"
        f"End Actor\n"
    )


def test_actor_add_stdin_mints_a_random_suffix_name(monkeypatch):
    src = _fake_src(parse_t3d("Begin Map\nEnd Map"))
    rc, src = _actor_add_dispatch(src, _light_t3d("Light"), monkeypatch)
    assert rc == 0
    _added_with_stem(src.save.call_args.kwargs["level"], "Light")   # Light → Light_<6 chars>


def test_actor_add_stdin_preserves_a_pre_existing_same_stem_actor(monkeypatch):
    src = _fake_src(parse_t3d(_light_t3d("Light0")))
    rc, src = _actor_add_dispatch(src, _light_t3d("Light"), monkeypatch)
    assert rc == 0
    level = src.save.call_args.kwargs["level"]
    assert "Light0" in level.actors                                 # pre-existing preserved
    _added_with_stem(level, "Light", before={"Light0"})            # new distinct Light_<suffix>


def test_actor_add_stdin_keeps_trailing_digits_in_the_stem(monkeypatch):
    # Regression (board bug 3): a user-supplied numbered base-name must NOT have its trailing digits
    # stripped — `--base-name Pillar1`/`Pillar2` must stay distinguishable, not both collapse to
    # `Pillar`. Here Light99 → Light99_<suffix>, keeping the `99`.
    src = _fake_src(parse_t3d("Begin Map\nEnd Map"))
    rc, src = _actor_add_dispatch(src, _light_t3d("Light99"), monkeypatch)
    assert rc == 0
    _added_with_stem(src.save.call_args.kwargs["level"], "Light99")   # digits kept, stem = Light99


def test_actor_add_stdin_numbered_base_names_stay_distinct(monkeypatch):
    # `--base-name Pillar1` + `--base-name Pillar2` keep their numbers as separate stems (they no
    # longer both strip to `Pillar`), so the two added actors are name-distinguishable.
    src = _fake_src(parse_t3d("Begin Map\nEnd Map"))
    t3d = _light_t3d("Pillar1") + _light_t3d("Pillar2")
    rc, src = _actor_add_dispatch(src, t3d, monkeypatch)
    assert rc == 0
    level = src.save.call_args.kwargs["level"]
    stems = {n.rpartition("_")[0] for n in level.actors}
    assert {"Pillar1", "Pillar2"} <= stems                          # distinct numbered stems kept


def test_actor_add_stdin_two_same_stem_actors_get_distinct_names(monkeypatch):
    src = _fake_src(parse_t3d("Begin Map\nEnd Map"))
    t3d = _light_t3d("Light") + _light_t3d("Light")                 # identical names, same stem
    rc, src = _actor_add_dispatch(src, t3d, monkeypatch)
    assert rc == 0
    level = src.save.call_args.kwargs["level"]
    added = [n for n in level.actors if n.rpartition("_")[0] == "Light"]
    assert len(added) == 2 and len(set(added)) == 2                 # two, and distinct


def test_actor_add_stdin_duplicate_named_actors_all_survive(monkeypatch):
    # Regression for the CRITICAL dogfooding bug: concatenating N actors that share a Name
    # (e.g. 14 `brush build --base-name Merlon | actor add`) must keep ALL N. parse_t3d's
    # Name-keyed dict silently collapsed them to 1 before the uniquify loop ever ran.
    src = _fake_src(parse_t3d("Begin Map\nEnd Map"))
    t3d = "".join(_light_t3d("Merlon") for _ in range(14))          # 14 IDENTICAL Names
    rc, src = _actor_add_dispatch(src, t3d, monkeypatch)
    assert rc == 0
    level = src.save.call_args.kwargs["level"]
    added = [n for n in level.actors if n.rpartition("_")[0] == "Merlon"]
    assert len(added) == 14 and len(set(added)) == 14              # all 14, all distinct


def test_actor_add_stdin_mixed_duplicate_and_unique_all_survive(monkeypatch):
    # A mix of duplicate + already-unique Names: every input actor is preserved.
    src = _fake_src(parse_t3d("Begin Map\nEnd Map"))
    t3d = _light_t3d("Torch") + _light_t3d("Torch") + _light_t3d("Sconce")
    rc, src = _actor_add_dispatch(src, t3d, monkeypatch)
    assert rc == 0
    level = src.save.call_args.kwargs["level"]
    assert len([n for n in level.actors if n.rpartition("_")[0] == "Torch"]) == 2
    assert len([n for n in level.actors if n.rpartition("_")[0] == "Sconce"]) == 1


def test_actor_add_prints_names_to_stdout_and_count_to_stderr(monkeypatch, capsys):
    # spec 2026-07-18 §8: allocated Names go to STDOUT (one/line, allocation order) so they can
    # feed a `-` consumer; the human-facing count moves to STDERR (never pollutes the pipe).
    src = _fake_src(parse_t3d("Begin Map\nEnd Map"))
    t3d = "".join(_light_t3d("Merlon") for _ in range(3))
    rc, src = _actor_add_dispatch(src, t3d, monkeypatch)
    assert rc == 0
    cap = capsys.readouterr()
    assert "added 3 actor(s)" in cap.err                            # count → stderr
    assert "added" not in cap.out                                   # ...not stdout
    out_names = cap.out.splitlines()
    added = [n for n in src.save.call_args.kwargs["level"].actors
             if n.rpartition("_")[0] == "Merlon"]
    assert out_names == added                                       # names, allocation order


def test_actor_add_stdin_malformed_t3d(monkeypatch, capsys):
    src = _fake_src(parse_t3d("Begin Map\nEnd Map"))
    rc, src = _actor_add_dispatch(src, "not t3d at all %%%", monkeypatch)
    # malformed T3D parses to zero actors — a clean exit 2 ("nothing to add"), NOT a silent
    # rc=0 no-op (which reads as success while adding nothing). The trunk is left untouched.
    assert rc == 2
    assert "no actors found" in capsys.readouterr().err
    src.save.assert_not_called()


def test_actor_add_file_also_uses_name_allocation(tmp_path):
    t3d_file = tmp_path / "snippet.t3d"
    t3d_file.write_text(_light_t3d("Light"))
    src = _fake_src(parse_t3d("Begin Map\nEnd Map"))
    args = Namespace(cmd="actor", sub="add", file=str(t3d_file), container="dx-lum-uned")
    with mock.patch("uedcli.cli.level_sources.resolve_level_source", return_value=src):
        rc = dispatch(args)
    assert rc == 0
    _added_with_stem(src.save.call_args.kwargs["level"], "Light")


def test_actor_add_stdin_brush_model_name_updated(monkeypatch):
    """When a brush actor is renamed, its model_name and Brush= prop must also be updated."""
    src = _fake_src(parse_t3d("Begin Map\nEnd Map"))
    rc, src = _actor_add_dispatch(src, _brush_t3d("Brush", "Model_Brush"), monkeypatch)
    assert rc == 0
    level = src.save.call_args.kwargs["level"]
    name = _added_with_stem(level, "Brush")
    a = level.actors[name]
    assert a.brush.model_name == f"Model_{name}"
    props = dict(a.props)
    assert props["Brush"] == f"Model'MyLevel.Model_{name}'"


# ── brush builders ────────────────────────────────────────────────────────────


def test_dispatch_build_cube_writes_t3d_to_stdout(capsys):
    """`brush build cube` writes a T3D actor block to stdout (session-free)."""
    # --group was ditched (2026-07-24 17:04); Group now rides --prop Group= (schema-validated, covered
    # elsewhere). This session-free unit test asserts the schema-free class/location/CsgOper baking.
    args = Namespace(cmd="brush", sub="build", shape="cube",
                     width=256.0, breadth=128.0, height=64.0, at=(100.0, 200.0, 300.0),
                     base_name=None, csg="subtract", solidity="nonsolid", texture="T",
                     prop=None, folder=None, label=[], mover_class=None, rotate=None)
    rc = dispatch(args)
    assert rc == 0
    out = capsys.readouterr().out
    level = parse_t3d(out)
    assert len(level.actors) == 1
    a = next(iter(level.actors.values()))
    props = dict(a.props)
    assert a.cls == "Engine.Brush" and a.location == (100.0, 200.0, 300.0)
    assert props["CsgOper"] == "CSG_Subtract"
    assert a.brush is not None and len(a.brush.polys) == 6


def test_dispatch_build_staircase_writes_one_actor(capsys):
    """`brush build staircase` writes ONE non-convex-brush actor named `Staircase`
    (decisions 2026-07-21 12:06 — one-brush redo), with `2 + 4*steps` faces."""
    steps = 4
    args = Namespace(cmd="brush", sub="build", shape="staircase",
                     steps=steps, depth=32.0, rise=16.0, breadth=128.0,
                     at=(0.0, 0.0, 0.0), base_name=None, csg="add", solidity="solid",
                     group=None, texture=None)
    rc = dispatch(args)
    assert rc == 0
    out = capsys.readouterr().out
    from uedcli.model import parse_t3d_actors
    actors = [a for a in parse_t3d_actors(out) if a.brush is not None]
    assert [a.name for a in actors] == ["Staircase"]
    assert len(actors[0].brush.polys) == 2 + 4 * steps


# ── Task 9: namespaced surface + session resolution ──────────────────────────

import os as _os


# test_resolve_store_resumes_a_branch_for_an_id / _returns_none_for_no_session removed:
# `_resolve_store` deleted with the session store (slice 4).
# test_read_with_a_resolved_session_that_has_history_succeeds /
# test_read_with_a_never_opened_session_errors removed: the session read contract is gone —
# reads now come from the trunk (covered by test_trunk_verbs.py).


def test_reads_require_a_project_and_error_without_one(tmp_path, capsys, monkeypatch):
    monkeypatch.chdir(tmp_path)                    # control cwd: walk-up must find NO ambient project
    args = SimpleNamespace(cmd="actor", sub="find", name=[], cls=[], group=[], prop=[], kind=None,
                           container="c")
    with mock.patch.dict(_os.environ, {"UEDCLI_PROJECT": ""}, clear=False):
        rc = dispatch(args)
    # Git-native trunk: a read outside any uedcli project is a clean exit 2, not a traceback.
    err = capsys.readouterr().err
    assert rc == 2 and "not in a uedcli project" in err


# ── level apply route ─────────────────────────────────────────────────────────


# `level apply`'s 3-way reconcile / --check / mode-flag routing tests were removed with the verb in
# git-native slice 3 (`level apply` → the pure `level materialize`). `run_apply` itself is retained
# (dead, deleted in slice 6) and still covered directly by test_apply.py; the new `level materialize`
# routing is covered by test_materialize_verb.py.


# test_no_session_performs_edit_but_records_nothing removed: the `--no-session` scratch mode
# (edit without recording) was removed with the session store (slice 4) — every mutate verb now
# goes through the trunk seam. test_load_main_reconstructs_level_from_the_store removed: `_load_main`
# was deleted; trunk load is covered by test_trunk_verbs.py.


# ── Phase 5 Task 10: model-side mutate verbs ──────────────────────────────────


def test_actor_add_is_model_side_and_appends_order():
    src = _fake_src(parse_t3d("Begin Map\nEnd Map"))
    args = SimpleNamespace(
        cmd="actor", sub="add",
        file="-", container="ct")
    import io
    with mock.patch("uedcli.cli.level_sources.resolve_level_source", return_value=src), \
         mock.patch("sys.stdin",
                    io.StringIO("Begin Map\nBegin Actor Class=Light Name=NewLight\n"
                                "    Name=\"NewLight\"\nEnd Actor\nEnd Map")):
        assert dispatch_mod._dispatch(args) == 0
    saved = src.save.call_args.kwargs["level"]
    name = _added_with_stem(saved, "NewLight")      # git-native random-suffix name
    assert saved.order == [name]                    # the add appended to order


# test_no_session_read_operates_on_an_empty_scratch_level_not_a_crash removed: `--no-session`
# (empty scratch level) was removed with the session store (slice 4).


def _preview_proj(tmp_path, actors, order, monkeypatch):
    """Write a trunk with the given actors, select it via $UEDCLI_LEVEL, return the project dir."""
    from uedcli import trunk
    from uedcli.model import Level
    proj = tmp_path / "repo"; (proj / "maps" / "lvl").mkdir(parents=True)
    (proj / "uedcli.toml").write_text('game = "deusex"\n')
    trunk.write_level(proj / "maps" / "lvl", Level(actors=actors, order=order),
                      {n: f"m{i}" for i, n in enumerate(order)})
    monkeypatch.setenv("UEDCLI_LEVEL", "lvl")
    return proj


def _preview_args(proj, tmp_path, **over):
    base = dict(cmd="level", sub="photo", shots=["at:0,0,0;rot:0,0"],
                out_dir=str(tmp_path / "out"), native=False, game=False, size="1280x960",
                fov=None, map=None, rebuild=False, keep_alive=False, project=str(proj),
                list_actors=None, sample=0)
    base.update(over)
    return SimpleNamespace(**base)


def _patch_user_config(monkeypatch):
    from uedcli import config
    monkeypatch.setattr(config, "load_user_config", lambda override=None: object())
    monkeypatch.setattr(config, "composed_search_files", lambda p, uc: [])


def test_level_preview_native_routes_shots_to_render(tmp_path, monkeypatch):
    from uedcli import builders
    from uedcli.cli import dispatch as D
    room = builders.make_brush_actor("Room", builders.cube(600, 600, 300, "T"),
                                     location=(0, 0, 0), csg="subtract")
    proj = _preview_proj(tmp_path, {"Room": room}, ["Room"], monkeypatch)
    seen = {}
    monkeypatch.setattr("uedcli.preview_native.render_shots",
                        lambda **kw: (seen.update(kw), 2)[1])
    _patch_user_config(monkeypatch)
    args = _preview_args(proj, tmp_path, native=True,     # --native is now opt-in (default is --game)
                         shots=["at:0,0,0;rot:0,0", "at:0,0,0;look:@room;name:hero"])
    assert D.dispatch(args) == 0
    assert [s.rot for s in seen["shots"]][0] == (0.0, 0.0)
    assert seen["shots"][1].look == "room" and seen["shots"][1].name == "hero"
    assert seen["size"] == (1280, 960)
    from uedcli.preview_native import DEFAULT_FOV
    assert seen["fov"] == DEFAULT_FOV                      # pinned game default (75)


def test_level_preview_bad_token_errors_before_any_work(tmp_path, monkeypatch, capsys):
    from uedcli.cli import dispatch as D
    monkeypatch.setattr("uedcli.preview_native.render_shots",
                        lambda **kw: (_ for _ in ()).throw(AssertionError("worked on bad shot")))
    args = _preview_args(tmp_path, tmp_path, shots=["Keep:wire=hero"])   # OLD grammar
    assert D.dispatch(args) == 2
    assert "photo grammar changed" in capsys.readouterr().err


def test_level_preview_game_routes_to_preview_game(tmp_path, monkeypatch):
    from uedcli.cli import dispatch as D
    seen = {}
    monkeypatch.setattr("uedcli.preview_game.render_shots",
                        lambda **kw: (seen.update(kw), 3)[1])
    _patch_user_config(monkeypatch)
    proj = _preview_proj(tmp_path, {}, [], monkeypatch)
    args = _preview_args(proj, tmp_path, game=True, map="/x/y.dx")   # --map: no trunk needed
    assert D.dispatch(args) == 0
    assert seen["map_path"] == "/x/y.dx" and seen["level"] is None
    assert seen["size"] == (1280, 960)


def test_level_preview_bare_defaults_to_game_backend(tmp_path, monkeypatch):
    # THE default flip (2026-07-17): a bare `level photo` (neither --native nor --game) routes to
    # the in-game tier, NOT the offline rasterizer. Without this, reverting `use_game = not
    # args.native` back to `args.game` would still pass every other photo test.
    from uedcli import builders
    from uedcli.cli import dispatch as D
    room = builders.make_brush_actor("Room", builders.cube(600, 600, 300, "T"),
                                     location=(0, 0, 0), csg="subtract")
    proj = _preview_proj(tmp_path, {"Room": room}, ["Room"], monkeypatch)
    seen = {}
    monkeypatch.setattr("uedcli.preview_game.render_shots",
                        lambda **kw: (seen.update(kw), 1)[1])
    monkeypatch.setattr("uedcli.preview_native.render_shots",
                        lambda **kw: (_ for _ in ()).throw(
                            AssertionError("bare `level photo` must NOT use the --native backend")))
    _patch_user_config(monkeypatch)
    args = _preview_args(proj, tmp_path)                 # native=False, game=False ⇒ default game
    assert D.dispatch(args) == 0
    assert seen["map_path"] is None                      # trunk mode (no --map)
    assert seen["level_name"] == "lvl" and seen["level"] is not None


def test_level_preview_fov_with_game_rejected(tmp_path, capsys):
    from uedcli.cli import dispatch as D
    args = _preview_args(tmp_path, tmp_path, game=True, fov=90.0)
    assert D.dispatch(args) == 2
    assert "--fov requires --native" in capsys.readouterr().err


def test_level_preview_game_only_flags_rejected_with_native(tmp_path, capsys):
    # --game is the default, so --map/--rebuild/--keep-alive are only rejected when --native is
    # explicitly opted into (they belong to the in-game tier, which --native turns off).
    from uedcli.cli import dispatch as D
    for over, flag in ((dict(map="x.dx"), "--map"), (dict(rebuild=True), "--rebuild"),
                       (dict(keep_alive=True), "--keep-alive")):
        args = _preview_args(tmp_path, tmp_path, native=True, **over)
        assert D.dispatch(args) == 2
        assert f"{flag} requires --game" in capsys.readouterr().err


def test_level_preview_bad_size_named(tmp_path, capsys):
    from uedcli.cli import dispatch as D
    args = _preview_args(tmp_path, tmp_path, size="huge")
    assert D.dispatch(args) == 2
    assert "invalid --size 'huge'" in capsys.readouterr().err


def test_level_preview_native_error_is_clean_exit_2(tmp_path, monkeypatch, capsys):
    from uedcli import builders
    from uedcli.cli import dispatch as D
    from uedcli.preview_native import NativePreviewError
    room = builders.make_brush_actor("Room", builders.cube(600, 600, 300, "T"),
                                     location=(0, 0, 0), csg="subtract")
    proj = _preview_proj(tmp_path, {"Room": room}, ["Room"], monkeypatch)
    monkeypatch.setattr("uedcli.preview_native.render_shots",
                        lambda **kw: (_ for _ in ()).throw(NativePreviewError("boom: Named")))
    _patch_user_config(monkeypatch)
    args = _preview_args(proj, tmp_path, native=True)     # --native is now opt-in (default is --game)
    assert D.dispatch(args) == 2
    assert "boom: Named" in capsys.readouterr().err


# test_level_preview_with_session_errors_trunk_only removed: the `--session` reject block was
# deleted with the session flags (slice 4) — photo is trunk-only unconditionally now.


def _rotated_brush_level():
    """A yaw-90 cube (Rotation=(Yaw=16384)) at the origin — clip/vertex move are now rotation-aware."""
    a = make_brush_actor("B1", cube(64, 64, 64),
                         location=(Decimal(0), Decimal(0), Decimal(0)))
    a.props.append(("Rotation", "(Yaw=16384)"))
    lv = Level()
    lv.actors["B1"] = a
    return lv


def _low_bit_rotated_brush_level():
    """A cube with Yaw=2 — a low-bit field the GMath table truncates to identity, so the editor
    renders it unrotated and the clip/vertex-move guard must NOT trip (is_identity_uu is True)."""
    a = make_brush_actor("B1", cube(64, 64, 64),
                         location=(Decimal(0), Decimal(0), Decimal(0)))
    a.props.append(("Rotation", "(Yaw=2)"))
    lv = Level()
    lv.actors["B1"] = a
    return lv


def test_brush_vertex_move_allows_a_low_bit_rotation_brush():
    # Yaw=2 truncates to identity in the GMath table → the editor renders it unrotated, so the guard
    # must NOT refuse it (the GPT-review finding). Mock the move itself — we assert the GUARD passed
    # (reached the move + recorded), not the geometry of moving a corner.
    args = SimpleNamespace(
        cmd="brush", sub="vertex", vsub="move", name="B1", container="c",
        at=[(Decimal(32), Decimal(32), Decimal(32))], to=None,
        by=(Decimal(0), Decimal(0), Decimal(16)))
    lv = _low_bit_rotated_brush_level()
    src = _fake_src(lv)
    with mock.patch("uedcli.cli.level_sources.resolve_level_source", return_value=src), \
         mock.patch("uedcli.vertex.move_vertices",
                    return_value=lv.actors["B1"].brush) as mv:
        rc = dispatch(args)
    assert rc == 0                 # guard did NOT refuse the low-bit-rotation brush
    mv.assert_called_once()        # proceeded into the move (guard passed)
    src.save.assert_called_once()


def test_brush_vertex_move_at_round_trips_through_prepivot():
    # A coord from `vertex list` (world = Location + (v − PrePivot)) must convert back to the exact
    # local corner for --at. Making the readers PrePivot-aware without the write side broke this
    # round-trip (GPT review); the write side now adds PrePivot. Assert --at resolves to local v.
    from uedcli.rotation import actor_prepivot
    a = make_brush_actor("B1", cube(64, 64, 64), location=(Decimal(100), Decimal(0), Decimal(0)))
    a.props.append(("PrePivot", "(X=10.000000,Y=4.000000,Z=2.000000)"))
    local_corner = a.brush.polys[0].vertices[0]
    pp, loc = actor_prepivot(a), a.location
    world = tuple(loc[i] + local_corner[i] - pp[i] for i in range(3))   # what `vertex list` reports
    lv = Level(); lv.actors["B1"] = a
    args = SimpleNamespace(cmd="brush", sub="vertex", vsub="move", name="B1",
                           container="c",
                           at=[world], to=None, by=(Decimal(0), Decimal(0), Decimal(8)))
    with mock.patch("uedcli.cli.level_sources.resolve_level_source", return_value=_fake_src(lv)), \
         mock.patch("uedcli.vertex.move_vertices", return_value=a.brush) as mv:
        assert dispatch(args) == 0
    assert tuple(mv.call_args.args[1][0]) == tuple(local_corner)   # --at → original local corner


def test_brush_vertex_move_handles_a_rotated_brush():
    # Rotation-aware: a world `--at` (as `vertex list` reports it) inverts to the exact local corner
    # via Rᵀ·(world − Location). Mock the move; assert the guard is gone and --at → the local corner.
    from uedcli.rotation import actor_matrix, actor_prepivot, local_offset
    from uedcli.emit import clean
    lv = _rotated_brush_level()                       # yaw-90 cube at origin
    a = lv.actors["B1"]
    v = a.brush.polys[0].vertices[0]
    w = local_offset(actor_matrix(a), actor_prepivot(a), v)
    loc = a.location
    world = tuple(loc[i] + w[i] for i in range(3))    # what `vertex list` reports
    args = SimpleNamespace(cmd="brush", sub="vertex", vsub="move", name="B1",
                           container="c",
                           at=[world], to=None, by=(Decimal(0), Decimal(0), Decimal(8)))
    with mock.patch("uedcli.cli.level_sources.resolve_level_source", return_value=_fake_src(lv)), \
         mock.patch("uedcli.vertex.move_vertices", return_value=a.brush) as mv:
        assert dispatch(args) == 0
    passed = mv.call_args.args[1][0]                  # world --at inverted to the local corner
    assert tuple(clean(c) for c in passed) == tuple(clean(c) for c in v)


def _rotate_level(actors_t3d: dict[str, str], order: list[str]) -> Level:
    """Build a Level from a name→actor-T3D dict (the shape the old store seeded)."""
    lv = parse_t3d("Begin Map\n" + "\n".join(actors_t3d[n] for n in order) + "\nEnd Map\n")
    lv.order = order
    return lv


def _run_rotate(args, actors_t3d: dict[str, str], order: list[str]):
    """Dispatch `actor rotate` through the trunk seam; return (rc, {name: canonical_t3d}).
    The stored form was a canonical-T3D string per actor, so re-canonicalize the saved level's actors
    to keep the original string assertions (`X=64.000000`, `Yaw=16384`, …) verbatim."""
    from uedcli.normalize import canonical_actor_t3d
    src = _fake_src(_rotate_level(actors_t3d, order))
    with mock.patch("uedcli.cli.level_sources.resolve_level_source", return_value=src):
        rc = dispatch_mod._dispatch(args)
    if not src.save.call_args:
        return rc, {}
    saved = src.save.call_args.kwargs["level"]
    return rc, {n: canonical_actor_t3d(a) for n, a in saved.actors.items()}


_L1_AT_64 = ("Begin Actor Class=Light Name=L1\n    Location=(X=64.000000,Y=0.000000,Z=0.000000)\n"
             "    Name=\"L1\"\nEnd Actor\n")


def test_actor_rotate_orbits_location_and_composes_rotation_model_side():
    args = SimpleNamespace(cmd="actor", sub="rotate", names=["L1"],
                           by=(Decimal(0), Decimal(16384), Decimal(0)),   # yaw 90°
                           pivot=(Decimal(0), Decimal(0), Decimal(0)), pivot_actor=None,
                           container="dx-lum-uned")
    rc, actors = _run_rotate(args, {"L1": _L1_AT_64}, ["L1"])
    assert rc == 0
    out = actors["L1"]
    assert "Y=64.000000" in out and "X=0.000000" in out    # (64,0,0) orbited to (0,64,0)
    assert "Yaw=16384" in out                              # rotation composed onto the actor


def test_actor_rotate_two_actors_orbit_a_shared_pivot():
    a = _L1_AT_64
    b = ("Begin Actor Class=Light Name=L2\n    Location=(X=0.000000,Y=64.000000,Z=0.000000)\n"
         "    Name=\"L2\"\nEnd Actor\n")
    args = SimpleNamespace(cmd="actor", sub="rotate", names=["L1", "L2"],
                           by=(Decimal(0), Decimal(16384), Decimal(0)),
                           pivot=(Decimal(0), Decimal(0), Decimal(0)), pivot_actor=None,
                           container="dx-lum-uned")
    rc, actors = _run_rotate(args, {"L1": a, "L2": b}, ["L1", "L2"])
    assert rc == 0
    assert "Y=64.000000" in actors["L1"]                  # (64,0,0) → (0,64,0)
    assert "X=-64.000000" in actors["L2"]                 # (0,64,0) → (-64,0,0)


def test_actor_rotate_dedupes_a_repeated_name():
    # A name passed twice is the SAME actor — it must rotate ONCE, not twice (a double field-add /
    # double orbit would send (64,0,0) past (0,64,0) to (-64,0,0) and store Yaw=32768).
    args = SimpleNamespace(cmd="actor", sub="rotate", names=["L1", "L1"],
                           by=(Decimal(0), Decimal(16384), Decimal(0)),   # yaw 90°
                           pivot=(Decimal(0), Decimal(0), Decimal(0)), pivot_actor=None,
                           container="dx-lum-uned")
    rc, actors = _run_rotate(args, {"L1": _L1_AT_64}, ["L1"])
    assert rc == 0
    out = actors["L1"]
    assert "Y=64.000000" in out and "X=0.000000" in out   # orbited ONCE: (64,0,0) → (0,64,0)
    assert "Yaw=16384" in out                             # composed ONCE, not Yaw=32768


def test_actor_rotate_brush_orbits_location_keeps_polylist_local():
    from uedcli.normalize import canonical_actor_t3d
    brush = make_brush_actor("B1", cube(64, 64, 64),
                             location=(Decimal(128), Decimal(0), Decimal(0)))
    args = SimpleNamespace(cmd="actor", sub="rotate", names=["B1"],
                           by=(Decimal(0), Decimal(16384), Decimal(0)),
                           pivot=(Decimal(0), Decimal(0), Decimal(0)), pivot_actor=None,
                           container="dx-lum-uned")
    rc, actors = _run_rotate(args, {"B1": canonical_actor_t3d(brush)}, ["B1"])
    assert rc == 0
    out = actors["B1"]
    assert "Y=128.000000" in out                          # Location (128,0,0) orbits to (0,128,0)
    assert "Yaw=16384" in out                             # Rotation composed onto the actor
    # PolyList stays LOCAL: a cube vertex at local +32 is unchanged (not vertex-baked).
    assert "+00032.000000" in out


def test_actor_rotate_default_pivot_is_best_grid_vertex():
    li = ("Begin Actor Class=Light Name=L1\n    Location=(X=128.000000,Y=128.000000,Z=0.000000)\n"
          "    Name=\"L1\"\nEnd Actor\n")
    args = SimpleNamespace(cmd="actor", sub="rotate", names=["L1"],
                           by=(Decimal(0), Decimal(16384), Decimal(0)),
                           pivot=None, pivot_actor=None,
                           container="dx-lum-uned")
    rc, actors = _run_rotate(args, {"L1": li}, ["L1"])
    assert rc == 0
    # Default pivot = the single actor's own Location (best-grid candidate), so it stays put.
    assert "X=128.000000" in actors["L1"] and "Y=128.000000" in actors["L1"]


def test_actor_rotate_not_found_exits_2():
    args = SimpleNamespace(cmd="actor", sub="rotate", names=["Ghost"],
                           by=(Decimal(0), Decimal(16384), Decimal(0)),
                           pivot=(Decimal(0), Decimal(0), Decimal(0)), pivot_actor=None,
                           container="dx-lum-uned")
    rc, _ = _run_rotate(args, {}, [])
    assert rc == 2


def test_actor_rotate_pivot_actor_missing_exits_2():
    args = SimpleNamespace(cmd="actor", sub="rotate", names=["L1"],
                           by=(Decimal(0), Decimal(16384), Decimal(0)),
                           pivot=None, pivot_actor="NoSuchPivot",
                           container="dx-lum-uned")
    rc, _ = _run_rotate(args, {"L1": _L1_AT_64}, ["L1"])
    assert rc == 2


def test_actor_rotate_pivot_actor_uses_that_actors_location():
    mover = _L1_AT_64
    pivot = ("Begin Actor Class=Light Name=P\n    Location=(X=64.000000,Y=64.000000,Z=0.000000)\n"
             "    Name=\"P\"\nEnd Actor\n")
    args = SimpleNamespace(cmd="actor", sub="rotate", names=["L1"],
                           by=(Decimal(0), Decimal(16384), Decimal(0)),
                           pivot=None, pivot_actor="P",
                           container="dx-lum-uned")
    rc, actors = _run_rotate(args, {"L1": mover, "P": pivot}, ["L1", "P"])
    assert rc == 0
    # Pivot P=(64,64,0); L1=(64,0,0). Yaw 90: rel=(0,-64,0) → (64,0,0) → world (128,64,0).
    assert "X=128.000000" in actors["L1"] and "Y=64.000000" in actors["L1"]


def test_actor_rotate_pitch_orbits_in_xz():
    args = SimpleNamespace(cmd="actor", sub="rotate", names=["L1"],
                           by=(Decimal(16384), Decimal(0), Decimal(0)),   # pitch 90° (16384 UU)
                           pivot=(Decimal(0), Decimal(0), Decimal(0)), pivot_actor=None,
                           container="dx-lum-uned")
    rc, actors = _run_rotate(args, {"L1": _L1_AT_64}, ["L1"])
    assert rc == 0
    # Pitch (x,z)→(-z,x): (64,0,0) → (0,0,64). Stored Rotation has the pitch field.
    assert "Z=64.000000" in actors["L1"] and "X=0.000000" in actors["L1"]
    assert "Pitch=16384" in actors["L1"]


def test_actor_rotate_composes_onto_an_already_rotated_actor_by_field_add():
    li = ("Begin Actor Class=Light Name=L1\n    Location=(X=64.000000,Y=0.000000,Z=0.000000)\n"
          "    Rotation=(Yaw=8192)\n    Name=\"L1\"\nEnd Actor\n")
    args = SimpleNamespace(cmd="actor", sub="rotate", names=["L1"],
                           by=(Decimal(0), Decimal(16384), Decimal(0)),   # +16384 yaw
                           pivot=(Decimal(0), Decimal(0), Decimal(0)), pivot_actor=None,
                           container="dx-lum-uned")
    rc, actors = _run_rotate(args, {"L1": li}, ["L1"])
    assert rc == 0
    assert "Yaw=24576" in actors["L1"]          # field-add: 8192 + 16384 = 24576


# --- poly set (2026-06-20, surface-flags-texturing spec) --------------------

def test_dispatch_poly_set_records_texture_edit():
    args = SimpleNamespace(
        cmd="brush", sub="poly", polysub="set", targets=["B1:all"], texture="DeusExDeco.Textures.Wood",
        add_flags=[], remove_flags=[])
    src = _fake_src(_brush_level())
    with mock.patch("uedcli.cli.level_sources.resolve_level_source", return_value=src):
        rc = dispatch(args)
    assert rc == 0
    saved = src.save.call_args.kwargs
    level = saved["level"]
    assert all(p.texture == "DeusExDeco.Textures.Wood" for p in level.actors["B1"].brush.polys)
    assert saved["touched"] == ["B1"]
    assert saved["args"]["texture"] == "DeusExDeco.Textures.Wood"


# The poly-set package-union tests went with the session store's package manifest (slice 4): the
# trunk has no manifest — the load set derives on demand at build. The texture EDIT itself is still
# covered by test_dispatch_poly_set_records_texture_edit and _flags.


def test_dispatch_poly_set_flags():
    args = SimpleNamespace(
        cmd="brush", sub="poly", polysub="set", targets=["B1:0"], texture=None,
        add_flags=["translucent"], remove_flags=[])
    src = _fake_src(_brush_level())
    with mock.patch("uedcli.cli.level_sources.resolve_level_source", return_value=src):
        rc = dispatch(args)
    assert rc == 0
    saved = src.save.call_args.kwargs
    assert saved["level"].actors["B1"].brush.polys[0].flags & 0x4
    assert saved["args"]["add_flags"] == ["translucent"]


def test_dispatch_poly_pan_records_the_write_and_writes_only_pan():
    args = SimpleNamespace(cmd="brush", sub="poly", polysub="pan", targets=["B1:0"],
                           pan_to=(10, 20), pan_by=None)
    src = _fake_src(_brush_level())
    with mock.patch("uedcli.cli.level_sources.resolve_level_source", return_value=src):
        rc = dispatch(args)
    assert rc == 0
    saved = src.save.call_args.kwargs
    assert saved["level"].actors["B1"].brush.polys[0].pan == (10, 20)
    assert saved["touched"] == ["B1"]
    assert saved["args"]["pan_to"] == ["10", "20"] and "pan_by" not in saved["args"]
    assert src.save.call_args.kwargs["verb"] == "poly-pan"


def test_dispatch_poly_rotate_records_the_write():
    args = SimpleNamespace(cmd="brush", sub="poly", polysub="rotate", targets=["B1:all"], by=16384)
    src = _fake_src(_brush_level())
    with mock.patch("uedcli.cli.level_sources.resolve_level_source", return_value=src):
        rc = dispatch(args)
    assert rc == 0
    saved = src.save.call_args.kwargs
    assert saved["verb"] == "poly-rotate" and saved["args"]["by"] == "16384"
    assert saved["touched"] == ["B1"]


def test_dispatch_poly_scale_records_the_write():
    args = SimpleNamespace(cmd="brush", sub="poly", polysub="scale", targets=["B1:all"],
                           by=(2.0, 0.5))
    src = _fake_src(_brush_level())
    with mock.patch("uedcli.cli.level_sources.resolve_level_source", return_value=src):
        rc = dispatch(args)
    assert rc == 0
    saved = src.save.call_args.kwargs
    assert saved["verb"] == "poly-scale" and saved["args"]["by"] == ["2.0", "0.5"]
    assert saved["touched"] == ["B1"]


def test_dispatch_poly_scale_bad_factor_returns_2_and_does_not_record(capsys):
    args = SimpleNamespace(cmd="brush", sub="poly", polysub="scale", targets=["B1:all"],
                           by=(0.0, 1.0), to=None)
    src = _fake_src(_brush_level())
    with mock.patch("uedcli.cli.level_sources.resolve_level_source", return_value=src):
        rc = dispatch(args)
    assert rc == 2
    assert "must be a positive number" in capsys.readouterr().err
    src.save.assert_not_called()


def test_dispatch_poly_scale_to_records_the_write(monkeypatch):
    from uedcli.cli import resources
    monkeypatch.setattr(resources, "texture_dims_resolver", lambda args: (lambda ref: (256, 256)))
    level = _brush_level()
    for p in level.actors["B1"].brush.polys:
        p.texture = "Pkg.Tex"
    args = SimpleNamespace(cmd="brush", sub="poly", polysub="scale", targets=["B1:all"],
                           by=None, to=(128.0, 128.0))
    src = _fake_src(level)
    with mock.patch("uedcli.cli.level_sources.resolve_level_source", return_value=src):
        rc = dispatch(args)
    assert rc == 0
    saved = src.save.call_args.kwargs
    assert saved["verb"] == "poly-scale" and saved["args"]["to"] == ["128.0", "128.0"]
    assert "by" not in saved["args"]


def test_dispatch_poly_scale_to_never_calls_texture_dims_resolver_for_by(monkeypatch):
    from uedcli.cli import resources
    calls = []
    monkeypatch.setattr(resources, "texture_dims_resolver", lambda args: calls.append(1))
    args = SimpleNamespace(cmd="brush", sub="poly", polysub="scale", targets=["B1:all"],
                           by=(2.0, 2.0), to=None)
    src = _fake_src(_brush_level())
    with mock.patch("uedcli.cli.level_sources.resolve_level_source", return_value=src):
        rc = dispatch(args)
    assert rc == 0 and not calls


def test_dispatch_poly_set_unknown_brush_returns_2_and_does_not_record(capsys):
    args = SimpleNamespace(
        cmd="brush", sub="poly", polysub="set", targets=["NoSuch:all"], texture="Engine.DefaultTexture",
        add_flags=[], remove_flags=[])
    src = _fake_src(_brush_level())
    with mock.patch("uedcli.cli.level_sources.resolve_level_source", return_value=src):
        rc = dispatch(args)
    assert rc == 2
    assert "unknown brush" in capsys.readouterr().err
    src.save.assert_not_called()


# ── actor find ────────────────────────────────────────────────────────────────


def _find_setup(tmp_path, monkeypatch, actors: dict, order: list[str]) -> tuple:
    """Build a Level from a name→actor-T3D dict and point the trunk seam at it (reads go through
    `_resolve_level_source(...).load()`). Returns (level, branch) — `branch` is a stable dummy the
    verb ignores, kept so `_find_args(branch, …)` calls read unchanged."""
    lv = parse_t3d("Begin Map\n" + "\n".join(actors[n] for n in order) + "\nEnd Map\n")
    lv.order = order
    monkeypatch.setattr("uedcli.cli.level_sources.resolve_level_source",
                        lambda args: _fake_src(lv))
    return lv, "session/x"


def _find_args(branch, *, cls=None, group=None, name=None, prop=None, kind=None,
               folder=None, no_folder=False):
    """Build an actor find SimpleNamespace; lists default to []."""
    return SimpleNamespace(
        cmd="actor", sub="find",
        cls=cls or [], group=group or [], name=name or [],
        prop=prop or [], kind=kind, folder=folder or [], no_folder=no_folder,
        tree=None,
        container="ct")


def _find_seams(monkeypatch):
    """Patch the four schema seams for the effective-value --prop matching (spec §7): a small
    Light-ish schema with defaults, mirroring test_actor_prop.py's fixtures."""
    from uedcli.uprops import Prop

    def _p(name, kind, **kw):
        return Prop(name=name, kind=kind, array_dim=kw.get("array_dim", 1), property_flags=0,
                    type_ref=kw.get("type_ref", 0), type_name=kw.get("type_name"),
                    owner="Engine.Actor", enum_value_names=tuple(kw.get("enum", ())))

    schema = {
        "group": _p("Group", "NameProperty"),
        "lightbrightness": _p("LightBrightness", "ByteProperty"),
        "lightradius": _p("LightRadius", "ByteProperty"),
        "bhidden": _p("bHidden", "BoolProperty"),
        "location": _p("Location", "StructProperty", type_ref=3, type_name="Vector"),
    }
    defaults = {("lightbrightness", 0): "64", ("bhidden", 0): "True"}
    monkeypatch.setattr("uedcli.cli.resources.class_schema",
                        lambda cls, project=None: dict(schema))
    monkeypatch.setattr("uedcli.cli.resources.class_defaults",
                        lambda cls, project=None: dict(defaults))
    monkeypatch.setattr("uedcli.cli.resources.struct_members", lambda p, project=None: [])
    monkeypatch.setattr("uedcli.cli.resources.enum_names",
                        lambda p, project=None: p.enum_value_names)


# Compact T3D strings for fixtures.
def _light_t3d(actor_name, group=None, extra_props=""):
    props = f"    Group=\"{group}\"\n" if group else ""
    if extra_props:
        props += extra_props
    return (f"Begin Actor Class=Engine.Light Name={actor_name}\n"
            f"    Name=\"{actor_name}\"\n{props}End Actor\n")


def _deco_t3d(actor_name, group=None):
    props = f"    Group=\"{group}\"\n" if group else ""
    return (f"Begin Actor Class=Engine.Decoration Name={actor_name}\n"
            f"    Name=\"{actor_name}\"\n{props}End Actor\n")


def _brush_t3d(actor_name, group=None):
    props = f"    Group=\"{group}\"\n" if group else ""
    return (f"Begin Actor Class=Engine.Brush Name={actor_name}\n"
            f"    Name=\"{actor_name}\"\n{props}Begin Brush Name=Model\n"
            f"    Begin PolyList\n    End PolyList\nEnd Brush\n"
            f"    Brush=Model'Model'\nEnd Actor\n")


def test_actor_find_by_group(tmp_path, monkeypatch, capsys):
    actors = {
        "Light1": _light_t3d("Light1", group="cells"),
        "Light2": _light_t3d("Light2", group="vents"),
    }
    _, branch = _find_setup(tmp_path, monkeypatch, actors, ["Light1", "Light2"])
    args = _find_args(branch, group=["cells"])
    rc = dispatch_mod._dispatch(args)
    out = capsys.readouterr().out
    assert rc == 0
    assert out == "Light1\n"


def test_actor_find_multi_group(tmp_path, monkeypatch, capsys):
    """Two groups in one Group= value (comma-separated, spaces stripped)."""
    actors = {
        "Light1": _light_t3d("Light1", group="cells, vents"),
        "Light2": _light_t3d("Light2", group="other"),
    }
    _, branch = _find_setup(tmp_path, monkeypatch, actors, ["Light1", "Light2"])
    # Both groups hit Light1; Light2 is not in cells or vents.
    args = _find_args(branch, group=["cells", "vents"])
    rc = dispatch_mod._dispatch(args)
    out = capsys.readouterr().out
    assert rc == 0
    assert set(out.splitlines()) == {"Light1"}


def test_actor_find_multi_group_not_matched_by_prop_exact(tmp_path, monkeypatch, capsys):
    """--prop Group=cells compares the whole value, so a multi-group actor (cells,vents) is NOT
    matched (use --group for membership)."""
    actors = {
        "Multi": _light_t3d("Multi", group="cells,vents"),
        "Single": _light_t3d("Single", group="cells"),
    }
    _, branch = _find_setup(tmp_path, monkeypatch, actors, ["Multi", "Single"])
    _find_seams(monkeypatch)
    args = _find_args(branch, prop=["Group=cells"])
    rc = dispatch_mod._dispatch(args)
    out = capsys.readouterr().out
    assert rc == 0
    # Only Single has Group= exactly "cells"; Multi has "cells,vents" which doesn't match.
    assert out.splitlines() == ["Single"]


def test_actor_find_single_group_matched_by_group_and_prop(tmp_path, monkeypatch, capsys):
    """A single-group actor is matched by --group and by --prop Group=cells (effective value)."""
    actors = {
        "Single": _light_t3d("Single", group="cells"),
        "Other": _light_t3d("Other", group="vents"),
    }
    _, branch = _find_setup(tmp_path, monkeypatch, actors, ["Single", "Other"])

    # --group cells hits Single (membership match)
    args = _find_args(branch, group=["cells"])
    rc = dispatch_mod._dispatch(args)
    out = capsys.readouterr().out
    assert rc == 0
    assert out.splitlines() == ["Single"]

    # --prop Group=cells hits Single (whole-value match on the effective value)
    _find_seams(monkeypatch)
    args = _find_args(branch, prop=["Group=cells"])
    rc = dispatch_mod._dispatch(args)
    out = capsys.readouterr().out
    assert rc == 0
    assert out.splitlines() == ["Single"]

    # surrounding quotes on the query value are stripped, like set's values
    args = _find_args(branch, prop=['Group="cells"'])
    rc = dispatch_mod._dispatch(args)
    out = capsys.readouterr().out
    assert rc == 0
    assert out.splitlines() == ["Single"]


def test_actor_find_ors_repeated_classes(tmp_path, monkeypatch, capsys):
    actors = {
        "L1": _light_t3d("L1"),
        "D1": _deco_t3d("D1"),
        "L2": _light_t3d("L2"),
    }
    _, branch = _find_setup(tmp_path, monkeypatch, actors, ["L1", "D1", "L2"])
    args = _find_args(branch, cls=["Light", "Decoration"])
    rc = dispatch_mod._dispatch(args)
    out = capsys.readouterr().out
    assert rc == 0
    assert set(out.splitlines()) == {"L1", "D1", "L2"}


def test_actor_find_ors_repeated_groups(tmp_path, monkeypatch, capsys):
    actors = {
        "L1": _light_t3d("L1", group="cells"),
        "L2": _light_t3d("L2", group="vents"),
        "L3": _light_t3d("L3", group="other"),
    }
    _, branch = _find_setup(tmp_path, monkeypatch, actors, ["L1", "L2", "L3"])
    args = _find_args(branch, group=["cells", "vents"])
    rc = dispatch_mod._dispatch(args)
    out = capsys.readouterr().out
    assert rc == 0
    assert set(out.splitlines()) == {"L1", "L2"}


def test_actor_find_ors_repeated_names(tmp_path, monkeypatch, capsys):
    actors = {
        "HelperLight0": _light_t3d("HelperLight0"),
        "HelperLight1": _light_t3d("HelperLight1"),
        "OtherActor": _light_t3d("OtherActor"),
    }
    _, branch = _find_setup(tmp_path, monkeypatch, actors,
                            ["HelperLight0", "HelperLight1", "OtherActor"])
    args = _find_args(branch, name=["HelperLight0", "HelperLight1"])
    rc = dispatch_mod._dispatch(args)
    out = capsys.readouterr().out
    assert rc == 0
    assert set(out.splitlines()) == {"HelperLight0", "HelperLight1"}


def test_actor_find_by_class_bare_and_qualified(tmp_path, monkeypatch, capsys):
    actors = {
        "L1": _light_t3d("L1"),
        "D1": _deco_t3d("D1"),
    }
    _, branch = _find_setup(tmp_path, monkeypatch, actors, ["L1", "D1"])
    # Bare name match.
    args = _find_args(branch, cls=["Light"])
    rc1 = dispatch_mod._dispatch(args)
    out1 = capsys.readouterr().out
    # Fully qualified match.
    args2 = _find_args(branch, cls=["Engine.Light"])
    rc2 = dispatch_mod._dispatch(args2)
    out2 = capsys.readouterr().out
    assert rc1 == 0 and out1 == "L1\n"
    assert rc2 == 0 and out2 == "L1\n"


def test_actor_find_matches_case_insensitively(tmp_path, monkeypatch, capsys):
    actors = {
        "HelperLight0": _light_t3d("HelperLight0", group="Cells"),
    }
    _, branch = _find_setup(tmp_path, monkeypatch, actors, ["HelperLight0"])
    # Name glob, class, and group all case-insensitive.
    args = _find_args(branch, name=["helperlight*"], cls=["light"], group=["CELLS"])
    rc = dispatch_mod._dispatch(args)
    out = capsys.readouterr().out
    assert rc == 0 and out == "HelperLight0\n"

    # Companion: a bare `--name` glob on find is also case-insensitive.
    glob_args = _find_args(branch, name=["HELPER*"])
    rc2 = dispatch_mod._dispatch(glob_args)
    out2 = capsys.readouterr().out
    assert rc2 == 0 and "HelperLight0" in out2


def test_actor_find_prop_key_ci_value_exact(tmp_path, monkeypatch, capsys):
    actors = {
        "L1": _light_t3d("L1", extra_props="    LightBrightness=128\n"),
        "L2": _light_t3d("L2", extra_props="    LightBrightness=64\n"),
    }
    _, branch = _find_setup(tmp_path, monkeypatch, actors, ["L1", "L2"])
    _find_seams(monkeypatch)
    # Key is case-insensitive; numeric values compare NUMERICALLY (128 == 128.0).
    args = _find_args(branch, prop=["lightbrightness=128"])
    rc = dispatch_mod._dispatch(args)
    out = capsys.readouterr().out
    assert rc == 0 and out == "L1\n"

    args2 = _find_args(branch, prop=["LightBrightness=128.0"])
    rc2 = dispatch_mod._dispatch(args2)
    out2 = capsys.readouterr().out
    assert rc2 == 0 and out2 == "L1\n"

    args3 = _find_args(branch, prop=["LightBrightness=127"])
    rc3 = dispatch_mod._dispatch(args3)
    out3 = capsys.readouterr().out
    assert rc3 == 0 and out3 == ""


def test_actor_find_by_kind(tmp_path, monkeypatch, capsys):
    actors = {
        "L1": _light_t3d("L1"),      # point actor (no brush)
        "B1": _brush_t3d("B1"),      # brush actor
    }
    _, branch = _find_setup(tmp_path, monkeypatch, actors, ["L1", "B1"])
    args_point = _find_args(branch, kind="point")
    rc1 = dispatch_mod._dispatch(args_point)
    out1 = capsys.readouterr().out
    args_brush = _find_args(branch, kind="brush")
    rc2 = dispatch_mod._dispatch(args_brush)
    out2 = capsys.readouterr().out
    assert rc1 == 0 and out1 == "L1\n"
    assert rc2 == 0 and out2 == "B1\n"


def test_actor_find_ands_multiple_props(tmp_path, monkeypatch, capsys):
    actors = {
        "L1": _light_t3d("L1", extra_props="    LightBrightness=128\n    LightRadius=64\n"),
        "L2": _light_t3d("L2", extra_props="    LightBrightness=128\n    LightRadius=32\n"),
    }
    _, branch = _find_setup(tmp_path, monkeypatch, actors, ["L1", "L2"])
    # Both props must match (AND).
    _find_seams(monkeypatch)
    args = _find_args(branch, prop=["LightBrightness=128", "LightRadius=64"])
    rc = dispatch_mod._dispatch(args)
    out = capsys.readouterr().out
    assert rc == 0 and out == "L1\n"


def test_actor_find_ands_across_different_flags(tmp_path, monkeypatch, capsys):
    """group ∧ class ∧ prop — all three must match."""
    actors = {
        "L1": _light_t3d("L1", group="cells", extra_props="    LightBrightness=42\n"),
        "L2": _light_t3d("L2", group="cells"),        # missing prop
        "D1": _deco_t3d("D1", group="cells"),          # wrong class
    }
    _, branch = _find_setup(tmp_path, monkeypatch, actors, ["L1", "L2", "D1"])
    _find_seams(monkeypatch)
    args = _find_args(branch, group=["cells"], cls=["Light"],
                      prop=["LightBrightness=42"])
    rc = dispatch_mod._dispatch(args)
    out = capsys.readouterr().out
    assert rc == 0 and out == "L1\n"


def test_actor_find_prop_matches_class_default(tmp_path, monkeypatch, capsys):
    """Effective-value matching (ruling R3): an actor with the prop UNSET matches its class
    DEFAULT value — bHidden defaults True in the seams fixture."""
    actors = {"L1": _light_t3d("L1"), "L2": _light_t3d("L2", extra_props="    bHidden=False\n")}
    _, branch = _find_setup(tmp_path, monkeypatch, actors, ["L1", "L2"])
    _find_seams(monkeypatch)
    args = _find_args(branch, prop=["bHidden=True"])
    rc = dispatch_mod._dispatch(args)
    out = capsys.readouterr().out
    assert rc == 0 and out == "L1\n"                     # L1 unset → default True; L2 stored False


def test_actor_find_prop_bool_canonicalizes(tmp_path, monkeypatch, capsys):
    actors = {"L1": _light_t3d("L1", extra_props="    bHidden=False\n")}
    _, branch = _find_setup(tmp_path, monkeypatch, actors, ["L1"])
    _find_seams(monkeypatch)
    args = _find_args(branch, prop=["bhidden=0"])         # 0 ≡ False
    rc = dispatch_mod._dispatch(args)
    assert rc == 0 and capsys.readouterr().out == "L1\n"


def test_actor_find_prop_key_on_no_class_errors(tmp_path, monkeypatch, capsys):
    actors = {"L1": _light_t3d("L1")}
    _, branch = _find_setup(tmp_path, monkeypatch, actors, ["L1"])
    _find_seams(monkeypatch)
    args = _find_args(branch, prop=["Bogus=1"])
    rc = dispatch_mod._dispatch(args)
    cap = capsys.readouterr()
    assert rc == 2 and cap.out == ""
    assert "Bogus" in cap.err


def test_actor_find_prop_location_path(tmp_path, monkeypatch, capsys):
    actors = {
        "L1": ("Begin Actor Class=Engine.Light Name=L1\n"
               "    Location=(X=512.000000,Y=0.000000,Z=64.000000)\nEnd Actor\n"),
        "L2": _light_t3d("L2"),
    }
    _, branch = _find_setup(tmp_path, monkeypatch, actors, ["L1", "L2"])
    _find_seams(monkeypatch)
    args = _find_args(branch, prop=["Location.X=512"])
    rc = dispatch_mod._dispatch(args)
    assert rc == 0 and capsys.readouterr().out == "L1\n"


def _csg_brush_t3d(actor_name, oper):
    """A content brush actor carrying an explicit CsgOper (CSG_Add / CSG_Subtract)."""
    return (f"Begin Actor Class=Engine.Brush Name={actor_name}\n"
            f"    Name=\"{actor_name}\"\n    CsgOper={oper}\n"
            f"    Begin Brush Name=Model{actor_name}\n"
            f"    Begin PolyList\n    End PolyList\nEnd Brush\n"
            f"    Brush=Model'Model{actor_name}'\nEnd Actor\n")


def _csg_seams(monkeypatch):
    """Schema seam for the CsgOper --prop pinning test: Engine.Brush's CsgOper enum, class default
    CSG_Active — the real ECsgOper declaration."""
    from uedcli.uprops import Prop
    csgoper = Prop(name="CsgOper", kind="ByteProperty", array_dim=1, property_flags=0, type_ref=1,
                   type_name=None, owner="Engine.Brush",
                   enum_value_names=("CSG_Active", "CSG_Add", "CSG_Subtract", "CSG_Intersect",
                                     "CSG_Deintersect"))
    monkeypatch.setattr("uedcli.cli.resources.class_schema",
                        lambda cls, project=None: {"csgoper": csgoper})
    monkeypatch.setattr("uedcli.cli.resources.class_defaults",
                        lambda cls, project=None: {("csgoper", 0): "CSG_Active"})
    monkeypatch.setattr("uedcli.cli.resources.struct_members", lambda p, project=None: [])
    monkeypatch.setattr("uedcli.cli.resources.enum_names",
                        lambda p, project=None: p.enum_value_names)


def test_actor_find_prop_csgoper_discovers_subtractive_and_additive(tmp_path, monkeypatch, capsys):
    """Pins the documented CSG-type discovery workflow: `actor find --prop CsgOper=…` selects
    subtractive vs additive brushes with no dedicated verb/flag (owner ruling 2026-08-02). If this
    breaks, the workflow that replaces a `brush find`/`--csg` surface has silently rotted."""
    actors = {
        "Carve": _csg_brush_t3d("Carve", "CSG_Subtract"),
        "Fill": _csg_brush_t3d("Fill", "CSG_Add"),
        "Info": "Begin Actor Class=Engine.LevelInfo Name=Info\n    Name=\"Info\"\nEnd Actor\n",
    }
    _, branch = _find_setup(tmp_path, monkeypatch, actors, ["Carve", "Fill", "Info"])
    _csg_seams(monkeypatch)

    rc = dispatch_mod._dispatch(_find_args(branch, prop=["CsgOper=CSG_Subtract"]))
    assert rc == 0 and capsys.readouterr().out.splitlines() == ["Carve"]

    rc = dispatch_mod._dispatch(_find_args(branch, prop=["CsgOper=CSG_Add"]))
    assert rc == 0 and capsys.readouterr().out.splitlines() == ["Fill"]

    # ANDs with --kind brush (the canonical spelling — a point-only set with no brush would exit 2).
    rc = dispatch_mod._dispatch(_find_args(branch, kind="brush", prop=["CsgOper=CSG_Subtract"]))
    assert rc == 0 and capsys.readouterr().out.splitlines() == ["Carve"]

    # A bogus enum value is a typo → exit 2 naming the offending value, not a silent empty result.
    rc = dispatch_mod._dispatch(_find_args(branch, prop=["CsgOper=CSG_Bogus"]))
    cap = capsys.readouterr()
    assert rc == 2 and cap.out == "" and "CSG_Bogus" in cap.err


def test_actor_find_prop_unbuildable_schema_errors(tmp_path, monkeypatch, capsys):
    from uedcli.uprops import SchemaError
    actors = {"L1": _light_t3d("L1")}
    _, branch = _find_setup(tmp_path, monkeypatch, actors, ["L1"])
    monkeypatch.setattr("uedcli.cli.resources.class_schema",
                        mock.Mock(side_effect=SchemaError("package Engine not found")))
    args = _find_args(branch, prop=["LightBrightness=64"])
    rc = dispatch_mod._dispatch(args)
    cap = capsys.readouterr()
    assert rc == 2 and "Engine" in cap.err


def test_actor_find_without_prop_never_touches_schema(tmp_path, monkeypatch, capsys):
    actors = {"L1": _light_t3d("L1", group="cells")}
    _, branch = _find_setup(tmp_path, monkeypatch, actors, ["L1"])
    boom = mock.Mock(side_effect=AssertionError("schema must not be resolved"))
    monkeypatch.setattr("uedcli.cli.resources.class_schema", boom)
    args = _find_args(branch, group=["cells"])
    rc = dispatch_mod._dispatch(args)
    assert rc == 0 and capsys.readouterr().out == "L1\n"
    assert not boom.called


def test_actor_find_prop_comma_sugar_and_struct_form_agree(tmp_path, monkeypatch, capsys):
    # review B4: find adopts set's Vector/Rotator comma sugar — both spellings must match
    actors = {"L1": ("Begin Actor Class=Engine.Light Name=L1\n"
                     "    Location=(X=1.000000,Y=2.000000,Z=3.000000)\nEnd Actor\n")}
    _, branch = _find_setup(tmp_path, monkeypatch, actors, ["L1"])
    _find_seams(monkeypatch)
    for spelling in ("Location=1,2,3", "Location=(X=1,Y=2,Z=3)"):
        args = _find_args(branch, prop=[spelling])
        rc = dispatch_mod._dispatch(args)
        assert rc == 0 and capsys.readouterr().out == "L1\n", spelling


def test_actor_find_prop_malformed_value_errors(tmp_path, monkeypatch, capsys):
    # review B8: a value that can NEVER match is a typo → exit 2, not a silent empty result
    actors = {"L1": _light_t3d("L1")}
    _, branch = _find_setup(tmp_path, monkeypatch, actors, ["L1"])
    _find_seams(monkeypatch)
    for tok in ("LightBrightness=abc", "bHidden=perhaps", "Location=abc"):
        args = _find_args(branch, prop=[tok])
        rc = dispatch_mod._dispatch(args)
        cap = capsys.readouterr()
        assert rc == 2 and cap.out == "", tok


def test_actor_find_prop_typo_flagged_even_with_empty_considered_set(tmp_path, monkeypatch,
                                                                     capsys):
    # review A6/B9: `--name zzz --prop Typoo=1` must still flag the undeclared key
    actors = {"L1": _light_t3d("L1")}
    _, branch = _find_setup(tmp_path, monkeypatch, actors, ["L1"])
    _find_seams(monkeypatch)
    args = _find_args(branch, name=["zzz*"], prop=["Typoo=1"])
    rc = dispatch_mod._dispatch(args)
    cap = capsys.readouterr()
    assert rc == 2 and "Typoo" in cap.err
    # …while a DECLARED key with an empty considered set stays a clean empty result
    args2 = _find_args(branch, name=["zzz*"], prop=["LightBrightness=64"])
    rc2 = dispatch_mod._dispatch(args2)
    assert rc2 == 0 and capsys.readouterr().out == ""


def test_actor_find_returns_all_names_with_no_filters(tmp_path, monkeypatch, capsys):
    actors = {
        "L1": _light_t3d("L1"),
        "L2": _light_t3d("L2"),
    }
    _, branch = _find_setup(tmp_path, monkeypatch, actors, ["L1", "L2"])
    args = _find_args(branch)  # no filters
    rc = dispatch_mod._dispatch(args)
    out = capsys.readouterr().out
    assert rc == 0 and set(out.splitlines()) == {"L1", "L2"}


def test_actor_find_returns_names_in_level_order(tmp_path, monkeypatch, capsys):
    """Names come out in level.order, not alphabetical insertion order."""
    actors = {
        "ZLight": _light_t3d("ZLight"),
        "ALight": _light_t3d("ALight"),
    }
    # Reverse-alphabetical order.
    _, branch = _find_setup(tmp_path, monkeypatch, actors, ["ZLight", "ALight"])
    args = _find_args(branch)
    rc = dispatch_mod._dispatch(args)
    out = capsys.readouterr().out
    assert rc == 0 and out == "ZLight\nALight\n"


def test_actor_find_returns_empty_and_exit_zero_on_no_match(tmp_path, monkeypatch, capsys):
    actors = {"L1": _light_t3d("L1")}
    _, branch = _find_setup(tmp_path, monkeypatch, actors, ["L1"])
    args = _find_args(branch, group=["nonexistent"])
    rc = dispatch_mod._dispatch(args)
    out, err = capsys.readouterr()
    assert rc == 0 and out == "" and err == ""


def test_actor_find_name_glob_is_whole_name_anchored(tmp_path, monkeypatch, capsys):
    """'Foo*' must NOT match 'XFooBar' (glob is not a substring search)."""
    actors = {
        "FooBar": _light_t3d("FooBar"),
        "XFooBar": _light_t3d("XFooBar"),
    }
    _, branch = _find_setup(tmp_path, monkeypatch, actors, ["FooBar", "XFooBar"])
    args = _find_args(branch, name=["Foo*"])
    rc = dispatch_mod._dispatch(args)
    out = capsys.readouterr().out
    assert rc == 0 and out == "FooBar\n"


# test_actor_find_returns_empty_on_no_session removed: the `--no-session` empty-scratch mode was
# removed with the session store (slice 4).


# --- mover key verbs (spec 2026-07-20: count owns NumKeys; move/rotate edit-only + frame) -----

def _mover_level(props=None, location=(Decimal(0), Decimal(0), Decimal("100"))):
    a = make_brush_actor("Lift", cube(128, 16, 256), location=location,
                         mover_class="Engine.Mover")
    if props:
        a.props += list(props)
    lv = Level()
    lv.actors["Lift"] = a
    return lv


def _run_mover_key(args_ns, level):
    """Dispatch a mover key verb through the trunk seam; return (rc, captured_level_or_None).
    The written level is captured on `src.save`; a read-only op (or a rejected op) leaves it unset."""
    src = _fake_src(level)
    with mock.patch("uedcli.cli.level_sources.resolve_level_source", return_value=src):
        rc = dispatch(args_ns)
    captured = src.save.call_args.kwargs["level"] if src.save.call_args else None
    return rc, captured


def _mk_args(keysub, name, **kw):
    # move/rotate carry the frame pair; default both False so a bare --to/--by test opts in per-case.
    kw.setdefault("from_base", False)
    kw.setdefault("from_world", False)
    return SimpleNamespace(cmd="mover", sub="key", keysub=keysub, name=name,
                           container="c", **kw)


# ── count: get/set NumKeys ────────────────────────────────────────────────────────────────────

def test_it_prints_num_keys_when_count_has_no_argument(capsys):
    lv = _mover_level(props=[("NumKeys", "4")])
    rc, cap = _run_mover_key(_mk_args("count", "Lift", n=None), lv)
    assert rc == 0
    assert cap is None                                   # getter is read-only — nothing saved
    assert capsys.readouterr().out == "4\n"


def test_it_sets_num_keys_when_count_has_an_argument(capsys):
    rc, cap = _run_mover_key(_mk_args("count", "Lift", n=6), _mover_level())
    assert rc == 0
    assert dict(cap.actors["Lift"].props)["NumKeys"] == "6"


def test_it_omits_num_keys_at_the_default_of_two(capsys):
    rc, cap = _run_mover_key(_mk_args("count", "Lift", n=2), _mover_level(props=[("NumKeys", "5")]))
    assert rc == 0
    assert "NumKeys" not in dict(cap.actors["Lift"].props)   # 2 is the editor default — omitted


# ── the schema-aware mover gate (board 9.4; dev/docs/direction/conventions.md 2026-07-25 10:18 UTC) ────────────────

def _named_mover_level(cls: str):
    """A one-actor level holding a mover-shaped brush actor (no CsgOper) re-labelled with `cls` —
    so the only thing under test is what the class NAME/hierarchy makes of it."""
    a = make_brush_actor("Door", cube(64, 8, 128), location=(Decimal(0), Decimal(0), Decimal(0)),
                         mover_class="Engine.Mover")
    a.cls = cls
    lv = Level()
    lv.actors["Door"] = a
    return lv


def test_mover_key_accepts_a_mover_subclass_whose_name_does_not_end_in_mover():
    # `CaroneElevatorSet.CEDoor` really extends DeusEx.DeusExMover; the old name-suffix guess
    # rejected it ("CEDoor0 is not a Mover"), which is what made the gate schema-aware.
    rc, cap = _run_mover_key(_mk_args("count", "Door", n=4), _named_mover_level(
        "CaroneElevatorSet.CEDoor"))
    assert rc == 0
    assert dict(cap.actors["Door"].props)["NumKeys"] == "4"


def test_mover_key_rejects_a_class_that_does_not_descend_from_engine_mover(capsys):
    # The other half: `Engine.Remover` ENDS in "Mover" but descends from nothing mover-ish, so the
    # suffix guess used to accept it. The error names the class and the base it failed against.
    rc, cap = _run_mover_key(_mk_args("count", "Door", n=4), _named_mover_level("Engine.Remover"))
    assert rc == 2 and cap is None
    err = capsys.readouterr().err
    assert "Door is not a Mover" in err and "Engine.Remover" in err and "Engine.Mover" in err


@pytest.mark.real_mover_index
def test_mover_index_returns_the_resolved_class_index():
    # The happy path of the seam every mover-aware verb goes through: resolve the project, build
    # the index, hand it back unchanged (the failure paths are the tests below).
    from uedcli.tests.conftest import StubClassIndex
    idx = StubClassIndex()
    args = SimpleNamespace(cmd="level", sub="doctor")
    with mock.patch("uedcli.cli.resources.resolve_project", return_value=object()), \
            mock.patch("uedcli.cli.resources.class_index", return_value=idx) as ci:
        assert resources.mover_index(args, "level doctor") is idx
    assert ci.call_count == 1


@pytest.mark.real_mover_index
def test_mover_index_names_the_verb_when_the_path_carries_no_packages(capsys):
    # The OTHER resolver-less route: the games config exists but resolves no `.u`, so `_class_index`
    # returns an EMPTY index instead of raising. Without this check the failure surfaced later,
    # from the library, with no verb in the message.
    from uedcli.tests.conftest import StubClassIndex
    with mock.patch("uedcli.cli.resources.resolve_project", return_value=object()), \
            mock.patch("uedcli.cli.resources.class_index",
                       return_value=StubClassIndex(resolves=False)):
        with pytest.raises(dispatch_mod.CommandError) as e:
            resources.mover_index(SimpleNamespace(), "event graph")
    assert e.value.message.startswith("event graph: ")
    assert "no package search path" in e.value.message
    assert "class resolver is required" in e.value.message


@pytest.mark.real_mover_index
@pytest.mark.parametrize("verb, args", [
    ("level doctor", dict(cmd="level", sub="doctor", json=False, severity=None, categories=[])),
    ("event graph", dict(cmd="event", sub="graph", json=False, dot=False)),
])
def test_a_mover_aware_verb_without_a_class_resolver_fails_clearly(capsys, tmp_project, verb, args):
    # Mover-aware verbs now REQUIRE a class resolver (for `doctor`, mover-ness decides which
    # brushes must be watertight). With no per-user games config each must exit 2 naming ITSELF and
    # the requirement — never a traceback, and never a report that silently calls every mover a
    # static brush.
    lv = _named_mover_level("Engine.Mover")
    ns = SimpleNamespace(project=None, container="c", **args)
    src = _fake_src(lv)
    src._ranks = {}
    src.display_name = "L"
    with mock.patch("uedcli.cli.level_sources.resolve_level_source", return_value=src):
        rc = dispatch(ns)
    err = capsys.readouterr().err
    assert rc == 2
    assert err.startswith(f"{verb}: ")
    assert "games config" in err and "class resolver is required" in err
    assert "Traceback" not in err


def _run_prop_set(level, tokens, schema):
    """Dispatch `actor prop set` against `level` with the schema seam mocked (the other three
    seams are unused for a whole-value scalar set). Returns rc."""
    args = SimpleNamespace(cmd="actor", sub="prop", propsub="set", name="lift",
                           tokens=list(tokens), kv=False)
    src = _fake_src(level)
    with mock.patch("uedcli.cli.level_sources.resolve_level_source", return_value=src), \
            mock.patch("uedcli.cli.resources.resolve_project",
                       side_effect=dispatch_mod.ProjectError("no project")), \
            mock.patch("uedcli.cli.resources.class_schema", lambda cls, project=None: dict(schema)):
        return dispatch(args), src


_NUMKEYS_SCHEMA = {"numkeys": Prop(name="NumKeys", kind="IntProperty", array_dim=1,
                                   property_flags=0, type_ref=0, type_name=None,
                                   owner="Engine.Mover", enum_value_names=())}


def test_it_rejects_an_out_of_range_count_identically_on_both_routes(capsys):
    # `mover key count Lift 9` and `actor prop set NumKeys=9` share one bounded setter, so they
    # must reject with the byte-identical message naming the offending value.
    rc_count, _ = _run_mover_key(_mk_args("count", "Lift", n=9), _mover_level())
    err_count = capsys.readouterr().err
    rc_prop, _src = _run_prop_set(_mover_level(), ["NumKeys=9"], _NUMKEYS_SCHEMA)
    err_prop = capsys.readouterr().err
    assert rc_count == 2 and rc_prop == 2
    assert err_count == err_prop == "NumKeys must be 2..8, got 9\n"


def test_it_stores_num_keys_identically_on_both_routes(capsys):
    # Byte-identity pin (review 2026-07-20): `mover key count` writes via movers._set_numkeys while
    # `actor prop set NumKeys=` re-implements the omit-when-2 write in propedit — two independent
    # copies. Assert the resulting stored props are identical (value form AND omit-at-2) so a change
    # to one omit rule that isn't mirrored trips this test.
    def _count_props(n):
        _rc, cap = _run_mover_key(_mk_args("count", "Lift", n=n), _mover_level())
        return dict(cap.actors["Lift"].props)

    def _prop_props(n):
        _rc, src = _run_prop_set(_mover_level(), [f"NumKeys={n}"], _NUMKEYS_SCHEMA)
        return dict(src.save.call_args.kwargs["level"].actors["Lift"].props)

    assert _count_props(6) == _prop_props(6)                # set form: identical
    assert _prop_props(6)["NumKeys"] == "6"
    assert _count_props(2) == _prop_props(2)                # omit-at-2: identical
    assert "NumKeys" not in _prop_props(2)


def test_it_keeps_stored_key_offsets_when_count_is_lowered(capsys):
    # Non-destructive: lowering the count leaves the now-inactive keys' KeyPos/KeyRot dormant.
    lv = _mover_level(props=[("KeyPos(4)", "(Z=512.000000)"), ("KeyRot(5)", "(Yaw=16384)"),
                             ("NumKeys", "6")])
    rc, cap = _run_mover_key(_mk_args("count", "Lift", n=2), lv)
    assert rc == 0
    props = dict(cap.actors["Lift"].props)
    assert "NumKeys" not in props                        # dropped to the default
    assert props["KeyPos(4)"] == "(Z=512.000000)"        # ...but the offsets survive
    assert props["KeyRot(5)"] == "(Yaw=16384)"


def test_it_rejects_count_on_a_non_mover(capsys):
    rc, _ = _run_mover_key(_mk_args("count", "B1", n=4), _brush_level())
    assert rc == 2
    assert "is not a Mover" in capsys.readouterr().err


# ── move / rotate: required frame + edit-only ─────────────────────────────────────────────────

def _two_key_lift(location=(Decimal(0), Decimal(0), Decimal("100"))):
    return _mover_level(props=[("KeyPos(1)", "(Z=256.000000)")], location=location)


_OFFSET_LOCATION = (Decimal("512.5"), Decimal("-256.25"), Decimal("96.0"))


def test_it_writes_the_offset_directly_on_move_from_base(capsys):
    # --from-base skips the base-subtraction: (0,0,64) lands verbatim even off a non-zero Location.
    rc, cap = _run_mover_key(
        _mk_args("move", "Lift", index=1, to=(Decimal(0), Decimal(0), Decimal("64")), by=None,
                 from_base=True),
        _two_key_lift(location=_OFFSET_LOCATION))
    assert rc == 0
    assert dict(cap.actors["Lift"].props)["KeyPos(1)"] == "(Z=64.000000)"


def test_it_subtracts_the_base_on_move_from_world(capsys):
    # --from-world keeps the world-absolute math: KeyPos = to - Location.
    rc, cap = _run_mover_key(
        _mk_args("move", "Lift", index=1,
                 to=(Decimal("512.5"), Decimal("-256.25"), Decimal("160")), by=None,
                 from_world=True),
        _two_key_lift(location=_OFFSET_LOCATION))
    assert rc == 0
    assert dict(cap.actors["Lift"].props)["KeyPos(1)"] == "(Z=64.000000)"   # 160 - 96


def test_it_adds_the_delta_on_move_by(capsys):
    rc, cap = _run_mover_key(
        _mk_args("move", "Lift", index=1, to=None, by=(Decimal(0), Decimal(0), Decimal("-56"))),
        _two_key_lift())
    assert rc == 0
    assert dict(cap.actors["Lift"].props)["KeyPos(1)"] == "(Z=200.000000)"   # 256 - 56


def test_it_writes_the_uu_directly_on_rotate_from_base(capsys):
    rc, cap = _run_mover_key(
        _mk_args("rotate", "Lift", index=1, to=(Decimal(0), Decimal("16384"), Decimal(0)), by=None,
                 from_base=True),
        _mover_level(props=[("Rotation", "(Yaw=8192)"), ("KeyPos(1)", "(Z=256.000000)")]))
    assert rc == 0
    # from-base ignores the non-zero base Rotation (Yaw=8192): 16384 lands verbatim.
    assert dict(cap.actors["Lift"].props)["KeyRot(1)"] == "(Yaw=16384)"


def test_it_subtracts_the_base_rotation_on_rotate_from_world(capsys):
    # --from-world takes the distinct subtract_uu path: KeyRot = to - baseRot (field-wise).
    rc, cap = _run_mover_key(
        _mk_args("rotate", "Lift", index=1, to=(Decimal(0), Decimal("16384"), Decimal(0)), by=None,
                 from_world=True),
        _mover_level(props=[("Rotation", "(Yaw=8192)"), ("KeyPos(1)", "(Z=256.000000)")]))
    assert rc == 0
    assert dict(cap.actors["Lift"].props)["KeyRot(1)"] == "(Yaw=8192)"      # 16384 - 8192


def test_it_composes_the_delta_on_rotate_by(capsys):
    lift = _mover_level(props=[("KeyPos(1)", "(Z=256.000000)"), ("KeyRot(1)", "(Yaw=16384)")])
    rc, cap = _run_mover_key(
        _mk_args("rotate", "Lift", index=1, to=None, by=(Decimal(0), Decimal("16384"), Decimal(0))),
        lift)
    assert rc == 0
    assert dict(cap.actors["Lift"].props)["KeyRot(1)"] == "(Yaw=32768)"      # 16384 + 16384


def test_it_rejects_move_to_without_a_frame(capsys):
    rc, _ = _run_mover_key(
        _mk_args("move", "Lift", index=1, to=(Decimal(0), Decimal(0), Decimal("64")), by=None),
        _two_key_lift())
    assert rc == 2
    assert "--to needs a coordinate frame" in capsys.readouterr().err


def test_it_rejects_move_by_with_a_frame(capsys):
    rc, _ = _run_mover_key(
        _mk_args("move", "Lift", index=1, to=None, by=(Decimal(0), Decimal(0), Decimal("64")),
                 from_base=True),
        _two_key_lift())
    assert rc == 2
    assert "--by is a frame-agnostic delta" in capsys.readouterr().err


def test_it_rejects_move_at_index_zero(capsys):
    rc, _ = _run_mover_key(
        _mk_args("move", "Lift", index=0, to=(Decimal(0), Decimal(0), Decimal("10")), by=None,
                 from_base=True),
        _two_key_lift())
    assert rc == 2
    assert "key 0 is the base pose" in capsys.readouterr().err


def test_it_rejects_move_at_the_num_keys_index_with_a_raise_hint(capsys):
    # i == NumKeys on a 3-key mover: edit-only, so it points at `mover key count` to grow first.
    rc, _ = _run_mover_key(
        _mk_args("move", "Lift", index=3, to=(Decimal(0), Decimal(0), Decimal("10")), by=None,
                 from_base=True),
        _three_key_lift())
    assert rc == 2
    err = capsys.readouterr().err
    assert "has no key 3" in err and "mover key count" in err


def _three_key_lift():
    return _mover_level(props=[("KeyPos(1)", "(Z=128.000000)"), ("KeyPos(2)", "(Z=256.000000)"),
                               ("KeyRot(2)", "(Yaw=16384)"), ("NumKeys", "3")])


# ── remove / list: unchanged ──────────────────────────────────────────────────────────────────

def test_mover_key_remove_compacts(capsys):
    rc, cap = _run_mover_key(_mk_args("remove", "Lift", index=1), _three_key_lift())
    assert rc == 0
    props = dict(cap.actors["Lift"].props)
    assert props["KeyPos(1)"] == "(Z=256.000000)"        # old key 2 shifted down to 1
    assert props["KeyRot(1)"] == "(Yaw=16384)"
    assert "KeyPos(2)" not in props
    assert props.get("NumKeys", "2") == "2"


def test_mover_key_remove_below_two_rejected(capsys):
    rc, _ = _run_mover_key(_mk_args("remove", "Lift", index=1), _two_key_lift())
    assert rc == 2
    assert "at least 2 keys" in capsys.readouterr().err


def test_mover_key_remove_index_zero_rejected(capsys):
    rc, _ = _run_mover_key(_mk_args("remove", "Lift", index=0), _three_key_lift())
    assert rc == 2


def test_mover_key_list_prints_world_and_offset(capsys):
    lv = _two_key_lift()
    src = _fake_src(lv)
    with mock.patch("uedcli.cli.level_sources.resolve_level_source", return_value=src):
        rc = dispatch(_mk_args("list", "Lift"))
    assert rc == 0
    src.save.assert_not_called()                # list is read-only — nothing written
    out = capsys.readouterr().out
    assert "(base)" in out and "0,0,356" in out and "0,0,256" in out


def test_mover_key_list_rejects_non_mover(capsys):
    src = _fake_src(_brush_level())
    with mock.patch("uedcli.cli.level_sources.resolve_level_source", return_value=src):
        rc = dispatch(_mk_args("list", "B1"))
    assert rc == 2
    assert "is not a Mover" in capsys.readouterr().err


# --- `mover key add` removed (spec 2026-07-20) ------------------------------------------------

def test_it_no_longer_offers_a_mover_key_add_verb():
    import pytest
    from uedcli.cli import main as cli
    with pytest.raises(SystemExit):              # argparse rejects the retired subcommand
        cli.build_parser().parse_args(["mover", "key", "add", "Lift", "--at", "0,0,64"])


# --- case-insensitive FName resolution for mover key -----------------------------------------

def test_mover_key_wrong_case_name_resolves_and_succeeds(capsys):
    """A wrong-case mover name resolves case-insensitively and the keyframe op succeeds."""
    lv = _mover_level()               # actor stored as "Lift"
    rc, cap = _run_mover_key(
        _mk_args("move", "lift", index=1, to=(Decimal(0), Decimal(0), Decimal("64")), by=None,
                 from_base=True),
        _two_key_lift())
    assert rc == 0
    # The canonical name "Lift" must be in the captured level and carry the edited key
    assert "Lift" in cap.actors
    assert dict(cap.actors["Lift"].props)["KeyPos(1)"] == "(Z=64.000000)"


def test_mover_key_missing_name_gives_clean_error_and_exit2(capsys):
    """A completely absent mover name gives a clear error message and exits 2."""
    lv = _mover_level()
    rc, _ = _run_mover_key(_mk_args("count", "NoSuchMover", n=4), lv)
    assert rc == 2
    err = capsys.readouterr().err
    assert "NoSuchMover" in err


# --- no spurious BaseRot warning on a base-rotated mover -------------------------------------

def _rotated_mover_level():
    """A mover with a non-identity base Rotation (Yaw=8192 = 45 deg) and one keyframe."""
    a = make_brush_actor("Lift", cube(128, 16, 256),
                         location=(Decimal(0), Decimal(0), Decimal("100")),
                         mover_class="Engine.Mover")
    a.props += [("Rotation", "(Yaw=8192)"), ("KeyPos(1)", "(Z=256.000000)")]
    lv = Level()
    lv.actors["Lift"] = a
    return lv


def test_it_does_not_warn_on_a_base_rotated_mover_key_op(capsys):
    """No stderr caution on move/rotate against a base-rotated mover: `KeyPos` offsets are
    world-additive and `KeyRot` composes with `BaseRot` by FRotator field-addition — both
    confirmed (spike `2026-06-25-mover-keyframe-basepos-semantics.md`), so the old warning was
    pure noise."""
    for op_args in (
        _mk_args("move", "Lift", index=1, to=(Decimal("128"), Decimal(0), Decimal("356")), by=None,
                 from_world=True),
        _mk_args("rotate", "Lift", index=1, to=(Decimal(0), Decimal("16384"), Decimal(0)), by=None,
                 from_world=True)):
        rc, _ = _run_mover_key(op_args, _rotated_mover_level())
        assert rc == 0
        assert capsys.readouterr().err == ""


# --- actor add / stash capture input-safety: bad path / malformed / degenerate never traceback ---
def _add_args(file):
    return SimpleNamespace(cmd="actor", sub="add", file=file, container="c", project=None)


def test_actor_add_missing_file_is_clean_exit2(capsys):
    with mock.patch("uedcli.cli.level_sources.resolve_level_source", return_value=_fake_src(Level())):
        rc = dispatch(_add_args("/no/such/file.t3d"))
    assert rc == 2
    err = capsys.readouterr().err
    assert "cannot read T3D file" in err and "file.t3d" in err        # names the offending path


def test_actor_add_input_with_no_actors_is_clean_exit2(capsys, monkeypatch):
    import io
    monkeypatch.setattr("sys.stdin", io.StringIO("not a T3D block {{{"))
    with mock.patch("uedcli.cli.level_sources.resolve_level_source", return_value=_fake_src(Level())):
        rc = dispatch(_add_args("-"))
    assert rc == 2
    assert "no actors found" in capsys.readouterr().err


def test_actor_add_degenerate_brush_is_clean_exit2(capsys, monkeypatch):
    import io
    degen = ("Begin Actor Class=Brush Name=B\n Begin Brush Name=M\n Begin PolyList\n"
             " Begin Polygon\n Vertex +0,+0,+0\n Vertex +0,+0,+0\n Vertex +0,+0,+0\n"
             " End Polygon\n End PolyList\n End Brush\n End Actor\n")
    monkeypatch.setattr("sys.stdin", io.StringIO(degen))
    with mock.patch("uedcli.cli.level_sources.resolve_level_source", return_value=_fake_src(Level())):
        rc = dispatch(_add_args("-"))
    assert rc == 2
    assert "invalid brush geometry" in capsys.readouterr().err        # GeometryError → clean


def test_stash_capture_missing_from_t3d_is_clean_exit2(capsys):
    # Mock the register so the test reaches the file-read path regardless of an ambient project
    # (register resolution runs before the read; without this a standalone checkout would fail
    # with "not in a uedcli project" instead of the file error we're asserting).
    args = SimpleNamespace(cmd="stash", sub="capture", from_t3d=["/no/such/x.t3d"],
                           names=[], id=None, force=False, project=None)
    with mock.patch("uedcli.cli.commands.stash._resolve_stash_register", return_value=mock.Mock()):
        rc = dispatch(args)
    assert rc == 2
    assert "cannot read T3D file" in capsys.readouterr().err


def test_level_preview_list_actors_requires_game_and_map(tmp_path, monkeypatch, capsys):
    from uedcli.cli import dispatch as D
    proj = _preview_proj(tmp_path, {}, [], monkeypatch)
    # --list-actors without --game (or without --map) → exit 2, before any work
    assert D.dispatch(_preview_args(proj, tmp_path, shots=[], list_actors="Engine.PathNode")) == 2
    assert "--list-actors" in capsys.readouterr().err


def test_level_preview_list_actors_routes_and_prints(tmp_path, monkeypatch, capsys):
    from uedcli.cli import dispatch as D
    seen = {}
    monkeypatch.setattr("uedcli.preview_game.list_actors",
                        lambda **kw: (seen.update(kw), "PathNode0 1 2 3\n")[1])
    _patch_user_config(monkeypatch)
    proj = _preview_proj(tmp_path, {}, [], monkeypatch)
    args = _preview_args(proj, tmp_path, game=True, map="/x/y.dx", out_dir=None,
                         shots=[], list_actors="Engine.PathNode", sample=8)
    assert D.dispatch(args) == 0
    assert seen["cls"] == "Engine.PathNode" and seen["sample"] == 8 and seen["map_path"] == "/x/y.dx"
    assert capsys.readouterr().out == "PathNode0 1 2 3\n"


def test_level_preview_negative_sample_rejected(tmp_path, monkeypatch, capsys):
    from uedcli.cli import dispatch as D
    proj = _preview_proj(tmp_path, {}, [], monkeypatch)
    args = _preview_args(proj, tmp_path, game=True, map="/x/y.dx", out_dir=None,
                         shots=[], list_actors="Engine.PathNode", sample=-1)
    assert D.dispatch(args) == 2
    assert "--sample" in capsys.readouterr().err


def test_maps_key_pointing_at_a_file_is_a_clean_filesystem_error(tmp_path, capsys):
    """A `maps` key aimed at an existing FILE must exit 2 with the dispatch filesystem-error
    backstop, never a NotADirectoryError traceback (round-3 adversarial review, 2026-07-18)."""
    import argparse
    from uedcli.cli import dispatch
    proj = tmp_path / "repo"
    proj.mkdir()
    (proj / "uedcli.toml").write_text('game = "dx"\nmaps = "mapsf"\n')
    (proj / "mapsf").write_text("a file, not a dir")
    rc = dispatch.dispatch(argparse.Namespace(cmd="level", sub="create", project=str(proj),
                                              name="l1"))
    assert rc == 2
    err = capsys.readouterr().err
    assert "filesystem error" in err and "Traceback" not in err


def test_actor_show_miss_is_a_clean_exit_2(tmp_path, monkeypatch, capsys):
    """`actor show <no-match>` exits 2 with 'Actor not found: …' — never a silent empty rc 0 and
    never a KeyError traceback. `show` does NOT glob (owner ruling 2026-07-25), so a pattern is
    just another name that matches nothing: exit 2 too, and no blank line on stdout."""
    import argparse
    from uedcli.cli import dispatch
    from uedcli.model import Level
    monkeypatch.setattr("uedcli.cli.level_sources.resolve_level_source",
                        lambda args: mock.Mock(load=lambda: Level(actors={})))
    ns = lambda name: argparse.Namespace(cmd="actor", sub="show", name=name, project=None,
                                         tree=None)
    rc = dispatch.dispatch(ns("Ghost"))
    assert rc == 2
    cap = capsys.readouterr()
    assert "Actor not found: Ghost" in cap.err and "Traceback" not in cap.err
    assert dispatch.dispatch(ns("Ghost*")) == 2            # a pattern is a name like any other
    cap = capsys.readouterr()
    assert "Actor not found: Ghost*" in cap.err
    assert cap.out == ""                                   # and NO spurious blank stdout line


# ── _git_hint: report the PROJECT's own repo, not uedcli's (board bug 2) ──────


def _git_init(path, branch="work"):
    import subprocess
    path.mkdir(parents=True, exist_ok=True)
    subprocess.run(["git", "init", "-q", str(path)], check=True)
    subprocess.run(["git", "-C", str(path), "symbolic-ref", "HEAD", f"refs/heads/{branch}"],
                   check=True)
    top = subprocess.run(["git", "-C", str(path), "rev-parse", "--show-toplevel"],
                         capture_output=True, text=True).stdout.strip()
    return top


def test_git_hint_reports_the_projects_own_branch(tmp_path):
    from uedcli.cli.commands.level import _git_hint
    proj = tmp_path / "proj"
    _git_init(proj, branch="feature")
    hint = _git_hint(proj, proj / "maps", tool_repo_root=None)      # no tool repo in play
    assert hint is not None and "on branch feature" in hint


def test_git_hint_does_not_leak_the_tool_repo_branch(tmp_path):
    # A scratch project living INSIDE uedcli's own source tree: git walks up to the tool repo. We
    # must report "not a git repo" instead of the tool repo's branch (the reported bug).
    from uedcli.cli.commands.level import _git_hint
    tool = tmp_path / "toolrepo"
    tool_top = _git_init(tool, branch="uedcli-impl")
    proj = tool / "_scratch" / "proj"
    proj.mkdir(parents=True)
    hint = _git_hint(proj, proj / "maps", tool_repo_root=tool_top)
    assert hint is not None
    assert "uedcli-impl" not in hint and "not a git repo" in hint


def test_git_hint_reports_not_a_repo_outside_git(tmp_path):
    from uedcli.cli.commands.level import _git_hint
    proj = tmp_path / "loose"
    proj.mkdir()
    assert _git_hint(proj, proj / "maps", tool_repo_root=None) == "project is not a git repo"


# ── duplicate point-actor Location warning (board bug 4) ──────────────────────


def _point(name, loc):
    from uedcli.model import Actor
    D = tuple(Decimal(str(c)) for c in loc)
    return Actor(name=name, cls="Engine.Light", location=D, brush=None)


def test_warn_duplicate_point_locations_fires_on_shared_spot(capsys):
    from uedcli.cli.commands.actor.edit import _warn_duplicate_point_locations
    lvl = Level()
    for a in (_point("A_x", (10, 20, 30)), _point("B_y", (10, 20, 30)), _point("C_z", (0, 0, 0))):
        lvl.actors[a.name] = a
    _warn_duplicate_point_locations(lvl, ["A_x", "B_y", "C_z"])
    err = capsys.readouterr().err
    assert "2 actors share Location (10,20,30)" in err
    assert "A_x" in err and "B_y" in err
    assert "(0,0,0)" not in err                                    # C_z is alone → no warning


def test_warn_duplicate_point_locations_silent_when_distinct(capsys):
    from uedcli.cli.commands.actor.edit import _warn_duplicate_point_locations
    lvl = Level()
    for a in (_point("A_x", (1, 2, 3)), _point("B_y", (4, 5, 6))):
        lvl.actors[a.name] = a
    _warn_duplicate_point_locations(lvl, ["A_x", "B_y"])
    assert "share Location" not in capsys.readouterr().err


def test_warn_duplicate_point_locations_ignores_brushes(capsys):
    # Two brushes at the same Location are a normal CSG pattern, not a silent point-actor collision.
    from uedcli.cli.commands.actor.edit import _warn_duplicate_point_locations
    b1 = make_brush_actor("Box_a", cube(64, 64, 64), location=(Decimal(0), Decimal(0), Decimal(0)))
    b2 = make_brush_actor("Box_b", cube(64, 64, 64), location=(Decimal(0), Decimal(0), Decimal(0)))
    lvl = Level()
    lvl.actors["Box_a"] = b1
    lvl.actors["Box_b"] = b2
    _warn_duplicate_point_locations(lvl, ["Box_a", "Box_b"])
    assert "share Location" not in capsys.readouterr().err


# ── brush build --at help states it is the CENTER on all axes (board bug 4) ───


def test_brush_build_at_help_says_center_on_all_axes():
    from uedcli.cli.main import build_parser
    parser = build_parser()
    help_text = parser.format_help()
    # Find the box builder's --at help via the subparser tree.
    import io
    # Cheapest robust check: the box builder help mentions CENTER + Z.
    buf = io.StringIO()
    for action in parser._subparsers._group_actions:
        for name, sub in action.choices.items():
            if name == "brush":
                for a2 in sub._subparsers._group_actions:
                    box = a2.choices.get("build")
                    if box is None:
                        continue
                    for a3 in box._subparsers._group_actions:
                        cube_p = a3.choices.get("box") or a3.choices.get("cube")
                        if cube_p is not None:
                            buf.write(cube_p.format_help())
    text = buf.getvalue()
    assert "CENTER" in text and "including Z" in text


# ── brush replace <name> - : in-place shape swap keeping identity (board Geometry #9) ─────────


def _replace_dispatch(src, stdin_text, name="WALL", shape="-"):
    """Drive `brush replace <name> <shape>` with `stdin_text` on stdin, `src` as the trunk seam."""
    import io
    args = SimpleNamespace(cmd="brush", sub="replace", name=name, shape=shape, container="c")
    with mock.patch("uedcli.cli.level_sources.resolve_level_source", return_value=src), \
         mock.patch("sys.stdin", io.StringIO(stdin_text)):
        return dispatch(args)


def _wall_level():
    """A single subtract brush `WALL` (cube 64) at (10,20,30), Group=rooms, PolyFlags=32 — a rich
    identity to prove `brush replace` preserves Name/Location/CsgOper/Group/PolyFlags/model_name."""
    a = make_brush_actor("WALL", cube(64, 64, 64),
                         location=(Decimal(10), Decimal(20), Decimal(30)),
                         csg="subtract", group="rooms", poly_flags=32)
    lv = Level()
    lv.actors["WALL"] = a
    return lv


def _shape_t3d(name="NewShape", size=200):
    """A generator-style cube brush T3D (explicit CsgOper ⇒ NOT filtered as the builder brush)."""
    from uedcli.emit import emit_actor_t3d
    return emit_actor_t3d(make_brush_actor(name, cube(size, size, size), csg="add"))


def test_brush_replace_swaps_geometry_and_keeps_identity():
    src = _fake_src(_wall_level())
    before = src.load.return_value.actors["WALL"]
    old_model, old_props = before.brush.model_name, list(before.props)
    rc = _replace_dispatch(src, _shape_t3d(size=200))
    assert rc == 0
    after = src.save.call_args.kwargs["level"].actors["WALL"]
    # Geometry swapped: the new box's half-extent 100 vertex is present, the old 32 is gone.
    verts = {v for p in after.brush.polys for v in p.vertices}
    assert (Decimal(100), Decimal(100), Decimal(100)) in verts
    assert (Decimal(32), Decimal(32), Decimal(32)) not in verts
    # Identity kept: Name, Location, CsgOper/Group/PolyFlags props, and the brush model_name.
    assert after.name == "WALL"
    assert after.location == (Decimal(10), Decimal(20), Decimal(30))
    assert list(after.props) == old_props            # CsgOper=CSG_Subtract, PolyFlags=32, Group, Brush ref
    assert after.brush.model_name == old_model       # stays Model_WALL (matches the Brush= ref)
    assert src.save.call_args.kwargs["touched"] == ["WALL"]


def test_brush_replace_empty_stdin_is_a_clean_noop():
    src = _fake_src(_wall_level())
    assert _replace_dispatch(src, "   \n  ") == 0
    src.save.assert_not_called()                     # no write on an empty pipe


def test_brush_replace_unknown_name_is_clean_exit_2(capsys):
    src = _fake_src(_wall_level())
    rc = _replace_dispatch(src, _shape_t3d(), name="NOPE")
    assert rc == 2
    err = capsys.readouterr().err
    assert "Actor not found: NOPE" in err and "Traceback" not in err
    src.save.assert_not_called()


def test_brush_replace_non_brush_target_is_clean_exit_2(capsys):
    lv = Level()
    lv.actors["Lamp"] = make_brush_actor("Lamp", cube(8, 8, 8))   # start from a brush…
    lv.actors["Lamp"].brush = None                                # …then make it a point actor
    lv.actors["Lamp"].cls = "Engine.Light"
    src = _fake_src(lv)
    rc = _replace_dispatch(src, _shape_t3d(), name="Lamp")
    assert rc == 2
    assert "Lamp is not a brush" in capsys.readouterr().err
    src.save.assert_not_called()


def test_brush_replace_no_brush_geometry_is_clean_exit_2(capsys):
    src = _fake_src(_wall_level())
    rc = _replace_dispatch(src, "Begin Map\nBegin Actor Class=Light Name=L1\nEnd Actor\nEnd Map")
    assert rc == 2
    assert "no brush geometry" in capsys.readouterr().err
    src.save.assert_not_called()


def test_brush_replace_more_than_one_brush_is_clean_exit_2(capsys):
    src = _fake_src(_wall_level())
    rc = _replace_dispatch(src, _shape_t3d("A", 100) + _shape_t3d("B", 120))
    assert rc == 2
    assert "2 brush actors" in capsys.readouterr().err
    src.save.assert_not_called()


def test_brush_replace_shape_arg_must_be_dash_exit_2(capsys):
    src = _fake_src(_wall_level())
    rc = _replace_dispatch(src, _shape_t3d(), shape="cube.t3d")
    assert rc == 2
    assert "must be `-`" in capsys.readouterr().err
    src.save.assert_not_called()
