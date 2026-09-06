# Brush Relation Family Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Fix the currently-broken `relation.py` (missing tolerance constants), then replace
`brush measure relation` with a new `brush relation {measure, find, set}` family: `measure`
restricted to 2 exact face selectors, `find` a pipeable candidate search, `set` a new verb that
translates a brush into a target gap/centroid/edge relationship with a reference face.

**Architecture:** All three verbs share `uedcli/relation.py`'s existing plane/footprint/delta math
(`plane_relationship`, `project_to_plane`, `classify_footprint_2d`, `compute_deltas`) through one
new shared helper, `_pairs_between`. Each verb gets its own thin entry point in `relation.py`
(`compute_pair`, `find_candidates`, `compute_set_translation`) and its own CLI command handler in a
new `uedcli/cli/commands/brush/relation.py`, replacing `uedcli/cli/commands/brush/measure.py`.

**Tech Stack:** Python, argparse, pytest (`bin/test`). No editor, no native CSG — pure model-side
compute against the git-tracked trunk (`dev/docs/architecture.md` "The core write pattern").

**Spec:** `dev/docs/superpowers/specs/2026-09-05-brush-relation-family-design.md`

## Global Constraints

- No back-compat cruft: `brush measure relation` is renamed outright to `brush relation measure`,
  no alias. `brush poly find`'s `names` argument becomes optional with a new default in the SAME
  change, not a follow-up.
- Never let a Python exception reach the user: every new/changed code path raises
  `relation.RelationError` (a `ValueError` subclass, same pattern as `polyalign.PolyAlignError`)
  naming the offending value, caught at the CLI layer and printed to stderr with exit 2.
- `-`/stdin reading goes through the ONE shared reader, `uedcli/cli/targets.py:resolve_target_names`
  — never re-implemented per verb. Empty stdin is always a clean no-op (exit 0).
- Coordinates written to `actor.location` are `decimal.Decimal` (`dev/docs/architecture.md` "Coords:
  exact Decimal"); `relation.py`'s geometry is float-based (existing convention in this module), so
  `set`'s float delta is converted via `Decimal(str(component))` at the single point it's added to
  `actor.location` — nowhere else.
- Run tests via `bin/test` or the project's documented `pytest` invocation
  (`dev/docs/rules/tests.md`), never bare `pytest` piped through `tail`.

---

## Task 1: Fix the precursor bug — restore the missing tolerance constants

`uedcli/relation.py:33,41,48` reference `polyalign._PARALLEL_EPS`/`polyalign._PLANE_EPS`, but
commit `252c4ad` deleted both from `polyalign.py`. Every call into `plane_relationship`/`compute`
currently raises `AttributeError`. Fix: `relation.py` now owns these two constants directly (nothing
else needs them post-252c4ad) — no cross-module dependency to restore.

**Files:**
- Modify: `uedcli/relation.py:1-49`
- Test: `uedcli/tests/test_relation.py` (existing — currently 12 of 27 tests fail on this)

**Interfaces:**
- Produces: `relation._PARALLEL_EPS` (float, `1e-3`), `relation._PLANE_EPS` (float, `0.5`) — module
  constants, used internally by `plane_relationship` (Task 1) and reused by every later task in this
  plan.

- [ ] **Step 1: Confirm the current failure**

Run: `TMPDIR=$PWD/_scratch/pttmp .venv/bin/python -m pytest -p no:cacheprovider -o cache_dir=_scratch/pttmp/pc uedcli/tests/test_relation.py -q`
Expected: `12 failed, 15 passed`, every failure `AttributeError: module 'uedcli.polyalign' has no attribute '_PARALLEL_EPS'`.

- [ ] **Step 2: Restore the constants in `relation.py`, dropping the `polyalign.` prefix**

In `uedcli/relation.py`, add the two constants right after the `Vec2`/`Vec3` type aliases (before
the `PlaneRelation` dataclass, around line 13):

```python
Vec2 = tuple[float, float]
Vec3 = tuple[float, float, float]

_PARALLEL_EPS = 1e-3   # 1 - |n.n'| below this => same plane orientation
_PLANE_EPS = 0.5       # |distance| below this => coplanar rather than merely parallel
```

Then update the three use sites:

```python
# docstring, was: "...within `polyalign._PARALLEL_EPS`."""
    their normals aren't parallel or anti-parallel within `_PARALLEL_EPS`."""
```

```python
    # was: if abs(abs(alignment) - 1.0) > polyalign._PARALLEL_EPS:
    if abs(abs(alignment) - 1.0) > _PARALLEL_EPS:
```

```python
    # was: plane = "coplanar" if abs(distance) <= polyalign._PLANE_EPS else "parallel"
    plane = "coplanar" if abs(distance) <= _PLANE_EPS else "parallel"
```

- [ ] **Step 3: Run the suite, verify it's green**

Run: `TMPDIR=$PWD/_scratch/pttmp .venv/bin/python -m pytest -p no:cacheprovider -o cache_dir=_scratch/pttmp/pc uedcli/tests/test_relation.py -q`
Expected: `27 passed`

- [ ] **Step 4: Commit**

```bash
git add uedcli/relation.py
git commit -m "relation.py: restore _PARALLEL_EPS/_PLANE_EPS, owned here not polyalign"
```

---

## Task 2: `relation.py` — shared pair-search helper + self-comparison-aware `measure`

Factor `compute()`'s inner double loop into a reusable helper, then build `compute_pair` (the new
`brush relation measure` core) on top of it. `compute_pair` handles the 2-selector grammar
(`Name` or `Name:SELECTOR`) and the `--allow-self` guard.

**Files:**
- Modify: `uedcli/relation.py`
- Test: `uedcli/tests/test_relation.py`

**Interfaces:**
- Consumes: `PairFace`, `PairGroup`, `RelationReport`, `plane_relationship`, `project_to_plane`,
  `classify_footprint_2d`, `compute_deltas`, `_candidate_sort_key`, `RelationError` (all already in
  `relation.py`); `surface.parse_poly_selector(token) -> (str, str)`,
  `surface.resolve_polys(selector, actor, *, brush_name) -> set[int]`,
  `query.resolve_actor_name(level, name) -> str` (raises `KeyError`).
- Produces: `_pairs_between(actor_a, idxs_a, actor_b, idxs_b) -> list[PairFace]` (module-private, reused by
  Tasks 3 and 4); `_resolve_measure_selector(level, token) -> (str, Actor, set[int])` (reused by
  Task 3); `compute_pair(level, ref_token, target_token, *, top=1, allow_self=False) -> RelationReport`.

- [ ] **Step 1: Write the failing tests**

Append to `uedcli/tests/test_relation.py`:

```python
def test_compute_pair_pins_to_exact_selectors():
    a = _brush("A", cube(32, 32, 32), loc=(0, 0, 0))
    b = _brush("B", cube(32, 32, 32), loc=(0, 0, 32))
    level = _level(a, b)
    top_a = next(i for i, p in enumerate(a.brush.polys) if p.normal == (0.0, 0.0, 1.0))
    bottom_b = next(i for i, p in enumerate(b.brush.polys) if p.normal == (0.0, 0.0, -1.0))
    report = relation.compute_pair(level, f"A:{top_a}", f"B:{bottom_b}")
    assert len(report.groups) == 1
    assert len(report.groups[0].shown) == 1  # pinned to one pair, no ranking needed
    assert report.groups[0].shown[0].plane.plane == "coincident" or report.groups[0].shown[0].plane.plane == "coplanar"


def test_compute_pair_bare_names_ranks_like_compute():
    a = _brush("A", cube(32, 32, 32), loc=(0, 0, 0))
    b = _brush("B", cube(32, 32, 32), loc=(0, 0, 32))
    level = _level(a, b)
    pair_report = relation.compute_pair(level, "A", "B", top=None)
    full_report = relation.compute(level, ["A", "B"], top=None)
    assert pair_report.groups[0].candidate_count == full_report.groups[0].candidate_count


def test_compute_pair_mixed_bare_and_pinned_selectors():
    # REF bare (ranks all its polys) against TARGET pinned to one exact poly.
    a = _brush("A", cube(32, 32, 32), loc=(0, 0, 0))
    b = _brush("B", cube(32, 32, 32), loc=(0, 0, 32))
    level = _level(a, b)
    bottom_b = next(i for i, p in enumerate(b.brush.polys) if p.normal == (0.0, 0.0, -1.0))
    report = relation.compute_pair(level, "A", f"B:{bottom_b}", top=None)
    assert report.groups
    assert all(p.poly_b == bottom_b for p in report.groups[0].shown)


def test_compute_pair_same_brush_rejected_by_default():
    a = _brush("A", cube(32, 32, 32))
    level = _level(a)
    with pytest.raises(relation.RelationError, match="allow-self"):
        relation.compute_pair(level, "A:0", "A:1")


def test_compute_pair_allow_self_permits_same_brush():
    a = _brush("A", cube(32, 32, 32))
    level = _level(a)
    report = relation.compute_pair(level, "A", "A", top=None, allow_self=True)
    assert report.brush_count == 1
    # every shown pair excludes the trivial (idx, idx) self-match
    assert all(not (p.poly_a == p.poly_b) for p in report.groups[0].shown) if report.groups else True


def test_compute_pair_disjoint_never_reports_exactly_one():
    a = _brush("A", cube(16, 16, 16), loc=(0, 0, 0))
    b = _brush("B", cube(16, 16, 16), loc=(500, 500, 500))
    b.props.insert(0, ("Rotation", "(Pitch=5000,Yaw=7000,Roll=3000)"))
    level = _level(a, b)
    report = relation.compute_pair(level, "A", "B")
    assert len(report.disjoint) in (0, 2)


def test_compute_pair_unknown_selector_raises():
    a = _brush("A", cube(16, 16, 16))
    level = _level(a)
    with pytest.raises(relation.RelationError):
        relation.compute_pair(level, "A", "NoSuchBrush")
```

- [ ] **Step 2: Run to verify failure**

Run: `TMPDIR=$PWD/_scratch/pttmp .venv/bin/python -m pytest -p no:cacheprovider -o cache_dir=_scratch/pttmp/pc uedcli/tests/test_relation.py -q -k compute_pair`
Expected: FAIL with `AttributeError: module 'uedcli.relation' has no attribute 'compute_pair'`

- [ ] **Step 3: Add imports, the shared helper, and `compute_pair` to `relation.py`**

At the top of `uedcli/relation.py`, alongside the existing `from . import polyalign`:

```python
from . import polyalign
from . import query
from . import surface
```

Replace `compute()`'s inner double loop (the `for actor_a, actor_b in itertools.combinations(actors, 2):` block's body) with a call to a new shared helper. Add the helper just above `compute()`:

```python
def _pairs_between(actor_a, idxs_a: set, actor_b, idxs_b: set) -> list:
    """Every (idx_a, idx_b) poly pair between `actor_a`'s `idxs_a` and `actor_b`'s `idxs_b` with a
    defined plane relationship, as `PairFace` objects ranked best-first (`_candidate_sort_key`).
    Skips the identical `(actor, idx)` pairing when `actor_a is actor_b` -- a poly compared to
    itself is never a meaningful relation, independent of any actor-level self-comparison guard a
    caller applies."""
    same_brush = actor_a is actor_b
    candidates: list[PairFace] = []
    for idx_a in idxs_a:
        poly_a = actor_a.brush.polys[idx_a]
        for idx_b in idxs_b:
            if same_brush and idx_a == idx_b:
                continue
            poly_b = actor_b.brush.polys[idx_b]
            rel = plane_relationship(actor_a, poly_a, actor_b, poly_b)
            if rel is None:
                continue
            world_a = polyalign._world_verts(actor_a, poly_a)
            world_b = polyalign._world_verts(actor_b, poly_b)
            uv_a = project_to_plane(world_a, rel.normal_a)
            uv_b = project_to_plane(world_b, rel.normal_a, origin=world_a[0])
            footprint_2d = classify_footprint_2d(uv_a, uv_b)
            deltas = compute_deltas(uv_a, uv_b)
            candidates.append(PairFace(
                brush_a=actor_a.name, poly_a=idx_a, brush_b=actor_b.name, poly_b=idx_b,
                plane=rel, footprint_2d=footprint_2d, deltas=deltas,
            ))
    candidates.sort(key=_candidate_sort_key)
    return candidates
```

Now `compute()`'s loop body becomes:

```python
    for actor_a, actor_b in itertools.combinations(actors, 2):
        candidates = _pairs_between(
            actor_a, set(range(len(actor_a.brush.polys))),
            actor_b, set(range(len(actor_b.brush.polys))),
        )
        if not candidates:
            continue
        shown = candidates if top is None else candidates[:top]
```

(delete the old inline double loop and its own `candidates.sort(key=_candidate_sort_key)` call — the
sort now happens inside `_pairs_between`.)

Then, after `compute()`, add:

```python
# --------------------------------------------------------------------- brush relation measure

def _resolve_measure_selector(level, token: str):
    """Bare `Name` (all its polys) or `Name:SELECTOR` -> (canonical_name, actor, index set).
    Raises `RelationError` naming the offender for every failure path."""
    if ":" in token:
        brush_name, selector = surface.parse_poly_selector(token)
    else:
        brush_name, selector = token, "all"
    try:
        canonical = query.resolve_actor_name(level, brush_name)
    except KeyError as e:
        raise RelationError(e.args[0]) from e
    actor = level.actors[canonical]
    if actor.brush is None:
        raise RelationError(f"{canonical!r} is not a brush actor (no PolyList)")
    try:
        indices = surface.resolve_polys(selector, actor, brush_name=canonical)
    except ValueError as e:
        raise RelationError(str(e)) from e
    return canonical, actor, indices


def compute_pair(level, ref_token: str, target_token: str, *, top: int | None = 1,
                  allow_self: bool = False) -> RelationReport:
    """`brush relation measure REF TARGET` -- exactly 2 selectors, each a bare brush Name (all its
    polys) or `Name:SELECTOR`. Returns a `RelationReport` with at most one `PairGroup`, reusing
    `format_report` as-is. Raises `RelationError` naming the offender for every failure path,
    including two selectors naming the same brush unless `allow_self`."""
    if top is not None and top < 1:
        raise RelationError(f"--top must be a positive integer or 'all', got {top!r}")
    ref_name, ref_actor, ref_idxs = _resolve_measure_selector(level, ref_token)
    target_name, target_actor, target_idxs = _resolve_measure_selector(level, target_token)
    if ref_name == target_name and not allow_self:
        raise RelationError(
            f"brush relation measure: both selectors name the same brush ({ref_name!r}) -- pass "
            f"--allow-self to compare two faces of one brush")
    candidates = _pairs_between(ref_actor, ref_idxs, target_actor, target_idxs)
    shown = candidates if top is None else candidates[:top]
    groups = []
    if candidates:
        groups.append(PairGroup(brush_a=ref_name, brush_b=target_name,
                                 shown=shown, candidate_count=len(candidates)))
    disjoint = sorted({ref_name, target_name}) if not candidates else []
    brush_count = 1 if ref_name == target_name else 2
    return RelationReport(groups=groups, disjoint=disjoint, brush_count=brush_count, pair_count=1)
```

- [ ] **Step 4: Run the full relation test file, verify all green (old + new)**

Run: `TMPDIR=$PWD/_scratch/pttmp .venv/bin/python -m pytest -p no:cacheprovider -o cache_dir=_scratch/pttmp/pc uedcli/tests/test_relation.py -q`
Expected: `34 passed` (27 existing + 7 new)

- [ ] **Step 5: Commit**

```bash
git add uedcli/relation.py uedcli/tests/test_relation.py
git commit -m "relation.py: shared _pairs_between helper, compute_pair for 2-selector measure"
```

---

## Task 3: `relation.py` — `find_candidates` and predicates

**Files:**
- Modify: `uedcli/relation.py`
- Test: `uedcli/tests/test_relation.py`

**Interfaces:**
- Consumes: `_pairs_between`, `_resolve_measure_selector` (Task 2), `PairFace`.
- Produces: `FindMatch` (frozen dataclass: `candidate: str`, `poly: int`, `pair: PairFace`);
  `find_candidates(level, ref_token, candidate_names: list[str], *, max_gap=None, min_gap=None,
  footprint: set[str] | None = None, plane: str | None = None, top: int | None = 1) ->
  list[FindMatch]`. `candidate_names` must already be canonical, brush-only names — resolution and
  self/non-brush filtering is the CLI layer's job (Task 6), matching `poly find`'s own split between
  resolving names and calling into pure geometry.

- [ ] **Step 1: Write the failing tests**

Append to `uedcli/tests/test_relation.py`:

```python
def test_find_candidates_ranks_and_caps_per_candidate():
    ref = _brush("Wall", cube(64, 64, 8), loc=(0, 0, 0))
    near = _brush("Near", cube(64, 64, 8), loc=(0, 0, 8))     # flush on top
    far = _brush("Far", cube(64, 64, 8), loc=(0, 0, 100))     # same axis, far gap
    level = _level(ref, near, far)
    matches = relation.find_candidates(level, "Wall", ["Near", "Far"], top=1)
    assert {m.candidate for m in matches} <= {"Near", "Far"}
    near_matches = [m for m in matches if m.candidate == "Near"]
    assert len(near_matches) == 1
    assert near_matches[0].pair.plane.plane == "coplanar"


def test_find_candidates_max_gap_filters_out_far():
    ref = _brush("Wall", cube(64, 64, 8), loc=(0, 0, 0))
    near = _brush("Near", cube(64, 64, 8), loc=(0, 0, 8))
    far = _brush("Far", cube(64, 64, 8), loc=(0, 0, 100))
    level = _level(ref, near, far)
    matches = relation.find_candidates(level, "Wall", ["Near", "Far"], max_gap=1.0)
    assert {m.candidate for m in matches} == {"Near"}


def test_find_candidates_min_gap_filters_out_near():
    ref = _brush("Wall", cube(64, 64, 8), loc=(0, 0, 0))
    near = _brush("Near", cube(64, 64, 8), loc=(0, 0, 8))
    far = _brush("Far", cube(64, 64, 8), loc=(0, 0, 100))
    level = _level(ref, near, far)
    matches = relation.find_candidates(level, "Wall", ["Near", "Far"], min_gap=50.0)
    assert {m.candidate for m in matches} == {"Far"}


def test_find_candidates_footprint_filter():
    ref = _brush("Wall", cube(64, 64, 8), loc=(0, 0, 0))
    small = _brush("Small", cube(8, 8, 8), loc=(0, 0, 8))     # small footprint, contained
    level = _level(ref, small)
    contained = relation.find_candidates(level, "Wall", ["Small"], footprint={"contains"})
    assert len(contained) == 1
    none_only = relation.find_candidates(level, "Wall", ["Small"], footprint={"none"})
    assert none_only == []


def test_find_candidates_plane_filter():
    ref = _brush("Wall", cube(64, 64, 8), loc=(0, 0, 0))
    coplanar = _brush("Coplanar", cube(64, 64, 8), loc=(0, 0, 8))
    parallel = _brush("Parallel", cube(64, 64, 8), loc=(0, 0, 20))
    level = _level(ref, coplanar, parallel)
    coplanar_only = relation.find_candidates(
        level, "Wall", ["Coplanar", "Parallel"], plane="coplanar")
    assert {m.candidate for m in coplanar_only} == {"Coplanar"}


def test_find_candidates_min_gap_exceeds_max_gap_raises():
    a = _brush("Wall", cube(16, 16, 16))
    level = _level(a)
    with pytest.raises(relation.RelationError):
        relation.find_candidates(level, "Wall", [], min_gap=10.0, max_gap=1.0)
```

- [ ] **Step 2: Run to verify failure**

Run: `TMPDIR=$PWD/_scratch/pttmp .venv/bin/python -m pytest -p no:cacheprovider -o cache_dir=_scratch/pttmp/pc uedcli/tests/test_relation.py -q -k find_candidates`
Expected: FAIL with `AttributeError: module 'uedcli.relation' has no attribute 'find_candidates'`

- [ ] **Step 3: Add `find_candidates` and its predicates to `relation.py`**

Append after `compute_pair`:

```python
# --------------------------------------------------------------------- brush relation find

_FOOTPRINT_FILTER_ALIASES = {"contains": {"contains_a_in_b", "contains_b_in_a"}}


@dataclass(frozen=True)
class FindMatch:
    candidate: str
    poly: int
    pair: PairFace   # REF is always pair.brush_a/poly_a; the candidate is pair.brush_b/poly_b


def _passes_predicates(pair: PairFace, *, max_gap, min_gap, footprint, plane) -> bool:
    if plane is not None and pair.plane.plane != plane:
        return False
    gap = abs(pair.plane.distance)
    if max_gap is not None and gap > max_gap:
        return False
    if min_gap is not None and gap < min_gap:
        return False
    if footprint is not None:
        allowed: set = set()
        for f in footprint:
            allowed |= _FOOTPRINT_FILTER_ALIASES.get(f, {f})
        if pair.footprint_2d not in allowed:
            return False
    return True


def find_candidates(level, ref_token: str, candidate_names: list, *,
                     max_gap: float | None = None, min_gap: float | None = None,
                     footprint: set | None = None, plane: str | None = None,
                     top: int | None = 1) -> list:
    """`brush relation find` -- rank every brush in `candidate_names` (already resolved to
    canonical brush-actor names by the caller) against `ref_token` (bare `Name` or `Name:idx`),
    keeping only poly pairs that satisfy every given predicate. Returns `FindMatch` objects, best
    pair first per candidate, `top` capping how many pairs per candidate are kept. Raises
    `RelationError` naming the offender for a bad `ref_token`, a bad `top`, or an inverted gap range."""
    if top is not None and top < 1:
        raise RelationError(f"--top must be a positive integer or 'all', got {top!r}")
    if min_gap is not None and max_gap is not None and min_gap > max_gap:
        raise RelationError(f"--min-gap ({min_gap}) must not exceed --max-gap ({max_gap})")
    ref_name, ref_actor, ref_idxs = _resolve_measure_selector(level, ref_token)
    results = []
    for cand_name in candidate_names:
        cand_actor = level.actors[cand_name]
        cand_idxs = set(range(len(cand_actor.brush.polys)))
        pairs = _pairs_between(ref_actor, ref_idxs, cand_actor, cand_idxs)
        pairs = [p for p in pairs
                 if _passes_predicates(p, max_gap=max_gap, min_gap=min_gap,
                                        footprint=footprint, plane=plane)]
        shown = pairs if top is None else pairs[:top]
        results.extend(FindMatch(candidate=cand_name, poly=p.poly_b, pair=p) for p in shown)
    return results
```

- [ ] **Step 4: Run, verify green**

Run: `TMPDIR=$PWD/_scratch/pttmp .venv/bin/python -m pytest -p no:cacheprovider -o cache_dir=_scratch/pttmp/pc uedcli/tests/test_relation.py -q`
Expected: `40 passed`

- [ ] **Step 5: Commit**

```bash
git add uedcli/relation.py uedcli/tests/test_relation.py
git commit -m "relation.py: find_candidates with gap/footprint/plane predicates"
```

---

## Task 4: `relation.py` — `compute_set_translation`

**Files:**
- Modify: `uedcli/relation.py`
- Test: `uedcli/tests/test_relation.py`

**Interfaces:**
- Consumes: `plane_relationship`, `project_to_plane`, `compute_deltas`, `_plane_basis` (already
  private in `relation.py`), `polyalign._world_verts`.
- Produces: `_resolve_exact_face(level, token, label) -> (str, Actor, int)`;
  `_edge_extent(poly_ref, poly_target, *, axis, mode) -> float`;
  `compute_set_translation(level, target_token, ref_token, *, gap=None, centroid_u=None,
  centroid_v=None, edge_u=None, edge_v=None) -> (str, str, tuple[float, float, float])` — returns
  `(target_name, ref_name, move)` where `move` is the world-space delta to ADD to TARGET's Location.

- [ ] **Step 1: Write the failing tests**

Append to `uedcli/tests/test_relation.py`:

```python
def test_compute_set_translation_gap_only():
    ref = _brush("Ref", cube(64, 64, 8), loc=(0, 0, 0))
    tgt = _brush("Tgt", cube(64, 64, 8), loc=(0, 0, 8))   # flush, gap=0 today
    level = _level(ref, tgt)
    top_ref = next(i for i, p in enumerate(ref.brush.polys) if p.normal == (0.0, 0.0, 1.0))
    bottom_tgt = next(i for i, p in enumerate(tgt.brush.polys) if p.normal == (0.0, 0.0, -1.0))
    name, ref_name, move = relation.compute_set_translation(
        level, f"Tgt:{bottom_tgt}", f"Ref:{top_ref}", gap=10.0)
    assert name == "Tgt"
    assert ref_name == "Ref"
    assert move == pytest.approx((0.0, 0.0, 10.0), abs=1e-6)  # was 0 gap, now 10 along +Z normal


def test_compute_set_translation_centroid_only_leaves_gap():
    ref = _brush("Ref", cube(64, 64, 8), loc=(0, 0, 0))
    tgt = _brush("Tgt", cube(64, 64, 8), loc=(20, 0, 8))  # offset 20uu in X (world U or V)
    level = _level(ref, tgt)
    top_ref = next(i for i, p in enumerate(ref.brush.polys) if p.normal == (0.0, 0.0, 1.0))
    bottom_tgt = next(i for i, p in enumerate(tgt.brush.polys) if p.normal == (0.0, 0.0, -1.0))
    name, ref_name, move = relation.compute_set_translation(
        level, f"Tgt:{bottom_tgt}", f"Ref:{top_ref}", centroid_u=0.0)
    # gap (Z) untouched: the move has zero Z component
    assert move[2] == pytest.approx(0.0, abs=1e-6)
    # some in-plane component is non-zero (the 20uu offset gets nulled on whichever axis U mapped to)
    assert abs(move[0]) + abs(move[1]) > 1.0


def test_compute_set_translation_no_flags_raises():
    ref = _brush("Ref", cube(16, 16, 16), loc=(0, 0, 0))
    tgt = _brush("Tgt", cube(16, 16, 16), loc=(0, 0, 16))
    level = _level(ref, tgt)
    with pytest.raises(relation.RelationError, match="at least one"):
        relation.compute_set_translation(level, "Tgt:0", "Ref:0")


def test_compute_set_translation_non_planar_pair_raises():
    ref = _brush("Ref", cube(64, 64, 8), loc=(0, 0, 0))
    tgt = _brush("Tgt", cube(64, 64, 8), loc=(0, 0, 8))
    level = _level(ref, tgt)
    top_ref = next(i for i, p in enumerate(ref.brush.polys) if p.normal == (0.0, 0.0, 1.0))
    side_tgt = next(i for i, p in enumerate(tgt.brush.polys) if p.normal == (1.0, 0.0, 0.0))
    with pytest.raises(relation.RelationError):
        relation.compute_set_translation(level, f"Tgt:{side_tgt}", f"Ref:{top_ref}", gap=0.0)


def test_compute_set_translation_bare_name_rejected():
    ref = _brush("Ref", cube(16, 16, 16), loc=(0, 0, 0))
    tgt = _brush("Tgt", cube(16, 16, 16), loc=(0, 0, 16))
    level = _level(ref, tgt)
    with pytest.raises(relation.RelationError):
        relation.compute_set_translation(level, "Tgt", "Ref:0", gap=0.0)  # TARGET must be BRUSH:idx


def test_compute_set_translation_same_brush_rejected():
    a = _brush("A", cube(16, 16, 16))
    level = _level(a)
    with pytest.raises(relation.RelationError):
        relation.compute_set_translation(level, "A:0", "A:1", gap=0.0)


def test_compute_set_translation_edge_u_min_explicit():
    ref = _brush("Ref", cube(64, 64, 8), loc=(0, 0, 0))
    tgt = _brush("Tgt", cube(64, 64, 8), loc=(0, 0, 8))
    level = _level(ref, tgt)
    top_ref = next(i for i, p in enumerate(ref.brush.polys) if p.normal == (0.0, 0.0, 1.0))
    bottom_tgt = next(i for i, p in enumerate(tgt.brush.polys) if p.normal == (0.0, 0.0, -1.0))
    name, ref_name, move = relation.compute_set_translation(
        level, f"Tgt:{bottom_tgt}", f"Ref:{top_ref}", edge_u=("min", 5.0))
    assert move[2] == pytest.approx(0.0, abs=1e-6)  # gap untouched
```

- [ ] **Step 2: Run to verify failure**

Run: `TMPDIR=$PWD/_scratch/pttmp .venv/bin/python -m pytest -p no:cacheprovider -o cache_dir=_scratch/pttmp/pc uedcli/tests/test_relation.py -q -k compute_set_translation`
Expected: FAIL with `AttributeError: module 'uedcli.relation' has no attribute 'compute_set_translation'`

- [ ] **Step 3: Add `_resolve_exact_face`, `_edge_extent`, and `compute_set_translation`**

Append after `find_candidates`:

```python
# --------------------------------------------------------------------- brush relation set

def _resolve_exact_face(level, token: str, label: str):
    """`BRUSH:idx` only -- a bare name or a comma/`all` selector is rejected, since a translation
    target or reference can't be ambiguous. Raises `RelationError` naming the offender."""
    if ":" not in token:
        raise RelationError(f"{label} must be BRUSH:idx (a bare brush name is not allowed): {token!r}")
    brush_name, selector = surface.parse_poly_selector(token)
    try:
        canonical = query.resolve_actor_name(level, brush_name)
    except KeyError as e:
        raise RelationError(e.args[0]) from e
    actor = level.actors[canonical]
    if actor.brush is None:
        raise RelationError(f"{canonical!r} is not a brush actor (no PolyList)")
    try:
        indices = surface.resolve_polys(selector, actor, brush_name=canonical)
    except ValueError as e:
        raise RelationError(str(e)) from e
    if len(indices) != 1:
        raise RelationError(f"{label} must select exactly one poly, got {len(indices)}: {token!r}")
    return canonical, actor, next(iter(indices))


def _edge_extent(poly_ref, poly_target, *, axis: int, mode: str) -> float:
    """The offset between TARGET's `mode` (`'min'`/`'max'`) extent on `axis` (0=U, 1=V) and REF's
    corresponding extent, in the shared UV frame. `compute_deltas` only reports whichever of
    min/max is currently CLOSER; `brush relation set` needs either one, explicitly picked."""
    ref_vals = [p[axis] for p in poly_ref]
    target_vals = [p[axis] for p in poly_target]
    pick = min if mode == "min" else max
    return pick(target_vals) - pick(ref_vals)


def compute_set_translation(level, target_token: str, ref_token: str, *,
                             gap: float | None = None,
                             centroid_u: float | None = None, centroid_v: float | None = None,
                             edge_u=None, edge_v=None):
    """`brush relation set TARGET --relative-to REF` -- resolves both exact faces, checks they
    share a plane relationship, and returns `(target_name, ref_name, move)` where `move` is the
    world-space `(dx, dy, dz)` delta to add to TARGET's Location so the requested degree(s) of
    freedom land exactly on their target value(s); an omitted degree of freedom's delta is 0.
    `edge_u`/`edge_v`, when given, are `(mode, value)` with `mode` `'min'`/`'max'`. Raises
    `RelationError` naming the offender for every failure path, including no flag given at all."""
    if (gap is None and centroid_u is None and centroid_v is None
            and edge_u is None and edge_v is None):
        raise RelationError(
            "brush relation set: at least one of --gap/--centroid-u/--centroid-v/--edge-u-min/"
            "--edge-u-max/--edge-v-min/--edge-v-max is required")
    target_name, target_actor, target_idx = _resolve_exact_face(level, target_token, "TARGET")
    ref_name, ref_actor, ref_idx = _resolve_exact_face(level, ref_token, "--relative-to")
    if target_name == ref_name:
        raise RelationError(
            f"brush relation set: TARGET and REF must be different brushes, both are {target_name!r}")
    ref_poly = ref_actor.brush.polys[ref_idx]
    target_poly = target_actor.brush.polys[target_idx]
    rel = plane_relationship(ref_actor, ref_poly, target_actor, target_poly)
    if rel is None:
        raise RelationError(
            f"brush relation set: {target_name}:{target_idx} and {ref_name}:{ref_idx} are not "
            f"parallel/coplanar -- no defined normal direction or in-plane frame to move along")
    normal = rel.normal_a
    u_axis, v_axis = _plane_basis(normal)
    ref_world = polyalign._world_verts(ref_actor, ref_poly)
    target_world = polyalign._world_verts(target_actor, target_poly)
    uv_ref = project_to_plane(ref_world, normal)
    uv_target = project_to_plane(target_world, normal, origin=ref_world[0])
    deltas = compute_deltas(uv_ref, uv_target)

    delta_n = (gap - rel.distance) if gap is not None else 0.0
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

- [ ] **Step 4: Run, verify green**

Run: `TMPDIR=$PWD/_scratch/pttmp .venv/bin/python -m pytest -p no:cacheprovider -o cache_dir=_scratch/pttmp/pc uedcli/tests/test_relation.py -q`
Expected: `47 passed`

- [ ] **Step 5: Commit**

```bash
git add uedcli/relation.py uedcli/tests/test_relation.py
git commit -m "relation.py: compute_set_translation for brush relation set"
```

---

## Task 5: CLI parsers — `relation` subtree, retire `measure`, `poly find` optional names

**Files:**
- Modify: `uedcli/cli/parsers/brush.py`

**Interfaces:**
- Produces (argparse namespace fields): `args.sub == "relation"`, `args.relationsub in
  {"measure", "find", "set"}`; `measure`: `args.ref`, `args.target`, `args.top`, `args.allow_self`;
  `find`: `args.candidates`, `args.relative_to`, `args.max_gap`, `args.min_gap`, `args.footprint`,
  `args.plane`, `args.top`, `args.allow_self`, `args.json`; `set`: `args.target` (list),
  `args.relative_to`, `args.gap`, `args.centroid_u`, `args.centroid_v`, `args.edge_u_min`,
  `args.edge_u_max`, `args.edge_v_min`, `args.edge_v_max`. `brush poly find`'s `args.names` becomes
  optional (`nargs="*"`, may be `[]`).

- [ ] **Step 1: Replace the `measure` parser block with `relation`**

In `uedcli/cli/parsers/brush.py`, delete lines 659-683 (the entire `measure = bsub.add_parser(...)`
block through the end of the file) and replace with:

```python
    def _parse_footprint_list(s: str) -> set[str]:
        valid = {"none", "vertex", "edge", "partial", "contains", "coincident"}
        parts = {p.strip() for p in s.split(",") if p.strip()}
        bad = parts - valid
        if bad:
            raise argparse.ArgumentTypeError(
                f"--footprint: unknown value(s) {sorted(bad)} (valid: {sorted(valid)})")
        return parts

    relation = bsub.add_parser(
        "relation", help="cross-brush geometric relationships: measure/find/set")
    rsub = relation.add_subparsers(dest="relationsub", required=True)

    _FOOTPRINT_EPILOG = (
        "footprint_2d values (the 2-D outline relationship, projected onto the shared or\n"
        "parallel plane -- independent of `distance`, the out-of-plane gap):\n"
        "  none        no touching or overlap at all\n"
        "  vertex      touch at a single point\n"
        "  edge        touch along a line segment, zero area overlap\n"
        "  partial     real area overlap, neither fully contains the other\n"
        "  contains    one fully inside the other's footprint (direction stated)\n"
        "  coincident  identical footprint both ways -- usually a stray duplicate\n"
    )

    rmeasure = rsub.add_parser(
        "measure",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        help="report the exact geometric relationship between 2 face selectors (plane, normals, "
             "distance, footprint_2d overlap, deltas)",
        epilog=_FOOTPRINT_EPILOG,
    )
    rmeasure.add_argument(
        "ref", metavar="REF_SELECTOR",
        help="reference face selector: a bare brush Name (all its polys) or Name:SELECTOR "
             "(SELECTOR = 'all' or comma indices). Sign conventions (distance, deltas) are "
             "relative to THIS selector")
    rmeasure.add_argument(
        "target", metavar="TARGET_SELECTOR",
        help="the other face selector, same grammar as REF_SELECTOR")
    rmeasure.add_argument(
        "--top", type=_top_arg, default=1,
        help="max ranked candidate poly-pairs to show (default 1); 'all' shows every "
             "qualifying pair with no cap")
    rmeasure.add_argument(
        "--allow-self", dest="allow_self", action="store_true",
        help="permit REF_SELECTOR and TARGET_SELECTOR to name the SAME brush (comparing two "
             "faces of one brush). Without it, naming the same brush on both sides is a clean "
             "exit 2 -- it usually means a typo or a copy-paste left the same name twice")

    rfind = rsub.add_parser(
        "find",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        help="print faces of one or more candidate brushes related to a reference face, "
             "filtered by gap/footprint/plane, as candidate:idx selectors",
        epilog=_FOOTPRINT_EPILOG,
    )
    rfind.add_argument(
        "candidates", nargs="*", metavar="NAME",
        help="candidate brush Name(s) to search, or '-' to read a newline name list from "
             "stdin (empty stdin: clean no-op). Omit entirely (no names, no '-') to search "
             "every OTHER brush in the level")
    rfind.add_argument(
        "--relative-to", dest="relative_to", required=True, metavar="REF[:idx]",
        help="the reference: a bare brush Name (rank against every one of its polys) or "
             "Name:idx (pin to exactly one reference poly)")
    rfind.add_argument(
        "--max-gap", dest="max_gap", type=float, default=None, metavar="N",
        help="keep only pairs whose perpendicular gap (absolute distance) is at most N world units")
    rfind.add_argument(
        "--min-gap", dest="min_gap", type=float, default=None, metavar="N",
        help="keep only pairs whose perpendicular gap (absolute distance) is at least N world units")
    rfind.add_argument(
        "--footprint", dest="footprint", type=_parse_footprint_list, default=None, metavar="LIST",
        help="comma-separated footprint_2d values to keep (none,vertex,edge,partial,contains,"
             "coincident -- 'contains' matches either direction). Omit: no filter")
    rfind.add_argument(
        "--plane", dest="plane", choices=["coplanar", "parallel"], default=None,
        help="keep only pairs of this plane relationship. Omit: either")
    rfind.add_argument(
        "--top", type=_top_arg, default=1,
        help="max ranked qualifying pairs to show PER CANDIDATE (default 1); 'all' shows "
             "every qualifying pair")
    rfind.add_argument(
        "--allow-self", dest="allow_self", action="store_true",
        help="permit the reference's OWN brush among the candidates (finding other faces of "
             "the same brush related to its reference face). Without it, the reference's own "
             "brush is excluded from the default level-wide search and rejected if named "
             "explicitly")
    rfind.add_argument(
        "--json", action="store_true",
        help="emit the full structured relation (plane, normals, distance, footprint_2d, "
             "deltas) per match as a JSON array on stdout, instead of bare candidate:idx "
             "lines; suppresses the stderr summary")

    rset = rsub.add_parser(
        "set",
        help="translate a brush (by its Location) so one of its faces hits a target gap/"
             "centroid/edge offset from a reference face")
    rset.add_argument(
        "target", nargs="+", metavar="TARGET:idx",
        help="the face to move, as an exact BRUSH:idx (a bare name or index list is not "
             "allowed). Repeat, or pass the single token '-' to read a newline TARGET:idx "
             "list from stdin (empty stdin: clean no-op) -- every target moves relative to "
             "the SAME --relative-to reference")
    rset.add_argument(
        "--relative-to", dest="relative_to", required=True, metavar="REF:idx",
        help="the fixed reference face, as an exact BRUSH:idx. Never moves")
    rset.add_argument(
        "--gap", type=float, default=None, metavar="N",
        help="set the signed perpendicular distance to the reference plane to exactly N "
             "(along the reference's own normal; 0 = flush/coplanar). Omit: leave untouched")
    ucg = rset.add_mutually_exclusive_group()
    ucg.add_argument(
        "--centroid-u", dest="centroid_u", type=float, default=None, metavar="N",
        help="set the footprint centroid's U offset from the reference to exactly N")
    ucg.add_argument(
        "--edge-u-min", dest="edge_u_min", type=float, default=None, metavar="N",
        help="set the offset between this face's U-min extent and the reference's to exactly N")
    ucg.add_argument(
        "--edge-u-max", dest="edge_u_max", type=float, default=None, metavar="N",
        help="set the offset between this face's U-max extent and the reference's to exactly N")
    vcg = rset.add_mutually_exclusive_group()
    vcg.add_argument(
        "--centroid-v", dest="centroid_v", type=float, default=None, metavar="N",
        help="set the footprint centroid's V offset from the reference to exactly N")
    vcg.add_argument(
        "--edge-v-min", dest="edge_v_min", type=float, default=None, metavar="N",
        help="set the offset between this face's V-min extent and the reference's to exactly N")
    vcg.add_argument(
        "--edge-v-max", dest="edge_v_max", type=float, default=None, metavar="N",
        help="set the offset between this face's V-max extent and the reference's to exactly N")
```

- [ ] **Step 2: Make `brush poly find`'s `names` optional**

Find the `pfind.add_argument("names", nargs="+", metavar="NAME", ...)` call (in the same file,
`poly find` section) and change to:

```python
    pfind.add_argument("names", nargs="*", metavar="NAME",
                       help="brush actor Name(s) to search (case-insensitive), or the single token "
                            "- to read the set from stdin (bare names, or the BRUSH:idx lines a "
                            "prior find/per-face verb prints — the :idx is stripped to the brush). "
                            "- is the sole source, not mixable; empty stdin is a clean no-op. Omit "
                            "entirely (no names, no -) to search every brush in the level. A "
                            "non-brush actor is warned and skipped; an unknown name is an error")
```

- [ ] **Step 3: Sanity-check the parser loads (no test file yet — that's Task 7)**

Run: `.venv/bin/python -c "from uedcli.cli.main import build_parser; build_parser().parse_args(['brush', 'relation', 'measure', '-h'])" 2>&1 | head -5`
Expected: `SystemExit: 0` after printing argparse help text (not a traceback) — confirms the parser
tree is well-formed. Repeat with `['brush', 'relation', 'find', '-h']` and
`['brush', 'relation', 'set', '-h']` to check all three subparsers.

- [ ] **Step 4: Commit**

```bash
git add uedcli/cli/parsers/brush.py
git commit -m "cli: brush relation {measure,find,set} parsers, poly find names optional"
```

---

## Task 6: CLI commands — new `relation.py` module, retire `measure.py`, update `poly.py`/`routes.py`

**Files:**
- Create: `uedcli/cli/commands/brush/relation.py`
- Delete: `uedcli/cli/commands/brush/measure.py`
- Modify: `uedcli/cli/commands/brush/routes.py`
- Modify: `uedcli/cli/commands/brush/poly.py` (`_find`)
- Test: manual smoke run in this task; full CLI tests are Task 7.

**Interfaces:**
- Consumes: `relation.compute_pair`, `relation.find_candidates`, `relation.compute_set_translation`,
  `relation._resolve_measure_selector`, `relation.RelationError`, `relation.format_report`,
  `query.resolve_actor_name`, `targets.resolve_target_names`.
- Produces: `uedcli/cli/commands/brush/relation.py:run(args, src) -> int` (the module `routes.py`
  calls for `args.sub == "relation"`).

- [ ] **Step 1: Update `routes.py`**

In `uedcli/cli/commands/brush/routes.py`, change:

```python
    elif sub == "measure":
        from . import measure as feature
```

to:

```python
    elif sub == "relation":
        from . import relation as feature
```

- [ ] **Step 2: Delete the old command module**

```bash
git rm uedcli/cli/commands/brush/measure.py
```

- [ ] **Step 3: Create the new command module**

Write `uedcli/cli/commands/brush/relation.py`:

```python
"""`brush relation measure|find|set` — cross-brush geometric relationships (plane, footprint,
deltas). `measure`/`find` are pure queries (no mutation); `set` translates a brush's Location.
Model-side, no editor. See dev/docs/superpowers/specs/2026-09-05-brush-relation-family-design.md."""
import sys
from decimal import Decimal

from ...targets import resolve_target_names
from ...errors import CommandError
from .... import query, relation


def run(args, src) -> int:
    if args.relationsub == "measure":
        return _measure(args, src)
    if args.relationsub == "find":
        return _find(args, src)
    if args.relationsub == "set":
        return _set(args, src)
    raise CommandError(f"unimplemented brush relation sub-verb: {args.relationsub}")


def _measure(args, src) -> int:
    top = None if args.top == "all" else args.top
    level = src.load()
    try:
        report = relation.compute_pair(level, args.ref, args.target,
                                        top=top, allow_self=args.allow_self)
    except relation.RelationError as e:
        print(str(e), file=sys.stderr)
        return 2
    print(relation.format_report(report))
    return 0


def _default_candidates(level, ref_name: str, allow_self: bool) -> list:
    return sorted(
        name for name, actor in level.actors.items()
        if actor.brush is not None and (allow_self or name != ref_name)
    )


def _find(args, src) -> int:
    top = None if args.top == "all" else args.top
    level = src.load()
    try:
        ref_name, _, _ = relation._resolve_measure_selector(level, args.relative_to)
    except relation.RelationError as e:
        print(str(e), file=sys.stderr)
        return 2

    if not args.candidates:                            # no names, no '-': every other brush
        candidate_names = _default_candidates(level, ref_name, args.allow_self)
    else:
        raw = resolve_target_names(args.candidates)     # `-` → stdin
        if not raw:
            return 0                                    # '-' with empty stdin: clean no-op
        candidate_names = []
        seen: set = set()
        for tok in raw:
            bname = tok.split(":", 1)[0]
            try:
                canonical = query.resolve_actor_name(level, bname)
            except KeyError as e:
                print(e.args[0], file=sys.stderr)
                return 2
            if canonical == ref_name and not args.allow_self:
                print(f"brush relation find: candidate {canonical!r} is the reference's own "
                      f"brush — pass --allow-self to include it", file=sys.stderr)
                return 2
            actor = level.actors[canonical]
            if actor.brush is None:
                print(f"skipping non-brush actor: {canonical}", file=sys.stderr)
                continue
            if canonical not in seen:
                seen.add(canonical)
                candidate_names.append(canonical)

    try:
        matches = relation.find_candidates(
            level, args.relative_to, candidate_names,
            max_gap=args.max_gap, min_gap=args.min_gap,
            footprint=args.footprint, plane=args.plane, top=top,
        )
    except relation.RelationError as e:
        print(str(e), file=sys.stderr)
        return 2

    if args.json:
        import json
        rows = [{
            "candidate": m.candidate, "poly": m.poly,
            "plane": m.pair.plane.plane,
            "normal_ref": list(m.pair.plane.normal_a),
            "normal_candidate": list(m.pair.plane.normal_b),
            "distance": m.pair.plane.distance,
            "footprint_2d": m.pair.footprint_2d,
            "deltas": {"centroid_u": m.pair.deltas.centroid_u, "centroid_v": m.pair.deltas.centroid_v,
                       "edge_u_label": m.pair.deltas.edge_u_label, "edge_u": m.pair.deltas.edge_u,
                       "edge_v_label": m.pair.deltas.edge_v_label, "edge_v": m.pair.deltas.edge_v},
        } for m in matches]
        print(json.dumps(rows, indent=2))
    else:
        for m in matches:
            print(f"{m.candidate}:{m.poly}")
        for m in matches:
            print(f"{args.relative_to} <-> {m.candidate}:{m.poly}  plane={m.pair.plane.plane} "
                  f"gap={relation._fmt(abs(m.pair.plane.distance))} "
                  f"footprint={m.pair.footprint_2d}", file=sys.stderr)
    return 0


def _set(args, src) -> int:
    raw = list(dict.fromkeys(resolve_target_names(args.target)))   # dedup exact repeats
    if not raw:
        return 0                                        # '-' with empty stdin: clean no-op
    level = src.load()
    edge_u = None
    if args.edge_u_min is not None:
        edge_u = ("min", args.edge_u_min)
    elif args.edge_u_max is not None:
        edge_u = ("max", args.edge_u_max)
    edge_v = None
    if args.edge_v_min is not None:
        edge_v = ("min", args.edge_v_min)
    elif args.edge_v_max is not None:
        edge_v = ("max", args.edge_v_max)

    touched = []
    for target_token in raw:
        try:
            target_name, ref_name, move = relation.compute_set_translation(
                level, target_token, args.relative_to,
                gap=args.gap, centroid_u=args.centroid_u, centroid_v=args.centroid_v,
                edge_u=edge_u, edge_v=edge_v,
            )
        except relation.RelationError as e:
            print(str(e), file=sys.stderr)
            return 2
        actor = level.actors[target_name]
        loc = actor.location or (Decimal(0), Decimal(0), Decimal(0))
        actor.location = tuple(loc[i] + Decimal(str(move[i])) for i in range(3))
        if target_name not in touched:
            touched.append(target_name)
        print(target_name)
    src.save(verb="relation-set", args={"target": raw, "relative_to": args.relative_to},
             level=level, touched=touched)
    print(f"moved {len(touched)} brush(es) relative to {args.relative_to}", file=sys.stderr)
    return 0
```

- [ ] **Step 4: Update `brush poly find`'s `_find` for optional names**

In `uedcli/cli/commands/brush/poly.py`, replace the `_find` function's target-resolution opening
(everything before `use_json = getattr(args, "json", False)`) with:

```python
def _find(args, src) -> int:
    from .... import facing_spec, polyalign
    try:
        spec = facing_spec.parse_facing_spec(args.facing) if args.facing is not None else None
    except ValueError as e:
        print(str(e), file=sys.stderr)                # malformed --facing → clean exit 2, naming it
        return 2
    if not args.names:                                 # no names, no '-': default to every brush
        level = src.load()
        brushes: list[str] = sorted(
            name for name, actor in level.actors.items() if actor.brush is not None)
    else:
        raw = target_names.resolve_target_names(args.names)   # `-` → stdin (bare names or BRUSH:idx lines)
        if not raw:
            return 0                                   # '-' with empty stdin: clean no-op
        level = src.load()
        brushes = []
        seen: set = set()
        for tok in raw:
            bname = tok.split(":", 1)[0]               # accept a BRUSH:idx line — the :idx is irrelevant here
            try:
                canonical = query.resolve_actor_name(level, bname)
            except KeyError as e:
                print(e.args[0], file=sys.stderr)      # unknown name → hard error (a typo must not pass)
                return 2
            if canonical not in seen:                  # dedup on canonical, first-seen order
                seen.add(canonical)
                brushes.append(canonical)
```

(the rest of the function — `use_json = ...` through the final `return 0` — is unchanged.)

- [ ] **Step 5: Smoke-test the wiring manually**

Run:
```bash
.venv/bin/python -c "
from uedcli.cli.commands.brush import routes
print(routes)  # imports cleanly
from uedcli.cli.commands.brush import relation
print(relation.run)
"
```
Expected: no traceback, prints the module and the function object.

- [ ] **Step 6: Commit**

```bash
git add uedcli/cli/commands/brush/relation.py uedcli/cli/commands/brush/routes.py \
        uedcli/cli/commands/brush/poly.py
git rm uedcli/cli/commands/brush/measure.py 2>/dev/null || true
git commit -m "cli: brush relation command module, retire measure.py, poly find default-all"
```

---

## Task 7: CLI tests

**Files:**
- Rename: `uedcli/tests/test_cli_brush_measure_relation.py` → `uedcli/tests/test_cli_brush_relation_measure.py`
- Create: `uedcli/tests/test_cli_brush_relation_find.py`
- Create: `uedcli/tests/test_cli_brush_relation_set.py`
- Modify: whichever existing `uedcli/tests/test_cli_brush_poly_find.py`-style file covers
  `poly find` today (grep `uedcli/tests/` for `polysub.*find`/`"find"` Namespace fixtures to find its
  exact name before editing — the existing file's `_ns` helper is the pattern to extend).

**Interfaces:**
- Consumes: `uedcli.cli.dispatch.dispatch(argparse.Namespace) -> int`, the `_brush`/`_project`
  fixtures already defined in `test_cli_brush_measure_relation.py` (reused/renamed here).

- [ ] **Step 1: Rename and adapt the `measure` CLI test file**

```bash
git mv uedcli/tests/test_cli_brush_measure_relation.py uedcli/tests/test_cli_brush_relation_measure.py
```

Update its `_ns` helper (2-selector grammar, new `sub`/`relationsub`, new `--allow-self`) and every
test's Namespace construction. Replace the whole `_ns` function with:

```python
def _ns(proj, ref, target, top=1, allow_self=False):
    return argparse.Namespace(
        cmd="brush", sub="relation", relationsub="measure",
        project=str(proj), tree=None, ref=ref, target=target, top=top, allow_self=allow_self,
    )
```

Update every call site: `dispatch.dispatch(_ns(proj, ["LegFoot", "FloorPad"]))` becomes
`dispatch.dispatch(_ns(proj, "LegFoot", "FloorPad"))` (two args instead of a list), and so on for
every test in the file. The `test_relation_fewer_than_two_names_exits_2` /
`test_relation_all_duplicate_names_exits_2` tests no longer apply (argparse itself now enforces
exactly 2 positionals) — delete them. Add:

```python
def test_relation_same_brush_rejected_by_default(tmp_path, monkeypatch, capsys):
    actors = [_brush("A", cube(16, 16, 16))]
    proj = _project(tmp_path, monkeypatch, actors)
    rc = dispatch.dispatch(_ns(proj, "A", "A"))
    assert rc == 2
    assert "allow-self" in capsys.readouterr().err


def test_relation_allow_self_permits_same_brush(tmp_path, monkeypatch, capsys):
    actors = [_brush("A", cube(16, 16, 16))]
    proj = _project(tmp_path, monkeypatch, actors)
    rc = dispatch.dispatch(_ns(proj, "A", "A", allow_self=True))
    assert rc == 0
```

- [ ] **Step 2: Write `test_cli_brush_relation_find.py`**

```python
import argparse
from decimal import Decimal

from uedcli import trunk
from uedcli.builders import cube, make_brush_actor
from uedcli.cli import dispatch
from uedcli.model import Level


def _brush(name, brush, loc=(0, 0, 0)):
    return make_brush_actor(name, brush, location=tuple(Decimal(str(c)) for c in loc))


def _lexo(i):
    return f"{i:04d}"


def _project(tmp_path, monkeypatch, actors, name="lvl"):
    proj = tmp_path / "repo"
    (proj / "maps" / name).mkdir(parents=True)
    (proj / "uedcli.toml").write_text('game = "deusex"\n')
    lvl = Level(actors={a.name: a for a in actors})
    trunk.write_level(proj / "maps" / name, lvl, {a.name: _lexo(i) for i, a in enumerate(actors)})
    monkeypatch.setenv("UEDCLI_LEVEL", name)
    return proj


def _ns(proj, candidates, relative_to, **overrides):
    defaults = dict(
        cmd="brush", sub="relation", relationsub="find",
        project=str(proj), tree=None, candidates=candidates, relative_to=relative_to,
        max_gap=None, min_gap=None, footprint=None, plane=None, top=1, allow_self=False, json=False,
    )
    defaults.update(overrides)
    return argparse.Namespace(**defaults)


def test_find_prints_matching_candidates(tmp_path, monkeypatch, capsys):
    actors = [
        _brush("Wall", cube(64, 64, 8), loc=(0, 0, 0)),
        _brush("Near", cube(64, 64, 8), loc=(0, 0, 8)),
        _brush("Far", cube(64, 64, 8), loc=(0, 0, 100)),
    ]
    proj = _project(tmp_path, monkeypatch, actors)
    rc = dispatch.dispatch(_ns(proj, ["Near", "Far"], "Wall"))
    assert rc == 0
    out = capsys.readouterr().out
    assert "Near:" in out


def test_find_max_gap_filters(tmp_path, monkeypatch, capsys):
    actors = [
        _brush("Wall", cube(64, 64, 8), loc=(0, 0, 0)),
        _brush("Near", cube(64, 64, 8), loc=(0, 0, 8)),
        _brush("Far", cube(64, 64, 8), loc=(0, 0, 100)),
    ]
    proj = _project(tmp_path, monkeypatch, actors)
    rc = dispatch.dispatch(_ns(proj, ["Near", "Far"], "Wall", max_gap=1.0))
    assert rc == 0
    out = capsys.readouterr().out
    assert "Near:" in out
    assert "Far:" not in out


def test_find_omitted_candidates_defaults_to_every_other_brush(tmp_path, monkeypatch, capsys):
    actors = [
        _brush("Wall", cube(64, 64, 8), loc=(0, 0, 0)),
        _brush("Near", cube(64, 64, 8), loc=(0, 0, 8)),
    ]
    proj = _project(tmp_path, monkeypatch, actors)
    rc = dispatch.dispatch(_ns(proj, [], "Wall"))
    assert rc == 0
    assert "Near:" in capsys.readouterr().out


def test_find_named_self_rejected_by_default(tmp_path, monkeypatch, capsys):
    actors = [_brush("Wall", cube(64, 64, 8))]
    proj = _project(tmp_path, monkeypatch, actors)
    rc = dispatch.dispatch(_ns(proj, ["Wall"], "Wall:0"))
    assert rc == 2
    assert "allow-self" in capsys.readouterr().err


def test_find_empty_stdin_dash_is_clean_noop(tmp_path, monkeypatch, capsys):
    actors = [_brush("Wall", cube(64, 64, 8))]
    proj = _project(tmp_path, monkeypatch, actors)
    monkeypatch.setattr("sys.stdin", __import__("io").StringIO(""))
    rc = dispatch.dispatch(_ns(proj, ["-"], "Wall"))
    assert rc == 0
    assert capsys.readouterr().out == ""


def test_find_json_emits_structured_array(tmp_path, monkeypatch, capsys):
    actors = [
        _brush("Wall", cube(64, 64, 8), loc=(0, 0, 0)),
        _brush("Near", cube(64, 64, 8), loc=(0, 0, 8)),
    ]
    proj = _project(tmp_path, monkeypatch, actors)
    rc = dispatch.dispatch(_ns(proj, ["Near"], "Wall", json=True))
    assert rc == 0
    out = capsys.readouterr().out
    assert out.strip().startswith("[")
    assert "footprint_2d" in out
```

- [ ] **Step 3: Write `test_cli_brush_relation_set.py`**

```python
import argparse
from decimal import Decimal

from uedcli import trunk
from uedcli.builders import cube, make_brush_actor
from uedcli.cli import dispatch
from uedcli.model import Level


def _brush(name, brush, loc=(0, 0, 0)):
    return make_brush_actor(name, brush, location=tuple(Decimal(str(c)) for c in loc))


def _lexo(i):
    return f"{i:04d}"


def _project(tmp_path, monkeypatch, actors, name="lvl"):
    proj = tmp_path / "repo"
    (proj / "maps" / name).mkdir(parents=True)
    (proj / "uedcli.toml").write_text('game = "deusex"\n')
    lvl = Level(actors={a.name: a for a in actors})
    trunk.write_level(proj / "maps" / name, lvl, {a.name: _lexo(i) for i, a in enumerate(actors)})
    monkeypatch.setenv("UEDCLI_LEVEL", name)
    return proj


def _ns(proj, target, relative_to, **overrides):
    defaults = dict(
        cmd="brush", sub="relation", relationsub="set",
        project=str(proj), tree=None, target=target, relative_to=relative_to,
        gap=None, centroid_u=None, centroid_v=None,
        edge_u_min=None, edge_u_max=None, edge_v_min=None, edge_v_max=None,
    )
    defaults.update(overrides)
    return argparse.Namespace(**defaults)


def _top_and_bottom(ref, tgt):
    top_ref = next(i for i, p in enumerate(ref.brush.polys) if p.normal == (0.0, 0.0, 1.0))
    bottom_tgt = next(i for i, p in enumerate(tgt.brush.polys) if p.normal == (0.0, 0.0, -1.0))
    return top_ref, bottom_tgt


def test_set_gap_moves_target_and_prints_name(tmp_path, monkeypatch, capsys):
    ref = _brush("Ref", cube(64, 64, 8), loc=(0, 0, 0))
    tgt = _brush("Tgt", cube(64, 64, 8), loc=(0, 0, 8))   # flush today
    proj = _project(tmp_path, monkeypatch, [ref, tgt])
    top_ref, bottom_tgt = _top_and_bottom(ref, tgt)
    rc = dispatch.dispatch(_ns(proj, [f"Tgt:{bottom_tgt}"], f"Ref:{top_ref}", gap=10.0))
    assert rc == 0
    out = capsys.readouterr().out
    assert out.strip() == "Tgt"
    lvl = trunk.read_level(proj / "maps" / "lvl")
    assert lvl.actors["Tgt"].location[2] == Decimal(str(8 + 10))


def test_set_no_flags_exits_2(tmp_path, monkeypatch, capsys):
    ref = _brush("Ref", cube(16, 16, 16), loc=(0, 0, 0))
    tgt = _brush("Tgt", cube(16, 16, 16), loc=(0, 0, 16))
    proj = _project(tmp_path, monkeypatch, [ref, tgt])
    rc = dispatch.dispatch(_ns(proj, ["Tgt:0"], "Ref:0"))
    assert rc == 2
    assert "at least one" in capsys.readouterr().err


def test_set_non_planar_pair_exits_2(tmp_path, monkeypatch, capsys):
    ref = _brush("Ref", cube(64, 64, 8), loc=(0, 0, 0))
    tgt = _brush("Tgt", cube(64, 64, 8), loc=(0, 0, 8))
    proj = _project(tmp_path, monkeypatch, [ref, tgt])
    top_ref, _ = _top_and_bottom(ref, tgt)
    side_tgt = next(i for i, p in enumerate(tgt.brush.polys) if p.normal == (1.0, 0.0, 0.0))
    rc = dispatch.dispatch(_ns(proj, [f"Tgt:{side_tgt}"], f"Ref:{top_ref}", gap=0.0))
    assert rc == 2


def test_set_empty_stdin_dash_is_clean_noop(tmp_path, monkeypatch, capsys):
    ref = _brush("Ref", cube(16, 16, 16), loc=(0, 0, 0))
    tgt = _brush("Tgt", cube(16, 16, 16), loc=(0, 0, 16))
    proj = _project(tmp_path, monkeypatch, [ref, tgt])
    monkeypatch.setattr("sys.stdin", __import__("io").StringIO(""))
    rc = dispatch.dispatch(_ns(proj, ["-"], "Ref:0", gap=0.0))
    assert rc == 0
    assert capsys.readouterr().out == ""


def test_set_ref_location_never_changes(tmp_path, monkeypatch, capsys):
    ref = _brush("Ref", cube(64, 64, 8), loc=(0, 0, 0))
    tgt = _brush("Tgt", cube(64, 64, 8), loc=(0, 0, 8))
    proj = _project(tmp_path, monkeypatch, [ref, tgt])
    top_ref, bottom_tgt = _top_and_bottom(ref, tgt)
    dispatch.dispatch(_ns(proj, [f"Tgt:{bottom_tgt}"], f"Ref:{top_ref}", gap=25.0))
    lvl = trunk.read_level(proj / "maps" / "lvl")
    assert lvl.actors["Ref"].location == (Decimal(0), Decimal(0), Decimal(0))
```

- [ ] **Step 4: Run the full new/changed test suite together**

Run:
```bash
TMPDIR=$PWD/_scratch/pttmp .venv/bin/python -m pytest -p no:cacheprovider -o cache_dir=_scratch/pttmp/pc \
  uedcli/tests/test_relation.py \
  uedcli/tests/test_cli_brush_relation_measure.py \
  uedcli/tests/test_cli_brush_relation_find.py \
  uedcli/tests/test_cli_brush_relation_set.py -q
```
Expected: all pass. Fix any fixture mismatches against the actual `dispatch`/`trunk` APIs before
moving on — the exact `trunk.read_level`/`trunk.write_level` call shapes above mirror
`test_cli_brush_measure_relation.py`'s existing `_project` helper; if the real signature differs,
match the existing helper exactly rather than guessing.

- [ ] **Step 5: Locate and update the existing `poly find` CLI test file for the optional-names default**

```bash
grep -rl 'polysub.*"find"\|relationsub.*find\|sub="poly".*find' uedcli/tests/*.py
```

Add one test to whichever file that finds (its `_ns`-style helper already exists — match its
pattern):

```python
def test_find_omitted_names_defaults_to_every_brush(tmp_path, monkeypatch, capsys):
    actors = [_brush("Wall", cube(16, 16, 16))]
    proj = _project(tmp_path, monkeypatch, actors)
    rc = dispatch.dispatch(_ns(proj, []))   # match the existing file's exact _ns signature
    assert rc == 0
    assert "Wall:" in capsys.readouterr().out
```

- [ ] **Step 6: Run that file too, then the whole relation+poly-find slice once more**

Run: `TMPDIR=$PWD/_scratch/pttmp .venv/bin/python -m pytest -p no:cacheprovider -o cache_dir=_scratch/pttmp/pc -k "relation or poly_find" -q`
Expected: all pass.

- [ ] **Step 7: Commit**

```bash
git add uedcli/tests/test_cli_brush_relation_measure.py uedcli/tests/test_cli_brush_relation_find.py \
        uedcli/tests/test_cli_brush_relation_set.py uedcli/tests/test_relation.py
git add -u uedcli/tests/  # picks up the poly-find test file edit + the measure->relation rename
git commit -m "tests: brush relation measure/find/set CLI coverage, poly find default-all"
```

---

## Task 8: Docs

**Files:**
- Create: `docs/reference/brush/relation.md`
- Delete: `docs/reference/brush/measure.md`
- Modify: `docs/reference/brush/README.md:14`
- Modify: `docs/reference/brush/poly.md:176`
- Modify: `docs/leveldesign/general/recipes/shapes/mitered-corner.md:63`

**Interfaces:** none (docs only).

- [ ] **Step 1: Write `docs/reference/brush/relation.md`**

```markdown
# brush relation

measure / find / set

**`brush relation measure REF TARGET`** reports the exact geometric relationship between exactly
2 face selectors — replaces eyeballing a render with computed facts: whether the planes are
coplanar or parallel, both normals, the signed distance between them, the 2-D footprint
relationship (`none`/`vertex`/`edge`/`partial`/`contains`/`coincident`), and the centroid/edge-min
deltas in the shared plane's own U/V axes. A selector is a bare brush Name (all its polys) or
`Name:SELECTOR` (`SELECTOR` = `all` or comma indices) — pin `Wall:5 Floor:4` to compare exactly
those two faces, or leave a side bare to rank every one of that brush's polys against the other
side. `--top N` caps how many ranked candidate pairs are shown (default 1, closest first); `--top
all` shows every qualifying pair. The two selectors must name different brushes unless
`--allow-self` is given (comparing two faces of the same brush).

```
$ uedcli brush relation measure Wall_North Floor
Wall_North <-> Floor  (1 of 12 candidates shown)
  Wall_North:5 <-> Floor:4
    plane: coplanar
    normals:
      Wall_North:5: (0.000, 0.000, -1.000)
      Floor:4: (0.000, 0.000, 1.000)
    distance: 0.000uu
    footprint_2d: contains (Wall_North:5 in Floor:4)
    deltas:
      centroid: U=120.000uu V=0.000uu
      edge: U-min=0.000uu V-min=0.000uu

checked: 2 brushes, 1 pairs, every face
```

**`brush relation find <candidates...> --relative-to REF[:idx]`** is a stateless producer: it
prints candidate faces related to a reference face as `candidate:idx` selectors, one per line, for
piping into `brush relation set -`, `brush poly align -`, or `brush poly move -`. `candidates` is
zero or more brush Names, or `-` to read a newline list from stdin; omit it entirely (no names, no
`-`) to search every OTHER brush in the level. `--relative-to` is required: a bare brush Name ranks
against every one of its polys, `Name:idx` pins to one reference face. Filters AND together:
`--max-gap N` / `--min-gap N` bound the perpendicular gap, `--footprint LIST` (comma-separated
`none`/`vertex`/`edge`/`partial`/`contains`/`coincident`) and `--plane {coplanar,parallel}` narrow
by relationship shape. `--top N` (default 1) / `--top all` controls how many pairs are kept per
candidate. A human summary of each match goes to stderr; `--json` emits the full structured
relation as a JSON array on stdout instead (and drops the stderr summary). The reference's own
brush is excluded from the default search and rejected if named explicitly, unless `--allow-self`.

```
$ uedcli brush relation find --relative-to Wall_North --max-gap 8
Panel:0
Shelf:2
```

**`brush relation set TARGET:idx --relative-to REF:idx`** moves `TARGET`'s whole brush (its
Location only — the shape is unchanged) so it hits a target gap, centroid offset, or edge offset
from the fixed `REF`, which never moves. Both selectors are exact `Name:idx` (a bare name or index
list is rejected — the move target can't be ambiguous); `TARGET` may instead be `-`, reading a
newline `TARGET:idx` list from stdin, moving each one relative to the same `REF`. The two faces
must already be parallel or coplanar (typically piped straight from `brush relation find`'s
output) — a non-planar pair is a clean exit 2. Every flag takes an explicit target distance, and an
omitted flag leaves that degree of freedom untouched: `--gap N` sets the signed perpendicular
distance along REF's normal; `--centroid-u N` / `--centroid-v N` set the footprint centroid offset
on that axis; `--edge-u-min N` / `--edge-u-max N` (and the `-v-` equivalents) set the offset from
that specific edge instead — mutually exclusive with the matching `--centroid-*` flag on the same
axis. At least one flag is required.

```
$ uedcli brush relation find --relative-to Wall_North --max-gap 8 | \
    uedcli brush relation set - --relative-to Wall_North:5 --gap 0 --centroid-u 0
Panel
Shelf
```

See also: [`brush poly`](poly.md), [`brush vertex`](vertex.md).
```

- [ ] **Step 2: Remove the old page**

```bash
git rm docs/reference/brush/measure.md
```

- [ ] **Step 3: Update `docs/reference/brush/README.md:14`**

Replace:
```markdown
| [`brush measure relation`](measure.md) | query | exact geometric facts between every pair of faces across 2+ brushes |
```
with:
```markdown
| [`brush relation measure/find/set`](relation.md) | query/mutate | exact geometric facts between two faces, filtered search, and move-to-relationship |
```

- [ ] **Step 4: Update `docs/reference/brush/poly.md:176`**

Replace:
```markdown
See also: [`brush vertex`](vertex.md), [`brush measure relation`](measure.md), [`actor diagram`](../actor/diagram.md), [Textures & surfaces](../../leveldesign/general/textures-and-surfaces.md) (the level-design craft of texture alignment).
```
with:
```markdown
See also: [`brush vertex`](vertex.md), [`brush relation`](relation.md), [`actor diagram`](../actor/diagram.md), [Textures & surfaces](../../leveldesign/general/textures-and-surfaces.md) (the level-design craft of texture alignment).
```

- [ ] **Step 5: Update `docs/leveldesign/general/recipes/shapes/mitered-corner.md:63`**

Replace the `brush measure relation` mention with `brush relation measure` (same sentence,
spelling only — re-read the surrounding paragraph first to confirm the example command itself, if
any, also needs its verb spelling updated).

- [ ] **Step 6: Check for any other stale references**

Run: `grep -rln "brush measure relation" docs/ dev/docs/superpowers/`
Expected: no hits (the design spec itself already uses the new spelling throughout; anything in
`docs/` still using the old spelling needs the same fix as steps 3-5).

- [ ] **Step 7: Commit**

```bash
git add docs/reference/brush/relation.md docs/reference/brush/README.md docs/reference/brush/poly.md \
        docs/leveldesign/general/recipes/shapes/mitered-corner.md
git rm docs/reference/brush/measure.md 2>/dev/null || true
git commit -m "docs: brush relation measure/find/set reference page, fix stale cross-links"
```

---

## Final verification (before merge)

- [ ] Run the full relevant slice one more time:
```bash
TMPDIR=$PWD/_scratch/pttmp .venv/bin/python -m pytest -p no:cacheprovider -o cache_dir=_scratch/pttmp/pc \
  -k "relation or poly_find" -q
```
Expected: all green, zero failures.

- [ ] Run `bin/test`'s documented doc-link checker if one exists (`test_doc_links` per
  `NATIVE-MATERIALIZE.md`'s pre-existing-reds list — note that one is ALREADY red on master
  unrelated to this work; don't treat it as a regression this plan introduced unless it newly fails
  on a path this plan touched).

- [ ] `git grep -n "brush measure relation\|measuresub\|cli.commands.brush.measure"` across the
  whole repo (code + docs) — should return nothing except historical mentions inside `dev/docs/`
  spec/plan files that document the OLD verb's history (those stay, they're a record).
