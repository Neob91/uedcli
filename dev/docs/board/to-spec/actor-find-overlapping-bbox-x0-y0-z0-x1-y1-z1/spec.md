# Spec — `actor find --overlapping-bbox X0,Y0,Z0,X1,Y1,Z1`

## Goal

A looser companion to `--within-bbox`: match actors whose world AABB **intersects** the given box,
so a room shell / floor / wall that straddles the box edge is grabbed. Better for "everything in
this area" (feeding `actor preview -`) than strict containment, which drops straddling brushes.

## Current state

- `--within-bbox` parser: `uedcli/cli/parsers/actor.py:57-67` (`type=parse_bbox`, single-valued,
  metavar `X0,Y0,Z0,X1,Y1,Z1`). Its help already ends "A looser 'also catch straddling brushes'
  variant, --overlapping-bbox, does not exist yet." — delete that closing sentence when this lands.
- Filter application: `uedcli/cli/commands/actor/query.py:129-132` — after `list_actors` and
  `--prop`, before the composable-`-` restrict. ANDs with the other filters.
- Containment predicate: `writes.aabb_within(inner, outer)` at `uedcli/writes.py:140-155`
  (edge-inclusive, `CLEAN_EPS`-tolerant). Bounds source: `writes.actor_bounds` (`writes.py:111`,
  full transform, Decimal). There is **no** `aabb_intersects` yet.
- Docs: `docs/usage.md:169-176` documents `--within-bbox` and states `--overlapping-bbox` "is not
  yet implemented."

## Design

New predicate in `writes.py`, mirroring `aabb_within`:

```python
def aabb_intersects(a, b) -> bool:
    """True when AABBs a=(lo,hi) and b=(lo,hi) overlap, edge-inclusive (a shared face/edge/corner
    counts). Per-axis: a.lo[i] <= b.hi[i] + CLEAN_EPS AND b.lo[i] <= a.hi[i] + CLEAN_EPS."""
```

Same `CLEAN_EPS` slack as `aabb_within`, and for the same reason: `actor_bounds` carries UE1 GMath
rotator noise while the box is authored, so an actor exactly touching the box edge must still count.

New parser flag on `find`, next to `--within-bbox`:

    find.add_argument(
        "--overlapping-bbox", dest="overlapping_bbox", default=None, type=parse_bbox,
        metavar="X0,Y0,Z0,X1,Y1,Z1",
        help="match actors whose world bounding box OVERLAPS the given axis-aligned box (a "
             "straddling brush that poked out of --within-bbox IS caught) — two opposite corners in "
             "any order, unreal units, edge-inclusive. Honours each actor's full transform; a point "
             "actor is its Location point. Single-valued; ANDs with the other filters. NOTE this "
             "tests the world AABB, so a diagonal/L-shaped brush can match on its bounding box "
             "without any solid geometry actually inside the box (a precise per-poly variant is not "
             "implemented — board item find-relational-predicates).")

Handler in `query.py`, right after the `--within-bbox` block:

    obox = getattr(args, "overlapping_bbox", None)
    if obox is not None:
        names = [n for n in names
                 if writes.aabb_intersects(writes.actor_bounds(level.actors[n]), obox)]

`--within-bbox` and `--overlapping-bbox` are distinct single-valued predicates. Whether both may
appear together is an **open question** (see `questions/`); the recommendation is to let them AND
like every other filter (no special mutual-exclusion), since `within ⊆ overlapping` makes the
combination degenerate to `within` rather than an error.

The L-/diagonal-brush AABB false-positive is **documented, not fixed** — the precise per-poly test is
the parked `find-relational-predicates` item. Say so in `--help` and `docs/usage.md`.

## Edge cases & errors

- Malformed coordinates → `parse_bbox` raises → argparse exits 2 (same path as `--within-bbox`; no
  traceback). Covered for `--within-bbox` in `test_find_spatial.py`; add the `--overlapping-bbox`
  parametrized case.
- No filters + `--overlapping-bbox`: the box is the sole predicate over every actor — normal.
- Empty match set: exit 0, empty stdout (glob-like empty result is legitimate pipeline data).
- Composable `-`: `--overlapping-bbox` ANDs into the predicate over the piped universe, same as
  `--within-bbox`; `--exclude` negates the whole predicate. No extra wiring.
- Point actor: zero-size box at Location — overlaps iff Location is inside the box (edge-inclusive).

## Tests

Extend `uedcli/tests/test_find_spatial.py` (reuse `_fixture`, which already has `BrushStraddle`
world 85..105 poking past x=100):

- `BrushStraddle` is **excluded** by `--within-bbox` but **included** by `--overlapping-bbox`.
- `Inside`/`Edge`/`BrushIn` still match; `Outside` (fully outside) still does not.
- Corner order free; edge-touching actor counts (shared face).
- Malformed `--overlapping-bbox` exits 2, no traceback.
- Composes with another filter (`--kind brush`) and with the `-` universe / `--exclude`.
- Unit test for `writes.aabb_intersects`: overlap, edge-touch, disjoint, containment (within ⇒
  intersects).

`docs/usage.md:169-176`: document `--overlapping-bbox`, remove the "not yet implemented" note, and
add a within-vs-overlapping one-liner (contained vs straddling) plus the AABB caveat.

## Open questions

- `questions/coexist-with-within-bbox.md` — may `--within-bbox` and `--overlapping-bbox` appear in
  the same invocation (AND), or are they a mutually-exclusive group?
