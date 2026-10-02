"""Slice 1 source characterization: the gaps the existing source tests leave open.

Already pinned elsewhere: interleaved writers, rank override, unchanged-file, folder-only and
label-only trunk deltas (`test_level_source.py`, `test_folders.py`, `test_labels_delta_write.py`),
and stash/prefab round-tripping (`test_tree_flag.py`). This file adds only what those miss:

- the trunk save takes `LOCK_EX` BEFORE the write and holds it DURING the write;
- a stash/prefab edit-save preserves the capture `meta` anchor and each member's folder;
- a stash/prefab round trip neither persists nor restores actor labels (the trunk-only label
  scope is not widened to the box wrappers).
"""
from __future__ import annotations

import pytest

from uedcli import stash_register, stashlib, trunk
from uedcli.cli import level_sources
from uedcli.model import Actor, Level


def _light(name, **kw):
    return Actor(name=name, cls="Engine.Light", location=(0, 0, 0), **kw)


# --- trunk save locking order ------------------------------------------------------------------

def test_trunk_save_takes_lock_ex_before_and_holds_it_during_write(tmp_path, monkeypatch):
    """`TrunkLevelSource.save` acquires `flock(LOCK_EX)` and only then calls `trunk.write_level`,
    inside the still-open lock fd. Record both calls: the write must see the lock already held
    (last event `LOCK_EX`, no intervening unlock) and run after it."""
    trunk.write_level(tmp_path, Level(actors={"A_1": _light("A_1")}, order=["A_1"]), {"A_1": "m"})
    src = level_sources.TrunkLevelSource(tmp_path)
    lv = src.load()
    lv.actors["B_2"] = _light("B_2")
    lv.order = ["A_1", "B_2"]

    events = []
    real_flock = level_sources.fcntl.flock

    def rec_flock(fd, op):
        events.append(("flock", op))
        return real_flock(fd, op)

    def rec_write(*a, **k):
        # Called from inside the `with open(lock) … flock(LOCK_EX)` block → the lock is held now.
        assert events and events[-1] == ("flock", level_sources.fcntl.LOCK_EX)
        events.append(("write",))

    monkeypatch.setattr(level_sources.fcntl, "flock", rec_flock)
    monkeypatch.setattr(level_sources.trunk, "write_level", rec_write)
    src.save(verb="add", args={}, level=lv, touched=["B_2"])

    assert events == [("flock", level_sources.fcntl.LOCK_EX), ("write",)]


# --- stash / prefab: meta + folder preserved through an edit -----------------------------------

def _cube_body(name):
    from uedcli import builders
    from uedcli.normalize import canonical_actor_t3d
    brush = builders.cube(64.0, 64.0, 64.0, "DeusExDeco.Stone.Block")
    return canonical_actor_t3d(builders.make_brush_actor(name, brush, location=(0.0, 0.0, 0.0)))


def test_stash_source_preserves_meta_anchor_and_member_folder_through_an_edit(tmp_path):
    reg = stash_register.FileStashRegister(tmp_path / "stash")
    reg.write_stash("bay", full_level={"Box": _cube_body("Box")}, order=["Box"],
                    packages=["DeusExDeco"], meta={"anchor": ["1", "2", "3"], "ts": 7},
                    folders={"Box": "props/crates"})

    src = level_sources.StashLevelSource(reg, "bay")
    level = src.load()
    assert level.actors["Box"].folder == "props/crates"        # folder restored on load
    level.actors["Box"].location = (100, 0, 0)                 # an unrelated edit
    src.save(verb="move", args={}, level=level, touched=["Box"])

    _blobs, _order, _pkgs, meta, folders = reg.read_stash("bay")
    assert meta == {"anchor": ["1", "2", "3"], "ts": 7}        # capture anchor preserved
    assert folders == {"Box": "props/crates"}                  # member folder preserved


def test_prefab_source_preserves_meta_anchor_and_member_folder_through_an_edit(tmp_path):
    root = tmp_path / "Prefabs"
    stashlib.write_prefab(root, "door", full_level={"Panel": _cube_body("Panel")}, order=["Panel"],
                          packages=["DeusExDeco"], meta={"anchor": ["4", "5", "6"]},
                          folders={"Panel": "arch/doors"})

    src = level_sources.PrefabLevelSource(root, "door")
    level = src.load()
    assert level.actors["Panel"].folder == "arch/doors"
    level.actors["Panel"].location = (0, 0, 128)
    src.save(verb="move", args={}, level=level, touched=["Panel"])

    _blobs, _order, _pkgs, meta, folders = stashlib.read_prefab(root, "door")
    assert meta == {"anchor": ["4", "5", "6"]}
    assert folders == {"Panel": "arch/doors"}


# --- stash / prefab: labels neither persisted nor restored -------------------------------------

def _make_stash(tmp_path):
    reg = stash_register.FileStashRegister(tmp_path / "stash")
    reg.write_stash("bay", full_level={"Box": _cube_body("Box")}, order=["Box"],
                    packages=["DeusExDeco"], meta={"anchor": ["0", "0", "0"]})
    return level_sources.StashLevelSource(reg, "bay"), (lambda: level_sources.StashLevelSource(reg, "bay"))


def _make_prefab(tmp_path):
    root = tmp_path / "Prefabs"
    stashlib.write_prefab(root, "door", full_level={"Box": _cube_body("Box")}, order=["Box"],
                          packages=["DeusExDeco"], meta={"anchor": ["0", "0", "0"]})
    return level_sources.PrefabLevelSource(root, "door"), (lambda: level_sources.PrefabLevelSource(root, "door"))


@pytest.mark.parametrize("factory", [_make_stash, _make_prefab], ids=["stash", "prefab"])
def test_box_source_does_not_persist_or_restore_actor_labels(tmp_path, factory):
    """The trunk-only label scope is NOT widened to stash/prefab wrappers: a label set on a box
    member is dropped by `save`, and `load` never re-attaches one. Fresh-loaded members carry the
    empty label set, and a stamped-then-saved label does not survive a reload."""
    src, reopen = factory(tmp_path)

    level = src.load()
    assert level.actors["Box"].labels == frozenset()           # never restored on load

    level.actors["Box"].labels = frozenset({"hero", "lighting"})
    src.save(verb="label", args={}, level=level, touched=["Box"])

    reread = reopen().load()
    assert reread.actors["Box"].labels == frozenset()          # not persisted through the save


# --- the ambient $UEDCLI_LEVEL announcement is emitted INSIDE TrunkLevelSource.save -------------

def test_trunk_from_env_save_announces_once_to_stderr(tmp_path, capsys):
    """A `from_env` trunk source announces the level to stderr from WITHIN `save` (the mutation
    seam), at most once — a read never reaches save, and a second save stays silent. Pins the
    announcement-in-save behaviour that moves to `cli/level_sources.py` in a later slice."""
    trunk.write_level(tmp_path, Level(actors={"A_1": _light("A_1")}, order=["A_1"]), {"A_1": "m"})
    src = level_sources.TrunkLevelSource(tmp_path)
    src.from_env = True
    lv = src.load()
    assert capsys.readouterr().err == ""                       # load() is silent

    lv.actors["B_2"] = _light("B_2")
    lv.order = ["A_1", "B_2"]
    src.save(verb="add", args={}, level=lv, touched=["B_2"])
    err1 = capsys.readouterr().err
    assert "from $UEDCLI_LEVEL" in err1 and err1.count("from $UEDCLI_LEVEL") == 1

    lv.actors["C_3"] = _light("C_3")
    lv.order = ["A_1", "B_2", "C_3"]
    src.save(verb="add", args={}, level=lv, touched=["C_3"])
    assert "from $UEDCLI_LEVEL" not in capsys.readouterr().err  # announced once per process, not per save
