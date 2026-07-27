"""`actor order` + `actor add --order` — end-to-end (spec in board item `csg-order-control-actor-order-actor-add-order` §5/§7).

Drives the real argparse parser through `dispatch()` so the mutually-exclusive selector group, the
`--order` grammar, the pre-resolve trunk-only guards, and the named exit-2 guards are all exercised.
`_stub_author_validation` (conftest autouse) no-ops the class/texture ingest gate so `actor add`
runs offline.
"""
import io
from unittest import mock

from uedcli import cli, dispatch, trunk
from uedcli.model import Actor, Level
from uedcli.normalize import canonical_level_hash


def _mkproject(tmp_path, monkeypatch, names, ranks=None):
    root = tmp_path / "proj"
    (root / "maps" / "lvl").mkdir(parents=True)
    (root / "uedcli.toml").write_text('game = "deusex"\n')
    monkeypatch.setenv("UEDCLI_PROJECT", str(root))
    actors = [Actor(name=n, cls="Engine.Light", location=(0, 0, 0)) for n in names]
    lvl = Level(actors={a.name: a for a in actors}, order=list(names))
    ranks = ranks or dict(zip(names, trunk.initial_ranks(len(names))))
    trunk.write_level(root / "maps" / "lvl", lvl, ranks)
    monkeypatch.setenv("UEDCLI_LEVEL", "lvl")
    return root


def _run(argv, stdin=""):
    args = cli.build_parser().parse_args(argv)
    with mock.patch("sys.stdin", io.StringIO(stdin)):
        return dispatch.dispatch(args)


def _order(root):
    lvl, _ = trunk.read_level(root / "maps" / "lvl")
    return lvl.order


_LIGHT_T3D = ("Begin Actor Class=Engine.Light Name=Src\n"
              "    Name=\"Src\"\nEnd Actor\n")


# ── actor order: each selector lands the right sort position ─────────────────────────

def test_order_first_moves_to_lowest(tmp_path, monkeypatch):
    root = _mkproject(tmp_path, monkeypatch, ["A_1", "B_2", "C_3"])
    assert _run(["actor", "order", "C_3", "--first"]) == 0
    assert _order(root) == ["C_3", "A_1", "B_2"]


def test_order_last_moves_to_highest(tmp_path, monkeypatch):
    root = _mkproject(tmp_path, monkeypatch, ["A_1", "B_2", "C_3"])
    assert _run(["actor", "order", "A_1", "--last"]) == 0
    assert _order(root) == ["B_2", "C_3", "A_1"]


def test_order_before_name(tmp_path, monkeypatch):
    root = _mkproject(tmp_path, monkeypatch, ["A_1", "B_2", "C_3"])
    assert _run(["actor", "order", "C_3", "--before", "B_2"]) == 0
    assert _order(root) == ["A_1", "C_3", "B_2"]


def test_order_after_name(tmp_path, monkeypatch):
    root = _mkproject(tmp_path, monkeypatch, ["A_1", "B_2", "C_3"])
    assert _run(["actor", "order", "A_1", "--after", "B_2"]) == 0
    assert _order(root) == ["B_2", "A_1", "C_3"]


def test_order_is_case_insensitive(tmp_path, monkeypatch):
    root = _mkproject(tmp_path, monkeypatch, ["A_1", "B_2", "C_3"])
    assert _run(["actor", "order", "c_3", "--before", "b_2"]) == 0
    assert _order(root) == ["A_1", "C_3", "B_2"]


# ── multi-actor block move (incl. non-contiguous) ───────────────────────────────────

def test_multi_block_move_preserves_relative_order_noncontiguous(tmp_path, monkeypatch):
    root = _mkproject(tmp_path, monkeypatch, ["A_1", "B_2", "C_3", "D_4", "E_5"])
    # move the NON-contiguous set {A,C,E}, passed shuffled — they keep A<C<E ahead of B,D.
    assert _run(["actor", "order", "E_5", "A_1", "C_3", "--first"]) == 0
    assert _order(root) == ["A_1", "C_3", "E_5", "B_2", "D_4"]


def test_block_move_before_name(tmp_path, monkeypatch):
    root = _mkproject(tmp_path, monkeypatch, ["A_1", "B_2", "C_3", "D_4"])
    assert _run(["actor", "order", "C_3", "D_4", "--before", "B_2"]) == 0
    assert _order(root) == ["A_1", "C_3", "D_4", "B_2"]


# ── `-` reads names from stdin ──────────────────────────────────────────────────────

def test_order_names_from_stdin(tmp_path, monkeypatch):
    root = _mkproject(tmp_path, monkeypatch, ["A_1", "B_2", "C_3"])
    assert _run(["actor", "order", "-", "--first"], stdin="C_3\n") == 0
    assert _order(root) == ["C_3", "A_1", "B_2"]


def test_order_empty_stdin_is_noop(tmp_path, monkeypatch):
    root = _mkproject(tmp_path, monkeypatch, ["A_1", "B_2"])
    assert _run(["actor", "order", "-", "--first"], stdin="") == 0
    assert _order(root) == ["A_1", "B_2"]                 # untouched


# ── the save(ranks=) seam: a reorder-only change persists AND changes the hash ──────

def test_reorder_persists_and_changes_canonical_hash(tmp_path, monkeypatch):
    root = _mkproject(tmp_path, monkeypatch, ["A_1", "B_2", "C_3"])
    before, _ = trunk.read_level(root / "maps" / "lvl")
    before_hash = canonical_level_hash(before)
    assert _run(["actor", "order", "C_3", "--first"]) == 0
    after, _ = trunk.read_level(root / "maps" / "lvl")
    assert after.order == ["C_3", "A_1", "B_2"]           # the override reached disk (seam works)
    assert canonical_level_hash(after) != before_hash     # a reorder is a real CSG state change


# ── guards (each a named exit-2, trunk untouched) ───────────────────────────────────

def test_order_unknown_moved_actor_exit2(tmp_path, monkeypatch, capsys):
    root = _mkproject(tmp_path, monkeypatch, ["A_1", "B_2"])
    assert _run(["actor", "order", "Nope_9", "--first"]) == 2
    assert "Nope_9" in capsys.readouterr().err
    assert _order(root) == ["A_1", "B_2"]


def test_order_missing_before_name_exit2(tmp_path, monkeypatch, capsys):
    root = _mkproject(tmp_path, monkeypatch, ["A_1", "B_2"])
    assert _run(["actor", "order", "A_1", "--before", "Ghost_9"]) == 2
    assert "Ghost_9" in capsys.readouterr().err
    assert _order(root) == ["A_1", "B_2"]


def test_order_self_reference_exit2(tmp_path, monkeypatch, capsys):
    root = _mkproject(tmp_path, monkeypatch, ["A_1", "B_2"])
    assert _run(["actor", "order", "A_1", "--before", "A_1"]) == 2
    assert "moved set" in capsys.readouterr().err
    assert _order(root) == ["A_1", "B_2"]


def test_order_rejects_stash_target(tmp_path, monkeypatch, capsys):
    root = _mkproject(tmp_path, monkeypatch, ["A_1", "B_2"])
    assert _run(["actor", "order", "A_1", "--first", "--tree", "stash/x"]) == 2
    assert "applies only to a level" in capsys.readouterr().err
    assert _order(root) == ["A_1", "B_2"]


def test_order_adjacent_imported_ranks_exit2(tmp_path, monkeypatch, capsys):
    # A ("a") and B ("a0") are lexicographically adjacent — no order_value fits between them.
    root = _mkproject(tmp_path, monkeypatch, ["A_1", "B_2", "C_3"],
                      ranks={"A_1": "a", "B_2": "a0", "C_3": "b"})
    assert _run(["actor", "order", "C_3", "--before", "B_2"]) == 2
    assert "cannot reorder" in capsys.readouterr().err
    assert _order(root) == ["A_1", "B_2", "C_3"]          # untouched


def test_order_first_against_smallest_digit_min_exit2(tmp_path, monkeypatch, capsys):
    # rank_between(None, '0') has no answer — the current min is the smallest digit.
    root = _mkproject(tmp_path, monkeypatch, ["A_1", "B_2"], ranks={"A_1": "0", "B_2": "m"})
    assert _run(["actor", "order", "B_2", "--first"]) == 2
    assert "cannot reorder" in capsys.readouterr().err
    assert _order(root) == ["A_1", "B_2"]


# ── actor add --order ───────────────────────────────────────────────────────────────

def test_add_order_first_places_new_lowest(tmp_path, monkeypatch, capsys):
    root = _mkproject(tmp_path, monkeypatch, ["A_1", "B_2"])
    assert _run(["actor", "add", "-", "--order", "first"], stdin=_LIGHT_T3D) == 0
    added = capsys.readouterr().out.split()
    assert len(added) == 1 and _order(root)[0] == added[0]


def test_add_default_still_appends(tmp_path, monkeypatch, capsys):
    root = _mkproject(tmp_path, monkeypatch, ["A_1", "B_2"])
    assert _run(["actor", "add", "-"], stdin=_LIGHT_T3D) == 0
    added = capsys.readouterr().out.split()
    assert _order(root)[-1] == added[0]                   # unchanged: default == last (append)


def test_add_order_before_name(tmp_path, monkeypatch, capsys):
    root = _mkproject(tmp_path, monkeypatch, ["A_1", "B_2"])
    assert _run(["actor", "add", "-", "--order", "before=B_2"], stdin=_LIGHT_T3D) == 0
    added = capsys.readouterr().out.split()
    assert _order(root) == ["A_1", added[0], "B_2"]


def test_add_order_selector_is_case_insensitive(tmp_path, monkeypatch, capsys):
    root = _mkproject(tmp_path, monkeypatch, ["A_1", "B_2"])
    assert _run(["actor", "add", "-", "--order", "FIRST"], stdin=_LIGHT_T3D) == 0
    added = capsys.readouterr().out.split()
    assert _order(root)[0] == added[0]                   # `FIRST` == `first`, not "malformed"


def test_add_order_uppercase_last_does_not_trip_the_trunk_only_guard(tmp_path, monkeypatch, capsys):
    # `LAST` is semantically the default append — it must NOT trip the ordering trunk-only guard on a
    # stash target (whatever else the stash add then does).
    _mkproject(tmp_path, monkeypatch, ["A_1"])
    _run(["actor", "add", "-", "--order", "LAST", "--tree", "stash/x"], stdin=_LIGHT_T3D)
    assert "ordering applies only to a level" not in capsys.readouterr().err


def test_add_order_rejects_stash_target(tmp_path, monkeypatch, capsys):
    _mkproject(tmp_path, monkeypatch, ["A_1"])
    assert _run(["actor", "add", "-", "--order", "first", "--tree", "stash/x"],
                stdin=_LIGHT_T3D) == 2
    assert "applies only to a level" in capsys.readouterr().err


def test_add_order_bad_value_exit2(tmp_path, monkeypatch, capsys):
    root = _mkproject(tmp_path, monkeypatch, ["A_1"])
    assert _run(["actor", "add", "-", "--order", "sideways"], stdin=_LIGHT_T3D) == 2
    assert "first|last|before=NAME|after=NAME" in capsys.readouterr().err
    assert set(_order(root)) == {"A_1"}                   # nothing added


def test_add_order_before_missing_name_exit2(tmp_path, monkeypatch, capsys):
    root = _mkproject(tmp_path, monkeypatch, ["A_1"])
    assert _run(["actor", "add", "-", "--order", "before=Ghost_9"], stdin=_LIGHT_T3D) == 2
    assert "Ghost_9" in capsys.readouterr().err
    assert set(_order(root)) == {"A_1"}                   # nothing added
