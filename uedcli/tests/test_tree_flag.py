"""`--tree KIND/NAME` generic content-verb targeting (level / stash / prefab).

Since 2026-07-20 the flag is `--tree` (the three boxes are one T3D-tree format) and the DEFAULT
source is the ambient `$UEDCLI_LEVEL` (not the old machine-local pointer). Covers: the
`_resolve_level_source` parse+routing front branch, the two `LevelSource` classes
(StashLevelSource/PrefabLevelSource) round-tripping, the [SR-#1] prefab meta-clobber regression,
[SR-#2] path-traversal refusal, [SR-#3] a stored order naming a missing blob, the not-found guards,
and the CLI flag scope (present on content verbs AND level materialize/preview level-only; absent on
generators / brush preview).
"""
import argparse
from decimal import Decimal

import pytest

from uedcli import builders, stash_register, stashlib, trunk
from uedcli.cli import errors, level_sources
from uedcli.cli import main as cli, dispatch
from uedcli.model import Actor, Level
from uedcli.normalize import canonical_actor_t3d


def _ns(**kw):
    kw.setdefault("tree", None)
    return argparse.Namespace(**kw)


def _project(tmp_path, monkeypatch, name="lvl", *, env=True):
    proj = tmp_path / "repo"
    (proj / "maps" / name).mkdir(parents=True)
    # `prefabs` points (absolute, honored verbatim) at the shared tmp Prefabs dir the prefab
    # tests seed — the uedcli.toml key replaced the retired UEDCLI_PREFAB_DIR env override.
    (proj / "uedcli.toml").write_text(
        f'game = "deusex"\nprefabs = "{tmp_path / "Prefabs"}"\n')
    lvl = Level(actors={"Lamp": Actor(name="Lamp", cls="Light", location=(0, 0, 0))})
    lvl.order = ["Lamp"]
    trunk.write_level(proj / "maps" / name, lvl, {"Lamp": "m"})
    if env:
        monkeypatch.setenv("UEDCLI_LEVEL", name)         # the ambient default level
    return proj, name


def _cube_t3d(name, *, texture="DeusExDeco.Stone.Block"):
    brush = builders.cube(64.0, 64.0, 64.0, texture)
    actor = builders.make_brush_actor(name, brush, location=(0.0, 0.0, 0.0))
    return canonical_actor_t3d(actor)


def _register(proj):
    return stash_register.FileStashRegister(proj / ".uedcli" / "stash")


def _seed_stash(proj, sid="bay"):
    reg = _register(proj)
    reg.write_stash(sid, full_level={"Box": _cube_t3d("Box")}, order=["Box"],
                    packages=["DeusExDeco"], meta={"anchor": ["0", "0", "0"], "ts": 1})
    return reg


def _seed_prefab(root, name="door"):
    stashlib.write_prefab(root, name, full_level={"Panel": _cube_t3d("Panel")},
                          order=["Panel"], packages=["DeusExDeco"], meta={"anchor": ["0", "0", "0"]})


# ── Parse / grammar ────────────────────────────────────────────────────────────────────────

@pytest.mark.parametrize("tree", ["level/other", "stash/bay", "prefab/door",
                                  "stash/hangar/archway"])
def test_valid_tree_parses_and_routes(tmp_path, monkeypatch, tree):
    proj, _ = _project(tmp_path, monkeypatch)
    (proj / "maps" / "other").mkdir(parents=True, exist_ok=True)
    trunk.write_level(proj / "maps" / "other",
                      Level(actors={"L": Actor(name="L", cls="Light")}, order=["L"]), {"L": "m"})
    _seed_stash(proj, "bay")
    reg = _register(proj)
    reg.write_stash("hangar/archway", full_level={"Box": _cube_t3d("Box")}, order=["Box"],
                    packages=["DeusExDeco"], meta={"anchor": ["0", "0", "0"]})
    _seed_prefab(tmp_path / "Prefabs", "door")

    src = level_sources.resolve_level_source(_ns(project=str(proj), tree=tree))
    kind = tree.split("/", 1)[0]
    expect = {"level": level_sources.TrunkLevelSource, "stash": level_sources.StashLevelSource,
              "prefab": level_sources.PrefabLevelSource}[kind]
    assert isinstance(src, expect)
    assert src.from_env is False                          # explicit --tree → silent (no echo)


def test_default_no_flag_is_the_env_level(tmp_path, monkeypatch):
    proj, name = _project(tmp_path, monkeypatch)
    src = level_sources.resolve_level_source(_ns(project=str(proj)))
    assert isinstance(src, level_sources.TrunkLevelSource)
    assert src.trunk_dir.name == name
    assert src.from_env is True                           # ambient → a mutation would announce it


def test_no_flag_and_no_env_is_a_clean_no_level(tmp_path, monkeypatch):
    proj, _ = _project(tmp_path, monkeypatch, env=False)  # nothing exported
    with pytest.raises(errors.LevelSelectionError, match="no level"):
        level_sources.resolve_level_source(_ns(project=str(proj)))


def test_malformed_no_slash_is_clean_exit(tmp_path, monkeypatch):
    proj, _ = _project(tmp_path, monkeypatch)
    with pytest.raises(dispatch.CommandError, match="KIND/NAME"):
        level_sources.resolve_level_source(_ns(project=str(proj), tree="bogus"))


def test_unknown_kind_is_clean_exit(tmp_path, monkeypatch):
    proj, _ = _project(tmp_path, monkeypatch)
    with pytest.raises(dispatch.CommandError, match="KIND/NAME"):
        level_sources.resolve_level_source(_ns(project=str(proj), tree="widget/foo"))


def test_empty_name_is_clean_exit(tmp_path, monkeypatch):
    proj, _ = _project(tmp_path, monkeypatch)
    with pytest.raises(dispatch.CommandError, match="KIND/NAME"):
        level_sources.resolve_level_source(_ns(project=str(proj), tree="stash/"))


# ── Not-found per kind ─────────────────────────────────────────────────────────────────────

def test_stash_not_found(tmp_path, monkeypatch):
    proj, _ = _project(tmp_path, monkeypatch)
    with pytest.raises(dispatch.CommandError, match="stash not found: 'nope'"):
        level_sources.resolve_level_source(_ns(project=str(proj), tree="stash/nope"))


def test_prefab_not_found(tmp_path, monkeypatch):
    proj, _ = _project(tmp_path, monkeypatch)
    with pytest.raises(dispatch.CommandError, match="prefab not found: 'nope'"):
        level_sources.resolve_level_source(_ns(project=str(proj), tree="prefab/nope"))


def test_level_not_found(tmp_path, monkeypatch):
    proj, _ = _project(tmp_path, monkeypatch)
    with pytest.raises(dispatch.CommandError, match="level not found: 'ghost'"):
        level_sources.resolve_level_source(_ns(project=str(proj), tree="level/ghost"))


def test_prefab_tree_works_with_no_env_level(tmp_path, monkeypatch):
    # A prefab edit must NOT require an ambient level (that's the whole point of the flag).
    proj, _ = _project(tmp_path, monkeypatch, env=False)
    _seed_prefab(tmp_path / "Prefabs", "door")
    src = level_sources.resolve_level_source(_ns(project=str(proj), tree="prefab/door"))
    assert isinstance(src, level_sources.PrefabLevelSource)


# ── [SR-#2] path traversal ─────────────────────────────────────────────────────────────────

@pytest.mark.parametrize("tree", ["stash/../../x", "level/../../x", "prefab/../x"])
def test_path_traversal_is_refused_before_any_source(tmp_path, monkeypatch, tree):
    proj, _ = _project(tmp_path, monkeypatch)
    escape = tmp_path / "x.t3d"
    escape.write_text("precious")
    with pytest.raises(dispatch.CommandError):
        level_sources.resolve_level_source(_ns(project=str(proj), tree=tree))
    assert escape.read_text() == "precious"    # nothing read/written outside the box root


# ── Round-trip each source ─────────────────────────────────────────────────────────────────

def test_stash_source_roundtrips_a_move(tmp_path, monkeypatch):
    proj, _ = _project(tmp_path, monkeypatch)
    _seed_stash(proj, "bay")
    src = level_sources.resolve_level_source(_ns(project=str(proj), tree="stash/bay"))
    level = src.load()
    assert level.order == ["Box"]
    level.actors["Box"].location = (Decimal(100), Decimal(0), Decimal(0))
    src.save(verb="move", args={}, level=level, touched=["Box"])
    blobs, order, pkgs, _meta, _folders = _register(proj).read_stash("bay")
    assert order == ["Box"]
    reread = level_sources.StashLevelSource(_register(proj), "bay").load()
    assert reread.actors["Box"].location == (Decimal(100), Decimal(0), Decimal(0))


def test_prefab_source_roundtrips_and_texture_edit_updates_packages(tmp_path, monkeypatch):
    proj, _ = _project(tmp_path, monkeypatch)
    _seed_prefab(tmp_path / "Prefabs", "door")
    src = level_sources.resolve_level_source(_ns(project=str(proj), tree="prefab/door"))
    level = src.load()
    for poly in level.actors["Panel"].brush.polys:
        poly.texture = "NewPkg.Wood"
    src.save(verb="poly-set", args={}, level=level, touched=["Panel"])
    _blobs, _order, packages, _meta, _folders = stashlib.read_prefab(tmp_path / "Prefabs", "door")
    assert packages == ["NewPkg"]               # save recomputed the texture-only dep set


# ── [SR-#1] prefab add-then-read (the meta-clobber regression) ─────────────────────────────

def test_prefab_add_then_read_keeps_the_added_actor(tmp_path, monkeypatch):
    # Before the read_prefab meta fix, the stale order/packages in `meta` clobbered the fresh ones
    # on re-save, dropping the just-added actor. This is the SR-#1 regression guard.
    proj, _ = _project(tmp_path, monkeypatch)
    _seed_prefab(tmp_path / "Prefabs", "door")

    args = _ns(cmd="actor", sub="add", file="-", tree="prefab/door", project=str(proj))
    monkeypatch.setattr("sys.stdin",
                        __import__("io").StringIO("Begin Map\n" + _cube_t3d("Extra") + "\nEnd Map\n"))
    assert dispatch.dispatch(args) == 0

    blobs, order, packages, _meta, _folders = stashlib.read_prefab(tmp_path / "Prefabs", "door")
    assert len(order) == 2 and "Panel" in order           # the original survives
    assert any(n != "Panel" for n in order)               # the added actor is present
    assert set(blobs) == set(order)                       # sidecar order matches the blobs (fresh)
    assert packages == ["DeusExDeco"]                     # fresh packages, not clobbered to stale


def test_prefab_delete_then_read_stays_gone(tmp_path, monkeypatch):
    proj, _ = _project(tmp_path, monkeypatch)
    # A two-actor prefab; delete one, confirm it does not resurrect on re-read.
    stashlib.write_prefab(tmp_path / "Prefabs", "door",
                          full_level={"Panel": _cube_t3d("Panel"), "Extra": _cube_t3d("Extra")},
                          order=["Panel", "Extra"], packages=["DeusExDeco"], meta={})
    args = _ns(cmd="actor", sub="delete", names=["Extra"], tree="prefab/door", project=str(proj))
    assert dispatch.dispatch(args) == 0
    _blobs, order, _pkgs, _meta, _folders = stashlib.read_prefab(tmp_path / "Prefabs", "door")
    assert order == ["Panel"] and "Extra" not in order


# ── [SR-#3] a stored order naming a missing blob → no KeyError ──────────────────────────────

def test_stash_order_with_missing_blob_loads_cleanly(tmp_path, monkeypatch):
    proj, _ = _project(tmp_path, monkeypatch)
    reg = _register(proj)
    # A stash whose order lists a name with no actor blob (a corrupt/partial write).
    reg.write_stash("bay", full_level={"Box": _cube_t3d("Box")}, order=["Box", "Ghost"],
                    packages=["DeusExDeco"], meta={"anchor": ["0", "0", "0"]})
    src = level_sources.StashLevelSource(reg, "bay")
    level = src.load()                                     # must not raise KeyError
    assert level.order == ["Box"]                          # missing name skipped


def test_prefab_partial_tree_loads_cleanly(tmp_path):
    # New-format analog of SR-#3: a torn/partial per-actor write (an actor dir with an EMPTY
    # actor.t3d, a crashed pre-atomic-write leftover) is skipped on read, so the prefab still loads
    # without a parse error.
    root = tmp_path / "Prefabs"
    stashlib.write_prefab(root, "door", full_level={"Panel": _cube_t3d("Panel")}, order=["Panel"],
                          packages=["DeusExDeco"], meta={"anchor": ["0", "0", "0"]})
    ghost = root / "door" / "actors" / "Ghost"
    ghost.mkdir()
    (ghost / "actor.t3d").write_text("")                   # torn write
    (ghost / "order_value").write_text("zzz\n")
    src = level_sources.PrefabLevelSource(root, "door")
    level = src.load()
    assert level.order == ["Panel"]                        # the torn actor is skipped


# ── End-to-end via a NAMED (non-ambient) level ─────────────────────────────────────────────

def test_tree_level_edits_a_non_ambient_level(tmp_path, monkeypatch):
    proj, _ = _project(tmp_path, monkeypatch, name="lvl")  # $UEDCLI_LEVEL='lvl'
    (proj / "maps" / "other").mkdir(parents=True)
    trunk.write_level(proj / "maps" / "other",
                      Level(actors={"Wall": Actor(name="Wall", cls="Light", location=(0, 0, 0))},
                            order=["Wall"]), {"Wall": "m"})
    args = _ns(cmd="actor", sub="move", name="Wall", to=(Decimal(5), Decimal(0), Decimal(0)),
               by=None, tree="level/other", project=str(proj))
    assert dispatch.dispatch(args) == 0
    got, _ = trunk.read_level(proj / "maps" / "other")
    assert got.actors["Wall"].location == (Decimal(5), Decimal(0), Decimal(0))
    # the ambient level is untouched
    sel, _ = trunk.read_level(proj / "maps" / "lvl")
    assert "Wall" not in sel.actors


# ── CLI flag scope ─────────────────────────────────────────────────────────────────────────

def _parses(argv):
    try:
        cli.build_parser().parse_args(argv)
        return True
    except SystemExit:
        return False


@pytest.mark.parametrize("argv", [
    ["actor", "move", "X", "--by", "0,0,1", "--tree", "stash/s"],
    ["actor", "delete", "X", "--tree", "prefab/door"],
    ["actor", "prop", "set", "X", "bStatic=True", "--tree", "level/other"],
    ["brush", "poly", "set", "W:all", "--texture", "P.Q", "--tree", "prefab/d"],
    ["mover", "key", "list", "M", "--tree", "prefab/d"],
    # Read verbs that would otherwise be stuck on the ambient level.
    ["actor", "show", "X", "--tree", "stash/s"],
    ["level", "status", "--tree", "level/other"],
    ["level", "doctor", "--tree", "prefab/d"],
    ["event", "graph", "--tree", "stash/s"],
    ["stash", "capture", "--tree", "level/other"],
    # Level build/preview NOW take --tree (level-only; dispatch rejects other kinds) — 2026-07-20.
    ["level", "materialize", "--out", "/tmp/x.dx", "--tree", "level/other"],
    ["level", "preview", "--out-dir", "/tmp/o", "at:0,0,0;rot:0,0", "--tree", "level/other"],
])
def test_tree_flag_present_on_content_and_build_verbs(argv):
    assert _parses(argv)


@pytest.mark.parametrize("argv", [
    # Generators read no box (the race is on the downstream `actor add`); build ops target nothing.
    ["brush", "build", "cube", "--width", "1", "--breadth", "1", "--height", "1",
     "--tree", "stash/s"],
    ["actor", "build", "Engine.Light", "--at", "0,0,0", "--tree", "stash/s"],
    ["actor", "preview", "X", "--tree", "stash/s"],   # a per-kind stash|prefab preview exists
    # `brush clip` is a stateless T3D filter (it reads a piped set, targets no box).
    ["brush", "clip", "-", "--axis", "x", "--offset", "0", "--tree", "stash/s"],
])
def test_tree_flag_absent_on_excluded_verbs(argv):
    assert not _parses(argv)


def test_materialize_preview_reject_non_level_tree(tmp_path, monkeypatch, capsys):
    # materialize/preview accept `--tree level/…` only; a stash/prefab has no world to build/walk.
    proj, _ = _project(tmp_path, monkeypatch)
    _seed_stash(proj, "bay")
    assert dispatch.dispatch(_ns(cmd="level", sub="materialize", project=str(proj),
                                 tree="stash/bay", out="/tmp/x.dx", overwrite=False,
                                 no_verify=False, keep_build=False)) == 2
    assert "operates on a level" in capsys.readouterr().err


# ── Behaviour: read verbs honour --tree; capture names the source ──────────────────────────

def _named_level(proj, name, actor="L"):
    (proj / "maps" / name).mkdir(parents=True, exist_ok=True)
    trunk.write_level(proj / "maps" / name,
                      Level(actors={actor: Actor(name=actor, cls="Light")}, order=[actor]),
                      {actor: "m"})


def test_level_status_tree_reads_the_named_level_not_the_ambient(tmp_path, monkeypatch, capsys):
    proj, _ = _project(tmp_path, monkeypatch)     # ambient level 'lvl' (actor "Lamp")
    _named_level(proj, "other")                   # a DIFFERENT level (actor "L")
    assert dispatch.dispatch(_ns(cmd="level", sub="status", project=str(proj),
                                 tree="level/other")) == 0
    out = capsys.readouterr().out
    assert "level: other" in out and "actors: 1  (0 brush, 1 point)" in out


def test_level_status_tree_stash_labels_kind(tmp_path, monkeypatch, capsys):
    proj, _ = _project(tmp_path, monkeypatch)
    _seed_stash(proj, "bay")                      # 1 brush "Box"
    assert dispatch.dispatch(_ns(cmd="level", sub="status", project=str(proj),
                                 tree="stash/bay")) == 0
    out = capsys.readouterr().out
    assert "stash: bay" in out and "actors: 1  (1 brush, 0 point)" in out
    assert "on branch" not in out                 # no git hint for a box source (level-trunk only)


def test_level_doctor_tree_stash_uses_display_name_not_trunk_dir(tmp_path, monkeypatch, capsys):
    proj, _ = _project(tmp_path, monkeypatch)
    _seed_stash(proj, "bay")
    # Before the display_name fix this AttributeError'd on src.trunk_dir for a stash source.
    assert dispatch.dispatch(_ns(cmd="level", sub="doctor", project=str(proj),
                                 tree="stash/bay", json=False, severity=None, category=None)) == 0
    assert "bay" in capsys.readouterr().out


def test_event_graph_tree_reads_the_box_not_the_ambient(tmp_path, monkeypatch, capsys):
    import json
    proj, _ = _project(tmp_path, monkeypatch)     # ambient 'lvl' = one Light → NO Event/Tag → empty graph
    trig = Actor(name="Trig", cls="Trigger", location=(0, 0, 0)); trig.props = [("Event", "boom")]
    door = Actor(name="Door", cls="Mover", location=(0, 0, 0)); door.props = [("Tag", "boom")]
    _register(proj).write_stash(
        "evt", full_level={"Trig": canonical_actor_t3d(trig), "Door": canonical_actor_t3d(door)},
        order=["Trig", "Door"], packages=[], meta={"anchor": ["0", "0", "0"], "ts": 1})
    assert dispatch.dispatch(_ns(cmd="event", sub="graph", project=str(proj),
                                 tree="stash/evt", json=True, dot=False)) == 0
    data = json.loads(capsys.readouterr().out)
    # the box's Trig --boom--> Door edge surfaces; the ambient level would have yielded zero — so a
    # non-empty graph proves --tree is honored, not silently ignored.
    assert len(data["edges"]) >= 1


def test_stash_capture_tree_names_the_source_level(tmp_path, monkeypatch):
    proj, _ = _project(tmp_path, monkeypatch)     # ambient 'lvl' (Lamp); --tree names a DIFFERENT source
    _named_level(proj, "other")
    assert dispatch.dispatch(_ns(cmd="stash", sub="capture", project=str(proj), tree="level/other",
                                 from_t3d=None, names=[], id="cap1", force=True)) == 0
    _blobs, order, *_ = _register(proj).read_stash("cap1")
    assert order == ["L"]                          # the SOURCE 'other', NOT the ambient 'lvl' (Lamp)


def test_stash_capture_tree_rejects_combining_with_from_source(tmp_path, monkeypatch):
    proj, _ = _project(tmp_path, monkeypatch)
    # --tree + --from-t3d is contradictory (two sources) → clean exit 2, never a silent ignore.
    assert dispatch.dispatch(_ns(cmd="stash", sub="capture", project=str(proj), tree="level/other",
                                 from_t3d=["x.t3d"], names=[], id=None, force=False)) == 2


# ── Review-gate hardening: corrupt box, emptied stash, traversal message, stash E2E ─────────

def test_corrupt_prefab_sidecar_is_clean_not_a_traceback(tmp_path, monkeypatch):
    # PrefabLevelSource.load calls read_prefab directly (bypassing _read_prefab_or_exit), so a
    # corrupt meta.json must be caught → clean exit 2, never a JSONDecodeError traceback.
    proj, _ = _project(tmp_path, monkeypatch)
    _seed_prefab(tmp_path / "Prefabs", "door")
    (tmp_path / "Prefabs" / "door" / "meta.json").write_text("{ not valid json")
    src = level_sources.resolve_level_source(_ns(project=str(proj), tree="prefab/door"))
    with pytest.raises(dispatch.CommandError, match="cannot read prefab 'door'"):
        src.load()


def test_corrupt_stash_meta_is_clean_not_a_traceback(tmp_path, monkeypatch):
    proj, _ = _project(tmp_path, monkeypatch)
    _seed_stash(proj, "bay")
    (proj / ".uedcli" / "stash" / "bay" / "meta.json").write_text("{ not valid json")
    src = level_sources.resolve_level_source(_ns(project=str(proj), tree="stash/bay"))
    with pytest.raises(dispatch.CommandError, match="cannot read stash 'bay'"):
        src.load()


def test_emptied_stash_stays_targetable(tmp_path, monkeypatch):
    # Deleting a stash's LAST actor via --tree leaves an empty-but-real stash. The existence
    # oracle keys on meta.json, so the stash is NOT falsely reported "not found" afterwards, and
    # you can add an actor back into it. (Content-emptiness could not tell empty from missing.)
    proj, _ = _project(tmp_path, monkeypatch)
    _seed_stash(proj, "bay")                                  # one actor: "Box"
    d = _ns(cmd="actor", sub="delete", names=["Box"], tree="stash/bay", project=str(proj))
    assert dispatch.dispatch(d) == 0
    assert _register(proj).exists("bay")                     # still a real stash, not a phantom
    # re-resolvable (no false "stash not found"), and an add lands back in it
    src = level_sources.resolve_level_source(_ns(project=str(proj), tree="stash/bay"))
    assert src.load().order == []                            # empty, but loads cleanly
    import io
    a = _ns(cmd="actor", sub="add", file="-", tree="stash/bay", project=str(proj))
    import sys as _sys; _sys.stdin = io.StringIO("Begin Map\n" + _cube_t3d("Refill") + "\nEnd Map\n")
    assert dispatch.dispatch(a) == 0
    blobs = _register(proj).read_stash("bay")[0]             # add mints a random-suffix name
    assert any(n.startswith("Refill") for n in blobs)       # the refill actor landed back in the stash


@pytest.mark.parametrize("tree", ["stash/../../x", "level/../../x", "prefab/../x"])
def test_path_traversal_message_and_exit2(tmp_path, monkeypatch, capsys, tree):
    # Stronger than the resolver-level check: route through dispatch.dispatch and assert a clean
    # exit 2 whose message names the invalid name (validate_member_name), not any other error.
    proj, _ = _project(tmp_path, monkeypatch)
    args = _ns(cmd="actor", sub="find", name=[], cls=[], group=[], prop=[], kind=None,
               tree=tree, project=str(proj))
    assert dispatch.dispatch(args) == 2
    assert "invalid name" in capsys.readouterr().err        # from validate_member_name, no traceback


def test_stash_edit_end_to_end_through_dispatch(tmp_path, monkeypatch):
    # Spec test-plan item: a stash E2E through the real dispatch (not just src.load/save), matching
    # the prefab/level E2Es. `actor move --tree stash/bay` must land on the on-disk stash.
    proj, _ = _project(tmp_path, monkeypatch)
    _seed_stash(proj, "bay")
    args = _ns(cmd="actor", sub="move", name="Box", to=(Decimal(5), Decimal(0), Decimal(0)),
               by=None, tree="stash/bay", project=str(proj))
    assert dispatch.dispatch(args) == 0
    reread = level_sources.StashLevelSource(_register(proj), "bay").load()
    assert reread.actors["Box"].location == (Decimal(5), Decimal(0), Decimal(0))
    # the ambient level is untouched (edit went to the stash, not the level)
    sel = level_sources.resolve_level_source(_ns(project=str(proj))).load()
    assert "Box" not in sel.actors
