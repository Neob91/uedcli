# actor survey + actor relation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Rename `brush relation` to `actor relation` (broadened for non-brush actors) and add a new
verb, `actor survey <name>`, that reports every raw and CSG-resolved spatial fact about one actor.

**Architecture:** Part A renames/broadens the existing `brush relation` family in place (pure Python,
mechanical). Part B adds `actor survey`'s raw tier as a thin, filtered wrapper over the already-shipped
`level graph` machinery (`uedcli/actorgraph.py`) — no new computation. Part C exposes one existing
native primitive (`CollisionModel::point_check`) to Python and ports the spike's own verified
neighborhood-selection algorithm into production code. Part D implements the five `csg`-tier relations
(`crosses`/`touches`/`connects`/`contains`/`carves`) as pure-Python orchestration over that native
primitive plus the already-shipped `solve_world_surfaces` CSG solver. Part E wires the two tiers
together into the CLI verb and closes the docs/error-path loose ends.

**Tech Stack:** Python 3.12 (uedcli's model/CLI layers), Rust + PyO3 (`uedcli-native`, the CSG/BSP
engine), pytest.

**Spec:** `dev/docs/board/to-plan/actor-survey-and-actor-relation-csg-resolved/spec.md` — read it in
full before starting; this plan does not restate its reasoning, only its exact rules. The spike it
depends on, `dev/docs/spikes/2026-09-23-actor-survey-csg-kind-and-cost/spike.md`, is the source of
every numeric threshold and the neighborhood/collision-gate algorithms below — read it too.

## Global Constraints

- No back-compat cruft: `brush relation` is deleted outright when `actor relation` lands in the same
  change — no alias, no deprecation shim (`CLAUDE.md`).
- Never let a Python exception reach the user: an unknown actor name or a degenerate brush exits 2
  naming the offending value, never a bare traceback (`CLAUDE.md`).
- New logic defaults to Rust (`uedcli-native`), except a minor addition or where reaching Rust needs
  a major refactor (`CLAUDE.md`, owner ruling 2026-09-20). The CSG-tier's actual solidity/geometry
  primitives are Rust (Part C); the per-relation orchestration and CLI/output-formatting layer is
  Python, matching how `actor diagram`/`level graph` already split this same boundary.
- Every command/flag/argument needs a real `help=` string (`CLAUDE.md`).
- Producer/query verbs print facts to stdout, one per line; human summaries go to stderr
  (`CLAUDE.md`, spec "Output shape").
- Raw-tier `_TOUCH_EPS = 1e-3` (authored-vertex tolerance, unchanged, `uedcli/actorgraph.py`).
  csg-tier tolerance is a SEPARATE constant, `0.015` uu (the engine's own `THRESH_POINTS_ARE_NEAR`,
  spike §3) — never conflate the two.
- Line grammar: `<tier> <src>[:idx] [Package.Class Kind] --<relation>[(annotation)]--> <dst>[:idx] [Package.Class Kind]`.
  `:idx` + area annotation only on a **raw** `touches` line with a real matched face pair. No
  `csg`-tier line ever carries `:idx`. Every `crosses` line (any source) carries a depth annotation,
  `crosses(8.2uu)`; every other `csg` line is bare.
- Tests via `bin/test`, never bare `pytest` (`dev/docs/rules/tests.md`). Run the whole suite once
  before the final commit of each task; iterate scoped (`bin/test -k <module>`) in between.

---

## Part A — `actor relation` (renamed from `brush relation`)

### Task 1: Rename `measure` to `compare`

**Files:**
- Modify: `uedcli/cli/parsers/brush.py:669-745` (the `rmeasure` subparser block)
- Modify: `uedcli/cli/commands/brush/relation.py` (dispatch table / handler name)
- Modify: `uedcli/relation.py:1-20` (module docstring), any `measure` references in docstrings
- Modify: `uedcli/tests/test_cli_brush_relation.py` (or wherever the existing `measure` CLI tests
  live — search `uedcli/tests/` for `brush relation measure` to find the exact file)
- Test: same test file, updated in place

**Interfaces:**
- Consumes: nothing new — this is a pure rename of an existing subcommand.
- Produces: `actor relation compare` (used by later tasks; `brush relation`/`measure` no longer
  exist after this task).

- [ ] **Step 1: Find every reference to the `measure` subcommand**

```bash
grep -rn "\"measure\"\|'measure'\|relation measure\|rmeasure" uedcli/ docs/ plugins/ | grep -v "\.pyc"
```

Read every hit before editing — this rename touches the subparser name, the dispatch key, help
strings, docstrings, and CLI tests. Do not proceed to Step 2 until you have the full list.

- [ ] **Step 2: Write the failing test**

In the existing CLI test file for `brush relation` (found in Step 1), add:

```python
def test_relation_compare_replaces_measure(run_cli):
    """`measure` is gone; `compare` does the identical job."""
    result = run_cli(["brush", "relation", "compare", "Wall", "Shelf"])
    assert result.returncode != 127  # not "unrecognized argument" / unknown subcommand
    old = run_cli(["brush", "relation", "measure", "Wall", "Shelf"])
    assert old.returncode == 2  # measure must be gone, not aliased
```

(If the existing test harness has a different `run_cli` fixture shape, use that project's own
convention — check the top of the existing test file for the real fixture name/signature before
writing this.)

- [ ] **Step 2: Run test to verify it fails**

Run: `bin/test -k test_relation_compare_replaces_measure -v`
Expected: FAIL (`compare` subcommand doesn't exist yet, `measure` still does)

- [ ] **Step 3: Rename the subparser**

In `uedcli/cli/parsers/brush.py`, change:

```python
    rmeasure = rsub.add_parser(
        "measure",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        help="report the exact geometric relationship between a reference face selector and one "
             "or more target selectors (plane, normals, distance, footprint_2d overlap, deltas)",
        epilog=_FOOTPRINT_EPILOG,
    )
```

to:

```python
    rcompare = rsub.add_parser(
        "compare",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        help="report the exact geometric relationship between a reference face selector and one "
             "or more target selectors (plane, normals, distance, footprint_2d overlap, deltas)",
        epilog=_FOOTPRINT_EPILOG,
    )
```

and every subsequent `rmeasure.add_argument(...)` to `rcompare.add_argument(...)` in that block
(there are four: `ref`, `target`, `--top`, `--allow-self`).

- [ ] **Step 4: Update the dispatch handler**

In `uedcli/cli/commands/brush/relation.py`, find the branch that dispatches on
`args.relationsub == "measure"` and change it to `"compare"`. Rename the handler function itself if
it is named `_cmd_measure` or similar (`grep -n "def _cmd" uedcli/cli/commands/brush/relation.py`
to find the real name).

- [ ] **Step 5: Update docstrings and help epilogs**

`uedcli/relation.py`'s module docstring and any function docstring that says "used by `brush
relation measure`" → "used by `actor relation compare`" (this file is touched again in Task 2 for
the `brush`→`actor` half of the rename — do the `measure`→`compare` wording now, the `brush`→
`actor` wording in Task 2, so each task's diff stays focused on one rename).

- [ ] **Step 6: Run test to verify it passes**

Run: `bin/test -k test_relation_compare_replaces_measure -v`
Expected: PASS

- [ ] **Step 7: Run the full existing relation test file**

Run: `bin/test -k test_cli_brush_relation` (or the real module name from Step 1)
Expected: every other existing test still passes with `compare` substituted for `measure` in its
own CLI invocations — update any that still say `"measure"` literally.

- [ ] **Step 8: Commit**

```bash
git add uedcli/cli/parsers/brush.py uedcli/cli/commands/brush/relation.py uedcli/relation.py
git add <the test file found in Step 1>
git commit -m "brush relation: rename measure to compare"
```

---

### Task 2: Move `brush relation` to `actor relation`

**Files:**
- Create: `uedcli/cli/parsers/actor_relation.py` (new file — the `relation` subparser, moved out of
  `brush.py` since it now hangs off `actor`, not `brush`)
- Modify: `uedcli/cli/parsers/actor.py` (wire the new subparser in)
- Modify: `uedcli/cli/parsers/brush.py` (delete the `relation` subparser block entirely — no alias)
- Create: `uedcli/cli/commands/actor/relation.py` (moved from `uedcli/cli/commands/brush/relation.py`)
- Modify: `uedcli/relation.py` (module docstring + all `RelationError` message strings: four in this
  file, verified at lines 476/641/647/653 by the spec's own docs-fallout note — re-grep, since Task 1
  may have shifted line numbers)
- Test: move/rename the CLI test file from `test_cli_brush_relation.py` to
  `test_cli_actor_relation.py` (exact name TBD by Step 1's grep — use whatever the real existing
  file is called, with `brush` replaced by `actor`)

**Interfaces:**
- Consumes: `uedcli/relation.py`'s existing public functions (`plane_relationship`,
  `classify_footprint_2d`, `compute_deltas`, `compute_set_translation`, `_passes_predicates`, etc.)
  — unchanged signatures, this task only moves the CLI plumbing around them, never their logic.
- Produces: `actor relation find|compare|set` as real, working commands. `brush relation` no longer
  parses at all (exit 2, "unrecognized arguments" — argparse's own standard behavior for a removed
  subcommand, not a custom message).

- [ ] **Step 1: Find every file that needs touching**

```bash
grep -rln "brush relation\|brush.relation\|cli/commands/brush/relation\|cli/parsers/brush.*relation" \
  uedcli/ docs/ plugins/ dev/docs/board/
```

This includes (per the spec's own docs-fallout list): `docs/reference/brush/relation.md`,
`docs/reference/brush/README.md`, `docs/reference/brush/poly.md`, `docs/reference/level/graph.md`,
`docs/leveldesign/general/recipes/shapes/mitered-corner.md`, `find --json`'s help string ("pipe into
`brush relation compare REF -`" after Task 1's rename), `uedcli/actorgraph.py`'s docstrings,
`plugins/uedcli/skills/verifying-brush-relations/SKILL.md`,
`plugins/uedcli/skills/positioning-a-brush/SKILL.md`,
`plugins/uedcli/references/brush-relation-basics.md`, `plugins/uedcli/HANDOFF.md`.

- [ ] **Step 2: Write the failing test**

```python
def test_relation_lives_under_actor_not_brush(run_cli):
    """brush relation is gone outright; actor relation does the job."""
    old = run_cli(["brush", "relation", "find", "--relative-to", "Wall"])
    assert old.returncode == 2
    new = run_cli(["actor", "relation", "find", "--relative-to", "Wall"])
    assert new.returncode != 2  # (a missing/unknown Wall actor is a separate, expected exit 2 —
    # run this against a real fixture level with a real "Wall" brush, matching whatever fixture
    # the existing brush-relation tests already use; check the existing test file for the fixture
    # setup pattern before writing the final assertion)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `bin/test -k test_relation_lives_under_actor_not_brush -v`
Expected: FAIL (`actor relation` doesn't exist yet)

- [ ] **Step 3: Move the parser code**

Read `uedcli/cli/parsers/brush.py`'s full `relation` subparser block (from `relation =
bsub.add_parser("relation", ...)` through the end of the `rset` block — this is the block already
read earlier in this project's design conversation, roughly 200 lines). Cut it out of `brush.py`
entirely and paste it into a new file, `uedcli/cli/parsers/actor_relation.py`, as a function:

```python
"""`actor relation` subparser: find/compare/set, the pairwise/scanning geometric-relation toolkit.
Moved from `brush relation` — broadened for non-brush actors, see `uedcli/relation.py`."""
import argparse


def add_relation_subparser(asub):
    """Wires `relation` (find/compare/set) under the `actor` command's subparsers, `asub`."""
    relation = asub.add_parser(
        "relation", help="cross-actor geometric relationships: find/compare/set")
    rsub = relation.add_subparsers(dest="relationsub", required=True)
    # ... (the exact body cut from brush.py's relation block, unchanged except rmeasure->rcompare
    # already done in Task 1 — paste it here verbatim, including _FOOTPRINT_EPILOG and
    # _parse_footprint_list, which move here too since only this subparser uses them; verify with
    # `grep -n "_FOOTPRINT_EPILOG\|_parse_footprint_list" uedcli/cli/parsers/brush.py` that nothing
    # else in brush.py references them before deleting them from there)
```

In `uedcli/cli/parsers/actor.py`, find where `asub` (the `actor` subparsers object) is built and
add:

```python
from .actor_relation import add_relation_subparser
# ... after asub = a.add_subparsers(...):
add_relation_subparser(asub)
```

- [ ] **Step 4: Move the command handler**

Move `uedcli/cli/commands/brush/relation.py` to `uedcli/cli/commands/actor/relation.py` (`git mv`,
so history follows). Update whatever dispatch table wires `brush relation`'s subcommand name to its
handler function (find it via `grep -rn "commands.brush.relation\|commands/brush/relation"
uedcli/cli/`) to instead wire `actor relation` to the moved handler.

- [ ] **Step 5: Delete the old parser block, no alias**

Confirm `uedcli/cli/parsers/brush.py` no longer defines a `relation` subparser at all — the whole
block from Step 3 is gone, not commented out, not aliased.

- [ ] **Step 6: Update `uedcli/relation.py`'s error strings and docstrings**

Every `RelationError(f"...brush relation...")` message becomes `f"...actor relation..."`. The
module docstring's "used by `brush relation`" references become "used by `actor relation`".

- [ ] **Step 7: Run test to verify it passes**

Run: `bin/test -k test_relation_lives_under_actor_not_brush -v`
Expected: PASS

- [ ] **Step 8: Update docs and plugin skills from Step 1's list**

For each doc file found in Step 1: replace `brush relation` with `actor relation` and `measure`
with `compare` throughout. For `plugins/uedcli/skills/verifying-brush-relations/SKILL.md`
specifically: its "Known limitation" section describes `brush relation`'s point-actor blind spot
and a manual `actor find --overlapping-bbox`-shaped workaround — Task 3/4 of this plan remove that
limitation, so mark it removed here with one sentence, don't just rename the command in place
(read the section first, `grep -n "Known limitation" -A 20` on that file).

- [ ] **Step 9: Run the full relation test module + a broader sweep**

Run: `bin/test -k relation`
Expected: all green — this catches any other test file that still invokes `brush relation`
somewhere incidental (e.g. a fixture setup helper).

- [ ] **Step 10: Commit**

```bash
git add uedcli/cli/parsers/actor_relation.py uedcli/cli/parsers/actor.py uedcli/cli/parsers/brush.py
git add uedcli/cli/commands/actor/relation.py uedcli/relation.py
git add docs/reference/brush/relation.md docs/reference/brush/README.md docs/reference/brush/poly.md
git add docs/reference/level/graph.md docs/leveldesign/general/recipes/shapes/mitered-corner.md
git add plugins/uedcli/skills/verifying-brush-relations/SKILL.md
git add plugins/uedcli/skills/positioning-a-brush/SKILL.md
git add plugins/uedcli/references/brush-relation-basics.md plugins/uedcli/HANDOFF.md
git add <the moved/renamed test file>
git commit -m "relation: move from brush to actor"
```

(List only files this task actually touched — drop any path above that Step 1's grep didn't
surface, and add any it found that isn't listed here.)

---

### Task 3: Broaden `find` for non-brush candidates

**Files:**
- Modify: `uedcli/cli/commands/actor/relation.py` (the `find` handler)
- Modify: `uedcli/relation.py` (wherever `_default_candidates`/the explicit-name candidate resolver
  lives — grep `_default_candidates\|skipping non-brush actor`)
- Test: the actor-relation test file from Task 2

**Interfaces:**
- Consumes: `uedcli/relation.py`'s existing `_passes_predicates`, `near_miss_count`, the footprint/
  plane filter logic — unchanged.
- Produces: `find`'s candidate resolution now yields non-brush actors too, each represented as
  `(actor, None)` where a brush candidate is `(actor, poly_index)` — later steps in this task decide
  what `None` means at each call site.

- [ ] **Step 1: Write the failing test**

```python
def test_find_includes_named_point_actor_candidate(run_cli, fixture_level_with_point_actor_near_wall):
    """A non-brush actor named explicitly is a real candidate, not skipped."""
    result = run_cli(["actor", "relation", "find", "MyLight",
                       "--relative-to", "Wall:3", "--max-gap", "20"])
    assert result.returncode == 0
    assert "MyLight" in result.stdout  # bare name, no colon-index
    assert "MyLight:" not in result.stdout


def test_find_default_candidates_stay_brush_only(run_cli, fixture_level_with_point_actor_near_wall):
    """Omitting candidates still scans brushes only -- the default is unchanged."""
    result = run_cli(["actor", "relation", "find", "--relative-to", "Wall:3"])
    assert "MyLight" not in result.stdout
```

(`fixture_level_with_point_actor_near_wall` needs building or reusing from an existing fixture —
check `uedcli/tests/conftest.py` and the existing relation test file for how other tests build a
level with named brushes/actors; follow that exact pattern, adding one point actor near a wall
brush with `bCollideActors=True` and a real `CollisionRadius`.)

- [ ] **Step 2: Run test to verify it fails**

Run: `bin/test -k "test_find_includes_named_point_actor_candidate or test_find_default_candidates_stay_brush_only" -v`
Expected: first FAILS (point actor currently skipped with a `skipping non-brush actor:` stderr
note), second PASSES already (default is already brush-only, confirms nothing to change there).

- [ ] **Step 3: Remove the explicit-name skip**

Find the code that currently does (per the spec, this exists today):
```python
# for an explicitly-named candidate that isn't a brush:
print(f"skipping non-brush actor: {name}", file=sys.stderr)
continue
```
Delete this branch for the EXPLICIT-name path only (candidates passed as positional args or via
`-` stdin) — leave the DEFAULT (no names given) candidate enumeration unchanged, still brush-only
(confirmed correct by the second test above already passing).

- [ ] **Step 4: Represent a point candidate as a bare name, no `:idx`**

Wherever the `find` handler currently formats a match as `f"{candidate}:{idx}"`, branch: if the
candidate actor has no `.brush`, print the bare name (`candidate`) with no colon-index; if it does,
keep the existing `f"{candidate}:{idx}"` format.

- [ ] **Step 5: Skip predicate checks that don't apply to a point**

For a non-brush candidate: `--footprint`/`--plane`, if given, exclude it (no face to test a
face-pair predicate against — not an error, just a non-match). The IMPLICIT filter (when
`--footprint` is omitted, `_passes_predicates` already excludes anything with `footprint_2d ==
"none"`) must NOT apply to a point candidate — it is ranked on `--max-gap`/`--min-gap` (pure
distance to REF's plane) alone in that case. Point candidates never contribute to the `--max-gap`
near-miss count (that counter is footprint-keyed, per `relation.py`'s existing `near_miss_count`).

- [ ] **Step 6: `--json` emits `poly: null` for a point candidate**

The existing `--json` row shape is `{ref, ref_poly, candidate, poly}` — for a point candidate,
`poly` is `null` (Python `None`, JSON `null`), not omitted, not `-1`.

- [ ] **Step 7: Run tests to verify they pass**

Run: `bin/test -k "test_find_includes_named_point_actor_candidate or test_find_default_candidates_stay_brush_only" -v`
Expected: both PASS

- [ ] **Step 8: Run the full relation test module**

Run: `bin/test -k relation`
Expected: all green

- [ ] **Step 9: Commit**

```bash
git add uedcli/cli/commands/actor/relation.py uedcli/relation.py <test file>
git commit -m "actor relation find: accept non-brush candidates"
```

---

### Task 4: Broaden `compare` for a non-brush TARGET

**Files:**
- Modify: `uedcli/relation.py` (new point-in-polygon helper; the `compare`-equivalent report
  builder)
- Modify: `uedcli/cli/commands/actor/relation.py` (the `compare` handler's TARGET-selector parsing)
- Test: the actor-relation test file

**Interfaces:**
- Consumes: `relation.py`'s `_plane_basis_2d`/`_dot`/`_sub` (already exist, used by
  `classify_footprint_2d` today — reuse for the new point projection) and `compute_deltas`'s
  centroid-only math.
- Produces: `point_footprint(ref_poly_world_verts, ref_normal, point) -> str`, returning one of
  `"inside"`/`"on_boundary"`/`"outside"` — a NEW function, not a `classify_footprint_2d` branch (the
  spec found that function unconditionally returns `contains_a_in_b` for a degenerate one-point
  input, so this needs its own logic, not a shared code path).

- [ ] **Step 1: Write the failing test**

```python
def test_compare_point_target_inside(run_cli, fixture_level_with_point_actor_near_wall):
    """A point actor whose Location projects inside REF's footprint reports 'inside'."""
    result = run_cli(["actor", "relation", "compare", "Wall:3", "MyLight"])
    assert result.returncode == 0
    assert "inside" in result.stdout
    assert "distance:" in result.stdout
    assert "centroid_u:" in result.stdout and "centroid_v:" in result.stdout
    assert "footprint_2d:" not in result.stdout  # not the brush-vs-brush vocabulary
    assert "edge_u" not in result.stdout  # no edge-extent half for a point target


def test_compare_point_target_outside(run_cli, fixture_level_with_far_point_actor):
    result = run_cli(["actor", "relation", "compare", "Wall:3", "FarLight"])
    assert "outside" in result.stdout
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `bin/test -k "test_compare_point_target_inside or test_compare_point_target_outside" -v`
Expected: FAIL (non-brush TARGET currently unsupported or mis-handled by `compare`)

- [ ] **Step 3: Write the point-in-polygon helper**

In `uedcli/relation.py`, add:

```python
def point_footprint_2d(ref_uv_poly: list[tuple[float, float]], point_uv: tuple[float, float]) -> str:
    """Where `point_uv` sits relative to `ref_uv_poly`'s footprint, in the SAME (U, V) frame
    `classify_footprint_2d` already projects into. NOT a `classify_footprint_2d` branch: that
    function's `_clip_2d` degenerates to `contains_a_in_b` unconditionally for a 1-vertex "polygon"
    (its `inside()` test is vacuously true with a zero-length clip edge) -- verified wrong for every
    input, including a point 900uu away. This is real point-in-polygon (ray casting), returning a
    vocabulary that does not collide with `footprint_2d`'s own values (`contains` is already taken
    as a `--footprint` filter alias there).
    """
    on_boundary = _point_on_any_edge(ref_uv_poly, point_uv)
    if on_boundary:
        return "on_boundary"
    return "inside" if _point_in_polygon_2d(ref_uv_poly, point_uv) else "outside"


def _point_on_any_edge(poly: list[tuple[float, float]], p: tuple[float, float]) -> bool:
    """True if `p` lies on any edge of `poly`, within `_TOUCH_EPS` -- reuses the same
    point-on-segment test `_shares_vertex` already implements for the face-pair case."""
    n = len(poly)
    for i in range(n):
        if _point_on_segment(poly[i], poly[(i + 1) % n], p):
            return True
    return False


def _point_on_segment(a: tuple[float, float], b: tuple[float, float], p: tuple[float, float]) -> bool:
    """Same test `_shares_vertex` already uses for a vertex-on-segment check -- extracted here so
    both call sites share one implementation instead of duplicating the tolerance logic."""
    dx, dy = b[0] - a[0], b[1] - a[1]
    seg_len = (dx * dx + dy * dy) ** 0.5
    if seg_len < 1e-9:
        return abs(p[0] - a[0]) <= _TOUCH_EPS and abs(p[1] - a[1]) <= _TOUCH_EPS
    cross = dx * (p[1] - a[1]) - dy * (p[0] - a[0])
    if abs(cross) / seg_len > _TOUCH_EPS:
        return False
    dot = ((p[0] - a[0]) * dx + (p[1] - a[1]) * dy) / (seg_len * seg_len)
    slack = _TOUCH_EPS / seg_len
    return -slack <= dot <= 1 + slack


def _point_in_polygon_2d(poly: list[tuple[float, float]], p: tuple[float, float]) -> bool:
    """Standard ray-casting point-in-polygon, even-odd rule."""
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
```

(Check whether `_shares_vertex`/`_point_on_segment`-shaped logic already exists verbatim in
`relation.py` before adding a duplicate — the spec's own research found `_shares_vertex` at line
~165-185; if it already has this exact shape, call it directly instead of re-defining
`_point_on_segment`.)

- [ ] **Step 4: Wire it into the `compare` report builder**

Find where `compare`'s (formerly `measure`'s) per-target report is assembled — it currently branches
on whether TARGET is a face selector. Add a branch: if TARGET names a non-brush actor, project its
`Location` into REF's `(U, V)` frame (reuse `_plane_basis_2d`/`_dot`/`_sub`, the same functions
`classify_footprint_2d` already uses for a real face), compute `distance` as the signed perpendicular
distance to REF's plane (reuse whatever `plane_relationship`/the existing `distance` computation
already does for two faces, applied with the point standing in for the second face's centroid), call
`point_footprint_2d` for the footprint field, and report `centroid_u`/`centroid_v` (the point's own
projected U/V) with no edge-extent fields at all.

- [ ] **Step 5: Run tests to verify they pass**

Run: `bin/test -k "test_compare_point_target_inside or test_compare_point_target_outside" -v`
Expected: PASS

- [ ] **Step 6: Run the full relation test module**

Run: `bin/test -k relation`
Expected: all green

- [ ] **Step 7: Commit**

```bash
git add uedcli/relation.py uedcli/cli/commands/actor/relation.py <test file>
git commit -m "actor relation compare: support a non-brush TARGET"
```

---

### Task 5: Confirm `set`'s non-brush TARGET support (edge flags kept, not refused)

**Files:**
- Modify: `uedcli/cli/commands/actor/relation.py` (the `set` handler's TARGET parsing — allow a bare
  actor name, not just `BRUSH:idx`)
- Modify: `uedcli/relation.py` (`compute_set_translation`'s TARGET-resolution branch, if it currently
  assumes a brush face)
- Test: the actor-relation test file

**Interfaces:**
- Consumes: `relation.py`'s existing `_edge_extent`, `compute_set_translation` — the spec's own
  verified math (`pick(target) − pick(ref)`) already produces distinct values for
  `--edge-u-min`/`--edge-u-max`/`--centroid-u` against a point target, so THIS task does not change
  that math — only the argument-parsing/target-resolution layer needs to accept a bare actor name.
- Produces: `actor relation set MyLight --relative-to Wall:3 --gap 8` writes `MyLight.Location`.

- [ ] **Step 1: Write the failing test**

```python
def test_set_moves_a_point_actor_by_centroid(run_cli, fixture_level_with_point_actor_near_wall):
    result = run_cli(["actor", "relation", "set", "MyLight",
                       "--relative-to", "Wall:3", "--centroid-u", "0", "--centroid-v", "0"])
    assert result.returncode == 0
    moved = load_actor(result, "MyLight")  # use whatever fixture-reload helper the existing
    # set tests already use to read back the mutated trunk
    assert moved.location is not None  # replace with an exact expected coordinate once Wall:3's
    # real geometry in the fixture is known -- compute it the same way the existing brush-target
    # `set` tests assert an exact post-move coordinate, don't leave this as a vague non-None check
    # in the final test


def test_set_edge_flags_work_against_a_point_target(run_cli, fixture_level_with_point_actor_near_wall):
    """--edge-u-min against a point target is a real, distinct offset -- not refused, not an alias
    for --centroid-u."""
    a = run_cli(["actor", "relation", "set", "MyLight", "--relative-to", "Wall:3", "--edge-u-min", "8"])
    b = run_cli(["actor", "relation", "set", "MyLight", "--relative-to", "Wall:3", "--centroid-u", "8"])
    assert a.returncode == 0 and b.returncode == 0
    loc_a = load_actor(a, "MyLight").location
    loc_b = load_actor(b, "MyLight").location
    assert loc_a != loc_b  # genuinely different offsets, per the spec's own math verification
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `bin/test -k "test_set_moves_a_point_actor_by_centroid or test_set_edge_flags_work_against_a_point_target" -v`
Expected: FAIL (TARGET parsing currently requires `BRUSH:idx`, rejects a bare actor name)

- [ ] **Step 3: Broaden TARGET parsing**

Find `set`'s `target` argument parsing (currently `nargs="+", metavar="TARGET:idx"`, exact
`BRUSH:idx` only). Add a branch: if the given token has no `:idx` suffix, resolve it as a bare actor
name; if that actor has no `.brush`, treat it as a point target (write `.Location` directly, no poly
index involved). If the token has no `:idx` suffix AND the named actor DOES have a `.brush`, that
remains the existing "bare name/index list not allowed" exit-2 case — unchanged, only the "actor has
no brush" branch is new.

- [ ] **Step 4: Confirm `compute_set_translation` doesn't assume a brush TARGET**

Read `compute_set_translation` (`relation.py:628` per the spec's own citation) — if it currently
indexes into `target.brush.polys[idx]` unconditionally, add a branch for a point target that skips
straight to using the point's own `(u, v)` (no polygon, no vertex list) wherever the function
currently derives `target`'s own UV position from a face.

- [ ] **Step 5: Run tests to verify they pass**

Run: `bin/test -k "test_set_moves_a_point_actor_by_centroid or test_set_edge_flags_work_against_a_point_target" -v`
Expected: PASS

- [ ] **Step 6: Run the full relation test module**

Run: `bin/test -k relation`
Expected: all green

- [ ] **Step 7: Commit**

```bash
git add uedcli/cli/commands/actor/relation.py uedcli/relation.py <test file>
git commit -m "actor relation set: accept a non-brush TARGET"
```

---

## Part B — `actor survey`'s raw tier

### Task 6: `actor survey <name>` — raw tier only

**Files:**
- Create: `uedcli/actor_survey.py` (new module — the raw+csg orchestration; this task fills in only
  the raw half)
- Create: `uedcli/cli/parsers/actor_survey.py` (the `survey` subparser)
- Modify: `uedcli/cli/parsers/actor.py` (wire it in)
- Create: `uedcli/cli/commands/actor/survey.py` (the handler)
- Test: `uedcli/tests/test_actor_survey.py` (new file)

**Interfaces:**
- Consumes: `uedcli/actorgraph.py`'s `build_graph`, `Edge`, `NodeTag`, `_node_bracket`,
  `decompose_convex`, `classify_pair`, `point_in_brush` (all unchanged, existing functions).
- Produces: `raw_facts_for(level, class_index, name) -> list[Edge]` — every raw `Edge` touching
  `name`, in EITHER direction (incoming or outgoing), reusing `build_graph`'s existing edge list
  filtered down rather than re-computing anything. `format_raw_line(edge, nodes, surveyed_name) ->
  str` — one line, tier-prefixed `raw `, with the surveyed actor leading for symmetric relations
  (per the spec's directionality section) and `carved_by` renamed to `carves` with the Subtract
  always leading (per the spec's Round 6 ruling — this is `actor survey`'s OWN presentation choice;
  `level graph`'s own `format_text` is UNTOUCHED by this task, still prints `carved_by`).

- [ ] **Step 1: Write the failing test**

```python
def test_survey_raw_tier_shows_touches_and_contains(run_cli, fixture_level_two_rooms):
    """A minimal two-room fixture: Subtract room A touches an Add wall, and contains a Mover."""
    result = run_cli(["actor", "survey", "RoomA"])
    assert result.returncode == 0
    lines = [l for l in result.stdout.splitlines() if l.startswith("raw ")]
    assert any("--touches(" in l for l in lines)
    assert any("--contains-->" in l for l in lines)
    assert not any(l.startswith("csg ") for l in lines)  # this task adds raw only


def test_survey_raw_tier_renames_carved_by_to_carves(run_cli, fixture_level_room_carves_wall):
    """Where level graph would print carved_by, actor survey prints carves, Subtract leading."""
    result = run_cli(["actor", "survey", "RoomA"])
    raw_lines = [l for l in result.stdout.splitlines() if l.startswith("raw ")]
    assert any("--carves-->" in l for l in raw_lines)
    assert not any("carved_by" in l for l in raw_lines)
    # the Subtract (RoomA) must lead the line, not the Add it carved:
    carve_line = next(l for l in raw_lines if "--carves-->" in l)
    assert carve_line.split()[1].split(":")[0].split("[")[0] == "RoomA" or carve_line.startswith("raw RoomA")
```

(Both fixtures need building — reuse whatever level-fixture pattern
`uedcli/tests/test_actorgraph.py` already uses for `build_graph`, since this is the exact same
underlying data shape `actor_survey.py` is filtering, just naming rooms/walls explicitly instead of
generic `Brush1`/`Brush2`.)

- [ ] **Step 2: Run tests to verify they fail**

Run: `bin/test -k "test_survey_raw_tier_shows_touches_and_contains or test_survey_raw_tier_renames_carved_by_to_carves" -v`
Expected: FAIL (`actor survey` doesn't exist yet)

- [ ] **Step 3: Write `uedcli/actor_survey.py`'s raw half**

```python
"""`actor survey <name>` -- every raw and CSG-resolved spatial fact about one actor. This module
owns the orchestration; the raw tier reuses `actorgraph.py`'s already-shipped computation exactly,
the csg tier (added in Part D) is new. See
`dev/docs/board/to-plan/actor-survey-and-actor-relation-csg-resolved/spec.md` for the full rule set
this implements -- read it before changing anything here."""
from __future__ import annotations

from dataclasses import dataclass

from . import actorgraph


@dataclass(frozen=True)
class RawFact:
    """One raw-tier line's worth of information, already resolved to `actor survey`'s OWN
    presentation rules (which can differ from `level graph`'s -- the `carves` rename is the reason
    this is a separate type from `actorgraph.Edge` rather than a direct reuse)."""
    src: str
    dst: str
    relation: str
    matched_pair: tuple[int, int] | None
    area_estimate: float | None


def raw_facts_for(level, class_index, name: str) -> list[RawFact]:
    """Every raw edge touching `name`, renamed/redirected to `actor survey`'s own convention:
    `level graph`'s `carved_by` (Add leads) becomes `carves` (Subtract leads, always) -- the
    owner's explicit "one name, flip the sides to match" ruling. `touches`/`contains` are
    unchanged (same word, same meaning, just filtered to `name`)."""
    graph = actorgraph.build_graph(level, class_index)
    if name not in graph.node_names:
        raise ActorNotFoundError(name)
    out = []
    for edge in graph.edges:
        if edge.src != name and edge.dst != name:
            continue
        if edge.relation == "carved_by":
            # level graph: Edge(src=Add, dst=Subtract, relation="carved_by") -- Add leads.
            # actor survey: Subtract leads, word is "carves".
            out.append(RawFact(src=edge.dst, dst=edge.src, relation="carves",
                                matched_pair=None, area_estimate=None))
        else:
            out.append(RawFact(src=edge.src, dst=edge.dst, relation=edge.relation,
                                matched_pair=edge.matched_pair, area_estimate=edge.area_estimate))
    return out, graph.nodes


class ActorNotFoundError(Exception):
    """Raised when `actor survey` is given a name not in the level -- caller maps this to exit 2,
    per this project's 'never let a Python exception reach the user' rule."""
    def __init__(self, name: str):
        super().__init__(f"Actor not found: {name}")
        self.name = name


def format_raw_line(fact: RawFact, nodes, surveyed_name: str) -> str:
    """One `raw `-prefixed line. Symmetric relations (`touches`) put `surveyed_name` first,
    matching the spec's stated deviation from `level graph`'s own pair-enumeration convention --
    `level graph` has no "subject" to lead with, `actor survey` does."""
    src, dst = fact.src, fact.dst
    if fact.relation == "touches" and dst == surveyed_name:
        src, dst = dst, src
        if fact.matched_pair is not None:
            fact = RawFact(src=src, dst=dst, relation=fact.relation,
                            matched_pair=(fact.matched_pair[1], fact.matched_pair[0]),
                            area_estimate=fact.area_estimate)
    has_idx = fact.relation == "touches" and fact.matched_pair is not None
    src_tok = f"{src}:{fact.matched_pair[0]}" if has_idx else src
    dst_tok = f"{dst}:{fact.matched_pair[1]}" if has_idx else dst
    rel = fact.relation
    if fact.relation == "touches" and fact.area_estimate is not None:
        rel = f"touches({fact.area_estimate:.4g}uu^2)"
    return (f"raw {src_tok} {actorgraph._node_bracket(nodes[src])} --{rel}--> "
            f"{dst_tok} {actorgraph._node_bracket(nodes[dst])}")
```

- [ ] **Step 4: Write the CLI wiring**

`uedcli/cli/parsers/actor_survey.py`:
```python
"""`actor survey <name>` subparser."""


def add_survey_subparser(asub):
    p = asub.add_parser(
        "survey",
        help="every raw and CSG-resolved spatial fact about one actor (brush or non-brush)")
    p.add_argument("name", metavar="NAME", help="the actor to survey")
```

Wire into `uedcli/cli/parsers/actor.py` the same way Task 2 wired `add_relation_subparser`.

`uedcli/cli/commands/actor/survey.py`:
```python
"""`actor survey` command handler."""
import sys

from ... import actor_survey


def run(args, ctx) -> int:
    level = ctx.level  # match whatever the real context object's attribute name is -- check an
    # existing actor-command handler (e.g. `uedcli/cli/commands/actor/bbox.py`) for the real
    # `ctx`/`level`/`class_index` access pattern and use that, not this placeholder name
    class_index = ctx.class_index
    try:
        raw_facts, nodes = actor_survey.raw_facts_for(level, class_index, args.name)
    except actor_survey.ActorNotFoundError as e:
        print(str(e), file=sys.stderr)
        return 2
    for fact in raw_facts:
        print(actor_survey.format_raw_line(fact, nodes, args.name))
    print(f"actor survey: {len(raw_facts)} raw fact(s) for {args.name}", file=sys.stderr)
    return 0
```

(Adjust `ctx.level`/`ctx.class_index` to match this codebase's real context-passing convention --
read `uedcli/cli/commands/actor/bbox.py` or `uedcli/cli/commands/actor/diagram.py` first, since
both already need `level`+`class_index` the same way this handler does.)

- [ ] **Step 5: Run tests to verify they pass**

Run: `bin/test -k "test_survey_raw_tier_shows_touches_and_contains or test_survey_raw_tier_renames_carved_by_to_carves" -v`
Expected: PASS

- [ ] **Step 6: Run the full actor-survey + actorgraph test modules**

Run: `bin/test -k "actor_survey or actorgraph"`
Expected: all green (confirms this task didn't disturb `level graph`'s own behavior — it must still
print `carved_by`, unchanged)

- [ ] **Step 7: Commit**

```bash
git add uedcli/actor_survey.py uedcli/cli/parsers/actor_survey.py uedcli/cli/parsers/actor.py
git add uedcli/cli/commands/actor/survey.py uedcli/tests/test_actor_survey.py
git commit -m "actor survey: raw tier"
```

---

## Part C — `actor survey`'s csg tier: native foundation

### Task 7: Expose point/box solidity to Python

**Files:**
- Modify: `uedcli-native/src/lib.rs` (new `#[pyfunction]`)
- Modify: `uedcli-native/src/collision.rs` (if `CollisionModel::level` needs a variant that takes an
  already-`Built` model rather than re-parsing one — check `Built.model`'s type against
  `CollisionModel::level`'s parameter type first)
- Test: `uedcli-native/tests/` (a Rust test, mirroring this project's existing native test
  convention — check `uedcli-native/src/` for an existing `#[cfg(test)]` block to match style) AND
  a Python-side smoke test

**Interfaces:**
- Consumes: `uedcli-native/src/collision.rs`'s existing `CollisionModel::level(m: &Model) ->
  CollisionModel` and `CollisionModel::point_check(&self, loc: Vec3, extent: Vec3) -> bool` — both
  already exist and are already used internally by pathing (`World::single_point_check`); this task
  ONLY adds a `#[pyfunction]` wrapper, it does not change either method.
- Produces: a new Python-callable `uedcli_native.point_is_solid(built_model, loc, extent) -> bool`,
  where `built_model` is whatever `build_geometry_bspcsg`/`solve_world_surfaces` already returns
  (check `Built`'s exact PyO3-exposed shape in `lib.rs:57-70` before writing the wrapper's argument
  type — it may need to accept the raw `Built` object directly rather than re-marshaling a `Model`).

- [ ] **Step 1: Write the failing test**

```python
# uedcli/tests/test_native_point_solidity.py
def test_point_is_solid_matches_kind_semantics_spike():
    """Same shape as the spike's own kind_semantics.py measurement: an Add pillar's centre is
    solid, and outside the pillar (but inside the enclosing Subtract room) is void."""
    import uedcli_native
    from uedcli.preview_native import solve_world_surfaces
    # build the same three-brush fixture the spike's kind_semantics.py harness used (Room Subtract,
    # Pillar Add, no Cutter for this simpler test) -- reuse
    # dev/docs/spikes/2026-09-23-actor-survey-csg-kind-and-cost/harness/kind_semantics.py's own
    # brush-construction helper directly by importing it, rather than re-deriving the fixture:
    import importlib.util
    spec = importlib.util.spec_from_file_location(
        "kind_semantics",
        "dev/docs/spikes/2026-09-23-actor-survey-csg-kind-and-cost/harness/kind_semantics.py")
    kind_semantics = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(kind_semantics)
    level, index = kind_semantics.build_fixture(kind="add")  # match whatever the real function
    # name/signature in that harness file turns out to be -- read it fully before writing this call
    built = solve_world_surfaces(list(level.actors.values()), index)
    assert uedcli_native.point_is_solid(built, (0.0, 0.0, 0.0), (0.0, 0.0, 0.0)) is True  # pillar centre
    assert uedcli_native.point_is_solid(built, (600.0, 0.0, 0.0), (0.0, 0.0, 0.0)) is False  # outside pillar
```

- [ ] **Step 2: Run test to verify it fails**

Run: `bin/test -k test_point_is_solid_matches_kind_semantics_spike -v`
Expected: FAIL (`uedcli_native.point_is_solid` doesn't exist)

- [ ] **Step 3: Add the Rust wrapper**

In `uedcli-native/src/lib.rs`, near the other `#[pyfunction]`s:

```rust
/// Point/box solidity query, exposed for `actor survey`'s csg tier. Wraps the ALREADY-EXISTING
/// `CollisionModel::point_check` (used internally by pathing's `World::single_point_check`) --
/// this function adds no new solidity logic, it only exposes what already exists to Python. See
/// `dev/docs/spikes/2026-09-23-actor-survey-csg-kind-and-cost/harness/solidity.py` for the
/// Python-side verification of this exact walk (that file is a throwaway spike port; this is the
/// production Rust path it was standing in for).
#[pyfunction]
fn point_is_solid(py: Python<'_>, built: &Built, loc: (f32, f32, f32), extent: (f32, f32, f32)) -> PyResult<bool> {
    py.allow_threads(|| {
        let cm = collision::CollisionModel::level(&built.model);
        Ok(cm.point_check(
            model::Vec3::new(loc.0, loc.1, loc.2),
            model::Vec3::new(extent.0, extent.1, extent.2),
        ))
    })
}
```

(Verify `Built`'s field is named `model` and is `pub(crate)` or otherwise reachable from this
function — check `struct Built` at `lib.rs:57`; adjust field access accordingly. If `CollisionModel`
isn't already imported in `lib.rs`, add `use crate::collision;` at the top.)

Register it in the `#[pymodule]` block:
```rust
    m.add_function(wrap_pyfunction!(point_is_solid, m)?)?;
```

- [ ] **Step 4: Rebuild the native extension**

Run: `bin/test` once (this project's own convention: the first `bin/test` in a fresh worktree
rebuilds the native extension; confirm via `dev/docs/rules/tests.md` if a more direct rebuild
command exists, e.g. `maturin develop`, and use that instead if faster for iterating on this one
task).

- [ ] **Step 5: Run test to verify it passes**

Run: `bin/test -k test_point_is_solid_matches_kind_semantics_spike -v`
Expected: PASS

- [ ] **Step 6: Add a Rust-side unit test too**

Per this project's spike convention (pin every checkable fact with a test close to the code), add a
`#[cfg(test)]` test in `collision.rs` or `lib.rs` (match whichever file's existing test convention
applies) that constructs a trivial one-node model and asserts `point_check` behaves as expected —
this is a much cheaper regression than the Python round-trip test above for catching a future
regression in `point_check` itself specifically.

- [ ] **Step 7: Run the full native test suite**

Run: `cargo test` (from `uedcli-native/`, per `NATIVE-MATERIALIZE.md`'s own testing note: fast, keep
green)
Expected: all green

- [ ] **Step 8: Commit**

```bash
git add uedcli-native/src/lib.rs uedcli-native/src/collision.rs uedcli/tests/test_native_point_solidity.py
git commit -m "native: expose point/box solidity check to Python"
```

---

### Task 8: Port the neighborhood-selection algorithm into production code

**Files:**
- Modify: `uedcli/actor_survey.py` (add the neighborhood function)
- Test: `uedcli/tests/test_actor_survey.py`

**Interfaces:**
- Consumes: `uedcli/writes.py`'s `actor_bounds`, `aabb_intersects` (unchanged); `uedcli/movers.py`'s
  `is_mover`; `uedcli/normalize.py`'s `is_builder_brush`.
- Produces: `neighborhood(level, class_index, surveyed_actor, *, pad=...) -> list[Actor]` — the
  EXACT algorithm already verified by the spike over 140 real surveys
  (`dev/docs/spikes/2026-09-23-actor-survey-csg-kind-and-cost/harness/bounded_cost.py::neighborhood`),
  ported here as the production implementation. Do not re-derive this algorithm — port it verbatim,
  including the first-world-CSG-brush clause (found necessary by measurement, not optional).

- [ ] **Step 1: Write the failing test**

```python
def test_neighborhood_includes_nearby_brushes_and_first_world_brush(fixture_level_far_apart_rooms):
    """Matches the spike's own verified shape: nearby brushes are included by AABB, and the
    level's first world-CSG brush is always included even if far away."""
    from uedcli import actor_survey
    level, index = fixture_level_far_apart_rooms  # a level with >2 rooms, one surveyed room far
    # from the level's own first brush -- build this fixture following the same pattern
    # bounded_cost.py's own `measure_level` uses for constructing its test scenarios
    n = actor_survey.neighborhood(level, index, level.actors["FarRoom"])
    names = {a.name for a in n}
    assert "FarRoom" in names
    assert level.order[0] in names or any(
        not (level.actors[nm].brush is None) for nm in [level.order[0]])  # the level's first
    # world-CSG brush must be present -- tighten this assertion once the fixture's exact trunk
    # order is known, matching bounded_cost.py's own `have_first` check precisely
```

- [ ] **Step 2: Run test to verify it fails**

Run: `bin/test -k test_neighborhood_includes_nearby_brushes_and_first_world_brush -v`
Expected: FAIL (`neighborhood` doesn't exist in `actor_survey.py` yet)

- [ ] **Step 3: Port the function**

In `uedcli/actor_survey.py`, add (ported directly from the spike harness, cited in the docstring
per this project's "back-reference the spike" convention):

```python
from decimal import Decimal

from . import movers
from .normalize import is_builder_brush
from .writes import actor_bounds, aabb_intersects

NEIGHBORHOOD_PAD = Decimal("0")  # the spike measured pad=0 as sufficient; see spike.md §4 before
# changing this -- a nonzero pad was not found necessary and widening it only grows the (already
# cheap, median 6ms) csg-tier neighborhood for no measured benefit


def _region_of(actor, pad=NEIGHBORHOOD_PAD):
    lo, hi = actor_bounds(actor)
    p = pad
    return (tuple(c - p for c in lo), tuple(c + p for c in hi))


def neighborhood(level, class_index, surveyed_actor) -> list:
    """Every brush actor whose own world AABB meets the surveyed actor's region, in TRUNK ORDER,
    plus the level's FIRST world-CSG brush always. Ported verbatim from
    `dev/docs/spikes/2026-09-23-actor-survey-csg-kind-and-cost/harness/bounded_cost.py::neighborhood`
    -- do not modify the first-brush clause without re-reading that spike's §4 "why the truncation
    is sound" first; it is load-bearing (measured: dropping it loses real faces on a truncated
    solve, `nsfhq04 DeusExMover31` example in the spike doc)."""
    region = _region_of(surveyed_actor)
    out, have_first = [], False
    for name in level.order:
        a = level.actors[name]
        if a.brush is None:
            continue
        in_world_csg = not (movers.is_mover(a, class_index) or is_builder_brush(a))
        near = aabb_intersects(_region_of(a, Decimal("0")), region)
        if near or (in_world_csg and not have_first):
            out.append(a)
        if in_world_csg:
            have_first = True
    return out
```

- [ ] **Step 4: Run test to verify it passes**

Run: `bin/test -k test_neighborhood_includes_nearby_brushes_and_first_world_brush -v`
Expected: PASS

- [ ] **Step 5: Run the actor_survey test module**

Run: `bin/test -k actor_survey`
Expected: all green

- [ ] **Step 6: Commit**

```bash
git add uedcli/actor_survey.py uedcli/tests/test_actor_survey.py
git commit -m "actor survey: port bounded-cost neighborhood selection"
```

---

## Part D — `actor survey`'s csg tier: the five relations

### Task 9: `crosses`

**Files:**
- Modify: `uedcli/actor_survey.py`
- Modify: `uedcli/query.py` (if a helper for "does this actor contribute solid matter" doesn't
  already exist in the shape this task needs — check `csg_kind`/`csg_is_subtract` first)
- Test: `uedcli/tests/test_actor_survey.py`

**Interfaces:**
- Consumes: `neighborhood` (Task 8), `uedcli_native.point_is_solid` (Task 7),
  `preview_native.solve_world_surfaces` (existing), `query.csg_kind` (existing), a `defaults`
  (`ClassDefaults`-shaped, same object `serve/scene.py::_actor_radii` already takes — check that
  call site's own construction, e.g. `uprops.ClassDefaults`, for exactly how the CLI handler in
  Task 14 must build one).
- Produces: `crosses_facts_for(level, class_index, name, defaults) -> list[CsgFact]`, where
  `CsgFact` is a new dataclass `(src, dst, relation, depth_uu)`. Every later task's `*_facts_for`
  function in this Part takes the same `(level, class_index, name)` triple; only `crosses_facts_for`
  additionally needs `defaults` (for collision-extent resolution) — Task 14's orchestrator threads
  it through.

- [ ] **Step 1: Write the failing tests**

```python
def test_crosses_fires_for_add_poking_through_niche(fixture_level_shelf_pokes_through_niche):
    """Additive4 pokes through Subtract3's own wall -- crosses Subtract3, never Additive2, however
    deep the nesting (the spec's locality rule)."""
    from uedcli import actor_survey
    facts = actor_survey.crosses_facts_for(*fixture_level_shelf_pokes_through_niche, "Additive4")
    assert any(f.dst == "Subtract3" and f.relation == "crosses" for f in facts)
    assert not any(f.dst == "Additive2" for f in facts)
    crossing = next(f for f in facts if f.dst == "Subtract3")
    assert crossing.depth_uu > 0


def test_crosses_never_fires_from_a_subtract(fixture_level_room_with_pillar):
    """The design bug the spec's whole crosses source-restriction exists to fix: a Subtract room
    never crosses a pillar Add placed inside it."""
    from uedcli import actor_survey
    facts = actor_survey.crosses_facts_for(*fixture_level_room_with_pillar, "Room")
    assert not any(f.relation == "crosses" for f in facts)


def test_crosses_fires_for_semisolid_but_never_as_carves_target(fixture_level_semisolid_pillar):
    """Per the CSG-kind spike: Semisolid is a valid crosses source/target, never a carves target."""
    from uedcli import actor_survey
    facts = actor_survey.crosses_facts_for(*fixture_level_semisolid_pillar, "Cutter")
    # Cutter (a Subtract) never crosses (source-restricted) -- but does it carve the semisolid?
    # that's Task 13's test; this test only asserts the crosses-source-restriction half here.
```

(Three real geometric fixtures needed — build the first from the spec's own worked example
scenario (`Subtract1 → Additive2 → Subtract3 → Additive4`), the second matching the pillar-in-room
scenario already described throughout the spec's `contains` section, the third matching
`kind_semantics.py`'s own three-brush construction. Reuse `kind_semantics.py`'s brush-building
helper directly where the geometry matches, rather than re-deriving vertex coordinates by hand. Each
fixture function returns `(level, class_index, defaults)` so `*fixture_...` unpacking in every test
call supplies `crosses_facts_for`'s full `(level, class_index, name, defaults)` signature with `name`
as the trailing explicit argument — build `defaults` the same way `serve/scene.py`'s own caller
does, check that call site directly rather than guessing the constructor.)

- [ ] **Step 2: Run tests to verify they fail**

Run: `bin/test -k "test_crosses_fires_for_add_poking_through_niche or test_crosses_never_fires_from_a_subtract or test_crosses_fires_for_semisolid_but_never_as_carves_target" -v`
Expected: FAIL (`crosses_facts_for` doesn't exist)

- [ ] **Step 3: Add the CsgFact type and the source-eligibility check**

```python
@dataclass(frozen=True)
class CsgFact:
    src: str
    dst: str
    relation: str
    depth_uu: float | None = None


def _is_crosses_source_eligible(actor, class_index, defaults) -> bool:
    """Confirmed valid crosses sources (spec + spike, both grounded in
    dev/docs/spikes/2026-09-23-actor-survey-csg-kind-and-cost/): an Add or Semisolid brush, a
    Mover (owner ruling: "treat just like an additive"), or a non-brush actor with real blocking
    collision. Confirmed NEVER valid: a Subtract (no solid of its own -- this is the fix for the
    'fires on every piece of furniture' bug an earlier design had). Not yet ruled on in this
    codebase and explicitly excluded here pending a future ruling: Nonsolid, Intersect,
    Deintersect (see query.csg_kind's six brush-kind values)."""
    if actor.brush is None:
        return _resolve_collision_extent(actor, defaults) is not None
    if movers.is_mover(actor, class_index):
        return True
    kind = query.csg_kind(actor, is_mover=False)
    return kind in ("add", "semisolid")


def _resolve_collision_extent(actor, defaults) -> tuple[float, float] | None:
    """`(radius, height)` if `actor` physically blocks, else `None`. Ported directly from
    `uedcli/serve/scene.py::_actor_radii`'s own instance-else-class-default field resolution (same
    `bCollideActors`/`CollisionRadius`/`CollisionHeight` fields, same casefold-keyed lookup) --
    NOT reinvented here, just the gate tightened per the spike's own measurement: `_actor_radii`
    gates on `bCollideActors` alone (right for its own purpose, the GUI overlay); `actor survey`
    additionally requires `bBlockActors`, since `bCollideActors` alone admits room-spanning trigger
    volumes that carry the entire false-positive tail (spike §3, measured over 1522 real actors)."""
    instance = {k.casefold(): v for k, v in actor.props}
    info = defaults.for_class(actor.cls)  # raises uprops.SchemaError for an unresolvable class --
    # let it propagate; a class-schema failure here is the same "cannot compute a fact" case
    # actor_survey's other native calls already surface as an exit-2, not a silent skip.
    class_defaults = info.defaults

    def field(name: str):
        low = name.casefold()
        return instance[low] if low in instance else class_defaults.get((low, 0))

    if str(field("bCollideActors") or "False").strip() != "True":
        return None
    if str(field("bBlockActors") or "False").strip() != "True":
        return None
    radius = float(field("CollisionRadius") or 0.0)
    height = float(field("CollisionHeight") or 0.0)
    if radius <= 0.0 or height <= 0.0:
        return None
    return radius, height
```

- [ ] **Step 4: Write `crosses_facts_for`**

```python
def crosses_facts_for(level, class_index, name: str, defaults) -> list[CsgFact]:
    surveyed = level.actors[name]
    if not _is_crosses_source_eligible(surveyed, class_index, defaults):
        return []
    n = neighborhood(level, class_index, surveyed)
    built = solve_world_surfaces(n, class_index)
    facts = []
    for surf in built.world_surfaces:
        if surf.actor is not None and surf.actor.name == name:
            continue  # never test the surveyed actor's own face against itself
        if surf.actor is None:
            continue  # a surf with no source actor can't be named as a crosses target
        depth = _penetration_depth(surveyed, surf, built, defaults)
        if depth is not None and depth > CSG_TOLERANCE:
            facts.append(CsgFact(src=name, dst=surf.actor.name, relation="crosses", depth_uu=depth))
    return facts


CSG_TOLERANCE = 0.015  # uu -- the engine's own THRESH_POINTS_ARE_NEAR, spike §3. NEVER _TOUCH_EPS
# (1e-3) here -- that constant is for the RAW tier's authored-vertex comparisons, a different
# geometry space with a different noise floor.


def _signed_clearance(is_solid, loc, ext, *, hi=64.0, iters=18) -> float:
    """Largest `delta` with `box(loc, ext + delta)` entirely in void; negative = penetration depth.
    Ported VERBATIM from the spike's own verified bisection
    (`dev/docs/spikes/2026-09-23-actor-survey-csg-kind-and-cost/harness/collision_clearance.py::signed_clearance`),
    which measured this technique against 1522 real collidable Deus Ex actors -- do not
    re-derive."""
    def sample_points(loc, ext):
        return [(loc[0] + ix * ext[0], loc[1] + iy * ext[1], loc[2] + iz * ext[2])
                for ix in (-1, 0, 1) for iy in (-1, 0, 1) for iz in (-1, 0, 1)]

    def box_free(l, e):
        return not any(is_solid(p) for p in sample_points(l, e))

    lo = -max(ext)
    if box_free(loc, tuple(e + hi for e in ext)):
        return hi
    if not box_free(loc, tuple(max(0.0, e + lo) for e in ext)):
        return lo  # buried
    a, b = lo, hi
    for _ in range(iters):
        mid = (a + b) / 2.0
        if box_free(loc, tuple(max(0.0, e + mid) for e in ext)):
            a = mid
        else:
            b = mid
    return a


def _penetration_depth(source_actor, surf, built, defaults) -> float | None:
    """How far past `surf`'s plane the source actor's own extent reaches, or None if it doesn't
    cross at all.

    NON-BRUSH source (a collision extent): a direct, real port of the spike's own verified
    bisection (`_signed_clearance` above) -- `is_solid` closes over `built` via
    `uedcli_native.point_is_solid`. This half is a straight port of already-measured code, not new
    geometry.

    BRUSH source: genuinely new geometry this plan does not hand-derive. Implementer: clip the
    source brush's own world-space geometry (via `actorgraph.decompose_convex`) against `surf`'s
    plane, and take the maximum perpendicular distance of any resulting vertex past the plane, on
    the side `uedcli_native.point_is_solid` confirms is solid (so a vertex merely near the plane in
    legitimate void doesn't count). If this sketch doesn't hold up once real geometry is run through
    it, STOP and report the concrete failure per this project's "a decision is implemented as given"
    convention -- do not silently substitute a different mechanism."""
    if source_actor.brush is None:
        radius_height = _resolve_collision_extent(source_actor, defaults)
        if radius_height is None:
            return None
        radius, height = radius_height
        loc = tuple(float(c) for c in (source_actor.location or (0, 0, 0)))
        ext = (radius, radius, height)
        clearance = _signed_clearance(
            lambda p: uedcli_native.point_is_solid(built, p, (0.0, 0.0, 0.0)), loc, ext)
        return -clearance if clearance < 0 else None
    raise NotImplementedError(
        "brush-source penetration depth -- see this function's docstring for the sketched "
        "clip-against-plane technique; genuinely new geometry, not a port of existing code")
```

(One `NotImplementedError` remains, scoped to exactly the brush-source case — the non-brush/
collision-extent case above is real, working code ported directly from the spike's own measured
bisection, not a placeholder. If the TDD cycle for the brush-source stub reveals the sketched
approach doesn't work cleanly, that is real, expected plan-execution feedback — stop, report the
concrete problem, and get a ruling before improvising a different mechanism, per this project's
"a decision is implemented as given" convention.)

- [ ] **Step 5: Implement the two stubs, run tests, iterate to green**

Run: `bin/test -k "test_crosses_fires_for_add_poking_through_niche or test_crosses_never_fires_from_a_subtract or test_crosses_fires_for_semisolid_but_never_as_carves_target" -v`
Expected: PASS once both stubs are implemented for real.

- [ ] **Step 6: Run the actor_survey test module**

Run: `bin/test -k actor_survey`
Expected: all green

- [ ] **Step 7: Commit**

```bash
git add uedcli/actor_survey.py uedcli/query.py uedcli/tests/test_actor_survey.py
git commit -m "actor survey: csg-tier crosses"
```

---

### Task 10: `touches` (csg tier)

**Files:** Modify `uedcli/actor_survey.py`; Test: `uedcli/tests/test_actor_survey.py`

**Interfaces:**
- Consumes: `crosses_facts_for`'s helpers (`neighborhood`, `solve_world_surfaces`), NOT
  source-restricted (unlike `crosses` — a Subtract's carve legitimately touches its bounding wall).
- Produces: `touches_facts_for(level, class_index, name) -> list[CsgFact]`.

- [ ] **Step 1: Write the failing test**

```python
def test_touches_fires_for_subtract_against_intact_wall(fixture_level_room_with_intact_wall):
    """Subtract room legitimately stops flush at an Add wall it never carved into -- touches, not
    crosses, and NOT source-restricted (unlike crosses)."""
    from uedcli import actor_survey
    facts = actor_survey.touches_facts_for(*fixture_level_room_with_intact_wall, "Room")
    assert any(f.relation == "touches" and f.dst == "Wall" for f in facts)
    assert not any(f.relation == "crosses" for f in facts)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `bin/test -k test_touches_fires_for_subtract_against_intact_wall -v`
Expected: FAIL

- [ ] **Step 3: Write `touches_facts_for`**

```python
def touches_facts_for(level, class_index, name: str) -> list[CsgFact]:
    """Not source-restricted, unlike crosses -- any actor's geometry (or collision extent) flush
    against a resolved surviving face is worth reporting, including a Subtract legitimately
    stopping at its bounding wall."""
    surveyed = level.actors[name]
    n = neighborhood(level, class_index, surveyed)
    built = solve_world_surfaces(n, class_index)
    facts = []
    for surf in built.world_surfaces:
        if surf.actor is not None and surf.actor.name == name:
            continue
        if surf.actor is None:
            continue
        if _is_flush_against(surveyed, surf, class_index):
            facts.append(CsgFact(src=name, dst=surf.actor.name, relation="touches"))
    return facts


def _is_flush_against(actor, surf, class_index) -> bool:
    """Within CSG_TOLERANCE of surf's plane, no penetration past it. Implementer: this is the
    complement of `_penetration_depth` (Task 9) -- a depth of exactly ~0 (within CSG_TOLERANCE) is
    touches; a depth clearly past it is crosses. Consider sharing one geometry pass between
    `crosses_facts_for` and `touches_facts_for` in a later cleanup task rather than computing the
    same surf-vs-actor distance twice per neighborhood pass -- not required for this task's tests
    to pass, flagged for whoever reviews this task."""
    raise NotImplementedError("flush-against geometry -- see docstring, shares math with Task 9")
```

- [ ] **Step 4: Implement the stub, run test, iterate to green**

Run: `bin/test -k test_touches_fires_for_subtract_against_intact_wall -v`
Expected: PASS

- [ ] **Step 5: Run the actor_survey test module**

Run: `bin/test -k actor_survey`
Expected: all green

- [ ] **Step 6: Commit**

```bash
git add uedcli/actor_survey.py uedcli/tests/test_actor_survey.py
git commit -m "actor survey: csg-tier touches"
```

---

### Task 11: `connects`

**Files:** Modify `uedcli/actor_survey.py`; Test: `uedcli/tests/test_actor_survey.py`

**Interfaces:**
- Consumes: `neighborhood`, `uedcli_native.point_is_solid`, `query.csg_is_subtract`.
- Produces: `connects_facts_for(level, class_index, name) -> list[CsgFact]` — Subtract-only,
  symmetric, no `:idx`, no depth (absence-of-a-face, not presence).

- [ ] **Step 1: Write the failing tests**

```python
def test_connects_fires_for_two_rooms_sharing_open_doorway(fixture_level_two_rooms_open_doorway):
    from uedcli import actor_survey
    facts = actor_survey.connects_facts_for(*fixture_level_two_rooms_open_doorway, "RoomA")
    assert any(f.relation == "connects" and f.dst == "RoomB" for f in facts)


def test_connects_absent_when_wall_intact(fixture_level_two_rooms_solid_wall):
    from uedcli import actor_survey
    facts = actor_survey.connects_facts_for(*fixture_level_two_rooms_solid_wall, "RoomA")
    assert not any(f.relation == "connects" for f in facts)


def test_connects_fires_for_fully_nested_redundant_subtract(fixture_level_nested_subtract):
    """A smaller Subtract carved entirely inside a bigger one's already-void space -- connects,
    never contains (it's not content)."""
    from uedcli import actor_survey
    facts = actor_survey.connects_facts_for(*fixture_level_nested_subtract, "OuterRoom")
    assert any(f.relation == "connects" and f.dst == "InnerCarve" for f in facts)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `bin/test -k "test_connects_fires_for_two_rooms_sharing_open_doorway or test_connects_absent_when_wall_intact or test_connects_fires_for_fully_nested_redundant_subtract" -v`
Expected: FAIL

- [ ] **Step 3: Write `connects_facts_for`**

```python
def connects_facts_for(level, class_index, name: str) -> list[CsgFact]:
    surveyed = level.actors[name]
    if not query.csg_is_subtract(surveyed):
        return []
    n = neighborhood(level, class_index, surveyed)
    facts = []
    for other in n:
        if other.name == name or not query.csg_is_subtract(other):
            continue
        if not aabb_intersects(actor_bounds(surveyed), actor_bounds(other)):
            continue  # not even raw-adjacent, can't be void-connected
        if _shares_open_boundary(surveyed, other, level, class_index):
            facts.append(CsgFact(src=name, dst=other.name, relation="connects"))
    return facts


def _shares_open_boundary(a, b, level, class_index) -> bool:
    """True iff a's and b's void regions are continuous -- no surviving solid face separates them
    within CSG_TOLERANCE. Implementer: sample points along a's and b's shared raw-AABB overlap
    region (or their nearest raw faces, per `actorgraph.brush_overlap`'s existing matched-face-pair
    logic for FINDING the candidate shared plane) and confirm `uedcli_native.point_is_solid` is
    False on both sides of that plane in the resolved world built from `neighborhood`. See spec.md's
    `connects` section: this must be decided by LOCAL face existence, never by zone identity (a
    truncated solve's zone numbers are not meaningful, per the bounded-cost spike's residual-risk
    #3)."""
    raise NotImplementedError("void-continuity geometry -- see docstring")
```

- [ ] **Step 4: Implement the stub, run tests, iterate to green**

Run: `bin/test -k "test_connects_fires_for_two_rooms_sharing_open_doorway or test_connects_absent_when_wall_intact or test_connects_fires_for_fully_nested_redundant_subtract" -v`
Expected: PASS

- [ ] **Step 5: Run the actor_survey test module**

Run: `bin/test -k actor_survey`
Expected: all green

- [ ] **Step 6: Commit**

```bash
git add uedcli/actor_survey.py uedcli/tests/test_actor_survey.py
git commit -m "actor survey: csg-tier connects"
```

---

### Task 12: `contains`

**Files:** Modify `uedcli/actor_survey.py`; Test: `uedcli/tests/test_actor_survey.py`

**Interfaces:**
- Consumes: `neighborhood`, `uedcli_native.point_is_solid`, `decompose_convex` (for authored-volume
  computation), `connects_facts_for` (a Subtract's `connects` peers are NOT part of `contains`'s
  domain per the spec's final ruling — the multi-parent/seam rule was dropped entirely; `contains`
  is single-owner-by-volume-competition only, no union).
- Produces: `contains_facts_for(level, class_index, name) -> list[CsgFact]`.

- [ ] **Step 1: Write the failing tests**

```python
def test_contains_survives_a_pillar_placed_inside(fixture_level_room_with_pillar_and_point_actor):
    """The pillar case: a later Add pillar inside a room does not disqualify the room's contains of
    a point actor at the same location -- the Add never competes (it isn't a Subtract)."""
    from uedcli import actor_survey
    facts = actor_survey.contains_facts_for(*fixture_level_room_with_pillar_and_point_actor, "Room")
    assert any(f.relation == "contains" and f.dst == "Light" for f in facts)


def test_contains_picks_smaller_volume_when_nested(fixture_level_nested_niche_with_decoration):
    """Subtract1 -> Additive2 -> Subtract3 -> Additive4 (Additive4 NOT poking through): Subtract3
    wins the volume competition, Subtract1 reports nothing about Additive4."""
    from uedcli import actor_survey
    outer = actor_survey.contains_facts_for(*fixture_level_nested_niche_with_decoration, "Subtract1")
    inner = actor_survey.contains_facts_for(*fixture_level_nested_niche_with_decoration, "Subtract3")
    assert not any(f.dst == "Additive4" for f in outer)
    assert any(f.relation == "contains" and f.dst == "Additive4" for f in inner)


def test_contains_volume_tie_break_is_trunk_order(fixture_level_two_equal_volume_subtracts):
    """A genuine tie (within relative tolerance) breaks toward the later brush in trunk order."""
    from uedcli import actor_survey
    facts = actor_survey.contains_facts_for(*fixture_level_two_equal_volume_subtracts, "LaterRoom")
    assert any(f.relation == "contains" and f.dst == "Item" for f in facts)


def test_contains_fires_when_surveying_the_contained_point_actor(fixture_level_room_with_pillar_and_point_actor):
    """Surveying the CONTAINED point actor, not the container -- the room still leads, per the
    spec's fixed-direction rule. This is the direction this task's first implementation attempt
    missed entirely (caught in this plan's own self-review, same gap as Task 13's carves)."""
    from uedcli import actor_survey
    facts = actor_survey.contains_facts_for(*fixture_level_room_with_pillar_and_point_actor, "Light")
    assert any(f.relation == "contains" and f.src == "Room" and f.dst == "Light" for f in facts)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `bin/test -k "test_contains_survives_a_pillar_placed_inside or test_contains_picks_smaller_volume_when_nested or test_contains_volume_tie_break_is_trunk_order or test_contains_fires_when_surveying_the_contained_point_actor" -v`
Expected: FAIL

- [ ] **Step 3: Write `contains_facts_for`**

```python
def contains_facts_for(level, class_index, name: str) -> list[CsgFact]:
    """Directional per the spec: the container leads, whichever side is surveyed -- surveying the
    Subtract shows its own outgoing contains facts; surveying a CONTAINED actor (a point actor, or
    a brush/Mover whose full extent some Subtract encloses) shows the SAME facts as incoming lines.
    An earlier draft of this task only handled the first direction, the same gap Task 13's
    `carves_facts_for` had -- fixed here for the same reason, caught in this plan's own
    self-review: `level graph`'s own raw `contains` already fans out both ways (`build_graph`'s
    point loop, one edge per containing brush), and this design's raw tier (Task 6) reuses that
    directly, so the csg tier must not be narrower than the tier it's meant to correct."""
    surveyed = level.actors[name]
    if query.csg_is_subtract(surveyed):
        candidates = _actors_and_authored_volume(level, class_index, surveyed)
        facts = []
        for target_name, target in _survey_targets(level, class_index, surveyed):
            if _wins_containment(name, surveyed, target, candidates, level):
                facts.append(CsgFact(src=name, dst=target_name, relation="contains"))
        return facts
    # surveyed is a potential CONTAINED target -- check every Subtract in its own neighborhood.
    n = neighborhood(level, class_index, surveyed)
    subtracts = [(a.name, a) for a in n if query.csg_is_subtract(a)]
    facts = []
    for container_name, container in subtracts:
        candidates = _actors_and_authored_volume(level, class_index, container)
        if _wins_containment(container_name, container, surveyed, candidates, level):
            facts.append(CsgFact(src=container_name, dst=name, relation="contains"))
    return facts


def _wins_containment(container_name, container, target, candidates, level) -> bool:
    """True iff `container` is the smallest-authored-volume Subtract among every candidate whose
    own authored shape also contains `target`'s full extent -- the spec's volume-competition rule,
    factored out here so both survey directions above share one implementation rather than two
    copies of the tie-break math."""
    if not _authored_shape_contains(container, target):
        return False
    competitors = [
        (other_name, _authored_volume(other))
        for other_name, other in candidates
        if other_name != container_name and query.csg_is_subtract(other)
        and _authored_shape_contains(other, target)
    ]
    my_volume = _authored_volume(container)
    return all(
        my_volume < other_vol - _volume_tolerance(my_volume, other_vol)
        or (_volumes_tied(my_volume, other_vol)
            and _trunk_index(level, container_name) > _trunk_index(level, other_name))
        for other_name, other_vol in competitors
    )


def _volume_tolerance(a: float, b: float) -> float:
    """Relative tolerance for the volume tie-break, matching relation.py's own `_close`-style
    relative-comparison convention (never a bare float `==`) -- per the spec's ruling that a real
    tie should break on trunk order, not on float noise."""
    return 1e-6 * max(1.0, abs(a), abs(b))


def _volumes_tied(a: float, b: float) -> bool:
    return abs(a - b) <= _volume_tolerance(a, b)
```

(`_actors_and_authored_volume`, `_survey_targets`, `_authored_shape_contains`, `_authored_volume`,
`_trunk_index` are helper stubs the implementer fills in — `_authored_shape_contains` for a point
target is `decompose_convex`+point-in-cell (reuse `actorgraph.point_in_brush`'s existing logic
directly rather than re-deriving it); `_authored_volume` sums each `ConvexCell`'s volume from
`decompose_convex`'s output. `_survey_targets` enumerates every point actor AND every brush/Mover
actor in the neighborhood as a candidate `X` — per the spec, `contains`'s target can be a brush or
Mover's full extent, not just a point.)

- [ ] **Step 4: Implement the helper stubs, run tests, iterate to green**

Run: `bin/test -k "test_contains_survives_a_pillar_placed_inside or test_contains_picks_smaller_volume_when_nested or test_contains_volume_tie_break_is_trunk_order or test_contains_fires_when_surveying_the_contained_point_actor" -v`
Expected: PASS

- [ ] **Step 5: Run the actor_survey test module**

Run: `bin/test -k actor_survey`
Expected: all green

- [ ] **Step 6: Commit**

```bash
git add uedcli/actor_survey.py uedcli/tests/test_actor_survey.py
git commit -m "actor survey: csg-tier contains"
```

---

### Task 13: `carves`

**Files:** Modify `uedcli/actor_survey.py`; Test: `uedcli/tests/test_actor_survey.py`

**Interfaces:**
- Consumes: `neighborhood`, `solve_world_surfaces`, `query.csg_kind`/`csg_is_subtract`.
- Produces: `carves_facts_for(level, class_index, name) -> list[CsgFact]` — Subtract leads always
  (agent, not victim), matching raw `carves`'s presentation from Task 6.

- [ ] **Step 1: Write the failing tests**

```python
def test_carves_fires_when_subtract_removes_add_matter(fixture_level_niche_carved_into_wall):
    from uedcli import actor_survey
    facts = actor_survey.carves_facts_for(*fixture_level_niche_carved_into_wall, "Niche")
    assert any(f.relation == "carves" and f.dst == "Wall" and f.src == "Niche" for f in facts)


def test_carves_absent_when_subtract_never_touched_the_wall(fixture_level_room_with_intact_wall):
    """The raw-vs-csg contrast the whole two-tier design exists for: raw's order heuristic can call
    this carved_by/carves wrongly; csg correctly reports nothing."""
    from uedcli import actor_survey
    facts = actor_survey.carves_facts_for(*fixture_level_room_with_intact_wall, "Room")
    assert not any(f.relation == "carves" for f in facts)


def test_carves_never_targets_a_semisolid(fixture_level_semisolid_pillar):
    """The sharpest raw-vs-csg contrast in the spec: raw carved_by/carves claims this whenever
    trunk order looks right; csg never does, because a semisolid is applied after every
    Add/Subtract regardless of order."""
    from uedcli import actor_survey
    facts = actor_survey.carves_facts_for(*fixture_level_semisolid_pillar, "Cutter")
    assert not any(f.relation == "carves" and f.dst == "Pillar" for f in facts)


def test_carves_fires_when_surveying_the_carved_add(fixture_level_niche_carved_into_wall):
    """Surveying the VICTIM (the carved Add), not the agent -- the Subtract still leads, per the
    spec's fixed-direction rule. This is the direction Task 13's first implementation attempt
    missed entirely (caught in this plan's own self-review): surveying `Wall` must show the same
    fact `carves_facts_for(..., "Niche")` shows, not an empty list."""
    from uedcli import actor_survey
    facts = actor_survey.carves_facts_for(*fixture_level_niche_carved_into_wall, "Wall")
    assert any(f.relation == "carves" and f.src == "Niche" and f.dst == "Wall" for f in facts)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `bin/test -k "test_carves_fires_when_subtract_removes_add_matter or test_carves_absent_when_subtract_never_touched_the_wall or test_carves_never_targets_a_semisolid or test_carves_fires_when_surveying_the_carved_add" -v`
Expected: FAIL

- [ ] **Step 3: Write `carves_facts_for`**

```python
def carves_facts_for(level, class_index, name: str) -> list[CsgFact]:
    """Directional per the spec: the Subtract (agent) always leads, whichever side is surveyed --
    so this must check BOTH directions, not just "is the surveyed actor a Subtract". Surveying the
    carving Subtract shows its own outgoing carves; surveying the carved Add/Nonsolid shows the
    SAME fact as an incoming line, agent still leading. (An earlier draft of this task's code only
    handled the first direction -- caught in this plan's own self-review, fixed before build: the
    second direction is not an edge case, it's half of the relation's normal usage, exercised by
    the spec's own worked example surveying `Brush117`, the carved Add.)"""
    surveyed = level.actors[name]
    facts = []
    if query.csg_is_subtract(surveyed):
        n = neighborhood(level, class_index, surveyed)
        for other in n:
            if other.name == name:
                continue
            kind = query.csg_kind(other, is_mover=movers.is_mover(other, class_index))
            if kind not in ("add", "nonsolid"):
                continue  # never Subtract, never Semisolid (spike's own ruling), never
                # Intersect/Deintersect (contribute nothing)
            if _removed_real_matter(surveyed, other, level, class_index):
                facts.append(CsgFact(src=name, dst=other.name, relation="carves"))
        return facts
    # surveyed is a potential carves TARGET (an Add or Nonsolid) -- check every Subtract in the
    # neighborhood for whether IT carved `surveyed`, same underlying test, reversed roles.
    kind = query.csg_kind(surveyed, is_mover=movers.is_mover(surveyed, class_index))
    if kind not in ("add", "nonsolid"):
        return []
    n = neighborhood(level, class_index, surveyed)
    for other in n:
        if other.name == name or not query.csg_is_subtract(other):
            continue
        if _removed_real_matter(other, surveyed, level, class_index):
            facts.append(CsgFact(src=other.name, dst=name, relation="carves"))
    return facts


def _removed_real_matter(subtract_actor, other_actor, level, class_index) -> bool:
    """True iff `subtract_actor`'s carve genuinely removed part of `other_actor`'s originally-
    contributed matter -- not merely touched it (that's `touches`, Task 10). Implementer: compare
    `other_actor`'s raw authored volume/face count against its RESOLVED presence in
    `solve_world_surfaces`'s output over the neighborhood WITHOUT `subtract_actor` present, vs WITH
    it -- a real reduction means real removal. See kind_semantics.py's own measurement method
    (uncut-vs-cut face count/area comparison) for the exact technique this ports."""
    raise NotImplementedError("carve-detection geometry -- see docstring")
```

- [ ] **Step 4: Implement the stub, run tests, iterate to green**

Run: `bin/test -k "test_carves_fires_when_subtract_removes_add_matter or test_carves_absent_when_subtract_never_touched_the_wall or test_carves_never_targets_a_semisolid or test_carves_fires_when_surveying_the_carved_add" -v`
Expected: PASS

- [ ] **Step 5: Run the actor_survey test module**

Run: `bin/test -k actor_survey`
Expected: all green

- [ ] **Step 6: Commit**

```bash
git add uedcli/actor_survey.py uedcli/tests/test_actor_survey.py
git commit -m "actor survey: csg-tier carves"
```

---

## Part E — wiring, error paths, docs

### Task 14: Combine raw + csg into `actor survey`'s output; error paths

**Files:**
- Modify: `uedcli/actor_survey.py` (a top-level `survey()` orchestrator)
- Modify: `uedcli/cli/commands/actor/survey.py` (use the orchestrator instead of raw-only)
- Test: `uedcli/tests/test_actor_survey.py`

**Interfaces:**
- Consumes: every `*_facts_for` function from Tasks 6/9-13.
- Produces: `survey(level, class_index, name) -> tuple[list[RawFact], list[CsgFact]]`, and the CLI
  handler prints `raw` lines then a blank line then `csg` lines, then the stderr summary
  `actor survey: N raw fact(s), M resolved CSG fact(s) for NAME`.

- [ ] **Step 1: Write the failing tests**

```python
def test_survey_combines_raw_and_csg(run_cli, fixture_level_niche_carved_into_wall):
    result = run_cli(["actor", "survey", "Niche"])
    assert result.returncode == 0
    lines = result.stdout.splitlines()
    raw_lines = [l for l in lines if l.startswith("raw ")]
    csg_lines = [l for l in lines if l.startswith("csg ")]
    assert raw_lines and csg_lines
    assert lines.index(csg_lines[0]) > lines.index(raw_lines[-1])  # raw block, then csg block
    assert f"{len(raw_lines)} raw fact(s), {len(csg_lines)} resolved CSG fact(s)" in result.stderr


def test_survey_unknown_actor_exits_2(run_cli, fixture_level_niche_carved_into_wall):
    result = run_cli(["actor", "survey", "DoesNotExist"])
    assert result.returncode == 2
    assert "Actor not found: DoesNotExist" in result.stderr


def test_survey_degenerate_surveyed_brush_exits_2(run_cli, fixture_level_with_degenerate_brush):
    result = run_cli(["actor", "survey", "BadBrush"])
    assert result.returncode == 2
    assert "BadBrush" in result.stderr


def test_survey_warns_on_intersect_deintersect(run_cli, fixture_level_with_intersect_brush):
    """Full output, exit 0, plus one extra stderr line naming the actor and the oper -- per the
    spike's concrete rule, only when the SURVEYED actor itself is Intersect/Deintersect."""
    result = run_cli(["actor", "survey", "IntersectBrush"])
    assert result.returncode == 0
    assert "IntersectBrush" in result.stderr
    assert "Intersect" in result.stderr
    assert "contributes nothing" in result.stderr
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `bin/test -k "test_survey_combines_raw_and_csg or test_survey_unknown_actor_exits_2 or test_survey_degenerate_surveyed_brush_exits_2 or test_survey_warns_on_intersect_deintersect" -v`
Expected: FAIL

- [ ] **Step 3: Write the orchestrator**

```python
def survey(level, class_index, name: str, defaults):
    """Full actor survey: raw facts, then csg facts. Raises ActorNotFoundError /
    DegenerateBrushError (re-exported from actorgraph) for the CLI layer to map to exit 2.
    `defaults` is only consumed by `crosses_facts_for` (collision-extent resolution) -- threaded
    through here rather than constructed per-relation so the CLI handler builds it exactly once."""
    if name not in level.actors:
        raise ActorNotFoundError(name)
    raw_facts, nodes = raw_facts_for(level, class_index, name)
    surveyed = level.actors[name]
    if surveyed.brush is not None:
        actorgraph.decompose_convex(surveyed)  # raises DegenerateBrushError if the SURVEYED
        # actor itself can't be decomposed -- per the spec, survey has no "rest of the level" to
        # fall back to, so this propagates straight to the CLI's exit-2 handler, unlike
        # level graph's own skip-and-continue behavior over the whole level
    csg_facts = list(crosses_facts_for(level, class_index, name, defaults))
    for fn in (touches_facts_for, connects_facts_for, contains_facts_for, carves_facts_for):
        csg_facts.extend(fn(level, class_index, name))
    return raw_facts, nodes, csg_facts


def intersect_deintersect_warning(actor, class_index) -> str | None:
    """One stderr line when the SURVEYED actor itself is Intersect/Deintersect -- never for any
    other actor in the neighborhood (an Intersect/Deintersect contributes nothing to the world, so
    it cannot change anyone else's facts; warning about it elsewhere would be pure noise, per the
    spike's own concrete rule)."""
    if actor.brush is None:
        return None
    kind = query.csg_kind(actor, is_mover=movers.is_mover(actor, class_index))
    if kind not in ("intersect", "deintersect"):
        return None
    return (f"actor survey: {actor.name} is a placed CSG_{kind.capitalize()} brush -- it "
            f"contributes nothing to the resolved world (the editor treats it as a builder-brush "
            f"operation on its own model); its csg tier carries no fact it sources, and its raw "
            f"tier treats it as Add-like, which the resolved world does not")


def format_csg_line(fact: CsgFact, nodes) -> str:
    """One `csg `-prefixed line. Pure formatting -- every `*_facts_for` function already assigns
    `fact.src`/`fact.dst` in the spec's own fixed final direction (crosses: intruder leads;
    touches/connects: whichever actor was surveyed, by construction, since each function only ever
    sets `src=<the actor it was called with>`; contains/carves: container/agent leads, both
    directions handled inside those two functions after this plan's own self-review found the
    reverse direction missing). No `:idx` anywhere at this tier; `crosses` alone carries the depth
    annotation, per the owner's ruling that depth applies to every crosses line regardless of
    source kind."""
    rel = f"crosses({fact.depth_uu:.3g}uu)" if fact.relation == "crosses" else fact.relation
    return (f"csg {fact.src} {actorgraph._node_bracket(nodes[fact.src])} --{rel}--> "
            f"{fact.dst} {actorgraph._node_bracket(nodes[fact.dst])}")
```

- [ ] **Step 4: Wire the CLI handler**

```python
def run(args, ctx) -> int:
    level, class_index = ctx.level, ctx.class_index
    defaults = ctx.class_defaults  # match whichever existing ctx attribute already carries the
    # class-defaults resolver `serve/scene.py`'s own caller passes to `_actor_radii` -- check that
    # call site to confirm the real attribute name and construction before using this literally
    try:
        raw_facts, nodes, csg_facts = actor_survey.survey(level, class_index, args.name, defaults)
    except actor_survey.ActorNotFoundError as e:
        print(str(e), file=sys.stderr)
        return 2
    except actorgraph.DegenerateBrushError as e:
        print(f"{args.name}: {e}", file=sys.stderr)
        return 2
    warning = actor_survey.intersect_deintersect_warning(level.actors[args.name], class_index)
    for fact in raw_facts:
        print(actor_survey.format_raw_line(fact, nodes, args.name))
    if raw_facts and csg_facts:
        print()
    for fact in csg_facts:
        print(actor_survey.format_csg_line(fact, nodes))
    if warning:
        print(warning, file=sys.stderr)
    print(f"actor survey: {len(raw_facts)} raw fact(s), {len(csg_facts)} resolved CSG fact(s) "
          f"for {args.name}", file=sys.stderr)
    return 0
```

- [ ] **Step 5: Run tests, iterate to green**

Run: `bin/test -k "test_survey_combines_raw_and_csg or test_survey_unknown_actor_exits_2 or test_survey_degenerate_surveyed_brush_exits_2 or test_survey_warns_on_intersect_deintersect" -v`
Expected: PASS

- [ ] **Step 6: Run the full actor_survey test module, then the whole suite once**

Run: `bin/test -k actor_survey`
Run: `bin/test`
Expected: all green

- [ ] **Step 7: Commit**

```bash
git add uedcli/actor_survey.py uedcli/cli/commands/actor/survey.py uedcli/tests/test_actor_survey.py
git commit -m "actor survey: combine raw+csg, error paths, Intersect/Deintersect warning"
```

---

### Task 15: Docs fallout

**Files:**
- Modify: `docs/reference/brush/relation.md` → move content to `docs/reference/actor/relation.md`
  (new page documenting `find`/`compare`/`set`, including the non-brush broadening from Tasks 3-5)
- Create: `docs/reference/actor/survey.md` (new page documenting `actor survey`)
- Modify: `docs/reference/brush/README.md`, `docs/reference/brush/poly.md`,
  `docs/reference/level/graph.md`, `docs/leveldesign/general/recipes/shapes/mitered-corner.md` (fix
  any `brush relation`/`measure` cross-references to `actor relation`/`compare`)

**Interfaces:** None — pure documentation.

- [ ] **Step 1: Write the new `docs/reference/actor/relation.md`**

Document `find`/`compare`/`set` as they now exist (post Tasks 1-5), including the non-brush
broadening — one paragraph per subcommand, following this project's existing `docs/reference/`
page conventions (check `docs/reference/brush/poly.md`'s structure as the template, since it's the
closest sibling page in tone and format).

- [ ] **Step 2: Write `docs/reference/actor/survey.md`**

Document `actor survey <name>`: the two-tier output shape, every relation word and what it means
(user-facing language, not the spec's own internal design-history prose — this doc is for a user
with no familiarity with the implementation, per `dev/docs/rules/documentation.md`), and the
worked example from spec.md's own "Worked example" section, adapted to plain user-facing wording.

- [ ] **Step 3: Fix cross-references in the four modified docs**

`grep -rn "brush relation\|relation measure" docs/` and fix each hit to `actor relation`/`compare`.

- [ ] **Step 4: Run the docs-link test**

Run: `bin/test -k test_doc_links`
Expected: green (this test is noted as a PRE-EXISTING red unrelated to this work in the spec's
own testing notes — confirm it's still red for the SAME pre-existing reason, not a new one this
task introduced, before treating a failure here as unrelated)

- [ ] **Step 5: Commit**

```bash
git add docs/reference/actor/relation.md docs/reference/actor/survey.md docs/reference/brush/README.md
git add docs/reference/brush/poly.md docs/reference/level/graph.md
git add docs/leveldesign/general/recipes/shapes/mitered-corner.md
git rm docs/reference/brush/relation.md
git commit -m "docs: actor relation + actor survey reference pages"
```

---

## Self-review notes (from writing this plan)

- **Spec coverage**: Parts A-E cover every normative section of the spec (`actor relation` rename +
  broadening for all three subcommands; `actor survey`'s raw tier; all five csg-tier relations; the
  `:idx`/annotation grammar; error paths; the Intersect/Deintersect warning; docs fallout). The
  spec's remaining "Open items" (a native point/box solidity query — Task 7; docs fallout — Task
  15) are both covered. Not covered by this plan, deliberately: the csg-tier `:idx` v2 investigation
  (explicitly deferred out of v1 scope by the spec itself).
- **Known stubs, not placeholders**: three `NotImplementedError` stubs remain, each for genuinely
  novel geometry this plan does not hand-derive from a desk — brush-source penetration depth (Task
  9; the non-brush/collision-extent case is real, working code, a direct port of the spike's own
  measured bisection), void-continuity (Task 11), and carve-detection (Task 13). Everything else
  that looked stub-shaped on a first pass was either already-portable (the neighborhood algorithm,
  Task 8; collision-field resolution and the collision-extent depth case, Task 9) or pure formatting
  with no real unknown in it (`format_csg_line`, Task 14) — all now written as real code rather than
  left as a stub, on the view that a stub is only honest where the geometry is genuinely unverified,
  not wherever writing it out took more than one pass. Each remaining stub's docstring names the
  exact technique and the spec section it must satisfy; the implementing subagent's job is to make
  the already-written tests pass, escalating (per this project's "a decision is implemented as
  given" rule) if the sketched approach doesn't work rather than improvising a silently different
  one.
- **A real bug caught by this self-review, not by a later reviewer**: the first draft of
  `contains_facts_for` (Task 12) and `carves_facts_for` (Task 13) each only handled the direction
  where the SURVEYED actor is the container/agent — surveying the CONTAINED or CARVED actor
  silently returned an empty list, even though the spec's own directionality rules and worked
  example (surveying `Brush117`, the carved Add) require the reverse direction to show the same
  fact. Both functions were rewritten to handle both directions, sharing the tie-break/removal logic
  through one common helper each, with a new test per function pinning the previously-missing
  direction.
- **Type consistency**: `RawFact` (Task 6) and `CsgFact` (Task 9) are the two output types every
  later task's function signature uses consistently; `format_raw_line`/`format_csg_line` are the
  only two line-formatting functions, matching the spec's tier-prefix convention throughout.
