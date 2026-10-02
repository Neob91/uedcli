# `level reimport` Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add `level reimport MAPFILE --tree level/NAME [--force]` — fold a hand-edited compiled
`.dx`/`.unr` back into the EXISTING trunk that produced it, matching actors by name so unrelated
actors, folders/labels and CSG order are left untouched.

**Architecture:** Reuse `level import`'s decode pipeline unchanged (`mapimport.import_map` →
`parse_t3d_actors` → `drop_editor_scratch` → `ingest.validate_ingest_actors`) to get a fresh
in-memory `Level`. A new pure module, `reimport_ops.py`, diffs that against the trunk's current
on-disk `Level` (by actor name) and recomputes brush `order_value`s with minimal churn. The verb
wires the two together and writes through the existing `trunk.write_level` delta path — no new
write primitive.

**Tech Stack:** Python 3.12, pytest, the existing `uedcli` CLI/model/trunk modules.

**Spec:** `dev/docs/board/to-plan/level-reimport-reimport-a-hand-edited-dx-unr/spec.md` (canonical
copy: `docs/superpowers/specs/2026-08-29-level-reimport-design.md`) — read it first; this plan
argues from it.

## Global Constraints

- No back-compat cruft: this is a brand new verb, nothing to preserve alongside.
- No silent half-answers: every refusal is a clean `CommandError` (→ exit 2) naming the offending
  value — never a bare traceback, never a partial write.
- Producer-verb output convention: imported actor names to **stdout**, one per line; the human
  summary and every `note:` line to **stderr**.
- `docs/usage.md` is updated in this same change (project `CLAUDE.md`: user-facing docs must stay
  current with the CLI).
- Every new function gets a docstring stating what it does and, where non-obvious, why.

---

### Task 1: `reimport_ops.diff_actors` — classify actors by name

**Files:**
- Create: `uedcli/reimport_ops.py`
- Test: `uedcli/tests/test_reimport_ops.py`

**Interfaces:**
- Produces: `ReimportDiff` (frozen dataclass: `added: frozenset[str]`, `deleted: frozenset[str]`,
  `changed: frozenset[str]`, `modified: frozenset[str]`); `diff_actors(existing: Level, new: Level)
  -> ReimportDiff`. `changed` = matched actors whose body differs AT ALL (gets rewritten). `modified`
  = matched actors whose body differs EXCLUDING a Location/Rotation-only difference (feeds the
  blast-radius guard in Task 2). Consumed by Task 2 and Task 4.

- [ ] **Step 1: Write the failing tests**

```python
# uedcli/tests/test_reimport_ops.py
"""Pure diff/order-recompute logic for `level reimport` — no I/O, no editor. See
dev/docs/board/to-plan/level-reimport-reimport-a-hand-edited-dx-unr/spec.md."""
from __future__ import annotations

from uedcli import reimport_ops
from uedcli.model import Actor, Brush, Level


def _level(*actors: Actor) -> Level:
    return Level(actors={a.name: a for a in actors}, order=[a.name for a in actors])


def test_added_and_deleted_are_classified_by_name_membership():
    existing = _level(Actor(name="Keep", cls="Engine.Light"),
                      Actor(name="Gone", cls="Engine.Light"))
    new = _level(Actor(name="Keep", cls="Engine.Light"),
                Actor(name="New", cls="Engine.Light"))

    diff = reimport_ops.diff_actors(existing, new)

    assert diff.added == {"New"}
    assert diff.deleted == {"Gone"}


def test_a_matched_actor_with_an_identical_body_is_neither_changed_nor_modified():
    existing = _level(Actor(name="A", cls="Engine.Light", props=[("Tag", "x")]))
    new = _level(Actor(name="A", cls="Engine.Light", props=[("Tag", "x")]))

    diff = reimport_ops.diff_actors(existing, new)

    assert diff.changed == frozenset()
    assert diff.modified == frozenset()


def test_a_property_change_is_both_changed_and_modified():
    existing = _level(Actor(name="A", cls="Engine.Light", props=[("Tag", "x")]))
    new = _level(Actor(name="A", cls="Engine.Light", props=[("Tag", "y")]))

    diff = reimport_ops.diff_actors(existing, new)

    assert diff.changed == {"A"}
    assert diff.modified == {"A"}


def test_a_location_only_move_is_changed_but_not_modified():
    """An ordinary reposition must be written (it's a real edit) but must NOT count toward the
    blast-radius guard (spec 'The blast-radius guard') — the guard exists to catch a wrong-file
    reimport, and moving actors around is routine editor work."""
    existing = _level(Actor(name="A", cls="Engine.Light", location=(0, 0, 0)))
    new = _level(Actor(name="A", cls="Engine.Light", location=(50, 0, 0)))

    diff = reimport_ops.diff_actors(existing, new)

    assert diff.changed == {"A"}
    assert diff.modified == frozenset()


def test_a_rotation_only_change_is_changed_but_not_modified():
    existing = _level(Actor(name="A", cls="Engine.Light", props=[("Rotation", "(Yaw=100)")]))
    new = _level(Actor(name="A", cls="Engine.Light", props=[("Rotation", "(Yaw=999)")]))

    diff = reimport_ops.diff_actors(existing, new)

    assert diff.changed == {"A"}
    assert diff.modified == frozenset()


def test_a_class_change_on_a_matched_name_counts_as_modified():
    """A same-name reclass (e.g. changing a mover's class) is a legitimate matched-actor edit — it
    just flows through as an ordinary body diff, no special-cased guard (spec 'Rejected')."""
    existing = _level(Actor(name="A", cls="Engine.Mover"))
    new = _level(Actor(name="A", cls="Engine.Light"))

    diff = reimport_ops.diff_actors(existing, new)

    assert diff.modified == {"A"}


def test_a_brush_actor_uses_the_same_pose_blind_comparison():
    existing = _level(Actor(name="B", cls="Engine.Brush", brush=Brush(model_name="Model", polys=[])))
    new = _level(Actor(name="B", cls="Engine.Brush", brush=Brush(model_name="Model", polys=[]),
                       location=(10, 0, 0)))

    diff = reimport_ops.diff_actors(existing, new)

    assert diff.changed == {"B"}
    assert diff.modified == frozenset()      # still just a location move
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `bin/test uedcli/tests/test_reimport_ops.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'uedcli.reimport_ops'` (or `ImportError`).

- [ ] **Step 3: Implement `reimport_ops.py`**

```python
# uedcli/reimport_ops.py
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
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `bin/test uedcli/tests/test_reimport_ops.py -v`
Expected: PASS (7 tests).

- [ ] **Step 5: Commit**

```bash
git add uedcli/reimport_ops.py uedcli/tests/test_reimport_ops.py
git commit -m "Add reimport_ops.diff_actors — classify actors by name for level reimport"
```

---

### Task 2: `reimport_ops.blast_radius_exceeded` and `compute_brush_ranks`

**Files:**
- Modify: `uedcli/reimport_ops.py`
- Test: `uedcli/tests/test_reimport_ops.py`

**Interfaces:**
- Consumes: `ReimportDiff` (Task 1).
- Produces: `blast_radius_exceeded(diff: ReimportDiff, old_actor_count: int, *, threshold: float =
  0.20) -> bool`; `compute_brush_ranks(existing_ranks: dict[str, str], new_level: Level, diff:
  ReimportDiff) -> dict[str, str]` (new `order_value` for every brush that will exist after the
  reimport — matched + added; a deleted brush needs none). Both consumed by Task 4.

- [ ] **Step 1: Write the failing tests**

```python
# append to uedcli/tests/test_reimport_ops.py

def test_blast_radius_is_not_exceeded_at_exactly_the_threshold():
    diff = reimport_ops.ReimportDiff(added=frozenset(), deleted=frozenset({"D"}),
                                     changed=frozenset(), modified=frozenset({"M"}))
    assert reimport_ops.blast_radius_exceeded(diff, old_actor_count=10) is False   # 2/10 == 20%


def test_blast_radius_is_exceeded_just_over_the_threshold():
    diff = reimport_ops.ReimportDiff(added=frozenset(), deleted=frozenset({"D"}),
                                     changed=frozenset(), modified=frozenset({"M1", "M2"}))
    assert reimport_ops.blast_radius_exceeded(diff, old_actor_count=10) is True    # 3/10 == 30%


def test_pure_additions_never_trip_the_blast_radius_guard():
    diff = reimport_ops.ReimportDiff(added=frozenset({f"N{i}" for i in range(50)}),
                                     deleted=frozenset(), changed=frozenset(), modified=frozenset())
    assert reimport_ops.blast_radius_exceeded(diff, old_actor_count=2) is False


def test_blast_radius_on_an_empty_trunk_is_never_exceeded():
    diff = reimport_ops.ReimportDiff(added=frozenset(), deleted=frozenset(), changed=frozenset(),
                                     modified=frozenset())
    assert reimport_ops.blast_radius_exceeded(diff, old_actor_count=0) is False


def _brush(name: str) -> Actor:
    return Actor(name=name, cls="Engine.Brush", brush=Brush(model_name="Model", polys=[]))


def test_an_unchanged_brush_order_keeps_every_order_value():
    existing_ranks = {"B1": "m", "B2": "n", "B3": "o"}
    new = _level(_brush("B1"), _brush("B2"), _brush("B3"))
    diff = reimport_ops.ReimportDiff(added=frozenset(), deleted=frozenset(), changed=frozenset(),
                                     modified=frozenset())

    ranks = reimport_ops.compute_brush_ranks(existing_ranks, new, diff)

    assert ranks == {"B1": "m", "B2": "n", "B3": "o"}


def test_reordering_two_brushes_only_re_ranks_the_minimal_one():
    """Swapping B2/B3's relative order: the longest-increasing-subsequence diff keeps B1/B3
    (already increasing) untouched and only mints a fresh rank for B2 (spec: 'brushes only ...
    keep their existing order_value untouched; everything else ... gets freshly minted')."""
    existing_ranks = {"B1": "m", "B2": "n", "B3": "o"}
    new = _level(_brush("B1"), _brush("B3"), _brush("B2"))     # B3 now before B2
    diff = reimport_ops.ReimportDiff(added=frozenset(), deleted=frozenset(), changed=frozenset(),
                                     modified=frozenset())

    ranks = reimport_ops.compute_brush_ranks(existing_ranks, new, diff)

    assert ranks["B1"] == "m"
    assert ranks["B3"] == "o"                 # unchanged: still the longest stable run
    assert ranks["B2"] not in ("m", "n", "o")  # freshly minted
    assert ranks["B3"] < ranks["B2"]           # and lands strictly after B3, per the new order


def test_a_new_brush_inserted_between_two_unchanged_ones_gets_a_rank_between_them():
    existing_ranks = {"B1": "m", "B2": "n"}
    new = _level(_brush("B1"), _brush("B3"), _brush("B2"))     # B3 is new, inserted in the middle
    diff = reimport_ops.ReimportDiff(added=frozenset({"B3"}), deleted=frozenset(),
                                     changed=frozenset(), modified=frozenset())

    ranks = reimport_ops.compute_brush_ranks(existing_ranks, new, diff)

    assert ranks["B1"] == "m"                  # both unchanged
    assert ranks["B2"] == "n"
    assert "m" < ranks["B3"] < "n"


def test_point_actors_are_ignored_entirely():
    existing_ranks = {"B1": "m", "P1": "z"}
    new = _level(_brush("B1"), Actor(name="P1", cls="Engine.Light"))
    diff = reimport_ops.ReimportDiff(added=frozenset(), deleted=frozenset(), changed=frozenset(),
                                     modified=frozenset())

    ranks = reimport_ops.compute_brush_ranks(existing_ranks, new, diff)

    assert ranks == {"B1": "m"}                # P1 never appears — brush-only, per the spec
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `bin/test uedcli/tests/test_reimport_ops.py -v`
Expected: FAIL — `AttributeError: module 'uedcli.reimport_ops' has no attribute
'blast_radius_exceeded'` (and `compute_brush_ranks`).

- [ ] **Step 3: Implement both functions**

```python
# append to uedcli/reimport_ops.py

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
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `bin/test uedcli/tests/test_reimport_ops.py -v`
Expected: PASS (16 tests total).

- [ ] **Step 5: Commit**

```bash
git add uedcli/reimport_ops.py uedcli/tests/test_reimport_ops.py
git commit -m "Add reimport_ops.blast_radius_exceeded and compute_brush_ranks"
```

---

### Task 3: CLI parser — `level reimport MAPFILE --tree level/NAME [--force]`

**Files:**
- Modify: `uedcli/cli/parsers/level.py`
- Test: `uedcli/tests/test_cli.py`

**Interfaces:**
- Produces: an argparse namespace with `cmd="level"`, `sub="reimport"`, `mapfile`, `tree`
  (default `None`), `force` (default `False`) — consumed by Task 4's `_level_reimport(args)`.

- [ ] **Step 1: Write the failing test**

```python
# append to uedcli/tests/test_cli.py

def test_level_reimport_parses_mapfile_tree_and_force():
    ns = build_parser().parse_args(
        ["level", "reimport", "edited.dx", "--tree", "level/m03-study", "--force"])
    assert ns.cmd == "level"
    assert ns.sub == "reimport"
    assert ns.mapfile == "edited.dx"
    assert ns.tree == "level/m03-study"
    assert ns.force is True


def test_level_reimport_tree_and_force_default_when_omitted():
    ns = build_parser().parse_args(["level", "reimport", "edited.dx"])
    assert ns.tree is None
    assert ns.force is False
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `bin/test uedcli/tests/test_cli.py -k level_reimport -v`
Expected: FAIL — `argument sub: invalid choice: 'reimport'` (or similar argparse error).

- [ ] **Step 3: Add the subparser**

In `uedcli/cli/parsers/level.py`, add immediately after the existing `limport` block (after its
`--overwrite` argument, before the `lmat = lsub.add_parser("materialize", ...)` line):

```python
    lreimport = lsub.add_parser(
        "reimport",
        help="fold a hand-edited COMPILED map (.dx/.unr) back into the level trunk that produced "
             "it. Matches actors by NAME, so unrelated actors, folders/labels and CSG order are "
             "left untouched — unlike `level import --overwrite`, which replaces the whole trunk. "
             "The level must already exist; use `level import` to create one")
    lreimport.add_argument(
        "mapfile", metavar="MAPFILE",
        help="the compiled map file to reimport (.dx or .unr), relative to the current directory. "
             "A file that is missing, unreadable, or not a UE1 package errors (exit 2) naming it")
    lreimport.add_argument(
        "--force", action="store_true",
        help="proceed even if more than 20%% of the trunk's actors would be modified or deleted "
             "(default: refuse, exit 2, naming the percentage — a guard against reimporting the "
             "wrong file by mistake). Pure additions never count toward this threshold")
    _tree_flag(lreimport, level_only=True)
```

Also update the family help string at the top of `register()` (currently
`"level lifecycle verbs (create/import/list/materialize/photo/status/doctor)"`) to include
`reimport`.

- [ ] **Step 4: Run the tests to verify they pass**

Run: `bin/test uedcli/tests/test_cli.py -k level_reimport -v`
Expected: PASS (2 tests).

- [ ] **Step 5: Commit**

```bash
git add uedcli/cli/parsers/level.py uedcli/tests/test_cli.py
git commit -m "Add level reimport's CLI parser"
```

---

### Task 4: `_level_reimport` verb — wire decode, diff, guard and write together

**Files:**
- Modify: `uedcli/cli/commands/level.py`
- Test: `uedcli/tests/test_reimport_verb.py`

**Interfaces:**
- Consumes: `reimport_ops.diff_actors`/`blast_radius_exceeded`/`compute_brush_ranks` (Tasks 1-2);
  the parser fields from Task 3; `level_sources.resolve_level_only`/`announce_env_level`
  (`uedcli/cli/level_sources.py`); `mapimport.import_map`/`drop_editor_scratch`
  (`uedcli/mapimport.py`); `ingest.validate_ingest_actors` (`uedcli/cli/ingest.py`);
  `trunk.read_level`/`write_level`/`append_rank` (`uedcli/trunk.py`).
- Produces: `_level_reimport(args) -> int`, routed from `run()`.

- [ ] **Step 1: Write the failing tests**

These reuse the SAME committed fixtures `test_import_verb.py` already uses
(`uedcli/tests/fixtures/map_import_bounds/{paste,import,importadd}.dx`), and the same
`_real_index`/`_ns`/`_run`-style harness. All three fixtures decode to byte-identical content
actors (`LevelInfo0`, `ProbeRoom`, `ProbePillar` — verified while writing this plan), so a reimport
of one over a trunk built from another is a genuine no-op; the "something actually changed" cases
are covered at the `reimport_ops` level (Tasks 1-2), so this suite focuses on wiring: destination
resolution, the guard, and the write path.

```python
# uedcli/tests/test_reimport_verb.py
"""The `level reimport` verb: destination resolution, the diff/write path, and the blast-radius
guard. Mirrors `test_import_verb.py`'s harness — see that file's module docstring for why the class
package seam is patched. Spec:
dev/docs/board/to-plan/level-reimport-reimport-a-hand-edited-dx-unr/spec.md."""
from __future__ import annotations

import argparse
from pathlib import Path
from unittest import mock

import pytest

from uedcli import trunk
from uedcli.cli import dispatch
from uedcli.classindex import ClassIndex

_ROOT = Path(__file__).resolve().parent.parent.parent
_UED22 = _ROOT / "uned" / "UED22"
_FIXTURES = Path(__file__).resolve().parent / "fixtures" / "map_import_bounds"

pytestmark = pytest.mark.skipif(
    not (_UED22 / "Engine.u").is_file(),
    reason="committed UED22/Engine.u not present (the decode needs class schemas + defaults)")


def _real_index(_project=None) -> ClassIndex:
    paths = {p.stem.casefold(): str(p) for p in _UED22.glob("*.u")}
    return ClassIndex(_paths=paths, _stems={k: Path(v).stem for k, v in paths.items()})


def _import_ns(mapfile, tree, *, project) -> argparse.Namespace:
    return argparse.Namespace(cmd="level", sub="import", mapfile=str(mapfile), tree=tree,
                              overwrite=False, project=str(project), container="c")


def _reimport_ns(mapfile, tree, *, project, force=False) -> argparse.Namespace:
    return argparse.Namespace(cmd="level", sub="reimport", mapfile=str(mapfile), tree=tree,
                              force=force, project=str(project), container="c")


def _seed(project, tree="level/m03-study", fixture="paste.dx"):
    """Import a fixture into a fresh trunk so a test has an EXISTING level to reimport onto."""
    with mock.patch("uedcli.cli.resources.class_index", _real_index):
        rc = dispatch.dispatch(_import_ns(_FIXTURES / fixture, tree, project=project))
    assert rc == 0


def _reimport(mapfile, tree, *, project, force=False) -> int:
    with mock.patch("uedcli.cli.resources.class_index", _real_index):
        return dispatch.dispatch(_reimport_ns(mapfile, tree, project=project, force=force))


def test_reimporting_the_same_map_is_a_true_no_op(tmp_project):
    _seed(tmp_project)
    level_dir = tmp_project / "maps" / "m03-study"
    before_mtimes = {p: p.stat().st_mtime_ns for p in level_dir.rglob("*") if p.is_file()}

    rc = _reimport(_FIXTURES / "paste.dx", "level/m03-study", project=tmp_project)

    assert rc == 0
    after_mtimes = {p: p.stat().st_mtime_ns for p in level_dir.rglob("*") if p.is_file()}
    assert before_mtimes == after_mtimes, "an unchanged reimport must touch NO file on disk"


def test_reimporting_a_different_map_with_the_same_actor_names_is_also_a_no_op(tmp_project):
    """paste.dx/import.dx/importadd.dx decode to byte-identical content actors (differing only in
    the editor scratch objects, which are dropped) — so this is still a real no-op, exercised
    through a genuinely different source file."""
    _seed(tmp_project, fixture="paste.dx")
    level_dir = tmp_project / "maps" / "m03-study"
    before_mtimes = {p: p.stat().st_mtime_ns for p in level_dir.rglob("*") if p.is_file()}

    rc = _reimport(_FIXTURES / "import.dx", "level/m03-study", project=tmp_project)

    assert rc == 0
    after_mtimes = {p: p.stat().st_mtime_ns for p in level_dir.rglob("*") if p.is_file()}
    assert before_mtimes == after_mtimes


def test_reimport_prints_actor_names_to_stdout_and_summary_to_stderr(capsys, tmp_project):
    _seed(tmp_project)

    rc = _reimport(_FIXTURES / "paste.dx", "level/m03-study", project=tmp_project)
    cap = capsys.readouterr()

    assert rc == 0
    assert sorted(cap.out.split()) == ["LevelInfo0", "ProbePillar", "ProbeRoom"]
    assert "reimported 3 actor(s)" in cap.err
    assert "0 added, 0 deleted, 0 changed" in cap.err
    assert "reimported" not in cap.out


def test_reimport_refuses_a_level_that_does_not_exist(capsys, tmp_project):
    rc = _reimport(_FIXTURES / "paste.dx", "level/does-not-exist", project=tmp_project)
    err = capsys.readouterr().err

    assert rc == 2
    assert "level not found: 'does-not-exist'" in err


def test_reimport_preserves_folders_and_labels_on_an_untouched_actor(tmp_project):
    """The compiled map format carries neither — a matched, UNCHANGED actor's sidecar must survive
    reimport untouched (spec: 'Folder/label sidecars are left untouched')."""
    _seed(tmp_project)
    level_dir = tmp_project / "maps" / "m03-study"
    (level_dir / "actors" / "ProbeRoom" / "folder").write_text("dungeon.hall\n")

    rc = _reimport(_FIXTURES / "paste.dx", "level/m03-study", project=tmp_project)

    assert rc == 0
    level, _ranks = trunk.read_level(level_dir)
    assert level.actors["ProbeRoom"].folder == "dungeon.hall"


def test_an_actor_absent_from_the_map_is_deleted_even_if_added_after_the_last_materialize(
        tmp_project):
    """`level reimport` diffs the CURRENT on-disk trunk against the decode — it has no notion of
    "since the materialize that produced MAPFILE", only "in the map, or not". An actor added to the
    trunk by a concurrent session (or by hand) after that materialize is therefore deleted, exactly
    like `level import --overwrite` already deletes anything the fresh import doesn't mention. This
    is a known, accepted limitation (spec: the write mechanism is shared with `--overwrite`'s
    whole-trunk delete, just scoped to the real diff) — not a guarantee reimport makes. `--force`
    sidesteps the (unrelated) blast-radius guard: deleting 1 of the resulting 4 actors is 25%,
    just over the 20% threshold, and that guard is Task 2's concern, not this one's."""
    _seed(tmp_project)
    level_dir = tmp_project / "maps" / "m03-study"
    extra_dir = level_dir / "actors" / "SomeOtherActor"
    extra_dir.mkdir()
    (extra_dir / "actor.t3d").write_text("Begin Actor Class=Engine.Light\nEnd Actor")
    (extra_dir / "order_value").write_text("zz\n")

    rc = _reimport(_FIXTURES / "paste.dx", "level/m03-study", project=tmp_project, force=True)

    assert rc == 0
    level, _ranks = trunk.read_level(level_dir)
    assert "SomeOtherActor" not in level.actors


def test_the_blast_radius_guard_refuses_without_force(capsys, tmp_project):
    _seed(tmp_project)
    level_dir = tmp_project / "maps" / "m03-study"
    for n in ("Extra1", "Extra2", "Extra3", "Extra4", "Extra5", "Extra6", "Extra7"):
        d = level_dir / "actors" / n
        d.mkdir()
        (d / "actor.t3d").write_text("Begin Actor Class=Engine.Light\nEnd Actor")
        (d / "order_value").write_text(trunk.append_rank({}) + "\n")
    # Trunk now holds 3 (paste.dx) + 7 = 10 actors; reimporting paste.dx alone deletes the 7 extras
    # — 7/10 = 70%, over the 20% guard.

    rc = _reimport(_FIXTURES / "paste.dx", "level/m03-study", project=tmp_project)
    err = capsys.readouterr().err

    assert rc == 2
    assert "70%" in err

    level, _ranks = trunk.read_level(level_dir)
    assert "Extra1" in level.actors, "the guard must refuse BEFORE writing anything"


def test_force_overrides_the_blast_radius_guard(tmp_project):
    _seed(tmp_project)
    level_dir = tmp_project / "maps" / "m03-study"
    for n in ("Extra1", "Extra2", "Extra3", "Extra4", "Extra5", "Extra6", "Extra7"):
        d = level_dir / "actors" / n
        d.mkdir()
        (d / "actor.t3d").write_text("Begin Actor Class=Engine.Light\nEnd Actor")
        (d / "order_value").write_text(trunk.append_rank({}) + "\n")

    rc = _reimport(_FIXTURES / "paste.dx", "level/m03-study", project=tmp_project, force=True)

    assert rc == 0
    level, _ranks = trunk.read_level(level_dir)
    assert "Extra1" not in level.actors
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `bin/test uedcli/tests/test_reimport_verb.py -v`
Expected: FAIL — `unimplemented level sub-verb: reimport` (from `run()`'s final `raise
CommandError`), or a `CommandError`/`SystemExit` mismatch. Skips entirely if `uned/UED22/Engine.u`
is absent — check `ls uned/UED22/Engine.u` first; if it is missing, `test_import_verb.py` already
skips too, so this is a pre-existing environment gap, not something to fix here.

- [ ] **Step 3: Implement `_level_reimport` and wire it into `run()`**

In `uedcli/cli/commands/level.py`, add to `run()`, next to the existing `if args.sub == "import"`
branch:

```python
    if args.sub == "reimport":
        return _level_reimport(args)
```

Then add the function itself, placed after `_level_import` (which it deliberately mirrors for the
decode half):

```python
def _level_reimport(args) -> int:
    """`level reimport MAPFILE --tree level/NAME [--force]` — fold a hand-edited COMPILED map back
    into the EXISTING trunk that produced it, matching actors by name so unrelated actors,
    folders/labels and CSG order are left untouched.

    Unlike `level import`, the destination must already exist (`level_sources.resolve_level_only`
    — the same level-only resolver `materialize`/`photo` use, so the ambient `$UEDCLI_LEVEL` is
    the default target and a mutation from it is announced once, same as any other trunk write).

    The pipeline:
    1. Resolve the level (must exist) and decode the map file — identical to `level import`'s
       steps 2-5 (`mapimport.import_map` -> parse -> drop editor scratch -> validate).
    2. Diff the decode against the trunk's current on-disk `Level`, by actor name
       (`reimport_ops.diff_actors`).
    3. The blast-radius guard: refuse (exit 2) unless `--force` if more than 20% of the trunk's
       actors would be modified or deleted (`reimport_ops.blast_radius_exceeded`).
    4. Recompute brush `order_value`s only (`reimport_ops.compute_brush_ranks`); point actors and
       unmodified brushes keep their existing rank untouched.
    5. Write through the ordinary trunk delta path (`trunk.write_level`), touching only the actors
       that actually changed body or rank.

    See dev/docs/board/to-plan/level-reimport-reimport-a-hand-edited-dx-unr/spec.md.
    """
    from ... import reimport_ops

    project = resources.resolve_project(args)
    name, from_env = level_sources.resolve_level_only(args, verb="level reimport")
    if from_env:
        level_sources.announce_env_level(name, action="reimporting into")
    level_dir = Path(config.project_maps_dir(project)) / name

    mapfile = Path(args.mapfile)
    if not mapfile.is_file():
        raise CommandError(f"map file not found: {args.mapfile}")

    # decode — identical to `level import` steps 2-5.
    index = resources.class_index(project)
    from ... import mapimport, upackage
    try:
        pkg = upackage.load_package(str(mapfile), name=mapfile.stem)
    except SchemaError as e:
        raise CommandError(f"{args.mapfile}: {e}")
    notes: list[str] = []
    text = mapimport.import_map(pkg, index, mapimport.ImportSchema(resolver=index.resolver()),
                                notes=notes)
    ordered = parse_t3d_actors(text)
    seen: set[str] = set()
    dups = sorted({a.name for a in ordered if a.name in seen or seen.add(a.name)})
    if dups:
        raise CommandError(
            f"{args.mapfile}: {len(dups)} actor name(s) appear more than once and would collapse "
            f"into a single actor: {', '.join(dups[:10])}" + (" …" if len(dups) > 10 else ""))
    new_level = Level(actors={a.name: a for a in ordered}, order=[a.name for a in ordered])
    dropped = mapimport.drop_editor_scratch(new_level)
    ingest.validate_ingest_actors(list(new_level.actors.values()), args)

    # diff against the existing trunk.
    existing_level, existing_ranks = trunk.read_level(level_dir)
    diff = reimport_ops.diff_actors(existing_level, new_level)

    if reimport_ops.blast_radius_exceeded(diff, len(existing_level.actors)) and not args.force:
        blast = len(diff.modified) + len(diff.deleted)
        pct = 100 * blast / len(existing_level.actors)
        raise CommandError(
            f"reimport would modify/delete {blast}/{len(existing_level.actors)} actors "
            f"({pct:.0f}%, over the 20% guard) — pass --force to proceed "
            f"({len(diff.modified)} modified, {len(diff.deleted)} deleted)")

    for n in sorted(diff.modified):
        old_cls = existing_level.actors[n].cls
        new_cls = new_level.actors[n].cls
        if old_cls != new_cls:
            print(f"note: {n} changed class {old_cls} -> {new_cls}", file=sys.stderr)

    # order_value: brushes only (point actors and unmoved brushes keep their existing rank).
    brush_ranks = reimport_ops.compute_brush_ranks(existing_ranks, new_level, diff)
    ranks = dict(existing_ranks)
    ranks.update(brush_ranks)
    for n in sorted(diff.added):
        if new_level.actors[n].brush is None:          # new POINT actors: append-after-all
            ranks[n] = trunk.append_rank(ranks)

    only = diff.changed | {n for n in new_level.actors if ranks.get(n) != existing_ranks.get(n)}
    trunk.write_level(level_dir, new_level, ranks, deleted=diff.deleted, only=only)

    for n in new_level.order:
        print(n)
    print(f"reimported {len(new_level.actors)} actor(s) from {mapfile.name} into level: {name} "
          f"({len(diff.added)} added, {len(diff.deleted)} deleted, {len(diff.changed)} changed)",
          file=sys.stderr)
    if dropped:
        print(f"note: dropped {len(dropped)} editor scratch object(s) ({', '.join(dropped[:6])}"
              + (" …" if len(dropped) > 6 else "") + ")", file=sys.stderr)
    for n in notes:
        print(f"note: {n}", file=sys.stderr)
    return 0
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `bin/test uedcli/tests/test_reimport_verb.py -v`
Expected: PASS (9 tests, or all SKIPPED together if `uned/UED22/Engine.u` is absent from this
checkout — same environment gate `test_import_verb.py` uses).

- [ ] **Step 5: Run the FULL offline suite**

Run: `bin/test`
Expected: PASS, no regressions (this task only adds a new sub-verb branch; nothing existing
changes behavior).

- [ ] **Step 6: Commit**

```bash
git add uedcli/cli/commands/level.py uedcli/tests/test_reimport_verb.py
git commit -m "Add the level reimport verb"
```

---

### Task 5: Docs — `docs/usage.md`

**Files:**
- Modify: `docs/usage.md`

- [ ] **Step 1: Add a table row next to the existing `level import` row**

Find the row (search for `level import MAPFILE --tree KIND/NAME`) in the level-verb summary table
and add directly below it:

```markdown
| `level reimport MAPFILE --tree level/NAME [--force]` | fold a hand-edited COMPILED map back into the level trunk that produced it, matching actors by NAME. See [`level reimport`](#level-reimport--fold-editor-changes-back-into-the-trunk) |
```

- [ ] **Step 2: Add a full section, mirroring `# level import`'s structure**

Insert a new `# level reimport — fold editor changes back into the trunk` section directly after
the existing `# level import — read an existing map file` section (after its final "Maps built by
uedcli's own native builder..." bullet, before the next `---` separator):

```markdown
---

# `level reimport` — fold editor changes back into the trunk

**`level reimport`** is `level import`'s sibling for a level you already have in trunk: it decodes
a compiled map file the same way, but instead of creating a fresh tree it MATCHES actors by name
against the trunk you point it at, so actors it doesn't mention are left completely alone —
their body, their folder/label, and their CSG order.

Use it when you (or someone else) opened the level's materialized `.dx`/`.unr` directly in
UnrealEd — to do something uedcli can't yet express — and want those changes back in trunk without
losing history or metadata for everything you didn't touch. `level import --overwrite` also
replaces an existing level, but wholesale: every actor is rewritten fresh, folders/labels are lost,
and the diff touches the entire level regardless of how small the real edit was. `level reimport`
is the targeted alternative.

```
level reimport MAPFILE --tree level/NAME [--force]
```

- **`MAPFILE`** is the compiled map to read — same rules as `level import`.
- **`--tree level/NAME`** names the level to reimport INTO, and it must already exist (the
  opposite of `level import`'s create-only destination) — use `level import` first if it doesn't.
  Defaults to the level named by `$UEDCLI_LEVEL`, like an ordinary content verb.
- **Matching is by actor name.** An actor present in both the trunk and the map is updated in
  place; one only in the map is added; one only in the trunk is deleted — including an actor added
  to the trunk after the materialize that produced MAPFILE (by another session, or by hand):
  reimport only knows "in the map, or not", the same as `level import --overwrite`.
- **CSG order (`order_value`) is recomputed for brushes only** — point actors don't participate in
  CSG, so their order is never touched. A brush whose relative position among brushes didn't
  change keeps its exact `order_value` (no diff); a moved or newly added brush gets a freshly
  computed one.
- **`--force`** is required if the reimport would modify or delete more than 20% of the trunk's
  actors — a guard against reimporting the wrong file. Ordinary repositioning (`Location`/
  `Rotation` only) and pure additions never count toward that percentage.
- **Output:** the reimported level's actor names go to stdout, one per line; the summary (added/
  deleted/changed counts) goes to stderr.

```
export UEDCLI_LEVEL=nyc-study
level materialize --out /tmp/nyc-study.dx
# ... open /tmp/nyc-study.dx in UnrealEd, tweak something, save ...
level reimport /tmp/nyc-study.dx --tree level/nyc-study
```

Everything `level import`'s "What import leaves out" and "Requirements and caveats" sections say
about the decode itself — the dropped builder brush and viewport cameras, the strict class/texture
validation, folders and labels having no equivalent in a compiled map — applies here too.
```

- [ ] **Step 3: Verify the new section reads correctly**

Run: `grep -n "level reimport" docs/usage.md` — confirm both the table row and the section heading
are present, and that the section's internal anchor link
(`#level-reimport--fold-editor-changes-back-into-the-trunk`) matches the heading slug GitHub/most
Markdown renderers would generate (lowercase, spaces and `` ` `` become `-`, repeated `-` collapse).

- [ ] **Step 4: Commit**

```bash
git add docs/usage.md
git commit -m "Document level reimport in docs/usage.md"
```

---

## Self-Review Notes (for the executor)

- **Spec coverage:** decode reuse (Task 4 step 3, mirrors `_level_import`), name-matching add/
  delete/modify (Task 1), brush-only order recompute with LIS-based minimal churn (Task 2), the
  blast-radius guard incl. `--force` (Task 2 + Task 4), folder/label preservation for untouched
  actors (Task 4 test), round-trip fidelity (inherited by construction — verbatim body write, no
  separate task needed), docs (Task 5).
- **Not in scope** (per spec's "Open follow-on"): verifying `level import`'s decode against a real
  UCC export of a retail map — pre-existing gap, tracked on the board separately.
- If `uned/UED22/Engine.u` is absent in the build environment, Task 4's and `test_import_verb.py`'s
  tests both skip identically — this is a pre-existing fixture-availability gate, not a regression
  to chase down.
