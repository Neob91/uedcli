"""Pure diff/order-recompute logic for `level reimport` — no I/O, no editor.

Classifies actors between an existing trunk and a freshly decoded map by NAME (the only identity a
compiled map and a trunk share), and recomputes brush `order_value`s with minimal churn. See
dev/docs/board/to-plan/level-reimport-reimport-a-hand-edited-dx-unr/spec.md.
"""
from __future__ import annotations

import copy
from dataclasses import dataclass

from . import trunk
from .model import Actor, Level


@dataclass(frozen=True)
class ReimportDiff:
    added: frozenset[str]      # names only in the freshly decoded map
    deleted: frozenset[str]    # names only in the existing trunk
    changed: frozenset[str]    # matched names whose body differs at all — gets (re)written
    modified: frozenset[str]   # `changed`, minus a Location/Rotation-only difference — feeds the
                                # blast-radius guard (an ordinary reposition shouldn't trip it)


def _pose_blind_body(actor: Actor) -> str:
    """`trunk.dump_actor_body`, blind to Location/Rotation. `Rotation` is a generic prop tuple
    (never a structured `Actor` field — see `model.Actor`), so it is filtered out of `props`;
    `location`/`location_text` are reset directly."""
    a = copy.deepcopy(actor)
    a.location = None
    a.location_text = None
    a.props = [(k, v) for k, v in a.props if k != "Rotation"]
    return trunk.dump_actor_body(a)


def diff_actors(existing: Level, new: Level) -> ReimportDiff:
    """Classify every actor name across the two levels. `existing` is the trunk's current on-disk
    `Level` (`trunk.read_level`); `new` is the freshly decoded map's `Level`."""
    old_names = set(existing.actors)
    new_names = set(new.actors)
    matched = old_names & new_names
    changed = {n for n in matched
              if trunk.dump_actor_body(existing.actors[n]) != trunk.dump_actor_body(new.actors[n])}
    modified = {n for n in matched
               if _pose_blind_body(existing.actors[n]) != _pose_blind_body(new.actors[n])}
    return ReimportDiff(added=frozenset(new_names - old_names),
                        deleted=frozenset(old_names - new_names),
                        changed=frozenset(changed), modified=frozenset(modified))


def blast_radius_exceeded(diff: ReimportDiff, old_actor_count: int, *,
                          threshold: float = 0.20) -> bool:
    """True when `(modified + deleted) / old_actor_count` exceeds `threshold`. Pure additions never
    enter either side (spec 'The blast-radius guard'). An empty trunk can never exceed it — there is
    nothing to lose."""
    if old_actor_count == 0:
        return False
    blast = len(diff.modified) + len(diff.deleted)
    return (blast / old_actor_count) > threshold


def _longest_increasing_subsequence(seq: list[str], key) -> list[str]:
    """The longest run of `seq` whose `key` is strictly increasing (O(n^2) DP — a level's brush
    count is small, tens to low hundreds, so clarity wins over asymptotic speed here). Ties in `key`
    never occur: LexoRank `order_value`s are unique per actor by construction."""
    n = len(seq)
    if n == 0:
        return []
    keys = [key(x) for x in seq]
    length = [1] * n
    prev = [-1] * n
    for i in range(n):
        for j in range(i):
            if keys[j] < keys[i] and length[j] + 1 > length[i]:
                length[i] = length[j] + 1
                prev[i] = j
    best = max(range(n), key=lambda i: length[i])
    out: list[str] = []
    i = best
    while i != -1:
        out.append(seq[i])
        i = prev[i]
    return list(reversed(out))


def compute_brush_ranks(existing_ranks: dict[str, str], new_level: Level,
                        diff: ReimportDiff) -> dict[str, str]:
    """New `order_value` for every brush actor that will exist after the reimport (matched +
    added — a deleted brush needs none). A matched brush whose relative position among brushes is
    UNCHANGED keeps its existing `order_value` (the longest-increasing-subsequence diff, by current
    rank); every other brush (moved, or newly added) gets a freshly minted LexoRank value at its new
    position, via `trunk.ranks_between` so a run of several new/moved brushes between the same two
    stable neighbours still lands in the right relative order. Point actors are never touched — the
    caller (`level reimport`) merges this dict with the untouched point-actor ranks."""
    new_brush_order = [n for n in new_level.order if new_level.actors[n].brush is not None]
    matched_brushes = [n for n in new_brush_order if n not in diff.added]
    stable = set(_longest_increasing_subsequence(matched_brushes, key=lambda n: existing_ranks[n]))

    ranks: dict[str, str] = {n: existing_ranks[n] for n in stable}
    i = 0
    lo: str | None = None
    while i < len(new_brush_order):
        name = new_brush_order[i]
        if name in stable:
            lo = ranks[name]
            i += 1
            continue
        run_start = i
        while i < len(new_brush_order) and new_brush_order[i] not in stable:
            i += 1
        run = new_brush_order[run_start:i]
        hi = ranks[new_brush_order[i]] if i < len(new_brush_order) else None
        for name, r in zip(run, trunk.ranks_between(lo, hi, len(run))):
            ranks[name] = r
        lo = hi
    return ranks
