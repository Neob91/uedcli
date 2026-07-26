"""Actor label verbs (plan Task 2.2 + 2.3) — end-to-end through the real argparse parser.

`actor label add|remove|clear|get`, `actor find --label/--no-label`, and `actor add --label`.
Labels are TRUNK-ONLY this slice: the verbs reject `--tree stash|prefab`. CLI tests drive the parser
through `dispatch()` so argparse defaults + the guards are exercised; `_stub_author_validation`
(autouse in conftest) no-ops the class/texture ingest gate so `actor add` runs offline.
"""
import io
from unittest import mock

import pytest

from uedcli import cli, dispatch, trunk
from uedcli.model import Actor, Level


def _mkproject(tmp_path, monkeypatch, actors):
    root = tmp_path / "proj"
    (root / "maps" / "lvl").mkdir(parents=True)
    (root / "uedcli.toml").write_text('game = "deusex"\n')
    monkeypatch.setenv("UEDCLI_PROJECT", str(root))
    lvl = Level(actors={a.name: a for a in actors}, order=[a.name for a in actors])
    ranks = dict(zip([a.name for a in actors], trunk.initial_ranks(len(actors)) or []))
    trunk.write_level(root / "maps" / "lvl", lvl, ranks)
    monkeypatch.setenv("UEDCLI_LEVEL", "lvl")
    return root


def _run(argv, stdin=""):
    args = cli.build_parser().parse_args(argv)
    with mock.patch("sys.stdin", io.StringIO(stdin)):
        return dispatch.dispatch(args)


def _read(root):
    lvl, _ranks = trunk.read_level(root / "maps" / "lvl")
    return lvl


def _light(name, **kw):
    return Actor(name=name, cls="Engine.Light", location=(0, 0, 0), **kw)


# ── add / remove / clear ─────────────────────────────────────────────────────────────

def test_it_adds_labels_as_a_union(tmp_path, monkeypatch, capsys):
    root = _mkproject(tmp_path, monkeypatch, [_light("A_1", labels=frozenset({"hero"}))])
    assert _run(["actor", "label", "add", "A_1", "--label", "lighting", "--label", "flammable"]) == 0
    assert _read(root).actors["A_1"].labels == {"hero", "lighting", "flammable"}


def test_it_echoes_touched_names_to_stdout(tmp_path, monkeypatch, capsys):
    _mkproject(tmp_path, monkeypatch, [_light("A_1"), _light("B_2")])
    assert _run(["actor", "label", "add", "A_1", "B_2", "--label", "lit"]) == 0
    out = capsys.readouterr().out
    assert out.split() == ["A_1", "B_2"]


def test_it_removes_labels_and_missing_is_a_noop(tmp_path, monkeypatch):
    root = _mkproject(tmp_path, monkeypatch,
                      [_light("A_1", labels=frozenset({"lighting", "hero"}))])
    assert _run(["actor", "label", "remove", "A_1", "--label", "hero", "--label", "absent"]) == 0
    assert _read(root).actors["A_1"].labels == {"lighting"}


def test_it_clears_all_labels_and_removes_the_sidecar(tmp_path, monkeypatch):
    root = _mkproject(tmp_path, monkeypatch,
                      [_light("A_1", labels=frozenset({"lighting", "hero"}))])
    assert (root / "maps" / "lvl" / "actors" / "A_1" / "labels").exists()  # precondition
    assert _run(["actor", "label", "clear", "A_1"]) == 0
    assert _read(root).actors["A_1"].labels == frozenset()
    assert not (root / "maps" / "lvl" / "actors" / "A_1" / "labels").exists()


# ── get ──────────────────────────────────────────────────────────────────────────────

def test_it_gets_labels_sorted_and_comma_joined(tmp_path, monkeypatch, capsys):
    _mkproject(tmp_path, monkeypatch,
               [_light("A_1", labels=frozenset({"hero", "lighting"})), _light("B_2")])
    assert _run(["actor", "label", "get", "A_1", "B_2"]) == 0
    assert capsys.readouterr().out == "A_1\thero,lighting\nB_2\t(none)\n"


def test_it_gets_labels_as_json(tmp_path, monkeypatch, capsys):
    import json
    _mkproject(tmp_path, monkeypatch,
               [_light("A_1", labels=frozenset({"hero", "lighting"})), _light("B_2")])
    assert _run(["actor", "label", "get", "A_1", "B_2", "--json"]) == 0
    assert json.loads(capsys.readouterr().out) == {"A_1": ["hero", "lighting"], "B_2": []}


# ── validate-all-then-apply ────────────────────────────────────────────────────────────

def test_it_rejects_a_bad_label_leaving_all_untouched(tmp_path, monkeypatch, capsys):
    root = _mkproject(tmp_path, monkeypatch, [_light("A_1"), _light("B_2")])
    assert _run(["actor", "label", "add", "A_1", "B_2", "--label", "a.b"]) == 2
    assert "a.b" in capsys.readouterr().err
    assert _read(root).actors["A_1"].labels == frozenset()
    assert _read(root).actors["B_2"].labels == frozenset()


def test_it_rejects_a_leading_dash_label(tmp_path, monkeypatch, capsys):
    # `--label=-x` (the `=` form) passes `-x` as a value past argparse so the label validator — not
    # argparse's option parser — rejects it, naming the offending value (spec §9 leading-`-` guard).
    root = _mkproject(tmp_path, monkeypatch, [_light("A_1")])
    assert _run(["actor", "label", "add", "A_1", "--label=-x"]) == 2
    assert "-x" in capsys.readouterr().err
    assert _read(root).actors["A_1"].labels == frozenset()


def test_it_rejects_an_unknown_name_leaving_all_untouched(tmp_path, monkeypatch, capsys):
    root = _mkproject(tmp_path, monkeypatch, [_light("A_1")])
    assert _run(["actor", "label", "add", "A_1", "Nope", "--label", "lit"]) == 2
    assert "Nope" in capsys.readouterr().err
    assert _read(root).actors["A_1"].labels == frozenset()


# ── stdin / no-op ──────────────────────────────────────────────────────────────────────

def test_it_reads_names_from_stdin(tmp_path, monkeypatch):
    root = _mkproject(tmp_path, monkeypatch, [_light("A_1"), _light("B_2")])
    assert _run(["actor", "label", "add", "-", "--label", "lit"], stdin="A_1\nB_2\n") == 0
    assert _read(root).actors["A_1"].labels == {"lit"}
    assert _read(root).actors["B_2"].labels == {"lit"}


def test_it_is_a_clean_noop_on_empty_stdin(tmp_path, monkeypatch):
    _mkproject(tmp_path, monkeypatch, [_light("A_1")])
    assert _run(["actor", "label", "add", "-", "--label", "lit"], stdin="") == 0


# ── trunk-only guard ────────────────────────────────────────────────────────────────────

@pytest.mark.parametrize("sub,extra", [
    ("add", ["--label", "lit"]), ("remove", ["--label", "lit"]), ("clear", []), ("get", []),
])
def test_it_rejects_stash_target(tmp_path, monkeypatch, capsys, sub, extra):
    _mkproject(tmp_path, monkeypatch, [_light("A_1")])
    assert _run(["actor", "label", sub, *extra, "--tree", "stash/foo", "A_1"]) == 2
    assert "labels apply only to a level" in capsys.readouterr().err


# ── find --label / --no-label (Task 2.3) ───────────────────────────────────────────────

def _labelled_project(tmp_path, monkeypatch):
    return _mkproject(tmp_path, monkeypatch, [
        _light("A_1", labels=frozenset({"lighting", "dup-a1b2c3"})),
        _light("B_2", labels=frozenset({"lighting"})),
        _light("C_3"),
    ])


def test_it_finds_by_label_glob(tmp_path, monkeypatch, capsys):
    _labelled_project(tmp_path, monkeypatch)
    assert _run(["actor", "find", "--label", "dup-*"]) == 0
    assert capsys.readouterr().out.split() == ["A_1"]


def test_it_ors_repeated_find_label(tmp_path, monkeypatch, capsys):
    _labelled_project(tmp_path, monkeypatch)
    assert _run(["actor", "find", "--label", "dup-*", "--label", "nope"]) == 0
    assert capsys.readouterr().out.split() == ["A_1"]


def test_it_ands_find_label_with_name(tmp_path, monkeypatch, capsys):
    _labelled_project(tmp_path, monkeypatch)
    assert _run(["actor", "find", "--label", "lighting", "--name", "B_2"]) == 0
    assert capsys.readouterr().out.split() == ["B_2"]


def test_it_finds_no_label(tmp_path, monkeypatch, capsys):
    _labelled_project(tmp_path, monkeypatch)
    assert _run(["actor", "find", "--no-label"]) == 0
    assert capsys.readouterr().out.split() == ["C_3"]


def test_it_rejects_a_char_class_find_label_pattern(tmp_path, monkeypatch, capsys):
    _labelled_project(tmp_path, monkeypatch)
    assert _run(["actor", "find", "--label", "dup-[a]"]) == 2
    assert "dup-[a]" in capsys.readouterr().err


def test_find_label_and_no_label_are_mutually_exclusive(tmp_path, monkeypatch):
    with pytest.raises(SystemExit):
        cli.build_parser().parse_args(["actor", "find", "--label", "a", "--no-label"])


def test_it_rejects_find_label_on_stash_target(tmp_path, monkeypatch, capsys):
    _labelled_project(tmp_path, monkeypatch)
    assert _run(["actor", "find", "--label", "a", "--tree", "stash/x"]) == 2
    assert "labels apply only to a level" in capsys.readouterr().err


# ── actor add --label + carrier precedence (Task 2.3) ───────────────────────────────────

_LIGHT_T3D = ("Begin Actor Class=Engine.Light Name=Src\n"
              "    Name=\"Src\"\nEnd Actor\n")


def test_actor_add_has_no_label_flag(tmp_path, monkeypatch, capsys):
    # --label was removed from `actor add` (moved to the generators, 2026-07-24 17:04); argparse rejects
    # it. The label-carrier persist path is covered by test_it_round_trips_labels_via_show_then_add.
    root = _mkproject(tmp_path, monkeypatch, [_light("Seed_1")])
    with pytest.raises(SystemExit) as e:
        _run(["actor", "add", "-", "--label", "lit"], stdin=_LIGHT_T3D)
    assert e.value.code == 2
    assert set(_read(root).actors) == {"Seed_1"}         # nothing added


def test_it_persists_the_incoming_label_carrier(tmp_path, monkeypatch, capsys):
    # No override channel any more — the incoming `// uedcli-labels:` carrier wins as-is.
    root = _mkproject(tmp_path, monkeypatch, [_light("Seed_1")])
    carried = ("Begin Actor Class=Engine.Light Name=Src\n"
               "    // uedcli-labels: fromcarrier\n"
               "    Name=\"Src\"\nEnd Actor\n")
    assert _run(["actor", "add", "-"], stdin=carried) == 0
    added = capsys.readouterr().out.split()
    assert _read(root).actors[added[0]].labels == {"fromcarrier"}


def test_it_round_trips_labels_via_show_then_add(tmp_path, monkeypatch, capsys):
    root = _mkproject(tmp_path, monkeypatch,
                      [_light("A_1", labels=frozenset({"lighting", "hero"}))])
    assert _run(["actor", "show", "A_1"]) == 0
    shown = capsys.readouterr().out
    assert _run(["actor", "add", "-"], stdin=shown) == 0
    added = [n for n in capsys.readouterr().out.split() if n != "A_1"]
    assert _read(root).actors[added[0]].labels == {"lighting", "hero"}


def test_it_rejects_label_carrier_on_stash_target(tmp_path, monkeypatch, capsys):
    # The label→stash guard now triggers on the incoming carrier (the only remaining label surface on
    # `actor add` after --label moved to the generators).
    _mkproject(tmp_path, monkeypatch, [_light("Seed_1")])
    assert _run(["stash", "capture", "Seed_1", "--id", "box"]) == 0
    capsys.readouterr()
    carried = ("Begin Actor Class=Engine.Light Name=Src\n"
               "    // uedcli-labels: lit\n"
               "    Name=\"Src\"\nEnd Actor\n")
    assert _run(["actor", "add", "-", "--tree", "stash/box"], stdin=carried) == 2
    assert "labels apply only to a level" in capsys.readouterr().err
