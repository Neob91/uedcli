"""Actor folders — end-to-end (spec 2026-07-18-actor-folders-hierarchical.md §7).

Trunk sidecar round-trip (incl. atomic write), the delta-write diff BOTH directions (set + the
symmetric `"x"`→None unset trap), hash/materialize exclusion, the CLI verbs + guards, the
`// uedcli-folder:` carrier round-trip, and Group⊥folder independence.

CLI tests drive the real argparse parser through `dispatch()` so argparse defaults (and the
mutually-exclusive/`required` guards) are exercised; `_stub_author_validation` (autouse) no-ops the
class/texture ingest gate so `actor add` runs offline.
"""
import io
import os
from unittest import mock

import pytest

from uedcli import cli, dispatch, trunk
from uedcli.model import Actor, Level
from uedcli.normalize import canonical_actor_t3d, canonical_level_hash


# ── helpers ─────────────────────────────────────────────────────────────────────────

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


# ── trunk sidecar round-trip (§7 "Trunk round-trip") ────────────────────────────────

def test_folder_sidecar_roundtrips(tmp_path):
    lvl = Level(actors={"A_1": _light("A_1", folder="castle.tower.roof")},
                order=["A_1"])
    trunk.write_level(tmp_path, lvl, {"A_1": "m"})
    assert (tmp_path / "actors" / "A_1" / "folder").read_text() == "castle.tower.roof\n"
    got, _ = trunk.read_level(tmp_path)
    assert got.actors["A_1"].folder == "castle.tower.roof"


def test_absent_folder_file_reads_as_none(tmp_path):
    lvl = Level(actors={"A_1": _light("A_1")}, order=["A_1"])
    trunk.write_level(tmp_path, lvl, {"A_1": "m"})
    assert not (tmp_path / "actors" / "A_1" / "folder").exists()
    got, _ = trunk.read_level(tmp_path)
    assert got.actors["A_1"].folder is None


def test_write_removes_the_folder_file_when_unset(tmp_path):
    lvl = Level(actors={"A_1": _light("A_1", folder="a.b")}, order=["A_1"])
    trunk.write_level(tmp_path, lvl, {"A_1": "m"})
    assert (tmp_path / "actors" / "A_1" / "folder").exists()
    lvl.actors["A_1"].folder = None
    trunk.write_level(tmp_path, lvl, {"A_1": "m"})
    assert not (tmp_path / "actors" / "A_1" / "folder").exists()


def test_long_and_deep_folder_path_roundtrips(tmp_path):
    deep = ".".join(f"seg{i}" for i in range(40))
    lvl = Level(actors={"A_1": _light("A_1", folder=deep)}, order=["A_1"])
    trunk.write_level(tmp_path, lvl, {"A_1": "m"})
    got, _ = trunk.read_level(tmp_path)
    assert got.actors["A_1"].folder == deep


def test_folder_written_atomically_via_os_replace(tmp_path):
    """The folder sidecar lands via tmp + os.replace (like actor.t3d), never a bare write_text of the
    final path — else a lock-free reader mid-write sees a truncated first line (§2 S3)."""
    lvl = Level(actors={"A_1": _light("A_1", folder="a.b")}, order=["A_1"])
    dests = []
    real_replace = os.replace

    def _spy(src, dst):
        dests.append(str(dst))
        return real_replace(src, dst)

    # The tree writer now lives in t3dtree (trunk.write_level re-exports it), so patch there.
    with mock.patch("uedcli.t3dtree.os.replace", _spy):
        trunk.write_level(tmp_path, lvl, {"A_1": "m"})
    assert str(tmp_path / "actors" / "A_1" / "folder") in dests


# ── delta-write, BOTH directions (§7 "Delta-write") ─────────────────────────────────

def test_folder_only_change_persists_via_delta_write(tmp_path):
    """A body-identical, folder-CHANGED actor IS in the written set (the §2 diff trap)."""
    lvl = Level(actors={"A_1": _light("A_1")}, order=["A_1"])
    trunk.write_level(tmp_path, lvl, {"A_1": "m"})
    src = dispatch.TrunkLevelSource(tmp_path)
    loaded = src.load()
    loaded.actors["A_1"].folder = "act2.wip"              # ONLY the folder changes (body+rank same)
    src.save(verb="folder", args={}, level=loaded, touched=["A_1"])
    got, _ = trunk.read_level(tmp_path)
    assert got.actors["A_1"].folder == "act2.wip"


def test_folder_unset_persists_via_delta_write(tmp_path):
    """The SYMMETRIC trap: `"x"`→None on an otherwise byte-identical actor also fires the delta."""
    lvl = Level(actors={"A_1": _light("A_1", folder="x")}, order=["A_1"])
    trunk.write_level(tmp_path, lvl, {"A_1": "m"})
    src = dispatch.TrunkLevelSource(tmp_path)
    loaded = src.load()
    assert loaded.actors["A_1"].folder == "x"
    loaded.actors["A_1"].folder = None                   # unset — body+rank unchanged
    src.save(verb="folder", args={}, level=loaded, touched=["A_1"])
    got, _ = trunk.read_level(tmp_path)
    assert got.actors["A_1"].folder is None
    assert not (tmp_path / "actors" / "A_1" / "folder").exists()


def test_folder_only_save_leaves_a_disjoint_actor_untouched(tmp_path):
    """A folder-only save of A_1 must not rewrite an untouched B_2 (compose-with-concurrent-writer
    invariant): B_2's actor.t3d mtime/inode is stable."""
    lvl = Level(actors={"A_1": _light("A_1"), "B_2": _light("B_2")}, order=["A_1", "B_2"])
    trunk.write_level(tmp_path, lvl, {"A_1": "m", "B_2": "t"})
    body_b = tmp_path / "actors" / "B_2" / "actor.t3d"
    before = os.stat(body_b)
    src = dispatch.TrunkLevelSource(tmp_path)
    loaded = src.load()
    loaded.actors["A_1"].folder = "z"
    src.save(verb="folder", args={}, level=loaded, touched=["A_1"])
    after = os.stat(body_b)
    assert (before.st_mtime_ns, before.st_ino) == (after.st_mtime_ns, after.st_ino)


# ── hash / materialize exclusion (§7 "Materialize") ─────────────────────────────────

def test_folder_excluded_from_canonical_level_hash():
    a = Level(actors={"A": _light("A", folder="castle.tower")}, order=["A"])
    b = Level(actors={"A": _light("A")}, order=["A"])     # identical but for the folder
    assert canonical_level_hash(a) == canonical_level_hash(b)


def test_folder_never_appears_in_emitted_t3d():
    a = _light("A", folder="castleXYZ.towerXYZ")
    t = canonical_actor_t3d(a)
    assert "castleXYZ" not in t and "uedcli-folder" not in t


# ── CLI: actor folder set/unset/get ─────────────────────────────────────────────────

def test_folder_set_get_unset_via_cli(tmp_path, monkeypatch, capsys):
    root = _mkproject(tmp_path, monkeypatch, [_light("A_1"), _light("B_2")])
    assert _run(["actor", "folder", "set", "--to", "castle.tower", "A_1"]) == 0
    assert _read(root).actors["A_1"].folder == "castle.tower"

    capsys.readouterr()
    assert _run(["actor", "folder", "get", "A_1", "B_2"]) == 0
    assert capsys.readouterr().out.splitlines() == ["castle.tower", "(none)"]

    assert _run(["actor", "folder", "unset", "A_1"]) == 0
    assert _read(root).actors["A_1"].folder is None


def test_folder_set_and_unset_echo_touched_names_to_stdout(tmp_path, monkeypatch, capsys):
    """`set`/`unset` are PRODUCERS — touched Names on stdout (so they chain into `| verb -`), the
    human count on stderr — exactly like the sibling `actor label` verbs. The two organizational
    dimensions must behave identically."""
    _mkproject(tmp_path, monkeypatch, [_light("A_1"), _light("B_2")])
    capsys.readouterr()
    assert _run(["actor", "folder", "set", "--to", "castle.tower", "A_1", "B_2"]) == 0
    cap = capsys.readouterr()
    assert cap.out.splitlines() == ["A_1", "B_2"]         # pipe-ready names, ONE PER LINE
    assert "2 actor(s)" in cap.err                        # count on stderr, never in the pipe

    assert _run(["actor", "folder", "unset", "A_1"]) == 0
    cap = capsys.readouterr()
    assert cap.out.splitlines() == ["A_1"]
    assert "1 actor(s)" in cap.err


def test_folder_get_is_not_touched_by_the_producer_change(tmp_path, monkeypatch, capsys):
    """`get` is a QUERY: it prints the folder values, never the names (the producer echo must not
    leak into it)."""
    _mkproject(tmp_path, monkeypatch, [_light("A_1", folder="a.b")])
    capsys.readouterr()
    assert _run(["actor", "folder", "get", "A_1"]) == 0
    assert capsys.readouterr().out.splitlines() == ["a.b"]


def test_folder_set_is_case_insensitive_on_names(tmp_path, monkeypatch):
    root = _mkproject(tmp_path, monkeypatch, [_light("Alpha_1")])
    assert _run(["actor", "folder", "set", "--to", "a.b", "alpha_1"]) == 0
    assert _read(root).actors["Alpha_1"].folder == "a.b"


def test_folder_set_reads_names_from_stdin(tmp_path, monkeypatch):
    root = _mkproject(tmp_path, monkeypatch, [_light("A_1"), _light("B_2")])
    assert _run(["actor", "folder", "set", "--to", "wip", "-"], stdin="A_1\nB_2\n") == 0
    lvl = _read(root)
    assert lvl.actors["A_1"].folder == "wip" and lvl.actors["B_2"].folder == "wip"


def test_folder_set_missing_actor_errors_exit2(tmp_path, monkeypatch, capsys):
    _mkproject(tmp_path, monkeypatch, [_light("A_1")])
    assert _run(["actor", "folder", "set", "--to", "a.b", "Nope"]) == 2
    assert "Nope" in capsys.readouterr().err


def test_folder_set_invalid_path_errors_exit2(tmp_path, monkeypatch, capsys):
    root = _mkproject(tmp_path, monkeypatch, [_light("A_1")])
    assert _run(["actor", "folder", "set", "--to", "a..b", "A_1"]) == 2
    assert "a..b" in capsys.readouterr().err
    assert _read(root).actors["A_1"].folder is None      # no write on a bad path


def test_folder_set_requires_to(tmp_path, monkeypatch):
    _mkproject(tmp_path, monkeypatch, [_light("A_1")])
    with pytest.raises(SystemExit):                       # argparse: --to is required
        cli.build_parser().parse_args(["actor", "folder", "set", "A_1"])


@pytest.mark.parametrize("sub,extra", [("set", ["--to", "a.b"]), ("unset", []), ("get", [])])
def test_folder_verbs_reject_stash_target(tmp_path, monkeypatch, capsys, sub, extra):
    _mkproject(tmp_path, monkeypatch, [_light("A_1")])
    rc = _run(["actor", "folder", sub, *extra, "--tree", "stash/foo", "A_1"])
    assert rc == 2
    assert "folders apply only to a level" in capsys.readouterr().err


# ── CLI: actor add --folder + the carrier ───────────────────────────────────────────

_LIGHT_T3D = ("Begin Actor Class=Engine.Light Name=Src\n"
              "    Name=\"Src\"\nEnd Actor\n")


def test_add_persists_incoming_folder_carrier(tmp_path, monkeypatch, capsys):
    # `actor add` is a pure carrier-consumer (no --folder as of 2026-07-24 17:04): the folder is
    # authored on the generator / carried by `actor show`, and `actor add` persists that carrier.
    root = _mkproject(tmp_path, monkeypatch, [_light("A_1", folder="castle.props")])
    assert _run(["actor", "show", "A_1"]) == 0
    shown = capsys.readouterr().out                      # carries `// uedcli-folder: castle.props`
    assert _run(["actor", "add", "-"], stdin=shown) == 0
    added = capsys.readouterr().out.split()
    assert _read(root).actors[added[0]].folder == "castle.props"


def test_actor_add_has_no_folder_flag(tmp_path, monkeypatch, capsys):
    # The --folder flag was removed from `actor add` (moved to the generators); argparse rejects it.
    root = _mkproject(tmp_path, monkeypatch, [_light("Seed_1")])
    with pytest.raises(SystemExit) as e:
        _run(["actor", "add", "-", "--folder", "castle.props"], stdin=_LIGHT_T3D)
    assert e.value.code == 2
    assert set(_read(root).actors) == {"Seed_1"}         # nothing added


def test_add_carrier_into_stash_target_is_rejected(tmp_path, monkeypatch, capsys):
    """A `// uedcli-folder:` carrier is a folder surface too — adding it into a stash box (which has
    no sidecar slot, so save would DROP it silently) is rejected, not silently dropped."""
    _mkproject(tmp_path, monkeypatch, [_light("Seed_1")])
    assert _run(["stash", "capture", "Seed_1", "--id", "box"]) == 0
    capsys.readouterr()
    carried = ("Begin Actor Class=Engine.Light Name=Src\n"
               "    // uedcli-folder: castle.props\n"
               "    Name=\"Src\"\nEnd Actor\n")
    assert _run(["actor", "add", "-", "--tree", "stash/box"], stdin=carried) == 2
    assert "folders apply only to a level" in capsys.readouterr().err


def test_show_emits_the_folder_carrier_by_default(tmp_path, monkeypatch, capsys):
    root = _mkproject(tmp_path, monkeypatch, [_light("A_1", folder="castle.tower")])
    name = list(_read(root).actors)[0]
    assert _run(["actor", "show", name]) == 0
    assert "// uedcli-folder: castle.tower" in capsys.readouterr().out


def test_show_t3d_only_suppresses_the_carrier(tmp_path, monkeypatch, capsys):
    root = _mkproject(tmp_path, monkeypatch, [_light("A_1", folder="castle.tower")])
    name = list(_read(root).actors)[0]
    assert _run(["actor", "show", name, "--t3d-only"]) == 0
    assert "uedcli-folder" not in capsys.readouterr().out


def test_show_add_carrier_roundtrips_the_folder(tmp_path, monkeypatch, capsys):
    """`actor show A | actor add -` reproduces A's folder (the carrier → sidecar round-trip)."""
    root = _mkproject(tmp_path, monkeypatch, [_light("A_1", folder="castle.tower.roof")])
    assert _run(["actor", "show", "A_1"]) == 0
    shown = capsys.readouterr().out
    assert _run(["actor", "add", "-"], stdin=shown) == 0
    added = capsys.readouterr().out.split()
    assert _read(root).actors[added[0]].folder == "castle.tower.roof"


def test_add_folder_carrier_wins_no_override(tmp_path, monkeypatch, capsys):
    # With --folder removed from `actor add`, the incoming `// uedcli-folder:` carrier always wins
    # (there is no override channel); post-hoc change is `actor folder set`.
    root = _mkproject(tmp_path, monkeypatch, [_light("A_1", folder="from.carrier")])
    assert _run(["actor", "show", "A_1"]) == 0
    shown = capsys.readouterr().out
    assert _run(["actor", "add", "-"], stdin=shown) == 0
    added = capsys.readouterr().out.split()
    assert _read(root).actors[added[0]].folder == "from.carrier"


def test_noncarrier_double_slash_comment_is_ignored(tmp_path, monkeypatch, capsys):
    root = _mkproject(tmp_path, monkeypatch, [_light("Seed_1")])
    t3d = ("Begin Actor Class=Engine.Light Name=Src\n"
           "    // just a comment, not a folder\n"
           "    Name=\"Src\"\nEnd Actor\n")
    assert _run(["actor", "add", "-"], stdin=t3d) == 0
    added = capsys.readouterr().out.split()
    assert _read(root).actors[added[0]].folder is None


# ── CLI: actor find --folder / --no-folder ──────────────────────────────────────────

def _find_project(tmp_path, monkeypatch):
    return _mkproject(tmp_path, monkeypatch, [
        _light("Roof_1", folder="castle.tower.roof"),
        _light("Tower_2", folder="castle.tower"),
        _light("Moat_3", folder="castle.moat"),
        _light("Free_4"),                                # unfoldered
    ])


def test_find_folder_subtree(tmp_path, monkeypatch, capsys):
    _find_project(tmp_path, monkeypatch)
    assert _run(["actor", "find", "--folder", "castle.tower"]) == 0
    assert set(capsys.readouterr().out.split()) == {"Roof_1", "Tower_2"}


def test_find_folder_single_segment_glob(tmp_path, monkeypatch, capsys):
    _find_project(tmp_path, monkeypatch)
    assert _run(["actor", "find", "--folder", "castle.*"]) == 0
    assert set(capsys.readouterr().out.split()) == {"Tower_2", "Moat_3"}   # NOT Roof_1 (depth 3)


def test_find_folder_globstar_any_depth(tmp_path, monkeypatch, capsys):
    _find_project(tmp_path, monkeypatch)
    assert _run(["actor", "find", "--folder", "**.roof"]) == 0
    assert set(capsys.readouterr().out.split()) == {"Roof_1"}


def test_find_folder_repeated_flag_ors(tmp_path, monkeypatch, capsys):
    _find_project(tmp_path, monkeypatch)
    assert _run(["actor", "find", "--folder", "**.roof", "--folder", "castle.moat"]) == 0
    assert set(capsys.readouterr().out.split()) == {"Roof_1", "Moat_3"}


def test_find_no_folder_selects_ungrouped(tmp_path, monkeypatch, capsys):
    _find_project(tmp_path, monkeypatch)
    assert _run(["actor", "find", "--no-folder"]) == 0
    assert capsys.readouterr().out.split() == ["Free_4"]


def test_find_folder_bad_pattern_errors_exit2(tmp_path, monkeypatch, capsys):
    _find_project(tmp_path, monkeypatch)
    assert _run(["actor", "find", "--folder", "roof?"]) == 2
    assert "roof?" in capsys.readouterr().err


def test_find_folder_and_no_folder_mutually_exclusive(tmp_path, monkeypatch):
    _mkproject(tmp_path, monkeypatch, [_light("A_1")])
    with pytest.raises(SystemExit):
        cli.build_parser().parse_args(["actor", "find", "--folder", "a", "--no-folder"])


def test_find_folder_rejects_stash_target(tmp_path, monkeypatch, capsys):
    _mkproject(tmp_path, monkeypatch, [_light("A_1")])
    assert _run(["actor", "find", "--folder", "a", "--tree", "stash/x"]) == 2
    assert "folders apply only to a level" in capsys.readouterr().err


# ── stash apply: --folder + --group are independent placement dimensions (§6, §7 "Apply") ──

def _capture(root, name, stash_id):
    """Capture a single trunk actor into a stash entry via the CLI."""
    return _run(["stash", "capture", name, "--id", stash_id])


def test_apply_folder_and_group_independent(tmp_path, monkeypatch, capsys):
    root = _mkproject(tmp_path, monkeypatch, [_light("A_1")])
    assert _capture(root, "A_1", "box") == 0
    capsys.readouterr()
    assert _run(["stash", "apply", "box", "--folder", "placed.here", "--group", "MyGroup",
                 "--at", "500,0,0"]) == 0
    placed = [a for n, a in _read(root).actors.items() if n != "A_1"]
    assert len(placed) == 1
    assert placed[0].folder == "placed.here"                 # sidecar stamped
    assert ("Group", "MyGroup") in placed[0].props           # T3D Group prop stamped (independent)


def test_apply_without_folder_is_unfoldered(tmp_path, monkeypatch, capsys):
    root = _mkproject(tmp_path, monkeypatch, [_light("A_1")])
    assert _capture(root, "A_1", "box") == 0
    capsys.readouterr()
    assert _run(["stash", "apply", "box", "--at", "500,0,0"]) == 0
    placed = [a for n, a in _read(root).actors.items() if n != "A_1"]
    assert len(placed) == 1
    assert placed[0].folder is None                          # no default — unfoldered
    assert any(k == "Group" for k, _ in placed[0].props)     # --group keeps its id/basename default


def test_apply_bad_folder_path_errors_exit2(tmp_path, monkeypatch, capsys):
    root = _mkproject(tmp_path, monkeypatch, [_light("A_1")])
    assert _capture(root, "A_1", "box") == 0
    capsys.readouterr()
    assert _run(["stash", "apply", "box", "--folder", "a..b", "--at", "500,0,0"]) == 2
    assert "a..b" in capsys.readouterr().err
    assert set(_read(root).actors) == {"A_1"}                # nothing placed


# ── Group ⊥ folder independence (§7 "Independence") ─────────────────────────────────

def test_folder_and_group_are_independent(tmp_path, monkeypatch):
    root = _mkproject(tmp_path, monkeypatch,
                      [_light("A_1", props=[("Group", "wip")], folder="castle.x")])
    lvl = _read(root)
    assert lvl.actors["A_1"].folder == "castle.x"
    assert ("Group", "wip") in lvl.actors["A_1"].props
    # setting the folder never touches Group
    assert _run(["actor", "folder", "set", "--to", "castle.y", "A_1"]) == 0
    lvl = _read(root)
    assert lvl.actors["A_1"].folder == "castle.y"
    assert ("Group", "wip") in lvl.actors["A_1"].props


def test_find_group_and_find_folder_are_separate_dimensions(tmp_path, monkeypatch, capsys):
    _mkproject(tmp_path, monkeypatch, [
        _light("A_1", props=[("Group", "wip")], folder="castle.a"),
        _light("B_2", props=[("Group", "wip")]),         # grouped wip, no folder
    ])
    assert _run(["actor", "find", "--group", "wip"]) == 0
    assert set(capsys.readouterr().out.split()) == {"A_1", "B_2"}
    assert _run(["actor", "find", "--folder", "castle"]) == 0
    assert capsys.readouterr().out.split() == ["A_1"]
