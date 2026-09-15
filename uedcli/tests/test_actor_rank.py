"""`actor rank <names…|-> [--json]` — an actor's 1-based position in `level.order` (CSG evaluation
order), printed `Name<TAB>RANK` in ARGUMENT order (matching `label get`/`folder get`, not `bbox`'s
single-aggregate shape). Board item
`expose-order-value-as-a-human-readable-csg-rank`."""
import argparse
import io
import json

import pytest

from uedcli import stash_register, trunk
from uedcli.cli import dispatch
from uedcli.model import Actor, Level
from uedcli.normalize import canonical_actor_t3d


def _lexo(i: int) -> str:
    return chr(ord("m") + i)


def _project(tmp_path, monkeypatch, actors, name="lvl"):
    proj = tmp_path / "repo"
    (proj / "maps" / name).mkdir(parents=True)
    (proj / "uedcli.toml").write_text('game = "deusex"\n')
    lvl = Level(actors={a.name: a for a in actors})
    trunk.write_level(proj / "maps" / name, lvl,
                      {a.name: _lexo(i) for i, a in enumerate(actors)})
    monkeypatch.setenv("UEDCLI_LEVEL", name)
    return proj


def _ns(proj, names, **kw):
    base = dict(cmd="actor", sub="rank", project=str(proj), tree=None, names=names, json=False)
    base.update(kw)
    return argparse.Namespace(**base)


def _points(*locs):
    return [Actor(name=f"P{i}", cls="Light", location=loc) for i, loc in enumerate(locs)]


# ── default text output, argument order (not CSG order) ────────────────────────────────────────

def test_rank_prints_name_tab_rank_in_argument_order(tmp_path, monkeypatch, capsys):
    # CSG order (via hand-assigned order_values) is Wall, Room, Door -> ranks 1, 2, 3.
    wall = Actor(name="Wall", cls="Light", location=(0, 0, 0))
    room = Actor(name="Room", cls="Light", location=(0, 0, 0))
    door = Actor(name="Door", cls="Light", location=(0, 0, 0))
    proj = _project(tmp_path, monkeypatch, [wall, room, door])
    rc = dispatch.dispatch(_ns(proj, ["Door", "Wall"]))       # requested out of CSG order
    assert rc == 0
    cap = capsys.readouterr()
    assert cap.out.splitlines() == ["Door\t3", "Wall\t1"]     # printed in ARGUMENT order
    assert "rank of 2 actor(s) (3 total)" in cap.err          # human summary -> stderr


def test_rank_json(tmp_path, monkeypatch, capsys):
    wall = Actor(name="Wall", cls="Light", location=(0, 0, 0))
    room = Actor(name="Room", cls="Light", location=(0, 0, 0))
    door = Actor(name="Door", cls="Light", location=(0, 0, 0))
    proj = _project(tmp_path, monkeypatch, [wall, room, door])
    rc = dispatch.dispatch(_ns(proj, ["Door", "Wall"], json=True))
    assert rc == 0
    doc = json.loads(capsys.readouterr().out)
    assert doc == {"Door": 3, "Wall": 1}


# ── errors: unknown name is all-or-nothing ──────────────────────────────────────────────────────

def test_rank_unknown_name_exits_2(tmp_path, monkeypatch, capsys):
    proj = _project(tmp_path, monkeypatch, _points((0, 0, 0)))
    rc = dispatch.dispatch(_ns(proj, ["P0", "Nope"]))
    assert rc == 2
    cap = capsys.readouterr()
    assert "Actors not found:" in cap.err and "Nope" in cap.err
    assert cap.out == ""                                      # all-or-nothing: no partial stdout


# ── stdin / dedup ────────────────────────────────────────────────────────────────────────────

def test_rank_empty_stdin_is_a_noop(tmp_path, monkeypatch, capsys):
    proj = _project(tmp_path, monkeypatch, _points((0, 0, 0)))
    monkeypatch.setattr("sys.stdin", io.StringIO(""))
    rc = dispatch.dispatch(_ns(proj, ["-"]))
    assert rc == 0
    assert capsys.readouterr().out == ""


def test_rank_dedupes_repeated_names(tmp_path, monkeypatch, capsys):
    proj = _project(tmp_path, monkeypatch, _points((0, 0, 0), (1, 0, 0)))
    rc = dispatch.dispatch(_ns(proj, ["P0", "P0"]))
    assert rc == 0
    assert capsys.readouterr().out.splitlines() == ["P0\t1"]  # printed once


# ── --tree stash: rank is read off the named box, not the ambient level ────────────────────────

def test_rank_honours_tree_stash(tmp_path, monkeypatch, capsys):
    # Ambient trunk: P0 rank=1, P1 rank=2. A bug that ignores --tree would print "P1\t2" here.
    proj = _project(tmp_path, monkeypatch, _points((0, 0, 0), (1, 0, 0)))
    reg = stash_register.FileStashRegister(proj / ".uedcli" / "stash")
    p1 = Actor(name="P1", cls="Light", location=(5, 0, 0))
    other = Actor(name="Other", cls="Light", location=(0, 0, 0))
    # In the stash, P1 is FIRST (rank 1) -- the opposite of its ambient-trunk rank (2).
    reg.write_stash("bay", full_level={"P1": canonical_actor_t3d(p1),
                                       "Other": canonical_actor_t3d(other)},
                    order=["P1", "Other"], packages=[], meta={"anchor": ["0", "0", "0"], "ts": 1})
    rc = dispatch.dispatch(_ns(proj, ["P1"], tree="stash/bay"))
    assert rc == 0
    assert capsys.readouterr().out.strip() == "P1\t1"
