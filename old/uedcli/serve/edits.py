"""GUI actor-edit business logic (Plan Task 2): stage/discard/save on top of `snapshots.StagingStore`
(Task 1). Writes go through `TrunkLevelSource`, the exact model-side path `cli/commands/actor/
edit.py`'s `_move` already uses (load once, mutate `level.actors[name].location`, save once) --
no separate write mechanism is introduced here.

Decimal throughout: every location this module touches stays `Decimal`, never `float`; a
`level.actors[name].location` of `None` (unset) is treated as `(Decimal(0), Decimal(0), Decimal(0))`
everywhere, matching `_move`'s own `--by` default (`edit.py:74`).

Save's conflict rule is per-actor, not per-property: a staged actor's CURRENT trunk `Location` is
compared, Decimal-to-Decimal, against the baseline captured at stage time. Unchanged -> the staged
move applies cleanly (any OTHER property changed externally in the meantime survives, since only
`Location` is ever mutated here). Changed -> a real Location conflict, left staged until the caller
supplies a resolution (`"staged"` or `"trunk"`).

Load's conflict check (`check_load_conflicts`) is the same comparison in the reverse direction: a
staged actor whose trunk `Location` moved externally since it was staged, discovered on an explicit
Load. Unlike Save, Load never blocks or fails on a conflict -- it only reports one; the caller's own
trunk refresh always completes."""
from __future__ import annotations

import copy
from dataclasses import dataclass
from decimal import Decimal
from pathlib import Path

from .. import config, query, trunk
from ..cli.errors import CommandError
from ..cli.level_sources import TrunkLevelSource
from ..model import Level
from .snapshots import StagedActor, StagingStore

_ZERO: tuple[Decimal, Decimal, Decimal] = (Decimal(0), Decimal(0), Decimal(0))


@dataclass(frozen=True, kw_only=True)
class SaveConflict:
    """One staged actor whose trunk `Location` moved (relative to its staged baseline) before Save
    could apply it -- left staged until the caller resolves it."""
    name: str
    staged_location: tuple[Decimal, Decimal, Decimal]
    trunk_location: tuple[Decimal, Decimal, Decimal]


@dataclass(frozen=True, kw_only=True)
class SaveResult:
    applied: list[str]
    conflicts: list[SaveConflict]


def _trunk_dir(project, level_name: str) -> Path:
    return Path(config.project_maps_dir(project)) / level_name


def stage_locations(
    project, level_name: str, moves: dict[str, tuple[Decimal, Decimal, Decimal]], *,
    store: StagingStore,
) -> list[str]:
    """Stage a batch of actor moves. Loads the trunk ONCE for the whole batch (not once per actor).
    Each actor's CURRENT `Location` (`None` -> `(0,0,0)`) is the baseline CANDIDATE --
    `StagingStore.stage` itself keeps an already-staged actor's original baseline, so re-staging
    never moves it (Task 1). Returns the staged canonical names.

    Raises `CommandError(f"actor not found: {name!r}")` for a `moves` key that doesn't resolve to a
    real actor -- never a bare `KeyError` (`query.resolve_actor_name` raises one internally; caught
    and re-raised here as the domain error `error_to_status` classifies as a 422)."""
    if not moves:
        return []
    trunk_dir = _trunk_dir(project, level_name)
    level, _ranks, bodies, _folders = trunk.read_level_with_bodies(trunk_dir)
    staged_names: list[str] = []
    for name, location in moves.items():
        try:
            canonical = query.resolve_actor_name(level, name)
        except KeyError:
            raise CommandError(f"actor not found: {name!r}")
        baseline = level.actors[canonical].location or _ZERO
        store.stage(level_name, canonical, actor_t3d_text=bodies[canonical],
                    baseline_location=baseline, staged_location=location)
        staged_names.append(canonical)
    return staged_names


def discard_staged(
    project, level_name: str, *, store: StagingStore, actors: list[str] | None = None,
) -> None:
    """Discard staged edits for `level_name`. No trunk interaction either way -- staging never
    touches the trunk until Save.

    `actors=None` (default): discard EVERY staged edit for the level (the original whole-level
    behavior, `StagingStore.discard`). A non-`None` `actors` list discards only THOSE actors'
    staged edits (`StagingStore.clear_actor` per name), leaving every other staged actor untouched
    -- lets a caller drop one conflicting actor's stage (e.g. from Save's conflict-resolution UI,
    Task 10) without losing unrelated staged work. `stage_locations`/`StagingStore.stage` have no
    equivalent partial-drop, so this is the one place that needs the distinction. A name not
    currently staged is silently a no-op (`clear_actor`'s own behavior), not an error -- discarding
    is idempotent, same as the whole-level case."""
    if actors is None:
        store.discard(level_name)
        return
    for name in actors:
        store.clear_actor(level_name, name)


def save_staged(
    project, level_name: str, *, store: StagingStore,
    resolutions: dict[str, str] | None = None,
) -> SaveResult:
    """Apply every staged actor's move to the trunk, one load + one save for the whole batch.

    Per staged actor: if its current trunk `Location` still equals its staged baseline, the move
    applies. Otherwise it's a conflict -- unless `resolutions[name]` is `"staged"` (apply the staged
    move anyway) or `"trunk"` (keep the current trunk value; a no-op location-wise, but the stage
    still clears, since the caller explicitly chose to drop it). With no resolution, the actor stays
    staged and is reported as a `SaveConflict`.

    Immediately before the actual write, every about-to-be-applied actor's trunk `Location` is
    re-read one more time and re-compared against the value this call itself just read (baseline,
    for the no-conflict path; the already-diverged trunk value, for a resolved conflict -- re-
    litigating THAT against the original baseline would immediately re-flag it) -- narrows (does not
    eliminate) the TOCTOU window between the check above and the write. A re-check failure moves
    that actor from `applied` back to `conflicts` and reverts its in-memory `Location`, so the stale
    write can't clobber whatever landed in the gap."""
    resolutions = resolutions or {}
    staged = store.read_staged(level_name)
    if not staged:
        return SaveResult(applied=[], conflicts=[])

    trunk_dir = _trunk_dir(project, level_name)
    src = TrunkLevelSource(trunk_dir)
    level = src.load()

    conflicts: list[SaveConflict] = []
    touched: list[str] = []
    originals: dict[str, tuple[Decimal, Decimal, Decimal] | None] = {}
    # What we expect the trunk to still hold for a touched actor right before the write: baseline
    # for the no-conflict auto-apply path, but the ALREADY-DIVERGED current value for a resolved
    # conflict ("staged"/"trunk") -- re-comparing a resolved conflict against its ORIGINAL baseline
    # would immediately re-flag it (that mismatch is exactly what the resolution just overrode). The
    # re-check's job is only to catch a FURTHER change landing after this load, not to re-litigate
    # a conflict the caller already resolved.
    expected_before_write: dict[str, tuple[Decimal, Decimal, Decimal]] = {}

    for name, entry in staged.items():
        actor = level.actors.get(name)
        if actor is None:
            raise CommandError(f"actor not found: {name!r}")
        current = actor.location or _ZERO
        if current == entry.baseline_location:
            new_location = entry.staged_location
        else:
            resolution = resolutions.get(name)
            if resolution == "staged":
                new_location = entry.staged_location
            elif resolution == "trunk":
                new_location = current
            else:
                conflicts.append(SaveConflict(name=name, staged_location=entry.staged_location,
                                               trunk_location=current))
                continue
        originals[name] = actor.location
        expected_before_write[name] = current
        actor.location = new_location
        touched.append(name)

    if touched:
        fresh_level, *_ = trunk.read_level_with_bodies(trunk_dir)
        still_touched: list[str] = []
        for name in touched:
            fresh_actor = fresh_level.actors.get(name)
            fresh_current = fresh_actor.location or _ZERO if fresh_actor is not None else _ZERO
            if fresh_current != expected_before_write[name]:
                level.actors[name].location = originals[name]   # revert -- don't clobber the race
                conflicts.append(SaveConflict(
                    name=name, staged_location=staged[name].staged_location,
                    trunk_location=fresh_current))
            else:
                still_touched.append(name)
        touched = still_touched

    if touched:
        src.save(verb="move", args={"names": touched}, level=level, touched=touched)
    for name in touched:
        store.clear_actor(level_name, name)

    return SaveResult(applied=touched, conflicts=conflicts)


def apply_staged_overlay(level: Level, staged: dict[str, StagedActor]) -> Level:
    """A new `Level` -- a shallow copy of `level` whose `actors` dict is itself a shallow copy, with
    only staged actors replaced by a copy carrying the staged `Location` -- never mutates `level`
    itself. Session-scoped Rebuild (plan Task 11) feeds this into `build_scene` instead of the
    shared `LevelContext.trunk_ref`'s `Level` directly, so two sessions (or two Rebuilds of the same
    session) can safely overlay the same shared trunk concurrently: neither ever writes into the
    original. A staged actor no longer present in `level` (e.g. deleted from the trunk externally)
    is silently skipped -- Rebuild has nothing to write, so there's nothing to protect by raising."""
    new_actors = dict(level.actors)
    for name, entry in staged.items():
        if name not in new_actors:
            continue
        actor_copy = copy.copy(new_actors[name])
        actor_copy.location = entry.staged_location
        new_actors[name] = actor_copy
    overlaid = copy.copy(level)
    overlaid.actors = new_actors
    return overlaid


def check_load_conflicts(
    level_name: str, incoming_level, *, store: StagingStore,
    resolutions: dict[str, str] | None = None,
) -> list[SaveConflict]:
    """Load-side symmetric conflict check (the reverse of `save_staged`'s): for each staged actor,
    compare `incoming_level`'s current `Location` (a freshly `trunk.read_level_with_bodies`-loaded
    `Level` the caller already has -- this never loads the trunk itself) against the staged entry's
    `baseline_location`, Decimal-exact. Equal -> no conflict, nothing to do (the staged edit's own
    baseline is still valid). Different -> a deliberately simplified resolution model: the only real
    action is `resolutions[name] == "accept-load"`, which clears that actor's stage (the caller chose
    to drop their staged edit and accept the external change). There is no separate "keep-staged"
    value -- declining to resolve (the default) already IS keep-staged, since the staged entry is
    left untouched and Save will re-surface the same conflict later.

    Never writes to the trunk and never blocks or raises -- the caller's own trunk refresh always
    completes regardless of what this reports. A staged actor no longer present in `incoming_level`
    (deleted from the trunk externally, not merely moved) has no `Location` to compare and no real
    `trunk_location` to report -- its now-stale staged entry is silently cleared (`store.clear_actor`)
    and it is NOT added to `conflicts`, exactly as if it had never been staged. This deliberately
    differs from `save_staged`'s analogous case (which raises `CommandError`, since Save is a write
    that must not proceed on bad data): Load has nothing to write, so there is nothing to protect by
    failing the request."""
    resolutions = resolutions or {}
    staged = store.read_staged(level_name)
    if not staged:
        return []

    conflicts: list[SaveConflict] = []
    for name, entry in staged.items():
        actor = incoming_level.actors.get(name)
        if actor is None:
            store.clear_actor(level_name, name)
            continue
        current = actor.location or _ZERO
        if current == entry.baseline_location:
            continue
        if resolutions.get(name) == "accept-load":
            store.clear_actor(level_name, name)
            continue
        conflicts.append(SaveConflict(name=name, staged_location=entry.staged_location,
                                       trunk_location=current))
    return conflicts
