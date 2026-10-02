# actor survey + actor relation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Rename `brush relation` to `actor relation` (broadened so a non-brush actor can be the
other side of a comparison) and add a new verb, `actor survey <name>`, that reports every raw and
CSG-resolved spatial fact about one actor.

**Architecture:** Part A moves and broadens the existing `brush relation` family (pure Python,
mostly mechanical, one genuinely new code path per subcommand for the non-brush side). Part B adds
`actor survey`'s raw tier: the spike's bounded-neighborhood selection rule plus a per-pair loop over
`actorgraph.classify_pair` — NOT `actorgraph.build_graph`, which is whole-level and is the measured
expensive half. Part C adds the one missing native primitive (a point-in-solid query on a built
model) and a single solve that returns both the surviving surfaces and a queryable solidity handle.
Part D implements the five `csg`-tier relations over that one solve. Part E wires the tiers
together, adds the truncation regression, and closes the docs fallout.

**Tech Stack:** Python 3.12 (uedcli's model/CLI layers), Rust + PyO3 (`uedcli-native`, the CSG/BSP
engine), pytest via `bin/test`.

**Spec:** `dev/docs/board/to-plan/actor-survey-and-actor-relation-csg-resolved/spec.md` — read it in
full before starting. Its supporting spike, `dev/docs/spikes/2026-09-23-actor-survey-csg-kind-and-cost/`
(`spike.md` plus `harness/`), is the source of every numeric threshold and of the two algorithms this
plan ports verbatim; read it too.

## Global Constraints

- No back-compat cruft: `brush relation` is deleted outright in the same change that adds
  `actor relation` — no alias, no deprecation shim (`CLAUDE.md`).
- Never let a Python exception reach the user: an unknown actor name, a degenerate brush, an
  unresolvable class schema (`uprops.SchemaError`) and an unbuilt native extension each exit 2 with a
  message naming the offending value, never a traceback (`CLAUDE.md`). Every such path gets a
  regression test.
- No fallbacks and no silent half-answers: a command that cannot fully satisfy a request exits 2
  naming the value, never a partial result plus a stderr warning (`CLAUDE.md`). The one stderr
  warning this plan adds (a surveyed Intersect/Deintersect brush) is explicitly allowed by the spec
  and the spike, because the answer it accompanies is complete, not partial.
- New logic defaults to Rust (`CLAUDE.md`, owner ruling 2026-09-20). Here that is exactly one thing:
  the point-in-solid query (Task 9). Everything else is orchestration over shipped parts, in Python,
  matching how `actor diagram`/`level graph` already split this boundary.
- Every command, flag and argument needs a real `help=` (`CLAUDE.md`).
- Producer/query verbs print facts to stdout one per line; human summaries and counts go to stderr
  (`CLAUDE.md`, spec "Output shape"). No `--json` on `survey` (spec: YAGNI).
- Two tolerances, never conflated:
  - raw tier: `actorgraph._TOUCH_EPS = 1e-3` (authored brush vertices) — unchanged, not referenced
    by any new code.
  - csg tier: a NEW constant `CSG_TOLERANCE = 0.015` uu — the engine's own `THRESH_POINTS_ARE_NEAR`
    (`uedcli-native/src/bspcsg.rs`), which spike.md §3 fixes as the csg tier's coincidence tolerance
    because it bounds every perturbation the bounded-neighborhood truncation can introduce (§4
    residual 2) and sits comfortably under the 0.043 uu smallest real penetration measured on
    shipped content.
- Line grammar (spec "Output shape"), identical to `actorgraph.format_text`'s real output plus a
  tier token:
  `<tier> <src>[:idx] [Package.Class Kind] --<relation>[(annotation)]--> <dst>[:idx] [Package.Class Kind]`
  `:idx` and the `touches(AREAuu^2)` annotation appear ONLY on a **raw** `touches` line that found a
  real matched face pair. No `csg` line ever carries `:idx`. Every `csg crosses` line carries a depth
  annotation, `crosses(8.2uu)`; every other `csg` line is bare.
- Tests run through `bin/test`, never bare `pytest` (`dev/docs/rules/tests.md`). Iterate scoped
  (`bin/test -k <name>`); run the whole suite once before the final commit of each task.
- Work happens in a feature worktree and is squash-merged from the main checkout
  (`dev/docs/rules/worktrees.md`). Never push the feature branch.

## Verified-facts table

Every fact this plan's code depends on, with where it was read. An implementer who doubts a line
should re-read the cited place, not guess.

| Fact | Where |
|---|---|
| `CollisionModel::point_check` returns true when the box is in **free** space (so it is NOT a solidity predicate) | `uedcli-native/src/collision.rs:236` and its own doc comment |
| `CollisionModel::level(m)` deep-clones the node/hull arrays | `uedcli-native/src/collision.rs:102-104` |
| `is_csg` / `child` / `combine_state` / `plane_dot` / `FRONT` / `BACK` are already imported into `collision.rs` | `uedcli-native/src/collision.rs:18` |
| `Built` is `#[pyclass] struct Built { model: model::Model }` with `#[pymethods]` giving counts + `world_soup()` | `uedcli-native/src/lib.rs:56-101` |
| `build_geometry_bspcsg` runs `passes::bsp_build_bounds`, so `leaf_hulls`/`i_collision_bound` are populated | `uedcli-native/src/bspcsg.rs:3231` (fn start) and `:3706` |
| `solve_world_surfaces` returns `SolvedWorld(world_surfaces, mover_polys)` and discards the native `Built` handle | `uedcli/preview_native.py:1139-1189` |
| `SolvedSurface(actor, poly_index, world_verts, poly_flags)`; `actor`/`poly_index` are None for a BSP node with no source poly | `uedcli/preview_native.py:1115-1128` |
| `actorgraph.classify_pair(name_a, actor_a, name_b, actor_b, *, order_index, class_index, cache)` | `uedcli/actorgraph.py:562` |
| `actorgraph.decompose_convex(actor, *, cache=None)`, `point_in_brush(actor, point, *, cache=None)`, `ConvexCell(vertices, half_spaces)` | `uedcli/actorgraph.py:216, 540, 62` |
| `actorgraph.build_graph` is whole-level `O(brushes^2)` — the measured expensive half | `uedcli/actorgraph.py:648`; spike.md §4 |
| `relation._point_on_segment(p, s0, s1)` already exists, in that argument order | `uedcli/relation.py:165` |
| `relation.compute_deltas` and `_edge_extent` work on a one-point "poly" (`_poly_centroid_2d` falls back to the vertex average at zero area; `min`/`max` of a 1-element list is that element) | `uedcli/relation.py:263, 618`; `uedcli/preview.py:410-424` |
| `serve/scene.py::_actor_radii`'s `field()`/`field_or()` split (and why `field(name) or default` is a bug) | `uedcli/serve/scene.py:413-458` |
| `actor/routes.py` is `def run(args) -> int`, dispatching on `args.sub` with per-branch imports; there is no `ctx` object anywhere | `uedcli/cli/commands/actor/routes.py:28-55` |
| Every feature module resolves its own source: `level_sources.resolve_level_source(args)` (which reads `getattr(args, "tree", None)`, so a missing `--tree` is tolerated) | `uedcli/cli/commands/actor/preview.py:33`; `uedcli/cli/level_sources.py:234` |
| The class-index + class-defaults pair is built as `index = resources.class_index(project)` / `ClassDefaults(resources.schema_resolver_for(project))`; `level graph` uses `resources.mover_index(args, verb)` for the mover-aware index | `uedcli/cli/commands/level.py:563-571, 807` |
| `ClassDefaults` lives in `uedcli.classdefaults`, constructor takes a schema-path resolver callable | `uedcli/classdefaults.py:112-137` |
| The native extension is imported through `from uedcli.native_ext import import_native` (raises `NativeExtensionStaleError`, an `ImportError` subclass) | `uedcli/native_ext.py:33-45` |
| The CLI test convention is a hand-built `argparse.Namespace` + `dispatch.dispatch(ns)` + `capsys`; argparse is never invoked | `uedcli/tests/test_cli_brush_relation_measure.py:30-46` |
| `conftest._stub_mover_class_index` is **autouse**: `resources.mover_index` returns a `StubClassIndex()` in every test unless marked `real_mover_index` | `uedcli/tests/conftest.py:259-270` |
| The CSG-kind facts are already pinned, with exact geometry, by `uedcli/tests/test_csg_kind_facts.py` (Room 1024³ Subtract, Pillar 128×128×512, Cutter 256³ at (128,0,0)) and its own `point_is_solid` Python walk | `uedcli/tests/test_csg_kind_facts.py` |
| The spike's neighborhood pad is `PAD = 1.0` uu, converted with `Decimal(str(pad))` because `actor_bounds` returns Decimals | `dev/docs/spikes/2026-09-23-actor-survey-csg-kind-and-cost/harness/bounded_cost.py:35, 195-202` |
| The spike's bisection is `signed_clearance(model, is_solid, loc, ext, *, hi=64.0, iters=18)` over a 27-point box sample, with a `buried` saturation case excluded from every percentile by `_stats` | `dev/docs/.../harness/collision_clearance.py:40-68, 194-212` |
| `kind_semantics.py`'s public surface is `_actor(...)`, `_solve(...)`, `scenario(kind) -> dict` — there is no `build_fixture`, and it `import corpus` (a sibling on `sys.path`), so it cannot be imported from the repo root | `dev/docs/.../harness/kind_semantics.py` |
| `_csg_oper` reads the FIRST `CsgOper` prop; `preview_native._csg_oper_or_skip` reads `dict(actor.props)` (LAST wins) — so a fixture must never carry two `CsgOper` entries | `uedcli/query.py:296-302`; `uedcli/preview_native.py:102-109, 1161` |
| `make_brush_actor(name, brush, location=…, csg="add"\|"subtract", poly_flags=…, mover_class=…)`; `CSG_OPER` has only add/subtract | `uedcli/builders.py:724-749, 55` |
| Four CLI/unit test files cover the relation family today: `test_cli_brush_relation_find.py`, `test_cli_brush_relation_measure.py`, `test_cli_brush_relation_set.py`, `test_relation.py` | `uedcli/tests/` |
| `uedcli/tests/fixtures/parser_baseline/{help,action_tree,argv_corpus,import_closure}.json` pin the live parser and MUST be regenerated by any parser change (`python -m uedcli.tests.parser_baseline`) | `uedcli/tests/test_parser_baseline.py:1-30` |

### Fresh greps (do not trust a cached count)

Run 2026-09-23 on this worktree:

- `uedcli/relation.py`: **18** `raise RelationError(` sites (plus the class definition at line 279).
  Of those, **4** hard-code the verb name in a user-visible message: lines **476, 641, 647, 653**.
  Section-divider comments and docstrings naming `brush relation` are at lines 1, 431, 456, 502, 555,
  594, 621, 632.
- `uedcli/cli/commands/brush/relation.py`: **3** user-visible hard-codings — line **19** (a
  `CommandError`), lines **70** and **146** (stderr prints). The spec's note says two; it missed
  line 19.
- `uedcli/actorgraph.py`: 3 docstring/comment references (lines **573, 753, 764**).
- Files containing the string `brush relation` at all:
  `docs/leveldesign/general/recipes/shapes/mitered-corner.md`, `docs/reference/brush/README.md`,
  `docs/reference/brush/poly.md`, `docs/reference/brush/relation.md`,
  `docs/reference/level/graph.md`, `plugins/uedcli/HANDOFF.md`,
  `plugins/uedcli/references/brush-relation-basics.md`,
  `plugins/uedcli/skills/positioning-a-brush/SKILL.md`,
  `plugins/uedcli/skills/verifying-brush-relations/SKILL.md`, `uedcli/actorgraph.py`,
  `uedcli/cli/commands/brush/relation.py`, `uedcli/cli/parsers/brush.py`, `uedcli/relation.py`,
  `uedcli/tests/fixtures/parser_baseline/action_tree.json`,
  `uedcli/tests/fixtures/parser_baseline/help.json`.

Re-run each grep at the start of the task that consumes it — earlier tasks shift line numbers.

---

## Part A — `actor relation` (moved and broadened from `brush relation`)

### Task 1: Rename the `measure` subcommand to `compare`

**Files:**
- Modify: `uedcli/cli/parsers/brush.py:684-711` (the `rmeasure` block)
- Modify: `uedcli/cli/parsers/brush.py:761` (`find --json`'s help string, which names
  `brush relation measure REF -`)
- Modify: `uedcli/cli/commands/brush/relation.py:12-19` (the dispatch branch)
- Modify: `uedcli/relation.py` (the `measure` wording in the module docstring, the section divider at
  line 431, `compute_pairs`'s docstring at 456, and the `RelationError` at 476)
- Modify: `uedcli/tests/test_cli_brush_relation_measure.py` (its `_ns` helper sets
  `relationsub="measure"`)
- Modify: `uedcli/tests/fixtures/parser_baseline/{help,action_tree,argv_corpus,import_closure}.json` (regenerated,
  never hand-edited)
- Test: `uedcli/tests/test_cli_brush_relation_measure.py`

**Interfaces:**
- Consumes: nothing new.
- Produces: `args.relationsub == "compare"` is the only spelling. `measure` no longer parses.

- [ ] **Step 1: Re-grep every reference**

```bash
grep -rn "relationsub\|\"measure\"\|'measure'\|relation measure\|rmeasure" \
  uedcli/ docs/ plugins/ --include='*.py' --include='*.md' --include='*.json'
```

Read every hit before editing. Do not proceed until the list is complete.

- [ ] **Step 2: Write the failing test**

Append to `uedcli/tests/test_cli_brush_relation_measure.py`. This uses the file's own real
`_brush`/`_project`/`_ns` helpers — read the top of the file first.

```python
def test_compare_is_the_only_spelling(tmp_path, monkeypatch, capsys):
    """`compare` does measure's job; `measure` is gone outright, no alias."""
    actors = [
        _brush("LegFoot", cube(16, 16, 4), loc=(0, 0, 4)),
        _brush("FloorPad", cube(200, 200, 8), loc=(0, 0, -8)),
    ]
    proj = _project(tmp_path, monkeypatch, actors)
    ns = _ns(proj, "LegFoot", "FloorPad")
    ns.relationsub = "compare"
    assert dispatch.dispatch(ns) == 0
    assert "LegFoot <-> FloorPad" in capsys.readouterr().out

    stale = _ns(proj, "LegFoot", "FloorPad")
    stale.relationsub = "measure"
    with pytest.raises(CommandError):
        dispatch.dispatch(stale)
```

Add `import pytest` and `from uedcli.cli.errors import CommandError` to the file's imports if absent.

The second half asserts against the REAL removal mechanism: `relation.run` raises
`CommandError(f"unimplemented brush relation sub-verb: …")` for an unknown `relationsub`
(`uedcli/cli/commands/brush/relation.py:19`). Whether `dispatch.dispatch` converts that to exit 2 or
lets it propagate is a fact to check in Step 3 — if it returns 2 instead of raising, change this half
to `assert dispatch.dispatch(stale) == 2`. Do not leave both spellings "passing".

- [ ] **Step 3: Run the test to verify it fails**

Run: `bin/test -k test_compare_is_the_only_spelling -v`
Expected: FAIL — `relationsub="compare"` falls through to the `CommandError` and `"measure"` succeeds,
the exact inverse of what the test asserts.

- [ ] **Step 4: Rename the subparser**

In `uedcli/cli/parsers/brush.py`, rename the local `rmeasure` to `rcompare` and its parser name from
`"measure"` to `"compare"`, keeping every `help=`/`epilog=` string as-is:

```python
    rcompare = rsub.add_parser(
        "compare",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        help="report the exact geometric relationship between a reference face selector and one "
             "or more target selectors (plane, normals, distance, footprint_2d overlap, deltas)",
        epilog=_FOOTPRINT_EPILOG,
    )
```

Rename all four `rmeasure.add_argument(...)` calls (`ref`, `target`, `--top`, `--allow-self`) to
`rcompare.add_argument(...)`. Update the `relation` parser's own help at line 670 from
`"cross-brush geometric relationships: measure/find/set"` to `"…: compare/find/set"`, and `find
--json`'s help at line 761 from `brush relation measure REF -` to `brush relation compare REF -`
(it becomes `actor relation compare REF -` in Task 2; do the `measure`→`compare` half now so each
task's diff stays one rename).

- [ ] **Step 5: Rename the dispatch branch and the handler**

In `uedcli/cli/commands/brush/relation.py`, change `if args.relationsub == "measure": return
_measure(args, src)` to `if args.relationsub == "compare": return _compare(args, src)`, and rename
`def _measure(args, src)` to `def _compare(args, src)`.

- [ ] **Step 6: Update `uedcli/relation.py`'s wording**

Module docstring line 1, the section divider at line 431, `compute_pairs`'s docstring at line 456,
and the `RelationError` message at line 476: `brush relation measure` → `brush relation compare`.
Leave `brush`→`actor` alone; Task 3 does that sweep.

- [ ] **Step 7: Update the existing test file's own `measure` literals**

`uedcli/tests/test_cli_brush_relation_measure.py`'s `_ns` helper sets `relationsub="measure"` —
change it to `"compare"`. Re-grep the other three relation test files for `"measure"` and fix any
hit.

- [ ] **Step 8: Regenerate the parser baseline**

Run: `.venv/bin/python -m uedcli.tests.parser_baseline`

`.venv/bin/python` does not exist in a fresh worktree until `bin/test` has run once, which builds
the venv; the module's own docstring spells the invocation `python -m uedcli.tests.parser_baseline`.
This applies to every `.venv/bin/python` command in this plan.

This rewrites all FOUR fixtures —
`uedcli/tests/fixtures/parser_baseline/{help,action_tree,argv_corpus,import_closure}.json`. Never
hand-edit them. Then `git diff` those files and confirm the only changes in the three parser
fixtures are `measure`→`compare` in the relation subtree — anything else means the rename touched
more than intended. `import_closure.json` records the import graph rather than the parser, so a diff
there is NOT a failure; check it matches the modules this task actually edited.

- [ ] **Step 9: Run the tests**

Run: `bin/test -k test_compare_is_the_only_spelling -v`
Expected: PASS

Run: `bin/test -k "relation or parser_baseline"`
Expected: all green.

- [ ] **Step 10: Run the whole suite, then commit**

Run: `bin/test`

```bash
git add uedcli/cli/parsers/brush.py uedcli/cli/commands/brush/relation.py uedcli/relation.py
git add uedcli/tests/test_cli_brush_relation_measure.py
git add uedcli/tests/fixtures/parser_baseline/
git commit -m "brush relation: rename measure to compare"
```

---

### Task 2: Move the relation family from `brush` to `actor`

Parser, handler and routing only. The docs/plugin/error-string sweep is Task 3; the non-brush
broadening is Tasks 4-6.

**Files:**
- Create: `uedcli/cli/parsers/actor_relation.py` (the whole `relation` subparser, moved out of
  `brush.py`)
- Modify: `uedcli/cli/parsers/brush.py` (delete lines 649-799 (to EOF): `_top_arg`, `_parse_footprint_list`,
  the `relation` block, `_FOOTPRINT_EPILOG`, and the `rcompare`/`rfind`/`rset` bodies — re-grep for
  the real range, Task 1 shifted nothing but confirm)
- Modify: `uedcli/cli/parsers/actor.py` (wire the new subparser in)
- Modify: `uedcli/cli/commands/brush/routes.py:47-48` (delete the `relation` branch)
- Modify: `uedcli/cli/commands/actor/routes.py` (add a `relation` branch)
- Create: `uedcli/cli/commands/actor/relation.py` (`git mv` from `uedcli/cli/commands/brush/relation.py`)
- Modify: `uedcli/tests/fixtures/parser_baseline/*.json` (regenerated)
- Test: `git mv` the three CLI test files to `test_cli_actor_relation_{find,compare,set}.py`; add one
  new test below

**Interfaces:**
- Consumes: `uedcli/relation.py`'s public functions unchanged (`compute_pairs`, `find_candidates`,
  `compute_set_translation`, `_resolve_measure_selector`, …) — this task moves plumbing only.
- Produces:
  - `uedcli/cli/parsers/actor_relation.py::add_relation_subparser(asub) -> None`
  - `uedcli/cli/commands/actor/relation.py::run(args) -> int` — note the **new** signature: the
    brush family's route resolved the source and passed it in (`run(args, src)`), the actor family's
    does not (`actor/routes.py` calls `module.run(args)` and each module resolves its own source,
    exactly as `actor/preview.py:33` does).
  - `actor relation compare|find|set` parse and work. `brush relation` does not parse at all
    (argparse's own `invalid choice` → exit 2).

- [ ] **Step 1: Re-read the two route files in full**

`uedcli/cli/commands/brush/routes.py` and `uedcli/cli/commands/actor/routes.py`. Note that the actor
route runs `_apply_source_free_guards(args)` before every non-`build` subverb, and that the guard
function switches on `args.sub` against a fixed set that does not include `relation` — so it is a
no-op for this verb and needs no change.

- [ ] **Step 2: Write the failing test**

New file `uedcli/tests/test_cli_actor_relation_move.py`:

```python
"""The relation family hangs off `actor`, not `brush` — and `brush relation` is gone outright."""
import argparse
from decimal import Decimal

import pytest

from uedcli import trunk
from uedcli.builders import cube, make_brush_actor
from uedcli.cli import dispatch
from uedcli.cli.main import build_parser
from uedcli.model import Level


def _project(tmp_path, monkeypatch, actors, name="lvl"):
    proj = tmp_path / "repo"
    (proj / "maps" / name).mkdir(parents=True)
    (proj / "uedcli.toml").write_text('game = "deusex"\n')
    lvl = Level(actors={a.name: a for a in actors})
    trunk.write_level(proj / "maps" / name, lvl,
                      {a.name: f"{i:04d}" for i, a in enumerate(actors)})
    monkeypatch.setenv("UEDCLI_LEVEL", name)
    return proj


def _pair():
    return [make_brush_actor("LegFoot", cube(16, 16, 4),
                             location=tuple(Decimal(str(c)) for c in (0, 0, 4))),
            make_brush_actor("FloorPad", cube(200, 200, 8),
                             location=tuple(Decimal(str(c)) for c in (0, 0, -8)))]


def test_actor_relation_compare_runs(tmp_path, monkeypatch, capsys):
    proj = _project(tmp_path, monkeypatch, _pair())
    ns = argparse.Namespace(cmd="actor", sub="relation", relationsub="compare",
                            project=str(proj), tree=None, ref="LegFoot",
                            target=["FloorPad"], top=1, allow_self=False)
    assert dispatch.dispatch(ns) == 0
    assert "LegFoot <-> FloorPad" in capsys.readouterr().out


def test_brush_relation_no_longer_parses():
    """argparse itself refuses the removed subcommand (SystemExit 2), no alias, no custom message."""
    with pytest.raises(SystemExit) as e:
        build_parser().parse_args(["brush", "relation", "compare", "A", "B"])
    assert e.value.code == 2
```

- [ ] **Step 3: Run the tests to verify they fail**

Run: `bin/test -k "test_actor_relation_compare_runs or test_brush_relation_no_longer_parses" -v`
Expected: the first FAILS (`actor relation` does not exist), the second FAILS (`brush relation` still
parses).

- [ ] **Step 4: Create the new parser module**

Cut lines 649-799 (to EOF) of `uedcli/cli/parsers/brush.py` — the file is 799 lines and the relation
block runs from 649 to the end, so this is a tail cut, not a mid-file excision. That is `_top_arg`,
`_parse_footprint_list`, the
`relation = bsub.add_parser(...)` call, `_FOOTPRINT_EPILOG`, and the full `rcompare`/`rfind`/`rset`
bodies. All four names are used ONLY by the relation block (verified: `_top_arg` at 649/703/746,
`_parse_footprint_list` at 660/739, `_FOOTPRINT_EPILOG` at 673/689/717 — every consumer is inside the
block). Re-run `grep -n "_top_arg\|_parse_footprint_list\|_FOOTPRINT_EPILOG" uedcli/cli/parsers/brush.py`
after the cut and confirm zero hits remain.

New file `uedcli/cli/parsers/actor_relation.py`:

```python
"""`actor relation` subparser: compare/find/set — the pairwise/scanning geometric-relation toolkit.
Moved wholesale out of `brush.py` when the family moved from `brush` to `actor`; the three helpers
below (`_top_arg`, `_parse_footprint_list`, `_FOOTPRINT_EPILOG`) came with it because nothing else in
`brush.py` used them."""
from __future__ import annotations

import argparse


def add_relation_subparser(asub) -> None:
    """Wire `relation` (compare/find/set) under the `actor` command's subparsers object `asub`."""
    # <paste lines 649-799 (to EOF) of brush.py here VERBATIM, re-indented by nothing (they are already at
    # one function-body level), with the single edit `bsub.add_parser` -> `asub.add_parser` on the
    # `relation = ...` line. Change no help text in this task — Task 3 does the `brush`->`actor`
    # wording sweep, so this task's diff stays a pure move that `git diff -M` can recognise.>
```

- [ ] **Step 5: Wire it into the actor parser**

In `uedcli/cli/parsers/actor.py`, after `asub = actor.add_subparsers(dest="sub", required=True)`
(line 18), add the import at the top of the file and the call:

```python
from .actor_relation import add_relation_subparser
```

```python
    add_relation_subparser(asub)
```

Place the call at the END of `register()` so the subcommand ordering in `--help` stays stable and the
parser-baseline diff is a clean append.

- [ ] **Step 6: Move the handler and change its signature**

```bash
git mv uedcli/cli/commands/brush/relation.py uedcli/cli/commands/actor/relation.py
```

Change its `run` from the brush family's `(args, src)` shape to the actor family's `(args)` shape,
resolving the source itself (this is the pattern `uedcli/cli/commands/actor/preview.py:33` uses):

```python
from ... import level_sources


def run(args) -> int:
    src = level_sources.resolve_level_source(args)
    if args.relationsub == "compare":
        return _compare(args, src)
    if args.relationsub == "find":
        return _find(args, src)
    if args.relationsub == "set":
        return _set(args, src)
    raise CommandError(f"unimplemented brush relation sub-verb: {args.relationsub}")
```

`_compare`/`_find`/`_set` keep their `(args, src)` signatures unchanged. The `CommandError` string
still says `brush relation` — Task 3 fixes it, with the rest of the sweep.

- [ ] **Step 7: Delete the brush route branch, add the actor one**

In `uedcli/cli/commands/brush/routes.py`, delete lines 47-48:

```python
    elif sub == "relation":
        from . import relation as feature
```

In `uedcli/cli/commands/actor/routes.py`, add a branch after the `diagram` one (order does not
matter functionally; this keeps read-only verbs together):

```python
    if args.sub == "relation":
        from . import relation
        return relation.run(args)
```

- [ ] **Step 8: Rename the test files**

```bash
git mv uedcli/tests/test_cli_brush_relation_find.py    uedcli/tests/test_cli_actor_relation_find.py
git mv uedcli/tests/test_cli_brush_relation_measure.py uedcli/tests/test_cli_actor_relation_compare.py
git mv uedcli/tests/test_cli_brush_relation_set.py     uedcli/tests/test_cli_actor_relation_set.py
```

In each, change every `argparse.Namespace(cmd="brush", …)` to `cmd="actor"`. Re-grep the three files
plus `uedcli/tests/test_relation.py` for `cmd="brush"` and `"brush", "relation"` and fix every hit.

- [ ] **Step 9: Regenerate the parser baseline**

Run: `.venv/bin/python -m uedcli.tests.parser_baseline`
Then `git diff uedcli/tests/fixtures/parser_baseline/` and confirm the change is exactly: the
`relation` subtree gone from `brush`, present under `actor`.

- [ ] **Step 10: Run the tests**

Run: `bin/test -k "test_actor_relation_compare_runs or test_brush_relation_no_longer_parses" -v`
Expected: PASS

Run: `bin/test -k "relation or parser_baseline or routes or dispatch"`
Expected: all green.

- [ ] **Step 11: Run the whole suite, then commit**

Run: `bin/test`

```bash
git add uedcli/cli/parsers/actor_relation.py uedcli/cli/parsers/actor.py uedcli/cli/parsers/brush.py
git add uedcli/cli/commands/actor/relation.py uedcli/cli/commands/actor/routes.py
git add uedcli/cli/commands/brush/routes.py
git add uedcli/tests/test_cli_actor_relation_find.py uedcli/tests/test_cli_actor_relation_compare.py
git add uedcli/tests/test_cli_actor_relation_set.py uedcli/tests/test_cli_actor_relation_move.py
git add uedcli/tests/test_relation.py uedcli/tests/fixtures/parser_baseline/
git commit -m "relation: move the family from brush to actor"
```

---

### Task 3: Sweep the old verb name out of messages, docstrings, docs and plugin skills

Mechanical wording only — no behavior change. The one non-mechanical doc edit (the plugin skill's
"Known limitation", which Tasks 4-6 actually remove) is deliberately NOT here: it lands in Task 6,
after the limitation is gone.

**Files:**
- Modify: `uedcli/relation.py` (lines 1, 431, 456, 476, 502, 555, 594, 621, 632, 641, 647, 653 —
  re-grep)
- Modify: `uedcli/cli/commands/actor/relation.py` (lines 1-3, 19, 70, 146 — re-grep)
- Modify: `uedcli/actorgraph.py` (lines 573, 753, 764 — docstrings only)
- Modify: `uedcli/cli/parsers/actor_relation.py` (the `find --json` help string's
  `brush relation compare REF -`)
- Modify: `docs/reference/brush/README.md`, `docs/reference/brush/poly.md`,
  `docs/reference/level/graph.md`, `docs/leveldesign/general/recipes/shapes/mitered-corner.md`
- Modify: `plugins/uedcli/HANDOFF.md`, `plugins/uedcli/references/brush-relation-basics.md`,
  `plugins/uedcli/skills/positioning-a-brush/SKILL.md`,
  `plugins/uedcli/skills/verifying-brush-relations/SKILL.md`
- Modify: `uedcli/tests/fixtures/parser_baseline/*.json` (regenerated — the help strings changed)
- Test: `uedcli/tests/test_cli_actor_relation_move.py` (one new assertion)

**Interfaces:** none — strings only.

- [ ] **Step 1: Re-grep**

```bash
grep -rn "brush relation" uedcli/ docs/ plugins/ | grep -v parser_baseline
```

- [ ] **Step 2: Write the failing test**

Append to `uedcli/tests/test_cli_actor_relation_move.py`:

```python
def test_no_source_or_doc_still_says_brush_relation():
    """The old verb name is gone from every user-visible string and every shipped doc. The parser
    baseline fixtures are excluded: they are regenerated from the parser, not authored."""
    import subprocess
    out = subprocess.run(
        ["grep", "-rn", "brush relation", "uedcli", "docs", "plugins"],
        capture_output=True, text=True).stdout
    hits = [ln for ln in out.splitlines() if "parser_baseline" not in ln]
    assert hits == [], "\n".join(hits)
```

Run this from the repo root (pytest's rootdir). If the suite runs from elsewhere, replace the
relative paths with ones derived from `Path(__file__).resolve().parents[2]`.

- [ ] **Step 3: Run the test to verify it fails**

Run: `bin/test -k test_no_source_or_doc_still_says_brush_relation -v`
Expected: FAIL, listing every remaining hit.

- [ ] **Step 4: Fix the Python strings**

In `uedcli/relation.py`, `uedcli/cli/commands/actor/relation.py`, `uedcli/actorgraph.py` and
`uedcli/cli/parsers/actor_relation.py`: replace `brush relation` with `actor relation` everywhere.
The four user-visible `RelationError` messages and the three in the handler are the ones that matter;
the docstrings and section dividers go with them.

- [ ] **Step 5: Fix the user docs**

`docs/reference/brush/relation.md` is MOVED in Task 20 (the docs task), not here — leave it alone for
now except for the `measure`→`compare` wording, which Task 1 already did. In the four other docs,
replace `brush relation` with `actor relation` and repoint any link to `relation.md` at
`../actor/relation.md`… **except** that the page does not exist yet, which would break
`test_doc_links`. So in this task, for the four cross-referencing docs, change only the COMMAND TEXT
(`brush relation` → `actor relation`) and leave every markdown LINK target pointing at
`docs/reference/brush/relation.md`. Task 20 moves the page and retargets the links in the same
commit.

- [ ] **Step 6: Fix the plugin skills**

`plugins/uedcli/HANDOFF.md`, `plugins/uedcli/references/brush-relation-basics.md`,
`plugins/uedcli/skills/positioning-a-brush/SKILL.md`,
`plugins/uedcli/skills/verifying-brush-relations/SKILL.md`: replace `brush relation` with
`actor relation`. Do NOT touch `verifying-brush-relations/SKILL.md`'s "Known limitation" section
beyond that literal replacement — Task 6 rewrites it, once the limitation is actually gone. Leave the
skill directory names and file names as they are; renaming a shipped skill is a separate decision and
nothing in the spec asks for it.

- [ ] **Step 7: Regenerate the parser baseline**

Run: `.venv/bin/python -m uedcli.tests.parser_baseline`

- [ ] **Step 8: Run the tests**

Run: `bin/test -k "test_no_source_or_doc_still_says_brush_relation or relation or doc_links or docs_command or parser_baseline"`
Expected: all green. If `test_doc_links` or `test_the_real_docs_tree_has_no_dead_links` goes red, a
link was retargeted at a page that does not exist yet — undo that retarget (Step 5's rule) rather
than creating the page early.

- [ ] **Step 9: Run the whole suite, then commit**

Run: `bin/test`

```bash
git add uedcli/relation.py uedcli/actorgraph.py uedcli/cli/commands/actor/relation.py
git add uedcli/cli/parsers/actor_relation.py docs/ plugins/
git add uedcli/tests/test_cli_actor_relation_move.py uedcli/tests/fixtures/parser_baseline/
git commit -m "relation: say actor relation everywhere the old verb name was hard-coded"
```

---

### Task 4: `find` — accept a non-brush candidate

**Files:**
- Modify: `uedcli/relation.py` (new `PointPair` type, `point_footprint_2d`, `point_pairs_between`,
  `find_point_candidates`)
- Modify: `uedcli/cli/commands/actor/relation.py` (`_find`: stop skipping, split the candidate list,
  merge the two result streams)
- Test: `uedcli/tests/test_cli_actor_relation_find.py`, `uedcli/tests/test_relation.py`

**Interfaces:**
- Consumes: `relation._plane_basis`, `project_to_plane`, `polyalign._world_normal`,
  `polyalign._world_verts`, `_point_on_segment(p, s0, s1)` (line 165 — call it, do NOT redefine it),
  `_edges`, `_footprint_bbox_gap`, `_TOUCH_EPS`, `_GAP_EPS` — all existing, unchanged.
- Produces:

```python
@dataclass(frozen=True)
class PointPair:
    brush_a: str            # REF's brush name
    poly_a: int             # REF's poly index
    actor_b: str            # the non-brush actor's name (never has a poly index)
    distance: float         # signed perpendicular distance from REF's plane to the Location
    point_footprint: str    # "inside" | "on_boundary" | "outside"
    centroid_u: float       # the point's own U in REF's frame
    centroid_v: float
    footprint_gap: float    # in-plane bbox gap; 0 unless point_footprint == "outside"

def point_footprint_2d(ref_uv: list[Vec2], point_uv: Vec2) -> str
def point_pairs_between(ref_actor, ref_idxs: set, point_actor) -> list[PointPair]
def find_point_candidates(level, ref_token: str, point_names: list[str], *,
                          max_gap=None, min_gap=None, footprint=None, plane=None) -> list[PointPair]
```

  `find_point_candidates` takes no `top`: a point candidate yields at most ONE row (see Step 1).

- [ ] **Step 1: One row per point candidate, whatever `--top` says**

`--top`'s own help says it caps "qualifying pairs PER CANDIDATE" — a cap whose purpose is to
distinguish candidate FACES. A point candidate has one position and prints a bare name with no
`:idx`, so `--top 3` against a bare `REF` would print the same name three times, three identical
stdout lines. The spec does not rule on this. The project owner decided it directly, in
conversation: one row per point candidate, regardless of `--top` — it is the only shape that keeps
`find`'s "one selector per line" stdout contract coherent. There is no written record of that
answer anywhere in the repo; this paragraph is it.
Alternatives not taken: repeat the bare name N times; or print `Name` once plus the matched ref poly
as a second column (a new output shape). Implement it as this task's behavior and pin it with the
test in Step 2.

- [ ] **Step 2: Write the failing tests**

Append to `uedcli/tests/test_relation.py` (unit level — read its existing helpers first and reuse
them; it already builds `Level`s of brush actors):

```python
def test_point_footprint_2d_classifies_inside_boundary_outside():
    """A real point-in-polygon test. NOT `classify_footprint_2d`: fed a one-vertex 'polygon' that
    function's `_clip_2d` degenerates to an always-true inside() test and returns
    `contains_a_in_b` for every input, including a point 900uu away (spec, verified by hand)."""
    from uedcli.relation import point_footprint_2d
    square = [(0.0, 0.0), (10.0, 0.0), (10.0, 10.0), (0.0, 10.0)]
    assert point_footprint_2d(square, (5.0, 5.0)) == "inside"
    assert point_footprint_2d(square, (0.0, 5.0)) == "on_boundary"
    assert point_footprint_2d(square, (900.0, 5.0)) == "outside"


def test_point_footprint_2d_reuses_the_existing_point_on_segment_helper():
    """Boundary detection calls `_point_on_segment(p, s0, s1)` (relation.py:165, that argument
    order) rather than carrying a second copy of the tolerance logic."""
    import inspect
    from uedcli import relation
    assert "_point_on_segment" in inspect.getsource(relation._point_on_any_edge)
```

Append to `uedcli/tests/test_cli_actor_relation_find.py` (CLI level — reuse that file's own
`_project`/`_ns` helpers; read them first, and extend `_ns` with whatever fields it does not already
carry rather than writing a second one):

```python
def _light(name, loc):
    """A non-brush point actor at `loc`. No collision props: `find` ranks on Location alone."""
    from uedcli.model import Actor
    return Actor(name=name, cls="Engine.Light",
                 location=tuple(Decimal(str(c)) for c in loc))


def test_find_accepts_an_explicitly_named_point_candidate(tmp_path, monkeypatch, capsys):
    actors = [make_brush_actor("Wall", cube(200, 8, 200),
                               location=tuple(Decimal(str(c)) for c in (0, 0, 0))),
              _light("MyLight", (0, 20, 0))]
    proj = _project(tmp_path, monkeypatch, actors)
    ns = _ns(proj, candidates=["MyLight"], relative_to="Wall", max_gap=40.0)
    assert dispatch.dispatch(ns) == 0
    out = capsys.readouterr()
    assert "MyLight" in out.out
    assert "MyLight:" not in out.out          # a point candidate never gets a :idx
    assert "skipping non-brush actor" not in out.err


def test_find_default_candidate_set_stays_brush_only(tmp_path, monkeypatch, capsys):
    """Omitting candidates scans brushes only — unchanged, per the spec's explicit carve-out."""
    actors = [make_brush_actor("Wall", cube(200, 8, 200),
                               location=tuple(Decimal(str(c)) for c in (0, 0, 0))),
              make_brush_actor("Shelf", cube(40, 8, 40),
                               location=tuple(Decimal(str(c)) for c in (0, 8, 0))),
              _light("MyLight", (0, 20, 0))]
    proj = _project(tmp_path, monkeypatch, actors)
    ns = _ns(proj, candidates=[], relative_to="Wall", max_gap=40.0)
    assert dispatch.dispatch(ns) == 0
    assert "MyLight" not in capsys.readouterr().out


def test_find_explicit_footprint_filter_excludes_a_point_candidate(tmp_path, monkeypatch, capsys):
    actors = [make_brush_actor("Wall", cube(200, 8, 200),
                               location=tuple(Decimal(str(c)) for c in (0, 0, 0))),
              _light("MyLight", (0, 20, 0))]
    proj = _project(tmp_path, monkeypatch, actors)
    ns = _ns(proj, candidates=["MyLight"], relative_to="Wall", max_gap=40.0,
             footprint={"partial"})
    assert dispatch.dispatch(ns) == 0
    assert "MyLight" not in capsys.readouterr().out


def test_find_json_emits_null_poly_for_a_point_candidate(tmp_path, monkeypatch, capsys):
    import json
    actors = [make_brush_actor("Wall", cube(200, 8, 200),
                               location=tuple(Decimal(str(c)) for c in (0, 0, 0))),
              _light("MyLight", (0, 20, 0))]
    proj = _project(tmp_path, monkeypatch, actors)
    ns = _ns(proj, candidates=["MyLight"], relative_to="Wall", max_gap=40.0, json=True)
    assert dispatch.dispatch(ns) == 0
    rows = json.loads(capsys.readouterr().out)
    assert any(r["candidate"] == "MyLight" and r["poly"] is None for r in rows)


def test_find_emits_one_row_per_point_candidate_even_under_top_all(tmp_path, monkeypatch, capsys):
    """The project owner decided this directly: a bare name with no :idx has nothing to distinguish
    N rows, so a point candidate emits exactly one, whatever --top says."""
    actors = [make_brush_actor("Wall", cube(200, 8, 200),
                               location=tuple(Decimal(str(c)) for c in (0, 0, 0))),
              _light("MyLight", (0, 20, 0))]
    proj = _project(tmp_path, monkeypatch, actors)
    ns = _ns(proj, candidates=["MyLight"], relative_to="Wall", max_gap=40.0, top="all")
    assert dispatch.dispatch(ns) == 0
    assert capsys.readouterr().out.count("MyLight") == 1
```

- [ ] **Step 3: Run the tests to verify they fail**

Run: `bin/test -k "point_footprint or find_accepts_an_explicitly_named or find_default_candidate_set or find_explicit_footprint_filter or find_json_emits_null_poly or find_emits_one_row_per_point" -v`
Expected: every test FAILS except `test_find_default_candidate_set_stays_brush_only`, which passes
already (the default is unchanged — that is what it is there to confirm).

- [ ] **Step 4: Add the point-in-polygon helpers to `uedcli/relation.py`**

Place these immediately after `_shares_vertex` (line 177), with the other 2-D predicates:

```python
def _point_on_any_edge(poly: list[Vec2], p: Vec2) -> bool:
    """True if `p` lies on any edge of `poly`, within `_TOUCH_EPS`. Calls the existing
    `_point_on_segment(p, s0, s1)` -- one implementation of the tolerance logic, not two."""
    return any(_point_on_segment(p, s0, s1) for s0, s1 in _edges(poly))


def _point_in_polygon_2d(poly: list[Vec2], p: Vec2) -> bool:
    """Ray-casting point-in-polygon, even-odd rule. Winding-agnostic, so the caller need not
    `_ensure_ccw` first."""
    inside = False
    n = len(poly)
    j = n - 1
    for i in range(n):
        xi, yi = poly[i]
        xj, yj = poly[j]
        if (yi > p[1]) != (yj > p[1]):
            x_cross = xj + (p[1] - yj) * (xi - xj) / (yi - yj)
            if p[0] < x_cross:
                inside = not inside
        j = i
    return inside


def point_footprint_2d(ref_uv: list[Vec2], point_uv: Vec2) -> str:
    """Where `point_uv` sits relative to `ref_uv`'s footprint, in the same (U, V) frame
    `project_to_plane` produces: `"inside"`, `"on_boundary"`, or `"outside"`.

    Deliberately NOT a `classify_footprint_2d` branch. That function, fed a one-vertex "polygon",
    treats it as a 1-edge clip polygon whose `inside()` test is vacuously true, so it returns
    `contains_a_in_b` for every input -- dead centre, on an edge, or 900uu away alike. The
    vocabulary is new on purpose too: `contains` is already taken in `footprint_2d`'s own value set
    and in `_FOOTPRINT_FILTER_ALIASES`/`_FOOTPRINT_2D_RANK`/`_FOOTPRINT_2D_LABELS`, so reusing it
    would collide with live tables, not just live words."""
    if _point_on_any_edge(ref_uv, point_uv):
        return "on_boundary"
    return "inside" if _point_in_polygon_2d(ref_uv, point_uv) else "outside"
```

- [ ] **Step 5: Add `PointPair` and `point_pairs_between`**

Place after `_pairs_between` (line 362):

```python
@dataclass(frozen=True)
class PointPair:
    """One REF face against one NON-BRUSH actor's `Location` -- the point analogue of `PairFace`.
    A point has no poly, no area and no edge extent, so this carries strictly fewer fields than
    `PairFace` rather than filling the missing ones with sentinels."""
    brush_a: str
    poly_a: int
    actor_b: str
    distance: float
    point_footprint: str
    centroid_u: float
    centroid_v: float
    footprint_gap: float


_POINT_FOOTPRINT_RANK = {"inside": 0, "on_boundary": 1, "outside": 2}


def _point_pair_sort_key(pair: PointPair) -> tuple:
    """Same shape as `_candidate_sort_key`: footprint quality first, then perpendicular distance,
    then the ref poly index as a deterministic tie-break."""
    return (_POINT_FOOTPRINT_RANK[pair.point_footprint], abs(pair.distance), pair.poly_a)


def point_pairs_between(ref_actor, ref_idxs: set, point_actor) -> list[PointPair]:
    """Every (ref poly, point) pairing, ranked best-first. `point_actor.location` is required -- an
    actor with no Location has no position to compare and yields no pairs at all. Never a
    substituted origin: a silently-defaulted (0,0,0) would report a confident, wrong distance."""
    if point_actor.location is None:
        return []
    point = tuple(float(c) for c in point_actor.location)
    out: list[PointPair] = []
    for idx in sorted(ref_idxs):
        poly = ref_actor.brush.polys[idx]
        try:
            normal = polyalign._world_normal(ref_actor, poly, ref=f"{ref_actor.name}:{idx}")
        except polyalign.PolyAlignError:
            continue                      # a degenerate ref face has no plane to compare against
        world = polyalign._world_verts(ref_actor, poly)
        distance = _dot(_sub(point, world[0]), normal)
        ref_uv = project_to_plane(world, normal)
        point_uv = project_to_plane([point], normal, origin=world[0])[0]
        fp = point_footprint_2d(ref_uv, point_uv)
        gap = _footprint_bbox_gap(ref_uv, [point_uv]) if fp == "outside" else 0.0
        out.append(PointPair(brush_a=ref_actor.name, poly_a=idx, actor_b=point_actor.name,
                              distance=distance, point_footprint=fp,
                              centroid_u=point_uv[0], centroid_v=point_uv[1],
                              footprint_gap=gap))
    out.sort(key=_point_pair_sort_key)
    return out
```

- [ ] **Step 6: Add `find_point_candidates`**

Place immediately after `find_candidates` (line 551):

```python
def find_point_candidates(level, ref_token: str, point_names: list[str], *,
                           max_gap: float | None = None, min_gap: float | None = None,
                           footprint: set | None = None,
                           plane: str | None = None) -> list[PointPair]:
    """`actor relation find`'s non-brush half: rank each named NON-BRUSH actor's `Location` against
    `ref_token`'s faces, keeping at most ONE row per actor whatever `--top` says -- the project
    owner decided that directly (Step 1).

    Predicate rules, exactly as the spec states them:
    * an explicit `--footprint` or `--plane` excludes every point candidate -- a face-pair predicate
      has nothing to test against a point. Not an error: a mixed brush/point candidate set is
      normal, and the filter simply narrows to the brush ones.
    * the IMPLICIT footprint filter `_passes_predicates` applies when `--footprint` is omitted
      (excluding `footprint_2d == "none"`) does NOT apply here -- "no footprint overlap" is not a
      meaningful exclusion for something with no footprint.
    * `--max-gap`/`--min-gap` apply normally, on `abs(distance)`, with the same `_GAP_EPS` slack
      `_passes_gap_and_plane` uses, so a genuinely flush point still passes `--max-gap 0`.
    * a point candidate never contributes to the near-miss count, which is footprint-keyed."""
    if footprint is not None or plane is not None:
        return []
    ref_name, ref_actor, ref_idxs = _resolve_measure_selector(level, ref_token)
    out: list[PointPair] = []
    for name in point_names:
        pairs = point_pairs_between(ref_actor, ref_idxs, level.actors[name])
        kept = [p for p in pairs
                if (max_gap is None or abs(p.distance) <= max_gap + _GAP_EPS)
                and (min_gap is None or abs(p.distance) >= min_gap - _GAP_EPS)]
        if kept:
            out.append(kept[0])
    return out
```

- [ ] **Step 7: Wire it into the `find` handler**

In `uedcli/cli/commands/actor/relation.py`'s `_find`, replace the `skipping non-brush actor` branch
(currently lines 74-76) with a split. The explicit-candidate loop becomes:

```python
        candidate_names: list[str] = []
        point_names: list[str] = []
        seen: set = set()
        for tok in raw:
            bname = tok.split(":", 1)[0]
            try:
                canonical = query.resolve_actor_name(level, bname)
            except KeyError as e:
                print(e.args[0], file=sys.stderr)
                return 2
            if canonical == ref_name and not args.allow_self:
                print(f"actor relation find: candidate {canonical!r} is the reference's own "
                      f"brush — pass --allow-self to include it", file=sys.stderr)
                return 2
            if canonical in seen:
                continue
            seen.add(canonical)
            if level.actors[canonical].brush is None:
                point_names.append(canonical)   # a named non-brush actor is a real candidate now
            else:
                candidate_names.append(canonical)
```

The default branch (`if not args.candidates:`) sets `point_names = []` alongside its existing
`candidate_names` assignment — the default stays brush-only.

After the existing `find_candidates` call, add:

```python
    try:
        point_matches = relation.find_point_candidates(
            level, args.relative_to, point_names,
            max_gap=args.max_gap, min_gap=args.min_gap,
            footprint=args.footprint, plane=args.plane,
        )
    except relation.RelationError as e:
        print(str(e), file=sys.stderr)
        return 2
```

In the `--json` branch, append the point rows with an explicit null poly:

```python
        rows += [{"ref": p.brush_a, "ref_poly": p.poly_a,
                  "candidate": p.actor_b, "poly": None} for p in point_matches]
```

In the plain branch, print each point match's bare name after the brush ones and include them in the
count:

```python
        for p in point_matches:
            print(p.actor_b)
        matched_candidates = len({m.candidate for m in matches} | {p.actor_b for p in point_matches})
        print(f"{len(matches) + len(point_matches)} face(s) matched across "
              f"{matched_candidates} candidate(s)", file=sys.stderr)
```

The near-miss note is untouched — `result.near_miss_count` never counts a point.

- [ ] **Step 8: Run the tests**

Run: `bin/test -k "point_footprint or find_accepts_an_explicitly_named or find_default_candidate_set or find_explicit_footprint_filter or find_json_emits_null_poly or find_emits_one_row_per_point" -v`
Expected: PASS

Run: `bin/test -k relation`
Expected: all green.

- [ ] **Step 9: Run the whole suite, then commit**

Run: `bin/test`

```bash
git add uedcli/relation.py uedcli/cli/commands/actor/relation.py
git add uedcli/tests/test_relation.py uedcli/tests/test_cli_actor_relation_find.py
git commit -m "actor relation find: accept a non-brush candidate"
```

---

### Task 5: `compare` — accept a non-brush TARGET

**Files:**
- Modify: `uedcli/relation.py` (`compute_point_pairs`, `format_point_report`)
- Modify: `uedcli/cli/commands/actor/relation.py` (`_compare`: split the target list)
- Test: `uedcli/tests/test_cli_actor_relation_compare.py`

**Interfaces:**
- Consumes: `PointPair`, `point_pairs_between`, `_resolve_measure_selector`, `_fmt` (relation.py:683,
  `f"{v + 0.0:.3f}uu"`) — all existing after Task 4.
- Produces:

```python
def compute_point_pairs(level, ref_token: str, point_names: list[str]) -> list[PointPair]
def format_point_report(pairs: list[PointPair]) -> str
```

  `compute_pairs`/`format_report` are untouched: a point target reports a strictly different field
  set, so a second formatter is honest where a shared one with blank columns would not be.

- [ ] **Step 1: Write the failing tests**

Append to `uedcli/tests/test_cli_actor_relation_compare.py`, reusing its own `_brush`/`_project`/`_ns`
helpers:

```python
def _light(name, loc):
    from uedcli.model import Actor
    return Actor(name=name, cls="Engine.Light",
                 location=tuple(Decimal(str(c)) for c in loc))


def test_compare_reports_a_point_target_inside_the_ref_footprint(tmp_path, monkeypatch, capsys):
    actors = [_brush("Wall", cube(200, 8, 200), loc=(0, 0, 0)), _light("MyLight", (0, 20, 0))]
    proj = _project(tmp_path, monkeypatch, actors)
    ns = _ns(proj, "Wall", "MyLight")
    ns.relationsub = "compare"
    assert dispatch.dispatch(ns) == 0
    out = capsys.readouterr().out
    assert "MyLight" in out
    assert "point_footprint: inside" in out
    assert "distance:" in out
    assert "centroid_u:" in out and "centroid_v:" in out
    assert "footprint_2d" not in out     # not the brush-vs-brush vocabulary
    assert "edge_u" not in out           # a point has no edge extent to report


def test_compare_reports_a_point_target_outside_the_ref_footprint(tmp_path, monkeypatch, capsys):
    actors = [_brush("Wall", cube(200, 8, 200), loc=(0, 0, 0)), _light("FarLight", (900, 20, 0))]
    proj = _project(tmp_path, monkeypatch, actors)
    ns = _ns(proj, "Wall", "FarLight")
    ns.relationsub = "compare"
    assert dispatch.dispatch(ns) == 0
    assert "point_footprint: outside" in capsys.readouterr().out


def test_compare_point_target_with_no_location_exits_2(tmp_path, monkeypatch, capsys):
    """No Location means no position to compare. Exit 2 naming the actor — never a substituted
    origin, which would report a confident, wrong distance."""
    from uedcli.model import Actor
    actors = [_brush("Wall", cube(200, 8, 200), loc=(0, 0, 0)),
              Actor(name="Nowhere", cls="Engine.Light")]
    proj = _project(tmp_path, monkeypatch, actors)
    ns = _ns(proj, "Wall", "Nowhere")
    ns.relationsub = "compare"
    assert dispatch.dispatch(ns) == 2
    assert "Nowhere" in capsys.readouterr().err
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `bin/test -k "compare_reports_a_point_target or compare_point_target_with_no_location" -v`
Expected: FAIL — `_resolve_measure_selector` currently raises
`RelationError("'MyLight' is not a brush actor (no PolyList)")` for the target, so the first two exit
2 with no report, and the third passes for the wrong reason (the wrong message).

- [ ] **Step 3: Add `compute_point_pairs` and `format_point_report`**

In `uedcli/relation.py`, after `compute_pairs` (which starts at line 454):

```python
def compute_point_pairs(level, ref_token: str, point_names: list[str]) -> list[PointPair]:
    """`actor relation compare REF POINT_ACTOR...` -- one ref selector against one or more NON-BRUSH
    actors, each reported at its best-ranked ref face. Raises `RelationError` naming the offender for
    a bad ref token, an actor with no `Location`, or a ref whose every face is degenerate."""
    ref_name, ref_actor, ref_idxs = _resolve_measure_selector(level, ref_token)
    out: list[PointPair] = []
    for name in point_names:
        actor = level.actors[name]
        if actor.location is None:
            raise RelationError(
                f"actor relation compare: {name!r} states no Location, so it has no position to "
                f"compare against {ref_name!r}")
        pairs = point_pairs_between(ref_actor, ref_idxs, actor)
        if not pairs:
            raise RelationError(
                f"actor relation compare: no selected face of {ref_name!r} has a usable plane to "
                f"compare {name!r} against (every one is degenerate)")
        out.append(pairs[0])
    return out


def format_point_report(pairs: list[PointPair]) -> str:
    """One block per point target. Deliberately a DIFFERENT field set from `format_report`: a point
    has no footprint area and no edge extent, so `footprint_2d`/`edge_u`/`edge_v` are absent rather
    than printed blank, and the point-only classification prints under its own key."""
    lines: list[str] = []
    for p in pairs:
        lines.append(f"{p.brush_a}:{p.poly_a} <-> {p.actor_b}")
        lines.append(f"  distance: {_fmt(p.distance)}")
        lines.append(f"  point_footprint: {p.point_footprint}")
        lines.append(f"  centroid_u: {_fmt(p.centroid_u)}")
        lines.append(f"  centroid_v: {_fmt(p.centroid_v)}")
    return "\n".join(lines)
```

- [ ] **Step 4: Split the target list in the `compare` handler**

In `uedcli/cli/commands/actor/relation.py`'s `_compare`, after `level = src.load()`:

```python
    brush_targets, point_targets = [], []
    for tok in targets:
        bname = tok.split(":", 1)[0]
        try:
            canonical = query.resolve_actor_name(level, bname)
        except KeyError as e:
            print(e.args[0], file=sys.stderr)
            return 2
        if level.actors[canonical].brush is None:
            if ":" in tok:
                print(f"actor relation compare: {canonical!r} is not a brush actor, so "
                      f"{tok!r} cannot name one of its faces", file=sys.stderr)
                return 2
            point_targets.append(canonical)
        else:
            brush_targets.append(tok)
```

Guard the existing `compute_pairs`/`format_report` block with `if brush_targets:` (passing
`brush_targets` where it passed `targets`), then add:

```python
    if point_targets:
        try:
            point_pairs = relation.compute_point_pairs(level, args.ref, point_targets)
        except relation.RelationError as e:
            print(str(e), file=sys.stderr)
            return 2
        print(relation.format_point_report(point_pairs))
```

- [ ] **Step 5: Run the tests**

Run: `bin/test -k "compare_reports_a_point_target or compare_point_target_with_no_location" -v`
Expected: PASS

Run: `bin/test -k relation`
Expected: all green.

- [ ] **Step 6: Run the whole suite, then commit**

Run: `bin/test`

```bash
git add uedcli/relation.py uedcli/cli/commands/actor/relation.py
git add uedcli/tests/test_cli_actor_relation_compare.py
git commit -m "actor relation compare: accept a non-brush TARGET"
```

---

### Task 6: `set` — accept a non-brush TARGET, and retire the skill's "Known limitation"

**Files:**
- Modify: `uedcli/relation.py` (`compute_point_set_translation`)
- Modify: `uedcli/cli/parsers/actor_relation.py` (`rset`'s `target` metavar/help — a bare actor name
  is now legal)
- Modify: `uedcli/cli/commands/actor/relation.py` (`_set`: pick the right translation function)
- Modify: `plugins/uedcli/skills/verifying-brush-relations/SKILL.md` (the "Known limitation" section
  at line 165, now false)
- Modify: `uedcli/tests/fixtures/parser_baseline/*.json` (regenerated — `rset`'s help changed)
- Test: `uedcli/tests/test_cli_actor_relation_set.py`

**Interfaces:**
- Consumes: `compute_deltas`, `_edge_extent`, `_plane_basis`, `project_to_plane`,
  `_resolve_exact_face` — all existing. Both `compute_deltas` and `_edge_extent` work correctly on a
  one-element "poly": `_poly_centroid_2d` falls back to the vertex average when the shoelace area is
  ~0 (`uedcli/preview.py:422-423`), and `min`/`max` of a one-element list is that element. So the
  point target reuses them rather than getting its own math.
- Produces:

```python
def compute_point_set_translation(level, target_name: str, ref_token: str, *,
                                  gap=None, centroid_u=None, centroid_v=None,
                                  edge_u=None, edge_v=None) -> tuple[str, str, Vec3]
```

  Same `(target_name, ref_name, move)` return shape as `compute_set_translation`, so `_set`'s
  two-pass plan/apply loop needs no restructuring.

- [ ] **Step 1: Write the failing tests**

Append to `uedcli/tests/test_cli_actor_relation_set.py` (the file Task 3 renamed from
`test_cli_brush_relation_set.py`). Its two real helpers, verified against the file as it stands:
`_project(tmp_path, monkeypatch, actors, name="lvl")` writes the trunk under `proj / "maps" / name`,
and `_ns(proj, target, relative_to, **overrides)` takes `target` as a POSITIONAL list of selector
tokens — there is no `targets=` keyword, and passing one would land in `**overrides` and leave the
required positional missing. There is no reload helper either: every test reads results back inline
with `lvl, _ = trunk.read_level(proj / "maps" / <name>)`. Re-check both before writing, and follow
whatever the file actually does.

```python
def _light(name, loc):
    from uedcli.model import Actor
    return Actor(name=name, cls="Engine.Light",
                 location=tuple(Decimal(str(c)) for c in loc))


def _plus_y_face(actor) -> int:
    """The index of the brush's +Y face: the one all of whose vertices sit at the brush's own
    maximum local Y. `cube(200, 8, 200)` puts that at y = +4."""
    ymax = max(v[1] for p in actor.brush.polys for v in p.vertices)
    return next(i for i, p in enumerate(actor.brush.polys)
                if all(v[1] == ymax for v in p.vertices))


def test_set_moves_a_point_actor_to_an_exact_gap(tmp_path, monkeypatch, capsys):
    """Wall is a 200x8x200 box at the origin, so its +Y face sits at y=4 with normal +Y. --gap 8
    puts MyLight at y=12 exactly; X and Z are untouched because no U/V flag was given."""
    wall = make_brush_actor("Wall", cube(200, 8, 200),
                            location=tuple(Decimal(str(c)) for c in (0, 0, 0)))
    actors = [wall, _light("MyLight", (0, 40, 0))]
    proj = _project(tmp_path, monkeypatch, actors)
    ns = _ns(proj, ["MyLight"], f"Wall:{_plus_y_face(wall)}", gap=8.0)
    assert dispatch.dispatch(ns) == 0
    lvl, _ = trunk.read_level(proj / "maps" / "lvl")
    moved = lvl.actors["MyLight"]
    assert moved.location[1] == Decimal("12")
    assert moved.location[0] == Decimal("0") and moved.location[2] == Decimal("0")


def test_set_edge_and_centroid_flags_differ_against_a_point_target(tmp_path, monkeypatch):
    """--edge-u-min and --centroid-u are genuinely different offsets against a point target:
    `_edge_extent` computes pick(target) - pick(ref), and while the POINT's own min/max/centroid all
    collapse to one value, REF's do not. (The spec's Round 4 draft refused these flags on the
    opposite claim; Round 5 reversed it.)"""
    wall = make_brush_actor("Wall", cube(200, 8, 200),
                            location=tuple(Decimal(str(c)) for c in (0, 0, 0)))
    ref = f"Wall:{_plus_y_face(wall)}"
    results = {}
    for flag in ("edge_u_min", "centroid_u"):
        actors = [wall, _light("MyLight", (0, 40, 0))]
        proj = _project(tmp_path, monkeypatch, actors, name=f"lvl_{flag}")
        ns = _ns(proj, ["MyLight"], ref)
        setattr(ns, flag, 8.0)
        assert dispatch.dispatch(ns) == 0
        lvl, _ = trunk.read_level(proj / "maps" / f"lvl_{flag}")
        results[flag] = lvl.actors["MyLight"].location
    assert results["edge_u_min"] != results["centroid_u"]


def test_set_rejects_an_idx_on_a_non_brush_target(tmp_path, monkeypatch, capsys):
    wall = make_brush_actor("Wall", cube(200, 8, 200),
                            location=tuple(Decimal(str(c)) for c in (0, 0, 0)))
    actors = [wall, _light("MyLight", (0, 40, 0))]
    proj = _project(tmp_path, monkeypatch, actors)
    ns = _ns(proj, ["MyLight:0"], f"Wall:{_plus_y_face(wall)}", gap=8.0)
    assert dispatch.dispatch(ns) == 2
    assert "MyLight" in capsys.readouterr().err
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `bin/test -k "set_moves_a_point_actor_to_an_exact_gap or set_edge_and_centroid_flags_differ or set_rejects_an_idx_on_a_non_brush" -v`
Expected: FAIL — `_resolve_exact_face` rejects a bare name with
`"TARGET must be BRUSH:idx (a bare brush name is not allowed)"`.

- [ ] **Step 3: Add `compute_point_set_translation`**

In `uedcli/relation.py`, after `compute_set_translation` (lines 628-680) and before `_fmt`
(line 683):

The hand-computed `distance` below stands in for `compute_set_translation`'s `rel.distance`, and
follows the same sign convention, checked against the real code rather than assumed:
`plane_relationship` computes `distance = _dot(_sub(point_b, point_a), normal_a)`
(`uedcli/relation.py:55`), and `compute_set_translation` calls it as
`plane_relationship(ref_actor, ref_poly, target_actor, target_poly)` (line 650) — so `a` is REF,
`b` is TARGET, and the value is TARGET minus REF projected on the REF face's normal. Positive means
the target sits on the side the ref face's normal points to. `_dot(_sub(point, ref_world[0]),
normal)` with `normal` the same ref-face world normal is that expression verbatim, so `--gap`'s
`gap - distance` means the same thing on both paths.

```python
def compute_point_set_translation(level, target_name: str, ref_token: str, *,
                                   gap: float | None = None,
                                   centroid_u: float | None = None, centroid_v: float | None = None,
                                   edge_u=None, edge_v=None):
    """`actor relation set POINT_ACTOR --relative-to REF:idx` -- the non-brush half of
    `compute_set_translation`, same `(target_name, ref_name, move)` return.

    The point stands in for the second face everywhere the brush path used one: there is no
    `plane_relationship` call (a point defines no plane of its own), so REF's own world normal IS
    the normal, and `compute_deltas`/`_edge_extent` take a one-element UV list.

    `--edge-u-min`/`--edge-u-max`/`--edge-v-*` stay MEANINGFUL against a point target and are kept,
    not refused: `_edge_extent` computes `pick(target) - pick(ref)`, and while the point's own min
    and max collapse to one value, REF's do not -- so "put this actor 8uu from the reference face's
    U-min edge" is a real instruction, distinct from "put its centroid 8uu from the reference
    centroid"."""
    if (gap is None and centroid_u is None and centroid_v is None
            and edge_u is None and edge_v is None):
        raise RelationError(
            "actor relation set: at least one of --gap/--centroid-u/--centroid-v/--edge-u-min/"
            "--edge-u-max/--edge-v-min/--edge-v-max is required")
    ref_name, ref_actor, ref_idx = _resolve_exact_face(level, ref_token, "--relative-to")
    target = level.actors[target_name]
    if target.location is None:
        raise RelationError(
            f"actor relation set: {target_name!r} states no Location, so there is nothing to "
            f"translate")
    ref_poly = ref_actor.brush.polys[ref_idx]
    try:
        normal = polyalign._world_normal(ref_actor, ref_poly, ref=f"{ref_name}:{ref_idx}")
    except polyalign.PolyAlignError as e:
        raise RelationError(
            f"actor relation set: {ref_name}:{ref_idx} is degenerate (zero area), so it defines no "
            f"normal to move along") from e
    u_axis, v_axis = _plane_basis(normal)
    ref_world = polyalign._world_verts(ref_actor, ref_poly)
    point = tuple(float(c) for c in target.location)
    uv_ref = project_to_plane(ref_world, normal)
    uv_target = project_to_plane([point], normal, origin=ref_world[0])
    distance = _dot(_sub(point, ref_world[0]), normal)
    deltas = compute_deltas(uv_ref, uv_target)

    delta_n = (gap - distance) if gap is not None else 0.0
    if centroid_u is not None:
        delta_u = centroid_u - deltas.centroid_u
    elif edge_u is not None:
        mode, want = edge_u
        delta_u = want - _edge_extent(uv_ref, uv_target, axis=0, mode=mode)
    else:
        delta_u = 0.0
    if centroid_v is not None:
        delta_v = centroid_v - deltas.centroid_v
    elif edge_v is not None:
        mode, want = edge_v
        delta_v = want - _edge_extent(uv_ref, uv_target, axis=1, mode=mode)
    else:
        delta_v = 0.0

    move = tuple(delta_n * normal[i] + delta_u * u_axis[i] + delta_v * v_axis[i] for i in range(3))
    return target_name, ref_name, move
```

- [ ] **Step 4: Pick the right function in the `set` handler**

In `uedcli/cli/commands/actor/relation.py`'s `_set`, inside the pass-1 loop, replace the single
`compute_set_translation` call with a branch on what the token names:

```python
        bname = target_token.split(":", 1)[0]
        try:
            canonical = query.resolve_actor_name(level, bname)
        except KeyError as e:
            print(e.args[0], file=sys.stderr)
            return 2
        is_point = level.actors[canonical].brush is None
        if is_point and ":" in target_token:
            print(f"actor relation set: {canonical!r} is not a brush actor, so {target_token!r} "
                  f"cannot name one of its faces", file=sys.stderr)
            return 2
        try:
            if is_point:
                target_name, ref_name, move = relation.compute_point_set_translation(
                    level, canonical, args.relative_to,
                    gap=args.gap, centroid_u=args.centroid_u, centroid_v=args.centroid_v,
                    edge_u=edge_u, edge_v=edge_v)
            else:
                target_name, ref_name, move = relation.compute_set_translation(
                    level, target_token, args.relative_to,
                    gap=args.gap, centroid_u=args.centroid_u, centroid_v=args.centroid_v,
                    edge_u=edge_u, edge_v=edge_v)
        except relation.RelationError as e:
            print(str(e), file=sys.stderr)
            return 2
```

A bare name that names a BRUSH still falls into the second branch and still exits 2 through
`_resolve_exact_face`'s existing "must be BRUSH:idx" message — unchanged.

- [ ] **Step 5: Update `rset`'s argument help**

In `uedcli/cli/parsers/actor_relation.py`, `rset`'s `target` currently says a bare name is not
allowed. Change its `metavar` to `TARGET` and its help to:

```python
        help="what to move: a brush face as an exact BRUSH:idx (a bare BRUSH name or an index list "
             "is not allowed), or a non-brush actor's bare Name (its Location moves). Repeat, or "
             "pass the single token '-' to read a newline list from stdin (empty stdin: clean "
             "no-op) -- every target moves relative to the SAME --relative-to reference"
```

- [ ] **Step 6: Retire the plugin skill's "Known limitation"**

`plugins/uedcli/skills/verifying-brush-relations/SKILL.md` lines 165-180 describe the point-actor
blind spot and an `actor find --overlapping-bbox` workaround. Tasks 4-6 removed it. Read the section
in full first (`grep -n "Known limitation" -A 25`), then replace its body with one short paragraph
saying a non-brush actor is now a real candidate (`actor relation find`) and a real TARGET
(`actor relation compare`, `actor relation set`), and that `--relative-to` is still a face selector
because a face is what you align against. Keep it shorter than what it replaces (`CLAUDE.md`, "Keep
it short and plain").

This edit sits in the LAST of the three broadening tasks deliberately: declaring the limitation gone
before the code removes it would ship a false doc.

- [ ] **Step 7: Regenerate the parser baseline**

Run: `.venv/bin/python -m uedcli.tests.parser_baseline`

- [ ] **Step 8: Run the tests**

Run: `bin/test -k "set_moves_a_point_actor_to_an_exact_gap or set_edge_and_centroid_flags_differ or set_rejects_an_idx_on_a_non_brush" -v`
Expected: PASS

Run: `bin/test -k "relation or parser_baseline"`
Expected: all green.

- [ ] **Step 9: Run the whole suite, then commit**

Run: `bin/test`

```bash
git add uedcli/relation.py uedcli/cli/parsers/actor_relation.py
git add uedcli/cli/commands/actor/relation.py uedcli/tests/test_cli_actor_relation_set.py
git add plugins/uedcli/skills/verifying-brush-relations/SKILL.md
git add uedcli/tests/fixtures/parser_baseline/
git commit -m "actor relation set: accept a non-brush TARGET"
```

---

## Part B — `actor survey`'s raw tier

Two new modules and one new test-support module. Their responsibilities, fixed here so later tasks
do not drift:

| File | Owns |
|---|---|
| `uedcli/actor_survey.py` | the whole survey: neighborhood selection, both tiers' fact computation, the line formatters, the error types. No CLI, no I/O. |
| `uedcli/cli/parsers/actor_survey.py` | the `survey` subparser only |
| `uedcli/cli/commands/actor/survey.py` | the handler: resolve source/index/defaults, call `actor_survey`, print, map errors to exit codes |
| `uedcli/tests/survey_scenarios.py` | every geometric fixture, built once, named, reused. Each builder returns a `Scenario` dataclass — never a tuple, so no test ever unpacks by arity. |

### Task 7: bounded-neighborhood selection

**Files:**
- Create: `uedcli/actor_survey.py`
- Create: `uedcli/tests/survey_scenarios.py`
- Test: `uedcli/tests/test_actor_survey.py` (new)

**Interfaces:**
- Consumes: `uedcli/writes.py`'s `actor_bounds(actor) -> (lo, hi)` (Decimals) and
  `aabb_intersects(a, b) -> bool`; `uedcli/movers.py`'s `is_mover(actor, index)`;
  `uedcli/normalize.py`'s `is_builder_brush(actor)` — all unchanged.
- Produces:

```python
NEIGHBORHOOD_PAD: Decimal = Decimal("1")

def region_of(actor, defaults, pad: Decimal = NEIGHBORHOOD_PAD) -> tuple[tuple, tuple]
def in_world_csg(actor, class_index) -> bool                      # contributes to the world solve?
def seed_brush_name(level, class_index) -> str | None             # the level's FIRST such brush
def neighborhood(level, class_index, surveyed_actor, defaults) -> list   # list[Actor], brushes only
def near_brushes(level, class_index, surveyed_actor, defaults) -> list   # the subset that meets R
def nearby_point_actors(level, surveyed_actor, defaults) -> list         # list[Actor], non-brush
```

  `defaults` is the class-defaults resolver (`classdefaults.ClassDefaults`, or the test stub
  below). `region_of` needs it because a NON-brush actor's shape is its collision extent, resolved
  instance-property-else-class-default — see the function's own docstring in Step 4.

  and in `uedcli/tests/survey_scenarios.py`:

```python
@dataclass(frozen=True)
class Scenario:
    level: Level
    index: object      # a StubClassIndex
    defaults: object   # a class-defaults stub (see below)
```

- [ ] **Step 1: Write the failing test**

New file `uedcli/tests/test_actor_survey.py`:

```python
"""`actor survey` — the bounded neighborhood, both tiers, and the CLI seam.

Fixtures live in `uedcli/tests/survey_scenarios.py`, one named builder per geometry, each returning
a `Scenario` so no test ever unpacks a tuple by arity.
"""
from __future__ import annotations

from uedcli import actor_survey
from uedcli.tests import survey_scenarios as scen


def test_neighborhood_takes_only_brushes_whose_aabb_meets_the_region():
    sc = scen.far_apart_rooms()
    names = [a.name for a in actor_survey.neighborhood(sc.level, sc.index,
                                                       sc.level.actors["FarRoom"], sc.defaults)]
    assert "FarRoom" in names
    assert "Touching" in names      # shares FarRoom's +X wall
    assert "Distant" not in names   # 4000uu away, and not the level's first world-CSG brush


def test_neighborhood_always_includes_the_levels_first_world_csg_brush():
    """Not for its geometry — `bsp_brush_csg` special-cases a LEADING CSG_Add against a node-less
    world, seeding it as the world shell instead of classifying it (`bspcsg.rs`'s `first_add_seed`).
    Truncation changes which brush is first, so the shortcut fires on the wrong one. The spike
    measured this: without the clause, `nsfhq04 DeusExMover31`'s truncated solve lost all four
    `Brush799` faces and gained a `Brush798` one.
    (`dev/docs/spikes/2026-09-23-actor-survey-csg-kind-and-cost/harness/bounded_cost.py::neighborhood`.)"""
    sc = scen.far_apart_rooms()
    first = sc.level.order[0]
    names = [a.name for a in actor_survey.neighborhood(sc.level, sc.index,
                                                       sc.level.actors["FarRoom"], sc.defaults)]
    assert first == "Shell"
    assert "Shell" in names


def test_seed_brush_name_skips_a_leading_mover_and_names_the_first_contributing_brush():
    """`bsp_brush_csg` seeds the world shell from the first brush that actually CONTRIBUTES to the
    world solve. A Mover is a brush and contributes nothing, so trunk index 0 is not the answer —
    and any guard that says "the first brush" by INDEX would protect the wrong actor while the real
    seed sat further down, droppable. Built inline rather than as a scenario: this is about trunk
    order alone, no geometry."""
    from uedcli.builders import cube, make_brush_actor
    from uedcli.model import Level
    from uedcli.tests.conftest import StubClassIndex
    door = make_brush_actor("Door", cube(64, 8, 128), mover_class="Engine.Mover")
    wall = make_brush_actor("Wall", cube(256, 64, 256), csg="add")
    lvl = Level(actors={a.name: a for a in (door, wall)}, order=["Door", "Wall"])
    index = StubClassIndex()
    assert lvl.order[0] == "Door"
    assert actor_survey.in_world_csg(door, index) is False
    assert actor_survey.seed_brush_name(lvl, index) == "Wall"


def test_neighborhood_preserves_trunk_order():
    """The CSG evaluation order IS the actor-set order, so the selection must not re-sort."""
    sc = scen.far_apart_rooms()
    names = [a.name for a in actor_survey.neighborhood(sc.level, sc.index,
                                                       sc.level.actors["FarRoom"], sc.defaults)]
    positions = [sc.level.order.index(n) for n in names]
    assert positions == sorted(positions)


def test_near_brushes_excludes_the_far_first_brush_that_neighborhood_forces_in():
    """The first-brush clause is for the SOLVE's correctness, not for pair-testing: a brush 4000uu
    away shares no face with anything here and must not be fed to `classify_pair`."""
    sc = scen.far_apart_rooms()
    near = [a.name for a in actor_survey.near_brushes(sc.level, sc.index,
                                                      sc.level.actors["FarRoom"], sc.defaults)]
    assert "Shell" not in near
    assert "Touching" in near


def test_region_pad_is_one_uu_and_stays_decimal():
    """`actor_bounds` returns Decimals and `aabb_intersects` adds its own Decimal slack, so a bare
    float pad raises TypeError against them. The value is 1.0 uu — the spike's own `PAD`
    (`harness/bounded_cost.py:35`), which every one of its 140 verified surveys ran at."""
    from decimal import Decimal
    sc = scen.far_apart_rooms()
    lo, hi = actor_survey.region_of(sc.level.actors["FarRoom"], sc.defaults)
    assert all(isinstance(c, Decimal) for c in lo + hi)
    assert actor_survey.NEIGHBORHOOD_PAD == Decimal("1")


def test_nearby_point_actors_finds_a_light_inside_the_surveyed_room():
    sc = scen.room_with_pillar_and_light()
    names = [a.name for a in actor_survey.nearby_point_actors(sc.level,
                                                              sc.level.actors["Room"],
                                                              sc.defaults)]
    assert "Light" in names
```

- [ ] **Step 2: Write the fixture module**

New file `uedcli/tests/survey_scenarios.py`. This task adds the two builders its own tests need;
later tasks append more, each written out in full in the task that first needs it.

```python
"""Geometric fixtures for `actor survey`'s tests.

One named builder per scenario, each returning a `Scenario` — never a bare tuple, so a test never
has to know how many things a fixture hands back. Geometry is stated in the builder's own docstring
in world units, because several tasks assert exact facts about it.

`index` is `conftest.StubClassIndex` (the offline mover/class-hierarchy stand-in the whole suite
already uses). `defaults` is the minimal class-defaults stand-in `test_serve_scene.py` already uses
for `_actor_radii` — a `for_class` returning an object with an empty `defaults` dict — so every
collision property a scenario needs is stated on the ACTOR, not resolved from a game package. A
scenario that wants an unresolvable class uses `failing_defaults()` instead.
"""
from __future__ import annotations

import dataclasses
from dataclasses import dataclass
from decimal import Decimal
from types import SimpleNamespace

from uedcli.builders import PF_SEMISOLID, cube, make_brush_actor
from uedcli.model import Actor, Level
from uedcli.tests.conftest import StubClassIndex


@dataclass(frozen=True)
class Scenario:
    level: Level
    index: object
    defaults: object


def stub_defaults():
    """Every class resolves, with no defaults of its own — so an actor's own props are the whole
    story. Mirrors `test_serve_scene.py`'s `_actor_radii` stub."""
    return SimpleNamespace(for_class=lambda cls: SimpleNamespace(defaults={}))


def failing_defaults():
    """Every class fails to resolve, the way a missing game package does."""
    from uedcli import uprops

    def _raise(cls):
        raise uprops.SchemaError(f"no schema for {cls}")

    return SimpleNamespace(for_class=_raise)


def _dec(v):
    return tuple(Decimal(str(c)) for c in v)


def brush(name, size, location, *, csg="add", poly_flags=0):
    """An axis-aligned box brush actor of world `size` centred at `location`."""
    return make_brush_actor(name, cube(*size), location=_dec(location), csg=csg,
                            poly_flags=poly_flags)


def oper_brush(name, size, location, oper):
    """A box brush carrying a raw `CsgOper` value `make_brush_actor` cannot author (`CSG_Intersect`,
    `CSG_Deintersect`). Strips the `CsgOper` `make_brush_actor` already added rather than appending a
    second one: `query._csg_oper` reads the FIRST match while `preview_native._csg_oper_or_skip`
    reads `dict(actor.props)` (last wins), so two entries would make the two disagree."""
    a = brush(name, size, location)
    props = [p for p in a.props if p[0].casefold() != "csgoper"] + [("CsgOper", oper)]
    return dataclasses.replace(a, props=props)


def point(name, location, *, cls="Engine.Light", props=()):
    return Actor(name=name, cls=cls, location=_dec(location), props=list(props))


def _level(actors) -> Level:
    return Level(actors={a.name: a for a in actors}, order=[a.name for a in actors])


def _scenario(actors, *, defaults=None) -> Scenario:
    return Scenario(level=_level(actors), index=StubClassIndex(),
                    defaults=defaults if defaults is not None else stub_defaults())


# --------------------------------------------------------------------- Task 7's scenarios

def far_apart_rooms() -> Scenario:
    """Trunk order: Shell, FarRoom, Touching, Distant.

    * `Shell`   1024^3 Add   at (0, 0, 0)          — the level's FIRST world-CSG brush
    * `FarRoom` 512^3 Subtract at (4000, 0, 0)     — the surveyed actor, far from Shell
    * `Touching` 256^3 Add   at (4384, 0, 0)       — flush against FarRoom's +X wall (x=4256)
    * `Distant` 256^3 Add    at (8000, 0, 0)       — meets nothing, and is not the first brush
    """
    return _scenario([
        brush("Shell", (1024, 1024, 1024), (0, 0, 0)),
        brush("FarRoom", (512, 512, 512), (4000, 0, 0), csg="subtract"),
        brush("Touching", (256, 256, 256), (4384, 0, 0)),
        brush("Distant", (256, 256, 256), (8000, 0, 0)),
    ])


def room_with_pillar_and_light() -> Scenario:
    """Trunk order: Room, Pillar, Light.

    * `Room`   1024^3 Subtract at (0, 0, 0)
    * `Pillar` 128 x 128 x 512 Add at (0, 0, 0)  — a later Add standing inside the room's void
    * `Light`  a point actor at (300, 0, 0)      — inside Room, outside Pillar

    The spec's pillar case: the Add never competes for `contains` (it is not a Subtract), so the
    Room owns the Light uncontested.
    """
    return _scenario([
        brush("Room", (1024, 1024, 1024), (0, 0, 0), csg="subtract"),
        brush("Pillar", (128, 128, 512), (0, 0, 0)),
        point("Light", (300, 0, 0)),
    ])
```

- [ ] **Step 3: Run the tests to verify they fail**

Run: `bin/test -k test_actor_survey -v`
Expected: collection FAILS — `uedcli.actor_survey` does not exist.

- [ ] **Step 4: Create `uedcli/actor_survey.py` with the neighborhood functions**

This is a direct port of
`dev/docs/spikes/2026-09-23-actor-survey-csg-kind-and-cost/harness/bounded_cost.py`'s `region_of`
(lines 195-202) and `neighborhood` (lines 205-231). Read that file before editing this one. The only
shape changes are that `neighborhood` takes the surveyed ACTOR and derives the region itself, rather
than taking `(lo, hi)` — the harness had already computed the region for its own timing — and that
`region_of` takes a class-defaults resolver, because the harness only ever ran it on brushes and a
non-brush actor's real shape is its collision extent.

The import block below carries only what THIS task's code uses. Later tasks widen it as they need
it: Task 8 adds `actorgraph`, Task 11 adds `query`, Task 12 adds `relation`.

```python
"""`actor survey <name>` -- every raw and CSG-resolved spatial fact about one actor.

The rules this implements are in
`dev/docs/board/to-plan/actor-survey-and-actor-relation-csg-resolved/spec.md`; the measurements
behind the neighborhood algorithm and the csg tier's tolerance are in
`dev/docs/spikes/2026-09-23-actor-survey-csg-kind-and-cost/`. Read both before changing anything
here -- several constants below are load-bearing for reasons that are not visible locally.
"""
from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from . import movers
from .normalize import is_builder_brush
from .writes import aabb_intersects, actor_bounds

# The neighborhood region is the surveyed actor's own world AABB grown by this much. 1.0 uu is the
# spike's own `PAD` (`harness/bounded_cost.py:35`) -- the value every one of its 140 verified
# surveys ran at, so changing it invalidates that evidence. Decimal, not float: `actor_bounds`
# returns Decimals and will not mix with a float.
NEIGHBORHOOD_PAD = Decimal("1")


class ActorNotFoundError(Exception):
    """`actor survey` was given a name the level does not carry. The CLI maps this to exit 2 --
    never a bare KeyError (`CLAUDE.md`)."""

    def __init__(self, name: str):
        super().__init__(f"Actor not found: {name}")
        self.name = name


def _to_decimal(text, default: Decimal = Decimal(0)) -> Decimal:
    """`text` as a Decimal, or `default` when it is absent or not a number -- the Decimal twin of
    the spike harness's `_to_float` (`collision_clearance.py:71`). It never raises: a malformed
    property value must not put a traceback in front of the user (`CLAUDE.md`)."""
    try:
        return Decimal(str(text).strip())
    except (TypeError, ValueError, ArithmeticError):
        return default


def _blocks_movement(actor, defaults) -> bool:
    """Does `actor` carry a collision volume the engine treats as MATTER -- `bCollideActors` AND
    `bBlockActors` both `True`?

    Instance property else class default, the same resolution `serve/scene.py::_actor_radii` uses
    for these fields -- including its `field`/`field_or` split, whose `is not None` test keeps a
    present-but-EMPTY value from being read as "absent" and silently replaced by the class default.
    These boolean gates are what need it.

    `bCollideActors` alone is not a claim about matter: shipped triggers that block nothing
    routinely carry a `CollisionRadius` of 520-630 uu so they can span a room. Ungated, surveying
    one would build a region over 1000 uu across and solve whatever neighborhood that region selects
    -- a cost the spike never measured (its 140 surveys ran on 1-uu-padded regions). Across 1522
    collidable shipped actors, requiring `bBlockActors` too drops the worst by-design overlap from
    436 uu to 64 uu (spike.md §3).

    This is the ONLY place the gate is written. Its two callers answer in different shapes --
    `_collision_half_extent` below in Decimal half-extents for region sizing, `collision_extent`
    (Task 11) in floats-or-None for the crossing gate -- but they must agree on WHETHER an actor
    collides at all. A second copy of the gate would let an edit to one drift from the other
    silently.

    `uprops.SchemaError` from an unresolvable class propagates -- guessing "does not collide" would
    be a substituted default. The CLI maps it to exit 2 (Task 18)."""
    instance = {k.casefold(): v for k, v in actor.props}
    class_defaults = defaults.for_class(actor.cls).defaults

    def field_or(name: str, default: str) -> str:
        low = name.casefold()
        value = instance[low] if low in instance else class_defaults.get((low, 0))
        return value if value is not None else default

    return (str(field_or("bCollideActors", "False")).strip() == "True"
            and str(field_or("bBlockActors", "False")).strip() == "True")


def _collision_half_extent(actor, defaults) -> tuple[Decimal, Decimal, Decimal]:
    """`(CollisionRadius, CollisionRadius, CollisionHeight)` when `actor` has a real BLOCKING
    collision volume (`_blocks_movement`), else `(0, 0, 0)`.

    The engine's collision volume is a CYLINDER: a circle of radius `CollisionRadius` in the XY
    plane, extruded in Z to half-height `CollisionHeight`. The project owner confirmed this
    directly, from first-hand Unreal Engine 1 experience, and `collision_extent` (Task 11) carries
    the disassembly that backs it. An earlier draft of this plan called it an axis-aligned box,
    sourced from a comment in `uedcli-native/src/collision.rs` that was never checked against the
    game binaries — do not reintroduce that claim or that citation.

    This function still returns THREE half-extents because its one caller, `region_of`, wants a
    bounding box and nothing else. A cylinder of radius R and half-height H has exactly the same
    axis-aligned bounding box as a box of half-extents (R, R, H), so no change is needed here: the
    region only has to be a conservative envelope for selecting candidate brushes and faces, never
    the true collision shape. Where the true shape does matter — testing whether the actor's own
    volume overlaps solid — the sampling is cylindrical (`cylinder_sample_points`, Task 11).

    An actor with no blocking collision volume resolves to `(0, 0, 0)`, which makes `region_of` fall
    back to the zero-size box at `Location`.

    `uprops.SchemaError` from an unresolvable class propagates -- guessing zero would be a
    substituted default. The CLI maps it to exit 2 (Task 18)."""
    if not _blocks_movement(actor, defaults):
        return Decimal(0), Decimal(0), Decimal(0)
    instance = {k.casefold(): v for k, v in actor.props}
    class_defaults = defaults.for_class(actor.cls).defaults

    def field(name: str):
        low = name.casefold()
        return instance[low] if low in instance else class_defaults.get((low, 0))

    radius = _to_decimal(field("CollisionRadius"))
    return radius, radius, _to_decimal(field("CollisionHeight"))


def region_of(actor, defaults, pad: Decimal = NEIGHBORHOOD_PAD):
    """`actor`'s REAL world AABB grown by `pad`, in Decimals.

    A brush's real shape is its own transformed vertices, which is what `writes.actor_bounds`
    returns. A non-brush actor's real shape is its collision cylinder, whose bounding box is
    `Location +/- (R, R, H)` from `_collision_half_extent` -- so that is added on top of the
    zero-size box `actor_bounds` gives a point actor. `pad` is then the SAME uniform padding in both
    cases; there is no separate point-actor padding. Without this a flush-mounted prop's region
    would be 2 uu across whatever its collision cylinder measures, and the wall it is mounted
    against would fall outside it.

    Ported from the spike harness's `region_of`, which only ever ran on brushes. The Decimal is not
    incidental -- `writes.aabb_intersects` adds its own Decimal slack and raises TypeError against a
    float bound, which is also why `_collision_half_extent` returns Decimals rather than floats."""
    lo, hi = actor_bounds(actor)
    if actor.brush is None:
        ext = _collision_half_extent(actor, defaults)
        lo = tuple(c - e for c, e in zip(lo, ext))
        hi = tuple(c + e for c, e in zip(hi, ext))
    return (tuple(c - pad for c in lo), tuple(c + pad for c in hi))


def in_world_csg(actor, class_index) -> bool:
    """Does this actor contribute to the WORLD CSG solve? A Mover and the builder brush are both
    brushes and neither does -- the same filter `preview_native.solve_world_surfaces` applies."""
    return actor.brush is not None and not (movers.is_mover(actor, class_index)
                                            or is_builder_brush(actor))


def seed_brush_name(level, class_index) -> str | None:
    """The name of the level's FIRST world-CSG-contributing brush in trunk order, or None if it has
    none.

    NOT `level.order[0]` and NOT `neighborhood(...)[0]`: a Mover or the builder brush can sit ahead
    of it and neither contributes, so the brush `bsp_brush_csg` actually seeds the world shell from
    (`uedcli-native/src/bspcsg.rs`'s `first_add_seed`) is often at a later index. Anything that must
    reason about "the first brush" -- `neighborhood`'s never-truncate clause, `removed_by`'s
    never-drop guard -- has to mean THIS one, so it is named once here rather than re-derived from
    an index at each site."""
    return next((n for n in level.order if in_world_csg(level.actors[n], class_index)), None)


def neighborhood(level, class_index, surveyed_actor, defaults) -> list:
    """Every BRUSH actor whose own world AABB meets the surveyed actor's region, in TRUNK ORDER --
    plus, always, the level's FIRST world-CSG brush.

    Ported from `bounded_cost.py::neighborhood`. The first-brush clause is not cosmetic and was
    found by the measurement failing without it: `bsp_brush_csg` special-cases a leading `CSG_Add`
    against a node-less world, SEEDING that brush as the world shell (storing every face reversed)
    instead of classifying it (`uedcli-native/src/bspcsg.rs`'s `first_add_seed`). Truncation changes
    which brush is first, so the shortcut fires on the wrong one -- measured on `nsfhq04
    DeusExMover31`, whose truncated solve lost all four `Brush799` faces and gained a `Brush798` one.
    Keeping the level's own first brush first makes the shortcut fire on exactly the brush it fires
    on in the full solve."""
    region = region_of(surveyed_actor, defaults)
    out, have_first = [], False
    for name in level.order:
        a = level.actors[name]
        if a.brush is None:
            continue
        contributes = in_world_csg(a, class_index)
        near = aabb_intersects(region_of(a, defaults, Decimal(0)), region)
        if near or (contributes and not have_first):
            out.append(a)
        if contributes:
            have_first = True
    return out


def near_brushes(level, class_index, surveyed_actor, defaults) -> list:
    """`neighborhood` minus the far first brush the seed clause forces in. The first brush is there
    for the SOLVE's correctness; it shares no geometry with the surveyed actor and must not be fed
    to `classify_pair` or named in any fact. Same filter the spike harness applies before its own
    raw-tier timing (`bounded_cost.py`'s `near = [...]`)."""
    region = region_of(surveyed_actor, defaults)
    return [a for a in neighborhood(level, class_index, surveyed_actor, defaults)
            if aabb_intersects(region_of(a, defaults, Decimal(0)), region)]


def nearby_point_actors(level, surveyed_actor, defaults) -> list:
    """Every NON-BRUSH actor whose own region meets the surveyed actor's region, in trunk order.
    `neighborhood` is brush-only by design (it feeds the CSG solve, which takes brushes), so the
    point-actor fan-out needs this second, cheaper selection.

    An actor with no `Location` is skipped -- it has no position to be contained at, and a
    substituted origin would invent a containment fact.

    The CANDIDATE is tested by its own extent-aware `region_of`, not by its bare `Location`, because
    this list feeds TWO facts. `contains` (Task 16) is satisfied by either test -- enclosing an
    actor's full extent already implies its `Location` sits inside the container's AABB, so the
    narrower test never dropped a real `contains`. `crosses` direction 2 (Task 12) is the one that
    needs the wider test: it asks whether a point actor's collision cylinder reaches INTO the
    surveyed brush, which is true for cylinders whose `Location` sits outside it. Under a
    bare-`Location` filter that crossing appeared when you surveyed the point actor and vanished
    when you surveyed the brush -- exactly the asymmetry `crosses_facts_for` is written to rule
    out.

    `pad=0` on the candidate: the pad is the solve's truncation safety margin, not part of an
    actor's shape, and the surveyed actor's region already carries it. Same call shape
    `neighborhood` and `near_brushes` use for their own candidates."""
    region = region_of(surveyed_actor, defaults)
    out = []
    for name in level.order:
        a = level.actors[name]
        if a.brush is not None or a.location is None:
            continue
        if aabb_intersects(region_of(a, defaults, Decimal(0)), region):
            out.append(a)
    return out
```

- [ ] **Step 5: Run the tests**

Run: `bin/test -k test_actor_survey -v`
Expected: PASS (seven tests)

- [ ] **Step 6: Run the whole suite, then commit**

Run: `bin/test`

```bash
git add uedcli/actor_survey.py uedcli/tests/survey_scenarios.py uedcli/tests/test_actor_survey.py
git commit -m "actor survey: bounded-neighborhood selection"
```

---

### Task 8: the raw tier, and the `actor survey` CLI

**Files:**
- Modify: `uedcli/actor_survey.py` (`RawFact`, `RawFacts`, `raw_facts_for`, `format_raw_line`)
- Create: `uedcli/cli/parsers/actor_survey.py`
- Modify: `uedcli/cli/parsers/actor.py` (wire it in)
- Create: `uedcli/cli/commands/actor/survey.py`
- Modify: `uedcli/cli/commands/actor/routes.py` (a `survey` branch)
- Modify: `uedcli/tests/survey_scenarios.py` (two more builders)
- Modify: `uedcli/tests/fixtures/parser_baseline/*.json` (regenerated)
- Test: `uedcli/tests/test_actor_survey.py`, `uedcli/tests/test_cli_actor_survey.py` (new)

**Interfaces:**
- Consumes: Task 7's `near_brushes`/`nearby_point_actors`; `actorgraph.classify_pair`,
  `decompose_convex`, `point_in_brush`, `DegenerateBrushError`, `_node_tag`, `_node_bracket`,
  `NodeTag`, `Edge` — all existing and unchanged.
- Produces:

```python
@dataclass(frozen=True)
class RawFact:
    src: str
    dst: str
    relation: str                          # "touches" | "contains" | "carves"
    matched_pair: tuple[int, int] | None
    area_estimate: float | None

@dataclass(frozen=True)
class RawFacts:
    facts: list[RawFact]
    nodes: dict[str, actorgraph.NodeTag]   # every name any fact mentions, plus the surveyed one
    skipped: list[tuple[str, str]]         # (name, reason) for a degenerate NEIGHBOUR brush

def raw_facts_for(level, class_index, name: str, defaults, *, cells: dict | None = None) -> RawFacts
def format_raw_line(fact: RawFact, nodes: dict) -> str
```

  `cells` is the shared `{actor_name: [ConvexCell]}` decomposition cache `decompose_convex` already
  takes. The caller (Task 18's orchestrator) owns ONE dict per survey call and passes it to both
  tiers, so no brush is decomposed twice in one survey.

  **Why not `actorgraph.build_graph`:** it is whole-level and `O(brushes^2)`, and the spike measured
  it as the genuinely expensive half — 12x a full CSG solve at 208 brushes, and unfinishable above
  that (spike.md §4). `raw_facts_for` runs the same `classify_pair` over the bounded neighborhood
  instead, which the spike timed at a median 31 ms.

- [ ] **Step 1: Write the failing tests**

Add two builders to `uedcli/tests/survey_scenarios.py` first:

```python
# --------------------------------------------------------------------- Task 8's scenarios

def niche_carved_into_wall() -> Scenario:
    """Trunk order: Wall, Niche, Bystander.

    * `Wall`      512 x 64 x 512 Add      at (0, 0, 0)     — x,z in [-256, 256], y in [-32, 32]
    * `Niche`     128 x 128 x 128 Subtract at (0, 0, 0)    — straddles the wall, removing real matter
    * `Bystander` 64^3 Add                at (0, 96, 0)    — flush against the wall's +Y face (y=32)

    `Niche` is LATER in trunk order than `Wall`, so the raw tier's order heuristic calls it
    `carves`; the csg tier confirms it (Task 17). `Bystander` touches the wall and nothing else.
    """
    return _scenario([
        brush("Wall", (512, 64, 512), (0, 0, 0)),
        brush("Niche", (128, 128, 128), (0, 0, 0), csg="subtract"),
        brush("Bystander", (64, 64, 64), (0, 96, 0)),
    ])


def room_contains_a_mover() -> Scenario:
    """Trunk order: Room, Door.

    * `Room` 1024^3 Subtract at (0, 0, 0)
    * `Door` 64 x 8 x 128 `DeusEx.DeusExMover` at (0, 0, 0) — fully inside Room's void

    A Mover carries no `CsgOper` at all, so trunk order is meaningless for it and `classify_pair`
    always reports `contains` from the Subtract (`actorgraph.py:599-602`). `StubClassIndex` puts
    `DeusEx.DeusExMover` under `Engine.Mover` via its `mover_classes` default.
    """
    door = make_brush_actor("Door", cube(64, 8, 128), location=_dec((0, 0, 0)),
                            mover_class="DeusEx.DeusExMover")
    return _scenario([brush("Room", (1024, 1024, 1024), (0, 0, 0), csg="subtract"), door])
```

Confirm `StubClassIndex`'s `MOVER_CLASSES` default really contains `DeusEx.DeusExMover`
(`grep -n "MOVER_CLASSES" uedcli/tests/conftest.py`). If it does not, pass the class explicitly:
`StubClassIndex(mover_classes=("Engine.Mover", "DeusEx.DeusExMover"))` via a `_scenario` argument.

Then append to `uedcli/tests/test_actor_survey.py`:

```python
def test_raw_tier_reports_touches_and_carves_for_the_surveyed_brush():
    sc = scen.niche_carved_into_wall()
    got = actor_survey.raw_facts_for(sc.level, sc.index, "Wall", sc.defaults)
    rels = {(f.src, f.relation, f.dst) for f in got.facts}
    assert ("Niche", "carves", "Wall") in rels
    assert ("Wall", "touches", "Bystander") in rels


def test_raw_tier_spells_it_carves_with_the_subtract_leading_not_carved_by():
    """`level graph` prints `carved_by` with the ADD leading (`actorgraph.classify_pair`'s last
    line). `actor survey` prints `carves` with the SUBTRACT leading, whichever side is surveyed --
    the owner's 'one name per interaction, flip the sides to match' ruling (spec, Round 6). This is
    a presentation choice in THIS verb only; `level graph` is untouched."""
    sc = scen.niche_carved_into_wall()
    for surveyed in ("Wall", "Niche"):
        facts = actor_survey.raw_facts_for(sc.level, sc.index, surveyed, sc.defaults).facts
        carve = next(f for f in facts if f.relation == "carves")
        assert (carve.src, carve.dst) == ("Niche", "Wall")
        assert not any(f.relation == "carved_by" for f in facts)


def test_raw_touches_puts_the_surveyed_actor_first_and_swaps_its_matched_pair_with_it():
    """A symmetric relation leads with whoever you asked about. `Edge.matched_pair` is glued to
    `(src, dst)` positionally, so flipping the names MUST flip the pair too -- a rename-only flip
    renders a real face selector against the wrong brush (spec, Output shape)."""
    sc = scen.niche_carved_into_wall()
    a = next(f for f in actor_survey.raw_facts_for(sc.level, sc.index, "Wall", sc.defaults).facts
             if f.relation == "touches" and f.dst == "Bystander")
    b = next(f for f in actor_survey.raw_facts_for(sc.level, sc.index, "Bystander",
                                                   sc.defaults).facts
             if f.relation == "touches" and f.dst == "Wall")
    assert (a.src, a.dst) == ("Wall", "Bystander")
    assert (b.src, b.dst) == ("Bystander", "Wall")
    assert a.matched_pair is not None
    assert b.matched_pair == (a.matched_pair[1], a.matched_pair[0])


def test_from_edge_flips_a_symmetric_fact_when_the_surveyed_actor_is_the_edges_dst():
    """`_from_edge`'s flip branch, exercised directly.

    `raw_facts_for` always passes the surveyed actor as `classify_pair`'s `name_a`, so every edge it
    hands `_from_edge` already leads with the surveyed name and the flip branch never fires through
    that path. The branch is still the thing that GUARANTEES the orientation: without this test it
    is unexercised code, and a later change to the call order would silently start emitting
    `touches` facts led by the wrong actor with nothing going red. Constructed here as a bare
    `actorgraph.Edge` rather than through a scenario, because no scenario can reach it.
    """
    from uedcli import actorgraph
    edge = actorgraph.Edge(src="Other", dst="Wall", relation="touches", directed=False,
                           matched_pair=(2, 5), area_estimate=64.0)
    fact = actor_survey._from_edge(edge, "Wall")
    assert (fact.src, fact.dst) == ("Wall", "Other")
    assert fact.matched_pair == (5, 2)          # glued to (src, dst) positionally
    assert fact.area_estimate == 64.0


def test_raw_tier_reports_contains_for_a_mover_inside_a_subtract():
    sc = scen.room_contains_a_mover()
    facts = actor_survey.raw_facts_for(sc.level, sc.index, "Room", sc.defaults).facts
    assert ("Room", "contains", "Door") in {(f.src, f.relation, f.dst) for f in facts}


def test_raw_tier_reports_contains_for_a_point_actor_inside_the_surveyed_brush():
    sc = scen.room_with_pillar_and_light()
    facts = actor_survey.raw_facts_for(sc.level, sc.index, "Room", sc.defaults).facts
    assert ("Room", "contains", "Light") in {(f.src, f.relation, f.dst) for f in facts}


def test_raw_tier_surveying_the_point_actor_shows_the_same_containment():
    """`contains` is fixed-direction: the container leads whichever side you survey."""
    sc = scen.room_with_pillar_and_light()
    facts = actor_survey.raw_facts_for(sc.level, sc.index, "Light", sc.defaults).facts
    assert ("Room", "contains", "Light") in {(f.src, f.relation, f.dst) for f in facts}


def test_raw_tier_does_not_use_build_graph():
    """`build_graph` is whole-level and O(brushes^2) -- the measured expensive half (spike.md §4).
    The raw tier must run `classify_pair` over the bounded neighborhood instead."""
    import inspect
    src = inspect.getsource(actor_survey.raw_facts_for)
    assert "build_graph" not in src
    assert "classify_pair" in src


def test_raw_line_format_matches_level_graphs_grammar_with_a_tier_prefix():
    sc = scen.niche_carved_into_wall()
    got = actor_survey.raw_facts_for(sc.level, sc.index, "Wall", sc.defaults)
    touch = next(f for f in got.facts if f.relation == "touches")
    line = actor_survey.format_raw_line(touch, got.nodes)
    assert line.startswith("raw Wall:")
    assert "[Engine.Brush Add] --touches(" in line
    assert "uu^2)--> Bystander:" in line


def test_raw_line_carries_no_idx_or_area_on_a_contains_line():
    sc = scen.room_with_pillar_and_light()
    got = actor_survey.raw_facts_for(sc.level, sc.index, "Room", sc.defaults)
    fact = next(f for f in got.facts if f.relation == "contains")
    line = actor_survey.format_raw_line(fact, got.nodes)
    assert line == ("raw Room [Engine.Brush Subtract] --contains--> Light [Engine.Light]")
```

And a new CLI file `uedcli/tests/test_cli_actor_survey.py`:

```python
"""The `actor survey` CLI seam: parser wiring, dispatch, output shape, exit codes.

Follows this codebase's real CLI-test convention (`test_cli_actor_relation_compare.py`,
`test_cli_level_graph.py`): a hand-built `argparse.Namespace` handed to `dispatch.dispatch`, output
read through `capsys`. argparse itself is never invoked except where a test is specifically about
parsing. `conftest._stub_mover_class_index` is autouse, so `resources.mover_index` already returns a
`StubClassIndex` here.
"""
import argparse

import pytest

from uedcli import trunk
from uedcli.cli import dispatch
from uedcli.model import Level
from uedcli.tests import survey_scenarios as scen


def _project(tmp_path, monkeypatch, scenario, name="lvl"):
    proj = tmp_path / "repo"
    (proj / "maps" / name).mkdir(parents=True)
    (proj / "uedcli.toml").write_text('game = "deusex"\n')
    order = scenario.level.order
    trunk.write_level(proj / "maps" / name,
                      Level(actors=dict(scenario.level.actors)),
                      {n: f"{i:04d}" for i, n in enumerate(order)})
    monkeypatch.setenv("UEDCLI_LEVEL", name)
    return proj


def _ns(proj, name, tree=None):
    return argparse.Namespace(cmd="actor", sub="survey", project=str(proj), tree=tree, name=name)


def test_survey_prints_raw_lines_and_a_stderr_summary(tmp_path, monkeypatch, capsys):
    proj = _project(tmp_path, monkeypatch, scen.niche_carved_into_wall())
    assert dispatch.dispatch(_ns(proj, "Wall")) == 0
    out = capsys.readouterr()
    raw = [ln for ln in out.out.splitlines() if ln.startswith("raw ")]
    assert raw
    assert "raw fact(s)" in out.err


def test_survey_unknown_actor_exits_2_naming_it(tmp_path, monkeypatch, capsys):
    proj = _project(tmp_path, monkeypatch, scen.niche_carved_into_wall())
    assert dispatch.dispatch(_ns(proj, "NoSuchActor")) == 2
    assert "Actor not found: NoSuchActor" in capsys.readouterr().err


def test_survey_subparser_exists_and_takes_a_name_and_tree():
    from uedcli.cli.main import build_parser
    ns = build_parser().parse_args(["actor", "survey", "Wall"])
    assert (ns.cmd, ns.sub, ns.name) == ("actor", "survey", "Wall")
    assert hasattr(ns, "tree")
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `bin/test -k "test_actor_survey or test_cli_actor_survey" -v`
Expected: the Task 7 tests still PASS; every new one FAILS.

- [ ] **Step 3: Add the raw tier to `uedcli/actor_survey.py`**

Add `actorgraph` to the module's import block first — Task 7 left it out because nothing there used
it.

```python
@dataclass(frozen=True)
class RawFact:
    """One raw-tier line's worth of information, already in `actor survey`'s OWN presentation form.
    A separate type from `actorgraph.Edge` for one reason: `level graph` spells the third relation
    `carved_by` with the ADD leading, and this verb spells it `carves` with the SUBTRACT leading
    (spec, Round 6). Keeping the rename in the type conversion rather than in the formatter means
    nothing downstream can accidentally print the other spelling."""
    src: str
    dst: str
    relation: str
    matched_pair: tuple[int, int] | None
    area_estimate: float | None


@dataclass(frozen=True)
class RawFacts:
    facts: list
    nodes: dict
    skipped: list


def _flip(fact: RawFact) -> RawFact:
    """Swap a symmetric fact's two sides, carrying `matched_pair` with them. The pair is glued to
    `(src, dst)` POSITIONALLY, so a rename-only flip would render a real face selector against the
    wrong brush (spec, Output shape)."""
    pair = None if fact.matched_pair is None else (fact.matched_pair[1], fact.matched_pair[0])
    return RawFact(src=fact.dst, dst=fact.src, relation=fact.relation,
                   matched_pair=pair, area_estimate=fact.area_estimate)


def _from_edge(edge, surveyed: str) -> RawFact:
    """One `actorgraph.Edge` in this verb's own presentation form.

    The `_flip` branch below is what GUARANTEES a symmetric fact leads with the surveyed actor. It
    happens not to fire through `raw_facts_for`, which always passes the surveyed actor as
    `classify_pair`'s `name_a` -- but that is an invariant of the CALL ORDER, not of this function,
    so the branch stays and is pinned directly by
    `test_from_edge_flips_a_symmetric_fact_when_the_surveyed_actor_is_the_edges_dst`."""
    if edge.relation == "carved_by":
        # level graph: Edge(src=Add, dst=Subtract, relation="carved_by") -- the victim leads.
        # actor survey: the agent leads, and the word is `carves`.
        return RawFact(src=edge.dst, dst=edge.src, relation="carves",
                       matched_pair=None, area_estimate=None)
    fact = RawFact(src=edge.src, dst=edge.dst, relation=edge.relation,
                   matched_pair=edge.matched_pair, area_estimate=edge.area_estimate)
    if edge.relation == "touches" and fact.dst == surveyed:
        return _flip(fact)                       # symmetric: the surveyed actor leads
    return fact


def raw_facts_for(level, class_index, name: str, defaults, *,
                  cells: dict | None = None) -> RawFacts:
    """Every raw-tier fact about `name`, computed over the BOUNDED NEIGHBORHOOD.

    Deliberately not `actorgraph.build_graph`: that walks every brush pair in the level, is
    `O(brushes^2)`, and the spike measured it at 12x a full CSG solve on a 208-brush level and
    unfinishable above that (spike.md §4). This runs the SAME `classify_pair` over
    `near_brushes(...)` instead -- a median 31 ms per survey in the same measurement.

    Raises `ActorNotFoundError` for an unknown name, and `actorgraph.DegenerateBrushError` when the
    SURVEYED actor's own brush cannot be decomposed -- unlike `level graph`, which skips a bad brush
    and carries on over the rest of the level, a single-actor report has nothing left to say. A
    degenerate NEIGHBOUR is skipped and recorded in `skipped`, exactly as `build_graph._safe` does.
    """
    if name not in level.actors:
        raise ActorNotFoundError(name)
    cells = {} if cells is None else cells
    surveyed = level.actors[name]
    order_index = {n: i for i, n in enumerate(level.order)
                   if level.actors[n].brush is not None}
    nodes: dict = {name: actorgraph._node_tag(surveyed, class_index)}
    facts: list[RawFact] = []
    skipped: dict[str, str] = {}

    others = [a for a in near_brushes(level, class_index, surveyed, defaults) if a.name != name]
    points = [a for a in nearby_point_actors(level, surveyed, defaults) if a.name != name]

    if surveyed.brush is not None:
        actorgraph.decompose_convex(surveyed, cache=cells)     # propagates on a bad SURVEYED brush
        for other in others:
            try:
                actorgraph.decompose_convex(other, cache=cells)
            except actorgraph.DegenerateBrushError as e:
                skipped[other.name] = str(e)
                continue
            for edge in actorgraph.classify_pair(name, surveyed, other.name, other,
                                                  order_index=order_index,
                                                  class_index=class_index, cache=cells):
                facts.append(_from_edge(edge, name))
                nodes[other.name] = actorgraph._node_tag(other, class_index)
        # The point-actor containment fan-out `build_graph` does for the whole level, scoped to the
        # surveyed brush: every point actor whose Location falls inside its volume.
        for p in points:
            loc = tuple(float(c) for c in p.location)
            if actorgraph.point_in_brush(surveyed, loc, cache=cells):
                facts.append(RawFact(src=name, dst=p.name, relation="contains",
                                      matched_pair=None, area_estimate=None))
                nodes[p.name] = actorgraph._node_tag(p, class_index)
    else:
        # The surveyed actor IS a point: the same fan-out seen from the other side. `contains` is
        # fixed-direction, so the containing brush still leads.
        if surveyed.location is not None:
            loc = tuple(float(c) for c in surveyed.location)
            for other in others:
                try:
                    if not actorgraph.point_in_brush(other, loc, cache=cells):
                        continue
                except actorgraph.DegenerateBrushError as e:
                    skipped[other.name] = str(e)
                    continue
                facts.append(RawFact(src=other.name, dst=name, relation="contains",
                                      matched_pair=None, area_estimate=None))
                nodes[other.name] = actorgraph._node_tag(other, class_index)

    return RawFacts(facts=facts, nodes=nodes, skipped=sorted(skipped.items()))


def format_raw_line(fact: RawFact, nodes: dict) -> str:
    """One `raw `-prefixed line, in `actorgraph.format_text`'s exact grammar. `:idx` and the area
    annotation ride ONLY a `touches` fact that found a real matched face pair; `contains`/`carves`
    print bare names with no annotation (spec, Output shape)."""
    has_idx = fact.relation == "touches" and fact.matched_pair is not None
    src = f"{fact.src}:{fact.matched_pair[0]}" if has_idx else fact.src
    dst = f"{fact.dst}:{fact.matched_pair[1]}" if has_idx else fact.dst
    rel = fact.relation
    if fact.relation == "touches" and fact.area_estimate is not None:
        rel = f"touches({fact.area_estimate:.4g}uu^2)"
    return (f"raw {src} {actorgraph._node_bracket(nodes[fact.src])} --{rel}--> "
            f"{dst} {actorgraph._node_bracket(nodes[fact.dst])}")
```

- [ ] **Step 4: Add the subparser**

New file `uedcli/cli/parsers/actor_survey.py`:

```python
"""`actor survey NAME` subparser."""
from __future__ import annotations

from ._arguments import _tree_flag


def add_survey_subparser(asub) -> None:
    """Wire `survey` under the `actor` command's subparsers object `asub`."""
    p = asub.add_parser(
        "survey",
        help="every raw and CSG-resolved spatial fact about one actor (brush or not): what it "
             "touches, contains, carves, connects to, and crosses into")
    p.add_argument(
        "name", metavar="NAME",
        help="the actor to survey — exactly one, never a set (both tiers are computed over a "
             "bounded neighborhood of this actor, which is what keeps the cost flat)")
    _tree_flag(p)     # read a named tree explicitly instead of $UEDCLI_LEVEL, like actor show/bbox
```

Confirm `_tree_flag`'s real import path first: it is defined in `uedcli/cli/parsers/_arguments.py`
(line 344) and `brush.py` imports it as `from ._arguments import _tree_flag` — copy that spelling.
`level_sources.resolve_level_source` reads it with `getattr(args, "tree", None)`, so a missing flag
would not crash; it is here because every other read-only `actor` subverb has it and a survey against
a named stash/prefab is a real thing to want.

Wire it in `uedcli/cli/parsers/actor.py` next to Task 2's relation call:

```python
from .actor_survey import add_survey_subparser
```

```python
    add_survey_subparser(asub)
```

- [ ] **Step 5: Add the handler and the route**

New file `uedcli/cli/commands/actor/survey.py`:

```python
"""`actor survey NAME` — every raw and CSG-resolved spatial fact about one actor.

Resolves its own source/class-index the way every actor feature module does (`preview.py` is the
closest analog: it also needs a native CSG solve). This slice prints the RAW tier only; Task 18 adds
the csg tier and the combined summary.
"""
from __future__ import annotations

import sys

from ... import level_sources, resources
from .... import actor_survey, actorgraph
from ....classdefaults import ClassDefaults


def run(args) -> int:
    """`actor survey` entry. Dispatch routes every `actor survey` here."""
    project = resources.resolve_project(args)
    src = level_sources.resolve_level_source(args)
    index = resources.mover_index(args, "actor survey", project)
    level = src.load()
    try:
        defaults = ClassDefaults(resources.schema_resolver_for(project))
        raw = actor_survey.raw_facts_for(level, index, args.name, defaults)
    except actor_survey.ActorNotFoundError as e:
        print(str(e), file=sys.stderr)
        return 2
    except actorgraph.DegenerateBrushError as e:
        print(f"actor survey: {e}", file=sys.stderr)
        return 2
    for bad_name, reason in raw.skipped:
        print(f"actor survey: skipping {reason}", file=sys.stderr)
    for fact in raw.facts:
        print(actor_survey.format_raw_line(fact, raw.nodes))
    print(f"actor survey: {len(raw.facts)} raw fact(s) for {args.name}", file=sys.stderr)
    return 0
```

Check the relative-import depth against a sibling before committing: `preview.py` (same directory)
uses `from ... import ingest, level_sources, …` for `uedcli.cli.*` and `from .... import query,
trunk` for `uedcli.*`. `resources` lives at `uedcli/cli/resources.py`, so it is a three-dot import.
`bad_name` is unused in the loop body on purpose — `reason` already begins with the actor's name
(`DegenerateBrushError`'s own message), and repeating it makes the line stutter, exactly as
`_level_graph`'s own comment records (`uedcli/cli/commands/level.py:810-812`).

`ClassDefaults` is here because `region_of` resolves a non-brush actor's collision extent from its
class defaults (Task 7). The `uprops.SchemaError` a survey can raise comes from
`defaults.for_class(...)`, called inside `raw_facts_for` — not from `schema_resolver_for`, which
only wraps `packages.schema_search_dirs` and returns an empty search path rather than raising when
there is no project or games config. Both sit inside the `try`; this slice has no `SchemaError`
branch of its own, so the error reaches `dispatch.py`'s generic handler, and Task 18 adds the
handler's own message naming the surveyed actor.

In `uedcli/cli/commands/actor/routes.py`, add after the `relation` branch:

```python
    if args.sub == "survey":
        from . import survey
        return survey.run(args)
```

- [ ] **Step 6: Regenerate the parser baseline**

Run: `.venv/bin/python -m uedcli.tests.parser_baseline`

- [ ] **Step 7: Run the tests**

Run: `bin/test -k "test_actor_survey or test_cli_actor_survey" -v`
Expected: PASS

Run: `bin/test -k "actorgraph or level_graph or parser_baseline"`
Expected: all green — in particular `level graph` must still print `carved_by`, unchanged. This task
touches none of its code, and that is what these tests confirm.

- [ ] **Step 8: Run the whole suite, then commit**

Run: `bin/test`

```bash
git add uedcli/actor_survey.py uedcli/cli/parsers/actor_survey.py uedcli/cli/parsers/actor.py
git add uedcli/cli/commands/actor/survey.py uedcli/cli/commands/actor/routes.py
git add uedcli/tests/survey_scenarios.py uedcli/tests/test_actor_survey.py
git add uedcli/tests/test_cli_actor_survey.py uedcli/tests/fixtures/parser_baseline/
git commit -m "actor survey: raw tier and CLI"
```

---

## Part C — the native foundation for the csg tier

Two tasks, and one design decision worth stating up front because Part D rests on it.

**Why a new Rust query rather than wrapping `CollisionModel::point_check`.** `point_check`
(`collision.rs:236`) is the engine's BOX path and its own doc comment says it returns "true when the
box is in **free** space" — so it is not a solidity predicate at all, and a wrapper returning it
unchanged would report every solid point as free. Negating it would fix the polarity but not the
bigger problem: the box path decides via the terminal leaf's `iCollisionBound` hull, and the spike
recorded explicitly that this half is untraced ("whether `bspBuildBounds` gives a thin semisolid slab
a hulled solid leaf is untraced by anyone", spike.md §1) and that nothing it measured depends on it,
because `crosses` needs the ZERO-EXTENT question. The 1522-actor clearance measurement, the CSG-kind
table, and the committed regression `uedcli/tests/test_csg_kind_facts.py` all use the zero-extent
node walk instead. So Task 9 ports exactly that walk into Rust, where its three primitives
(`is_csg`/`child`/`combine_state`) already live and are already imported into `collision.rs`.

**Why one solve, not five.** Each of the five csg relations needs the same resolved world. Task 10
adds a single `solve_world_probe` that returns the surviving surfaces AND a solidity handle from one
`build_geometry_bspcsg` call, and Task 11 puts both into a `SurveyContext` built once per survey.
`CollisionModel::level` deep-clones the node and hull arrays (`collision.rs:102-104`), so the handle
is built once too.

### Task 9: expose a point-in-solid query from `uedcli-native`

**Files:**
- Modify: `uedcli-native/src/collision.rs` (a new `CollisionModel::point_is_solid`, plus a unit test
  in the existing `#[cfg(test)]` module at line 715)
- Modify: `uedcli-native/src/lib.rs` (a `Solidity` pyclass and a `Built::solidity()` method)
- Test: `uedcli/tests/test_native_solidity.py` (new)

**Interfaces:**
- Consumes: `linecheck::{is_csg, child, combine_state, plane_dot, FRONT, BACK}` — already imported
  into `collision.rs` at line 18, no new `use` needed there.
- Produces:

```rust
impl CollisionModel { pub fn point_is_solid(&self, loc: Vec3) -> bool }
#[pymethods] impl Built { fn solidity(&self) -> Solidity }
#[pymethods] impl Solidity {
    fn point_is_solid(&self, p: (f32, f32, f32)) -> bool
    fn any_point_solid(&self, points: Vec<(f32, f32, f32)>) -> bool
}
```

  Python side: `built.solidity()` once per solve, then `.point_is_solid((x, y, z))` or
  `.any_point_solid([(x, y, z), ...])`. `any_point_solid` is not speculative surface — it is the
  exact primitive the spike's `_box_free` needs (a 27-point sample, cylindrical here — Task 11's
  `cylinder_sample_points`), and the spike's bisection ran that sample ~20 times per candidate, so
  it keeps the FFI boundary bulk rather than per-op as `lib.rs`'s own module docstring requires.

- [ ] **Step 1: Write the failing test**

New file `uedcli/tests/test_native_solidity.py`:

```python
"""`uedcli_native`'s point-in-solid query, against the SAME scenario and the SAME expected answers
that `test_csg_kind_facts.py` already pins with its own Python port of the walk.

That file's `point_is_solid` is the reference: it is a direct port of the zero-extent form of the
engine's collision walk (`linecheck.rs`'s `is_csg`/`child`/`combine_state` plus `collision.rs`'s
entry state), it is what the spike's 1522-actor clearance measurement used, and it is already
committed and green. The native query must agree with it exactly — that is what makes this a real
regression rather than a restatement.
"""
from __future__ import annotations

import pytest

from uedcli.tests.test_csg_kind_facts import LEFT, RIGHT, _solve, point_is_solid

uedcli_native = pytest.importorskip("uedcli_native")


@pytest.mark.parametrize("kind,left,right", [
    ("add", True, False),            # an Add contributes solid; a later Subtract carves it
    ("semisolid", True, True),       # contributes solid, and no Subtract can carve it
    ("nonsolid", False, False),      # contributes no solid at all
])
def test_native_point_is_solid_matches_the_committed_python_walk(kind, left, right):
    _, _, model = _solve(kind)
    built = _built(kind)
    sol = built.solidity()
    assert sol.point_is_solid(LEFT) is left
    assert sol.point_is_solid(RIGHT) is right
    # ...and agrees with the reference walk over the same parsed model, not just with the table.
    assert sol.point_is_solid(LEFT) == point_is_solid(model, LEFT)
    assert sol.point_is_solid(RIGHT) == point_is_solid(model, RIGHT)


def test_any_point_solid_is_true_when_any_sample_is_inside_solid():
    built = _built("add")
    sol = built.solidity()
    assert sol.any_point_solid([RIGHT, LEFT]) is True     # LEFT is solid
    assert sol.any_point_solid([RIGHT]) is False          # the carved half is not
    assert sol.any_point_solid([]) is False


def test_solidity_is_not_point_check_negated():
    """`CollisionModel::point_check` answers the BOX question via the terminal leaf's collision
    hull, and returns true for FREE space (`collision.rs:236`). This query is the zero-extent NODE
    walk instead — the one the spike measured with. Pinned so a later 'simplification' to
    `not point_check(...)` trips here."""
    import inspect
    src = (_repo_root() / "uedcli-native" / "src" / "lib.rs").read_text()
    assert "point_is_solid" in src
    assert "point_check" not in src, "lib.rs must not expose the free-space box query"
    del inspect


def _repo_root():
    from pathlib import Path
    return Path(__file__).resolve().parents[2]


def _built(kind):
    """The same three-brush scenario `test_csg_kind_facts._solve` builds, but returning the native
    `Built` handle rather than the parsed model. Uses that module's own `_brush` so the geometry can
    never drift from the committed regression's."""
    import dataclasses  # noqa: F401  (kept in sync with test_csg_kind_facts' own imports)
    from uedcli import preview_native as pn
    from uedcli.tests.test_csg_kind_facts import PF_NOTSOLID, PF_SEMISOLID, _brush
    oper, flags = {
        "add": ("CSG_Add", 0),
        "semisolid": ("CSG_Add", PF_SEMISOLID),
        "nonsolid": ("CSG_Add", PF_NOTSOLID),
    }[kind]
    actors = [_brush("Room", (1024, 1024, 1024), (0, 0, 0), "CSG_Subtract"),
              _brush("Pillar", (128, 128, 512), (0, 0, 0), oper, flags),
              _brush("Cutter", (256, 256, 256), (128, 0, 0), "CSG_Subtract")]
    return uedcli_native.build_geometry_bspcsg([pn._marshal_brush(a) for a in actors])
```

Before running this, confirm `test_csg_kind_facts.py` really exports `LEFT`, `RIGHT`,
`PF_SEMISOLID`, `PF_NOTSOLID`, `_brush`, `_solve` and `point_is_solid` at module level with those
exact names (it does as of this plan — re-check, and adjust the imports rather than copying the
scenario if anything moved).

- [ ] **Step 2: Run the test to verify it fails**

Run: `bin/test -k test_native_solidity -v`
Expected: FAIL — `Built` has no `solidity` attribute.

- [ ] **Step 3: Add the walk to `collision.rs`**

Inside `impl CollisionModel`, next to `point_region` and `point_check`:

```rust
    /// Is `loc` inside SOLID space?  The ZERO-EXTENT form of the engine's own collision walk:
    /// `FBspNode::IsCsg` plus the walker's running "outside" state, never a leaf index and never a
    /// `PolyFlags` read (`linecheck.rs`'s `is_csg`/`child`/`combine_state`, and this type's own
    /// entry state).  Going FRONT of a CSG-solid node proves open space, BACK of one proves solid,
    /// a non-CSG node passes the state through unchanged.
    ///
    /// Deliberately NOT `point_check` with a zero extent: that is the BOX path, it decides via the
    /// terminal leaf's `iCollisionBound` hull, and it answers the opposite question (true = free).
    /// It is also the half `dev/docs/spikes/2026-09-23-actor-survey-csg-kind-and-cost/spike.md` §1
    /// records as untraced for a thin semisolid slab.  Nor `point_region`: a semisolid's nodes are
    /// added after the zone pass, so `PointRegion` reports a semisolid's interior as void — pinned
    /// by `uedcli/tests/test_csg_kind_facts.py`.
    pub fn point_is_solid(&self, loc: Vec3) -> bool {
        if self.nodes.is_empty() {
            return !self.root_outside;
        }
        let mut state = self.root_outside;
        let mut i_node = 0i32;
        while i_node != -1 {
            let node = &self.nodes[i_node as usize];
            let side = if plane_dot(&node.plane, &loc) >= 0.0 { FRONT } else { BACK };
            state = combine_state(side, state, is_csg(node, 0, false));
            i_node = child(node, side);
        }
        !state
    }
```

- [ ] **Step 4: Add a Rust unit test**

In `collision.rs`'s existing `#[cfg(test)] mod tests` (line 715), add a test that builds a trivial
model and asserts both branches. Read the module's existing tests first and follow whatever helper
they already use to construct a `Model`/`CollisionModel`; if there is none, assert the empty-model
branch, which needs no construction:

```rust
    #[test]
    fn point_is_solid_on_an_empty_model_is_the_inverse_of_root_outside() {
        let mut m = Model::default();
        m.root_outside = false;                  // a DX level: solid world, Subtract carves
        let cm = CollisionModel::level(&m);
        assert!(cm.point_is_solid(Vec3::new(0.0, 0.0, 0.0)));
        m.root_outside = true;
        let cm = CollisionModel::level(&m);
        assert!(!cm.point_is_solid(Vec3::new(0.0, 0.0, 0.0)));
    }
```

- [ ] **Step 5: Add the PyO3 surface to `lib.rs`**

Beside `Built`:

```rust
/// A built model prepared for point-in-solid queries.  Holds the `CollisionModel` so it is built
/// ONCE per solve: `CollisionModel::level` deep-clones the node and hull arrays
/// (`collision.rs:102`), so rebuilding it per query would clone the whole tree per point.
#[pyclass]
struct Solidity {
    model: collision::CollisionModel,
}

#[pymethods]
impl Solidity {
    /// True when `p` is inside SOLID space (see `CollisionModel::point_is_solid`).
    fn point_is_solid(&self, p: (f32, f32, f32)) -> bool {
        self.model.point_is_solid(model::Vec3::new(p.0, p.1, p.2))
    }

    /// True when ANY of `points` is inside solid.  Bulk by design (§8.1, "never per-op"): the
    /// caller's box test samples 27 points at a time and its bisection runs that ~20 times per
    /// candidate, so this is one crossing instead of 540.
    fn any_point_solid(&self, points: Vec<(f32, f32, f32)>) -> bool {
        points
            .iter()
            .any(|p| self.model.point_is_solid(model::Vec3::new(p.0, p.1, p.2)))
    }
}
```

and, in `#[pymethods] impl Built`:

```rust
    /// A handle for point-in-solid queries against this model.  Build it once per solve.
    fn solidity(&self) -> Solidity {
        Solidity { model: collision::CollisionModel::level(&self.model) }
    }
```

`lib.rs` already refers to `model::Vec3` throughout, so no new import is needed there. `collision`
is declared as a module at the top (`mod collision;`) but may not be referenced yet — if
`collision::CollisionModel` does not resolve, add `use crate::collision;` beside the other `use`
lines. Do NOT add `m.add_class::<Solidity>()` unless `Built` is registered too: `lib.rs` currently
registers no classes at all (`grep -n "add_class" uedcli-native/src/lib.rs` returns nothing), and a
returned pyclass works without registration. Match the file's own convention rather than introducing
a second one.

- [ ] **Step 6: Rebuild the native extension and run the tests**

Run: `bin/test -k test_native_solidity -v`
(`bin/test` builds `uedcli_native` into the venv as part of its run — `dev/docs/rules/tests.md`.)
Expected: PASS

- [ ] **Step 7: Run the Rust goldens**

Run: `bin/test -k "nothing_matches_this"` once if you want a pytest-free pass, or simply the full
`bin/test` below — it runs `cargo test` in the container every time
(`dev/docs/rules/tests.md`).
Expected: green.

- [ ] **Step 8: Run the whole suite, then commit**

Run: `bin/test`

```bash
git add uedcli-native/src/collision.rs uedcli-native/src/lib.rs
git add uedcli/tests/test_native_solidity.py
git commit -m "native: expose a point-in-solid query on a built model"
```

---

### Task 10: one solve, two answers — `solve_world_probe` and the deduped face set

**Files:**
- Modify: `uedcli/preview_native.py` (extract `_solve_world`; add `WorldProbe` and
  `solve_world_probe`; `solve_world_surfaces` keeps its exact signature and behavior)
- Modify: `uedcli/actor_survey.py` (`CSG_TOLERANCE`, `CsgFace`, `csg_faces`)
- Test: `uedcli/tests/test_actor_survey.py`, `uedcli/tests/test_preview_native.py`

**Interfaces:**
- Consumes: `uedcli_native.build_geometry_bspcsg`, `uedcli_native.serialize_model`,
  `native.umodel.parse_model_body`, `_node_polys`, `_marshal_brush`, `_csg_oper_or_skip`,
  `movers.is_mover`, `normalize.is_builder_brush` — all existing, all already used by
  `solve_world_surfaces` itself.
- Produces:

```python
# uedcli/preview_native.py
@dataclass(frozen=True)
class WorldProbe:
    world_surfaces: list      # list[SolvedSurface] — the same objects solve_world_surfaces returns
    solidity: object | None   # a uedcli_native.Solidity, or None when the set had no world CSG brush

def solve_world_probe(actors, index) -> WorldProbe

# uedcli/actor_survey.py
CSG_TOLERANCE: float = 0.015

@dataclass(frozen=True)
class CsgFace:
    owner: str            # the authoring actor's name
    normal: tuple         # unit normal, sign-canonicalized (see csg_faces)
    offset: float         # dot(normal, a point on the plane)
    verts: list           # ONE representative surviving fragment's world ring

def csg_faces(probe, region) -> list[CsgFace]
```

**Why the face set is deduped by (owner, plane), and why that is the operative form of the spec's
own soundness constraint.** A `SolvedSurface` is one BSP fragment: a single authored face routinely
splits into many, so a naive per-surf loop would report the same relationship several times. Dedup
fixes that — and it is also how the spec's rule "`touches`/`crosses` must be decided by plane
coincidence within the tolerance, never by 'does a face exist here'" gets implemented. Collapsing
every coplanar fragment of one owner to one candidate PLANE means a redundant coplanar face appearing
or vanishing in a truncated solve cannot change a reported fact, which is exactly what the spike's
two measured structural residuals (2 of 140 surveys, both exact-coplanar ties) require.

**The honest limit, stated rather than implied.** If the ONLY face of owner `X` on that plane
vanishes from the truncated solve, the fact about `X` does vanish with it — the dedup bounds the
damage to "a redundant duplicate", not to "the last one". In both residuals the spike actually
measured, the divergent face lay exactly on an ADJACENT brush's face plane, so another owner still
supplied the same plane and no answer moved. That is the measured position; it is not a proof of
immunity, and Task 19's truncation regression is what watches it.

- [ ] **Step 1: Write the failing tests**

Append to `uedcli/tests/test_preview_native.py`:

```python
def test_solve_world_probe_returns_surfaces_and_a_solidity_handle():
    """One native solve, two answers. `solve_world_surfaces` keeps its own exact behavior — the
    shipped `actor diagram --mode fullbright` path must not move."""
    room = make_brush_actor("Room", cube(1024, 1024, 1024), csg="subtract")
    inner = make_brush_actor("Inner", cube(256, 256, 256), csg="add")
    actors = [room, inner]
    probe = pn.solve_world_probe(actors, IDX)
    assert len(probe.world_surfaces) == len(_solve(actors).world_surfaces)
    assert probe.solidity is not None
    assert probe.solidity.point_is_solid((0.0, 0.0, 0.0)) in (True, False)


def test_solve_world_probe_on_a_set_with_no_world_csg_brush_has_no_solidity():
    """A complete answer, not a partial one: a set with no world CSG brush resolves to no faces and
    no solid, so there is nothing to query."""
    probe = pn.solve_world_probe([Actor(name="Light1", cls="Engine.Light")], IDX)
    assert probe.world_surfaces == []
    assert probe.solidity is None


def test_solve_world_surfaces_not_built_message_is_unchanged_by_the_extraction(monkeypatch):
    """The shipped user-facing text on `actor diagram --mode fullbright`'s path. Extracting
    `_solve_world` must not reword it, so it is pinned here verbatim — nothing pinned it before.
    `UEDCLI_NATIVE_EXT_FRESH=0` makes `native_ext.import_native` raise `NativeExtensionStaleError`,
    which subclasses `ImportError` (`test_native_ext.py`), so the not-built branch is reached
    without uninstalling anything."""
    monkeypatch.setenv("UEDCLI_NATIVE_EXT_FRESH", "0")
    room = make_brush_actor("Room", cube(256, 256, 256), csg="subtract")
    with pytest.raises(pn.NativePreviewError) as excinfo:
        pn.solve_world_surfaces([room], IDX)
    assert str(excinfo.value) == (
        "the uedcli_native extension is not built — `actor diagram --mode fullbright` needs it "
        "(build with `maturin develop`, or run bin/test once)")


def test_solve_world_probe_not_built_message_names_actor_survey(monkeypatch):
    """The NEW path gets its own feature name in the same sentence — the only difference between
    the two messages."""
    monkeypatch.setenv("UEDCLI_NATIVE_EXT_FRESH", "0")
    room = make_brush_actor("Room", cube(256, 256, 256), csg="subtract")
    with pytest.raises(pn.NativePreviewError) as excinfo:
        pn.solve_world_probe([room], IDX)
    assert "`actor survey` needs it" in str(excinfo.value)
```

These follow the module's own conventions rather than inventing helpers: `pn`, `IDX`
(`StubClassIndex()` at module scope — the OFFLINE resolver; `_ued22_index()` loads the real UED22
corpus and is only for mesh-actor tests), `cube`/`make_brush_actor` from `uedcli.builders`, `Actor`
from `uedcli.model`, and `_solve(actors)`, the module's existing one-line wrapper for
`pn.solve_world_surfaces(actors, IDX)`. All are already imported at the top of the file; add
nothing. The `Room`/`Inner` pair is the same shape
`test_solve_carves_room_shows_interior_add_and_hides_buried_add` uses.

Copy the expected string in `test_solve_world_surfaces_not_built_message_is_unchanged_by_the_extraction`
from the real `uedcli/preview_native.py:1152` rather than from this plan — including the em dash and
the backticks — so the test pins what ships, not what this document retyped.

Append to `uedcli/tests/test_actor_survey.py`:

```python
def test_csg_faces_collapses_every_coplanar_fragment_of_one_owner_to_one_candidate():
    """A `SolvedSurface` is a BSP FRAGMENT: one authored face routinely splits into many. Dedup by
    (owner, plane) is what stops one relationship being reported N times — and it is also how the
    spec's 'decide by plane coincidence, never by face existence' rule is implemented."""
    import pytest
    pytest.importorskip("uedcli_native")
    sc = scen.niche_carved_into_wall()
    surveyed = sc.level.actors["Wall"]
    probe = _probe(sc, "Wall")
    faces = actor_survey.csg_faces(probe, actor_survey.region_of(surveyed, sc.defaults))
    keys = [(f.owner, tuple(round(c, 3) for c in f.normal), round(f.offset, 3)) for f in faces]
    assert len(keys) == len(set(keys))
    # The wall is a box: at most 6 distinct planes, however many fragments the carve produced.
    assert sum(1 for f in faces if f.owner == "Wall") <= 6
    assert len(probe.world_surfaces) > sum(1 for f in faces if f.owner == "Wall")


def test_csg_faces_normal_sign_is_canonical_so_one_plane_has_one_key():
    """Two fragments of the same plane can come back wound oppositely. The key must not depend on
    which one was seen first."""
    import pytest
    pytest.importorskip("uedcli_native")
    sc = scen.niche_carved_into_wall()
    faces = actor_survey.csg_faces(_probe(sc, "Wall"),
                                   actor_survey.region_of(sc.level.actors["Wall"], sc.defaults))
    for f in faces:
        first = next(c for c in f.normal if abs(c) > 1e-9)
        assert first > 0


def test_csg_faces_drops_a_face_that_only_shares_one_coordinate_band_with_the_region():
    """The region filter is an AABB INTERSECTION, not a per-axis OR. `Wall` is 512x64x512 at the
    origin, so its +Y face sits at y=32 and its +X face at x=256. A 2uu region on the +Y face
    shares the +X face's y band (that ring spans y=-32..32) while sitting 256 uu away from it: an
    OR-across-axes test keeps that face, an intersection test drops it."""
    import pytest
    pytest.importorskip("uedcli_native")
    sc = scen.niche_carved_into_wall()
    probe = _probe(sc, "Wall")
    region = ((-1.0, 31.0, -1.0), (1.0, 33.0, 1.0))      # 2uu box on the wall's +Y face
    planes = {(tuple(round(c, 3) for c in f.normal), round(f.offset, 3))
              for f in actor_survey.csg_faces(probe, region)}
    assert ((0.0, 1.0, 0.0), 32.0) in planes             # the face the region is on
    assert ((1.0, 0.0, 0.0), 256.0) not in planes        # 256uu away — never a candidate
```

Both asserted planes are read off the fixture's authored geometry, not off a solve that was run.
If the solve does not produce the +Y plane at all (a fragment of it is enough), print the whole
`planes` set before touching the assertion — a missing +Y face would be a finding about the solve,
not a test to relax. The second assertion is the one that must not be weakened: it is the whole
point of the test.

and a small helper at the top of the test module:

```python
def _probe(sc, name):
    """The bounded-neighborhood solve for one surveyed actor in a scenario."""
    from uedcli.preview_native import solve_world_probe
    surveyed = sc.level.actors[name]
    return solve_world_probe(actor_survey.neighborhood(sc.level, sc.index, surveyed, sc.defaults),
                             sc.index)
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `bin/test -k "solve_world_probe or csg_faces or not_built_message" -v`
Expected: FAIL — neither `solve_world_probe` nor `csg_faces` exists. The one exception is
`test_solve_world_surfaces_not_built_message_is_unchanged_by_the_extraction`, which must PASS from
the start: it pins the message as it ships TODAY, and a failure here means the string was copied
wrong, not that the feature is missing.

- [ ] **Step 3: Extract the shared solve in `preview_native.py`**

Read `solve_world_surfaces` (lines 1139-1189) in full first. Split its body without changing what it
returns:

```python
def _solve_world(actors, index, *, needs: str):
    """The shared body of `solve_world_surfaces`/`solve_world_probe`: filter `actors` to the world
    CSG brushes (movers and the builder brush excluded, a non-world CsgOper skipped), build them
    natively in the order given -- the actor-set order IS the CSG evaluation order -- and parse the
    result back. Returns `(built, model, join)`, or `(None, None, [])` when the set carries no world
    CSG brush at all. Raises `NativePreviewError` if the extension is not built or the solve fails.

    `needs` names the caller's user-facing feature in the not-built message. It is a parameter and
    not a fixed string so that `solve_world_surfaces`'s message stays BYTE-IDENTICAL to the one it
    ships today -- that text is what a user sees when `actor diagram --mode fullbright` hits an
    unbuilt extension, and this extraction must not reword it."""
    try:
        from uedcli.native_ext import import_native
        uedcli_native = import_native()
    except ImportError:
        raise NativePreviewError(
            f"the uedcli_native extension is not built — {needs} needs it "
            "(build with `maturin develop`, or run bin/test once)") from None

    brushes, join = [], []
    for actor in actors:
        if actor.brush is None:
            continue
        if movers.is_mover(actor, index) or is_builder_brush(actor):
            continue
        if _csg_oper_or_skip(actor.name, dict(actor.props)) is None:
            continue
        brushes.append(_marshal_brush(actor))
        join.append(actor)
    if not brushes:
        return None, None, []
    try:
        built = uedcli_native.build_geometry_bspcsg(brushes)
        body = uedcli_native.serialize_model(built)
    except uedcli_native.BuildError as ex:
        raise NativePreviewError(f"native CSG solve failed: {ex}") from ex
    from .native.umodel import parse_model_body
    return built, parse_model_body(body, 0, len(body)), join


def _surfaces_from(model, join) -> list:
    """`model`'s surviving node polys as `SolvedSurface`s, joined back to their source brush poly.
    An out-of-range owner or poly index yields a surface with `actor`/`poly_index` None (it renders
    flat grey and names no actor) -- the same guard `solve_world_surfaces` has always applied."""
    out = []
    for world_verts, i_actor, i_brush_poly, poly_flags, _i_surf in _node_polys(model):
        if 0 <= i_actor < len(join) and 0 <= i_brush_poly < len(join[i_actor].brush.polys):
            out.append(SolvedSurface(join[i_actor], i_brush_poly, world_verts, poly_flags))
        else:
            out.append(SolvedSurface(None, None, world_verts, poly_flags))
    return out
```

Rewrite `solve_world_surfaces` to use them, keeping its signature, its docstring's meaning and its
`mover_polys` half exactly as they are:

```python
def solve_world_surfaces(actors, index, search_files=None) -> SolvedWorld:
    """<unchanged docstring>"""
    _built, model, join = _solve_world(
        actors, index, needs="`actor diagram --mode fullbright`")
    world_surfaces = [] if model is None else _surfaces_from(model, join)
    mover_polys = []
    for actor in actors:
        if actor.brush is not None and movers.is_mover(actor, index):
            mover_polys += _mover_actor_world_polys(actor)
    return SolvedWorld(world_surfaces=world_surfaces, mover_polys=mover_polys)
```

Then add the probe:

```python
@dataclass(frozen=True)
class WorldProbe:
    """One native CSG solve, kept in the form `actor survey`'s csg tier needs: the surviving world
    surfaces (the same `SolvedSurface` objects `solve_world_surfaces` returns) AND a point-in-solid
    handle over the SAME built model, from the same single `build_geometry_bspcsg` call.

    `solidity` is None when the actor set carried no world CSG brush. That is a complete answer, not
    a partial one -- an empty world has no faces and no solid, so there is nothing to query."""
    world_surfaces: list
    solidity: object | None


def solve_world_probe(actors, index) -> WorldProbe:
    """`solve_world_surfaces`'s sibling for `actor survey`: same solve, same surfaces, plus the
    solidity handle the csg tier's `crosses`/`connects` need. Movers are excluded from world CSG
    here exactly as they are there -- a Mover's own matter is read from its authored brush, never
    from the world model."""
    built, model, join = _solve_world(actors, index, needs="`actor survey`")
    if built is None:
        return WorldProbe(world_surfaces=[], solidity=None)
    return WorldProbe(world_surfaces=_surfaces_from(model, join), solidity=built.solidity())
```

The `needs=` values are the ONLY thing that differs between the two not-built messages.
`solve_world_surfaces` passes the exact phrase its shipped message already contains
(`uedcli/preview_native.py:1152`), so a user on the `actor diagram --mode fullbright` path sees the
same sentence, character for character, as before this refactor. Diff the two strings before
committing; nothing else in that message may move.

- [ ] **Step 4: Add `CSG_TOLERANCE`, `CsgFace` and `csg_faces` to `uedcli/actor_survey.py`**

```python
# The csg tier's coincidence tolerance, in world units: the engine's own THRESH_POINTS_ARE_NEAR
# (`uedcli-native/src/bspcsg.rs`). Resolved point coordinates are only reproducible to the CSG
# point-dedup thresholds, so nothing finer is a real geometric distinction in a resolved model --
# and every perturbation the bounded-neighborhood truncation can introduce is inside this band
# (spike.md §3 and §4 residual 2). It sits comfortably under the 0.043 uu smallest real penetration
# measured on shipped content, so it suppresses no real fact.
#
# NEVER `actorgraph._TOUCH_EPS` (1e-3) here: that is the RAW tier's tolerance, for authored brush
# vertices, a different geometry space with a different noise floor.
CSG_TOLERANCE = 0.015


@dataclass(frozen=True)
class CsgFace:
    """One resolved PLANE authored by one actor, not one BSP fragment.

    `csg_faces` collapses every surviving fragment of the same owner's same plane into one of these.
    That is both the dedup `H1` asks for (a single authored face routinely splits into many, and a
    naive per-surf loop would report one relationship N times) and the operative form of the spec's
    soundness rule: deciding a fact against a PLANE rather than against the existence of a
    particular fragment means a redundant coplanar face appearing or vanishing in a truncated solve
    cannot change the answer."""
    owner: str
    normal: tuple
    offset: float
    verts: list


def _canonical_plane(verts):
    """`(unit normal, offset)` for a world-space ring, with the normal's SIGN canonicalized so two
    oppositely-wound fragments of one plane produce one key. Returns None for a degenerate ring.

    The sign rule is "the first component whose magnitude exceeds 1e-9 is positive" -- arbitrary,
    but deterministic and orientation-free, which is all a plane IDENTITY needs. Facing direction is
    not lost by this: where a relation needs it (Task 12's depth sign), it is measured against the
    surveyed actor's own geometry, not read off this normal."""
    from .texframe import newell
    raw = newell([tuple(float(c) for c in v) for v in verts])
    length = (raw[0] ** 2 + raw[1] ** 2 + raw[2] ** 2) ** 0.5
    if length < 1e-9:
        return None
    n = tuple(c / length for c in raw)
    first = next((c for c in n if abs(c) > 1e-9), 0.0)
    if first < 0:
        n = tuple(-c for c in n)
    v0 = tuple(float(c) for c in verts[0])
    return n, sum(n[i] * v0[i] for i in range(3))


def _ring_meets_region(verts, lo, hi) -> bool:
    """Does a world ring's own AABB overlap the region box -- on ALL THREE axes at once?

    The question a face has to answer is "does this polygon MEET the region", so this is an
    AABB-vs-AABB overlap test: per axis, each box's low end at or below the other's high end, and
    that must hold on EVERY axis (hence `all(...)`, across the three axes of one comparison).
    Same keep/drop decision `bounded_cost.py::face_signature` reaches when it clips each surviving
    surface to the region and keeps whatever still has area, minus the clipping this caller does
    not need: a ring whose AABB misses the box on any axis cannot have any part inside it.
    `CSG_TOLERANCE` of slack on each side so a face exactly flush with the region's edge counts.

    What this replaced, and why: the first draft asked whether ANY vertex had ANY single coordinate
    inside that coordinate's own range, OR-ed across axes. That is not a containment test at all --
    on the 512x64x512 wall fixture, a region around a point on the wall's +Y face also keeps the +X
    face 256 uu away, because that face happens to have a vertex whose y lands in the region's y
    band. It over-selects rather than under-selects, so the cost was wasted candidate planes for
    every relation to re-reject, not missing facts.

    Conservative in one direction only: a ring's AABB can overlap the box while the polygon itself
    does not (a diagonal face clipping a corner). That keeps an extra candidate plane, which the
    per-relation tests then reject on their own geometry -- it never invents a fact."""
    ring_lo = tuple(min(float(v[i]) for v in verts) for i in range(3))
    ring_hi = tuple(max(float(v[i]) for v in verts) for i in range(3))
    return all(ring_lo[i] <= hi[i] + CSG_TOLERANCE and lo[i] <= ring_hi[i] + CSG_TOLERANCE
               for i in range(3))


def csg_faces(probe, region) -> list:
    """Every resolved plane MEETING `region` that an actor authored, one `CsgFace` per (owner, plane).

    A surface with no source actor (`SolvedSurface.actor is None` -- a BSP node that joined to no
    source poly) names nobody and is dropped: a fact must name an actor. Fragments are deduped by
    owner plus plane coincidence within `CSG_TOLERANCE`, by a linear scan per owner rather than by
    rounding to a grid -- a rounded key decides two planes 0.001 uu apart differently depending on
    which side of a bucket boundary they fall, and the neighborhood's face count is small enough
    (hundreds) that the exact test costs nothing."""
    lo, hi = (tuple(float(c) for c in region[0]), tuple(float(c) for c in region[1]))
    by_owner: dict = {}
    for surf in probe.world_surfaces:
        if surf.actor is None:
            continue
        if not _ring_meets_region(surf.world_verts, lo, hi):
            continue
        plane = _canonical_plane(surf.world_verts)
        if plane is None:
            continue
        normal, offset = plane
        seen = by_owner.setdefault(surf.actor.name, [])
        if any(abs(sum(normal[i] * f.normal[i] for i in range(3)) - 1.0) <= 1e-6
               and abs(offset - f.offset) <= CSG_TOLERANCE for f in seen):
            continue
        seen.append(CsgFace(owner=surf.actor.name, normal=normal, offset=offset,
                             verts=[tuple(float(c) for c in v) for v in surf.world_verts]))
    return [f for faces in by_owner.values() for f in faces]
```

The region filter keeps a face whose ring merely OVERLAPS the region — a face partly inside it is
still a face the surveyed actor can meet, and the big bounding walls a `touches` fact is usually
about are exactly the ones that stick far outside. It is an AABB-vs-AABB overlap test, so the
`all(...)` in `_ring_meets_region` is across the three AXES of one comparison, not a tightening of
the keep rule: overlap means the boxes meet on x AND y AND z. Do not turn it back into a
"some vertex lies in the region" test — that keeps faces hundreds of uu away, as
`_ring_meets_region`'s docstring records.

`test_csg_faces_drops_a_face_that_only_shares_one_coordinate_band_with_the_region` (Step 1) is what
pins this: the two filters agree on most geometry, and only a far-off face separates them.

- [ ] **Step 5: Run the tests**

Run: `bin/test -k "solve_world_probe or csg_faces or not_built_message" -v`
Expected: PASS

Run: `bin/test -k "preview_native or actor_survey or csg_kind"`
Expected: all green — in particular every existing `solve_world_surfaces` test, which this task's
refactor must leave byte-for-byte identical in behavior.

- [ ] **Step 6: Run the whole suite, then commit**

Run: `bin/test`

```bash
git add uedcli/preview_native.py uedcli/actor_survey.py
git add uedcli/tests/test_preview_native.py uedcli/tests/test_actor_survey.py
git commit -m "actor survey: one solve giving both surfaces and a solidity probe"
```

---

## Part D — the five csg-tier relations

All five read one `SurveyContext`, built once per survey in Task 11 and threaded through unchanged.
Each relation is one function with the same shape, `<relation>_facts_for(ctx) -> list[CsgFact]`, so
Task 18's orchestrator is a loop, not a special case per relation.

**One design decision, made here because four tasks depend on it: `crosses`'s depth is measured per
PLANE, not by the spike's isotropic bisection.** The spike's `signed_clearance`
(`harness/collision_clearance.py:54-68`) grows or shrinks the whole box uniformly until it is free,
and its own `_stats` (line 194) then EXCLUDES every "buried" actor — one whose box centre is already
in solid — from every percentile, because such an actor saturates at the shrink floor `-max(ext)` and
the number it reports is the box's own half-extent, not a penetration depth. Reporting that
saturated value on a `crosses` line would be reporting an artifact as a measurement.

The spec already defines the depth differently and better: "the intruding geometry's own maximum
perpendicular distance past the crossed face's plane, within the overlap region" — and rules that the
same shape applies to a collision-extent source, not just a brush one (Round 8). Measured that way
there is no saturation to exclude: a buried actor gets a large, genuine per-plane number. So this
plan ports the spike's sampling test (which answers "does this reach into solid at all", the
crossing GATE — with the sample points made cylindrical, Task 11) and deliberately does not port the
bisection, whose only contribution was a magnitude
this design gets from the plane instead. That is recorded here rather than left implicit, because it
is a departure from "port the spike verbatim".

### Task 11: the survey context, the fact type, and the crossing gate

**Files:**
- Modify: `uedcli/actor_survey.py`
- Modify: `uedcli/tests/survey_scenarios.py` (one more builder)
- Test: `uedcli/tests/test_actor_survey.py`

**Interfaces:**
- Consumes: Task 7's `neighborhood`/`near_brushes`/`nearby_point_actors`/`region_of` and its
  `_blocks_movement` collision gate; Task 10's `preview_native.solve_world_probe` and `csg_faces`;
  `query.csg_kind`, `movers.is_mover`, `uprops.SchemaError`.
- Produces:

```python
@dataclass(frozen=True)
class CsgFact:
    src: str
    dst: str
    relation: str              # "crosses"|"touches"|"connects"|"contains"|"carves"
    depth_uu: float | None = None      # set on `crosses` only

@dataclass(frozen=True)
class SurveyContext:
    level: object
    class_index: object
    defaults: object
    name: str
    surveyed: object
    region: tuple              # (lo, hi), Decimals
    neighbors: list            # brush actors, trunk order — the SOLVE set
    near: list                 # the subset whose own AABB meets the region — the PAIR-TEST set
    points: list               # non-brush actors in the region (excluding the surveyed one)
    probe: object              # preview_native.WorldProbe
    faces: list                # list[CsgFace], deduped by (owner, plane)
    cells: dict                # the shared decompose_convex cache, shared with the raw tier

def build_context(level, class_index, name, defaults, *, cells=None) -> SurveyContext
def kind_of(actor, class_index) -> str
def crosses_source_eligible(actor, class_index, defaults) -> bool
def crosses_target_eligible(actor, class_index) -> bool
def collision_extent(actor, defaults) -> tuple[float, float] | None
def cylinder_sample_points(loc, radius, height) -> list[tuple[float, float, float]]
def extent_reaches_solid(ctx, loc, radius, height) -> bool
```

- [ ] **Step 1: Write the failing tests**

Add one builder to `uedcli/tests/survey_scenarios.py`:

```python
# --------------------------------------------------------------------- Task 11's scenario

def room_with_a_flush_mounted_prop() -> Scenario:
    """Trunk order: Room, Keypad, Trigger, Ghost, Bracket.

    * `Room`    1024^3 Subtract at (0, 0, 0)       — walls at x = +/-512
    * `Keypad`  a point actor at (504, 0, 0), bCollideActors + bBlockActors, R=16 H=16 —
                its collision cylinder spans x in [488, 520], so 8uu of it is inside the +X wall's
                solid
    * `Trigger` a point actor at the same place, bCollideActors but NOT bBlockActors, R=520 —
                a room-spanning trigger volume, the exact shape the spike's source gate excludes
    * `Ghost`   a point actor at (504, 0, 0) with no collision props at all
    * `Bracket` a point actor at (520, 0, 0), same blocking collision as `Keypad`, R=16 H=16 —
                its LOCATION is buried in the +X wall and sits OUTSIDE `Room`'s own padded AABB
                (x = 513), but its cylinder spans x in [504, 536], which does meet that AABB. This
                is the case `nearby_point_actors`' extent-aware candidate test exists for: a bare-
                `Location` filter drops `Bracket` from `Room`'s point candidates, and its
                `crosses` fact then shows up when you survey `Bracket` and vanishes when you
                survey `Room`. Its deepest sample point is 24 uu past the wall face at x=512.
    """
    coll = [("bCollideActors", "True"), ("bBlockActors", "True"),
            ("CollisionRadius", "16"), ("CollisionHeight", "16")]
    trig = [("bCollideActors", "True"), ("bBlockActors", "False"),
            ("CollisionRadius", "520"), ("CollisionHeight", "520")]
    return _scenario([
        brush("Room", (1024, 1024, 1024), (0, 0, 0), csg="subtract"),
        point("Keypad", (504, 0, 0), cls="DeusEx.Keypad1", props=coll),
        point("Trigger", (504, 0, 0), cls="Engine.Trigger", props=trig),
        point("Ghost", (504, 0, 0), cls="Engine.Light"),
        point("Bracket", (520, 0, 0), cls="DeusEx.Keypad1", props=coll),
    ])
```

Append to `uedcli/tests/test_actor_survey.py`:

```python
def test_collision_extent_needs_both_collide_and_block():
    """`bCollideActors` alone is not a claim about matter: a DataLinkTrigger (R=520), a FlagTrigger
    (R=630), a Teleporter all set it so they can be touched, block nothing, and are routinely sized
    to span rooms, walls included. Measured across 1522 collidable shipped actors, the non-blocking
    ones are 471 of them and carry the entire deep tail — gating them out drops the worst by-design
    overlap from 436 uu to 64 uu (spike.md §3)."""
    sc = scen.room_with_a_flush_mounted_prop()
    assert actor_survey.collision_extent(sc.level.actors["Keypad"], sc.defaults) == (16.0, 16.0)
    assert actor_survey.collision_extent(sc.level.actors["Trigger"], sc.defaults) is None
    assert actor_survey.collision_extent(sc.level.actors["Ghost"], sc.defaults) is None


def test_region_of_a_point_actor_covers_its_real_collision_extent():
    """A non-brush actor's shape is its collision cylinder, exactly as a brush's is its own
    vertices. A cylinder of radius R and half-height H bounds to `Location +/- (R, R, H)` -- the
    same box a box-shaped volume of those half-extents would -- and then the SAME `NEIGHBORHOOD_PAD`
    goes on top. Without it `Keypad`'s region would be 2 uu across and the `+X` wall it is mounted
    flush against (x=512) would fall outside it, so no face of that wall would ever reach
    `ctx.faces`. `Ghost` has no collision volume, so the same formula gives it the bare padded point
    box -- the degenerate case, not a special one.

    `Trigger` shows the gate: it sets `bCollideActors` and `CollisionRadius=520` but blocks nothing,
    so its cylinder is not matter and sizing a 1042-uu region (and solving the neighborhood that
    selects) off it would buy nothing. Same gate `collision_extent` applies, so the two agree."""
    from decimal import Decimal
    sc = scen.room_with_a_flush_mounted_prop()
    lo, hi = actor_survey.region_of(sc.level.actors["Keypad"], sc.defaults)
    assert (lo[0], hi[0]) == (Decimal(487), Decimal(521))      # 504 -/+ 16, then -/+ 1 of pad
    assert actor_survey.region_of(sc.level.actors["Ghost"], sc.defaults) == \
        ((Decimal(503), Decimal(-1), Decimal(-1)), (Decimal(505), Decimal(1), Decimal(1)))
    assert actor_survey.region_of(sc.level.actors["Trigger"], sc.defaults) == \
        ((Decimal(503), Decimal(-1), Decimal(-1)), (Decimal(505), Decimal(1), Decimal(1)))


def test_collision_extent_does_not_coalesce_present_but_empty_with_absent():
    """`field(name) or default` would treat an explicitly-present empty value as absent and
    substitute the class default — a bug `serve/scene.py::_actor_radii` already found and fixed with
    an `is not None` test (its own `field_or` comment). Keep that split.

    The split lives in `_blocks_movement` (Task 7), which is also the single copy of the gate: the
    second assertion pins that `collision_extent` calls it rather than re-implementing it, so the
    two can never drift into disagreeing about whether an actor collides."""
    import inspect
    assert "is not None" in inspect.getsource(actor_survey._blocks_movement)
    assert "_blocks_movement" in inspect.getsource(actor_survey.collision_extent)


def test_collision_extent_propagates_a_schema_error_rather_than_guessing():
    """An unresolvable class means the collision gate cannot be answered. Exit 2 is the caller's job
    (Task 18); silently treating it as 'does not collide' would be a substituted default."""
    import pytest
    from uedcli import uprops
    sc = scen.room_with_a_flush_mounted_prop()
    with pytest.raises(uprops.SchemaError):
        actor_survey.collision_extent(sc.level.actors["Keypad"], scen.failing_defaults())


def test_crosses_source_eligibility_follows_the_specs_kind_table():
    sc = scen.kind_table_scenario()
    ci, d = sc.index, sc.defaults
    eligible = {n for n in sc.level.order
                if actor_survey.crosses_source_eligible(sc.level.actors[n], ci, d)}
    assert {"Adder", "Semi", "Door"} <= eligible          # Add, Semisolid, Mover
    assert eligible.isdisjoint({"Cutter", "Nonsolid", "Inter", "Deinter"})


def test_crosses_target_eligibility_follows_the_specs_kind_table():
    sc = scen.kind_table_scenario()
    ci = sc.index
    ok = {n for n in sc.level.order
          if actor_survey.crosses_target_eligible(sc.level.actors[n], ci)}
    assert {"Adder", "Semi", "Cutter"} <= ok              # Add, Semisolid, Subtract author faces
    assert ok.isdisjoint({"Nonsolid", "Inter", "Deinter", "Door", "Lamp"})


def test_cylinder_sample_points_never_leaves_the_cylinder():
    """The regression against reintroducing box sampling. The engine's collision volume is a
    cylinder, so no sample may stand further than `radius` from the axis -- a box corner would stand
    at `radius * sqrt(2)` = 22.6 uu for R=16 and invent penetration into a diagonal wall.

    Hand-checked: 3 Z levels x (1 axis point + 8 ring points) = 27, the same count the box version
    used. The first ring point is at +X exactly, so an axis-aligned face sees the cylinder's true
    extreme; that is what keeps the flush-mount depths below exact."""
    from math import hypot
    pts = actor_survey.cylinder_sample_points((504.0, 0.0, 0.0), 16.0, 16.0)
    assert len(pts) == 27
    assert {round(p[2], 6) for p in pts} == {-16.0, 0.0, 16.0}
    assert max(round(hypot(p[0] - 504.0, p[1]), 6) for p in pts) == 16.0
    assert max(round(p[0], 6) for p in pts) == 520.0


def test_extent_reaches_solid_is_true_for_a_flush_mounted_prop():
    import pytest
    pytest.importorskip("uedcli_native")
    sc = scen.room_with_a_flush_mounted_prop()
    ctx = actor_survey.build_context(sc.level, sc.index, "Keypad", sc.defaults)
    assert actor_survey.extent_reaches_solid(ctx, (504.0, 0.0, 0.0), 16.0, 16.0) is True
    assert actor_survey.extent_reaches_solid(ctx, (0.0, 0.0, 0.0), 16.0, 16.0) is False


def test_build_context_solves_once_and_shares_the_decomposition_cache():
    import pytest
    pytest.importorskip("uedcli_native")
    sc = scen.niche_carved_into_wall()
    cells = {}
    ctx = actor_survey.build_context(sc.level, sc.index, "Wall", sc.defaults, cells=cells)
    assert ctx.cells is cells
    assert ctx.probe.solidity is not None
    assert ctx.faces and all(isinstance(f, actor_survey.CsgFace) for f in ctx.faces)
    assert [a.name for a in ctx.near] == ["Niche", "Bystander"]
```

and one more builder for the kind table:

```python
# --------------------------------------------------------------------- the CSG-kind table

def kind_table_scenario() -> Scenario:
    """One actor of every kind the spec's `crosses` table names, all in one level, so the two
    eligibility tests read as a table rather than as seven separate fixtures. Geometry is
    irrelevant here — only the kinds are under test — so every brush is a 64^3 box on its own
    100uu step along +X.

    Trunk order: Adder, Semi, Nonsolid, Cutter, Inter, Deinter, Door, Lamp.
    """
    from uedcli.builders import PF_NOTSOLID
    door = make_brush_actor("Door", cube(64, 64, 64), location=_dec((600, 0, 0)),
                            mover_class="DeusEx.DeusExMover")
    return _scenario([
        brush("Adder", (64, 64, 64), (0, 0, 0)),
        brush("Semi", (64, 64, 64), (100, 0, 0), poly_flags=PF_SEMISOLID),
        brush("Nonsolid", (64, 64, 64), (200, 0, 0), poly_flags=PF_NOTSOLID),
        brush("Cutter", (64, 64, 64), (300, 0, 0), csg="subtract"),
        oper_brush("Inter", (64, 64, 64), (400, 0, 0), "CSG_Intersect"),
        oper_brush("Deinter", (64, 64, 64), (500, 0, 0), "CSG_Deintersect"),
        door,
        point("Lamp", (700, 0, 0)),
    ])
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `bin/test -k "collision_extent or region_of_a_point_actor or crosses_source_eligibility or crosses_target_eligibility or cylinder_sample_points or extent_reaches_solid or build_context_solves_once" -v`
Expected: FAIL — none of these functions exists.

- [ ] **Step 3: Add the fact type, the context and the kind predicates**

In `uedcli/actor_survey.py`:

```python
@dataclass(frozen=True)
class CsgFact:
    """One csg-tier line. `depth_uu` is set on `crosses` and on nothing else -- the spec gives that
    one relation an annotation and leaves every other csg line bare."""
    src: str
    dst: str
    relation: str
    depth_uu: float | None = None


@dataclass(frozen=True)
class SurveyContext:
    """Everything the five csg relations share, built ONCE per survey.

    `neighbors` is the solve set (trunk order, including the level's first world-CSG brush whether
    or not it is near). `near` is the subset that really meets the region -- the only actors any
    fact may name. `probe` is one `build_geometry_bspcsg` call's output; `faces` is its surfaces
    deduped to one entry per (owner, plane); `cells` is the decomposition cache shared with the raw
    tier so no brush is decomposed twice in one survey.

    `seed` is the NAME of the level's first world-CSG brush -- the one `bsp_brush_csg` turns into
    the world shell instead of classifying. It is carried explicitly rather than read back as
    `neighbors[0].name`, because `neighbors` is in trunk order and index 0 can perfectly well be a
    Mover or the builder brush, neither of which contributes to world CSG. Anything that must not
    disturb the seed (`removed_by`) compares against this."""
    level: object
    class_index: object
    defaults: object
    name: str
    surveyed: object
    region: tuple
    neighbors: list
    near: list
    points: list
    probe: object
    faces: list
    cells: dict
    seed: str | None


def build_context(level, class_index, name: str, defaults, *, cells=None) -> SurveyContext:
    """Build the shared csg-tier context. Raises `ActorNotFoundError` for an unknown name and
    `preview_native.NativePreviewError` when the native extension is missing or the solve fails --
    both mapped to exit 2 by the CLI handler (Task 18)."""
    from .preview_native import solve_world_probe
    if name not in level.actors:
        raise ActorNotFoundError(name)
    surveyed = level.actors[name]
    region = region_of(surveyed, defaults)
    neighbors = neighborhood(level, class_index, surveyed, defaults)
    probe = solve_world_probe(neighbors, class_index)
    return SurveyContext(
        level=level, class_index=class_index, defaults=defaults, name=name, surveyed=surveyed,
        region=region,
        neighbors=neighbors,
        near=[a for a in near_brushes(level, class_index, surveyed, defaults) if a.name != name],
        points=[a for a in nearby_point_actors(level, surveyed, defaults) if a.name != name],
        probe=probe,
        faces=csg_faces(probe, region),
        cells={} if cells is None else cells,
        seed=seed_brush_name(level, class_index),
    )


def kind_of(actor, class_index) -> str:
    """`query.csg_kind`'s flat kind for a brush actor: one of add/subtract/semisolid/nonsolid/
    intersect/deintersect/mover. `is_mover` is the caller's authoritative answer, never guessed."""
    return query.csg_kind(actor, is_mover=movers.is_mover(actor, class_index))


# The spec's own `crosses` table, stated positively. Each row was measured against the native CSG
# core, not reasoned from the kind's name (spike.md §1; regression `test_csg_kind_facts.py`):
#   add        contributes solid                                     -> source and target
#   semisolid  contributes real solid and collides like solid        -> source and target
#   subtract   no solid of its own, but authors real carved faces     -> target only
#   nonsolid   NF_NotCsg: its nodes bound no solid, the walk passes   -> neither
#   intersect/deintersect  contribute nothing whatever                -> neither
#   mover      excluded from world CSG, so nothing can cross INTO it, but it carries a real private
#              UModel of genuine solid matter treated exactly like an Add's (owner ruling, Round 8)
#                                                                     -> source only
_CROSSES_SOURCE_KINDS = frozenset({"add", "semisolid", "mover"})
_CROSSES_TARGET_KINDS = frozenset({"add", "semisolid", "subtract"})


def crosses_source_eligible(actor, class_index, defaults) -> bool:
    """Can this actor's own matter be the INTRUDER on a `crosses` line? A non-brush actor qualifies
    only when it has a real blocking collision cylinder (see `collision_extent`)."""
    if actor.brush is None:
        return collision_extent(actor, defaults) is not None
    return kind_of(actor, class_index) in _CROSSES_SOURCE_KINDS


def crosses_target_eligible(actor, class_index) -> bool:
    """Can this actor be the `dst` of a `crosses`/`touches` line -- i.e. does it author a resolved
    face something can be flush against or penetrate? A non-brush actor never does: its collision
    cylinder is not world geometry."""
    if actor.brush is None:
        return False
    return kind_of(actor, class_index) in _CROSSES_TARGET_KINDS
```

- [ ] **Step 4: Add the collision-extent resolution**

```python
def _to_float(text, default: float = 0.0) -> float:
    """Ported from the spike harness's own `_to_float` (`collision_clearance.py:71`)."""
    try:
        return float(str(text).strip())
    except (TypeError, ValueError):
        return default


def collision_extent(actor, defaults) -> tuple[float, float] | None:
    """`(radius, height)` when `actor` has a real BLOCKING collision volume, else None.

    The engine collides a CYLINDER: radius `CollisionRadius` in the XY plane, half-height
    `CollisionHeight` in Z. The project owner confirmed this directly, from first-hand Unreal
    Engine 1 experience. An earlier draft called it an axis-aligned box on the strength of a comment
    in `uedcli-native/src/collision.rs` that was never checked against the game binaries -- do not
    reintroduce that claim or that citation.

    Confirmed since, statically, against this repo's own `uned/UED22/Engine.dll` (ImageBase
    0x10000000). `AActor::SetCollisionSize` (RVA 0x12e8b0) stores its two float args to [this+0x190]
    and [this+0x194], pinning CollisionRadius/CollisionHeight; `ULevel::FarMoveActor` (RVA 0x15ff80)
    writes Location.X/Y/Z to [actor+0xd0/0xd4/0xd8]. `UPrimitive::PointCheck` (RVA 0x1935d0, reached
    from `FCollisionHash::ActorPointCheck` at 0x125380 through vtable slot [eax+0x54]) then tests,
    at VA 0x10193611-0x10193682:

        (Extent.Z + CollisionHeight)^2 > dz^2                      -- Z alone
        (Extent.X + CollisionRadius)^2 > dx*dx + dy*dy             -- XY as ONE circular sum

    `AActor::IsOverlapping` (RVA 0x12d3d0) has the same shape for actor-vs-actor at 0x1012d457. Two
    details recorded because they are not guessable: the comparisons are STRICT (`jbe` -> miss, so
    exact contact is a miss), and `Extent.Y` is never read at all -- a query box is collapsed to a
    cylinder using its X half-extent as the radius. The broad phase (`FCollisionHash`) is an AABB
    grid, which is what a reader skimming the collision code can mistake for a box collision test.
    This covers actor-primitive collision only; `UModel`/`UMesh` line and point checks were not
    examined. RVA 0x1aeba0, the address `collision.rs` cites, is genuinely `UModel::PointCheck` --
    BSP world geometry, not actor collision, so it was never evidence for this question either way.

    The gate is `_blocks_movement` (Task 7) -- the SAME function `_collision_half_extent` calls, not
    a second copy of it, so region sizing and the crossing gate cannot drift apart. It is TIGHTER
    than `_actor_radii`'s, and deliberately so: that function gates on `bCollideActors` alone, which
    is right for a GUI overlay but admits room-spanning trigger volumes. `_blocks_movement` also
    requires `bBlockActors` -- the engine's own name for "this actor's extent occupies space others
    cannot" -- which spike.md §3 measured as the gate that removes the entire deep tail (max
    penetration 436 uu -> 64 uu, p90 52 uu -> 12.7 uu across 1522 shipped actors). It carries the
    `is not None` split that keeps a present-but-EMPTY property from reading as absent.

    A non-positive radius or height is not a volume: `_blocks_movement` answers "claims to block",
    this adds "and has a size".

    Radius and height resolve instance-property-else-class-default, exactly as
    `serve/scene.py::_actor_radii` does it. `_to_float` already maps an empty or malformed value to
    0.0, which the size test below rejects.

    `uprops.SchemaError` from an unresolvable class propagates: the gate cannot be answered, and
    guessing "does not collide" would be a substituted default. The CLI maps it to exit 2."""
    if not _blocks_movement(actor, defaults):
        return None
    instance = {k.casefold(): v for k, v in actor.props}
    class_defaults = defaults.for_class(actor.cls).defaults

    def field(name: str):
        low = name.casefold()
        return instance[low] if low in instance else class_defaults.get((low, 0))

    radius = _to_float(field("CollisionRadius"))
    height = _to_float(field("CollisionHeight"))
    if radius <= 0.0 or height <= 0.0:
        return None
    return radius, height
```

- [ ] **Step 5: Add the crossing gate**

Add `import math` to `actor_survey.py`'s import block in this task.

```python
# How many evenly spaced angles the collision cylinder's curved surface is sampled at, per Z level.
RING_SAMPLES = 8


def cylinder_sample_points(loc, radius: float, height: float) -> list:
    """The 27 sample points of the collision cylinder centred at `loc`: at each of three Z levels
    (`-height`, `0`, `+height`), the point on the axis plus `RING_SAMPLES` points evenly spaced
    around the circle of radius `radius`, the first at +X and each 45 degrees on from the last.

    This REPLACES the spike harness's `_sample_points` (`collision_clearance.py:40-47`), which laid
    a 3x3x3 grid over an axis-aligned box -- a shape the engine does not collide with (see
    `collision_extent`). The difference is not cosmetic: a box corner stands `radius * sqrt(2)` from
    the axis, 41% further out than any part of the real cylinder, so box sampling reports the actor
    inside a diagonal wall it never touches.

    8 ring points and 3 Z levels are chosen to MATCH the box version's granularity, not to improve
    on it. The box put 9 points on each of 3 Z levels (4 corners, 4 edge midpoints, 1 centre); this
    puts 9 on each of the same 3 levels (8 ring points, 1 axis point). The total stays 27, so the
    cost of the `any_point_solid` call below is unchanged. The 45-degree step also lands a sample
    exactly on the cylinder's extreme point for any face whose normal is axis-aligned or a 45-degree
    XY diagonal -- every face in this plan's fixtures, and the great majority in shipped levels.

    Two limits, stated rather than smoothed away. The first is inherited from the box version: 27
    points can miss a solid slab thinner than the sample spacing. The second is the ring's own
    price: against a face whose XY normal falls BETWEEN two ring angles, the deepest sample sits
    short of the cylinder's true extreme point by up to `radius * (1 - cos(pi / RING_SAMPLES))` =
    `0.0761 * radius` -- 1.2 uu at the 16-uu radius the fixtures use -- so a depth can under-report
    by that much. Under-reporting is the safe direction: the box's `sqrt(2)` corner OVER-reported,
    inventing penetration, which is what made it wrong rather than merely coarse."""
    out = []
    for iz in (-1, 0, 1):
        z = loc[2] + iz * height
        out.append((loc[0], loc[1], z))
        for k in range(RING_SAMPLES):
            angle = 2.0 * math.pi * k / RING_SAMPLES
            out.append((loc[0] + radius * math.cos(angle),
                        loc[1] + radius * math.sin(angle), z))
    return out


def extent_reaches_solid(ctx: SurveyContext, loc, radius: float, height: float) -> bool:
    """Does the collision cylinder at `loc` reach into RESOLVED SOLID matter? The spike's own
    `_box_free` test (`collision_clearance.py:50`) at delta = 0, negated, with its box sample
    swapped for `cylinder_sample_points`, run through the native query in one call.

    This is the crossing GATE only. The spike's `signed_clearance` bisection around it is
    deliberately NOT ported: its only extra output was an isotropic magnitude, and that magnitude
    saturates at the shrink floor for a 'buried' actor -- which is exactly why the harness's own
    `_stats` (line 194) excludes buried actors from every percentile. The spec measures a `crosses`
    depth against the crossed face's own plane instead (Task 12), where there is nothing to
    saturate."""
    if ctx.probe.solidity is None:
        return False                      # an empty world has no solid to reach
    return ctx.probe.solidity.any_point_solid(cylinder_sample_points(loc, radius, height))
```

Only the sample-point generation changes. Everything built on top of it is shape-agnostic: the gate
is "is any of these points solid", and Task 12's `penetration_depth` is "how far past this plane
does the furthest of these points lie". Neither reads an extent, an axis, or a corner, so neither
needed a second look once the point set was right. The isotropic bisection, the one piece that WOULD have
assumed a uniformly scalable box, is the piece this plan already declined to port.

- [ ] **Step 6: Run the tests**

Run: `bin/test -k "collision_extent or region_of_a_point_actor or crosses_source_eligibility or crosses_target_eligibility or cylinder_sample_points or extent_reaches_solid or build_context_solves_once" -v`
Expected: PASS

Run: `bin/test -k actor_survey`
Expected: all green.

- [ ] **Step 7: Run the whole suite, then commit**

Run: `bin/test`

```bash
git add uedcli/actor_survey.py uedcli/tests/survey_scenarios.py uedcli/tests/test_actor_survey.py
git commit -m "actor survey: csg context, CSG-kind eligibility, collision extent"
```

---

### Task 12: `crosses` — face orientation, per-plane depth, both directions

**Files:**
- Modify: `uedcli/actor_survey.py`
- Modify: `uedcli/tests/survey_scenarios.py` (two more builders)
- Test: `uedcli/tests/test_actor_survey.py`

**Interfaces:**
- Consumes: Task 11's `SurveyContext`, `CsgFact`, `crosses_source_eligible`,
  `crosses_target_eligible`, `collision_extent`, `extent_reaches_solid`, `cylinder_sample_points`;
  Task 10's `CsgFace`, `CSG_TOLERANCE`; `actorgraph.decompose_convex`;
  `relation.project_to_plane` (existing) and `relation._point_in_polygon_2d` (Task 4's addition),
  which bound `penetration_depth` to a face's own footprint.
- Produces:

```python
def face_outward_sign(ctx, face: CsgFace) -> float | None
def source_points(ctx, actor) -> list[tuple[float, float, float]] | None
def penetration_depth(ctx, points, face) -> float | None
def crosses_facts_for(ctx) -> list[CsgFact]
```

**The one thing this task must measure before it can implement anything.** A `CsgFace`'s stored
normal is sign-canonicalized (Task 10) and carries no facing information, and the winding a resolved
surface comes back with is NOT something this plan verified — `bspcsg.rs`'s leading-Add seed stores
its faces REVERSED, so "the ring winds outward from solid" is a guess until measured. Step 1 measures
it, against the already-committed `test_csg_kind_facts` scenario, whose solid/void answers are
themselves already pinned. Everything after that uses the measured answer.

- [ ] **Step 1: Measure which side of a resolved face is solid**

Write this test FIRST and run it; it is the task's own probe and its permanent regression.

```python
def test_a_resolved_faces_solid_side_is_determined_by_the_solidity_probe_not_by_winding():
    """A `CsgFace`'s normal is sign-canonicalized and carries no facing. Rather than trust the
    ring's winding -- which `bspcsg.rs`'s leading-Add seed deliberately reverses for the world
    shell -- the solid side is MEASURED: step a short distance off the face's centroid both ways and
    ask the native solidity query. Exactly one side must be solid for a face that bounds solid.

    Scenario: `test_csg_kind_facts`' own Room/Pillar/Cutter, whose solid/void answers at LEFT and
    RIGHT are already pinned by that committed regression."""
    import pytest
    pytest.importorskip("uedcli_native")
    sc = scen.pillar_in_room()
    ctx = actor_survey.build_context(sc.level, sc.index, "Pillar", sc.defaults)
    pillar_faces = [f for f in ctx.faces if f.owner == "Pillar"]
    assert pillar_faces, "the Add pillar contributes surviving faces"
    for f in pillar_faces:
        sign = actor_survey.face_outward_sign(ctx, f)
        assert sign in (1.0, -1.0), "exactly one side of a solid-bounding face is solid"
```

Add the scenario:

```python
# --------------------------------------------------------------------- Task 12's scenarios

def pillar_in_room() -> Scenario:
    """The scenario `uedcli/tests/test_csg_kind_facts.py` already pins, rebuilt here through this
    module's own helpers so both stay in step. Trunk order: Room, Pillar, Cutter.

    * `Room`   1024^3 Subtract at (0, 0, 0)
    * `Pillar` 128 x 128 x 512 Add at (0, 0, 0)
    * `Cutter` 256^3 Subtract at (128, 0, 0)  — takes the pillar's RIGHT half over the middle of
      its height, leaving the left half and both ends

    Pinned there: (-40, 0, 0) is solid, (40, 0, 0) is not, the pillar keeps 11 faces and
    229376 uu^2 of its original 294912.
    """
    return _scenario([
        brush("Room", (1024, 1024, 1024), (0, 0, 0), csg="subtract"),
        brush("Pillar", (128, 128, 512), (0, 0, 0)),
        brush("Cutter", (256, 256, 256), (128, 0, 0), csg="subtract"),
    ])


def shelf_pokes_through_a_niche_wall() -> Scenario:
    """The spec's own nesting example, `Subtract1 -> Additive2 -> Subtract3 -> Additive4`.

    * `Subtract1` 1024^3 Subtract at (0, 0, 0)          — the outer room
    * `Additive2` 256 x 64 x 256 Add at (0, 128, 0)     — a wall inside it, y in [96, 160]
    * `Subtract3` 128 x 128 x 128 Subtract at (0, 128, 0) — a niche carved into that wall
    * `Additive4` 32 x 256 x 32 Add at (0, 128, 0)      — a shelf poking out through the niche's
      own -Y and +Y walls, y in [0, 256]

    `Additive4` crosses `Subtract3` -- the immediate boundary it pushes through -- and never
    `Additive2`, however the nesting reads (the spec's strict-locality rule).
    """
    return _scenario([
        brush("Subtract1", (1024, 1024, 1024), (0, 0, 0), csg="subtract"),
        brush("Additive2", (256, 64, 256), (0, 128, 0)),
        brush("Subtract3", (128, 128, 128), (0, 128, 0), csg="subtract"),
        brush("Additive4", (32, 256, 32), (0, 128, 0)),
    ])
```

Run: `bin/test -k test_a_resolved_faces_solid_side -v`
Expected: FAIL — `face_outward_sign` does not exist.

- [ ] **Step 2: Implement `face_outward_sign`**

```python
# How far off a face to step when asking which of its two sides is solid. Comfortably clear of
# CSG_TOLERANCE (0.015 uu, the point-dedup resolution limit) so the probe never lands ON the plane,
# and far below the smallest real content feature the spike measured (0.043 uu penetration).
_SIDE_PROBE_STEP = 0.05


def _face_centroid(face) -> tuple:
    n = len(face.verts)
    return tuple(sum(v[i] for v in face.verts) / n for i in range(3))


def face_outward_sign(ctx: SurveyContext, face) -> float | None:
    """`+1` when SOLID lies on the face's `+normal` side, `-1` when it lies on the `-normal` side,
    `None` when the probe finds solid on both sides or neither (a face that bounds no solid here, or
    one whose centroid falls outside the solved region).

    Measured, never inferred from the ring's winding: `bspcsg.rs`'s leading-Add seed deliberately
    stores the world shell's faces REVERSED, and `csg_faces` canonicalizes the normal's sign anyway,
    so winding carries no usable facing. Stepping `_SIDE_PROBE_STEP` off the centroid and asking the
    native solidity query is the same oracle the CSG-kind regression uses."""
    if ctx.probe.solidity is None:
        return None
    c = _face_centroid(face)
    plus = tuple(c[i] + face.normal[i] * _SIDE_PROBE_STEP for i in range(3))
    minus = tuple(c[i] - face.normal[i] * _SIDE_PROBE_STEP for i in range(3))
    solid_plus = ctx.probe.solidity.point_is_solid(plus)
    solid_minus = ctx.probe.solidity.point_is_solid(minus)
    if solid_plus == solid_minus:
        return None
    return 1.0 if solid_plus else -1.0
```

Run: `bin/test -k test_a_resolved_faces_solid_side -v`
Expected: PASS. **If it does not** — if some pillar face reports `None` — stop and report the
concrete finding rather than loosening the assertion: a face of a solid Add that bounds solid on
neither side would mean the probe step or the solidity query is wrong, and that is a real result
this plan wants to hear about, not paper over.

- [ ] **Step 3: Write the remaining failing tests**

```python
def test_crosses_fires_for_an_add_poking_through_a_niche_wall_and_names_only_the_immediate_owner():
    """The spec's locality rule: `Additive4` crosses `Subtract3`, the boundary it actually pushes
    through, and never `Additive2`, however deep the nesting."""
    import pytest
    pytest.importorskip("uedcli_native")
    sc = scen.shelf_pokes_through_a_niche_wall()
    ctx = actor_survey.build_context(sc.level, sc.index, "Additive4", sc.defaults)
    facts = actor_survey.crosses_facts_for(ctx)
    assert any(f.src == "Additive4" and f.dst == "Subtract3" for f in facts)
    assert not any(f.dst == "Additive2" for f in facts)
    assert all(f.relation == "crosses" and f.depth_uu is not None and f.depth_uu > 0
               for f in facts)


def test_crosses_never_fires_from_a_subtract():
    """The design bug the source restriction exists to fix: without it, a Subtract room's raw shape
    trivially 'crosses' every Add placed inside it — firing for every piece of furniture in every
    room."""
    import pytest
    pytest.importorskip("uedcli_native")
    sc = scen.pillar_in_room()
    ctx = actor_survey.build_context(sc.level, sc.index, "Room", sc.defaults)
    assert actor_survey.crosses_facts_for(ctx) == []


def test_crosses_fires_for_a_flush_mounted_collision_extent_with_a_measured_depth():
    """Under the bBlockActors gate, ~12% of physically-blocking shipped actors really are inside
    solid, by ~8 uu at the median. The fact is true and is reported, made readable by the depth
    (spike.md §3).

    `Keypad` sits at x=504 with R=16, and the `+X` wall's face is at x=512. The wall's normal is
    axis-aligned, so `cylinder_sample_points`' first ring point lands on the cylinder's extreme at
    x = 504 + 16 = 520 exactly, and the measured depth is 8 uu — the same number the old box sample
    gave, because a box face centre and a cylinder ring point coincide on an axis-aligned normal.
    That face only reaches `ctx.faces` because `region_of` covers the actor's real collision extent
    (Task 7) — a zero-size point box would leave it 7 uu outside the region."""
    import pytest
    pytest.importorskip("uedcli_native")
    sc = scen.room_with_a_flush_mounted_prop()
    ctx = actor_survey.build_context(sc.level, sc.index, "Keypad", sc.defaults)
    facts = actor_survey.crosses_facts_for(ctx)
    assert any(f.src == "Keypad" and f.dst == "Room" for f in facts)
    assert 4.0 < next(f for f in facts if f.dst == "Room").depth_uu < 12.0


def test_crosses_fires_for_a_point_actor_whose_location_is_outside_the_surveyed_brush():
    """Direction 2, and the regression for `nearby_point_actors`' extent-aware candidate test
    (Task 7). `Bracket` sits at x=520, OUTSIDE `Room`'s own padded AABB (x = 513), so a candidate
    filter reading the bare `Location` drops it from `ctx.points` and this fact disappears when you
    survey `Room` while still appearing when you survey `Bracket` — the one-sided pair
    `crosses_facts_for` is written to rule out. Its collision cylinder spans x in [504, 536], which
    does meet the region, so the extent-aware test keeps it, and its deepest sample point — the
    ring point at +X, at x = 520 + 16 = 536 — is 24 uu past the `+X` wall's face at x=512.

    `Keypad` is not the case under test here: its `Location` is inside `Room`'s AABB, so the
    narrower filter would keep it and this direction would look fine."""
    import pytest
    pytest.importorskip("uedcli_native")
    from decimal import Decimal
    sc = scen.room_with_a_flush_mounted_prop()
    assert Decimal(520) > actor_survey.region_of(sc.level.actors["Room"], sc.defaults)[1][0]
    ctx = actor_survey.build_context(sc.level, sc.index, "Room", sc.defaults)
    assert "Bracket" in [a.name for a in ctx.points]
    facts = actor_survey.crosses_facts_for(ctx)
    fact = next((f for f in facts if f.src == "Bracket" and f.dst == "Room"), None)
    assert fact is not None and fact.relation == "crosses"
    assert 20.0 < fact.depth_uu < 28.0


def test_crosses_does_not_fire_for_a_non_blocking_trigger_volume():
    import pytest
    pytest.importorskip("uedcli_native")
    sc = scen.room_with_a_flush_mounted_prop()
    ctx = actor_survey.build_context(sc.level, sc.index, "Trigger", sc.defaults)
    assert actor_survey.crosses_facts_for(ctx) == []


def test_crosses_reports_the_reverse_direction_when_the_surveyed_actor_is_the_target():
    """`crosses` is fixed-direction: the intruder always leads. Surveying the actor that was crossed
    INTO must still show the fact, with the intruder as src — the spec's own worked example has
    `Additive4 --crosses--> Subtract3`, and surveying `Subtract3` has to show it too."""
    import pytest
    pytest.importorskip("uedcli_native")
    sc = scen.shelf_pokes_through_a_niche_wall()
    ctx = actor_survey.build_context(sc.level, sc.index, "Subtract3", sc.defaults)
    facts = actor_survey.crosses_facts_for(ctx)
    assert any(f.src == "Additive4" and f.dst == "Subtract3" for f in facts)


def test_crosses_dedupes_to_one_fact_per_src_dst_pair():
    """A wall is many BSP fragments and several planes. One relationship, one line."""
    import pytest
    pytest.importorskip("uedcli_native")
    sc = scen.shelf_pokes_through_a_niche_wall()
    ctx = actor_survey.build_context(sc.level, sc.index, "Additive4", sc.defaults)
    facts = actor_survey.crosses_facts_for(ctx)
    keys = [(f.src, f.dst, f.relation) for f in facts]
    assert len(keys) == len(set(keys))
```

- [ ] **Step 4: Run them to verify they fail**

Run: `bin/test -k "crosses_fires or crosses_never_fires or crosses_does_not_fire or crosses_reports_the_reverse or crosses_dedupes" -v`
Expected: FAIL — `crosses_facts_for` does not exist.

- [ ] **Step 5: Implement the source geometry and the per-plane depth**

```python
def source_points(ctx: SurveyContext, actor) -> list | None:
    """The world-space points that stand for `actor`'s own contributed matter, or None when it has
    none. A BRUSH (Mover included -- its private model is treated exactly like an Add's, owner
    ruling Round 8) contributes its decomposed cells' vertices; a NON-BRUSH actor contributes the 27
    sample points of its collision cylinder.

    An actor with no `Location` contributes nothing rather than being placed at the origin: a
    substituted position would invent a fact (this is the same rule `collision_clearance.py`'s own
    candidate walk applies, skipping any actor whose `location is None`)."""
    if actor.brush is not None:
        return [tuple(float(c) for c in v)
                for cell in actorgraph.decompose_convex(actor, cache=ctx.cells)
                for v in cell.vertices]
    ext = collision_extent(actor, ctx.defaults)
    if ext is None or actor.location is None:
        return None
    radius, height = ext
    loc = tuple(float(c) for c in actor.location)
    return cylinder_sample_points(loc, radius, height)


def penetration_depth(ctx: SurveyContext, points, face) -> float | None:
    """How far `points` reach past `face` INTO the solid it bounds, or None when none of them do by
    more than `CSG_TOLERANCE`.

    This is the spec's own definition -- "the intruding geometry's own maximum perpendicular
    distance past the crossed face's plane" -- and it is one shape for every source kind, brush and
    collision extent alike (owner ruling, Round 8). Measuring against the PLANE, not by an isotropic
    clearance, is also what keeps a deeply-buried actor honest: the spike's bisection saturates at
    its own shrink floor there and its `_stats` has to exclude such actors from every percentile.

    Bounded to the face's OWN footprint, because the spec says "within the overlap region" and a
    plane is unbounded where a face is not. Without the bound, a source point nowhere near this
    face -- across the room, past the end of the wall -- still sits on the solid side of the face's
    infinite plane, and `crosses` would fire against an actor the source never reaches. So each
    point is projected onto the face's plane and kept only if it lands inside the face's own stored
    vertex ring. `project_to_plane` defaults its origin to the polygon's first vertex, so the ring
    and the point MUST be projected against the same explicit origin or the two land in unrelated
    frames (that function's own docstring, and the bug it cites).

    This is NOT the nearest-owner-wins filter, and must never be turned into one. That filter would
    compare SEVERAL faces against each other and keep only the closest owner, discarding true facts
    about the rest -- a new rule this plan has no authority to invent. This is a per-face bound
    asking one local question, "is this point over this face at all", answered from that one face's
    own geometry with no reference to any other face or owner.

    Known limit, stated rather than hidden: `_point_in_polygon_2d` is an even-odd ray cast, so a
    point landing EXACTLY on the ring's edge may read either way. A sample point exactly on a face
    boundary is a tie the spec does not rule on; if a fixture turns out to depend on it, report that
    rather than reaching for `relation._point_on_any_edge` on your own."""
    sign = face_outward_sign(ctx, face)
    if sign is None:
        return None
    ring_uv = relation.project_to_plane(face.verts, face.normal, origin=face.verts[0])
    # `sign` says which side is solid; the depth is how far past the plane a point lies ON that side.
    best = 0.0
    for p in points:
        past = sign * (sum(face.normal[i] * p[i] for i in range(3)) - face.offset)
        if past <= best:
            continue
        point_uv = relation.project_to_plane([p], face.normal, origin=face.verts[0])[0]
        if not relation._point_in_polygon_2d(ring_uv, point_uv):
            continue                  # past the PLANE, but not over the FACE
        best = past
    return best if best > CSG_TOLERANCE else None
```

`relation.project_to_plane` and `relation._point_in_polygon_2d` are the same two helpers Task 4 put
in `uedcli/relation.py` (`project_to_plane` was already there; `_point_in_polygon_2d` is Task 4's
addition, placed after `_shares_vertex`). Add `from . import relation` to `actor_survey.py`'s import
block in this task — Task 7 left it out because nothing needed it yet.

`face.verts` holds ONE representative surviving fragment of that (owner, plane), not the whole
authored face (Task 10's dedup). The bound is therefore against that fragment's ring. That is the
correct scope for locality — a fragment is real surviving surface — but it does mean a source point
over a DIFFERENT fragment of the same owner-plane is not counted. Both `crosses` fixtures place the
intruder over the face it pokes through, so neither exercises that; if a real level turns up a case
that needs the whole plane instead, report it rather than widening the bound here.

- [ ] **Step 6: Implement `crosses_facts_for`, both directions**

```python
def crosses_facts_for(ctx: SurveyContext) -> list:
    """`crosses`: a solid actor's own matter extends past a resolved surviving face belonging to
    another actor, into space it does not itself claim.

    Fixed-direction -- the intruder always leads -- so this computes BOTH directions:

    * the surveyed actor as the INTRUDER, when it is source-eligible: test its own matter against
      every eligible face in the neighborhood.
    * the surveyed actor as the TARGET, always: scan the neighborhood for source-eligible actors
      whose matter lands past one of the SURVEYED actor's own faces. A source-ineligible surveyed
      actor (a Subtract, say) has no outgoing `crosses` at all, but can perfectly well be the `dst`
      of someone else's -- the spec's own worked example is exactly that shape.

    At most one fact per (src, dst): a wall is many fragments and several planes, and one
    relationship is one line."""
    facts: dict = {}
    if ctx.probe.solidity is None:
        return []

    def record(src, dst, depth):
        key = (src, dst)
        prev = facts.get(key)
        if prev is None or depth > prev.depth_uu:
            facts[key] = CsgFact(src=src, dst=dst, relation="crosses", depth_uu=depth)

    # Direction 1: the surveyed actor intrudes.
    if crosses_source_eligible(ctx.surveyed, ctx.class_index, ctx.defaults):
        points = source_points(ctx, ctx.surveyed)
        if points:
            for face in ctx.faces:
                if face.owner == ctx.name:
                    continue
                target = ctx.level.actors.get(face.owner)
                if target is None or not crosses_target_eligible(target, ctx.class_index):
                    continue
                depth = penetration_depth(ctx, points, face)
                if depth is not None:
                    record(ctx.name, face.owner, depth)

    # Direction 2: somebody else intrudes on the surveyed actor.
    if crosses_target_eligible(ctx.surveyed, ctx.class_index):
        own_faces = [f for f in ctx.faces if f.owner == ctx.name]
        if own_faces:
            for other in ctx.near:
                if not crosses_source_eligible(other, ctx.class_index, ctx.defaults):
                    continue
                points = source_points(ctx, other)
                if not points:
                    continue
                for face in own_faces:
                    depth = penetration_depth(ctx, points, face)
                    if depth is not None:
                        record(other.name, ctx.name, depth)
            # Point actors too. This is why `nearby_point_actors` (Task 7) filters candidates by
            # their own extent-aware region: a collision cylinder can reach into the surveyed
            # brush from a `Location` outside it, and a bare-`Location` filter drops those --
            # making the fact visible from one side of the pair and not the other.
            for p in ctx.points:
                if not crosses_source_eligible(p, ctx.class_index, ctx.defaults):
                    continue
                points = source_points(ctx, p)
                if not points:
                    continue
                for face in own_faces:
                    depth = penetration_depth(ctx, points, face)
                    if depth is not None:
                        record(p.name, ctx.name, depth)

    return [facts[k] for k in sorted(facts)]
```

- [ ] **Step 7: Run the tests, iterate to green**

Run: `bin/test -k "crosses_fires or crosses_never_fires or crosses_does_not_fire or crosses_reports_the_reverse or crosses_dedupes or face_outward" -v`
Expected: PASS

If `test_crosses_fires_for_an_add_poking_through_a_niche_wall...` fires against `Additive2` as well
as `Subtract3`, check WHICH face by printing `(face.owner, face.normal, face.offset, depth)` first.

The mechanism that is supposed to stop it is `penetration_depth`'s within-the-ring bound (Step 5):
a shelf point may well sit on the solid side of `Additive2`'s infinite plane, but if it does not
project INSIDE that face's own vertex ring it contributes no depth and no fact. A stray `Additive2`
fact almost certainly means that bound is missing or projecting against mismatched origins — fix
the bound.

Do NOT reach instead for a nearest-owner-wins filter: comparing the candidate faces against each
other and keeping only the closest owner is a different mechanism and a new rule this plan has no
authority to invent — it would throw away true facts about the other owners. The two are easy to
confuse because they suppress the same symptom here; only the ring bound is authorised. If the ring
bound is correct and `Additive2` still fires, that is a real disagreement between the spec's
locality rule and the geometry: report it and get a ruling.

- [ ] **Step 8: Run the whole suite, then commit**

Run: `bin/test`

```bash
git add uedcli/actor_survey.py uedcli/tests/survey_scenarios.py uedcli/tests/test_actor_survey.py
git commit -m "actor survey: csg-tier crosses"
```

---

### Task 13: `touches` (csg tier)

**Files:**
- Modify: `uedcli/actor_survey.py`
- Test: `uedcli/tests/test_actor_survey.py`

**Interfaces:**
- Consumes: Task 12's `source_points`, `face_outward_sign`, `penetration_depth`; Task 11's
  eligibility predicates.
- Produces: `def touches_facts_for(ctx) -> list[CsgFact]` — symmetric, the surveyed actor leads, no
  depth, no `:idx`. NOT source-restricted (unlike `crosses`): a Subtract's carve legitimately stops
  flush against a wall it never cut, and that is worth reporting.

- [ ] **Step 1: Write the failing tests**

```python
def test_touches_fires_between_the_surveyed_actor_and_a_face_it_is_flush_against():
    import pytest
    pytest.importorskip("uedcli_native")
    sc = scen.niche_carved_into_wall()
    ctx = actor_survey.build_context(sc.level, sc.index, "Bystander", sc.defaults)
    facts = actor_survey.touches_facts_for(ctx)
    assert any(f.src == "Bystander" and f.dst == "Wall" and f.relation == "touches"
               for f in facts)
    assert all(f.depth_uu is None for f in facts)


def test_touches_is_not_source_restricted_so_a_subtract_can_lead_one():
    """Unlike `crosses`. A room's Subtract stopping exactly at its bounding wall is how 'this room
    is bounded by that wall, and the wall is intact' gets stated."""
    import pytest
    pytest.importorskip("uedcli_native")
    sc = scen.subtract_stops_flush_against_a_wall()
    ctx = actor_survey.build_context(sc.level, sc.index, "Room", sc.defaults)
    facts = actor_survey.touches_facts_for(ctx)
    assert any(f.src == "Room" and f.dst == "Wall" for f in facts)


def test_touches_and_crosses_are_mutually_exclusive_for_one_pair():
    """Within CSG_TOLERANCE of coincident is `touches`; clearly past it is `crosses`. A pair is
    never both."""
    import pytest
    pytest.importorskip("uedcli_native")
    sc = scen.shelf_pokes_through_a_niche_wall()
    ctx = actor_survey.build_context(sc.level, sc.index, "Additive4", sc.defaults)
    crossed = {(f.src, f.dst) for f in actor_survey.crosses_facts_for(ctx)}
    touched = {(f.src, f.dst) for f in actor_survey.touches_facts_for(ctx)}
    assert crossed & touched == set()


def test_touches_never_names_a_nonsolid_or_an_intersect_as_the_other_side():
    import pytest
    pytest.importorskip("uedcli_native")
    sc = scen.kind_table_scenario()
    ctx = actor_survey.build_context(sc.level, sc.index, "Adder", sc.defaults)
    named = {f.dst for f in actor_survey.touches_facts_for(ctx)}
    assert named.isdisjoint({"Nonsolid", "Inter", "Deinter", "Lamp"})
```

Add the scenario:

```python
# --------------------------------------------------------------------- Task 13's scenario

def subtract_stops_flush_against_a_wall() -> Scenario:
    """Trunk order: Wall, Room.

    * `Wall` 64 x 512 x 512 Add at (256, 0, 0)       — x in [224, 288]
    * `Room` 448 x 512 x 512 Subtract at (0, 0, 0)   — x in [-224, 224], stopping EXACTLY at the
      wall's -X face and removing none of its matter

    `Room` is later in trunk order, so the raw tier's order heuristic calls this `carves`; the csg
    tier must call it `touches` and NOT `carves` (Task 17's contrast test uses the same fixture).
    """
    return _scenario([
        brush("Wall", (64, 512, 512), (256, 0, 0)),
        brush("Room", (448, 512, 512), (0, 0, 0), csg="subtract"),
    ])
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `bin/test -k "touches_fires_between or touches_is_not_source_restricted or touches_and_crosses_are_mutually or touches_never_names" -v`
Expected: FAIL — `touches_facts_for` does not exist.

- [ ] **Step 3: Implement `touches_facts_for`**

```python
def _is_flush(ctx: SurveyContext, points, face) -> bool:
    """Is any of `points` ON `face`'s plane, within `CSG_TOLERANCE`, without reaching past it?

    Decided by PLANE COINCIDENCE, which is the spec's own soundness constraint: a redundant coplanar
    face appearing or vanishing in a truncated solve must not change a reported fact. `ctx.faces`
    has already collapsed every coplanar fragment of one owner to one plane, so what is tested here
    is the plane, not the fragment."""
    if penetration_depth(ctx, points, face) is not None:
        return False                      # it reaches past: that is `crosses`, not `touches`
    return any(abs(sum(face.normal[i] * p[i] for i in range(3)) - face.offset) <= CSG_TOLERANCE
               for p in points)


def touches_facts_for(ctx: SurveyContext) -> list:
    """`touches`: the surveyed actor's own matter is flush against a resolved face belonging to
    another actor, with no penetration.

    Symmetric, so the surveyed actor always leads (spec, Directionality). NOT source-restricted,
    unlike `crosses` -- a Subtract's carve legitimately touching the resolved boundary it stopped at
    is exactly the fact worth reporting. The OTHER side must still author a resolved face, so
    `crosses_target_eligible` gates it: a Nonsolid bounds no solid, an Intersect/Deintersect
    contributes nothing, and a non-brush actor's collision cylinder is not world geometry.

    Two Subtracts sharing a plane produce no surviving face between them at all, so this never fires
    for that pair -- that case is `connects` (Task 14), and the spec spells out why they cannot
    collide."""
    if ctx.probe.solidity is None:
        return []
    points = source_points(ctx, ctx.surveyed)
    if not points:
        return []
    seen: dict = {}
    for face in ctx.faces:
        if face.owner == ctx.name:
            continue
        other = ctx.level.actors.get(face.owner)
        if other is None or not crosses_target_eligible(other, ctx.class_index):
            continue
        if (ctx.name, face.owner) in seen:
            continue
        if _is_flush(ctx, points, face):
            seen[(ctx.name, face.owner)] = CsgFact(src=ctx.name, dst=face.owner,
                                                    relation="touches")
    return [seen[k] for k in sorted(seen)]
```

`source_points` returns the surveyed actor's own matter — its brush cells' vertices, or its
collision cylinder samples. For a SUBTRACT the cells' vertices are its authored carve volume's
corners, which is what "the carve stopped here" means geometrically.

- [ ] **Step 4: Run the tests, iterate to green**

Run: `bin/test -k "touches_fires_between or touches_is_not_source_restricted or touches_and_crosses_are_mutually or touches_never_names" -v`
Expected: PASS

- [ ] **Step 5: Run the whole suite, then commit**

Run: `bin/test`

```bash
git add uedcli/actor_survey.py uedcli/tests/survey_scenarios.py uedcli/tests/test_actor_survey.py
git commit -m "actor survey: csg-tier touches"
```

---

### Task 14: `connects`

**Files:**
- Modify: `uedcli/actor_survey.py`
- Modify: `uedcli/tests/survey_scenarios.py` (three builders)
- Test: `uedcli/tests/test_actor_survey.py`

**Interfaces:**
- Consumes: `query.csg_is_subtract`, `actorgraph.point_in_brush`, the `SurveyContext`'s `probe` and
  `cells`.
- Produces:

```python
CONNECT_GRID: int = 5

def shared_region(a, b) -> tuple | None          # the intersection box of two actors' AABBs, or None
def region_sample_points(lo, hi, n: int = CONNECT_GRID) -> list
def voids_meet(ctx, a, b) -> bool
def connects_facts_for(ctx) -> list[CsgFact]
```

**The rule, and why it is decided this way.** Two Subtracts `connect` when their void regions are
continuous — structurally the ABSENCE of a separating face, not the presence of one. The spec forbids
deciding it by zone number (the zone flood is a whole-model pass, so zone numbers are not reproducible
under a truncated solve, spike.md §4 residual 3). What it must be decided by is local solidity.

Concretely: take the intersection box of the two Subtracts' own authored AABBs, grown by
`CSG_TOLERANCE`; `connects` fires when at least one sampled point in that box is claimed by BOTH
actors' authored shapes and is VOID in the resolved world. Read against the spec's own cases:

- **partial merge** (two overlapping rooms): the shared box is a real volume, void inside → fires.
- **full nesting** (a smaller Subtract carved entirely inside a bigger one's already-void space):
  the shared box is the inner volume, void → fires. `connects`, never `contains` — it is not content.
- **two adjacent rooms sharing a coincident plane** (an extremely common shape): the shared box is a
  zero-thickness slab, and its centre sample lies exactly on both authored boundaries, which
  `point_in_brush` accepts within its own `_VERTEX_EPS`. Void → fires. This is the spec's key
  disambiguation: it is `connects`, not `touches`, because two Subtracts sharing a plane leave no
  surviving solid face for anything to be flush against.
- **two rooms separated by an intact Add wall**: either the authored boxes do not meet at all, or the
  shared samples are SOLID (the Add fills them) → does not fire.

**Its honest limit:** a fixed `CONNECT_GRID` sample can miss a connection narrower than the sample
spacing — a doorway one grid cell wide in a large shared box. The grid always includes the box centre
and its eight corners, so the common shapes above are covered; a genuinely thin opening is a known
false negative, recorded here rather than claimed away.

- [ ] **Step 1: Write the failing tests**

Add the scenarios:

```python
# --------------------------------------------------------------------- Task 14's scenarios

def two_rooms_sharing_a_plane() -> Scenario:
    """Trunk order: Shell, RoomA, RoomB.

    * `Shell` 2048^3 Add at (0, 0, 0)               — solid matter for the rooms to carve
    * `RoomA` 512^3 Subtract at (-256, 0, 0)        — x in [-512, 0]
    * `RoomB` 512^3 Subtract at (256, 0, 0)         — x in [0, 512], sharing the x = 0 plane exactly

    The spec's disambiguation case: `connects`, never `touches` — nothing solid survives between
    them to be flush against.
    """
    return _scenario([
        brush("Shell", (2048, 2048, 2048), (0, 0, 0)),
        brush("RoomA", (512, 512, 512), (-256, 0, 0), csg="subtract"),
        brush("RoomB", (512, 512, 512), (256, 0, 0), csg="subtract"),
    ])


def two_rooms_split_by_an_intact_wall() -> Scenario:
    """Trunk order: Shell, RoomA, RoomB, Wall.

    Same two rooms, plus `Wall` 64 x 512 x 512 Add at (0, 0, 0) filling x in [-32, 32] — so the
    shared region between them is solid and the voids do not meet.
    """
    return _scenario([
        brush("Shell", (2048, 2048, 2048), (0, 0, 0)),
        brush("RoomA", (576, 512, 512), (-288, 0, 0), csg="subtract"),
        brush("RoomB", (576, 512, 512), (288, 0, 0), csg="subtract"),
        brush("Wall", (64, 512, 512), (0, 0, 0)),
    ])


def redundant_nested_subtract() -> Scenario:
    """Trunk order: Shell, OuterRoom, InnerCarve.

    * `Shell`      2048^3 Add at (0, 0, 0)
    * `OuterRoom`  512^3 Subtract at (0, 0, 0)
    * `InnerCarve` 128^3 Subtract at (0, 0, 0)   — entirely inside OuterRoom's already-void space

    `connects`, never `contains`: a redundant carve is not content.
    """
    return _scenario([
        brush("Shell", (2048, 2048, 2048), (0, 0, 0)),
        brush("OuterRoom", (512, 512, 512), (0, 0, 0), csg="subtract"),
        brush("InnerCarve", (128, 128, 128), (0, 0, 0), csg="subtract"),
    ])
```

Append to `uedcli/tests/test_actor_survey.py`:

```python
def test_connects_fires_for_two_subtracts_sharing_a_plane_and_touches_does_not():
    """The spec's key disambiguation. Two Subtracts sharing a coincident plane leave no surviving
    solid face between them, so there is nothing to be flush against — it can only be `connects`."""
    import pytest
    pytest.importorskip("uedcli_native")
    sc = scen.two_rooms_sharing_a_plane()
    ctx = actor_survey.build_context(sc.level, sc.index, "RoomA", sc.defaults)
    assert any(f.src == "RoomA" and f.dst == "RoomB" and f.relation == "connects"
               for f in actor_survey.connects_facts_for(ctx))
    assert not any(f.dst == "RoomB" for f in actor_survey.touches_facts_for(ctx))


def test_connects_does_not_fire_across_an_intact_wall():
    import pytest
    pytest.importorskip("uedcli_native")
    sc = scen.two_rooms_split_by_an_intact_wall()
    ctx = actor_survey.build_context(sc.level, sc.index, "RoomA", sc.defaults)
    assert not any(f.dst == "RoomB" for f in actor_survey.connects_facts_for(ctx))


def test_connects_fires_for_a_fully_nested_redundant_subtract():
    import pytest
    pytest.importorskip("uedcli_native")
    sc = scen.redundant_nested_subtract()
    ctx = actor_survey.build_context(sc.level, sc.index, "OuterRoom", sc.defaults)
    assert any(f.dst == "InnerCarve" and f.relation == "connects"
               for f in actor_survey.connects_facts_for(ctx))


def test_connects_is_subtract_only():
    import pytest
    pytest.importorskip("uedcli_native")
    sc = scen.two_rooms_sharing_a_plane()
    ctx = actor_survey.build_context(sc.level, sc.index, "Shell", sc.defaults)
    assert actor_survey.connects_facts_for(ctx) == []


def test_connects_reads_no_zone_number():
    """The zone flood is a whole-model pass, so zone numbers are not reproducible under a truncated
    solve (spike.md §4 residual 3). No survey relation may read one."""
    import inspect
    src = inspect.getsource(actor_survey.connects_facts_for) + \
        inspect.getsource(actor_survey.voids_meet)
    assert "zone" not in src.lower()
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `bin/test -k "connects_" -v`
Expected: FAIL — `connects_facts_for` does not exist.

- [ ] **Step 3: Implement it**

```python
# How finely the shared region between two Subtracts is sampled when deciding whether their voids
# meet. 5 per axis = 125 points, and the grid always lands exactly on the box centre and its eight
# corners (n odd), which is what makes the zero-thickness coincident-plane case work.
CONNECT_GRID = 5


def shared_region(a, b):
    """The intersection of two actors' world AABBs, grown by `CSG_TOLERANCE`, or None when they do
    not meet at all. Returned in floats -- this feeds sampling, not `aabb_intersects`."""
    a_lo, a_hi = actor_bounds(a)
    b_lo, b_hi = actor_bounds(b)
    lo = tuple(max(float(a_lo[i]), float(b_lo[i])) - CSG_TOLERANCE for i in range(3))
    hi = tuple(min(float(a_hi[i]), float(b_hi[i])) + CSG_TOLERANCE for i in range(3))
    if any(lo[i] > hi[i] for i in range(3)):
        return None
    return lo, hi


def region_sample_points(lo, hi, n: int = CONNECT_GRID) -> list:
    """An `n x n x n` grid over the box, endpoints included. `n` must be odd so the grid lands on
    the box CENTRE -- for a zero-thickness axis (two brushes sharing a plane exactly) the centre is
    the only sample that lies on both authored boundaries."""
    def axis(i):
        span = hi[i] - lo[i]
        if span <= 0.0:
            return [lo[i]]
        return [lo[i] + span * k / (n - 1) for k in range(n)]
    xs, ys, zs = axis(0), axis(1), axis(2)
    return [(x, y, z) for x in xs for y in ys for z in zs]


def voids_meet(ctx: SurveyContext, a, b) -> bool:
    """Are `a`'s and `b`'s void regions continuous -- no surviving solid between them?

    Decided by LOCAL SOLIDITY, never by zone identity: the zone flood is a whole-model pass, so zone
    numbers are not reproducible under the bounded-neighborhood solve (spike.md §4 residual 3), and
    two rooms can share a zone without their voids meeting at all.

    True when at least one sampled point of the two actors' shared region is claimed by BOTH
    authored shapes and is VOID in the resolved world. Known limit: a connection narrower than the
    sample spacing can be missed; the grid always includes the box centre and corners, so the
    partial-merge, full-nesting and shared-plane shapes the spec names are covered."""
    if ctx.probe.solidity is None:
        return False
    region = shared_region(a, b)
    if region is None:
        return False
    for p in region_sample_points(*region):
        if ctx.probe.solidity.point_is_solid(p):
            continue
        if actorgraph.point_in_brush(a, p, cache=ctx.cells) and \
                actorgraph.point_in_brush(b, p, cache=ctx.cells):
            return True
    return False


def connects_facts_for(ctx: SurveyContext) -> list:
    """`connects`: the surveyed Subtract's void is continuous with another Subtract's void.

    Subtract-only on both sides, symmetric, so the surveyed actor leads. No depth and no `:idx` --
    the fact is the absence of a face, and there is no face to name."""
    if ctx.surveyed.brush is None or not query.csg_is_subtract(ctx.surveyed):
        return []
    out = []
    for other in ctx.near:
        if not query.csg_is_subtract(other):
            continue
        try:
            if voids_meet(ctx, ctx.surveyed, other):
                out.append(CsgFact(src=ctx.name, dst=other.name, relation="connects"))
        except actorgraph.DegenerateBrushError:
            continue          # a bad neighbour is skipped, as it is in the raw tier
    return sorted(out, key=lambda f: f.dst)
```

`actor_bounds` is already imported at the top of `actor_survey.py` (Task 7).

- [ ] **Step 4: Run the tests, iterate to green**

Run: `bin/test -k "connects_" -v`
Expected: PASS

- [ ] **Step 5: Run the whole suite, then commit**

Run: `bin/test`

```bash
git add uedcli/actor_survey.py uedcli/tests/survey_scenarios.py uedcli/tests/test_actor_survey.py
git commit -m "actor survey: csg-tier connects"
```

---

### Task 15: `contains` primitives — authored volume and authored containment

Split out of `contains` so the geometry lands and is tested on its own, before the competition rule
and the two survey directions are layered on it (Task 16).

**Files:**
- Modify: `uedcli/actor_survey.py`
- Test: `uedcli/tests/test_actor_survey.py`

**Interfaces:**
- Consumes: `actorgraph.decompose_convex`, `actorgraph.point_in_brush`, `actorgraph.ConvexCell`,
  `actorgraph._VERTEX_EPS`, `texframe.newell`.
- Produces:

```python
def cell_volume(cell) -> float
def authored_volume(actor, cells: dict) -> float
def authored_shape_contains(container, target, cells: dict) -> bool
```

  Note the naming: both take ACTORS and say so. (An earlier draft of this plan had a function called
  `_authored_volume` being handed an actor, which reads as if it takes a volume — a subagent
  implementing from the name alone would get it backwards.)

- [ ] **Step 1: Write the failing tests**

```python
def test_cell_volume_of_a_cube_is_exact():
    from uedcli import actorgraph
    sc = scen.kind_table_scenario()
    cells = actorgraph.decompose_convex(sc.level.actors["Adder"])
    assert len(cells) == 1
    assert actor_survey.cell_volume(cells[0]) == pytest.approx(64.0 ** 3, rel=1e-6)


def test_authored_volume_sums_every_cell_of_a_non_convex_brush():
    """An L-shaped brush decomposes to 2+ cells; the authored volume is their sum, not one cell's.
    Geometry: the same L `test_actorgraph.py::_l_shaped_brush` builds — a 128x128x64 footprint with
    the upper-right 64x64 quadrant missing, so 3/4 of 128*128*64."""
    from uedcli.tests.test_actorgraph import _l_shaped_brush
    a = _l_shaped_brush()
    assert actor_survey.authored_volume(a, {}) == pytest.approx(128 * 128 * 64 * 0.75, rel=1e-4)


def test_authored_shape_contains_a_point_actor_by_its_location():
    sc = scen.room_with_pillar_and_light()
    assert actor_survey.authored_shape_contains(sc.level.actors["Room"],
                                                sc.level.actors["Light"], {}) is True
    assert actor_survey.authored_shape_contains(sc.level.actors["Pillar"],
                                                sc.level.actors["Light"], {}) is False


def test_authored_shape_contains_a_brush_only_on_FULL_containment():
    """Strict full containment, deliberately (spec): a large Add that only PARTIALLY pokes out of a
    Subtract gets no csg `contains`, even though raw `contains` (touch-or-overlap) reports one.
    That is the stated cost of a strict predicate, not an oversight."""
    sc = scen.shelf_pokes_through_a_niche_wall()
    inside = sc.level.actors["Subtract3"]
    poking = sc.level.actors["Additive4"]
    assert actor_survey.authored_shape_contains(inside, poking, {}) is False
    small = scen.pillar_in_room()
    assert actor_survey.authored_shape_contains(small.level.actors["Room"],
                                                small.level.actors["Pillar"], {}) is True


def test_authored_shape_contains_uses_the_actors_own_authored_shape_not_its_aabb():
    """An L-shaped container must not claim something sitting in its notch."""
    from uedcli.model import Actor, Level
    from uedcli.tests.test_actorgraph import _l_shaped_brush
    from decimal import Decimal
    container = _l_shaped_brush()
    in_notch = Actor(name="Notch", cls="Engine.Light",
                     location=tuple(Decimal(str(c)) for c in (96, 96, 0)))
    in_arm = Actor(name="Arm", cls="Engine.Light",
                   location=tuple(Decimal(str(c)) for c in (32, 32, 0)))
    del Level
    assert actor_survey.authored_shape_contains(container, in_notch, {}) is False
    assert actor_survey.authored_shape_contains(container, in_arm, {}) is True
```

Add `import pytest` at the top of `uedcli/tests/test_actor_survey.py` if it is not already there.
Check `_l_shaped_brush`'s real footprint before trusting the 0.75 factor: read
`uedcli/tests/test_actorgraph.py`'s own `_l_shaped_brush` and compute the expected volume from its
actual vertex list (the L is 128x128 minus a 64x64 quadrant, 64 tall, as of this plan — re-derive it
rather than copying this number if the fixture has changed).

- [ ] **Step 2: Run the tests to verify they fail**

Run: `bin/test -k "cell_volume or authored_volume or authored_shape_contains" -v`
Expected: FAIL — none of these exists.

- [ ] **Step 3: Implement them**

```python
def cell_volume(cell) -> float:
    """The volume of one `actorgraph.ConvexCell`.

    A convex polytope's volume is the sum of tetrahedra from any interior point to each face's
    triangulation. The cell's vertex centroid IS interior (a convex hull's centroid always is), so
    every tetrahedron is non-overlapping and the absolute values sum cleanly -- no winding or
    orientation question to get wrong. Each face is the vertex subset lying on one bounding plane,
    ordered around that plane's normal before fanning."""
    verts = [tuple(float(c) for c in v) for v in cell.vertices]
    if len(verts) < 4:
        return 0.0
    c = tuple(sum(v[i] for v in verts) / len(verts) for i in range(3))
    total = 0.0
    for normal, d in cell.half_spaces:
        n = tuple(float(x) for x in normal)
        on = [v for v in verts
              if abs(sum(n[i] * v[i] for i in range(3)) - float(d)) <= actorgraph._VERTEX_EPS]
        if len(on) < 3:
            continue
        ordered = _order_around(on, n)
        a = ordered[0]
        for i in range(1, len(ordered) - 1):
            b, e = ordered[i], ordered[i + 1]
            ab = tuple(a[k] - c[k] for k in range(3))
            cb = tuple(b[k] - c[k] for k in range(3))
            db = tuple(e[k] - c[k] for k in range(3))
            cross = (cb[1] * db[2] - cb[2] * db[1],
                     cb[2] * db[0] - cb[0] * db[2],
                     cb[0] * db[1] - cb[1] * db[0])
            total += abs(sum(ab[k] * cross[k] for k in range(3))) / 6.0
    return total


def _order_around(points, normal) -> list:
    """`points` (all on one plane with the given normal) sorted by angle around their own centroid,
    so a fan triangulation over them covers the face exactly once."""
    import math
    helper = (0.0, 0.0, 1.0) if abs(normal[2]) < 0.9 else (1.0, 0.0, 0.0)
    u = (helper[1] * normal[2] - helper[2] * normal[1],
         helper[2] * normal[0] - helper[0] * normal[2],
         helper[0] * normal[1] - helper[1] * normal[0])
    ul = (u[0] ** 2 + u[1] ** 2 + u[2] ** 2) ** 0.5 or 1.0
    u = tuple(x / ul for x in u)
    v = (normal[1] * u[2] - normal[2] * u[1],
         normal[2] * u[0] - normal[0] * u[2],
         normal[0] * u[1] - normal[1] * u[0])
    c = tuple(sum(p[i] for p in points) / len(points) for i in range(3))
    def angle(p):
        r = tuple(p[i] - c[i] for i in range(3))
        return math.atan2(sum(r[i] * v[i] for i in range(3)),
                          sum(r[i] * u[i] for i in range(3)))
    return sorted(points, key=angle)


def authored_volume(actor, cells: dict) -> float:
    """The total volume of ACTOR's own authored brush shape (every convex cell summed), in cubic
    world units. 0.0 for a non-brush actor -- it authors no volume, and so never competes to be a
    container. Raises `actorgraph.DegenerateBrushError` for a malformed brush."""
    if actor.brush is None:
        return 0.0
    return sum(cell_volume(c) for c in actorgraph.decompose_convex(actor, cache=cells))


def authored_shape_contains(container, target, cells: dict) -> bool:
    """Does CONTAINER's own authored shape enclose TARGET entirely?

    A non-brush TARGET is tested at its `Location` (an actor with no Location is never contained --
    a substituted origin would invent the fact). A brush or Mover TARGET is tested on its FULL
    extent: every vertex of every decomposed cell must be inside. Strict full containment is
    deliberate (spec): a large Add or Mover that only partially pokes out of a Subtract gets no csg
    `contains`, even though raw `contains` reports one, and majority-of-extent was considered and
    rejected as its own source of ambiguity.

    The test is against the authored SHAPE, via `actorgraph.point_in_brush`, never against an AABB
    -- an L-shaped container must not claim something sitting in its notch."""
    if container.brush is None:
        return False
    if target.brush is None:
        if target.location is None:
            return False
        p = tuple(float(c) for c in target.location)
        return actorgraph.point_in_brush(container, p, cache=cells)
    points = [tuple(float(c) for c in v)
              for cell in actorgraph.decompose_convex(target, cache=cells)
              for v in cell.vertices]
    return bool(points) and all(
        actorgraph.point_in_brush(container, p, cache=cells) for p in points)
```

- [ ] **Step 4: Run the tests, iterate to green**

Run: `bin/test -k "cell_volume or authored_volume or authored_shape_contains or _order_around" -v`
Expected: PASS

- [ ] **Step 5: Run the whole suite, then commit**

Run: `bin/test`

```bash
git add uedcli/actor_survey.py uedcli/tests/test_actor_survey.py
git commit -m "actor survey: authored-volume and authored-containment primitives"
```

---

### Task 16: `contains` — the volume competition, both survey directions

**Files:**
- Modify: `uedcli/actor_survey.py`
- Modify: `uedcli/tests/survey_scenarios.py` (two builders)
- Test: `uedcli/tests/test_actor_survey.py`

**Interfaces:**
- Consumes: Task 15's `authored_volume`/`authored_shape_contains`; `query.csg_is_subtract`.
- Produces:

```python
VOLUME_TOLERANCE_REL: float = 1e-6

def volume_tolerance(a: float, b: float) -> float
def volumes_tied(a: float, b: float) -> bool
def containment_winner(ctx, target, candidates) -> str | None
def contains_facts_for(ctx) -> list[CsgFact]
```

- [ ] **Step 1: Write the failing tests**

Add the scenarios:

```python
# --------------------------------------------------------------------- Task 16's scenarios

def nested_niche_with_a_decoration() -> Scenario:
    """The spec's nesting case, with the inner Add NOT poking through. Trunk order:
    Subtract1, Additive2, Subtract3, Additive4.

    * `Subtract1` 1024^3 Subtract at (0, 0, 0)
    * `Additive2` 256 x 64 x 256 Add at (0, 128, 0)
    * `Subtract3` 128 x 128 x 128 Subtract at (0, 128, 0)   — deliberately OVERSIZED past
      `Additive2`'s own y-extent, the routine way to avoid a coplanar face
    * `Additive4` 32 x 32 x 32 Add at (0, 128, 0)            — a decoration wholly inside Subtract3

    `Subtract3`'s authored volume (2097152) is far smaller than `Subtract1`'s (1073741824), so it
    wins the competition and `Subtract1` reports nothing about `Additive4` — even though `Subtract3`
    is not a strict subset of anything. That is the point of a VOLUME rule rather than a nesting one.
    """
    return _scenario([
        brush("Subtract1", (1024, 1024, 1024), (0, 0, 0), csg="subtract"),
        brush("Additive2", (256, 64, 256), (0, 128, 0)),
        brush("Subtract3", (128, 128, 128), (0, 128, 0), csg="subtract"),
        brush("Additive4", (32, 32, 32), (0, 128, 0)),
    ])


def two_equal_volume_subtracts() -> Scenario:
    """A genuine tie. Trunk order: Shell, EarlierRoom, LaterRoom, Item.

    * `Shell`       2048^3 Add at (0, 0, 0)
    * `EarlierRoom` 512^3 Subtract at (0, 0, 0)
    * `LaterRoom`   512^3 Subtract at (0, 0, 0)   — the SAME box, so the volumes are exactly equal
    * `Item`        a point actor at (0, 0, 0)

    Both contain the Item and their volumes tie within the relative tolerance, so the tie breaks
    toward the LATER one in trunk order.
    """
    return _scenario([
        brush("Shell", (2048, 2048, 2048), (0, 0, 0)),
        brush("EarlierRoom", (512, 512, 512), (0, 0, 0), csg="subtract"),
        brush("LaterRoom", (512, 512, 512), (0, 0, 0), csg="subtract"),
        point("Item", (0, 0, 0)),
    ])
```

Append to `uedcli/tests/test_actor_survey.py`:

```python
def test_contains_is_uncontested_when_the_only_other_candidate_is_an_add():
    """The pillar case: a later Add pillar inside a room never enters the competition — it is not a
    Subtract — so the room wins uncontested and the light is contained regardless of the pillar."""
    import pytest
    pytest.importorskip("uedcli_native")
    sc = scen.room_with_pillar_and_light()
    ctx = actor_survey.build_context(sc.level, sc.index, "Room", sc.defaults)
    assert any(f.src == "Room" and f.dst == "Light" and f.relation == "contains"
               for f in actor_survey.contains_facts_for(ctx))


def test_contains_picks_the_smallest_authored_volume_when_nested():
    import pytest
    pytest.importorskip("uedcli_native")
    sc = scen.nested_niche_with_a_decoration()
    inner = actor_survey.build_context(sc.level, sc.index, "Subtract3", sc.defaults)
    outer = actor_survey.build_context(sc.level, sc.index, "Subtract1", sc.defaults)
    assert any(f.src == "Subtract3" and f.dst == "Additive4"
               for f in actor_survey.contains_facts_for(inner))
    assert not any(f.dst == "Additive4" for f in actor_survey.contains_facts_for(outer))


def test_contains_breaks_an_exact_volume_tie_toward_the_later_brush():
    import pytest
    pytest.importorskip("uedcli_native")
    sc = scen.two_equal_volume_subtracts()
    later = actor_survey.build_context(sc.level, sc.index, "LaterRoom", sc.defaults)
    earlier = actor_survey.build_context(sc.level, sc.index, "EarlierRoom", sc.defaults)
    assert any(f.src == "LaterRoom" and f.dst == "Item"
               for f in actor_survey.contains_facts_for(later))
    assert not any(f.dst == "Item" for f in actor_survey.contains_facts_for(earlier))


def test_contains_shows_the_same_fact_when_the_contained_actor_is_surveyed():
    """Fixed-direction: the container leads whichever side you ask about."""
    import pytest
    pytest.importorskip("uedcli_native")
    sc = scen.room_with_pillar_and_light()
    ctx = actor_survey.build_context(sc.level, sc.index, "Light", sc.defaults)
    assert any(f.src == "Room" and f.dst == "Light"
               for f in actor_survey.contains_facts_for(ctx))


def test_contains_never_has_an_intersect_or_deintersect_as_the_container():
    """They contribute nothing to the world at all, so they can never be the container side."""
    import pytest
    pytest.importorskip("uedcli_native")
    sc = scen.kind_table_scenario()
    ctx = actor_survey.build_context(sc.level, sc.index, "Lamp", sc.defaults)
    assert not any(f.src in ("Inter", "Deinter")
                   for f in actor_survey.contains_facts_for(ctx))


def test_volume_tolerance_is_a_named_constant_not_an_inline_literal():
    import inspect
    assert actor_survey.VOLUME_TOLERANCE_REL == 1e-6
    assert "1e-6" not in inspect.getsource(actor_survey.containment_winner)
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `bin/test -k "contains_is_uncontested or contains_picks_the_smallest or contains_breaks_an_exact or contains_shows_the_same_fact or contains_never_has_an_intersect or volume_tolerance_is_a_named" -v`
Expected: FAIL — `contains_facts_for` does not exist.

- [ ] **Step 3: Implement the competition**

```python
# Relative tolerance for the containment volume comparison. Named, not an inline literal, and
# RELATIVE rather than absolute: a level's Subtract volumes span many orders of magnitude, so a
# fixed epsilon would be meaningless at one end and dominant at the other. Matches `relation.py`'s
# own `_close`-style convention for the same problem on areas (spec: a genuine tie must break on
# trunk order, not on float noise).
VOLUME_TOLERANCE_REL = 1e-6


def volume_tolerance(a: float, b: float) -> float:
    return VOLUME_TOLERANCE_REL * max(1.0, abs(a), abs(b))


def volumes_tied(a: float, b: float) -> bool:
    return abs(a - b) <= volume_tolerance(a, b)


def containment_winner(ctx: SurveyContext, target, candidates) -> str | None:
    """Which of `candidates` (Subtract actors) owns `target`, or None when none does.

    The spec's rule: every candidate whose own AUTHORED shape fully contains `target` competes, and
    the one with the SMALLEST authored volume wins; a genuine tie within the relative tolerance
    breaks toward the LATER one in trunk order. A volume comparison, not a strict-subset/nesting
    test -- it stays correct when a carve brush is deliberately oversized past what it carves into,
    which is routine (to avoid coplanar faces) and which a subset rule silently gets wrong."""
    order = {n: i for i, n in enumerate(ctx.level.order)}
    best_name, best_volume = None, None
    for c in candidates:
        if c.name == target.name or not query.csg_is_subtract(c):
            continue
        try:
            if not authored_shape_contains(c, target, ctx.cells):
                continue
            volume = authored_volume(c, ctx.cells)
        except actorgraph.DegenerateBrushError:
            continue
        if best_volume is None or volume < best_volume - volume_tolerance(volume, best_volume):
            best_name, best_volume = c.name, volume
        elif volumes_tied(volume, best_volume) and order[c.name] > order[best_name]:
            best_name, best_volume = c.name, volume
    return best_name


def _containment_candidates(ctx: SurveyContext) -> list:
    """Every Subtract that could own something here: the surveyed actor when it is one, plus every
    Subtract in its neighborhood. `Intersect`/`Deintersect` are excluded by `csg_is_subtract` itself
    (their `CsgOper` is neither), which is also why they can never be a container."""
    out = [a for a in ctx.near if a.brush is not None and query.csg_is_subtract(a)]
    if ctx.surveyed.brush is not None and query.csg_is_subtract(ctx.surveyed):
        out.append(ctx.surveyed)
    return out


def contains_facts_for(ctx: SurveyContext) -> list:
    """`contains`: the container (a Subtract) leads, whichever side is surveyed.

    Two directions, both computed:
    * the surveyed actor as CONTAINER, when it is a Subtract: every brush, Mover and point actor in
      its neighborhood whose full extent (or Location) its authored shape encloses, and which it
      WINS against every other competing Subtract.
    * the surveyed actor as CONTAINED, always: whichever Subtract in its neighborhood wins it.

    Not narrower than the raw tier, which fans containment out both ways already -- `build_graph`
    emits one edge per containing brush, and Task 8's raw tier reuses that shape."""
    candidates = _containment_candidates(ctx)
    facts: list = []

    if ctx.surveyed.brush is not None and query.csg_is_subtract(ctx.surveyed):
        targets = [a for a in ctx.near if a.name != ctx.name] + list(ctx.points)
        for target in targets:
            if containment_winner(ctx, target, candidates) == ctx.name:
                facts.append(CsgFact(src=ctx.name, dst=target.name, relation="contains"))

    owner = containment_winner(ctx, ctx.surveyed, candidates)
    if owner is not None and owner != ctx.name:
        facts.append(CsgFact(src=owner, dst=ctx.name, relation="contains"))

    return sorted(facts, key=lambda f: (f.src, f.dst))
```

- [ ] **Step 4: Run the tests, iterate to green**

Run: `bin/test -k "contains_is_uncontested or contains_picks_the_smallest or contains_breaks_an_exact or contains_shows_the_same_fact or contains_never_has_an_intersect or volume_tolerance_is_a_named" -v`
Expected: PASS

If `test_contains_breaks_an_exact_volume_tie_toward_the_later_brush` fails because the two identical
boxes' computed volumes differ by more than the relative tolerance, that is a real finding about
`cell_volume`'s numerical behavior on identical inputs — report it rather than widening the tolerance,
which would change the spec's stated rule.

- [ ] **Step 5: Run the whole suite, then commit**

Run: `bin/test`

```bash
git add uedcli/actor_survey.py uedcli/tests/survey_scenarios.py uedcli/tests/test_actor_survey.py
git commit -m "actor survey: csg-tier contains"
```

---

### Task 17: `carves`

**Files:**
- Modify: `uedcli/actor_survey.py`
- Modify: `uedcli/tests/survey_scenarios.py` (two builders)
- Test: `uedcli/tests/test_actor_survey.py`

**Interfaces:**
- Consumes: `preview_native.solve_world_probe`, `texframe.newell`, `polyalign._world_verts`,
  `query.csg_is_subtract`, `kind_of`, Task 11's `SurveyContext`.
- Produces:

```python
CARVE_AREA_EPS: float = 1.0        # uu^2

def poly_area(verts) -> float
def authored_face_area(actor) -> float
def surviving_face_area(probe, owner: str) -> float
def removed_by(ctx, subtract, victim) -> bool
def carves_facts_for(ctx) -> list[CsgFact]
```

**The technique, chosen rather than sketched.** `carves` records HISTORY — matter that used to extend
further before a Subtract reduced it — which neither `crosses` nor `touches` expresses. One solve can
say "X lost face area" (compare X's surviving world-face area against its own authored face area),
but not by WHOSE hand. The spec needs attribution, and it also rules on the case that makes
attribution hard: a second Subtract carving *exactly* the region a first one already carved must NOT
report `carves` against the original Add (there is nothing left of it to remove there), while one
that only *partially* overlaps must report `carves` for the genuinely new part.

An area-overlap heuristic ("S's volume covers part of X's face, and some of that face is missing")
gets the exact-duplicate case wrong. So this task uses a **counterfactual solve**: re-solve the same
neighborhood with `S` removed, and compare `X`'s surviving face area with and without it. More area
survives without `S` ⟺ `S` removed some of `X`'s matter. That is exactly the comparison
`kind_semantics.py` makes for its own uncut-vs-cut measurement (`_solve([room, pillar])` against
`_solve([room, pillar, cutter])`, then `_pillar_area` on each), and it gets both spec cases right by
construction.

Its cost, stated with the measured numbers rather than hand-waved: one extra neighborhood solve per
candidate Subtract. The spike timed a neighborhood solve at a median 6 ms and a worst 46 ms over 140
surveys, and a survey's neighborhood typically holds a handful of Subtracts — so this is tens of
milliseconds, against the 31 ms the raw tier costs on the same survey. This is NOT the level-wide
`O(N)` cost the technique would have had if applied to a whole level; it is bounded by the
neighborhood, which is a median 0.5% of a level's brushes.

Two guards it needs, both from the spike's own residuals:

1. **Never drop the level's first world-CSG brush** from the counterfactual set — that would fire
   `bsp_brush_csg`'s leading-Add world-shell shortcut on a different brush and change the whole
   tree (spike.md §4 residual 4). When the candidate Subtract IS that brush, skip the counterfactual
   and report nothing for it, rather than solving a world the argument does not cover.
2. **Compare AREA, never face COUNT or poly identity** — a different tree shape splits the same
   surface into different polygons (residual 1). `CARVE_AREA_EPS` is the floor below which an area
   difference is not a claim; 1.0 uu² is far above the boundary displacements the spike measured
   (eight of nine at ≤ 0.024 uu, worst symmetric difference 224 uu² on a 1-uu-wide sliver) — re-check
   that against the fixtures when the tests run and report if it turns out to be the wrong order of
   magnitude, rather than tuning it until the tests pass.

- [ ] **Step 1: Write the failing tests**

Add the scenarios:

```python
# --------------------------------------------------------------------- Task 17's scenarios

def semisolid_pillar_straddled_by_a_subtract() -> Scenario:
    """Trunk order: Room, Pillar, Cutter — the same shape as `pillar_in_room`, but the pillar is
    SEMISOLID. The editor runs every Add/Subtract in its LOOP 2 and only then, after the
    repartition, the semisolid brushes in LOOP 3, so no Subtract in the trunk can ever remove a
    semisolid's matter, whatever trunk order says. Measured: the pillar keeps all 6 faces and its
    full 294912 uu^2 (`uedcli/tests/test_csg_kind_facts.py`).

    The sharpest raw-vs-csg contrast in the spec: raw `carves` claims this pair whenever trunk order
    looks right; csg never does.
    """
    return _scenario([
        brush("Room", (1024, 1024, 1024), (0, 0, 0), csg="subtract"),
        brush("Pillar", (128, 128, 512), (0, 0, 0), poly_flags=PF_SEMISOLID),
        brush("Cutter", (256, 256, 256), (128, 0, 0), csg="subtract"),
    ])


def partial_and_total_carves() -> Scenario:
    """Trunk order: Shell, Room, Block, FirstCut, SecondCut, Gone, Eraser.

    * `Shell`     2048^3 Add at (0, 0, 0)
    * `Room`      1024^3 Subtract at (0, 0, 0)
    * `Block`     256^3 Add at (0, 0, 0)
    * `FirstCut`  128 x 512 x 512 Subtract at (-64, 0, 0)  — takes the block's -X half
    * `SecondCut` 256 x 512 x 512 Subtract at (0, 0, 0)    — covers FirstCut's region AND new matter
    * `Gone`      64^3 Add at (700, 0, 0)
    * `Eraser`    128^3 Subtract at (700, 0, 0)            — swallows `Gone` entirely

    Exercises three spec rules at once: `FirstCut` and `SecondCut` both carve `Block` (SecondCut's
    overlap is only partial, so it genuinely removes new matter); `Eraser` carves `Gone` even though
    nothing of `Gone` survives; and `Gone` gets no accompanying `touches`, because there is nothing
    left to be flush against.
    """
    return _scenario([
        brush("Shell", (2048, 2048, 2048), (0, 0, 0)),
        brush("Room", (1024, 1024, 1024), (0, 0, 0), csg="subtract"),
        brush("Block", (256, 256, 256), (0, 0, 0)),
        brush("FirstCut", (128, 512, 512), (-64, 0, 0), csg="subtract"),
        brush("SecondCut", (256, 512, 512), (0, 0, 0), csg="subtract"),
        brush("Gone", (64, 64, 64), (700, 0, 0)),
        brush("Eraser", (128, 128, 128), (700, 0, 0), csg="subtract"),
    ])
```

`PF_SEMISOLID` is already imported at the top of `survey_scenarios.py` (Task 7).

Append to `uedcli/tests/test_actor_survey.py`:

```python
def test_carves_fires_when_a_subtract_removes_real_add_matter():
    import pytest
    pytest.importorskip("uedcli_native")
    sc = scen.niche_carved_into_wall()
    ctx = actor_survey.build_context(sc.level, sc.index, "Niche", sc.defaults)
    assert any(f.src == "Niche" and f.dst == "Wall" and f.relation == "carves"
               for f in actor_survey.carves_facts_for(ctx))


def test_carves_is_absent_where_the_subtract_only_stopped_flush():
    """The raw-vs-csg contrast the whole two-tier design exists for: the raw order heuristic calls
    this pair `carves` (the Subtract is later in trunk order); the csg tier correctly reports
    nothing, and reports `touches` instead."""
    import pytest
    pytest.importorskip("uedcli_native")
    sc = scen.subtract_stops_flush_against_a_wall()
    ctx = actor_survey.build_context(sc.level, sc.index, "Room", sc.defaults)
    assert actor_survey.carves_facts_for(ctx) == []
    assert any(f.dst == "Wall" for f in actor_survey.touches_facts_for(ctx))
    raw = actor_survey.raw_facts_for(sc.level, sc.index, "Room", sc.defaults).facts
    assert any(f.relation == "carves" for f in raw), "raw's heuristic really does claim it"


def test_carves_never_targets_a_semisolid():
    import pytest
    pytest.importorskip("uedcli_native")
    sc = scen.semisolid_pillar_straddled_by_a_subtract()
    ctx = actor_survey.build_context(sc.level, sc.index, "Cutter", sc.defaults)
    assert not any(f.dst == "Pillar" for f in actor_survey.carves_facts_for(ctx))


def test_carves_fires_for_total_removal_with_no_accompanying_touches():
    import pytest
    pytest.importorskip("uedcli_native")
    sc = scen.partial_and_total_carves()
    ctx = actor_survey.build_context(sc.level, sc.index, "Eraser", sc.defaults)
    assert any(f.src == "Eraser" and f.dst == "Gone"
               for f in actor_survey.carves_facts_for(ctx))
    assert not any(f.dst == "Gone" for f in actor_survey.touches_facts_for(ctx))


def test_a_partially_overlapping_second_subtract_carves_and_connects():
    """The spec's coexistence case: `SecondCut` covers `FirstCut`'s already-carved region AND new
    matter, so it reports `carves Block` for the new part and `connects FirstCut` for the redundant
    part."""
    import pytest
    pytest.importorskip("uedcli_native")
    sc = scen.partial_and_total_carves()
    ctx = actor_survey.build_context(sc.level, sc.index, "SecondCut", sc.defaults)
    assert any(f.dst == "Block" for f in actor_survey.carves_facts_for(ctx))
    assert any(f.dst == "FirstCut" for f in actor_survey.connects_facts_for(ctx))


def test_carves_shows_the_same_fact_when_the_carved_actor_is_surveyed():
    """Fixed-direction: the Subtract leads whichever side you ask about. The spec's own worked
    example surveys `Brush117`, the carved Add, and still prints the Subtract first."""
    import pytest
    pytest.importorskip("uedcli_native")
    sc = scen.niche_carved_into_wall()
    ctx = actor_survey.build_context(sc.level, sc.index, "Wall", sc.defaults)
    assert any(f.src == "Niche" and f.dst == "Wall"
               for f in actor_survey.carves_facts_for(ctx))
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `bin/test -k "carves_ or a_partially_overlapping_second" -v`
Expected: FAIL — `carves_facts_for` does not exist.

- [ ] **Step 3: Implement it**

```python
# Below this many square world units, a surviving-area difference is not a claim. Well above the
# boundary displacements the bounded-neighborhood truncation can introduce (eight of the spike's
# nine measured area differences moved a boundary by <= 0.024 uu; the worst symmetric difference was
# 224 uu^2, and that one was a known native `first_add_seed` defect on a 1-uu sliver, not truncation
# noise -- spike.md §4).
CARVE_AREA_EPS = 1.0

# A Subtract can only have removed matter from a kind that HAS matter to remove and is applied
# BEFORE it. Measured (spike.md §1, regression `test_csg_kind_facts.py`):
#   add       carved, with real area loss                                  -> valid target
#   nonsolid  contributes no solid, but its FACES are real world surfaces and a later Subtract
#             removes them with exactly the same area loss as an Add's     -> valid target
#   semisolid NEVER: the editor applies every Add/Subtract in LOOP 2 and only then, after the
#             repartition, the semisolids in LOOP 3, so trunk order cannot make one carveable
#   subtract/intersect/deintersect/mover  contribute nothing a Subtract could take
_CARVE_TARGET_KINDS = frozenset({"add", "nonsolid"})


def poly_area(verts) -> float:
    """A planar polygon's area, `0.5 * |newell|` -- the same relation `query.py`'s own `poly list`
    area uses (`texframe.newell`'s docstring)."""
    from .texframe import newell
    n = newell([tuple(float(c) for c in v) for v in verts])
    return 0.5 * (n[0] ** 2 + n[1] ** 2 + n[2] ** 2) ** 0.5


def authored_face_area(actor) -> float:
    """The total world-space area of ACTOR's own authored brush faces, before any CSG."""
    from . import polyalign
    if actor.brush is None:
        return 0.0
    return sum(poly_area(polyalign._world_verts(actor, p)) for p in actor.brush.polys
               if len(p.vertices) >= 3)


def surviving_face_area(probe, owner: str) -> float:
    """The total area of `owner`'s faces that survive in `probe`'s resolved world.

    Area, never face COUNT and never poly identity: a different tree shape splits the same surface
    into different polygons, so counts and indices are not comparable across two solves (spike.md §4
    residual 1). Summing area is."""
    return sum(poly_area(s.world_verts) for s in probe.world_surfaces
               if s.actor is not None and s.actor.name == owner)


def removed_by(ctx: SurveyContext, subtract, victim) -> bool:
    """Did `subtract` genuinely remove part of `victim`'s originally-contributed matter?

    Answered by a COUNTERFACTUAL SOLVE: re-solve the same neighborhood with `subtract` dropped and
    compare `victim`'s surviving face area. More survives without it <=> it took some. This is the
    same uncut-vs-cut comparison `kind_semantics.py` makes (`_solve([room, pillar])` against
    `_solve([room, pillar, cutter])`, then the pillar's own area on each), and it is what
    distinguishes the spec's two hard cases: a second Subtract carving EXACTLY an already-carved
    region changes nothing and reports nothing, while one that only PARTIALLY overlaps really does
    remove new matter and reports it.

    Never drops the level's FIRST world-CSG brush: that would fire `bsp_brush_csg`'s leading-Add
    world-shell shortcut on a different brush and change the whole tree (spike.md §4 residual 4).
    When `subtract` IS that brush, this returns False rather than solving a world the bounded-cost
    argument does not cover.

    The guard compares against `ctx.seed`, NOT `ctx.neighbors[0].name`. `neighbors` is in trunk
    order, so index 0 can be a Mover or the builder brush -- neither contributes to world CSG, so
    neither is the brush the solver seeds from, and the real seed would then sit at a later index
    and be droppable. `ctx.seed` is `seed_brush_name`'s answer: the first brush that actually
    contributes."""
    from .preview_native import solve_world_probe
    if not ctx.neighbors or subtract.name == ctx.seed:
        return False
    without = [a for a in ctx.neighbors if a.name != subtract.name]
    counterfactual = solve_world_probe(without, ctx.class_index)
    gained = surviving_face_area(counterfactual, victim.name) - \
        surviving_face_area(ctx.probe, victim.name)
    return gained > CARVE_AREA_EPS


def carves_facts_for(ctx: SurveyContext) -> list:
    """`carves`: a Subtract removed part of another actor's originally-contributed matter.

    The agent leads, whichever side is surveyed -- so both directions are computed. "Part" means at
    least part: an Add entirely consumed by a later Subtract still reports `carves`, and that is the
    most valuable case of this fact, not an excluded one. Whatever of the victim still survives
    elsewhere reports `touches` as normal; if nothing survives, no `touches` accompanies the
    `carves`, which is correct -- there is nothing left to be flush against."""
    facts: list = []

    if ctx.surveyed.brush is not None and query.csg_is_subtract(ctx.surveyed):
        for other in ctx.near:
            if kind_of(other, ctx.class_index) not in _CARVE_TARGET_KINDS:
                continue
            if removed_by(ctx, ctx.surveyed, other):
                facts.append(CsgFact(src=ctx.name, dst=other.name, relation="carves"))
    elif ctx.surveyed.brush is not None and \
            kind_of(ctx.surveyed, ctx.class_index) in _CARVE_TARGET_KINDS:
        for other in ctx.near:
            if not query.csg_is_subtract(other):
                continue
            if removed_by(ctx, other, ctx.surveyed):
                facts.append(CsgFact(src=other.name, dst=ctx.name, relation="carves"))

    return sorted(facts, key=lambda f: (f.src, f.dst))
```

- [ ] **Step 4: Run the tests, iterate to green**

Run: `bin/test -k "carves_ or a_partially_overlapping_second" -v`
Expected: PASS

If `CARVE_AREA_EPS` turns out to be the wrong order of magnitude for these fixtures (a real carve
producing less than 1 uu² of area change, or truncation noise producing more), report the measured
numbers and propose a value — do not silently tune the constant until the tests go green, which would
make the threshold a fit to the fixtures rather than to the measurement behind it.

- [ ] **Step 5: Run the whole suite, then commit**

Run: `bin/test`

```bash
git add uedcli/actor_survey.py uedcli/tests/survey_scenarios.py uedcli/tests/test_actor_survey.py
git commit -m "actor survey: csg-tier carves"
```

---

## Part E — wiring, error paths, regressions, docs

### Task 18: combine the tiers, the csg line format, and every error path

**Files:**
- Modify: `uedcli/actor_survey.py` (`csg_facts_for`, `survey`, `format_csg_line`,
  `intersect_deintersect_warning`, `SurveyResult`)
- Modify: `uedcli/cli/commands/actor/survey.py` (use the orchestrator; map every failure to exit 2)
- Modify: `uedcli/tests/survey_scenarios.py` (one builder)
- Test: `uedcli/tests/test_actor_survey.py`, `uedcli/tests/test_cli_actor_survey.py`

**Interfaces:**
- Consumes: every `*_facts_for` from Tasks 8 and 12-17; `resources.class_index`/`resolve_project`/
  `schema_resolver_for`; `classdefaults.ClassDefaults`; `preview_native.NativePreviewError`;
  `uprops.SchemaError`.
- Produces:

```python
@dataclass(frozen=True)
class SurveyResult:
    raw: list          # list[RawFact]
    csg: list          # list[CsgFact]
    nodes: dict        # name -> actorgraph.NodeTag, covering every name either list mentions
    skipped: list      # (name, reason) for a degenerate NEIGHBOUR brush
    warning: str | None

def csg_facts_for(ctx) -> list[CsgFact]
def survey(level, class_index, name: str, defaults) -> SurveyResult
def format_csg_line(fact: CsgFact, nodes: dict) -> str
def intersect_deintersect_warning(actor, class_index) -> str | None
```

- [ ] **Step 1: Write the failing tests**

Add the scenario:

```python
# --------------------------------------------------------------------- Task 18's scenarios

def level_with_a_placed_intersect() -> Scenario:
    """Trunk order: Room, Inter. `Inter` is a placed `CSG_Intersect` brush — it contributes nothing
    whatever to the resolved world (`bspBrushCSG` dispatches it to a tail that rewrites the BRUSH's
    own model and never touches the world), so its csg tier is empty and its raw tier treats it as
    Add-like, which the resolved world does not."""
    return _scenario([
        brush("Room", (1024, 1024, 1024), (0, 0, 0), csg="subtract"),
        oper_brush("Inter", (128, 128, 128), (0, 0, 0), "CSG_Intersect"),
    ])


def level_with_a_degenerate_brush() -> Scenario:
    """Trunk order: Room, BadBrush. `BadBrush` carries a PolyList that bounds no valid solid, so
    `decompose_convex` raises `DegenerateBrushError` naming it."""
    from uedcli.model import Brush, Polygon
    flat = Brush(model_name="Model_BadBrush", polys=[
        Polygon(vertices=[(Decimal(0), Decimal(0), Decimal(0)),
                          (Decimal(64), Decimal(0), Decimal(0)),
                          (Decimal(64), Decimal(64), Decimal(0))]),
    ])
    bad = make_brush_actor("BadBrush", flat, location=_dec((0, 0, 0)))
    return _scenario([brush("Room", (1024, 1024, 1024), (0, 0, 0), csg="subtract"), bad])
```

Confirm the degenerate fixture really raises before relying on it:
`python -c "..."` is awkward here, so assert it directly in the test below rather than assuming.

Append to `uedcli/tests/test_actor_survey.py`:

```python
def test_survey_returns_both_tiers_and_one_node_tag_per_named_actor():
    import pytest
    pytest.importorskip("uedcli_native")
    sc = scen.niche_carved_into_wall()
    got = actor_survey.survey(sc.level, sc.index, "Wall", sc.defaults)
    assert got.raw and got.csg
    named = {f.src for f in got.raw} | {f.dst for f in got.raw} \
        | {f.src for f in got.csg} | {f.dst for f in got.csg}
    assert named <= set(got.nodes)


def test_csg_line_carries_a_depth_on_crosses_and_nothing_on_the_others():
    sc = scen.niche_carved_into_wall()
    nodes = actor_survey.raw_facts_for(sc.level, sc.index, "Wall", sc.defaults).nodes
    crossing = actor_survey.CsgFact(src="Wall", dst="Niche", relation="crosses", depth_uu=8.25)
    touching = actor_survey.CsgFact(src="Wall", dst="Niche", relation="touches")
    assert actor_survey.format_csg_line(crossing, nodes) == (
        "csg Wall [Engine.Brush Add] --crosses(8.25uu)--> Niche [Engine.Brush Subtract]")
    assert actor_survey.format_csg_line(touching, nodes) == (
        "csg Wall [Engine.Brush Add] --touches--> Niche [Engine.Brush Subtract]")


def test_no_csg_line_ever_carries_an_idx():
    """Cut from this tier entirely (spec): a `Name:idx` token is a promise of a pipeable selector,
    and the attribution mechanism for one was found factually wrong against the native code twice.
    Poly identity is also not reproducible under the bounded solve (spike.md §4 residual 1)."""
    import pytest
    pytest.importorskip("uedcli_native")
    sc = scen.shelf_pokes_through_a_niche_wall()
    got = actor_survey.survey(sc.level, sc.index, "Additive4", sc.defaults)
    for fact in got.csg:
        line = actor_survey.format_csg_line(fact, got.nodes)
        assert ":" not in line.split("--")[0]


def test_survey_warns_only_when_the_surveyed_actor_is_an_intersect():
    import pytest
    pytest.importorskip("uedcli_native")
    sc = scen.level_with_a_placed_intersect()
    assert "Inter" in actor_survey.survey(sc.level, sc.index, "Inter", sc.defaults).warning
    assert actor_survey.survey(sc.level, sc.index, "Room", sc.defaults).warning is None


def test_survey_propagates_a_degenerate_surveyed_brush():
    """`level graph` skips a bad brush and carries on over the rest of the level. A single-actor
    report has nothing left to say, so this propagates to the CLI's exit 2 instead."""
    import pytest
    from uedcli import actorgraph
    sc = scen.level_with_a_degenerate_brush()
    with pytest.raises(actorgraph.DegenerateBrushError):
        actor_survey.survey(sc.level, sc.index, "BadBrush", sc.defaults)
```

Append to `uedcli/tests/test_cli_actor_survey.py`:

```python
def test_survey_prints_raw_block_then_csg_block_then_a_two_number_summary(
        tmp_path, monkeypatch, capsys):
    pytest.importorskip("uedcli_native")
    proj = _project(tmp_path, monkeypatch, scen.niche_carved_into_wall())
    assert dispatch.dispatch(_ns(proj, "Wall")) == 0
    out = capsys.readouterr()
    lines = out.out.splitlines()
    raw = [i for i, ln in enumerate(lines) if ln.startswith("raw ")]
    csg = [i for i, ln in enumerate(lines) if ln.startswith("csg ")]
    assert raw and csg
    assert min(csg) > max(raw)
    assert f"{len(raw)} raw fact(s), {len(csg)} resolved CSG fact(s) for Wall" in out.err


def test_survey_every_line_starts_with_its_tier_token(tmp_path, monkeypatch, capsys):
    """A tier token as the FIRST WORD, never a section header — so the guarantee survives grep,
    truncation, or one line quoted mid-context into a later prompt (spec, Output shape)."""
    pytest.importorskip("uedcli_native")
    proj = _project(tmp_path, monkeypatch, scen.niche_carved_into_wall())
    assert dispatch.dispatch(_ns(proj, "Wall")) == 0
    for line in capsys.readouterr().out.splitlines():
        assert line == "" or line.split()[0] in ("raw", "csg")


def test_survey_degenerate_surveyed_brush_exits_2_naming_it(tmp_path, monkeypatch, capsys):
    proj = _project(tmp_path, monkeypatch, scen.level_with_a_degenerate_brush())
    assert dispatch.dispatch(_ns(proj, "BadBrush")) == 2
    assert "BadBrush" in capsys.readouterr().err


def test_survey_warns_on_a_placed_intersect_and_still_exits_0(tmp_path, monkeypatch, capsys):
    pytest.importorskip("uedcli_native")
    proj = _project(tmp_path, monkeypatch, scen.level_with_a_placed_intersect())
    assert dispatch.dispatch(_ns(proj, "Inter")) == 0
    err = capsys.readouterr().err
    assert "Inter" in err and "contributes nothing" in err


def test_survey_unresolvable_class_exits_2_not_a_traceback(tmp_path, monkeypatch, capsys):
    """A `uprops.SchemaError` from the collision gate must never reach the user — and must be THIS
    handler's message, which names the surveyed actor, not `dispatch.py`'s generic
    `except SchemaError` backstop, which does not.

    The raise comes from `defaults.for_class(...)` inside `survey`, so the test substitutes a
    class-defaults object whose `for_class` raises — `survey_scenarios.failing_defaults()`, the
    same helper Task 11's unit test uses. Patching `resources.schema_resolver_for` would prove
    nothing: it returns a resolver over an empty search path and cannot raise `SchemaError`."""
    pytest.importorskip("uedcli_native")
    from uedcli.cli.commands.actor import survey as survey_cmd
    proj = _project(tmp_path, monkeypatch, scen.room_with_a_flush_mounted_prop())
    monkeypatch.setattr(survey_cmd, "ClassDefaults", lambda resolver: scen.failing_defaults())
    assert dispatch.dispatch(_ns(proj, "Keypad")) == 2
    err = capsys.readouterr().err          # read ONCE: readouterr() drains the buffer
    assert "Keypad" in err
    assert "schema" in err
```

`capsys.readouterr()` is read into a local on purpose. Calling it twice in one assertion — the shape
this test had while it was being written — empties the buffer on the first call, so the second half
of an `or` can never be true and the assertion silently tests only its first half.

Before writing that last test's monkeypatch, check that `ClassDefaults` is still the name this
handler binds and calls inside its `try` (`grep -n "ClassDefaults"
uedcli/cli/commands/actor/survey.py`); if it builds its defaults object differently, patch whatever
it actually calls there. The patched seam has to be one the handler reaches INSIDE the `try` AND
one that makes `defaults.for_class(...)` raise — a seam that runs before the `try` would exercise
`dispatch.py`'s generic handler, and one that cannot raise `SchemaError` would exercise nothing;
either way the test would pass while proving nothing.

- [ ] **Step 2: Run the tests to verify they fail**

Run: `bin/test -k "survey_returns_both_tiers or csg_line_carries or no_csg_line_ever or survey_warns or survey_propagates or survey_prints_raw_block or survey_every_line or survey_degenerate or survey_unresolvable" -v`
Expected: FAIL.

- [ ] **Step 3: Add the orchestrator and the formatter**

```python
@dataclass(frozen=True)
class SurveyResult:
    raw: list
    csg: list
    nodes: dict
    skipped: list
    warning: str | None


def csg_facts_for(ctx: SurveyContext) -> list:
    """Every csg-tier fact about the surveyed actor, in a fixed relation order so the output is
    stable between runs."""
    out: list = []
    for fn in (crosses_facts_for, touches_facts_for, connects_facts_for,
               contains_facts_for, carves_facts_for):
        out.extend(fn(ctx))
    return out


def survey(level, class_index, name: str, defaults) -> SurveyResult:
    """Both tiers for one actor, over ONE shared decomposition cache and ONE native solve.

    Raises `ActorNotFoundError` (unknown name), `actorgraph.DegenerateBrushError` (the SURVEYED
    actor's own brush), `preview_native.NativePreviewError` (no native extension, or a failed
    solve) and `uprops.SchemaError` (an unresolvable class in the collision gate). The CLI maps
    every one of them to exit 2 -- none may reach the user as a traceback."""
    if name not in level.actors:
        raise ActorNotFoundError(name)
    cells: dict = {}
    raw = raw_facts_for(level, class_index, name, defaults, cells=cells)
    ctx = build_context(level, class_index, name, defaults, cells=cells)
    csg = csg_facts_for(ctx)
    nodes = dict(raw.nodes)
    for fact in csg:
        for side in (fact.src, fact.dst):
            if side not in nodes and side in level.actors:
                nodes[side] = actorgraph._node_tag(level.actors[side], class_index)
    return SurveyResult(raw=raw.facts, csg=csg, nodes=nodes, skipped=raw.skipped,
                         warning=intersect_deintersect_warning(level.actors[name], class_index))


def format_csg_line(fact: CsgFact, nodes: dict) -> str:
    """One `csg `-prefixed line. Every `*_facts_for` already assigned `src`/`dst` in the spec's
    final direction, so this is pure formatting. No `:idx` at this tier, ever -- `crosses` alone
    carries an annotation, the measured penetration depth."""
    rel = fact.relation
    if fact.relation == "crosses" and fact.depth_uu is not None:
        rel = f"crosses({fact.depth_uu:.3g}uu)"
    return (f"csg {fact.src} {actorgraph._node_bracket(nodes[fact.src])} --{rel}--> "
            f"{fact.dst} {actorgraph._node_bracket(nodes[fact.dst])}")


def intersect_deintersect_warning(actor, class_index) -> str | None:
    """One stderr line when the SURVEYED actor itself is a placed Intersect/Deintersect brush.

    No other actor's survey warns. Such a brush contributes nothing to the resolved world at all --
    `bspBrushCSG` dispatches it to a tail that rewrites the BRUSH's own model and never touches the
    world (measured: the world is node-identical with and without one, spike.md §2) -- so it cannot
    change anyone else's facts, and a neighborhood scan for one would be pure noise. The spec's
    earlier reason for the warning ("can affect resolution outside a single actor's immediate
    neighborhood") is false; the real reason is narrower and local: its own csg tier is correctly
    empty, and its raw tier treats it as Add-like, which the resolved world does not.

    A stderr warning beside a complete answer, which `CLAUDE.md`'s no-silent-half-answers rule
    would normally refuse -- allowed here because the answer is not partial, and recorded because
    the owner ruled 'warn on Intersect/Deintersect'."""
    if actor.brush is None:
        return None
    kind = kind_of(actor, class_index)
    if kind not in ("intersect", "deintersect"):
        return None
    oper = "CSG_Intersect" if kind == "intersect" else "CSG_Deintersect"
    return (f"actor survey: {actor.name} is a placed {oper} brush — it contributes nothing to the "
            f"resolved world (the editor treats it as a builder-brush operation on its own model), "
            f"so its csg tier carries no fact it sources, and its raw tier treats it as Add-like, "
            f"which the resolved world does not")


def format_lines(result: SurveyResult) -> list:
    """Every stdout line of a survey, in order: the raw block, a blank separator when both tiers
    have something, then the csg block. A blank line is the ONLY line that does not start with a
    tier token."""
    lines = [format_raw_line(f, result.nodes) for f in result.raw]
    csg_lines = [format_csg_line(f, result.nodes) for f in result.csg]
    if lines and csg_lines:
        lines.append("")
    return lines + csg_lines
```

- [ ] **Step 4: Rewrite the CLI handler**

`uedcli/cli/commands/actor/survey.py` becomes:

```python
"""`actor survey NAME` — every raw and CSG-resolved spatial fact about one actor.

Resolves its own source, class index and class defaults the way every actor feature module does
(`preview.py` is the closest analog: it also drives a native CSG solve). Every failure mode is
mapped to exit 2 with a message naming the offending value — never a traceback (`CLAUDE.md`).
"""
from __future__ import annotations

import sys

from ... import level_sources, resources
from ...errors import CommandError
from .... import actor_survey, actorgraph, uprops
from ....classdefaults import ClassDefaults
from ....preview_native import NativePreviewError


def run(args) -> int:
    """`actor survey` entry. Dispatch routes every `actor survey` here."""
    project = resources.resolve_project(args)
    src = level_sources.resolve_level_source(args)
    index = resources.mover_index(args, "actor survey", project)
    level = src.load()
    try:
        # The `SchemaError` caught below is raised by `defaults.for_class(...)` inside `survey`, not
        # by `schema_resolver_for` — that one returns a resolver over an empty search path rather
        # than raising (`packages.schema_search_dirs`). Catching it here instead of letting
        # `dispatch.py`'s generic `except SchemaError` (dispatch.py:69) take it is what puts the
        # surveyed actor's name in the message.
        defaults = ClassDefaults(resources.schema_resolver_for(project))
        result = actor_survey.survey(level, index, args.name, defaults)
    except actor_survey.ActorNotFoundError as e:
        print(str(e), file=sys.stderr)
        return 2
    except actorgraph.DegenerateBrushError as e:
        print(f"actor survey: {e}", file=sys.stderr)
        return 2
    except uprops.SchemaError as e:
        raise CommandError(
            f"actor survey: cannot resolve a class schema while surveying {args.name!r} — the "
            f"collision gate needs it ({e}). Qualify the class as Package.Class and put its "
            f"package on the project's search paths") from None
    except NativePreviewError as e:
        raise CommandError(f"actor survey: {e}") from None
    for _bad_name, reason in result.skipped:
        print(f"actor survey: skipping {reason}", file=sys.stderr)
    for line in actor_survey.format_lines(result):
        print(line)
    if result.warning:
        print(result.warning, file=sys.stderr)
    print(f"actor survey: {len(result.raw)} raw fact(s), {len(result.csg)} resolved CSG fact(s) "
          f"for {args.name}", file=sys.stderr)
    return 0
```

Two things to verify against the real code before committing, rather than trusting this sketch:
`resources.resolve_project(args)`'s exact name (it is used that way in
`uedcli/cli/commands/level.py:556`), and that `dispatch` turns a raised `CommandError` into exit 2
(it does for every other feature module; confirm with
`grep -n "CommandError" uedcli/cli/dispatch.py`). `_bad_name` goes unused deliberately —
`DegenerateBrushError`'s own message already starts with the actor's name, and repeating it makes
the line stutter (`uedcli/cli/commands/level.py:810-812`'s own comment).

- [ ] **Step 5: Run the tests, iterate to green**

Run: `bin/test -k "test_actor_survey or test_cli_actor_survey" -v`
Expected: PASS

- [ ] **Step 6: Run the whole suite, then commit**

Run: `bin/test`

```bash
git add uedcli/actor_survey.py uedcli/cli/commands/actor/survey.py
git add uedcli/tests/survey_scenarios.py uedcli/tests/test_actor_survey.py
git add uedcli/tests/test_cli_actor_survey.py
git commit -m "actor survey: combine both tiers, csg line format, error paths"
```

---

### Task 19: the bounded-neighborhood truncation regression

The spec's testing notes ask for this by name: *"the same actor surveyed over the neighborhood and
over the whole level must produce the same fact set"*, built on a small synthetic level rather than
the gitignored corpus. This is the one test that watches the whole bounded-cost argument, including
the residuals Task 10 recorded honestly rather than claimed away.

**Files:**
- Modify: `uedcli/tests/survey_scenarios.py` (one builder)
- Test: `uedcli/tests/test_actor_survey_truncation.py` (new)

**Interfaces:**
- Consumes: `actor_survey.build_context`, `csg_facts_for`, `csg_faces`, `region_of`,
  `poly_area` (Task 17's); `preview_native.solve_world_probe`; `dataclasses.replace`.
- Produces: nothing importable — this task adds only tests. No production flag is added for
  "solve the whole level": the test constructs that context itself with `dataclasses.replace`, and a
  user-facing flag nothing asks for would be speculative surface (`CLAUDE.md`, YAGNI).

- [ ] **Step 1: Write the failing test**

Add the scenario:

```python
# --------------------------------------------------------------------- Task 19's scenario

def truncation_probe_level() -> Scenario:
    """A level big enough that the neighborhood is a real subset, small enough to solve whole.

    Trunk order: Shell, then eight 256^3 Add pillars on a 1024uu grid at z = 0, then `Room`
    (a 512^3 Subtract at (0, 0, 0)) and `Probe` (a 128^3 Add at (200, 0, 0), flush against nothing,
    poking into Room's +X wall). Only Shell, Room, Probe and the two nearest pillars meet `Probe`'s
    region; the other six are identity on it.
    """
    actors = [brush("Shell", (4096, 4096, 1024), (0, 0, 0))]
    for i in range(8):
        actors.append(brush(f"Pillar{i}", (256, 256, 256), (1024 * (i - 4) + 512, 1024, 0)))
    actors.append(brush("Room", (512, 512, 512), (0, 0, 0), csg="subtract"))
    actors.append(brush("Probe", (128, 128, 128), (200, 0, 0)))
    return _scenario(actors)
```

New file `uedcli/tests/test_actor_survey_truncation.py`:

```python
"""The bounded-neighborhood truncation regression.

The whole csg tier rests on one claim: a CSG operation changes the world's solid/void labelling only
inside its own brush volume, so solving over `{brushes whose AABB meets the surveyed actor's region}`
reproduces, inside that region, exactly what the full-level solve produces
(`dev/docs/spikes/2026-09-23-actor-survey-csg-kind-and-cost/spike.md` §4). The spike measured that
over 140 surveys of real levels; this is the committed version, on a synthetic level small enough to
solve whole.

Two checks, matching what the spike itself compared: the FACT SET must be identical, and the face
signature inside the region must agree by owner and area (never by poly index or face count — a
different tree shape splits the same surface differently, which is not a divergence).
"""
from __future__ import annotations

import dataclasses

import pytest

from uedcli import actor_survey
from uedcli.preview_native import solve_world_probe
from uedcli.tests import survey_scenarios as scen

pytest.importorskip("uedcli_native")


def _whole_level_context(sc, name):
    """The same `SurveyContext`, but solved over EVERY brush in the level instead of the bounded
    neighborhood. `near`/`points` stay as they are — the truncation claim is about the SOLVE, not
    about which actors a fact may name. `seed` carries over unchanged, correctly: it names the
    LEVEL's first world-CSG brush, which is the same brush in both solves."""
    ctx = actor_survey.build_context(sc.level, sc.index, name, sc.defaults)
    everything = [sc.level.actors[n] for n in sc.level.order
                  if sc.level.actors[n].brush is not None]
    probe = solve_world_probe(everything, sc.index)
    return dataclasses.replace(ctx, neighbors=everything, probe=probe,
                               faces=actor_survey.csg_faces(probe, ctx.region))


def _key(facts):
    return sorted((f.src, f.dst, f.relation) for f in facts)


def _clip_to_halfspace(poly, axis, limit, keep_below):
    """Clip a 3-D convex polygon by one axis-aligned half-space. Ported verbatim from
    `dev/docs/spikes/2026-09-23-actor-survey-csg-kind-and-cost/harness/bounded_cost.py`."""
    out = []
    for i in range(len(poly)):
        cur, prev = poly[i], poly[i - 1]
        cur_in = (cur[axis] <= limit) if keep_below else (cur[axis] >= limit)
        prev_in = (prev[axis] <= limit) if keep_below else (prev[axis] >= limit)
        if cur_in != prev_in:
            t = (limit - prev[axis]) / (cur[axis] - prev[axis])
            out.append(tuple(prev[k] + t * (cur[k] - prev[k]) for k in range(3)))
        if cur_in:
            out.append(cur)
    return out


def _clip_to_box(poly, lo, hi):
    for axis in range(3):
        poly = _clip_to_halfspace(poly, axis, hi[axis], True)
        if not poly:
            return []
        poly = _clip_to_halfspace(poly, axis, lo[axis], False)
        if not poly:
            return []
    return poly


def _signature(ctx):
    """Total CLIPPED surface area per owner inside the survey region.

    Summed over `ctx.probe.world_surfaces` — EVERY surviving fragment — and deliberately not over
    `ctx.faces`, which holds one arbitrary representative fragment per (owner, plane). Two solves
    that split the same surface differently pick different representatives with different areas, so
    summing `ctx.faces` would report a different BSP split as a divergence, which is precisely what
    this comparison exists NOT to do. Clipping every fragment to the region and accumulating per
    owner is `bounded_cost.py`'s own `face_signature` technique, minus its poly-index half (the csg
    tier names no poly index).
    """
    lo, hi = (tuple(float(c) for c in ctx.region[0]), tuple(float(c) for c in ctx.region[1]))
    out: dict = {}
    for surf in ctx.probe.world_surfaces:
        if surf.actor is None:
            continue
        clipped = _clip_to_box([tuple(float(c) for c in v) for v in surf.world_verts], lo, hi)
        if len(clipped) < 3:
            continue
        area = actor_survey.poly_area(clipped)
        if area <= 1e-9:
            continue
        out[surf.actor.name] = out.get(surf.actor.name, 0.0) + area
    return out


@pytest.mark.parametrize("name", ["Probe", "Room", "Pillar4"])
def test_the_bounded_solve_and_the_whole_level_solve_agree_on_the_fact_set(name):
    sc = scen.truncation_probe_level()
    bounded = actor_survey.build_context(sc.level, sc.index, name, sc.defaults)
    whole = _whole_level_context(sc, name)
    assert len(whole.neighbors) > len(bounded.neighbors), "the neighborhood is a real subset"
    assert _key(actor_survey.csg_facts_for(bounded)) == \
        _key(actor_survey.csg_facts_for(whole))


def test_the_face_signature_inside_the_region_agrees_by_owner_and_area():
    """Compared by (owner, total clipped area), never by polygon identity or face count — the
    spike's own method, and the reason it works: a different BSP split of the same surface is not a
    divergence (spike.md §4, 'The empirical check'). `_signature` sums EVERY surviving fragment
    clipped to the region, not `ctx.faces`'s one representative per plane, which is what makes that
    true."""
    sc = scen.truncation_probe_level()
    bounded = actor_survey.build_context(sc.level, sc.index, "Probe", sc.defaults)
    whole = _whole_level_context(sc, "Probe")
    a, b = _signature(bounded), _signature(whole)
    assert set(a) == set(b)
    for owner in a:
        assert a[owner] == pytest.approx(b[owner], rel=1e-4)


def test_dropping_the_first_world_csg_brush_really_does_change_the_answer():
    """The first-brush clause is load-bearing, not cosmetic: `bsp_brush_csg` SEEDS a leading
    `CSG_Add` as the world shell rather than classifying it, so truncating it away fires that
    shortcut on a different brush. This asserts the mechanism is still live — if it ever stops
    mattering, the clause can be revisited, and this test going green-by-accident would hide that.
    """
    sc = scen.truncation_probe_level()
    ctx = actor_survey.build_context(sc.level, sc.index, "Probe", sc.defaults)
    assert ctx.seed == "Shell"            # the first CONTRIBUTING brush, not trunk index 0
    without_shell = [a for a in ctx.neighbors if a.name != "Shell"]
    probe = solve_world_probe(without_shell, sc.index)
    seeded = {f.owner for f in actor_survey.csg_faces(ctx.probe, ctx.region)}
    unseeded = {f.owner for f in actor_survey.csg_faces(probe, ctx.region)}
    assert seeded != unseeded
```

The last test asserts that removing the seed brush genuinely changes the resolved faces. If it turns
out NOT to on this fixture, do not delete the test and do not weaken it — report that the fixture is
not exercising the trap, and make the shell a small solid at the origin in a much larger map (the
shape `paris-chateau` has, where the spike actually observed the effect).

- [ ] **Step 2: Run the tests to verify they fail**

Run: `bin/test -k test_actor_survey_truncation -v`
Expected: collection FAILS until `truncation_probe_level` exists; then the tests run for real.

- [ ] **Step 3: Make them pass**

There is no production code to write here — if a fact set differs between the two solves, that is a
REAL finding about the bounded-cost rule on this geometry, not a test to adjust. Diagnose it, report
the concrete divergence (which relation, which pair, which owner's area moved and by how much), and
get a ruling before changing either the rule or the test. Widening a tolerance to make this green
would destroy the only thing the test is for.

- [ ] **Step 4: Run the whole suite, then commit**

Run: `bin/test`

```bash
git add uedcli/tests/survey_scenarios.py uedcli/tests/test_actor_survey_truncation.py
git commit -m "actor survey: bounded-neighborhood truncation regression"
```

---

### Task 20: user-facing documentation

**Files:**
- Create: `docs/reference/actor/relation.md` (moved content from `docs/reference/brush/relation.md`,
  plus the non-brush broadening from Tasks 4-6)
- Create: `docs/reference/actor/survey.md`
- Delete: `docs/reference/brush/relation.md`
- Modify: `docs/reference/actor/README.md` (two new table rows)
- Modify: `docs/reference/brush/README.md` (drop the `relation` row, point at the new page)
- Modify: `docs/reference/brush/poly.md`, `docs/reference/level/graph.md`,
  `docs/leveldesign/general/recipes/shapes/mitered-corner.md` (retarget the links Task 3 deliberately
  left pointing at the old path)

**Interfaces:** none — documentation only.

- [ ] **Step 1: Move the relation page**

```bash
git mv docs/reference/brush/relation.md docs/reference/actor/relation.md
```

Read it in full, then update it: the verb is `actor relation`, the subcommand is `compare` not
`measure`, and each of the three subcommands gained a non-brush side (Tasks 4-6). Document what a
user can observe:

- `find`: a non-brush actor named explicitly (or piped in via `-`) is a real candidate; it prints as
  a bare name with no `:idx`; `--json` gives it `"poly": null`; the default (no names) candidate set
  is still brush-only; an explicit `--footprint`/`--plane` excludes point candidates.
- `compare`: a bare actor name as TARGET reports `distance`, `point_footprint`
  (`inside`/`on_boundary`/`outside`) and `centroid_u`/`centroid_v` — and no `footprint_2d`,
  `edge_u` or `edge_v`, because a point has neither area nor edges.
- `set`: a bare actor name as TARGET moves its `Location`; `--gap`, `--centroid-*` and `--edge-*` all
  work against it and all mean different things.

`--relative-to`/`REF` stay face selectors everywhere, because a face is what you align against.

- [ ] **Step 2: Write `docs/reference/actor/survey.md`**

For a reader with no familiarity with the implementation (`dev/docs/rules/documentation.md`): what
the verb does, the two-tier output, one line per relation word and what it means, and the worked
example. Cover:

- the line grammar, and that the tier token is the first word of every line;
- `raw` = cheap geometry over the actors' authored shapes, before CSG — always computable, sometimes
  wrong in a way the `csg` tier corrects;
- `csg` = the authoritative answer from a real CSG solve;
- each relation: `touches`, `contains`, `carves` (both tiers), `connects`, `crosses` (csg only);
- that a `crosses` line carries a measured depth, that a raw `touches` line can carry a `:idx` face
  selector you can paste into `actor relation compare`, and that no `csg` line ever does;
- that `level graph` currently prints `carved_by` with the other side leading for the same
  underlying pair, and that this is a known, temporary difference in wording, not a bug.

This page documents how a uedcli tool behaves, which `CLAUDE.md` says is fine to write without the
owner's approval. Do NOT add level-design craft guidance, engine claims, or human-scale numbers —
that needs the owner's yes, and this page does not need any. `docs/` must never reference the
developer tree, so cite no spike, board item or `dev/docs/` path anywhere in it.

- [ ] **Step 3: Update the two README tables**

In `docs/reference/actor/README.md`, add two query rows (matching the file's existing column
alignment, `dev/docs/rules/documentation.md`):

```markdown
| [`actor relation find/compare/set`](relation.md) | query/mutate | exact geometric facts between a reference face and other actors, filtered search, and move-to-relationship |
| [`actor survey`](survey.md) | query | every raw and CSG-resolved spatial fact about one actor |
```

In `docs/reference/brush/README.md`, delete the `brush relation` row (line 14) and, if the page has a
"see also" area, point at `../actor/relation.md`.

- [ ] **Step 4: Retarget the remaining links**

Task 3 changed the command TEXT in `docs/reference/brush/poly.md`, `docs/reference/level/graph.md`
and `docs/leveldesign/general/recipes/shapes/mitered-corner.md` but left their markdown LINKS
pointing at `docs/reference/brush/relation.md`, because the destination page did not exist yet. Now
it does:

```bash
grep -rn "brush/relation.md\|relation.md" docs/
```

Retarget each hit to the new path, relative to the file it sits in.

- [ ] **Step 5: Run the link tests**

Run: `bin/test -k "doc_links or docs_command"`
Expected: green. `test_doc_links.py::test_markdown_links_resolve` and
`test_docs_command.py::test_the_real_docs_tree_has_no_dead_links` both walk the shipped tree, and a
page move is exactly what they exist to catch. **If either goes red, it is this task's fault** —
there is no pre-existing failure to hide behind, and this plan makes no claim that there is.

- [ ] **Step 6: Run the whole suite, then commit**

Run: `bin/test`

```bash
git add docs/reference/actor/relation.md docs/reference/actor/survey.md
git add docs/reference/actor/README.md docs/reference/brush/README.md docs/reference/brush/poly.md
git add docs/reference/level/graph.md docs/leveldesign/general/recipes/shapes/mitered-corner.md
git rm docs/reference/brush/relation.md
git commit -m "docs: actor relation and actor survey reference pages"
```

---

## Self-review

Run against the spec with fresh eyes after writing the plan, per the `writing-plans` skill. Findings
fixed inline where fixable, and stated plainly where not.

### 1. Spec coverage

| Spec section | Task(s) |
|---|---|
| Part 1: `measure` → `compare` rename | 1 |
| Part 1: `relation` moves from `brush` to `actor` | 2, 3 |
| Part 1: `find`'s non-brush broadening (explicit-only, bare name, `poly: null`, implicit-filter carve-out, near-miss exclusion) | 4 |
| Part 1: `compare`'s non-brush TARGET (distance, centroid-only deltas, the new three-value point field, no `footprint_2d` reuse) | 5 |
| Part 1: `set`'s non-brush TARGET, edge flags KEPT not refused | 6 |
| Part 2: output shape, tier token first, line grammar, `:idx` only on raw `touches` | 8, 18 |
| Part 2: directionality table (symmetric leads / fixed-direction both ways) | 8 (raw), 12, 13, 14, 16, 17 (csg) |
| Part 2: raw tier = `classify_pair`'s three relations, `carved_by` → `carves` | 8 |
| Part 2: `crosses` source/target kind table, collision gate, depth annotation, locality | 11, 12 |
| Part 2: `touches`, csg tolerance 0.015 | 10, 13 |
| Part 2: `connects` (Subtract-only, face-absence, never zone) | 14 |
| Part 2: `contains` (authored shape, strict full containment, volume competition, trunk-order tie) | 15, 16 |
| Part 2: `carves` (Semisolid never a target, Nonsolid is, total removal, partial-overlap coexistence) | 17 |
| Bounded cost: the neighborhood rule + the first-brush clause | 7, 19 |
| Bounded cost: the "decide by plane, not face existence" constraint | 10 (dedup), 13 |
| Open items: a production home for the point-in-solid test | 9 |
| Open items: error paths (unknown name, degenerate surveyed brush) | 18 |
| Open items: docs fallout (incl. the plugin skills tree and the skill's Known limitation) | 3, 6, 20 |
| Testing notes: reuse `test_csg_kind_facts.py` rather than rebuilding it | 9, 12, 17 |
| Testing notes: truncation-equivalence regression on a small synthetic level | 19 |
| Testing notes: pillar `contains`+`crosses` coexistence; 4-level nested competition with an oversized inner Subtract; genuine volume tie; redundant-nested `connects`; partial-overlap `carves`+`connects`; total-removal `carves` with no `touches`; two-adjacent-rooms `connects`-not-`touches` | 12, 14, 16, 17 |

**Deliberately not covered**, and why: the csg-tier `:idx` (the spec itself defers it to a v2
investigation against `uedcli-native`); `level graph`'s own `carved_by` vocabulary (a separate board
item by explicit owner instruction, and Task 8 has a test asserting this plan leaves it alone).

### 2. Placeholder scan

Every code block in this plan is either verified against the real file it edits (see the
verified-facts table and the fresh greps at the top) or is new code written out in full. Specifically
checked:

- **No `NotImplementedError` stubs remain.** The predecessor plan had three. Two of them
  (void-continuity, carve-detection) turned out to be writable once the real primitives were read —
  `actorgraph.point_in_brush` plus the native solidity query for `connects`, and a counterfactual
  neighborhood solve for `carves`. The third (brush-source penetration depth) dissolved when the
  depth was redefined per-plane, which the spec already required and which also removes the buried-
  actor artifact.
- **No invented APIs.** `run_cli` is gone; every test uses the real
  `argparse.Namespace` + `dispatch.dispatch` + `capsys` convention. `ctx.level`/`ctx.class_index`/
  `ctx.class_defaults` are gone; `actor/routes.py` has no `ctx` and every handler resolves its own
  source. `kind_semantics.build_fixture` is gone; Task 9 and Task 12 build the pillar scenario from
  `test_csg_kind_facts.py`'s own committed helpers instead of importing a spike harness (which is
  throwaway investigative code per `dev/docs/rules/spikes.md`, and whose `import corpus` cannot
  resolve from the repo root anyway).
- **No fabricated citations.** `NEIGHBORHOOD_PAD = Decimal("1")` cites `bounded_cost.py:35`'s own
  `PAD = 1.0`, which is where the value actually lives; spike.md §4's prose does not contain the word
  "pad" and is not quoted for it.
- **Every cited file path was checked to exist**, including the four docs and four plugin files in
  Task 3, and `docs/reference/actor/` (16 files: `README.md` plus 15 pages, but no `bbox.py`-style
  command module — the `actor/` command package is `_guards/build/edit/folder/label/preview/prop/
  query/routes`, which is what Tasks 8 and 18 point at).

### 3. Type consistency

- `RawFact` (Task 8) and `CsgFact` (Task 11) are the only two fact types; `format_raw_line` and
  `format_csg_line` are the only two line formatters.
- `raw_facts_for` returns `RawFacts` — one shape, named in the Interfaces block, in the function's
  own annotation, and at both call sites (Task 8's handler and Task 18's orchestrator). The
  predecessor plan's `(list, nodes)` tuple that its own type annotation disagreed with is gone.
- Every csg relation is `<name>_facts_for(ctx) -> list[CsgFact]`, one argument, so Task 18's
  orchestrator is a loop.
- Every scenario builder returns `Scenario(level, index, defaults)` — a dataclass with named fields.
  No test unpacks a fixture positionally, so no task can disagree with another about a fixture's
  arity.
- `authored_volume(actor, cells)` and `authored_shape_contains(container, target, cells)` both take
  ACTORS and say so in their names.

### 4. What I am not fully confident in

Stated plainly rather than smoothed over, because this project's own convention is that an honest
"not yet confirmed" belongs in the document.

1. **Face orientation (Task 12).** Which side of a resolved world surface is solid was NOT verified
   while writing this plan — `bspcsg.rs`'s leading-Add seed stores the world shell's faces reversed,
   so ring winding is not a safe oracle. Task 12 therefore measures it with a probe test before
   implementing anything that depends on it, and says explicitly what to do if the probe comes back
   `None`. If the measurement disagrees with the design, that is a real finding, and the task says to
   report it rather than loosen the assertion.
2. **`connects`'s grid sampling (Task 14).** The algorithm is concrete and covers every shape the
   spec names, but a connection narrower than the sample spacing is a known false negative. The spec
   states the criterion ("no separating solid face"), not an algorithm; this is my reading of it, and
   it is the one piece of Part D with no measurement behind it.
3. **`carves`'s counterfactual solve (Task 17).** This resolves the review's own cost/soundness
   question by choosing a technique rather than leaving a sketch — but it is a choice, made on the
   spike's timing numbers (a neighborhood solve is a median 6 ms) and guarded against the first-brush
   trap. It is not a technique the spike itself validated for this purpose. `CARVE_AREA_EPS = 1.0`
   uu² is likewise reasoned from the spike's measured boundary displacements, not fitted to anything;
   Task 17 says to report rather than tune it if the fixtures disagree.
4. **`test_csg_kind_facts.py`'s exact public names (Task 9).** The plan imports `LEFT`, `RIGHT`,
   `PF_SEMISOLID`, `PF_NOTSOLID`, `_brush`, `_solve` and `point_is_solid` from it. All seven exist
   today and the task says to re-check before running; if any has moved, adapt the import rather than
   copying the scenario, so the two never drift.
5. **`_l_shaped_brush`'s volume (Task 15).** The 0.75 factor is derived from the fixture's footprint
   as it reads now. The task says to re-derive it from the actual vertex list rather than trusting
   the number.
6. **`_csg_oper_or_skip`'s existing stderr WARNING.** `preview_native` already prints
   `WARNING: brush <name>: CsgOper ... is not a world CSG op; skipped` for every Intersect/
   Deintersect brush it filters out, on every solve. A survey of a level containing one will emit
   that line alongside this plan's own warning. Nothing in this plan changes it, and no task
   suppresses it — flagged because it is pre-existing behavior a reviewer might otherwise attribute
   to this change.
7. **The "one row per point candidate" decision (Task 4) is recorded only here.** The owner made it
   in conversation and Task 4's Step 1 is the only written copy of it and of its reasoning. This is a
   plan, which `dev/docs/rules/documentation.md` treats as ephemeral — plans are deleted once the
   work lands — so that written record goes with it. The BEHAVIOR survives in
   `test_find_emits_one_row_per_point_candidate_even_under_top_all`, which is what pins it long
   term; the reasoning behind it is not written down anywhere that outlives this file.
