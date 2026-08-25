import argparse
from unittest import mock

import pytest

from uedcli import trunk
from uedcli.cli import errors, level_sources
from uedcli.cli import dispatch
from uedcli.model import Actor, Level


def _ns(**kw):
    return argparse.Namespace(**kw)


def _proj(tmp_path, name="lvl"):
    p = tmp_path / "myrepo"
    (p / "maps" / name).mkdir(parents=True)
    (p / "uedcli.toml").write_text('game = "deusex"\n')
    return p, name


# (The `StoreLevelSource` delegation tests were removed with the class in the session-store un-wire,
# slice 4 — `_resolve_level_source` is now trunk-only. `TrunkLevelSource` is the only level source.)


# --- Task 2: TrunkLevelSource round-trip + rank reconciliation ---

def test_trunk_source_roundtrips_and_ranks_a_new_actor(tmp_path):
    seed = Level(actors={"A_1": Actor(name="A_1", cls="Light"),
                         "B_2": Actor(name="B_2", cls="Light")})
    trunk.write_level(tmp_path, seed, {"A_1": "m", "B_2": "t"})

    src = level_sources.TrunkLevelSource(tmp_path)
    level = src.load()
    assert level.order == ["A_1", "B_2"]

    level.actors["C_3"] = Actor(name="C_3", cls="Light")
    level.order.append("C_3")
    src.save(level=level, verb="add", args={}, touched=["C_3"])

    got, ranks = trunk.read_level(tmp_path)
    assert set(got.actors) == {"A_1", "B_2", "C_3"}
    assert ranks["A_1"] == "m" and ranks["B_2"] == "t"
    assert ranks["C_3"] > "t"


def test_trunk_source_drops_a_removed_actor(tmp_path):
    seed = Level(actors={"A_1": Actor(name="A_1", cls="Light"),
                         "B_2": Actor(name="B_2", cls="Light")})
    trunk.write_level(tmp_path, seed, {"A_1": "m", "B_2": "t"})
    src = level_sources.TrunkLevelSource(tmp_path)
    level = src.load()
    del level.actors["B_2"]
    level.order.remove("B_2")
    src.save(level=level, verb="delete", args={}, touched=["B_2"])
    got, _ = trunk.read_level(tmp_path)
    assert set(got.actors) == {"A_1"}


def test_trunk_source_interleaved_new_actor_does_not_collide(tmp_path):
    # No current verb inserts mid-order, but the rank reconciliation must never mint a colliding
    # order_value even if level.order interleaves a new actor between existing ones.
    seed = Level(actors={"A_1": Actor(name="A_1", cls="Light"),
                         "B_2": Actor(name="B_2", cls="Light")})
    trunk.write_level(tmp_path, seed, {"A_1": "m", "B_2": "t"})
    src = level_sources.TrunkLevelSource(tmp_path)
    level = src.load()
    level.actors["C_3"] = Actor(name="C_3", cls="Light")
    level.order = ["A_1", "C_3", "B_2"]
    src.save(level=level, verb="add", args={}, touched=["C_3"])
    _, ranks = trunk.read_level(tmp_path)
    assert len(set(ranks.values())) == 3                 # all distinct — no duplicate order_value
    assert ranks["A_1"] == "m" and ranks["B_2"] == "t"


def test_trunk_source_preserves_an_empty_stored_rank(tmp_path):
    seed = Level(actors={"A_1": Actor(name="A_1", cls="Light"),
                         "B_2": Actor(name="B_2", cls="Light")})
    trunk.write_level(tmp_path, seed, {"A_1": "", "B_2": "t"})   # A_1's rank is a (degenerate) empty string
    src = level_sources.TrunkLevelSource(tmp_path)
    level = src.load()
    level.actors["C_3"] = Actor(name="C_3", cls="Light")
    level.order.append("C_3")
    src.save(level=level, verb="add", args={}, touched=["C_3"])
    _, ranks = trunk.read_level(tmp_path)
    assert ranks["A_1"] == ""                            # preserved (membership test), not re-minted


def test_trunk_source_save_without_load_raises(tmp_path):
    with pytest.raises(RuntimeError, match="prior load"):
        level_sources.TrunkLevelSource(tmp_path).save(level=Level(), verb="add", args={}, touched=[])


def test_trunk_source_ranks_override_reorders_an_existing_actor(tmp_path):
    # The CSG-order seam (spec 2026-07-18 §3): a `ranks=` override changes an EXISTING actor's
    # order_value even though the Level carries no per-actor rank — the reorder must reach disk.
    seed = Level(actors={"A_1": Actor(name="A_1", cls="Light"),
                         "B_2": Actor(name="B_2", cls="Light")})
    trunk.write_level(tmp_path, seed, {"A_1": "m", "B_2": "t"})
    src = level_sources.TrunkLevelSource(tmp_path)
    level = src.load()
    src.save(level=level, verb="order", args={}, touched=["B_2"], ranks={"B_2": "a"})
    got, ranks = trunk.read_level(tmp_path)
    assert ranks["B_2"] == "a" and ranks["A_1"] == "m"    # override applied, other rank preserved
    assert got.order == ["B_2", "A_1"]                    # B_2 now sorts first


# --- Task 3: _resolve_level_source routing (trunk-only) ---

def test_resolve_source_uses_the_trunk_for_a_project_and_selection(tmp_path, monkeypatch):
    proj, name = _proj(tmp_path)
    monkeypatch.setenv("UEDCLI_LEVEL", name)
    src = level_sources.resolve_level_source(_ns(project=str(proj)))
    assert isinstance(src, level_sources.TrunkLevelSource)
    assert src.trunk_dir.name == name


def test_resolve_source_errors_with_no_project(tmp_path, monkeypatch):
    monkeypatch.delenv("UEDCLI_PROJECT", raising=False)
    monkeypatch.chdir(tmp_path)
    with pytest.raises(dispatch.ProjectError):
        level_sources.resolve_level_source(_ns(project=None))


def test_resolve_source_errors_with_a_project_but_no_selection(tmp_path):
    proj, _ = _proj(tmp_path)
    with pytest.raises(errors.LevelSelectionError):
        level_sources.resolve_level_source(_ns(project=str(proj)))


# --- concurrent-writer delta saves (dev/docs/direction/trunk-and-editor.md 2026-07-18 — trunk delta writes) ---

def test_interleaved_saves_compose_disjoint_adds(tmp_path):
    """Two sources loaded from the same snapshot, each adding a DIFFERENT actor: both adds must
    survive on disk. The old make-disk-match-memory full prune made the second save silently
    delete the first's actor (the reproduced 8-parallel-adds → +1 lost-update, round-3 review)."""
    seed = Level(actors={"Base_1": Actor(name="Base_1", cls="Light")})
    trunk.write_level(tmp_path, seed, {"Base_1": "m"})
    a, b = level_sources.TrunkLevelSource(tmp_path), level_sources.TrunkLevelSource(tmp_path)
    la, lb = a.load(), b.load()                        # both see only Base_1
    lb.actors["FromB_2"] = Actor(name="FromB_2", cls="Light")
    lb.order = ["Base_1", "FromB_2"]
    b.save(verb="actor add", args={}, level=lb, touched=["FromB_2"])
    la.actors["FromA_3"] = Actor(name="FromA_3", cls="Light")
    la.order = ["Base_1", "FromA_3"]
    a.save(verb="actor add", args={}, level=la, touched=["FromA_3"])   # must NOT prune FromB_2
    on_disk, ranks = trunk.read_level(tmp_path)
    assert set(on_disk.actors) == {"Base_1", "FromA_3", "FromB_2"}
    # both fresh ranks sort after the base; equal values are fine (name tiebreak, 2026-07-05 15:11)
    assert ranks["FromA_3"] > "m" and ranks["FromB_2"] > "m"


def test_save_prunes_only_its_own_deletions(tmp_path):
    """A source that DELETED an actor prunes exactly that actor — a concurrently-added dir it
    never loaded is left alone, and re-loading shows both effects."""
    seed = Level(actors={"Keep_1": Actor(name="Keep_1", cls="Light"),
                         "Gone_2": Actor(name="Gone_2", cls="Light")})
    trunk.write_level(tmp_path, seed, {"Keep_1": "m", "Gone_2": "t"})
    src = level_sources.TrunkLevelSource(tmp_path)
    lv = src.load()
    # a concurrent writer lands a new actor AFTER our load
    other = level_sources.TrunkLevelSource(tmp_path)
    lo = other.load()
    lo.actors["Late_3"] = Actor(name="Late_3", cls="Light")
    lo.order = ["Keep_1", "Gone_2", "Late_3"]
    other.save(verb="actor add", args={}, level=lo, touched=["Late_3"])
    # our own save deletes Gone_2 only
    del lv.actors["Gone_2"]
    lv.order = ["Keep_1"]
    src.save(verb="actor delete", args={}, level=lv, touched=["Gone_2"])
    on_disk, _ = trunk.read_level(tmp_path)
    assert set(on_disk.actors) == {"Keep_1", "Late_3"}


def test_save_takes_a_per_level_flock_in_maps_locks(tmp_path):
    """The save serializes under `<maps-dir>/.locks/level-<name>.lock` — resource-adjacent and
    self-ignoring, like the catalog locks (dev/docs/direction/safety.md 2026-07-18)."""
    proj, name = _proj(tmp_path)
    trunk_dir = proj / "maps" / name
    src = level_sources.TrunkLevelSource(trunk_dir)
    lv = src.load()
    lv.actors["A_1"] = Actor(name="A_1", cls="Light")
    lv.order = ["A_1"]
    src.save(verb="actor add", args={}, level=lv, touched=["A_1"])
    locks = proj / "maps" / ".locks"
    assert (locks / f"level-{name}.lock").exists()
    assert (locks / ".gitignore").read_text() == "*\n"


def test_interleaved_save_does_not_revert_a_concurrent_edit(tmp_path):
    """An add-only saver must not rewrite an actor another process EDITED after our load — the
    content-diff keeps untouched actors' dirs alone (review round on the delta-write fix,
    2026-07-18: an add-only save reverted a concurrent prop edit / resurrected a concurrent
    delete from the stale model)."""
    seed = Level(actors={"Base_1": Actor(name="Base_1", cls="Light")})
    trunk.write_level(tmp_path, seed, {"Base_1": "m"})
    a, b = level_sources.TrunkLevelSource(tmp_path), level_sources.TrunkLevelSource(tmp_path)
    la, lb = a.load(), b.load()
    # B edits Base_1 and saves
    lb.actors["Base_1"].props = [("LightBrightness", "200")]
    b.save(verb="actor prop", args={}, level=lb, touched=["Base_1"])
    # A (stale Base_1) saves a disjoint add — must NOT revert B's edit
    la.actors["New_2"] = Actor(name="New_2", cls="Light")
    la.order = ["Base_1", "New_2"]
    a.save(verb="actor add", args={}, level=la, touched=["New_2"])
    on_disk, _ = trunk.read_level(tmp_path)
    assert ("LightBrightness", "200") in on_disk.actors["Base_1"].props
    assert set(on_disk.actors) == {"Base_1", "New_2"}


def test_interleaved_save_does_not_resurrect_a_concurrent_delete(tmp_path):
    """An add-only saver must not resurrect an actor another process DELETED after our load."""
    seed = Level(actors={"Base_1": Actor(name="Base_1", cls="Light"),
                         "Victim_2": Actor(name="Victim_2", cls="Light")})
    trunk.write_level(tmp_path, seed, {"Base_1": "m", "Victim_2": "t"})
    a, b = level_sources.TrunkLevelSource(tmp_path), level_sources.TrunkLevelSource(tmp_path)
    la, lb = a.load(), b.load()
    del lb.actors["Victim_2"]
    lb.order = ["Base_1"]
    b.save(verb="actor delete", args={}, level=lb, touched=["Victim_2"])
    la.actors["New_3"] = Actor(name="New_3", cls="Light")
    la.order = ["Base_1", "Victim_2", "New_3"]
    a.save(verb="actor add", args={}, level=la, touched=["New_3"])   # stale model holds Victim_2
    on_disk, _ = trunk.read_level(tmp_path)
    assert set(on_disk.actors) == {"Base_1", "New_3"}                # Victim_2 stays deleted


def test_unchanged_actor_files_are_not_rewritten(tmp_path):
    """The content-diff means an untouched actor's files are not even opened for write — pinned
    via mtime/inode stability across a disjoint-add save."""
    import os as _os
    seed = Level(actors={"Base_1": Actor(name="Base_1", cls="Light")})
    trunk.write_level(tmp_path, seed, {"Base_1": "m"})
    body = tmp_path / "actors" / "Base_1" / "actor.t3d"
    before = _os.stat(body)
    src = level_sources.TrunkLevelSource(tmp_path)
    lv = src.load()
    lv.actors["New_2"] = Actor(name="New_2", cls="Light")
    lv.order = ["Base_1", "New_2"]
    src.save(verb="actor add", args={}, level=lv, touched=["New_2"])
    after = _os.stat(body)
    assert (before.st_mtime_ns, before.st_ino) == (after.st_mtime_ns, after.st_ino)


def test_read_level_skips_an_empty_torn_body(tmp_path):
    """A 0-byte `actor.t3d` (crashed pre-atomic writer) is skipped like a missing one — it used
    to make EVERY later read of the level die on a raw StopIteration until hand-repair."""
    seed = Level(actors={"Good_1": Actor(name="Good_1", cls="Light")})
    trunk.write_level(tmp_path, seed, {"Good_1": "m"})
    torn = tmp_path / "actors" / "Torn_2"
    torn.mkdir()
    (torn / "actor.t3d").write_text("")
    (torn / "order_value").write_text("t\n")
    lv, ranks = trunk.read_level(tmp_path)
    assert set(lv.actors) == {"Good_1"} and "Torn_2" not in ranks


def test_read_level_errors_cleanly_on_a_corrupt_non_blank_body(tmp_path):
    """A non-blank but unparseable actor.t3d (e.g. unresolved merge markers) is a HARD error naming
    the actor — not a raw StopIteration, and not silently dropped like the 0-byte torn case."""
    seed = Level(actors={"Good_1": Actor(name="Good_1", cls="Light")})
    trunk.write_level(tmp_path, seed, {"Good_1": "m"})
    bad = tmp_path / "actors" / "Bad_2"
    bad.mkdir()
    (bad / "actor.t3d").write_text("<<<<<<< HEAD\nsome garbage\n=======\n")
    (bad / "order_value").write_text("t\n")
    src = level_sources.TrunkLevelSource(tmp_path)
    with pytest.raises(errors.CommandError, match="Bad_2"):
        src.load()


def test_load_actor_body_rejects_a_body_with_no_actor_block():
    with pytest.raises(ValueError, match="Foo"):
        trunk.load_actor_body("garbage, not a t3d actor block\n", "Foo")
