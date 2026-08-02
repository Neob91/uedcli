# Plan — `actor find --overlapping-bbox`

Build in a worktree (`andrzej/p3/actor-find-overlapping-bbox`). One merged commit. All slices are
model-side; no editor.

## Slice 1 — `writes.aabb_intersects`

Add beside `aabb_within` (`uedcli/writes.py:140`). Edge-inclusive, same `CLEAN_EPS` slack and the
same rationale (raw `actor_bounds` GMath noise vs an authored box). Per-axis:
`a.lo[i] <= b.hi[i] + CLEAN_EPS AND b.lo[i] <= a.hi[i] + CLEAN_EPS` for all three axes.

Test (`uedcli/tests/test_find_spatial.py`, unit): overlap, edge-touch (shared face), disjoint,
containment (`within ⇒ intersects`), and symmetry (`intersects(a,b) == intersects(b,a)`).

## Slice 2 — parser flag

In `uedcli/cli/parsers/actor.py`, add `--overlapping-bbox` as a plain `add_argument` right after the
`--within-bbox` block (ends `actor.py:67`) — NOT in the `--folder` mutually-exclusive group at
`actor.py:77`. `dest="overlapping_bbox"`, `default=None`, `type=parse_bbox`, metavar
`X0,Y0,Z0,X1,Y1,Z1`, help per spec (world-AABB overlap, straddler caught, AABB false-positive caveat
pointing at board item `find-relational-predicates`).

Same slice: drop the closing "(A looser … --overlapping-bbox, does not exist yet.)" sentence from
the `--within-bbox` help (`actor.py:66-67`) — no-back-compat, the stale note goes when the thing
lands.

## Slice 3 — handler

In `uedcli/cli/commands/actor/query.py`, right after the `--within-bbox` block
(`query.py:129-132`), add the symmetric filter:

    obox = getattr(args, "overlapping_bbox", None)
    if obox is not None:
        names = [n for n in names
                 if writes.aabb_intersects(writes.actor_bounds(level.actors[n]), obox)]

It ANDs with the other filters; no exclusion wiring (owner, 2026-08-02). `-`/`--exclude` already
operate on the final `names`, so no extra work.

## Slice 4 — CLI + docs tests

`uedcli/tests/test_find_spatial.py` (reuse `_fixture` with `BrushStraddle` world 85..105):
- `BrushStraddle` excluded by `--within-bbox`, included by `--overlapping-bbox`.
- `Inside`/`Edge`/`BrushIn` still match; fully-`Outside` does not.
- corner order free; edge-touching actor counts.
- malformed `--overlapping-bbox` → exit 2, no traceback (parametrize alongside `--within-bbox`).
- composes with `--kind brush`, the `-` universe, and `--exclude`.
- both flags together (`--within-bbox B --overlapping-bbox B`) accepted, yields the `--within-bbox`
  set (degenerate AND) — pins the no-exclusion ruling.

Regenerate the parser-baseline fixtures with `python -m uedcli.tests.parser_baseline` and commit
`tests/fixtures/parser_baseline/{action_tree.json,help.json,argv_corpus.json}` — any parser-surface
change (here the new `--overlapping-bbox` flag) reddens `test_action_tree_matches_baseline` /
`test_help_screens_match_baseline` (`test_parser_baseline.py`) otherwise.

`docs/usage.md:169-176`: document `--overlapping-bbox`, remove the "not yet implemented" note, add
the contained-vs-straddling one-liner and the AABB caveat.

## Verify

`bin/test` green; formatter/linter/type-checker on touched files. Exercise:
`uedcli actor find --overlapping-bbox <box>` and `--within-bbox <box>` on a fixture level, confirm
the straddler appears only under overlapping and both-flags degenerates to within.
