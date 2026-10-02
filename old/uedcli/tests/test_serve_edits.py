"""Backend edit logic (plan Task 2): stage/discard/save actor location edits with per-property
conflict detection on top of `serve/snapshots.py`'s `StagingStore` (Task 1). Mirrors
`test_serve_scene.py`'s fixture pattern -- a tiny real trunk under `tmp_path` -- but needs no
`ClassIndex`/`ClassDefaults`/CSG solve: this module never resolves classes or builds geometry, it
only reads/writes actor `Location` via the same model-side path `actor move` uses."""
from __future__ import annotations

from decimal import Decimal
from pathlib import Path
from types import SimpleNamespace

import pytest

from uedcli import config, trunk
from uedcli.cli.errors import CommandError
from uedcli.cli.level_sources import TrunkLevelSource
from uedcli.model import Level
from uedcli.serve.edits import (
    apply_staged_overlay,
    check_load_conflicts,
    discard_staged,
    save_staged,
    stage_locations,
)
from uedcli.serve.snapshots import StagedActor, StagingStore
from uedcli.tests.conftest import cube_room, set_prop


def _write_fixture_trunk(tmp_path: Path) -> tuple:
    """A tiny project (`<tmp>/proj/maps/TestLevel/`) holding one brush actor -- small enough to
    load/save with no CSG solve (this module never touches geometry)."""
    root = tmp_path / "proj"
    maps_dir = root / "maps" / "TestLevel"
    maps_dir.mkdir(parents=True)
    brush = cube_room("Brush1")
    level = Level(actors={brush.name: brush}, order=[brush.name])
    trunk.write_level(maps_dir, level, {brush.name: "m"})
    project = SimpleNamespace(root=str(root), maps=None)
    return project, "TestLevel"


@pytest.fixture
def _project_and_level(tmp_path):
    return _write_fixture_trunk(tmp_path)


@pytest.fixture
def project(_project_and_level):
    return _project_and_level[0]


@pytest.fixture
def level_name(_project_and_level):
    return _project_and_level[1]


@pytest.fixture
def store(tmp_path):
    return StagingStore(tmp_path / "sessions", tmp_path / "staging" / "blobs")


def _trunk_dir(project, level_name) -> Path:
    return Path(config.project_maps_dir(project)) / level_name


def _read_actor(project, level_name, name):
    level, *_ = trunk.read_level_with_bodies(_trunk_dir(project, level_name))
    return level.actors[name]


def _external_edit(project, level_name, mutate) -> None:
    """Apply `mutate(level)` via the real model-side write path (`TrunkLevelSource`), bypassing the
    staging store entirely -- simulates an AI/terminal edit landing between Stage and Save."""
    src = TrunkLevelSource(_trunk_dir(project, level_name))
    level = src.load()
    mutate(level)
    src.save(verb="test-external-edit", args={}, level=level, touched=list(level.actors))


def _make_level_with_actor(name: str, *, location: tuple[Decimal, Decimal, Decimal]) -> Level:
    """A minimal in-memory `Level` holding one actor at `location` -- `apply_staged_overlay` needs
    no real trunk on disk (it never reads/writes one), just a `Level`/`Actor` shape."""
    actor = cube_room(name)
    actor.location = location
    return Level(actors={name: actor}, order=[name])


def test_apply_staged_overlay_does_not_mutate_the_original_level() -> None:
    level = _make_level_with_actor("Light12", location=(Decimal(0), Decimal(0), Decimal(0)))
    staged = {"Light12": StagedActor(
        baseline_location=(Decimal(0), Decimal(0), Decimal(0)),
        staged_location=(Decimal(0), Decimal(0), Decimal(99)), blob_hash="x")}

    overlaid = apply_staged_overlay(level, staged)

    assert level.actors["Light12"].location == (Decimal(0), Decimal(0), Decimal(0))
    assert overlaid.actors["Light12"].location == (Decimal(0), Decimal(0), Decimal(99))


def test_apply_staged_overlay_leaves_unstaged_actors_untouched() -> None:
    level = _make_level_with_actor("Brush1", location=(Decimal(5), Decimal(5), Decimal(5)))

    overlaid = apply_staged_overlay(level, {})

    assert overlaid.actors["Brush1"].location == (Decimal(5), Decimal(5), Decimal(5))


def test_apply_staged_overlay_skips_a_staged_actor_no_longer_in_the_level() -> None:
    """A staged actor deleted from the trunk externally (not present in `level.actors` at all) --
    silently skipped, mirroring `check_load_conflicts`'s analogous case (Rebuild has nothing to
    write, so raising here would only block a solve that doesn't even touch that actor)."""
    level = _make_level_with_actor("Brush1", location=(Decimal(0), Decimal(0), Decimal(0)))
    staged = {"Deleted": StagedActor(
        baseline_location=(Decimal(0), Decimal(0), Decimal(0)),
        staged_location=(Decimal(0), Decimal(0), Decimal(1)), blob_hash="x")}

    overlaid = apply_staged_overlay(level, staged)

    assert set(overlaid.actors) == {"Brush1"}


def test_save_no_conflict_preserves_other_property(project, level_name, store) -> None:
    stage_locations(project, level_name,
                     {"Brush1": (Decimal("10"), Decimal("0"), Decimal("0"))}, store=store)

    # external edit to a DIFFERENT property on the same actor, between Stage and Save
    _external_edit(project, level_name,
                    lambda level: set_prop(level.actors["Brush1"], "Tag", "ExternalEdit"))

    result = save_staged(project, level_name, store=store)
    assert result.applied == ["Brush1"]
    assert result.conflicts == []
    assert not store.read_staged(level_name)

    actor = _read_actor(project, level_name, "Brush1")
    assert actor.location == (Decimal("10"), Decimal("0"), Decimal("0"))   # staged move applied
    assert ("Tag", "ExternalEdit") in actor.props                          # external edit survives


def test_save_same_property_conflict_blocks_until_resolved(project, level_name, store) -> None:
    stage_locations(project, level_name,
                     {"Brush1": (Decimal("10"), Decimal("0"), Decimal("0"))}, store=store)

    # external Location change to the SAME actor/property, between Stage and Save
    _external_edit(project, level_name, lambda level: setattr(
        level.actors["Brush1"], "location", (Decimal("999"), Decimal("0"), Decimal("0"))))

    result = save_staged(project, level_name, store=store)
    assert result.applied == []
    assert len(result.conflicts) == 1
    assert result.conflicts[0].name == "Brush1"
    assert result.conflicts[0].staged_location == (Decimal("10"), Decimal("0"), Decimal("0"))
    assert result.conflicts[0].trunk_location == (Decimal("999"), Decimal("0"), Decimal("0"))
    assert store.read_staged(level_name)   # still staged -- not cleared

    actor = _read_actor(project, level_name, "Brush1")
    assert actor.location == (Decimal("999"), Decimal("0"), Decimal("0"))   # untouched by the failed Save

    result2 = save_staged(project, level_name, store=store, resolutions={"Brush1": "staged"})
    assert result2.applied == ["Brush1"]
    assert result2.conflicts == []
    assert not store.read_staged(level_name)
    actor = _read_actor(project, level_name, "Brush1")
    assert actor.location == (Decimal("10"), Decimal("0"), Decimal("0"))


def test_save_trunk_resolution_clears_stage_without_changing_trunk(project, level_name, store) -> None:
    stage_locations(project, level_name,
                     {"Brush1": (Decimal("10"), Decimal("0"), Decimal("0"))}, store=store)
    _external_edit(project, level_name, lambda level: setattr(
        level.actors["Brush1"], "location", (Decimal("999"), Decimal("0"), Decimal("0"))))

    result = save_staged(project, level_name, store=store)
    assert len(result.conflicts) == 1

    result2 = save_staged(project, level_name, store=store, resolutions={"Brush1": "trunk"})
    assert result2.applied == ["Brush1"]
    assert not store.read_staged(level_name)
    actor = _read_actor(project, level_name, "Brush1")
    assert actor.location == (Decimal("999"), Decimal("0"), Decimal("0"))   # unchanged -- trunk kept


def test_discard_clears_stage_without_touching_trunk(project, level_name, store) -> None:
    stage_locations(project, level_name,
                     {"Brush1": (Decimal("10"), Decimal("0"), Decimal("0"))}, store=store)
    discard_staged(project, level_name, store=store)
    assert store.read_staged(level_name) == {}
    actor = _read_actor(project, level_name, "Brush1")
    assert actor.location == (Decimal("0"), Decimal("0"), Decimal("0"))   # cube_room's own default


def test_discard_staged_with_actors_subset_clears_only_those(project, level_name, store) -> None:
    """Task 10's `/discard` extension: an `actors` subset discards only those actors' staged
    edits, leaving every OTHER staged actor's edit in place -- the mechanism the Save
    conflict-resolution UI needs to drop one conflicting actor's stage without losing unrelated
    staged work."""
    _external_edit(project, level_name, lambda level: (
        level.actors.__setitem__("Brush2", cube_room("Brush2")),
        level.order.append("Brush2"),
    ))
    stage_locations(project, level_name, {
        "Brush1": (Decimal("10"), Decimal("0"), Decimal("0")),
        "Brush2": (Decimal("20"), Decimal("0"), Decimal("0")),
    }, store=store)

    discard_staged(project, level_name, store=store, actors=["Brush1"])

    assert store.read_staged(level_name).keys() == {"Brush2"}   # Brush1 dropped, Brush2 untouched
    actor = _read_actor(project, level_name, "Brush1")
    assert actor.location == (Decimal("0"), Decimal("0"), Decimal("0"))   # trunk never touched


def test_discard_staged_actors_none_default_discards_the_whole_level(
        project, level_name, store) -> None:
    """`actors=None` (the default, unchanged from before this extension) still discards EVERY
    staged edit for the level -- the subset param is purely additive."""
    stage_locations(project, level_name,
                     {"Brush1": (Decimal("10"), Decimal("0"), Decimal("0"))}, store=store)
    discard_staged(project, level_name, store=store)
    assert store.read_staged(level_name) == {}


def test_discard_staged_empty_actors_list_is_a_no_op(project, level_name, store) -> None:
    """A non-`None` but EMPTY `actors` list discards nothing -- distinct from `None` (whole-level)."""
    stage_locations(project, level_name,
                     {"Brush1": (Decimal("10"), Decimal("0"), Decimal("0"))}, store=store)
    discard_staged(project, level_name, store=store, actors=[])
    assert store.read_staged(level_name).keys() == {"Brush1"}


def test_discard_staged_unstaged_actor_name_is_a_silent_no_op(project, level_name, store) -> None:
    """A name in `actors` that isn't currently staged doesn't raise -- discarding is idempotent."""
    stage_locations(project, level_name,
                     {"Brush1": (Decimal("10"), Decimal("0"), Decimal("0"))}, store=store)
    discard_staged(project, level_name, store=store, actors=["NoSuchActor"])
    assert store.read_staged(level_name).keys() == {"Brush1"}


def test_stage_locations_unknown_actor_raises_command_error(project, level_name, store) -> None:
    with pytest.raises(CommandError):
        stage_locations(project, level_name,
                         {"NoSuchActor": (Decimal("1"), Decimal("0"), Decimal("0"))}, store=store)
    assert store.read_staged(level_name) == {}   # nothing staged from the failed batch


def test_save_multiple_staged_actors_resolve_independently(project, level_name, store) -> None:
    _external_edit(project, level_name, lambda level: (
        level.actors.__setitem__("Brush2", cube_room("Brush2")),
        level.order.append("Brush2"),
    ))

    stage_locations(project, level_name, {
        "Brush1": (Decimal("10"), Decimal("0"), Decimal("0")),
        "Brush2": (Decimal("20"), Decimal("0"), Decimal("0")),
    }, store=store)

    # externally move Brush1 ONLY, so Brush1 conflicts and Brush2 doesn't
    _external_edit(project, level_name, lambda level: setattr(
        level.actors["Brush1"], "location", (Decimal("999"), Decimal("0"), Decimal("0"))))

    result = save_staged(project, level_name, store=store)
    assert result.applied == ["Brush2"]
    assert len(result.conflicts) == 1
    assert result.conflicts[0].name == "Brush1"
    assert store.read_staged(level_name).keys() == {"Brush1"}   # Brush2 cleared, Brush1 still staged

    brush1 = _read_actor(project, level_name, "Brush1")
    brush2 = _read_actor(project, level_name, "Brush2")
    assert brush1.location == (Decimal("999"), Decimal("0"), Decimal("0"))   # conflict -- untouched
    assert brush2.location == (Decimal("20"), Decimal("0"), Decimal("0"))    # applied


def test_save_prewrite_recheck_catches_a_race_after_the_main_check(
        project, level_name, store, monkeypatch) -> None:
    """The pre-write re-check (immediately before the final `.save()`) re-reads the trunk one more
    time; a change landing in the gap between the main conflict check and the write must move the
    actor from `applied` back to `conflicts`, and must NOT be clobbered by the stale write."""
    stage_locations(project, level_name,
                     {"Brush1": (Decimal("10"), Decimal("0"), Decimal("0"))}, store=store)

    real_read = trunk.read_level_with_bodies
    calls = {"n": 0}

    def racy_read(trunk_dir):
        result = real_read(trunk_dir)
        calls["n"] += 1
        if calls["n"] == 2:   # 1st = save_staged's own load; 2nd = the pre-write re-check
            result[0].actors["Brush1"].location = (Decimal("777"), Decimal("0"), Decimal("0"))
        return result

    monkeypatch.setattr("uedcli.serve.edits.trunk.read_level_with_bodies", racy_read)

    result = save_staged(project, level_name, store=store)
    assert result.applied == []
    assert len(result.conflicts) == 1
    assert result.conflicts[0].name == "Brush1"
    assert result.conflicts[0].trunk_location == (Decimal("777"), Decimal("0"), Decimal("0"))
    assert store.read_staged(level_name)   # still staged

    monkeypatch.undo()
    actor = _read_actor(project, level_name, "Brush1")
    assert actor.location == (Decimal("0"), Decimal("0"), Decimal("0"))   # write correctly withheld


def test_save_staged_actor_deleted_from_trunk_raises_command_error_and_leaves_store_untouched(
        project, level_name, store) -> None:
    """A staged actor deleted from the trunk entirely (not just moved) between Stage and Save must
    not crash with a bare `KeyError` -- and since that aborts the whole `save_staged` call, no OTHER
    staged actor in the same batch may be silently cleared either (`store.clear_actor` only runs
    after the whole per-actor loop + re-check succeed, so raising mid-loop must leave the store
    exactly as it was)."""
    _external_edit(project, level_name, lambda level: (
        level.actors.__setitem__("Brush2", cube_room("Brush2")),
        level.order.append("Brush2"),
    ))
    stage_locations(project, level_name, {
        "Brush1": (Decimal("10"), Decimal("0"), Decimal("0")),   # would apply cleanly on its own
        "Brush2": (Decimal("20"), Decimal("0"), Decimal("0")),   # about to be deleted externally
    }, store=store)

    def _delete_brush2(level: Level) -> None:
        del level.actors["Brush2"]
        level.order.remove("Brush2")

    _external_edit(project, level_name, _delete_brush2)   # Brush2 no longer exists in the trunk

    with pytest.raises(CommandError, match=r"actor not found: 'Brush2'"):
        save_staged(project, level_name, store=store)

    # nothing cleared -- both actors are still staged, INCLUDING Brush1, which on its own would
    # have applied cleanly (proves no per-actor clear_actor call happened before the raise)
    assert store.read_staged(level_name).keys() == {"Brush1", "Brush2"}

    # the aborted Save never reached the write -- Brush1's trunk Location is untouched
    brush1 = _read_actor(project, level_name, "Brush1")
    assert brush1.location == (Decimal("0"), Decimal("0"), Decimal("0"))


def test_check_load_conflicts_no_staged_edits_returns_empty(project, level_name, store) -> None:
    lvl, *_ = trunk.read_level_with_bodies(_trunk_dir(project, level_name))
    assert check_load_conflicts(level_name, lvl, store=store) == []


def test_check_load_conflicts_no_conflict_when_trunk_matches_baseline(
        project, level_name, store) -> None:
    stage_locations(project, level_name,
                     {"Brush1": (Decimal("10"), Decimal("0"), Decimal("0"))}, store=store)

    lvl, *_ = trunk.read_level_with_bodies(_trunk_dir(project, level_name))
    assert check_load_conflicts(level_name, lvl, store=store) == []
    assert store.read_staged(level_name)   # untouched -- nothing to resolve


def test_load_reports_but_never_blocks_on_conflict_and_accept_load_clears_stage(
        project, level_name, store: StagingStore) -> None:
    stage_locations(project, level_name,
                     {"Brush1": (Decimal("10"), Decimal("0"), Decimal("0"))}, store=store)

    # simulate an external Location change to Brush1 in the trunk, bypassing the staging store
    _external_edit(project, level_name, lambda level: setattr(
        level.actors["Brush1"], "location", (Decimal("999"), Decimal("0"), Decimal("0"))))

    lvl, *_ = trunk.read_level_with_bodies(_trunk_dir(project, level_name))
    conflicts = check_load_conflicts(level_name, lvl, store=store)
    assert len(conflicts) == 1 and conflicts[0].name == "Brush1"
    assert conflicts[0].staged_location == (Decimal("10"), Decimal("0"), Decimal("0"))
    assert conflicts[0].trunk_location == (Decimal("999"), Decimal("0"), Decimal("0"))
    assert store.read_staged(level_name)   # untouched -- default is "keep staged"

    conflicts2 = check_load_conflicts(
        level_name, lvl, store=store, resolutions={"Brush1": "accept-load"})
    assert conflicts2 == []
    assert not store.read_staged(level_name)   # cleared


def test_check_load_conflicts_staged_actor_deleted_externally_clears_stage_silently(
        project, level_name, store) -> None:
    """A staged actor deleted from the trunk entirely (not just moved) must NOT raise -- Load never
    blocks or fails on a conflict, and a deleted actor is not a reportable conflict (no real
    `trunk_location` to show). Its now-stale staged entry is silently dropped instead, exactly as if
    it had never been staged."""
    stage_locations(project, level_name,
                     {"Brush1": (Decimal("10"), Decimal("0"), Decimal("0"))}, store=store)

    def _delete_brush1(level: Level) -> None:
        del level.actors["Brush1"]
        level.order.remove("Brush1")

    _external_edit(project, level_name, _delete_brush1)

    lvl, *_ = trunk.read_level_with_bodies(_trunk_dir(project, level_name))
    conflicts = check_load_conflicts(level_name, lvl, store=store)
    assert conflicts == []
    assert not store.read_staged(level_name)   # the stale entry is gone


def test_save_prewrite_recheck_catches_a_race_after_a_resolved_conflict(
        project, level_name, store, monkeypatch) -> None:
    """The pre-write re-check must also catch a race for an actor that reached `touched` via an
    EXPLICIT conflict resolution (`"staged"`/`"trunk"`), not just the no-conflict auto-apply path.
    Comparing against the actor's ORIGINAL stage-time baseline here would immediately (and wrongly)
    re-flag the very divergence the resolution just overrode; comparing against the decision-time
    value this very `save_staged` call already read (`expected_before_write`) correctly flags only
    a FURTHER change landing after that read -- this is the exact case the report's deviation from
    the brief's literal "re-compare against its baseline" wording rests on."""
    stage_locations(project, level_name,
                     {"Brush1": (Decimal("10"), Decimal("0"), Decimal("0"))}, store=store)
    # first external change -- makes this a conflict the caller must resolve
    _external_edit(project, level_name, lambda level: setattr(
        level.actors["Brush1"], "location", (Decimal("999"), Decimal("0"), Decimal("0"))))

    real_read = trunk.read_level_with_bodies
    calls = {"n": 0}

    def racy_read(trunk_dir):
        result = real_read(trunk_dir)
        calls["n"] += 1
        if calls["n"] == 2:   # 1st = save_staged's own load; 2nd = the pre-write re-check
            # a SECOND external change, landing after this Save call's own load -- on top of the
            # already-resolved 999 divergence
            result[0].actors["Brush1"].location = (Decimal("555"), Decimal("0"), Decimal("0"))
        return result

    monkeypatch.setattr("uedcli.serve.edits.trunk.read_level_with_bodies", racy_read)

    result = save_staged(project, level_name, store=store, resolutions={"Brush1": "staged"})
    assert result.applied == []
    assert len(result.conflicts) == 1
    assert result.conflicts[0].name == "Brush1"
    assert result.conflicts[0].staged_location == (Decimal("10"), Decimal("0"), Decimal("0"))
    assert result.conflicts[0].trunk_location == (Decimal("555"), Decimal("0"), Decimal("0"))
    assert store.read_staged(level_name)   # still staged -- the resolution never got to apply

    monkeypatch.undo()
    actor = _read_actor(project, level_name, "Brush1")
    assert actor.location == (Decimal("999"), Decimal("0"), Decimal("0"))   # write correctly withheld
