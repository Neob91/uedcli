"""actor-name composition pipe — `-` (names from stdin) on the name-taking verbs, and
`actor add`'s Names→stdout output. Spec in board item `actor-name-composition-pipe` (§8 authoritative).

Offline: the trunk seam (`_resolve_level_source`) and, for `prop`, the four schema seams are
mocked, and stdin is a `StringIO`. These are the verb-level pipe contracts; the shared helper's
own edge cases (mixing/empty/dedup) are asserted here per verb.
"""
from __future__ import annotations

import io
from decimal import Decimal
from types import SimpleNamespace
from unittest import mock

from uedcli.cli import dispatch as dispatch_mod
from uedcli.cli.dispatch import dispatch
from uedcli.model import Actor, Level, parse_t3d
from uedcli.uprops import Prop


# ── fixtures ──────────────────────────────────────────────────────────────────────

def _actor(name, cls="Engine.Brush", props=None, location=(0, 0, 0)):
    """The Location is STATED deliberately. These tests are about name composition (`-`, dedupe,
    canonicalisation); an actor that states NO Location sends `actor rotate --by` to the class schema
    for its default one — `Engine.Camera` really defaults it to (-500,-300,300) — which needs a
    resolvable package path, i.e. a real project. Stating a Location keeps these the offline unit
    tests they are meant to be."""
    loc = None if location is None else tuple(Decimal(str(c)) for c in location)
    return Actor(name=name, cls=cls, location=loc, props=list(props or []))


def _two_actor_level():
    """Two actors of DIFFERENT classes — so the multi-actor `prop` path exercises per-actor
    class context (piped actors may be different classes)."""
    lv = Level()
    lv.actors["Wall1"] = _actor("Wall1", cls="Engine.Brush", props=[("Group", "cells")])
    lv.actors["Wall2"] = _actor("Wall2", cls="Engine.Light", props=[("Group", "cells")])
    lv.order = ["Wall1", "Wall2"]
    return lv


def _prop(name, kind):
    return Prop(name=name, kind=kind, array_dim=1, property_flags=0, type_ref=0,
                type_name=None, owner="Engine.Actor")


def _schema(cls, project=None):
    """Group on every class (Engine.Actor); Mass ONLY on Engine.Brush — so a `Mass=` token is a
    per-class unknown on the Light, exercising cross-class two-phase atomicity."""
    s = {"group": _prop("Group", "NameProperty")}
    if cls.casefold() == "engine.brush":
        s["mass"] = _prop("Mass", "FloatProperty")
    return s


def _fake_src(level):
    src = mock.Mock()
    src.load.return_value = level
    return src


def _drive(args, level=None, stdin="", *, src=None):
    """Drive the top-level `dispatch` with `stdin` as fake stdin. Returns (rc, src)."""
    if src is None:
        src = _fake_src(level)
    with mock.patch("uedcli.cli.level_sources.resolve_level_source", return_value=src), \
            mock.patch("sys.stdin", io.StringIO(stdin)):
        rc = dispatch(args)
    return rc, src


def _drive_prop(args, level, stdin="", *, src=None):
    """`dispatch` with stdin AND the four prop schema seams mocked (offline)."""
    if src is None:
        src = _fake_src(level)
    with mock.patch("uedcli.cli.level_sources.resolve_level_source", return_value=src), \
            mock.patch("sys.stdin", io.StringIO(stdin)), \
            mock.patch("uedcli.cli.resources.resolve_project",
                       side_effect=dispatch_mod.ProjectError("no project")), \
            mock.patch("uedcli.cli.resources.class_schema", _schema), \
            mock.patch("uedcli.cli.resources.class_defaults", lambda cls, project=None: {}), \
            mock.patch("uedcli.cli.resources.struct_members", lambda p, project=None: []), \
            mock.patch("uedcli.cli.resources.enum_names", lambda p, project=None: p.enum_value_names):
        rc = dispatch(args)
    return rc, src


def _delete_args(names):
    return SimpleNamespace(cmd="actor", sub="delete", names=list(names), container="x")


def _rotate_args(names):
    return SimpleNamespace(cmd="actor", sub="rotate", names=list(names),
                           by=(Decimal(0), Decimal(90), Decimal(0)),
                           pivot=None, pivot_actor=None, container="x")


def _prop_args(propsub, name, tokens=(), *, kv=False):
    return SimpleNamespace(cmd="actor", sub="prop", propsub=propsub, name=name,
                           tokens=list(tokens), kv=kv)


def _show_args(name):
    return SimpleNamespace(cmd="actor", sub="show", name=name)


# ── delete - ──────────────────────────────────────────────────────────────────────

def test_delete_dash_reads_names_from_stdin():
    lv = _two_actor_level()
    rc, src = _drive(_delete_args(["-"]), lv, stdin="Wall1\nWall2\n")
    assert rc == 0
    actors = src.save.call_args.kwargs["level"].actors
    assert "Wall1" not in actors and "Wall2" not in actors


def test_delete_dash_tolerates_crlf_blank_lines_and_bom():
    # `find`'s output is the intended producer, but be robust: CRLF line endings, a leading UTF-8
    # BOM, and blank lines must not corrupt the first/any name (str.strip alone leaves a BOM).
    lv = _two_actor_level()
    rc, src = _drive(_delete_args(["-"]), lv, stdin="﻿Wall1\r\n\r\nWall2\r\n")
    assert rc == 0
    assert src.save.call_args.kwargs["args"]["names"] == ["Wall1", "Wall2"]


def test_delete_dash_empty_stdin_is_noop_exit0():
    lv = _two_actor_level()
    rc, src = _drive(_delete_args(["-"]), lv, stdin="")
    assert rc == 0
    src.save.assert_not_called()                         # trunk untouched


def test_delete_dash_unknown_piped_name_exit2_trunk_untouched(capsys):
    lv = _two_actor_level()
    rc, src = _drive(_delete_args(["-"]), lv, stdin="Wall1\nNope\n")
    assert rc == 2
    assert "Actors not found: Nope" in capsys.readouterr().err
    src.save.assert_not_called()


def test_delete_dash_mixed_with_cli_name_exit2(capsys):
    lv = _two_actor_level()
    rc, src = _drive(_delete_args(["-", "Wall1"]), lv, stdin="Wall2\n")
    assert rc == 2
    assert "cannot be combined" in capsys.readouterr().err
    src.save.assert_not_called()


def test_delete_dash_dedupes_on_canonical_name():
    lv = _two_actor_level()
    rc, src = _drive(_delete_args(["-"]), lv, stdin="Wall1\nwall1\nWALL1\n")
    assert rc == 0
    assert src.save.call_args.kwargs["args"]["names"] == ["Wall1"]   # deduped, not popped twice


# ── rotate - ────────────────────────────────────────────────────────────────────────

def test_rotate_dash_reads_names_from_stdin():
    lv = _two_actor_level()
    rc, src = _drive(_rotate_args(["-"]), lv, stdin="Wall1\n")
    assert rc == 0
    assert src.save.call_args.kwargs["args"]["names"] == ["Wall1"]


def test_rotate_dash_empty_stdin_is_noop_exit0():
    lv = _two_actor_level()
    rc, src = _drive(_rotate_args(["-"]), lv, stdin="")
    assert rc == 0
    src.save.assert_not_called()


def test_rotate_dash_mixed_with_cli_name_exit2(capsys):
    lv = _two_actor_level()
    rc, src = _drive(_rotate_args(["Wall1", "-"]), lv, stdin="Wall2\n")
    assert rc == 2
    assert "cannot be combined" in capsys.readouterr().err
    src.save.assert_not_called()


def test_rotate_dash_dedupes_on_canonical_name():
    # rotate double-apply is NON-idempotent (unlike delete's re-pop), so its dedupe is the
    # motivating hazard (spec §8) — pin it: a case-varied repeat rotates the actor once.
    lv = _two_actor_level()
    rc, src = _drive(_rotate_args(["-"]), lv, stdin="Wall1\nwall1\nWALL1\n")
    assert rc == 0
    assert src.save.call_args.kwargs["args"]["names"] == ["Wall1"]


def test_rotate_dash_unknown_piped_name_exit2(capsys):
    lv = _two_actor_level()
    rc, src = _drive(_rotate_args(["-"]), lv, stdin="Nope\n")
    assert rc == 2
    assert "Actors not found: Nope" in capsys.readouterr().err
    src.save.assert_not_called()


# ── prop set - (multi-actor, two-phase atomic) ──────────────────────────────────────

def test_prop_set_dash_applies_to_every_piped_actor():
    lv = _two_actor_level()
    rc, src = _drive_prop(_prop_args("set", "-", ["Group=walls"]), lv, stdin="Wall1\nWall2\n")
    assert rc == 0
    saved = src.save.call_args.kwargs
    assert saved["args"]["names"] == ["Wall1", "Wall2"]
    for n in ("Wall1", "Wall2"):
        assert ("Group", "walls") in lv.actors[n].props


def test_prop_set_dash_bad_token_leaves_all_untouched(capsys):
    # `Mass=5` is unknown on the Light (Wall2) — planning it raises AFTER Wall1's plan is built
    # but BEFORE any actor is mutated (two-phase). Both actors keep their original props.
    lv = _two_actor_level()
    before = {n: list(a.props) for n, a in lv.actors.items()}
    rc, src = _drive_prop(_prop_args("set", "-", ["Mass=5"]), lv, stdin="Wall1\nWall2\n")
    assert rc == 2
    assert "unknown property Mass" in capsys.readouterr().err
    src.save.assert_not_called()
    for n, a in lv.actors.items():
        assert a.props == before[n]                      # NOTHING mutated, incl. the valid Wall1


def test_prop_set_dash_empty_stdin_is_noop_exit0():
    lv = _two_actor_level()
    rc, src = _drive_prop(_prop_args("set", "-", ["Group=walls"]), lv, stdin="")
    assert rc == 0
    src.save.assert_not_called()


def test_prop_set_dash_unknown_piped_name_exit2(capsys):
    lv = _two_actor_level()
    rc, src = _drive_prop(_prop_args("set", "-", ["Group=walls"]), lv, stdin="Nope\n")
    assert rc == 2
    assert "Actors not found: Nope" in capsys.readouterr().err
    src.save.assert_not_called()


def test_prop_set_dash_dedupes_on_canonical_name():
    lv = _two_actor_level()
    rc, src = _drive_prop(_prop_args("set", "-", ["Group=walls"]), lv, stdin="Wall1\nwall1\n")
    assert rc == 0
    assert src.save.call_args.kwargs["args"]["names"] == ["Wall1"]


# ── prop unset - (its own plan_edit branch — clears members / whole props) ───────────

def test_prop_unset_dash_clears_prop_on_every_piped_actor():
    lv = _two_actor_level()                              # both seeded Group=cells
    rc, src = _drive_prop(_prop_args("unset", "-", ["Group"]), lv, stdin="Wall1\nWall2\n")
    assert rc == 0
    assert src.save.call_args.kwargs["args"]["names"] == ["Wall1", "Wall2"]
    for n in ("Wall1", "Wall2"):
        assert all(k != "Group" for k, _v in lv.actors[n].props)   # reverted to class default


def test_prop_unset_dash_bad_token_leaves_all_untouched(capsys):
    # `Mass` is unknown on the Light (Wall2) — planning raises before ANY actor is mutated.
    lv = _two_actor_level()
    before = {n: list(a.props) for n, a in lv.actors.items()}
    rc, src = _drive_prop(_prop_args("unset", "-", ["Mass"]), lv, stdin="Wall1\nWall2\n")
    assert rc == 2
    assert "unknown property Mass" in capsys.readouterr().err
    src.save.assert_not_called()
    for n, a in lv.actors.items():
        assert a.props == before[n]


def test_prop_get_dash_empty_stdin_is_noop_exit0(capsys):
    lv = _two_actor_level()
    rc, src = _drive_prop(_prop_args("get", "-", ["Group"]), lv, stdin="")
    assert rc == 0
    assert capsys.readouterr().out.strip() == ""
    src.load.assert_not_called()                         # empty stdin never touches the trunk


# ── prop get - (multi-actor, name-prefixed KV) ──────────────────────────────────────

def test_prop_get_dash_prefixes_name_and_key(capsys):
    lv = _two_actor_level()
    lv.actors["Wall1"].props = [("Group", "north")]
    lv.actors["Wall2"].props = [("Group", "south")]
    rc, _src = _drive_prop(_prop_args("get", "-", ["Group"]), lv, stdin="Wall1\nWall2\n")
    assert rc == 0
    out = capsys.readouterr().out.splitlines()
    assert out == ["Wall1\tGroup=north", "Wall2\tGroup=south"]


def test_prop_get_single_name_keeps_bare_output(capsys):
    lv = _two_actor_level()
    lv.actors["Wall1"].props = [("Group", "north")]
    rc, _src = _drive_prop(_prop_args("get", "Wall1", ["Group"]), lv)
    assert rc == 0
    assert capsys.readouterr().out.splitlines() == ["north"]   # bare, un-prefixed


def test_prop_get_dash_single_resolved_actor_still_name_prefixed(capsys):
    # Output shape is keyed on WHETHER `-` was used, NOT on the resolved count (spec §8): a `-`
    # that resolves to exactly ONE actor still gets `<name>\t<key>=<value>` (a regression keying
    # on len(names)==1 would wrongly fall back to bare output).
    lv = _two_actor_level()
    lv.actors["Wall1"].props = [("Group", "north")]
    rc, _src = _drive_prop(_prop_args("get", "-", ["Group"]), lv, stdin="Wall1\n")
    assert rc == 0
    assert capsys.readouterr().out.splitlines() == ["Wall1\tGroup=north"]


# ── show - ──────────────────────────────────────────────────────────────────────────

def test_show_dash_concatenates_blocks_in_piped_order(capsys):
    lv = _two_actor_level()
    rc, _src = _drive(_show_args("-"), lv, stdin="Wall1\nWall2\n")
    assert rc == 0
    out = capsys.readouterr().out
    assert "Name=Wall1" in out and "Name=Wall2" in out
    assert out.index("Name=Wall1") < out.index("Name=Wall2")   # piped order


def test_show_dash_empty_stdin_is_noop_exit0(capsys):
    lv = _two_actor_level()
    rc, _src = _drive(_show_args("-"), lv, stdin="")
    assert rc == 0
    assert capsys.readouterr().out.strip() == ""


def test_show_dash_unknown_piped_name_exit2(capsys):
    lv = _two_actor_level()
    rc, _src = _drive(_show_args("-"), lv, stdin="Nope\n")
    assert rc == 2
    assert "Actors not found: Nope" in capsys.readouterr().err


# ── duplicate (sugar for `show <names> | add -`) ─────────────────────────────────────

def _dup_args(names, folder=None, by=(Decimal(0), Decimal(0), Decimal(0)), at=None, label=None):
    # duplicate now REQUIRES a placement (argparse enforces the --by/--at mutex); these
    # handler-level drives supply a no-op --by 0,0,0 by default so copies land where the source is.
    return SimpleNamespace(cmd="actor", sub="duplicate", names=list(names), folder=folder,
                           by=by, at=at, label=label)


def _dup_level():
    lv = Level()
    lv.actors["Lamp"] = _actor("Lamp", cls="Engine.Light")
    lv.actors["Lamp"].location = (Decimal(1), Decimal(2), Decimal(3))
    lv.order = ["Lamp"]
    return lv


def test_duplicate_copies_with_a_fresh_name_prints_it_to_stdout(capsys):
    lv = _dup_level()
    rc, src = _drive(_dup_args(["Lamp"]), lv)
    assert rc == 0
    cap = capsys.readouterr()
    new = cap.out.strip().splitlines()
    assert len(new) == 1 and new[0].startswith("Lamp_") and new[0] != "Lamp"   # fresh <stem>_<rand>
    assert "duplicated 1 actor(s)" in cap.err                                  # count → stderr
    assert new[0] in lv.actors and lv.actors[new[0]].location == (Decimal(1), Decimal(2), Decimal(3))
    assert "Lamp" in lv.actors                                               # ORIGINAL survives the copy
    src.save.assert_called_once()                                             # persisted


def test_duplicate_dash_reads_names_from_stdin_and_dupes_each(capsys):
    lv = _dup_level()
    lv.actors["Lamp2"] = _actor("Lamp2", cls="Engine.Light")
    lv.actors["Lamp2"].location = (Decimal(0), Decimal(0), Decimal(0))
    lv.order.append("Lamp2")
    rc, _src = _drive(_dup_args(["-"]), lv, stdin="Lamp\nLamp2\n")
    assert rc == 0
    assert len(capsys.readouterr().out.strip().splitlines()) == 2            # both copied


def test_duplicate_empty_stdin_is_noop_exit0(capsys):
    lv = _dup_level()
    rc, src = _drive(_dup_args(["-"]), lv, stdin="")
    assert rc == 0
    assert capsys.readouterr().out.strip() == ""
    src.save.assert_not_called()                                             # nothing written


def test_duplicate_unknown_name_exit2(capsys):
    lv = _dup_level()
    rc, src = _drive(_dup_args(["Nope"]), lv)
    assert rc == 2
    assert "Actors not found: Nope" in capsys.readouterr().err
    src.save.assert_not_called()


def test_duplicate_folder_override_stamps_the_copy(capsys):
    lv = _dup_level()
    rc, _src = _drive(_dup_args(["Lamp"], folder="deco.lamps"), lv)
    assert rc == 0
    new = capsys.readouterr().out.strip()
    assert lv.actors[new].folder == "deco.lamps"


# ── move does NOT accept - ───────────────────────────────────────────────────────────

def test_move_dash_is_treated_as_an_unknown_actor_not_stdin(capsys):
    lv = _two_actor_level()
    args = SimpleNamespace(cmd="actor", sub="move", name="-",
                           to=(Decimal(1), Decimal(2), Decimal(3)), by=None, container="x")
    rc, src = _drive(args, lv, stdin="Wall1\n")
    assert rc == 2
    assert "Actor not found: -" in capsys.readouterr().err
    src.save.assert_not_called()


# ── end-to-end: build | add - | prop set - ──────────────────────────────────────────

def test_build_add_prop_pipe_end_to_end(capsys):
    """The real pipeline: `brush build cube` emits T3D → `actor add -` ingests it and prints the
    allocated Name → `actor prop set -` reads that Name and sets a prop on the added actor."""
    src = _fake_src(parse_t3d("Begin Map\nEnd Map"))

    # Stage 1 — build: generator writes T3D to stdout (stateless, no level/project).
    build_args = SimpleNamespace(
        cmd="brush", sub="build", shape="cube",
        width=64.0, breadth=64.0, height=64.0,
        at=(Decimal(0), Decimal(0), Decimal(0)), base_name="Wall",
        csg=None, solidity=None, group=None, texture=None, mover_class=None)
    assert dispatch(build_args) == 0
    t3d = capsys.readouterr().out
    assert "Begin Actor" in t3d

    # Stage 2 — add -: ingest the T3D, print the allocated Name(s) to stdout (count → stderr).
    add_args = SimpleNamespace(cmd="actor", sub="add", file="-", container="x")
    with mock.patch("uedcli.cli.level_sources.resolve_level_source", return_value=src), \
            mock.patch("uedcli.cli.ingest.validate_ingest_actors", lambda actors, args: None), \
            mock.patch("sys.stdin", io.StringIO(t3d)):
        assert dispatch(add_args) == 0
    add_cap = capsys.readouterr()
    names = add_cap.out.splitlines()
    assert len(names) == 1 and names[0].rpartition("_")[0] == "Wall"
    assert "added 1 actor(s)" in add_cap.err

    # Stage 3 — prop set -: the added Name feeds straight into the multi-actor prop setter.
    prop_args = _prop_args("set", "-", ["Group=walls"])
    rc, _src = _drive_prop(prop_args, src.load.return_value, stdin=add_cap.out, src=src)
    assert rc == 0
    added = src.load.return_value.actors[names[0]]
    assert ("Group", "walls") in added.props


# ── argparse pins: the real parser accepts a bare `-` in every `-` positional ─────────

def test_real_parser_accepts_dash_in_name_positionals():
    from uedcli.cli.main import build_parser
    p = build_parser()
    assert p.parse_args(["actor", "delete", "-"]).names == ["-"]
    assert p.parse_args(["actor", "rotate", "-", "--by", "0,90,0"]).names == ["-"]
    assert p.parse_args(["actor", "show", "-"]).name == "-"
    for sub in ("set", "get", "unset"):
        ns = p.parse_args(["actor", "prop", sub, "-", "Group"]
                          if sub != "set" else ["actor", "prop", "set", "-", "Group=x"])
        assert ns.name == "-"
    # delete/rotate still accept `-` alongside a real name at the parser level (the SEMANTIC
    # rejection lives in dispatch, so both tokens must survive argparse).
    assert p.parse_args(["actor", "delete", "-", "Wall1"]).names == ["-", "Wall1"]
