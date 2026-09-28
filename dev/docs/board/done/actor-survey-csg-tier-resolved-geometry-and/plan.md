# actor survey: two-tier reshape — implementation plan

**Goal:** Reshape `actor survey` into the two disjoint-vocabulary tiers `spec.md` rules: raw = pure
authored geometry (`encloses`/`overlaps`/`meets`/`coincides`), csg = resolved matter
(`touches`/`crosses`/`occupies`/`carves`/`connects`), bare output. (`--json` is out of scope for this
item — owner ruling, 2026-09-27.)

**Architecture:** `uedcli/actor_survey.py` stays the one module. The raw tier drops its dependency on
`actorgraph.classify_pair`/`brush_overlap` (CSG-order/Subtract/Mover branching) for a new, local,
pure-geometry pairwise classifier built on the existing `authored_shape_contains` and a new
depth-returning SAT variant. The csg tier's `occupies`/`carves` need a measurement primitive that does
not exist yet — an exact, non-sampling boolean-CSG region evaluator (convex-piece partitioning against
an ordered brush list), built once and shared by both relations; `crosses`' own resolved-matter fix
turns out to need the same partitioning (against a narrower brush list — later Subtracts only), so it
is built on top of that evaluator rather than a bespoke filter of its own (a first-pass per-corner
filter was reviewed and found not to work — see Task 3). Output formatting drops every magnitude
and `:idx`.

**Tech Stack:** Pure Python (`uedcli/actor_survey.py`, `uedcli/actorgraph.py`), pytest (`bin/test`).

**Spec:** `dev/docs/board/to-spec/actor-survey-csg-tier-resolved-geometry-and/spec.md` (owner rulings,
2026-09-26/27) — read it in full before touching any task below; this plan does not restate its
rulings, only how to build them.

## Global Constraints

- No back-compat cruft: relation names and output fields being replaced (`contains`, raw `carves`,
  `touches(<area>)`, `crosses(<depth>)`, `:idx`, `depth_uu`) are deleted outright in the same change
  that adds their replacement — no alias, no dual format.
- No sampling for `occupies`/`carves` — exact per-query boolean-CSG evaluation only (owner ruling).
- Every new tolerance is derived from the module's existing `CSG_TOLERANCE`/`_TOUCH_EPS`, never a
  fresh arbitrary constant (matches the file's own `_MIN_CONTACT_AREA = CSG_TOLERANCE ** 2`
  precedent).
- `dev/docs/board/to-spec/actor-survey-csg-tier-resolved-geometry-and/spec.md` is implemented exactly
  as written. Do not soften, extend, or "fix" a ruling while building it.
- `actorgraph.classify_pair`/`build_graph` (used by `level graph`) are NOT touched — this item's scope
  is `actor survey` only (`overview.md`). The one addition to `actorgraph.py` is a new, additive
  sibling of `cells_touch_or_overlap` (a depth-returning SAT variant); nothing existing in that module
  changes behavior.
- `dev/docs/direction/` is out of scope — do not touch it.
- Run tests via `bin/test`, never bare `pytest` (`dev/docs/rules/tests.md`). Scope iteration with
  `bin/test -k actor_survey`; run the whole suite once before the final commit.
- Update `docs/reference/actor/survey.md` in the same change (last task below).

## Sequencing (owner, `spec.md` "Sequencing")

Correctness first: `crosses`' resolved-matter fix and csg `contains`→`occupies` both land before the
raw tier rework and output-shape changes — spec's priority is which BEHAVIOR lands first, not that
each fix's code must have zero shared-infrastructure dependency. Both fixes turn out to need the same
exact convex-piece partition machinery, so that machinery is built once, first, and both correctness
fixes wire onto it directly — no throwaway narrow version inside `crosses`' own fix that `occupies`'s
work would later replace. Tasks below follow that order:

1. The exact boolean-CSG evaluator primitives `occupies`/`carves`/`crosses` all need (Tasks 1–2)
2. `crosses` resolved-matter fix + regression fixture, built on Tasks 1–2 (Task 3)
3. `occupies` (Tasks 4–6), `carves` (Task 7), `connects` reachability fixture (Task 8)
4. Raw tier rework (Tasks 9–11)
5. Output shape: bare lines, symmetric left-anchoring (Tasks 12, 14; Task 13 dropped)
6. Docs (Task 15)

**Three questions came up during planning; all three are answered (owner, 2026-09-27) and folded into
`spec.md`, no open blockers remain:**

- Dropped-prefix group marker → no new marker; fixed order + blank separator only (folded into
  `spec.md`'s Output section; Task 12 Step 7 implements it directly).
- `--json` → dropped from this item entirely (folded into `spec.md`'s Output section; Task 13 is a
  no-op stub, skip it).
- `classify_pair`/`level graph` scope → confirmed: `classify_pair`/`build_graph` stay untouched; Task 9
  adds a new, separate, local pure-geometry classifier for `actor survey`'s raw tier instead (folded
  into `spec.md`'s "Removed" bullet).

---

## Research findings (read before starting)

- Every function/line citation in `spec.md` was checked against the current code and **matches
  exactly** — no drift. `_cell_intersection_volume` (519–564), `authored_shape_contains` (567–609),
  the `_source_cells` brush branch (975–977), `_was_solid_before` (1549–1560), `resolved_matter_of`
  (1267–1315), `removed_by` (2110–2138), `_planar_void_contact` (1835), `containment_winner`
  (1990–2025), `_CARVE_TARGET_KINDS` (2081), `crosses_target_eligible` (828–834), `_convex_hull_2d`
  (986–1017) in `actor_survey.py`; `classify_pair` (562–606), `cells_touch_or_overlap` (307–325),
  `_sat_axes` (295–304), `_TOUCH_EPS` (253) in `actorgraph.py`.
- `actor relation` (`uedcli/cli/commands/actor/relation.py`) already exists — `compare`/`find`/`set`,
  plane/footprint/delta geometry. It has no concept of `actor survey`'s CSG magnitudes
  (`touches`-area, `crosses`-depth) today. Migrating those metrics into it is explicitly **not** this
  item's job (`overview.md` scopes this item to `actor survey` only) — this plan does not touch
  `relation.py` or `cli/commands/actor/relation.py`.
- No existing scenario in `uedcli/tests/survey_scenarios.py` matches the spec's worked example
  (`Subtract190 → Add196 → Subtract269 → semisolid184`, `19_Multiport`) — Task 3 adds a new one.
  `nested_niche_with_a_decoration` (an Add wholly inside an oversized Subtract, itself inside a bigger
  Subtract) is the closest existing shape and is reused/adapted for `occupies` matter-branch tests
  (Task 4). No scenario exists for a sealed internal Subtract bubble either — Task 8 adds one.
- The `2026-09-23-actor-survey-csg-kind-and-cost` spike's harness (`kind_semantics.py`,
  `bounded_cost.py`, `collision_clearance.py`) has no exact-evaluator prototype — the evaluator in
  Tasks 1–2 is new work, not a port.
- The old csg `contains` machinery (`containment_winner`, `_containment_candidates`,
  `contains_facts_for`, `VOLUME_TOLERANCE_REL`, `volume_tolerance`, `volumes_tied`) is winner-take-all
  (smallest authored volume wins, ties break toward the later brush) — `occupies` has **no such
  contest**: it is evaluated independently per `(X, S)` pair, and the spec's own "composes where
  containment cannot" section requires that (an Add seated across two Subtracts' voids reports
  `occupies` against BOTH). This machinery becomes dead code the moment `occupies` replaces `contains`
  and must be deleted outright (Task 6), not left orphaned.

---

## Task 1: exact boolean-CSG evaluator — cell splitting primitives

The hardest part. `occupies`/`carves` both need an EXACT (no sampling) measure of a region defined by
an ordered, multi-brush boolean-CSG predicate; Task 3's `crosses` fix needs the same splitting
machinery for a narrower job (partitioning one source cell against later Subtracts only). Build the
splitting primitives here; Task 2 builds the region-partition and point-predicate layer on top of
them; Task 3 consumes `_partition_by_brushes` directly for `crosses`; Tasks 4–7 wire the rest into
`occupies`/`carves`.

**Performance note (unmeasured — flag, don't fake).** Every other neighborhood-bounded routine in this
file cites a real spike measurement of its cost (`classify_pair`'s "12x a full CSG solve on a
208-brush level", `_brush_bounds`' "measured at 22% of the tier's whole runtime"). No such measurement
exists yet for this evaluator: `_partition_by_brushes` (Task 2) calls `_cell_intersection`/
`_subtract_cell` once per piece per brush, and `_polytope_from_planes`' vertex enumeration is
`O(planes^3)`, so cost could compound quickly against a brush-dense neighborhood. Run a timing pass
against a realistic neighborhood before landing `occupies`/`carves` (Tasks 4–7) — do not invent a
number here.

**Design.** Every relevant primitive already exists in fragments:
`_cell_intersection_volume` (519-564) already does H-rep→V-rep→volume for TWO cells' intersection, via
vertex-triple enumeration (`actorgraph._intersect_three_planes`) bounded by a `CSG_TOLERANCE`-padded
box (the poisoned-unbounded-plane guard, board item
`authored-volume-poisoned-by-unbounded-plane`). Refactor its vertex-enumeration core out into a
shared helper that returns the POLYTOPE, not just its volume, then build two more primitives on it:
splitting a cell by one extra half-space, and subtracting one convex cell's volume from another as a
list of convex fragments (standard "convex minus convex = union of ≤k convex pieces," k = the
cutter's own half-space count — clip what's left to each of the cutter's own planes in turn, peeling
off the "strictly outside this plane" fragment before continuing to the next). With those two, an
arbitrary query cell can be partitioned against any ordered list of brushes into pieces each fully
inside or fully outside every one of those brushes — the "split by the ordered earlier/later brushes'
half-spaces into convex sub-pieces" the spec calls for.

**Files:**
- Modify: `uedcli/actor_survey.py:519-564` (`_cell_intersection_volume`) — refactor, same external
  behavior
- Test: `uedcli/tests/test_actor_survey.py`

**Interfaces:**
- Consumes: `actorgraph.ConvexCell(vertices, half_spaces)`, `actorgraph._intersect_three_planes`,
  `actorgraph._VERTEX_EPS`, `cell_volume(cell) -> float` (existing, `actor_survey.py:471`).
- Produces:
  - `_polytope_from_planes(planes: list[tuple[tuple[float,float,float], float]], bounds: tuple | None) -> actorgraph.ConvexCell | None`
  - `_cell_intersection(cell_a: actorgraph.ConvexCell, cell_b: actorgraph.ConvexCell) -> actorgraph.ConvexCell | None`
  - `_cell_intersection_volume(cell_a, cell_b) -> float` (unchanged signature, now a thin wrapper)
  - `_clip_cell(cell: actorgraph.ConvexCell, normal: tuple, offset: float) -> actorgraph.ConvexCell | None`
  - `_subtract_cell(piece: actorgraph.ConvexCell, cutter: actorgraph.ConvexCell) -> list[actorgraph.ConvexCell]`

- [ ] **Step 1: Write the failing tests**

Add to `uedcli/tests/test_actor_survey.py` near the existing `test_cell_volume_of_a_cube_is_exact`
(around line 1475):

```python
def _box_cell(lo, hi):
    """A `ConvexCell` for the axis-aligned box `[lo, hi]`, for testing the splitting primitives
    directly without a whole Actor/Level."""
    x0, y0, z0 = lo
    x1, y1, z1 = hi
    half_spaces = [((1.0, 0.0, 0.0), x1), ((-1.0, 0.0, 0.0), -x0),
                   ((0.0, 1.0, 0.0), y1), ((0.0, -1.0, 0.0), -y0),
                   ((0.0, 0.0, 1.0), z1), ((0.0, 0.0, -1.0), -z0)]
    verts = [(x, y, z) for x in (x0, x1) for y in (y0, y1) for z in (z0, z1)]
    return actorgraph.ConvexCell(vertices=verts, half_spaces=half_spaces)


def test_cell_intersection_returns_the_polytope_not_just_its_volume():
    a = _box_cell((0, 0, 0), (10, 10, 10))
    b = _box_cell((5, 5, 5), (15, 15, 15))
    cell = _cell_intersection(a, b)
    assert cell is not None
    assert cell_volume(cell) == pytest.approx(125.0)  # the shared 5^3 corner


def test_cell_intersection_volume_still_matches_the_refactored_polytope():
    a = _box_cell((0, 0, 0), (10, 10, 10))
    b = _box_cell((5, 5, 5), (15, 15, 15))
    assert _cell_intersection_volume(a, b) == pytest.approx(125.0)


def test_cell_intersection_is_none_for_disjoint_cells():
    a = _box_cell((0, 0, 0), (10, 10, 10))
    b = _box_cell((100, 100, 100), (110, 110, 110))
    assert _cell_intersection(a, b) is None


def test_clip_cell_halves_a_cube():
    cube = _box_cell((0, 0, 0), (10, 10, 10))
    clipped = _clip_cell(cube, (0.0, 0.0, 1.0), 5.0)   # z <= 5
    assert clipped is not None
    assert cell_volume(clipped) == pytest.approx(500.0)


def test_clip_cell_is_none_when_the_half_space_misses_entirely():
    cube = _box_cell((0, 0, 0), (10, 10, 10))
    assert _clip_cell(cube, (0.0, 0.0, 1.0), -5.0) is None   # z <= -5: misses [0,10]


def test_subtract_cell_removes_a_smaller_cube_fully_inside():
    outer = _box_cell((0, 0, 0), (10, 10, 10))
    inner = _box_cell((3, 3, 3), (7, 7, 7))
    pieces = _subtract_cell(outer, inner)
    assert sum(cell_volume(p) for p in pieces) == pytest.approx(1000.0 - 64.0)


def test_subtract_cell_is_unchanged_when_the_cutter_misses_entirely():
    outer = _box_cell((0, 0, 0), (10, 10, 10))
    far = _box_cell((100, 100, 100), (110, 110, 110))
    pieces = _subtract_cell(outer, far)
    assert sum(cell_volume(p) for p in pieces) == pytest.approx(1000.0)
```

Import `pytest` and `actorgraph` at the top of the test file if not already present (both are already
imported by the existing test suite).

- [ ] **Step 2: Run them, confirm they fail**

`bin/test -k "cell_intersection or clip_cell or subtract_cell"`
Expected: FAIL — `_cell_intersection`, `_clip_cell`, `_subtract_cell` do not exist yet.

- [ ] **Step 3: Implement the primitives**

Replace `_cell_intersection_volume` (`actor_survey.py:519-564`) with:

```python
def _polytope_from_planes(planes: list[tuple[tuple[float, float, float], float]],
                          bounds: tuple | None) -> "actorgraph.ConvexCell | None":
    """The convex polytope `{p : n.p <= d for (n, d) in planes}`, via H-rep -> V-rep vertex
    enumeration: every plane TRIPLE's intersection point (`actorgraph._intersect_three_planes`),
    kept only when it also satisfies every other plane. `bounds` (`(lo, hi)`, already padded), when
    given, additionally drops a candidate vertex outside it BEFORE the half-space check -- the
    poisoned-unbounded-plane guard (board item `authored-volume-poisoned-by-unbounded-plane`): two
    near-parallel planes intersect at a point whose distance from either blows up as they approach
    parallel, and nothing else here catches a resulting vertex light-years from the real geometry.
    None when fewer than 4 vertices survive (empty or degenerate)."""
    eps = actorgraph._VERTEX_EPS
    verts: list = []
    for i, j, k in itertools.combinations(range(len(planes)), 3):
        p = actorgraph._intersect_three_planes(planes[i], planes[j], planes[k])
        if p is None:
            continue
        if bounds is not None:
            lo, hi = bounds
            if any(p[m] < lo[m] or p[m] > hi[m] for m in range(3)):
                continue
        if not all(n[0] * p[0] + n[1] * p[1] + n[2] * p[2] <= d + eps for n, d in planes):
            continue
        if not any(math.dist(p, q) < eps for q in verts):
            verts.append(p)
    if len(verts) < 4:
        return None
    return actorgraph.ConvexCell(vertices=verts, half_spaces=planes)


def _cell_intersection(cell_a, cell_b) -> "actorgraph.ConvexCell | None":
    """The convex intersection `cell_a INTERSECT cell_b` as its own polytope (not just its volume)
    -- `_polytope_from_planes` over both cells' half-spaces, bounded by their combined bounding
    boxes padded by `CSG_TOLERANCE` (any real point of the intersection lies inside both cells' own
    boxes, so a candidate outside the padded combined box is provably not a real vertex here). None
    for cells whose boxes don't meet, or a genuinely empty/degenerate intersection."""
    a_lo, a_hi = _cell_bounds(cell_a)
    b_lo, b_hi = _cell_bounds(cell_b)
    lo = tuple(max(a_lo[i], b_lo[i]) - CSG_TOLERANCE for i in range(3))
    hi = tuple(min(a_hi[i], b_hi[i]) + CSG_TOLERANCE for i in range(3))
    if any(lo[i] > hi[i] for i in range(3)):
        return None
    return _polytope_from_planes(list(cell_a.half_spaces) + list(cell_b.half_spaces), (lo, hi))


def _cell_intersection_volume(cell_a, cell_b) -> float:
    """The volume of `cell_a INTERSECT cell_b`. Thin wrapper over `_cell_intersection` -- see that
    function for the vertex-enumeration pipeline and the poisoned-unbounded-plane guard."""
    cell = _cell_intersection(cell_a, cell_b)
    return cell_volume(cell) if cell is not None else 0.0


def _clip_cell(cell, normal, offset: float) -> "actorgraph.ConvexCell | None":
    """`cell` intersected with the single half-space `normal . p <= offset` -- `_cell_intersection`
    with one extra plane instead of a second full cell, bounded by `cell`'s OWN box padded by
    `CSG_TOLERANCE` (no second cell to intersect against). None when the half-space excludes `cell`
    entirely, or the result is degenerate."""
    lo, hi = _cell_bounds(cell)
    bounds = (tuple(c - CSG_TOLERANCE for c in lo), tuple(c + CSG_TOLERANCE for c in hi))
    return _polytope_from_planes(list(cell.half_spaces) + [(normal, offset)], bounds)


def _subtract_cell(piece, cutter) -> list:
    """`piece` minus `cutter`'s convex volume, as a list of disjoint convex pieces (possibly empty).
    Standard convex-polytope subtraction by sequential half-space clipping: for each of `cutter`'s
    own half-spaces in turn, split off whatever of what's left lies STRICTLY OUTSIDE this one plane
    (definitely not in `cutter`, since it fails this plane alone) into the output, and keep only the
    inside-this-plane remainder to test against the next -- `piece` minus a convex region is the
    union of at most `len(cutter.half_spaces)` such fragments. Reuses `_clip_cell`'s own vertex
    enumeration and bounds guard; introduces no new tolerance."""
    remaining = [piece]
    outside: list = []
    for normal, offset in cutter.half_spaces:
        next_remaining = []
        for p in remaining:
            out_part = _clip_cell(p, tuple(-c for c in normal), -offset)
            if out_part is not None:
                outside.append(out_part)
            keep_part = _clip_cell(p, normal, offset)
            if keep_part is not None:
                next_remaining.append(keep_part)
        remaining = next_remaining
    return outside
```

- [ ] **Step 4: Run the new tests, confirm they pass**

`bin/test -k "cell_intersection or clip_cell or subtract_cell"` → PASS

- [ ] **Step 5: Run the existing `_cell_intersection_volume`/`authored_shape_contains` tests — this was a refactor, nothing about their behavior should change**

`bin/test -k "authored_shape_contains or cell_volume"` → all still PASS (same numeric results,
`_cell_intersection_volume`'s call sites are unchanged).

- [ ] **Step 6: Commit**

```bash
git add uedcli/actor_survey.py uedcli/tests/test_actor_survey.py
git commit -m "Add cell-splitting primitives for the exact boolean-CSG evaluator"
```

**Bug found during Task 9 (foundational, fixed ahead of it, own commit):** `_polytope_from_planes`
concatenated both cells' half-spaces with no dedup, so two cells sharing an exact coincident plane
(the `coincides` case -- identical/stacked brushes) double-counted that shared face in
`cell_volume`, inflating `_cell_intersection_volume` ~2x and making `authored_shape_contains` (and
`coincides`) unreachable for coincident brushes. Fixed by deduping `planes` via the existing
`_same_plane` at the top of `_polytope_from_planes`, before Task 9's own commit (shared
infrastructure, not raw-tier-specific).

---

## Task 2: exact boolean-CSG evaluator — region partition and last-writer helpers

Build the region-partition function and the two point-level helpers the spec names explicitly: a
full-order last-writer walk (optionally excluding one actor), and a victim-specific
matter-just-before-a-Subtract test. `_partition_by_brushes`/`_piece_centroid` are also consumed
directly by Task 3's `crosses` fix (partitioning a source cell against later Subtracts is the same
splitting job, against a narrower brush list) — build them here, not duplicated there.

**Placement matters here** (`CLAUDE.md`: helpers above their callers). `_piece_centroid`/
`_partition_by_brushes`/`CARVE_VOLUME_EPS` depend only on Task 1's primitives plus the existing
`cell_volume`/`decompose_convex` — all defined earlier in the file than `_source_cells`
(`actor_survey.py:957`) — so place them BEFORE `_source_cells`, since Task 3's rewritten
`_source_cells` calls `_partition_by_brushes`/`_piece_centroid` directly. `_last_writer_excluding`/
`_is_void_excluding`/`_victim_matter_just_before` depend on `_in_authored_volume`/`resolved_matter_of`/
`_was_solid_before`, which live later in the file (`actor_survey.py:1256-1560`); place those three
AFTER `_was_solid_before` instead — they are only consumed by Tasks 4–7's `occupies`/`carves`, much
later in the file, and calling a name defined later in the same module works fine at runtime, but
reading top-to-bottom in call order is the point.

**Files:**
- Modify: `uedcli/actor_survey.py` (two insertion points — see Placement above)
- Test: `uedcli/tests/test_actor_survey.py`
- Test fixture: `uedcli/tests/survey_scenarios.py` (one new fixture, Step 1)

**Interfaces:**
- Consumes: `_cell_intersection`, `_subtract_cell` (Task 1), `actorgraph.decompose_convex`,
  `SurveyContext.csg_order`/`csg_index`/`kinds`/`cells`, `_in_authored_volume(ctx, actor, point) -> bool`
  (existing, `actor_survey.py:1256`), `_was_solid_before(ctx, subtract, point) -> bool` (existing,
  `actor_survey.py:1549`).
- Produces:
  - `_piece_centroid(cell: actorgraph.ConvexCell) -> tuple[float, float, float]`
  - `_partition_by_brushes(query_cell: actorgraph.ConvexCell, brush_actors: list, ctx: SurveyContext) -> list[actorgraph.ConvexCell]`
  - `_last_writer_excluding(ctx: SurveyContext, point, *, exclude: str | None = None) -> str | None`
  - `_is_void_excluding(ctx: SurveyContext, point, *, exclude: str | None = None) -> bool`
  - `_victim_matter_just_before(ctx: SurveyContext, victim, subtract, point) -> bool`
  - `CARVE_VOLUME_EPS: float` (named constant)

- [ ] **Step 1: Add a fixture pinning the refill-then-recut shape**

The review found the test this fixture backs (Step 2 below) didn't actually exercise what its
docstring claimed — it asserted against `partial_and_total_carves`, which has no refilling Add at
all. Add a real one, near `partial_and_total_carves` in `survey_scenarios.py`:

```python
def victim_matter_refilled_then_recut() -> Scenario:
    """Trunk order: Shell, Room, Block, FirstCut, Refill, SecondCut.

    * `Shell`     2048^3 Add at (0, 0, 0)
    * `Room`      1024^3 Subtract at (0, 0, 0)
    * `Block`     256^3 Add at (0, 0, 0)                  — the victim, x,y,z in [-128, 128]
    * `FirstCut`  128 x 512 x 512 Subtract at (-64, 0, 0) — takes Block's -X half, x in [-128, 0]
    * `Refill`    128 x 512 x 512 Add at (-64, 0, 0)      — a DIFFERENT actor re-adds matter over
      the exact same region `FirstCut` just cut. Generic solidity reads True there again, but it is
      `Refill`'s matter, never `Block`'s own.
    * `SecondCut` 128 x 512 x 512 Subtract at (-64, 0, 0) — recarves the same region.

    Pins the distinction `_victim_matter_just_before` exists for: at p=(-64,0,0),
    `_was_solid_before(SecondCut, p)` (generic) reads True -- `Refill` is the last writer there and
    it is an Add -- but `_victim_matter_just_before(Block, SecondCut, p)` must read False, because
    `Block`'s OWN matter at p was already gone the moment `FirstCut` ran, long before `Refill` or
    `SecondCut`. Counting this point toward `carves(SecondCut, Block)` would be exactly the
    generic-solidity bug the spec's "restrict to victim's own matter" ruling warns about.
    """
    return _scenario([
        brush("Shell", (2048, 2048, 2048), (0, 0, 0)),
        brush("Room", (1024, 1024, 1024), (0, 0, 0), csg="subtract"),
        brush("Block", (256, 256, 256), (0, 0, 0)),
        brush("FirstCut", (128, 512, 512), (-64, 0, 0), csg="subtract"),
        brush("Refill", (128, 512, 512), (-64, 0, 0)),
        brush("SecondCut", (128, 512, 512), (-64, 0, 0), csg="subtract"),
    ])
```

- [ ] **Step 2: Write the failing tests**

```python
def test_partition_by_brushes_splits_a_cell_around_a_carving_subtract():
    s = survey_scenarios.pillar_in_room()   # Room(subtract), Pillar(add), Cutter(subtract, right half)
    ctx = build_context(s.level, s.index, "Pillar", s.defaults)
    pillar_cell = actorgraph.decompose_convex(s.level.actors["Pillar"], cache=ctx.cells)[0]
    cutter = s.level.actors["Cutter"]
    pieces = _partition_by_brushes(pillar_cell, [cutter], ctx)
    # Pillar is 128x128x512 = 8388608 total; Cutter takes its right half over part of its height.
    assert sum(cell_volume(p) for p in pieces) == pytest.approx(cell_volume(pillar_cell))


def test_is_void_excluding_matches_the_native_solidity_oracle_with_no_exclusion():
    """`_is_void_excluding(ctx, p)` with no exclusion asks "per the FULL trunk order, is p void" --
    on `pillar_in_room` that must agree with the native solver's own pooled solidity oracle, since
    the leading world-pass brush (`Room`) is a Subtract, not an Add: `resolved_matter_of`'s
    "leading-Add shell inversion" caveat (its own docstring) only inverts the oracle when the FIRST
    brush is an Add, which does not apply here.

    (An earlier version of this test compared `_is_void_excluding` against `_was_solid_before`,
    which asks a different question -- solid just BEFORE one given Subtract, not the fully resolved
    state. They happen to agree at `(40, 0, 0)`, where `Cutter` -- the last actor in trunk order --
    reaches a point `Pillar`'s matter already occupied, but not at `(100, 100, 0)`: also inside
    `Cutter`'s carve region, but outside `Pillar`'s own box, so `Room` (a Subtract) is the nearest
    earlier writer there and `_was_solid_before(Cutter, p)` is False, while `Cutter` is still the
    last writer overall and `_is_void_excluding(p)` is True. Neither the original assertion nor its
    un-negated form is a general law; this test checks the actual invariant instead.)
    """
    pytest.importorskip("uedcli_native")
    s = survey_scenarios.pillar_in_room()
    ctx = build_context(s.level, s.index, "Pillar", s.defaults)
    for p in [(40.0, 0.0, 0.0), (100.0, 100.0, 0.0), (-40.0, 0.0, 0.0)]:
        assert _is_void_excluding(ctx, p) == (not ctx.probe.solidity.point_is_solid(p)), p


def test_last_writer_excluding_skips_the_named_actor():
    s = survey_scenarios.nested_niche_with_a_decoration()
    ctx = build_context(s.level, s.index, "Additive4", s.defaults)
    p = (0.0, 128.0, 0.0)   # inside Additive4's own volume, inside Subtract3's carved region
    excluding_self = _last_writer_excluding(ctx, p, exclude="Additive4")
    assert excluding_self != "Additive4"


def test_victim_matter_just_before_excludes_matter_refilled_after_a_later_subtract():
    # sub1 (FirstCut) carves victim (Block); a later Add (Refill) refills the SAME point; a
    # still-later Subtract (SecondCut) is the one under test -- `_victim_matter_just_before(Block,
    # SecondCut, p)` must be False, because it is Refill's matter there, not Block's own, just before
    # SecondCut ran. Demonstrates the exact divergence from generic `_was_solid_before`, which DOES
    # read solid there (Refill is its last writer) -- the bug the spec's "restrict to victim's own
    # matter" ruling exists to prevent.
    s = survey_scenarios.victim_matter_refilled_then_recut()
    ctx = build_context(s.level, s.index, "Block", s.defaults)
    p = (-64.0, 0.0, 0.0)
    block, second_cut = s.level.actors["Block"], s.level.actors["SecondCut"]
    assert _was_solid_before(ctx, second_cut, p) is True         # generic: Refill reads as solid
    assert _victim_matter_just_before(ctx, block, second_cut, p) is False   # victim-specific: correct
```

- [ ] **Step 3: Run them, confirm they fail**

`bin/test -k "partition_by_brushes or last_writer_excluding or is_void_excluding or victim_matter_just_before"`
Expected: FAIL — none of these names exist yet.

- [ ] **Step 4: Implement**

Add `CARVE_VOLUME_EPS`, `_piece_centroid`, `_partition_by_brushes` to `actor_survey.py` BEFORE
`_source_cells` (`actor_survey.py:957`) — e.g. directly after `authored_shape_contains`:

```python
# The resolved tier's own volume floor -- derived from CSG_TOLERANCE the same way _MIN_CONTACT_AREA
# derives an area floor from it (CSG_TOLERANCE ** 2): a cubic volume below CSG_TOLERANCE ** 3 is not
# a real geometric distinction in a resolved model, any more than an area below CSG_TOLERANCE ** 2
# is. Used both to drop float-dust pieces from `_partition_by_brushes` and as `carves`'s own `> eps`
# volume threshold (spec: "a named volume tolerance for carves's > eps, resolved tier -- CARVE_AREA_EPS
# was an area and does not transfer").
CARVE_VOLUME_EPS = CSG_TOLERANCE ** 3


def _piece_centroid(cell) -> tuple:
    """A convex cell's vertex centroid -- always interior to the cell (a convex hull's centroid
    always is), so it is a valid representative point for ANY per-point predicate that is constant
    over the whole cell (see `_partition_by_brushes`)."""
    n = len(cell.vertices)
    return tuple(sum(v[i] for v in cell.vertices) / n for i in range(3))


def _partition_by_brushes(query_cell, brush_actors, ctx: SurveyContext) -> list:
    """`query_cell` split into convex sub-pieces, each fully INSIDE or fully OUTSIDE every one of
    `brush_actors`' own decomposed cells -- an ARRANGEMENT over the query region, not an attribution
    to any one brush. Every surviving piece's membership in every listed brush is therefore constant
    across the whole piece, which is what lets a per-brush point-predicate be evaluated ONCE per
    piece (at its centroid, `_piece_centroid`) and be exactly right for every point in it -- the
    "split by the ordered earlier/later brushes' half-spaces into convex sub-pieces" the spec's
    `occupies` section calls for. Order of `brush_actors` does not matter for the SPLIT itself (only
    for how a caller later reads "last writer" off the pieces); pieces with volume at or below
    `CARVE_VOLUME_EPS` are dropped as float dust, not real geometry."""
    pieces = [query_cell]
    for actor in brush_actors:
        for cutter in actorgraph.decompose_convex(actor, cache=ctx.cells):
            next_pieces = []
            for p in pieces:
                inside = _cell_intersection(p, cutter)
                if inside is not None:
                    next_pieces.append(inside)
                next_pieces.extend(_subtract_cell(p, cutter))
            pieces = next_pieces
    return [p for p in pieces if cell_volume(p) > CARVE_VOLUME_EPS]
```

Add `_last_writer_excluding`, `_is_void_excluding`, `_victim_matter_just_before` AFTER
`_was_solid_before` (`actor_survey.py:1549-1560`) — they need it and `_in_authored_volume`, both
defined earlier in that neighborhood, and are consumed only by Tasks 4–7, much later in the file:

```python
def _last_writer_excluding(ctx: SurveyContext, point, *, exclude: str | None = None) -> str | None:
    """The NAME of the LAST brush in `ctx.csg_order` (latest first) whose authored volume reaches
    `point`, skipping `exclude` if given, or None when nothing in the order reaches it there.
    Generalizes `_was_solid_before` (which only walks brushes earlier than one given Subtract, and
    cannot exclude an arbitrary Add) and `resolved_matter_of` (which answers for one actor only) into
    the full-order, exclusion-capable walk `occupies`'s condition (iii) needs."""
    for a in reversed(ctx.csg_order):
        if a.name == exclude:
            continue
        if _in_authored_volume(ctx, a, point):
            return a.name
    return None


def _is_void_excluding(ctx: SurveyContext, point, *, exclude: str | None = None) -> bool:
    """Is `point` VOID once the whole trunk (minus `exclude`, if given) has resolved? True only when
    a real last-writer reaches the point AND it is a Subtract -- no writer at all is the `MAP NEW`
    default-solid world (`_was_solid_before`'s own base case), which is NOT void."""
    last = _last_writer_excluding(ctx, point, exclude=exclude)
    return last is not None and ctx.kinds[last] == "subtract"


def _victim_matter_just_before(ctx: SurveyContext, victim, subtract, point) -> bool:
    """Was `point` still `victim`'s OWN surviving matter at the moment JUST BEFORE `subtract` ran --
    in `victim`'s own authored volume, and not yet overwritten by any Subtract between `victim`'s own
    position in `ctx.csg_order` and `subtract`'s? Deliberately narrower than `_was_solid_before`
    (which would count ANY actor's matter as solid-before-`subtract`, wrongly crediting
    `carves(subtract, victim)` for a point a DIFFERENT Add refilled after `victim` was cut and before
    `subtract` ran) -- the victim-specific delta the retired `removed_by` got right via a
    counterfactual solve; this is its exact, per-point equivalent."""
    if not _in_authored_volume(ctx, victim, point):
        return False
    v_i = ctx.csg_index.get(victim.name, -1)
    s_i = ctx.csg_index.get(subtract.name, len(ctx.csg_order))
    between = ctx.csg_order[v_i + 1:s_i]
    return not any(ctx.kinds[a.name] == "subtract" and _in_authored_volume(ctx, a, point)
                   for a in between)
```

- [ ] **Step 5: Run the new tests, confirm they pass**

`bin/test -k "partition_by_brushes or last_writer_excluding or is_void_excluding or victim_matter_just_before"` → PASS

- [ ] **Step 6: Commit**

```bash
git add uedcli/actor_survey.py uedcli/tests/survey_scenarios.py uedcli/tests/test_actor_survey.py
git commit -m "Add the region-partition and last-writer helpers for occupies/carves"
```

**Bug found during Task 15's doc-example prep (own commit):** `_victim_matter_just_before`'s
`csg_order[v_i + 1:s_i]` slice assumed `subtract` always follows `victim` (the S-after-A shape).
When `subtract` precedes `victim` instead (`s_i <= v_i` — the S-before-A shape, spec's own "duals"
rule: only `occupies` is possible there), Python does not raise or reverse the slice on
`start > stop` — it is empty, so `not any([])` read vacuously True, and `carves(subtract, victim)`
fired even though `subtract` ran before `victim` existed. Live repro: `pillar_in_room`'s `Room`
(Subtract, trunk-first) reported `Room --carves--> Pillar` (Add, trunk-second, fully enclosed).
Fixed by guarding `s_i <= v_i` and returning `False` before building `between`; pinned with
`test_carves_never_fires_for_a_subtract_that_precedes_its_victim_in_trunk_order`.

---

## Task 3: `crosses` resolved-matter fix + worked-example regression fixture

Correctness-critical (spec's own framing), but it needs Tasks 1–2's convex-piece partition machinery
to fix correctly, so it lands third in build order — spec's sequencing intent is about which BEHAVIOR
matters most / lands first among the correctness fixes, not that this fix's own code must have zero
shared-infrastructure dependency (see the top-level Sequencing section).

`_source_cells` (`actor_survey.py:975-977`) feeds `penetration_depth` a source's AUTHORED decomposed
cells with no resolved filter, so an Add whose matter a later Subtract carved away still "crosses" an
actor sitting in that carved void.

**Why a per-corner-vertex filter does not work (rejected design, caught in review).** A first-pass fix
tested each authored cell's own corner vertices against `resolved_matter_of` and kept only cells whose
corners all survived. This does not fix the bug: a carve interior to a cell, touching none of its
corners, is the ORDINARY case (a Subtract carving a chunk out of the middle of a larger Add), not an
edge case. In the worked example below, `Middle` is a 256^3 box (corners at +/-128 on every axis) and
`Later` is a 192^3 Subtract centered on the same point, carving only the interior +/-96 region — every
one of `Middle`'s 8 authored corners sits OUTSIDE `Later`'s carved region, so a per-corner test finds
all 8 corners still "solid" and filters nothing out. `Middle`'s cell would reach `penetration_depth`
completely unfiltered and the false-positive `crosses` would still fire exactly as before any fix.

**The correct fix: partition, then filter by point membership.** Split each of the source's
`decompose_convex` cells into convex sub-pieces by the LATER-in-trunk-order Subtracts' half-spaces
(`_partition_by_brushes`, Task 2), then keep only the pieces whose matter actually SURVIVES
(`resolved_matter_of` tested once at each piece's centroid, `_piece_centroid` — valid because
`_partition_by_brushes` makes every point of one piece share the same answer to any per-brush
predicate). Each surviving PIECE — never the raw authored cell — is what reaches `penetration_depth`.
This is still "a point-membership filter on the straddle points / footprint, not a reshape of the
source convex cells into one (possibly non-convex) shape" (spec's own ruling): the output stays a LIST
of convex pieces, never merged into one non-convex hull — the same multi-cell-per-brush precedent
`_source_cells`' own docstring already establishes for a non-convex brush (each `decompose_convex`
cell tested independently); this just adds one more level of splitting, by later-subtract
half-spaces, on top of it.

**Files:**
- Modify: `uedcli/actor_survey.py:957-983` (`_source_cells` only — its two call sites in
  `crosses_facts_for` are unchanged, same call shape)
- Test: `uedcli/tests/test_actor_survey.py` — remove the strict `xfail` from
  `test_touches_fires_for_a_blind_pockets_carve_victim` and add three new regression tests for the
  board item this fix resolves (Step 7); rewrite
  `test_crosses_fires_for_an_add_poking_through_a_niche_wall_and_names_only_the_immediate_owner` as
  `test_touches_fires_for_a_carved_shelf_and_names_only_the_immediate_niche` (Step 10), delete
  `test_crosses_reports_the_reverse_direction_when_the_surveyed_actor_is_the_target` (Step 11), add
  `test_crosses_fires_for_a_semisolid_partially_overlapping_an_add` (Step 12 — the suite's first
  genuine brush-sourced `crosses` regression, unrelated to this bug), swap the fixture under
  `test_touches_and_crosses_are_mutually_exclusive_for_one_pair` (Step 13), re-fixture
  `test_crosses_dedupes_to_one_fact_per_src_dst_pair` (Step 14) — these last two, plus Steps 10-11,
  depend on this task's other fixture's pre-fix (buggy) `crosses` fact, per review round 4/5
- Test fixture: `uedcli/tests/survey_scenarios.py` — the new worked-example fixture (Step 1), plus
  correct `shelf_pokes_through_a_niche_wall`'s own docstring (Step 9), which described the bug this
  task fixes as the intended behavior, the Semisolid-crossing fixture (Step 12), and a new
  collision-extent dedup fixture (Step 14)
- Board: `git mv dev/docs/board/inbox/crosses-fires-on-a-subtract-s-carve-victim` to `done/` (Step 8)
  once the fix and its regression tests are confirmed landed

**Interfaces:**
- Consumes: `resolved_matter_of(ctx: SurveyContext, actor, point) -> bool` (existing,
  `actor_survey.py:1267`), `_partition_by_brushes`, `_piece_centroid` (Task 2), `SurveyContext`
  (existing).
- Produces: `_source_cells(ctx, actor) -> list[list[tuple[float,float,float]]] | None` — same
  signature and return shape, now filtered by partition + point membership instead of reshaped or
  filtered per corner.

- [ ] **Step 1: Add the worked-example fixture to `survey_scenarios.py`**

Add after `shelf_pokes_through_a_niche_wall` (around line 292):

```python
def later_subtract_carves_an_add_that_encloses_a_semisolid() -> Scenario:
    """The spec's own worked example (`19_Multiport`, `Brush190/196/269/184`), rebuilt as a minimal
    fixture. Trunk order: Outer, Earlier, Middle, Later, Enclosed.

    * `Outer`    2048^3 Subtract at (0, 0, 0)            — the void everything else lives in
    * `Earlier`  512^3 Subtract at (600, 0, 0)           — precedes `Middle`; does not carve it
      (x in [344, 856], well clear of `Middle`'s [-128, 128])
    * `Middle`   256^3 Add at (0, 0, 0)                  — x,y,z in [-128, 128]
    * `Later`    192^3 Subtract at (0, 0, 0)             — x,y,z in [-96, 96], carves `Middle`'s
      matter from the region it shares with `Enclosed`, and fully encloses `Enclosed`
    * `Enclosed` 64^3 Add, `poly_flags=PF_SEMISOLID`, at (0, 0, 0)  — x,y,z in [-32, 32], fully
      inside `Later`'s void

    Before the fix: `_source_cells(Middle)` feeds `penetration_depth` `Middle`'s AUTHORED cells, so
    `Middle` (whose matter at `Enclosed`'s location was carved away by `Later`) still reports
    `crosses(Enclosed)`. After the fix: `Middle` has no resolved matter left adjacent to `Enclosed`
    (it was carved out by `Later`), so `crosses` is silent between them; raw still reports
    `Middle encloses Enclosed` (Middle's AUTHORED volume, pre-CSG, does contain Enclosed).
    """
    return _scenario([
        brush("Outer", (2048, 2048, 2048), (0, 0, 0), csg="subtract"),
        brush("Earlier", (512, 512, 512), (600, 0, 0), csg="subtract"),
        brush("Middle", (256, 256, 256), (0, 0, 0)),
        brush("Later", (192, 192, 192), (0, 0, 0), csg="subtract"),
        brush("Enclosed", (64, 64, 64), (0, 0, 0), poly_flags=PF_SEMISOLID),
    ])
```

- [ ] **Step 2: Write the failing test**

Add to `uedcli/tests/test_actor_survey.py` near `test_crosses_never_fires_from_a_subtract` (around
line 634):

```python
def test_crosses_uses_resolved_matter_not_authored_cells():
    s = survey_scenarios.later_subtract_carves_an_add_that_encloses_a_semisolid()
    ctx = build_context(s.level, s.index, "Middle", s.defaults)
    facts = crosses_facts_for(ctx)
    assert not any(f.dst == "Enclosed" for f in facts), (
        "Middle's matter at Enclosed's location was carved away by Later; it must not report "
        "crosses against a carved-out void")
```

- [ ] **Step 3: Run it, confirm it fails**

`bin/test -k test_crosses_uses_resolved_matter_not_authored_cells -v`
Expected: FAIL — `Middle --crosses--> Enclosed` is present (the bug).

- [ ] **Step 4: Fix `_source_cells`**

```python
def _source_cells(ctx: SurveyContext, actor) -> list[list[tuple[float, float, float]]] | None:
    """... (existing docstring, plus:) Filtered to the SURVIVING matter only: each authored cell is
    split into convex sub-pieces by every Subtract LATER than `actor` in trunk order
    (`_partition_by_brushes`), and a piece is kept only when `resolved_matter_of` still holds at its
    centroid -- a point-membership filter on the straddle points, never a reshape of the convex cells
    into one (possibly non-convex) hull: `resolved_matter_of` of an Add is "authored body minus later
    subtracts", possibly non-convex, and `penetration_depth`'s own per-cell convex footprint
    (`_convex_hull_2d`) requires each group to stay convex. A per-corner-vertex test cannot do this --
    a carve interior to a cell, touching none of its corners, is the ordinary case, not an edge case
    (see this function's own worked-example regression). A cell with no surviving piece at all
    contributes nothing crossable."""
    if actor.brush is not None:
        cells = actorgraph.decompose_convex(actor, cache=ctx.cells)
        later_subtracts = [a for a in ctx.csg_order[ctx.csg_index.get(actor.name, len(ctx.csg_order)) + 1:]
                           if ctx.kinds[a.name] == "subtract"]
        groups = []
        for cell in cells:
            for piece in _partition_by_brushes(cell, later_subtracts, ctx):
                if resolved_matter_of(ctx, actor, _piece_centroid(piece)):
                    groups.append([tuple(float(c) for c in v) for v in piece.vertices])
        return groups or None
    ext = collision_extent(actor, ctx.defaults)
    if ext is None or actor.location is None:
        return None
    radius, height = ext
    loc = tuple(float(c) for c in actor.location)
    return [cylinder_sample_points(loc, radius, height)]
```

`ctx.csg_index.get(actor.name, len(ctx.csg_order))` defaults to "after everything" for an actor not in
`csg_order` at all (a Mover, always excluded from world CSG) — the slice is then empty, so
`later_subtracts` is `[]` and the loop below degenerates to the identity partition, matching
`resolved_matter_of`'s own rule that nothing in the trunk can cut a Mover. The same happens for a
Semisolid: `csg_order` places every semisolid after every Add/Subtract, so nothing after one is ever a
Subtract, and `later_subtracts` is again always `[]` — no splitting, matching
`resolved_matter_of`'s "no Subtract in the trunk can cut a semisolid" rule. Only an Add source (the
actual bug) ever gets a non-empty `later_subtracts` and a real split.

**Hand-trace confirming Step 4 passes the Step 2 test.** `Middle` decomposes to one cell, the box
`[-128,128]^3`. `Middle`'s only later Subtract is `Later` (`Earlier` precedes `Middle`; `Enclosed` is
not a Subtract) — `later_subtracts = [Later]`. `_partition_by_brushes(middle_cell, [Later], ctx)`
intersects `Later`'s own cell (`[-96,96]^3`) against `Middle`'s: one piece is the shared
`[-96,96]^3` box (the region `Later` carved away), and `_subtract_cell` produces the remaining shell
pieces of `Middle`'s box outside `[-96,96]^3` in each axis (up to 6 slab fragments, e.g. `x in
[96,128], y,z in [-128,128]`, and the mirror/rotations). Testing each piece's centroid:
`resolved_matter_of(Middle, centroid)` is False for the `[-96,96]^3` piece (its centroid, the origin,
sits inside both `Middle`'s and `Later`'s authored volumes, and `Later` is a Subtract after `Middle`)
— dropped. Every shell-fragment piece's centroid sits OUTSIDE `[-96,96]^3` in at least one axis, so
none is inside `Later` — `resolved_matter_of` is True for all of them — kept. The surviving groups are
therefore exactly `Middle`'s outer shell, none of which extends anywhere near `Enclosed`'s own
footprint (`[-32,32]^3`, deep inside the carved-out `[-96,96]^3` region) — `penetration_depth` finds no
footprint overlap between any surviving piece and any face near `Enclosed`, so `crosses` never fires.
`Middle encloses Enclosed` still holds in the RAW tier (Task 9-10), which reasons over `Middle`'s
AUTHORED box directly and never calls `_source_cells`.

- [ ] **Step 5: Run it, confirm it passes**

`bin/test -k test_crosses_uses_resolved_matter_not_authored_cells -v` → PASS

- [ ] **Step 6: Run the whole test file to find every regression**

`bin/test uedcli/tests/test_actor_survey.py` — the whole file, not `-k "crosses"`: the fix also flips
`test_touches_fires_for_a_blind_pockets_carve_victim` (`:936-952`) from a strict-`xfail`'d failure to
an unexpected PASS, which `strict=True` turns into a hard failure of its own — a `-k "crosses"` filter
would never select that test by name (it has no `crosses` in it) and would miss this until the final
whole-suite run, tasks later. Expect two categories of non-pass here, both handled in Step 7 next: that
strict-xfail collision, and every existing `test_crosses_*`/`test_touches_and_crosses_*` test that
depended on this fixture's pre-fix (buggy) fact, fixed below in Steps 9-11, 13-14 — `shelf_pokes_through_a_niche_wall`'s
`Additive4` IS carved by a later Subtract (`Subtract3`), so it is not covered by the "no fixture
carves the source" argument that holds for every OTHER existing fixture (`peg_buried_in_a_wall`,
`room_with_a_flush_mounted_prop`, etc. — none of THOSE authors a matter source that a later Subtract
in the same trunk then re-carves, so `later_subtracts` is empty for them, `_partition_by_brushes`
degenerates to the identity, and every existing fact there is unaffected). If anything else
regresses, re-read `resolved_matter_of`'s docstring on why it reads authored volumes, never the
pooled solidity oracle.

- [ ] **Step 7: resolve the strict-xfail collision — un-xfail the blind-pocket test, pin the board
  item's other three fixtures (its own table's two, plus its closing paragraph's fourth case)**

`dev/docs/board/inbox/crosses-fires-on-a-subtract-s-carve-victim/` (open, p1) tracks this exact bug on
three table fixtures — `blind_pocket_in_a_wall`, `two_rooms_side_by_side`, `a_doorway_through_a_wall_seam`
— plus a fourth case named only in its closing paragraph, `Rock --crosses(1.47e+03uu)--> Crate` on the
already-committed `an_oversized_corridor_past_its_room` fixture (Add-to-Add, where `Room`/`Corridor`,
Subtracts later than `Rock` in trunk order, carve away the matter that would otherwise reach `Crate`).
Step 4's fix resolves all four. Left as-is, `test_touches_fires_for_a_blind_pockets_carve_victim`
(`uedcli/tests/test_actor_survey.py:936-952`) breaks `bin/test` the moment Step 4 lands: it is
`@pytest.mark.xfail(strict=True)`, its `reason=` naming this exact bug, and `strict=True` turns an
unexpected pass into a hard failure. Fix all three fixtures here.

Remove the `xfail` marker (and its `reason=`/`strict=` args) from
`test_touches_fires_for_a_blind_pockets_carve_victim` — the test body itself is unchanged, its own
assertions now just pass:

```python
def test_touches_fires_for_a_blind_pockets_carve_victim():
    """The same carve-victim fact as above, on a fixture with none of `niche_carved_into_wall`'s
    quirks -- an ordinary solve and a carve that stops inside the wall."""
    pytest.importorskip("uedcli_native")
    sc = scen.blind_pocket_in_a_wall()
    ctx = actor_survey.build_context(sc.level, sc.index, "Pocket", sc.defaults)
    assert actor_survey.pair_touches(ctx, ctx.level.actors["Pocket"], ctx.level.actors["Wall"])
    facts = actor_survey.touches_facts_for(ctx)
    assert any(f.src == "Pocket" and f.dst == "Wall" for f in facts), facts
```

Add regression tests for the board item's other two fixtures, near it:

```python
def test_crosses_does_not_fire_for_a_room_carved_into_solid_rock():
    """Board item `crosses-fires-on-a-subtract-s-carve-victim`: `Rock` wrongly reported `crosses`
    against `RoomA`/`RoomB` (462uu/512uu) pre-fix -- the ordinary "solid rock, rooms carved into
    it" case, not a genuine penetration."""
    sc = scen.two_rooms_side_by_side()
    ctx = actor_survey.build_context(sc.level, sc.index, "Rock", sc.defaults)
    facts = actor_survey.crosses_facts_for(ctx)
    assert not any(f.dst in ("RoomA", "RoomB") for f in facts)


def test_touches_fires_both_directions_for_a_doorway_cut_through_a_wall_seam():
    """Board item `crosses-fires-on-a-subtract-s-carve-victim`: `WallA` wrongly reported `crosses`
    against `Doorway` (192uu) pre-fix, with `touches` suppressed both directions
    (`pair_touches(WallA, Doorway)` was already `True`; only the `crosses`-claims-the-pair exclusion
    blocked it). Post-fix, `crosses` is silent and `touches` fires both ways -- the doorway's carve
    boundary is real on the wall it cuts through, seen from either side."""
    sc = scen.a_doorway_through_a_wall_seam()
    ctx_a = actor_survey.build_context(sc.level, sc.index, "WallA", sc.defaults)
    assert not any(f.dst == "Doorway" for f in actor_survey.crosses_facts_for(ctx_a))
    assert any(f.src == "WallA" and f.dst == "Doorway" for f in actor_survey.touches_facts_for(ctx_a))

    ctx_doorway = actor_survey.build_context(sc.level, sc.index, "Doorway", sc.defaults)
    assert any(f.src == "Doorway" and f.dst == "WallA"
              for f in actor_survey.touches_facts_for(ctx_doorway))


def test_crosses_does_not_fire_for_an_add_to_add_pair_whose_source_was_later_recarved():
    """Board item `crosses-fires-on-a-subtract-s-carve-victim`'s own closing paragraph, the fourth
    case (no fixture pinned it before this): `Rock --crosses(1.47e+03uu)--> Crate` pre-fix, an
    Add-to-Add pair where `Room`/`Corridor` (Subtracts later than `Rock` in trunk order) carve away
    the matter that would otherwise reach `Crate` -- the same `_source_cells`-sources-authored-cells
    root cause as the other three rows, not a separate bug. Reuses the already-committed
    `an_oversized_corridor_past_its_room` fixture (verified live, pre-fix: `crosses_facts_for(Rock)`
    reports exactly `Rock --crosses(1472.0uu)--> Crate`, matching the board item's own cited figure);
    no new fixture needed."""
    sc = scen.an_oversized_corridor_past_its_room()
    ctx = actor_survey.build_context(sc.level, sc.index, "Rock", sc.defaults)
    assert not any(f.dst == "Crate" for f in actor_survey.crosses_facts_for(ctx))
```

Run `bin/test uedcli/tests/test_actor_survey.py` again → the strict-xfail collision and all four new
tests now PASS. (Steps 9-11, 13-14 below still have their own regressions to fix — Step 12 adds new
coverage, not a regression fix; this step only clears the board-item collision, not the whole file.)

- [ ] **Step 8: resolve the board item**

Once Step 7's four assertions (the un-xfailed test and the three new ones) are confirmed passing:
`git mv dev/docs/board/inbox/crosses-fires-on-a-subtract-s-carve-victim dev/docs/board/done/`, trimmed
to a short reference line (the board's own `done/` convention, `dev/docs/board/README.md` — never
leave a ticked `[x]` behind). This task's fix plus Step 7's tests cover the item's table AND its
closing paragraph's fourth case in full — nothing left uncovered to caveat in the trimmed reference
line.

- [ ] **Step 9: Correct `shelf_pokes_through_a_niche_wall`'s docstring**

Owner-confirmed finding (review round 4): this fixture's existing docstring and dependent tests
assert `Additive4 --crosses--> Subtract3`, "64uu deep on each end" — that number is each surviving
stub's own authored length past `Subtract3`'s cut planes, i.e. exactly the unfiltered-authored-cell
bug Step 4 above fixes, not a genuine penetration. Post-fix, `Additive4`'s two stubs (y in [0,64) and
(192,256]) are bounded EXACTLY by `Subtract3`'s own y=64/y=192 cut planes — flush, not crossing — so
`crosses` goes silent for this pair; `touches` fires instead (`Additive4`'s matter rests directly
against a REAL carve boundary: `_is_carve_boundary`'s "carve must be real" condition holds, since
`Subtract3` genuinely removed `Additive4`'s own matter there).

Replace `shelf_pokes_through_a_niche_wall`'s docstring (`uedcli/tests/survey_scenarios.py:254-284`,
the prose above the `return _scenario([...])`, brush list unchanged) with:

```
    """The spec's own nesting example -- `Subtract1 -> Additive2 -> Subtract3 -> Additive4` is a
    NESTING chain (each one geometrically inside/carved-from the previous), not a trunk-order
    mandate. Trunk order here is `Subtract1, Additive2, Additive4, Subtract3` -- `Additive4` is
    authored BEFORE `Subtract3`, load-bearing (see the correction note below).

    * `Subtract1` 1024^3 Subtract at (0, 0, 0)          -- the outer room
    * `Additive2` 256 x 64 x 256 Add at (0, 128, 0)     -- a wall inside it, y in [96, 160]
    * `Additive4` 32 x 256 x 32 Add at (0, 128, 0)      -- a shelf, x,z in [-16, 16] (inside
      `Subtract3`'s future hole footprint, so it never touches `Additive2`'s own faces), y in
      [0, 256] (past `Additive2`'s wall on both ends).
    * `Subtract3` 128 x 128 x 128 Subtract at (0, 128, 0) -- a niche, y in [64, 192]. Carved AFTER
      `Additive4`, it removes `Additive4`'s own matter within its box too (x,z in [-64, 64]),
      leaving `Additive4`'s y in [0, 64) and (192, 256] surviving on either side, past
      `Subtract3`'s own y=64/y=192 caps.

    `Additive4` does NOT cross `Subtract3`. An earlier version of this fixture claimed it did, "64uu
    deep on each end" -- that number was each surviving stub's own authored length past the cut
    planes, not a real penetration, and is exactly the unfiltered-authored-cell bug this item fixes.
    Filtered to resolved matter, each stub is bounded EXACTLY by `Subtract3`'s own y=64/y=192 planes
    -- flush, not crossing -- so `crosses` is silent for this pair. `Additive4 touches Subtract3`
    instead, at both caps: each stub's matter rests directly against a carve boundary that is REAL
    (`Subtract3` genuinely removed `Additive4`'s own matter there, so `_is_carve_boundary`'s "the
    carve must be real" condition holds). `Additive4` never touches or crosses `Additive2`, however
    the nesting reads (the spec's strict-locality rule): its footprint sits entirely inside the hole
    `Subtract3` cut through `Additive2`, well clear of `Additive2`'s own remaining ring.

    (Trunk order is the fix, not a dimension: with the naive order `..., Subtract3, Additive4`
    (`Additive4` authored AFTER the niche), `Additive4`'s own matter, wherever it overlaps
    `Additive2`'s already-solid ring `x,z` in [64, 128]/[-128, -64], gets folded into that solid by
    plain CSG_Add union (no internal face between two Adds); AND wherever `Additive4` fills what
    `Subtract3` carved to void, `Subtract3`'s own face there gets removed as now-interior. Both
    effects erase exactly the face `Additive4` would need to overlap to register ANY fact at all --
    verified directly: with that order, `Additive4`'s resolved footprint is clipped to `Subtract3`'s
    own +-64 hole (nothing survives past it), and neither `crosses_facts_for` nor `touches_facts_for`
    reports any `Additive4`-owned fact at all. Authoring `Additive4` first means `Subtract3`'s later
    carve is what PRODUCES the y=64/y=192 faces, as a real carve into `Additive4`'s own pre-existing
    matter, so they survive intact and `Additive4`'s stubs rest flush against them.)
    """
```

- [ ] **Step 10: Rewrite `test_crosses_fires_for_an_add_poking_through_a_niche_wall_and_names_only_the_immediate_owner`**

The old test (`uedcli/tests/test_actor_survey.py:600-631`) asserted the bug's own behavior
(`Additive4 --crosses--> Subtract3`, `depth_uu > 0`). Its real point — locality: the immediate
carve gets named, the outer nesting never does, proven both by surveying `Additive4` (where
region-clipping could pass by accident) AND by surveying `Additive2` (where its own faces are
genuinely in-region, closing that gap) — still holds, now for `touches` instead of `crosses` (the
corrected relation for this pair). Replace the whole test with:

```python
def test_touches_fires_for_a_carved_shelf_and_names_only_the_immediate_niche():
    """The spec's locality rule, now for `touches`: `Additive4`'s two surviving stubs sit flush
    against `Subtract3`'s own cut planes -- the immediate boundary that carved it -- and never
    against `Additive2`, however deep the nesting. `crosses` is confirmed silent for this pair
    entirely (the resolved-matter fix's own regression fixture, Step 2 above, already pins that);
    this test is the locality half, for the relation that actually fires here.

    Surveying `Additive4` alone would pass this even by accident: region-clipping keeps `Additive2`'s
    own faces out of `Additive4`'s survey region entirely. Surveying `Additive2` closes that gap:
    `Additive2`'s own faces ARE in-region there, and `Additive4`'s stubs sit entirely inside the hole
    `Subtract3` cut through `Additive2`, nowhere near `Additive2`'s own remaining ring -- so this is
    the case the immediate-owner attribution exists for, not a region-clipping accident."""
    pytest.importorskip("uedcli_native")
    sc = scen.shelf_pokes_through_a_niche_wall()

    ctx = actor_survey.build_context(sc.level, sc.index, "Additive4", sc.defaults)
    assert actor_survey.crosses_facts_for(ctx) == []
    facts = actor_survey.touches_facts_for(ctx)
    assert any(f.src == "Additive4" and f.dst == "Subtract3" for f in facts)
    assert not any(f.dst == "Additive2" for f in facts)
    assert not any(f.src == "Additive2" and f.dst == "Additive4" for f in facts)

    ctx2 = actor_survey.build_context(sc.level, sc.index, "Additive2", sc.defaults)
    assert any(f.owner == "Additive2" for f in ctx2.faces), \
        "the real case: Additive2's own faces must be in-region for this to test anything"
    facts2 = actor_survey.touches_facts_for(ctx2)
    assert not any(f.src == "Additive4" and f.dst == "Additive2" for f in facts2)
```

- [ ] **Step 11: Delete `test_crosses_reports_the_reverse_direction_when_the_surveyed_actor_is_the_target`**

(`uedcli/tests/test_actor_survey.py:692-700`.) Its only fact (`Additive4 --crosses--> Subtract3`) no
longer exists — this fixture's crossing was exactly the bug fixed. Its point (`crosses` is
fixed-direction: surveying the TARGET must still show the fact with the intruder leading) stays
covered without it: `test_crosses_fires_for_a_point_actor_whose_location_is_outside_the_surveyed_brush`
(`:663-682`) already surveys `Room` — the target — and asserts the fact still shows with `Bracket`
(the intruder) leading, on a fixture this fix does not touch.

No same-shape brush replacement is substituted for THIS fixture: board item
`crosses-fires-on-a-subtract-s-carve-victim` names two more of the same bug, `two_rooms_side_by_side`
and `a_doorway_through_a_wall_seam`, pinned as absence-of-crossing regressions in Step 7 above — all
three, this one included, were the authored-cells false positive, never a genuine crossing. That is
narrower than "no genuine brush-sourced `crosses` exists in this engine at all" — it does, for a
Semisolid overlapping an Add (corrected invariant note below; Step 12 pins it as the suite's first
real brush-sourced `crosses` coverage). Every OTHER genuinely-crossing fixture already in this suite
still crosses via a non-brush collision extent (`Keypad`/`Bracket`'s cylinders); an Add/Add or
Add/Subtract merge still consumes the shared face before a brush source could straddle it
(`test_a_contact_plane_outlives_the_resolved_face_it_would_have_been_read_from`'s own finding, same
mechanism) — that part of the earlier reasoning holds, narrowed to those two kinds.

**Narrowed invariant: an Add/Add or Add/Subtract merge cannot produce a genuine brush-sourced
`crosses` — but a Semisolid can, and does (review round 6 finding; Step 12 below pins it).**
`ctx.faces` is read from `probe.world_surfaces` -- the FULLY resolved BSP, computed after every
Add/Subtract in the trunk (the candidate crossing source included) is applied. For those two kinds, a
face fragment surviving into it is exactly a patch where the resolved geometry has solid on one side
and genuine void on the other, and any Add/Subtract matter reaching that patch would already have
consumed the face there instead of leaving it to straddle -- confirmed directly, not asserted:

- `_matter_side`/`contact_planes`'s own docstring (`actor_survey.py:1466-1470`): "two Adds butted face
  to face with identical footprints consume each other's face on the shared plane, so NEITHER owner
  has a surviving fragment there."
- `shelf_pokes_through_a_niche_wall`'s confirmed finding (this task's own fixture, Step 9's corrected
  docstring): wherever a later Add fills what an earlier Subtract carved to void, the carve boundary's
  face is removed as now-interior -- the same erasure, from the refill side.
- `test_a_contact_plane_outlives_the_resolved_face_it_would_have_been_read_from`
  (`test_actor_survey.py:853-873`, already in the suite and passing today) confirms the general case
  directly: on `peg_buried_in_a_wall`, `Wall`'s x=192 face survives ONLY as the flanking fragment
  starting past `Peg`'s own footprint (`min(v[1] for v in final.verts) == 32.0`) -- the exact portion
  `Peg` overlaps is already gone from `ctx.faces`, not merely un-crossed.
- Verified live against two fresh probe fixtures built for this finding (Room 1024^3 Subtract at
  origin; `B` a 200^3 Add at origin; `D` a later Add positioned to bridge across one of `B`'s faces):
  with `D` sized 40x200x200 at `(110, 0, 0)` (full-height overlap, x in [90,130] against `B`'s x in
  [-100,100]), `B`'s +X face is absent from `ctx.faces` entirely -- `crosses_facts_for` returns `[]`
  surveying either actor. With `D` sized 40x100x200 at `(110,-50,0)` (half-height overlap, y in
  [-100,0] against `B`'s y in [-100,100]), `B`'s +X face survives ONLY for y in [0,100] -- exactly
  the flanking half `D` does not reach -- again `crosses_facts_for` returns `[]` surveying either
  actor. Both match the `peg_buried_in_a_wall` pattern exactly: the surviving footprint and the
  intruder's own footprint are structurally disjoint by construction, so the straddle test that would
  fire `crosses` never gets a face to fire it against.

**This does NOT extend to a Semisolid source.** `csg_order` places every Semisolid AFTER every
Add/Subtract, applied in its own later, separate pass (`csgRebuild`'s LOOP 2/LOOP 3,
`actor_survey.py:737-740`, "no Subtract in the trunk can cut a semisolid") -- and that pass does not
SPLIT the underlying Add's already-resolved face where a Semisolid's own volume overlaps it, the way
an Add/Add merge in the main pass does. So an Add's face can survive into `ctx.faces` completely
intact through a region a later Semisolid's own matter also occupies, and the Semisolid's matter can
genuinely straddle it: some of its own points on the void side of that face, others past it into the
Add's solid.

Verified live: `B` a 200^3 Add at the origin (x,y,z in [-100,100]), `Spike` a 40x20x20 Semisolid at
`(110,80,80)` (x in [90,130], y,z in [70,90] -- a corner strip clear of `B`'s face centroid,
overlapping `B` by 10uu in x). `crosses_facts_for` reports `Spike --crosses--> B` (`depth_uu == 30.0`)
from either survey direction. A same-geometry control with `Spike` authored as a plain Add instead of
Semisolid does NOT report this fact -- confirming the Semisolid's separate, non-splitting CSG pass,
not the geometry, produces it. `_CROSSES_SOURCE_KINDS` already includes `semisolid`
(`actor_survey.py:816`), so this is in scope for `crosses_facts_for` as shipped, not an edge case
outside it. This fixture has no Subtract at all, so Task 3's `_source_cells` fix (filtering by LATER
Subtracts) is a no-op against it either way -- the fact holds identically before and after this task's
fix lands.

This settles Fix 2 of the plan's revision as outcome (b) for Add/Add and Add/Subtract pairs only, not
(a): the absence of brush-sourced `crosses` coverage for THOSE two kinds is a confirmed structural
invariant, not a gap to fill. For a Semisolid source it is outcome (a) instead -- a genuine, missing
regression fixture -- pinned in Step 12 below as the suite's first real brush-sourced `crosses`
coverage.

- [ ] **Step 12: Pin the Semisolid-vs-Add `crosses` regression — the suite's first genuine
  brush-sourced crossing**

Review round 6 finding, not this fix's job to change: the fixture below has no Subtract at all, so
Task 3's own `_source_cells` fix (Step 4) is a no-op against it either way — verified live before
writing this step. Adds coverage only; no `actor_survey.py` change follows.

Add to `survey_scenarios.py`, alongside `semisolid_pillar_straddled_by_a_subtract` (the file's own
carve-immunity precedent for the same later, separate Semisolid CSG pass):

```python
def semisolid_partially_overlapping_an_add() -> Scenario:
    """A genuine brush-sourced `crosses`, next to `semisolid_pillar_straddled_by_a_subtract` above as
    the same later, separate CSG pass's other consequence: `csgRebuild`'s LOOP 2/LOOP 3
    (`actor_survey.py:737-740`) makes a Semisolid immune to being carved (that fixture), but it also
    never SPLITS the underlying Add's already-resolved face where a Semisolid's own volume overlaps
    it -- unlike an ordinary Add/Add merge, which DOES consume the shared face
    (`_matter_side`/`contact_planes`'s own docstring, `actor_survey.py:1466-1470`). So the Semisolid's
    matter can genuinely straddle that face: real solid on one side (the Add's), real void on the
    other (the Semisolid's own point just short of it).

    Trunk order: B, Spike.
    * `B`     200^3 Add at (0, 0, 0)                  -- x, y, z in [-100, 100]
    * `Spike` 40 x 20 x 20 Semisolid at (110, 80, 80)  -- x in [90, 130], y, z in [70, 90], a corner
      strip clear of B's +X face centroid, overlapping B by 10uu in x

    Verified live: `crosses_facts_for` reports `Spike --crosses--> B` (`depth_uu == 30.0`) from
    either survey direction, both before and after Task 3's fix (no Subtract here for that fix's
    filter to touch). A same-geometry control with `Spike` as a plain Add instead of Semisolid does
    NOT report this fact -- confirming the Semisolid's own separate CSG pass, not the geometry, is
    what produces it.
    """
    return _scenario([
        brush("B", (200, 200, 200), (0, 0, 0)),
        brush("Spike", (40, 20, 20), (110, 80, 80), poly_flags=PF_SEMISOLID),
    ])
```

Add to `test_actor_survey.py`, near `test_crosses_uses_resolved_matter_not_authored_cells` (Step 2
above):

```python
def test_crosses_fires_for_a_semisolid_partially_overlapping_an_add():
    """The suite's first genuine brush-sourced `crosses` -- a Semisolid's later, separate CSG pass
    never splits the underlying Add's face it overlaps (fixture's own docstring), so its matter
    genuinely pokes past it. Pinned so a future change to the semisolid CSG pass cannot silently
    break it; unaffected by Task 3's own fix (no Subtract in this fixture)."""
    pytest.importorskip("uedcli_native")
    sc = scen.semisolid_partially_overlapping_an_add()
    for surveyed in ("Spike", "B"):
        ctx = actor_survey.build_context(sc.level, sc.index, surveyed, sc.defaults)
        facts = actor_survey.crosses_facts_for(ctx)
        fact = next((f for f in facts if f.src == "Spike" and f.dst == "B"), None)
        assert fact is not None, f"surveying {surveyed}"
        assert 25.0 < fact.depth_uu < 35.0
```

`bin/test -k test_crosses_fires_for_a_semisolid_partially_overlapping_an_add -v` → PASS immediately —
this pins existing correct behavior; no implementation follows.

- [ ] **Step 13: Fix `test_touches_and_crosses_are_mutually_exclusive_for_one_pair`**

(`uedcli/tests/test_actor_survey.py:982-990`.) `assert crossed` now fails (`crossed` is empty for
this fixture post-fix). Swap to `room_with_a_flush_mounted_prop`'s `Keypad`, an existing, unaffected
fixture that already genuinely crosses `Room`
(`test_crosses_fires_for_a_flush_mounted_collision_extent_with_a_measured_depth`):

```python
def test_touches_and_crosses_are_mutually_exclusive_for_one_pair():
    """Within CSG_TOLERANCE of coincident is `touches`; clearly past it is `crosses`. A pair is
    never both."""
    pytest.importorskip("uedcli_native")
    sc = scen.room_with_a_flush_mounted_prop()
    ctx = actor_survey.build_context(sc.level, sc.index, "Keypad", sc.defaults)
    crossed = {(f.src, f.dst) for f in actor_survey.crosses_facts_for(ctx)}
    touched = {(f.src, f.dst) for f in actor_survey.touches_facts_for(ctx)}
    assert crossed and crossed & touched == set()
```

- [ ] **Step 14: Re-fixture `test_crosses_dedupes_to_one_fact_per_src_dst_pair` — its old fixture
  goes vacuous once this fix lands**

(`uedcli/tests/test_actor_survey.py:703-710`.) This test's fixture is `shelf_pokes_through_a_niche_wall`
/`Additive4` — the exact fixture whose only `crosses` fact Step 4's fix removes (Steps 9-11 above).
Left as-is, `crosses_facts_for(ctx)` for `Additive4` returns `[]` post-fix, so `len(keys) ==
len(set(keys))` degrades to a vacuous `0 == 0` — the test still passes but no longer tests
de-duplication at all.

Every fixture this fix leaves genuinely crossing is sourced from a non-brush collision extent, EXCEPT
Step 12's Semisolid-vs-Add fixture (`B`/`Spike`), which crosses on a single face only and cannot cover
a two-face dedup by itself — so the replacement fixture here still has to dedupe a collision-extent
source, not a brush. Add a new fixture to `survey_scenarios.py`, near `room_with_a_flush_mounted_prop`:

```python
def point_actor_pokes_through_two_walls_at_a_room_corner() -> Scenario:
    """Trunk order: Room, Corner.

    * `Room`   1024^3 Subtract at (0, 0, 0)        -- walls at x = +/-512, y = +/-512
    * `Corner` a point actor at (500, 500, 0), bCollideActors + bBlockActors, R=16 H=16 --
               its collision cylinder spans x in [484, 516] and y in [484, 516], so it pokes
               4uu past BOTH the +X wall (x=512) and the +Y wall (y=512) at once. One actor,
               two genuinely-crossed faces of the SAME target (`Room`) -- the dedup case
               `crosses_facts_for`'s (src, dst)-keyed `record()` exists for. Every FALSE-POSITIVE
               brush-sourced crossing in this suite is gone (this task's own fix); the only
               genuine one left, Step 12's Semisolid fixture, crosses one face only, so a
               collision extent is the only remaining source that can supply TWO for this dedup
               test -- `_source_cells`' non-brush branch never filters it (unaffected by this fix).

    Verified live against the current (pre-Step-4) code: `ctx.faces` for this fixture holds
    exactly `Room`'s +X and +Y planes, and `penetration_depth` returns `4.0` for BOTH,
    independently, from the same source cell -- two real `record("Corner", "Room", ...)` calls
    for the one (src, dst) pair, collapsed by the dict-keyed dedup to the single
    `CsgFact(src="Corner", dst="Room", relation="crosses")` `crosses_facts_for` actually returns.
    Nothing about this path touches a brush or `_source_cells`' brush branch, so Step 4's fix
    changes nothing about it.
    """
    coll = [("bCollideActors", "True"), ("bBlockActors", "True"),
            ("CollisionRadius", "16"), ("CollisionHeight", "16")]
    return _scenario([
        brush("Room", (1024, 1024, 1024), (0, 0, 0), csg="subtract"),
        point("Corner", (500, 500, 0), cls="DeusEx.Keypad1", props=coll),
    ])
```

Replace the test body (same name, new fixture):

```python
def test_crosses_dedupes_to_one_fact_per_src_dst_pair():
    """One actor can genuinely cross TWO distinct faces of the same target at once (a room corner)
    -- still one relationship, one line. `shelf_pokes_through_a_niche_wall`'s `Additive4` no longer
    crosses `Subtract3` at all post-fix (Steps 9-11 above), so the dedup case is re-pinned here on a
    fixture that is a genuine double-crossing instead of the retired false positive."""
    pytest.importorskip("uedcli_native")
    sc = scen.point_actor_pokes_through_two_walls_at_a_room_corner()
    ctx = actor_survey.build_context(sc.level, sc.index, "Corner", sc.defaults)
    facts = actor_survey.crosses_facts_for(ctx)
    keys = [(f.src, f.dst, f.relation) for f in facts]
    assert len(keys) == len(set(keys))
    assert keys == [("Corner", "Room", "crosses")]
```

Run `bin/test -k test_crosses_dedupes_to_one_fact_per_src_dst_pair -v` → PASS.

- [ ] **Step 15: Run the full `crosses`/`touches` test set again**

`bin/test -k "crosses or touches"` → PASS, including every test touched by Steps 7, 9-14 and every
unrelated existing test.

- [ ] **Step 16: Commit**

```bash
git add uedcli/actor_survey.py uedcli/tests/survey_scenarios.py uedcli/tests/test_actor_survey.py
git commit -m "Fix crosses to use resolved matter via convex-piece partitioning, not per-corner filtering"
```

---

## Task 4: `occupies` — matter branch (Add/Semisolid, marginal test)

**Files:**
- Modify: `uedcli/actor_survey.py` (add near `contains_facts_for`, which Task 6 removes)
- Test: `uedcli/tests/test_actor_survey.py`

**Interfaces:**
- Consumes: `_partition_by_brushes`, `_piece_centroid`, `_is_void_excluding`, `_last_writer_excluding`
  (Task 2), `_cell_intersection` (Task 1), `resolved_matter_of` (existing).
- Produces: `_occupies_matter_exists(ctx: SurveyContext, x, s) -> bool`

- [ ] **Step 1: Write the failing tests**

```python
def test_occupies_fires_for_an_add_seated_in_an_oversized_subtracts_void():
    # nested_niche_with_a_decoration: Additive4 (Add) wholly inside Subtract3's void, Subtract3
    # itself oversized past Additive2's own extent (routine carve idiom).
    s = survey_scenarios.nested_niche_with_a_decoration()
    ctx = build_context(s.level, s.index, "Additive4", s.defaults)
    assert _occupies_matter_exists(ctx, s.level.actors["Additive4"], s.level.actors["Subtract3"])


def test_occupies_does_not_credit_the_trunk_first_subtract_with_a_carve_it_did_not_make():
    # Same bug class as test_occupies_facts_for_composes_across_two_subtracts's Outer, one tier
    # down: nested_niche_with_a_decoration's Subtract1 is first in csg_order, so the old
    # `_was_solid_before(Subtract1, p)` condition (ii) was tautologically True for it regardless of
    # p -- Additive4 sits inside Subtract1's box too (Subtract1 is the outer room), so it would
    # falsely occupy Subtract1 alongside the correct Subtract3. Subtract3 is the actual operative
    # carve at Additive4's location (last writer excluding Additive4), not Subtract1.
    s = survey_scenarios.nested_niche_with_a_decoration()
    ctx = build_context(s.level, s.index, "Additive4", s.defaults)
    assert not _occupies_matter_exists(ctx, s.level.actors["Additive4"], s.level.actors["Subtract1"])


def test_occupies_does_not_fire_for_the_carved_away_worked_example():
    # Task 3's fixture: Middle's matter at Enclosed's own footprint was carved away by Later, so
    # Middle does not occupy Later there (nothing of Middle's own matter survives to sit in it).
    s = survey_scenarios.later_subtract_carves_an_add_that_encloses_a_semisolid()
    ctx = build_context(s.level, s.index, "Middle", s.defaults)
    assert not _occupies_matter_exists(ctx, s.level.actors["Middle"], s.level.actors["Later"])


def test_occupies_over_fires_without_the_own_matter_condition_pinned_by_construction():
    # spec's own regression case: order sub1 -> A -> sub2, sub2 re-carving A. A point in
    # A ∩ sub1 ∩ sub2 passes (ii)+(iii) though A has no surviving matter there. Pinned as a
    # regression: A must NOT occupy sub2 at all (A's matter there was re-carved away).
    s = survey_scenarios.partial_and_total_carves()  # FirstCut then SecondCut both cut Block
    ctx = build_context(s.level, s.index, "Block", s.defaults)
    assert not _occupies_matter_exists(ctx, s.level.actors["Block"], s.level.actors["SecondCut"])
```

- [ ] **Step 2: Run them, confirm they fail**

`bin/test -k "occupies"` → FAIL (`_occupies_matter_exists` does not exist).

- [ ] **Step 3: Implement**

**Review finding, round 4: condition (ii) as `_was_solid_before(ctx, s, p)` alone is a tautology.**
`_was_solid_before` walks backward from `s`'s own position in `csg_order` for the nearest earlier
occupant of `p` -- it never looks at `s`'s own geometry at all. So whenever `x` precedes `s` and
condition (i) holds (`resolved_matter_of(x, p)` True, meaning no Subtract AFTER `x` covers `p`),
walking backward from `s` always finds `x` itself (or another non-Subtract) as the nearest earlier
occupant, making (ii) trivially True for EVERY surviving point of `x`, regardless of whether `p` is
anywhere near `s`'s own box. `_occupies_nonsolid_exists`/`_occupies_point_exists` (Task 5) already
guard against exactly this by restricting to `x`'s cells intersected with `s`'s own cells (nonsolid
branch) or `_in_authored_volume(ctx, s, p)` (point branch) before testing anything else -- the same
restriction is missing here. Fixed: intersect each of `x`'s cells with each of `s`'s cells FIRST (so
every `p` tested is provably somewhere `s` could have carved), then partition that overlap by every
other brush.

**Review finding, round 5: even restricted to the overlap, `_was_solid_before(s, p)` is STILL a
tautology whenever `s` is the FIRST brush in `csg_order`.** `_was_solid_before`'s own base case --
"no earlier brush reaches `p`" reads as solid, the `MAP NEW` default-solid world -- returns True
unconditionally for the trunk-first brush, with no check that `s` is even the CURRENT reason `p` is
void. Caught live on `two_rooms_side_by_side` (`Outer`, a Subtract, first in trunk order, later
entirely refilled by `Rock` and then re-carved by `RoomA`/`RoomB`): `occupies_facts_for(Bridge)`
wrongly reported `occupies(Bridge, Outer)` alongside the two correct facts, because condition (ii)
read True for `Outer` regardless of which later brush actually carves `Bridge`'s location today.
Same class of bug in `nested_niche_with_a_decoration` (`Subtract1` is trunk-first there) -- pinned
by a new test in Step 1 below. **Fix: replace `_was_solid_before(s, p)` with "`s` is the OPERATIVE
carve at `p`" -- the last writer reaching `p` once `x` is excluded is `s` itself**
(`_last_writer_excluding(ctx, p, exclude=x.name) == s.name`, Task 2). This only credits the Subtract
that is CURRENTLY the reason `p` is void, never one superseded by a later carve or refill:

```python
def _occupies_matter_exists(ctx: SurveyContext, x, s) -> bool:
    """Does matter actor `x` (Add/Semisolid) `occupies` Subtract `s` -- the MARGINAL test (owner
    ruling): a point p qualifies iff ALL of (i) `resolved_matter_of(x, p)` -- x's own matter
    survives; (ii) `s` is the OPERATIVE carve at p -- the last writer reaching p once x is excluded
    is s itself (`_last_writer_excluding(ctx, p, exclude=x.name) == s.name`); (iii)
    `_is_void_excluding(p, exclude=x.name)` -- p is void when x is excluded (implied by (ii) here,
    since s is always a Subtract, but kept as its own check to match the spec's three-condition
    form). Restricted throughout to p WITHIN s's own authored volume (`_cell_intersection(x_cell,
    s_cell)`, the same guard `_occupies_nonsolid_exists`/`_occupies_point_exists` already use).
    Partitions the x-and-s overlap against every OTHER brush (any of them can still flip (i)/(ii))
    and tests each resulting piece's centroid once -- exact, not sampled."""
    relevant = [a for a in ctx.csg_order if a.name != x.name]
    for x_cell in actorgraph.decompose_convex(x, cache=ctx.cells):
        for s_cell in actorgraph.decompose_convex(s, cache=ctx.cells):
            overlap = _cell_intersection(x_cell, s_cell)
            if overlap is None:
                continue
            for piece in _partition_by_brushes(overlap, relevant, ctx):
                p = _piece_centroid(piece)
                if (resolved_matter_of(ctx, x, p)
                        and _last_writer_excluding(ctx, p, exclude=x.name) == s.name
                        and _is_void_excluding(ctx, p, exclude=x.name)):
                    return True
    return False
```

`relevant` still includes `s` itself (matching Task 4's original list, only `x.name` excluded) --
harmless, not incorrect: every point of `overlap` is already inside `s`'s own cell by construction,
so partitioning by `s` again can only ever produce the same single piece back (the "outside s"
half is empty), never a wrong split.

- [ ] **Step 4: Hand-trace the fix against the worked-example test**

`test_occupies_does_not_fire_for_the_carved_away_worked_example` (Step 1) asserts `not
_occupies_matter_exists(ctx, Middle, Later)` on `later_subtract_carves_an_add_that_encloses_a_semisolid`
(Task 3's fixture: `Middle` 256^3 Add at origin, `Later` 192^3 Subtract at origin, `Later` fully
inside `Middle`). Before either fix, condition (ii) was a tautology: `Middle`'s own shell, e.g. the
point `(0, 112, 0)` -- inside `Middle`'s surviving shell (`y=112` is past `Later`'s own `y<=96`
face) but NOT inside `Later`'s authored box at all -- would still pass the OLD (unguarded) (ii)
(`_was_solid_before(Later, (0,112,0))` reads True purely because `Middle` is the nearest earlier
occupant there, with nothing checking whether `Later` itself reaches that point), wrongly firing.

With the round-4 overlap restriction alone: `overlap = _cell_intersection(Middle_cell, Later_cell)`
is `Later`'s own whole box `[-96,96]^3` (fully inside `Middle`'s `[-128,128]^3`) -- `(0, 112, 0)` is
OUTSIDE this overlap entirely and is never tested at all. Every point that IS tested lies within
`Later`'s own box, and `Later` -- a Subtract strictly later than `Middle` in trunk order -- covers
every one of them, so `resolved_matter_of(ctx, Middle, p)` (condition i: "no Subtract after `Middle`
covers p") is False for every single piece the partition produces. Condition (i) already fails
everywhere in the restricted region here, so this fixture's own assertion passes on the round-4 fix
alone -- the round-5 fix changes nothing about THIS trace (still correctly False), but is needed for
`two_rooms_side_by_side`/`nested_niche_with_a_decoration` below, where (i) does NOT fail and the old
(ii) was the only thing wrongly letting the fact through.

This is not a coincidence of this one fixture: for ANY `x`-before-`s` pair, every point of
`x`'s-cells-intersect-`s`'s-cells lies inside `s`'s own box, and `s` (a Subtract after `x`) always
counts against `resolved_matter_of(x, p)` there -- so (i) fails identically for every `x`-before-`s`
pair. This is spec's own "S-after-A -> only carves possible" case (`s` authored after `x`) -- the
fix makes `_occupies_matter_exists` correctly never fire there, restoring `carves`/`occupies` mutual
exclusivity exactly as spec's "(i) also restores carves/occupies mutual exclusivity for an S-after-X
pair" says.

**`test_occupies_composes_across_two_subtracts`-style facts still hold.** Task 6's
`test_occupies_facts_for_composes_across_two_subtracts` needs `Bridge` (authored LAST, so no
Subtract follows it) to occupy both `RoomA` and `RoomB`, and NEITHER to fire for `Outer` (trunk-first
Subtract, the round-5 regression). For the `RoomA` direction:
`overlap = _cell_intersection(Bridge_cell, RoomA_cell)` is `Bridge`'s own `x in [-120,-100]` slice
(the 20uu of `Bridge` inside `RoomA`'s box). Partitioned by the other brushes (`Outer`/`Rock` fully
contain it, no split; `RoomB`'s box starts at `x=-100`, a shared-plane touch with no real overlap),
the surviving piece is that slice itself, centroid `p ~ (-110, 0, 0)`. (i) `Bridge` is last in trunk
order, so nothing after it can remove its matter -- True. (ii) `_last_writer_excluding(p,
exclude="Bridge")`: reversed trunk order excluding `Bridge` is `RoomB, RoomA, Rock, Outer` --
`RoomB` doesn't reach `x=-110`, `RoomA` does and is the first (latest) match, so the last writer is
`RoomA` == `s.name` -- True. (iii) follows automatically (the last writer is a Subtract) -- True.
All three hold, so `occupies(Bridge, RoomA)` still fires; symmetric for `RoomB` (its own overlap
slice's last writer excluding `Bridge` is `RoomB` itself). For the `Outer` direction: same overlap
slice `p ~ (-110, 0, 0)` (fully inside `Outer`'s box too, so `_cell_intersection(Bridge_cell,
Outer_cell)` produces the same partitioned piece) -- `_last_writer_excluding(p, exclude="Bridge")`
is still `RoomA`, not `"Outer"`, so (ii) fails and `occupies(Bridge, Outer)` correctly does not fire.
Under the OLD (ii), `_was_solid_before(Outer, p)` would have read True regardless (`Outer` is
trunk-first, the round-5 tautology), which is exactly the bug this fix resolves.

**`nested_niche_with_a_decoration`'s own equivalent case, added as a regression test (Step 1's
`test_occupies_does_not_credit_the_trunk_first_subtract_with_a_carve_it_did_not_make`).**
`Subtract1` is trunk-first there (a Subtract), and `Additive4` sits inside both `Subtract1`'s and
`Subtract3`'s boxes -- the exact same shape as `Outer`/`Bridge` above, one tier down. Under the OLD
(ii), `_was_solid_before(Subtract1, p)` at `Additive4`'s centroid would read True unconditionally
(the round-5 tautology), wrongly firing `occupies(Additive4, Subtract1)` alongside the correct
`occupies(Additive4, Subtract3)`. Under the fix, `_last_writer_excluding(p, exclude="Additive4")` is
`Subtract3` (the actual operative carve there, `Subtract1`'s own carve at that point having been
superseded first by `Additive2`'s refill and then by `Subtract3`'s own re-carve) -- never
`"Subtract1"` -- so (ii) fails for `s=Subtract1` and the false positive does not occur. This existing
fixture was reused for the matter-branch tests (Task 4's research note) but no test before this round
checked for this false positive; the new test closes that gap.

- [ ] **Step 5: Run, confirm pass**

`bin/test -k "occupies"` → PASS

- [ ] **Step 6: Commit**

```bash
git add uedcli/actor_survey.py uedcli/tests/test_actor_survey.py
git commit -m "Add occupies matter-branch marginal test"
```

---

## Task 5: `occupies` — nonsolid branch (by shape) and point-actor branch

**Files:**
- Modify: `uedcli/actor_survey.py`
- Test: `uedcli/tests/test_actor_survey.py`
- Test fixture: `uedcli/tests/survey_scenarios.py`

**Interfaces:**
- Consumes: `_cell_intersection`, `_partition_by_brushes`, `_piece_centroid`, `_was_solid_before`,
  `_is_void_excluding`, `_in_authored_volume`.
- Produces: `_occupies_nonsolid_exists(ctx, x, s) -> bool`, `_occupies_point_exists(ctx, x, s) -> bool`

- [ ] **Step 1: Add a nonsolid-in-a-room fixture**

Add to `survey_scenarios.py`, near `nested_niche_with_a_decoration`:

```python
def nonsolid_decoration_in_a_subtracts_void() -> Scenario:
    """Trunk order: Room, Decal. `Room` 1024^3 Subtract at (0, 0, 0). `Decal` 32^3 Add with
    `poly_flags=PF_NOTSOLID` at (0, 0, 0) -- wholly inside Room's void. A Nonsolid brush contributes
    no matter (so the marginal test doesn't apply to it), but its authored SHAPE still lands inside
    Room's carved region -- the "not left with zero csg facts" case the spec's `occupies` nonsolid
    branch exists for."""
    from uedcli.builders import PF_NOTSOLID
    return _scenario([
        brush("Room", (1024, 1024, 1024), (0, 0, 0), csg="subtract"),
        brush("Decal", (32, 32, 32), (0, 0, 0), poly_flags=PF_NOTSOLID),
    ])
```

- [ ] **Step 2: Write the failing tests**

```python
def test_occupies_nonsolid_branch_fires_by_shape():
    s = survey_scenarios.nonsolid_decoration_in_a_subtracts_void()
    ctx = build_context(s.level, s.index, "Decal", s.defaults)
    assert _occupies_nonsolid_exists(ctx, s.level.actors["Decal"], s.level.actors["Room"])


def test_occupies_point_actor_branch_fires_for_a_light_in_a_carved_room():
    s = survey_scenarios.room_with_pillar_and_light()   # Room(subtract), Pillar(add), Light(point)
    ctx = build_context(s.level, s.index, "Light", s.defaults)
    light = s.level.actors["Light"]
    assert _occupies_point_exists(ctx, light, s.level.actors["Room"])


def test_occupies_point_actor_branch_is_silent_outside_the_room():
    s = survey_scenarios.far_apart_rooms()
    ctx = build_context(s.level, s.index, "FarRoom", s.defaults)
    ghost = point("Ghost", (0, 0, 0))   # world origin, inside Shell's solid, not any Subtract's void
    assert not _occupies_point_exists(ctx, ghost, s.level.actors["FarRoom"])
```

- [ ] **Step 3: Run them, confirm they fail**

`bin/test -k "occupies_nonsolid or occupies_point"` → FAIL

- [ ] **Step 4: Implement**

```python
def _brushes_before(ctx: SurveyContext, subtract) -> list:
    """`ctx.csg_order` truncated to every brush strictly before `subtract` -- the only ones
    `_was_solid_before(subtract, ...)` ever reads, and so the only ones needed to make it
    piecewise-constant over a `_partition_by_brushes` split."""
    return ctx.csg_order[:ctx.csg_index.get(subtract.name, len(ctx.csg_order))]


def _occupies_nonsolid_exists(ctx: SurveyContext, x, s) -> bool:
    """Does Nonsolid brush `x` `occupies` Subtract `s` BY SHAPE -- `nonsolid INTERSECT s INTERSECT
    was-solid-before(s)`, non-empty? `x` contributes no matter, so the marginal test's conditions
    (i)/(iii) make no sense for it; this is a pure authored-shape-in-carved-region test, exact via
    the same partition machinery."""
    earlier = _brushes_before(ctx, s)
    for x_cell in actorgraph.decompose_convex(x, cache=ctx.cells):
        for s_cell in actorgraph.decompose_convex(s, cache=ctx.cells):
            overlap = _cell_intersection(x_cell, s_cell)
            if overlap is None:
                continue
            for piece in _partition_by_brushes(overlap, earlier, ctx):
                if _was_solid_before(ctx, s, _piece_centroid(piece)):
                    return True
    return False


def _occupies_point_exists(ctx: SurveyContext, x, s) -> bool:
    """Does non-matter/point actor `x` `occupies` Subtract `s`? `x`'s own `Location`, tested the
    AUTHORED/relative way `resolved_matter_of` is (never the pooled `point_is_solid` oracle -- see
    its own docstring), is in `s`'s carved region and still resolved-void there. A single point, not
    a volume -- `x` has no cells to partition."""
    if x.location is None:
        return False
    p = tuple(float(c) for c in x.location)
    if not _in_authored_volume(ctx, s, p):
        return False
    if not _was_solid_before(ctx, s, p):
        return False
    return _is_void_excluding(ctx, p)
```

- [ ] **Step 5: Run, confirm pass**

`bin/test -k "occupies_nonsolid or occupies_point"` → PASS

- [ ] **Step 6: Commit**

```bash
git add uedcli/actor_survey.py uedcli/tests/survey_scenarios.py uedcli/tests/test_actor_survey.py
git commit -m "Add occupies nonsolid and point-actor branches"
```

---

## Task 6: wire `occupies_facts_for` into the csg pipeline; delete the old `contains` machinery

**Files:**
- Modify: `uedcli/actor_survey.py:1990-2064` (delete `containment_winner`, `_containment_candidates`,
  `contains_facts_for`; delete `VOLUME_TOLERANCE_REL`/`volume_tolerance`/`volumes_tied` at
  1974-1987), `uedcli/actor_survey.py:2177-2184` (`csg_facts_for`'s relation list)
- Test: `uedcli/tests/test_actor_survey.py` — delete every `test_contains_*` test (lines ~1624-1694;
  they test winner-take-all semantics `occupies` does not have) and every `test_volume_tolerance_*`
  test
- Test fixture: `uedcli/tests/survey_scenarios.py` — delete
  `mover_wrongly_tagged_as_subtract_competes_for_an_item`, orphaned by the `test_contains_*`
  deletion above and not reused by any later task (unlike `two_equal_volume_subtracts`, which Task 9
  reuses for a `coincides` test — keep that one)

**Interfaces:**
- Consumes: `_occupies_matter_exists`, `_occupies_nonsolid_exists`, `_occupies_point_exists` (Tasks
  4–5), `_MATTER_KINDS` (existing, `actor_survey.py:1227` — reuse for the matter-vs-nonsolid dispatch;
  note it includes `"mover"`, which `occupies` must never treat as a source — a Mover is excluded as a
  matter source per spec, so gate on `kind in {"add", "semisolid"}` directly, not on `_MATTER_KINDS`).
- Produces: `occupies_facts_for(ctx: SurveyContext) -> list[CsgFact]`

- [ ] **Step 1: Write the failing tests**

```python
def test_occupies_facts_for_reports_the_matter_branch():
    s = survey_scenarios.nested_niche_with_a_decoration()
    ctx = build_context(s.level, s.index, "Additive4", s.defaults)
    facts = occupies_facts_for(ctx)
    assert any(f.src == "Additive4" and f.dst == "Subtract3" and f.relation == "occupies"
               for f in facts)


def test_occupies_facts_for_composes_across_two_subtracts():
    # spec's "composes where containment cannot": an Add seated across two Subtracts' voids reports
    # occupies against BOTH, and crosses neither. `two_rooms_side_by_side`'s RoomA (x in [-200,-100])
    # and RoomB (x in [-100,0]) share the x=-100 plane with nothing solid between their voids
    # (`Rock` is carved straight through by both, both spanning the same y in [-100,100], z in
    # [-50,50]) -- `Bridge` (40 x 200 x 100 at (-100,0,0), so x in [-120,-80]) straddles that shared
    # plane, 20uu into each room's void, matching both rooms' y/z extents exactly (flush, never past
    # them) and nowhere near either room's own outer wall (x=-200 / x=0).
    #
    # Hand-traced (see Task 4's own hand-trace for the operative-last-writer condition (ii)): for
    # the piece of Bridge in RoomA's box (x in [-120,-100]), `_last_writer_excluding(p,
    # exclude="Bridge")` is RoomA itself, so (ii) holds; (iii) follows automatically since RoomA is
    # a Subtract. Symmetrically for RoomB's box (x in [-100,-80]). Bridge is the LAST actor in trunk
    # order, so `resolved_matter_of(Bridge, p)` holds everywhere in it and `_source_cells(Bridge)`
    # is unfiltered -- but its matter never reaches a resolved SOLID face (its x-range sits entirely
    # inside the RoomA/RoomB void union, and its y/z faces are flush with, never past, each room's
    # own walls), so `crosses` stays silent both directions. This test ALSO pins the round-5
    # regression (Task 4): `Outer` is first in trunk order and the old condition (ii) read True for
    # it unconditionally, so it must NOT appear in `dsts` alongside the two correct facts.
    s = survey_scenarios.two_rooms_side_by_side()
    outer_shared_add = brush("Bridge", (40, 200, 100), (-100, 0, 0))
    level = dataclasses.replace(s.level, actors={**s.level.actors, "Bridge": outer_shared_add},
                                order=s.level.order + ["Bridge"])
    ctx = build_context(level, s.index, "Bridge", s.defaults)
    facts = occupies_facts_for(ctx)
    dsts = {f.dst for f in facts if f.src == "Bridge" and f.relation == "occupies"}
    # Equality, not a subset check: also pins that "Outer" does not appear.
    assert dsts == {"RoomA", "RoomB"}
    assert not any(f.relation == "crosses" for f in crosses_facts_for(ctx))


def test_containment_winner_and_contains_facts_for_are_gone():
    """No back-compat cruft: the winner-take-all contains machinery must not exist any more."""
    assert not hasattr(actor_survey, "containment_winner")
    assert not hasattr(actor_survey, "contains_facts_for")
    assert not hasattr(actor_survey, "_containment_candidates")
```

- [ ] **Step 2: Run them, confirm they fail**

`bin/test -k "occupies_facts_for or containment_winner_and_contains_facts_for"` → FAIL

- [ ] **Step 3: Implement**

First `grep -rn "containment_winner\|_containment_candidates\|contains_facts_for\|VOLUME_TOLERANCE_REL\|volume_tolerance\|volumes_tied" uedcli/`
to confirm nothing outside this deleted block calls them (expected: only their own tests, which Step
1 already lists for deletion). `authored_volume` (`actor_survey.py:504-510`) is NOT part of this
deletion — it has its own standalone tests (`test_authored_volume_sums_every_cell_of_a_non_convex_brush`,
`test_authored_volume_of_a_non_brush_actor_is_zero`) independent of `containment_winner`'s use of it,
so it stays as a general-purpose utility even though its one internal caller is going away. Delete
lines 1974-2064 (`VOLUME_TOLERANCE_REL` through `contains_facts_for`) entirely. In their place:

```python
def occupies_facts_for(ctx: SurveyContext) -> list[CsgFact]:
    """`occupies`: the occupant leads, whichever side is surveyed. Two directions, both computed --
    the surveyed actor as OCCUPANT (against every Subtract in its neighborhood) and as SUBTRACT
    (against every occupant candidate in its neighborhood). NOT a competition: `occupies` fires
    independently per `(occupant, subtract)` pair, unlike the retired `contains`'s single-winner
    rule -- an occupant seated across two Subtracts' voids reports `occupies` against both (spec,
    "composes where containment cannot")."""
    facts: list = []

    def _occupies(occupant, subtract) -> bool:
        if occupant.brush is None:
            return _occupies_point_exists(ctx, occupant, subtract)
        kind = _kind(ctx, occupant)
        if kind in ("add", "semisolid"):
            return _occupies_matter_exists(ctx, occupant, subtract)
        if kind == "nonsolid":
            return _occupies_nonsolid_exists(ctx, occupant, subtract)
        return False   # subtract/intersect/deintersect/mover are never occupants

    if ctx.surveyed.brush is None or _kind(ctx, ctx.surveyed) != "subtract":
        subtracts = [a for a in ctx.near if a.brush is not None and _kind(ctx, a) == "subtract"]
        for s in subtracts:
            if s.name != ctx.name and _occupies(ctx.surveyed, s):
                facts.append(CsgFact(src=ctx.name, dst=s.name, relation="occupies"))
    if ctx.surveyed.brush is not None and _kind(ctx, ctx.surveyed) == "subtract":
        candidates = list(ctx.near) + list(ctx.points)
        for occupant in candidates:
            if occupant.name != ctx.name and _occupies(occupant, ctx.surveyed):
                facts.append(CsgFact(src=occupant.name, dst=ctx.name, relation="occupies"))

    return sorted(facts, key=lambda f: (f.src, f.dst))
```

Update `csg_facts_for` (`actor_survey.py:2177-2184`) to call `occupies_facts_for` instead of
`contains_facts_for`, keeping the spec's fixed print order (`crosses`, `touches`, `connects`,
`occupies`, `carves`):

```python
def csg_facts_for(ctx: SurveyContext) -> list:
    out: list = []
    for fn in (crosses_facts_for, touches_facts_for, connects_facts_for,
               occupies_facts_for, carves_facts_for):
        out.extend(fn(ctx))
    return out
```

Delete every `test_contains_*` test (`test_contains_is_uncontested_when_the_only_other_candidate_is_an_add`
through `test_contains_does_not_treat_a_mover_as_a_subtract`, `test_volume_tolerance_is_a_named_constant_not_an_inline_literal`)
from `test_actor_survey.py` — they test a relation and a mechanism (single-winner competition) that no
longer exist.

- [ ] **Step 4: Run, confirm pass**

`bin/test -k "occupies"` → PASS. `bin/test -k "actor_survey"` → no `contains`-named test remains, no
`AttributeError` from a stale reference.

- [ ] **Step 5: Commit**

```bash
git add uedcli/actor_survey.py uedcli/tests/test_actor_survey.py
git commit -m "Replace csg contains with occupies; delete the winner-take-all machinery"
```

---

## Task 7: `carves` — exact ordered-volume measure

**Files:**
- Modify: `uedcli/actor_survey.py:2066-2081` (`CARVE_AREA_EPS`, `_CARVE_TARGET_KINDS` stay —
  `CARVE_AREA_EPS` is deleted, replaced by Task 2's `CARVE_VOLUME_EPS`), `2091-2166`
  (`authored_face_area`/`surviving_face_area`/`removed_by`/`carves_facts_for` — the first three are
  deleted, `removed_by`'s counterfactual-solve approach is replaced)
- Test: `uedcli/tests/test_actor_survey.py`
- Test fixture: `uedcli/tests/survey_scenarios.py`

**Interfaces:**
- Consumes: `_cell_intersection`, `_partition_by_brushes`, `_piece_centroid`, `_victim_matter_just_before`
  (Task 2), `cell_volume` (existing).
- Produces: `_carves_volume(ctx: SurveyContext, s, victim) -> float`

- [ ] **Step 1: Add the internal-cavity fixture**

```python
def a_subtract_buried_inside_an_adds_interior() -> Scenario:
    """Trunk order: Room, Block, InnerCut.

    * `Room`     1024^3 Subtract at (0, 0, 0)
    * `Block`    256^3 Add at (0, 0, 0)             — x,y,z in [-128, 128]
    * `InnerCut` 64^3 Subtract at (0, 0, 0)          — x,y,z in [-32, 32], fully inside `Block`'s
      interior; none of its six faces coincide with any of `Block`'s six, so `Block`'s own EXTERIOR
      polys are untouched by the carve (an internal cavity, no exterior-face area lost).

    Pins the spec's central `carves` case: the retired face-area `removed_by` would report NO carve
    here (`Block`'s own surviving face area is unchanged), but a real internal cavity IS a carve by
    the exact-volume measure -- `carves(InnerCut, Block)`'s volume is exactly `InnerCut`'s own
    64^3 = 262144.
    """
    return _scenario([
        brush("Room", (1024, 1024, 1024), (0, 0, 0), csg="subtract"),
        brush("Block", (256, 256, 256), (0, 0, 0)),
        brush("InnerCut", (64, 64, 64), (0, 0, 0), csg="subtract"),
    ])
```

- [ ] **Step 2: Write the failing tests**

```python
def test_carves_volume_finds_a_fully_internal_cavity():
    s = survey_scenarios.a_subtract_buried_inside_an_adds_interior()
    ctx = build_context(s.level, s.index, "Block", s.defaults)
    volume = _carves_volume(ctx, s.level.actors["InnerCut"], s.level.actors["Block"])
    assert volume == pytest.approx(64.0 ** 3)


def test_carves_volume_restricts_to_the_victims_own_matter():
    # spec's own worked distinction: `removed_by`'s replacement must count only the VICTIM's own
    # matter as solid-before-S, not any Add's -- pillar_in_room-style: Cutter only takes the right
    # half of Pillar's height; the LEFT half of Pillar's volume must not be counted.
    s = survey_scenarios.pillar_in_room()
    ctx = build_context(s.level, s.index, "Pillar", s.defaults)
    volume = _carves_volume(ctx, s.level.actors["Cutter"], s.level.actors["Pillar"])
    pillar_volume = 128.0 * 128.0 * 512.0
    assert 0 < volume < pillar_volume


def test_carves_volume_is_zero_where_the_subtract_only_stopped_flush():
    s = survey_scenarios.subtract_stops_flush_against_a_wall()
    ctx = build_context(s.level, s.index, "Wall", s.defaults)
    volume = _carves_volume(ctx, s.level.actors["Room"], s.level.actors["Wall"])
    assert volume == pytest.approx(0.0)
```

- [ ] **Step 3: Run them, confirm they fail**

`bin/test -k "carves_volume"` → FAIL

- [ ] **Step 4: Implement**

First check for other call sites before deleting anything: `grep -rn "authored_face_area\|surviving_face_area\|removed_by\|CARVE_AREA_EPS" uedcli/`
(inside and outside `actor_survey.py` — includes any test that calls one of these directly rather than
through `carves_facts_for`). If a test calls one of them directly to compute an expected value, update
that test to compute its expectation a different way (or delete it if it was specifically testing the
retired face-area mechanism) rather than leaving a dangling reference. Then delete
`authored_face_area`, `surviving_face_area`, `removed_by` (`actor_survey.py:2091-2138`) and
`CARVE_AREA_EPS` (`2066-2071`) — nothing in `carves_facts_for` calls them once rewritten below.

```python
def _carves_volume(ctx: SurveyContext, s, victim) -> float:
    """The EXACT volume of `victim INTERSECT s INTERSECT {victim's own matter, just before s}` --
    `carves`'s measurement basis (owner ruling), replacing the retired face-area `removed_by`. Same
    exact evaluator as `occupies`: partition the shared `victim INTERSECT s` region by the Subtracts
    strictly between `victim` and `s` in trunk order (the only brushes `_victim_matter_just_before`
    reads), then sum the pieces whose centroid still passes it."""
    v_i = ctx.csg_index.get(victim.name, -1)
    s_i = ctx.csg_index.get(s.name, len(ctx.csg_order))
    between_subtracts = [a for a in ctx.csg_order[v_i + 1:s_i] if ctx.kinds[a.name] == "subtract"]
    total = 0.0
    for v_cell in actorgraph.decompose_convex(victim, cache=ctx.cells):
        for s_cell in actorgraph.decompose_convex(s, cache=ctx.cells):
            overlap = _cell_intersection(v_cell, s_cell)
            if overlap is None:
                continue
            for piece in _partition_by_brushes(overlap, between_subtracts, ctx):
                if _victim_matter_just_before(ctx, victim, s, _piece_centroid(piece)):
                    total += cell_volume(piece)
    return total
```

Rewrite `carves_facts_for` (`actor_survey.py:2141-2166`) to use `_carves_volume` in place of
`removed_by`:

```python
def carves_facts_for(ctx: SurveyContext) -> list[CsgFact]:
    """`carves`: a Subtract removed part of another actor's originally-contributed matter -- ANY
    amount, including a fully-internal cavity (`_carves_volume` > `CARVE_VOLUME_EPS`). The agent
    (the Subtract) leads, whichever side is surveyed, so both directions are computed."""
    facts: list = []

    if ctx.surveyed.brush is not None and query.csg_is_subtract(ctx.surveyed):
        for other in ctx.near:
            if kind_of(other, ctx.class_index) not in _CARVE_TARGET_KINDS:
                continue
            if _carves_volume(ctx, ctx.surveyed, other) > CARVE_VOLUME_EPS:
                facts.append(CsgFact(src=ctx.name, dst=other.name, relation="carves"))
    elif ctx.surveyed.brush is not None and \
            kind_of(ctx.surveyed, ctx.class_index) in _CARVE_TARGET_KINDS:
        for other in ctx.near:
            if not query.csg_is_subtract(other):
                continue
            if _carves_volume(ctx, other, ctx.surveyed) > CARVE_VOLUME_EPS:
                facts.append(CsgFact(src=other.name, dst=ctx.name, relation="carves"))

    return sorted(facts, key=lambda f: (f.src, f.dst))
```

- [ ] **Step 5: Run, confirm pass**

`bin/test -k "carves"` → PASS, including the pre-existing `test_carves_*`/
`test_a_partially_overlapping_second_subtract_carves_and_connects` tests (same relation, new
mechanism underneath).

- [ ] **Step 6: Commit**

```bash
git add uedcli/actor_survey.py uedcli/tests/survey_scenarios.py uedcli/tests/test_actor_survey.py
git commit -m "Move carves to an exact ordered-volume measure"
```

- [ ] **Step 7: trim the inbox finding this task fixes**

`dev/docs/board/inbox/csg-carves-misses-a-carve-entirely-interior-to/` documents this exact bug —
once this lands, `git mv` it to `dev/docs/board/done/`, trimmed to a one-line reference (the board's
own `done/` convention), rather than left in `inbox/` to be re-discovered later.

---

## Task 8: `connects` — sealed-bubble reachability fixture (conditional fix)

The spec itself flags this as unconfirmed ("appears, from reading, to still report `connects`... if
confirmed, `connects` needs a reachability test"). Build the fixture, observe ACTUAL current behavior
before writing any fix code — do not assume the bug is real.

**Files:**
- Modify: `uedcli/actor_survey.py:1835-1936` (`_planar_void_contact`/`voids_meet`) — only if Step 3
  below observes the false positive
- Test: `uedcli/tests/test_actor_survey.py`
- Test fixture: `uedcli/tests/survey_scenarios.py`

**Interfaces:**
- Consumes: `voids_meet(ctx: SurveyContext, a, b) -> bool` (existing, `actor_survey.py:1921`),
  `connects_facts_for` (existing, `1939`).
- Produces: unchanged signatures; `voids_meet`'s body only, if the fixture confirms the bug.

- [ ] **Step 1: Add the fixture**

```python
def subtract_sealed_inside_a_block_sharing_the_outer_walls_plane() -> Scenario:
    """Trunk order: OuterRoom, Block, InnerCut.

    * `OuterRoom` 1024^3 Subtract at (0, 0, 0)         — walls at x = +/-512
    * `Block`     256 x 1024 x 1024 Add at (-384, 0, 0) — x in [-512, -256], flush against
      OuterRoom's own -X wall (x=-512) — an ordinary "shelf pushed back against the wall" idiom
      (compare `an_add_inside_an_enclosing_subtract(clearance=0)`)
    * `InnerCut`  64 x 512 x 512 Subtract at (-480, 0, 0) — x in [-512, -448], carved into `Block`
      from the SAME x=-512 plane `Block` shares with `OuterRoom`'s own wall, but not reaching past
      `Block`'s own +X extent (x=-256) — a bubble sealed inside `Block`'s solid, nowhere near
      `OuterRoom`'s own big central void (which starts around x=-256 and runs to x=512)

    `InnerCut` and `OuterRoom` share a real, coincident x=-512 plane (both author a wall there), so
    `_planar_void_contact`'s candidate-plane test has something to test at all -- the question this
    fixture is FOR is whether the voidness probe on that shared patch correctly tells "InnerCut's own
    sealed pocket" apart from "OuterRoom's own reachable interior", or reports `connects` merely
    because BOTH read void immediately off that one coincident plane.
    """
    return _scenario([
        brush("OuterRoom", (1024, 1024, 1024), (0, 0, 0), csg="subtract"),
        brush("Block", (256, 1024, 1024), (-384, 0, 0)),
        brush("InnerCut", (64, 512, 512), (-480, 0, 0), csg="subtract"),
    ])
```

- [ ] **Step 2: Write the test asserting the CORRECT (desired) behavior**

```python
def test_connects_does_not_fire_for_a_subtract_sealed_inside_a_solid_block():
    s = survey_scenarios.subtract_sealed_inside_a_block_sharing_the_outer_walls_plane()
    ctx = build_context(s.level, s.index, "InnerCut", s.defaults)
    facts = connects_facts_for(ctx)
    assert not any(f.dst == "OuterRoom" for f in facts), (
        "InnerCut's void is sealed inside Block's solid -- it must not report connects to "
        "OuterRoom just because they share a coincident wall plane")
```

- [ ] **Step 3: Run it and read the actual result — this determines the rest of the task**

`bin/test -k test_connects_does_not_fire_for_a_subtract_sealed_inside_a_solid_block -v`

- **If it PASSES already:** the described false positive does not reproduce on this construction.
  Keep the fixture and test as a regression pin regardless (a sealed-bubble-vs-outer-wall shape is
  worth having either way). Do not write any fix code. Log a short finding via
  `bin/board new inbox` noting the spec's described false positive could not be reproduced on this
  construction, so a future session knows it was checked, and stop here — proceed to Step 6.
- **If it FAILS (connects wrongly fires):** the false positive is confirmed. Continue to Step 4.

- [ ] **Step 4 (only if Step 3 failed): fix `voids_meet`/`_planar_void_contact` to require reachability**

Change `voids_meet` (`actor_survey.py:1921-1936`) to additionally verify the void patch found by
`_planar_void_contact` is reachable from `b`'s own carved interior, not merely void at the shared
plane — walk outward from the contact patch through `b`'s own resolved void using the same
`ctx.probe.solidity.point_is_solid` oracle `_planar_void_contact` already calls, stepping along `b`'s
own carve by `CSG_TOLERANCE`-scaled increments until either the void patch is confirmed connected to
`b`'s own interior sample point or a solid wall is hit within `b`'s own authored bounds. (Work out the
exact step function against the confirmed-failing fixture from Step 3 — its own geometry is the
target to satisfy; do not generalize past it without a second confirmed case.)

**Step 4 landed one-directional, then was corrected to be symmetric.** The confirmed-failing fixture
above was surveyed from `InnerCut` only, so the first landing of `_void_reaches_interior` was wired
one-directional: `voids_meet(ctx, a, b)` walked only toward `b`'s own interior. That closes the
`InnerCut`-survey direction (`voids_meet(ctx, InnerCut, OuterRoom)` walks toward `OuterRoom`'s
interior, blocked by `Block`'s solid — correctly no fact) but `spec.md` states `connects` is
symmetric, and the one-directional check does not satisfy that: surveying `OuterRoom` instead calls
`voids_meet(ctx, OuterRoom, InnerCut)`, which walks toward `InnerCut`'s own interior — trivially
reachable, since `InnerCut`'s sealed bubble is void all the way to its own centroid — and wrongly
reports `connects(OuterRoom, InnerCut)`. Confirmed live by running `connects_facts_for` surveying each
actor in turn, not by hand-tracing.

Fixed by requiring **both** directions: `voids_meet` now returns
`_void_reaches_interior(ctx, point, a) and _void_reaches_interior(ctx, point, b)` — the contact point
must reach both `a`'s own interior and `b`'s own interior, or the patch is rejected as a sealed
bubble on whichever side is blocked. Added
`test_connects_does_not_fire_the_other_direction_either` (surveying `OuterRoom` on the same fixture)
alongside the original `InnerCut`-direction test — the gap this closes is exactly that the original
Step 2 test only checked one survey direction of a relation `spec.md` already declares symmetric.

- [ ] **Step 5 (only if Step 4 ran): run the full `connects` test set**

`bin/test -k "connects"` — every existing `test_connects_*` test (`test_connects_fires_for_two_subtracts_sharing_a_plane_and_touches_does_not`
through `test_connects_still_rejects_an_edge_only_meeting_with_the_broader_candidate_set`) must still
pass; they are all reachable-void cases, so a correct reachability fix changes nothing about them.

- [ ] **Step 6: Commit**

```bash
git add uedcli/actor_survey.py uedcli/tests/survey_scenarios.py uedcli/tests/test_actor_survey.py
git commit -m "Pin the sealed-subtract-bubble connects fixture"
```

(If Step 4 ran, use `"Add connects reachability test for a sealed subtract bubble"` instead, and
include the `actor_survey.py` diff.)

---

## Task 9: raw tier — the pure-geometry pairwise relation

Replaces the raw tier's dependency on `actorgraph.classify_pair`/`brush_overlap` (CSG-order/
Subtract/Mover branching — `actorgraph.py:562-606`) with a new, local, pure-geometry classifier.
`actorgraph.classify_pair`/`build_graph` themselves are NOT modified — `level graph` keeps its current
behavior; this task only stops `actor_survey.py`'s raw tier from calling into that branching logic. The
one addition to `actorgraph.py` is new and additive: a depth-returning sibling of
`cells_touch_or_overlap`, needed to split `overlaps` from `meets`.

**Owner ruling, 2026-09-27** (folded into `spec.md`'s "Removed" bullet): `classify_pair` is shared with
`level graph`'s `build_graph`, so this task adds a separate function rather than rewriting
`classify_pair` in place. Proceed with the design below.

**Files:**
- Modify: `uedcli/actorgraph.py` (add `sat_interpenetration_depth`, after `cells_touch_or_overlap`,
  line 325)
- Modify: `uedcli/actor_survey.py` (new `raw_relation_for`, near `authored_shape_contains`)
- Test: `uedcli/tests/test_actor_survey.py`, new tests in `uedcli/tests/test_actorgraph.py` if that
  file exists (check with `find uedcli/tests -iname 'test_actorgraph*'`; if none exists, add the SAT
  test to `test_actor_survey.py` instead, importing `actorgraph` directly — do not create a new test
  module for one function)

**Interfaces:**
- Consumes: `actorgraph._sat_axes`, `actorgraph._bbox`, `actorgraph._TOUCH_EPS`,
  `authored_shape_contains(container, target, cells) -> bool` (existing, `actor_survey.py:567`),
  `actorgraph.decompose_convex`.
- Produces:
  - `actorgraph.sat_interpenetration_depth(cell_a, cell_b) -> float | None`
  - `raw_relation_for(name_a, actor_a, name_b, actor_b, cache: dict) -> tuple[str, str, str] | None`

- [ ] **Step 1: Write the failing tests**

```python
def test_sat_interpenetration_depth_is_none_for_disjoint_cells():
    a = _box_cell((0, 0, 0), (10, 10, 10))
    b = _box_cell((100, 100, 100), (110, 110, 110))
    assert actorgraph.sat_interpenetration_depth(a, b) is None


def test_sat_interpenetration_depth_is_small_for_a_flush_contact():
    a = _box_cell((0, 0, 0), (10, 10, 10))
    b = _box_cell((10, 0, 0), (20, 10, 10))
    depth = actorgraph.sat_interpenetration_depth(a, b)
    assert depth is not None and depth <= actorgraph._TOUCH_EPS


def test_sat_interpenetration_depth_is_large_for_a_real_overlap():
    a = _box_cell((0, 0, 0), (10, 10, 10))
    b = _box_cell((5, 0, 0), (15, 10, 10))
    depth = actorgraph.sat_interpenetration_depth(a, b)
    assert depth == pytest.approx(5.0)


def test_raw_relation_reports_coincides_for_identical_brushes():
    s = survey_scenarios.two_equal_volume_subtracts()
    cache: dict = {}
    rel = raw_relation_for("EarlierRoom", s.level.actors["EarlierRoom"],
                           "LaterRoom", s.level.actors["LaterRoom"], cache)
    assert rel == ("EarlierRoom", "LaterRoom", "coincides")


def test_raw_relation_reports_encloses_with_the_container_leading():
    s = survey_scenarios.room_with_pillar_and_light()
    cache: dict = {}
    rel = raw_relation_for("Pillar", s.level.actors["Pillar"],
                           "Room", s.level.actors["Room"], cache)
    assert rel == ("Room", "Pillar", "encloses")


def test_raw_relation_reports_overlaps_for_a_subtract_carving_its_add():
    s = survey_scenarios.niche_carved_into_wall()
    cache: dict = {}
    rel = raw_relation_for("Wall", s.level.actors["Wall"],
                           "Niche", s.level.actors["Niche"], cache)
    assert rel == ("Wall", "Niche", "overlaps")


def test_raw_relation_reports_meets_for_a_flush_contact():
    s = survey_scenarios.two_adds_butted_face_to_face(offset=0.0)
    cache: dict = {}
    rel = raw_relation_for("BlockA", s.level.actors["BlockA"],
                           "BlockB", s.level.actors["BlockB"], cache)
    assert rel == ("BlockA", "BlockB", "meets")


def test_raw_relation_is_none_for_disjoint_brushes():
    s = survey_scenarios.far_apart_rooms()
    cache: dict = {}
    rel = raw_relation_for("FarRoom", s.level.actors["FarRoom"],
                           "Distant", s.level.actors["Distant"], cache)
    assert rel is None
```

- [ ] **Step 2: Run them, confirm they fail**

`bin/test -k "sat_interpenetration_depth or raw_relation"` → FAIL

- [ ] **Step 3: Implement `sat_interpenetration_depth`**

Add to `actorgraph.py`, directly after `cells_touch_or_overlap` (line 325):

```python
def sat_interpenetration_depth(cell_a: ConvexCell, cell_b: ConvexCell) -> float | None:
    """The minimum positive-axis overlap across every SAT candidate axis (`_sat_axes`) -- how far
    the two convex cells' interiors interpenetrate -- or None when some axis separates them by more
    than `_TOUCH_EPS` (disjoint, or merely touching with zero real overlap). Generalizes
    `cells_touch_or_overlap`'s own axis loop from a boolean reject to the minimum positive overlap
    depth, so a caller can tell flush contact (depth <= `_TOUCH_EPS`) from real interpenetration
    (depth > `_TOUCH_EPS`) -- the discriminator `actor survey`'s raw tier needs to split `overlaps`
    from `meets` (`_TOUCH_EPS` alone cannot: `cells_touch_or_overlap` already lumps both cases into
    one boolean)."""
    a_lo, a_hi = _bbox(cell_a)
    b_lo, b_hi = _bbox(cell_b)
    if any(a_hi[i] < b_lo[i] - _TOUCH_EPS or b_hi[i] < a_lo[i] - _TOUCH_EPS for i in range(3)):
        return None
    min_overlap = None
    for axis in _sat_axes(cell_a, cell_b):
        a_vals = [_dot(axis, v) for v in cell_a.vertices]
        b_vals = [_dot(axis, v) for v in cell_b.vertices]
        overlap = min(max(a_vals), max(b_vals)) - max(min(a_vals), min(b_vals))
        if overlap < -_TOUCH_EPS:
            return None
        min_overlap = overlap if min_overlap is None else min(min_overlap, overlap)
    return min_overlap
```

- [ ] **Step 4: Implement `raw_relation_for`**

Add to `actor_survey.py`, directly after `authored_shape_contains` (line 609):

```python
def raw_relation_for(name_a, actor_a, name_b, actor_b, cache: dict) -> tuple[str, str, str] | None:
    """The RCC (region-connection-calculus) relation between two BRUSH actors' own AUTHORED volumes
    -- pure geometry, ignoring CsgOper, trunk order, and Mover-ness entirely (spec, raw tier). None
    for disjoint volumes. Decision procedure (spec's own): mutual full containment -> `coincides`
    (checked FIRST -- takes priority over `encloses`, since identical brushes satisfy
    `authored_shape_contains` both ways); one-way full containment -> `encloses`; interiors
    interpenetrate beyond `_TOUCH_EPS` -> `overlaps`; boundaries meet with no interior penetration ->
    `meets`. Returns `(src, dst, relation)` already in display direction: `coincides`/`overlaps`/
    `meets` are symmetric and lead with `name_a` (the caller's own convention -- always the surveyed
    actor); `encloses` leads with whichever of the two is the container."""
    b_in_a = authored_shape_contains(actor_a, actor_b, cache)
    a_in_b = authored_shape_contains(actor_b, actor_a, cache)
    if a_in_b and b_in_a:
        return (name_a, name_b, "coincides")
    if b_in_a:
        return (name_a, name_b, "encloses")
    if a_in_b:
        return (name_b, name_a, "encloses")

    cells_a = actorgraph.decompose_convex(actor_a, cache=cache)
    cells_b = actorgraph.decompose_convex(actor_b, cache=cache)
    best_depth, any_touch = None, False
    for ca in cells_a:
        for cb in cells_b:
            depth = actorgraph.sat_interpenetration_depth(ca, cb)
            if depth is not None:
                any_touch = True
                best_depth = depth if best_depth is None else max(best_depth, depth)
    if best_depth is not None and best_depth > actorgraph._TOUCH_EPS:
        return (name_a, name_b, "overlaps")
    if any_touch:
        return (name_a, name_b, "meets")
    return None
```

- [ ] **Step 5: Run, confirm pass**

`bin/test -k "sat_interpenetration_depth or raw_relation"` → PASS

- [ ] **Step 6: Commit**

```bash
git add uedcli/actorgraph.py uedcli/actor_survey.py uedcli/tests/test_actor_survey.py
git commit -m "Add the raw tier's pure-geometry pairwise relation"
```

---

## Task 10: raw tier — rewrite `raw_facts_for`, remove the old `RawFact` shape

**Files:**
- Modify: `uedcli/actor_survey.py:304-419` (`RawFact`, `RawFacts`, `_flip`, `_from_edge`,
  `raw_facts_for`), `422-433` (`format_raw_line`)
- Test: `uedcli/tests/test_actor_survey.py` — delete
  `test_raw_tier_reports_touches_and_carves_for_the_surveyed_brush`,
  `test_raw_tier_spells_it_carves_with_the_subtract_leading_not_carved_by`,
  `test_raw_touches_puts_the_surveyed_actor_first_and_swaps_its_matched_pair_with_it`,
  `test_from_edge_flips_a_symmetric_fact_when_the_surveyed_actor_is_the_edges_dst`,
  `test_raw_tier_reports_contains_for_a_mover_inside_a_subtract`,
  `test_raw_tier_reports_contains_for_a_point_actor_inside_the_surveyed_brush`,
  `test_raw_tier_surveying_the_point_actor_shows_the_same_containment`,
  `test_raw_tier_does_not_use_build_graph`,
  `test_raw_line_format_matches_level_graphs_grammar_with_a_tier_prefix`,
  `test_raw_line_carries_no_idx_or_area_on_a_contains_line` — all test a shape (`contains`/`carves`,
  `matched_pair`, `_flip`/`_from_edge`) this task removes; replaced by the tests below.

**Interfaces:**
- Consumes: `raw_relation_for` (Task 9), `near_brushes`, `nearby_point_actors` (existing, unchanged).
- Produces: `RawFact(src: str, dst: str, relation: str)` (drops `matched_pair`/`area_estimate`),
  `raw_facts_for(level, class_index, name, defaults, *, cells=None) -> RawFacts` (same signature,
  new body), `format_raw_line(fact: RawFact, nodes: dict) -> str` (bare, no annotation ever).

- [ ] **Step 1: Write the failing tests**

```python
def test_raw_tier_reports_encloses_for_a_subtract_around_an_add():
    s = survey_scenarios.room_with_pillar_and_light()
    raw = raw_facts_for(s.level, s.index, "Room", s.defaults)
    assert any(f.src == "Room" and f.dst == "Light" and f.relation == "encloses"
               for f in raw.facts)


def test_raw_tier_never_reports_carves():
    s = survey_scenarios.niche_carved_into_wall()
    raw = raw_facts_for(s.level, s.index, "Wall", s.defaults)
    assert not any(f.relation == "carves" for f in raw.facts)
    assert any(f.relation == "overlaps" for f in raw.facts)


def test_raw_tier_leads_symmetric_relations_with_the_surveyed_actor():
    s = survey_scenarios.two_adds_butted_face_to_face(offset=0.0)
    raw = raw_facts_for(s.level, s.index, "BlockB", s.defaults)
    fact = next(f for f in raw.facts if f.relation == "meets")
    assert fact.src == "BlockB"


def test_raw_tier_encloses_for_a_point_actor_names_the_container():
    s = survey_scenarios.room_with_pillar_and_light()
    raw = raw_facts_for(s.level, s.index, "Light", s.defaults)
    assert raw.facts == [RawFact(src="Room", dst="Light", relation="encloses")]


def test_raw_facts_for_does_not_call_classify_pair(monkeypatch):
    called = []
    monkeypatch.setattr(actorgraph, "classify_pair",
                        lambda *a, **k: called.append(1) or [])
    s = survey_scenarios.niche_carved_into_wall()
    raw_facts_for(s.level, s.index, "Wall", s.defaults)
    assert not called
```

- [ ] **Step 2: Run them, confirm they fail**

`bin/test -k "raw_tier or raw_facts_for"` → FAIL

- [ ] **Step 3: Implement**

Replace `RawFact`, `RawFacts`, `_flip`, `_from_edge`, `raw_facts_for`, `format_raw_line`
(`actor_survey.py:304-433`) with:

```python
@dataclass(frozen=True)
class RawFact:
    """One raw-tier line's worth of information. `src`/`dst` are already in the spec's final
    display direction (`raw_relation_for`'s own job) -- no separate flip step downstream."""
    src: str
    dst: str
    relation: str


@dataclass(frozen=True)
class RawFacts:
    facts: list
    nodes: dict
    skipped: list


def raw_facts_for(level, class_index, name: str, defaults, *,
                  cells: dict | None = None) -> RawFacts:
    """Every raw-tier fact about `name` -- pure authored geometry, over the bounded neighborhood
    (see the module docstring for why bounded). Raises `ActorNotFoundError` for an unknown name, and
    `actorgraph.DegenerateBrushError` when the SURVEYED actor's own brush cannot be decomposed; a
    degenerate NEIGHBOUR is skipped and recorded in `skipped`."""
    if name not in level.actors:
        raise ActorNotFoundError(name)
    cells = {} if cells is None else cells
    surveyed = level.actors[name]
    nodes: dict = {name: actorgraph._node_tag(surveyed, class_index)}
    facts: list[RawFact] = []
    skipped: dict[str, str] = {}

    others = [a for a in near_brushes(level, class_index, surveyed, defaults) if a.name != name]
    points = [a for a in nearby_point_actors(level, surveyed, defaults) if a.name != name]

    if surveyed.brush is not None:
        actorgraph.decompose_convex(surveyed, cache=cells)
        for other in others:
            try:
                actorgraph.decompose_convex(other, cache=cells)
            except actorgraph.DegenerateBrushError as e:
                skipped[other.name] = str(e)
                continue
            rel = raw_relation_for(name, surveyed, other.name, other, cells)
            if rel is not None:
                src, dst, relation = rel
                facts.append(RawFact(src=src, dst=dst, relation=relation))
                nodes[other.name] = actorgraph._node_tag(other, class_index)
        for p in points:
            loc = tuple(float(c) for c in p.location)
            if actorgraph.point_in_brush(surveyed, loc, cache=cells):
                facts.append(RawFact(src=name, dst=p.name, relation="encloses"))
                nodes[p.name] = actorgraph._node_tag(p, class_index)
    else:
        if surveyed.location is not None:
            loc = tuple(float(c) for c in surveyed.location)
            for other in others:
                try:
                    if not actorgraph.point_in_brush(other, loc, cache=cells):
                        continue
                except actorgraph.DegenerateBrushError as e:
                    skipped[other.name] = str(e)
                    continue
                facts.append(RawFact(src=other.name, dst=name, relation="encloses"))
                nodes[other.name] = actorgraph._node_tag(other, class_index)

    return RawFacts(facts=facts, nodes=nodes, skipped=sorted(skipped.items()))


def format_raw_line(fact: RawFact, nodes: dict) -> str:
    """One raw-tier line -- bare, no annotation of any kind, and NO tier-token prefix: the spec's
    Output section drops the per-line `raw `/`csg ` prefix now that relation names are unique across
    tiers ("each line self-identifies its tier by its verb"). The two printed GROUPS are marked by
    fixed order alone, no new marker (owner ruling) -- that is `format_lines`'s concern (Task 12),
    not this function's; this function only ever formats one already-tier-identified fact."""
    return (f"{fact.src} {actorgraph._node_bracket(nodes[fact.src])} --{fact.relation}--> "
            f"{fact.dst} {actorgraph._node_bracket(nodes[fact.dst])}")
```

- [ ] **Step 4: Run, confirm pass**

`bin/test -k "raw_tier or raw_facts_for"` → PASS. Then `bin/test -k actor_survey` and delete/fix any
remaining reference to the removed tests/names (the ones listed in this task's Files section).

- [ ] **Step 5: Commit**

```bash
git add uedcli/actor_survey.py uedcli/tests/test_actor_survey.py
git commit -m "Rewrite the raw tier as pure geometry: encloses/overlaps/meets/coincides"
```

---

## Task 11: raw tier — non-brush display note, no behavior change

The spec's "each raw line still shows the brush kind as a label... not used in the relation" and
"non-brush actors: raw treats a non-brush actor as its Location point only" are both already true of
Task 10's rewrite (`actorgraph._node_bracket` already prints the kind; the non-brush branch already
only ever produces `encloses`). This task is a verification-only pass, not new code.

**Files:**
- Test: `uedcli/tests/test_actor_survey.py`

**Interfaces:**
- Consumes: `raw_facts_for`, `format_raw_line` (Task 10).

- [ ] **Step 1: Write the confirming tests**

```python
def test_raw_line_shows_the_brush_kind_label():
    s = survey_scenarios.niche_carved_into_wall()
    raw = raw_facts_for(s.level, s.index, "Wall", s.defaults)
    lines = [format_raw_line(f, raw.nodes) for f in raw.facts]
    assert any("[Engine.Brush Subtract]" in line for line in lines)


def test_raw_tier_never_reports_overlaps_meets_or_coincides_for_a_point_actor():
    s = survey_scenarios.room_with_a_flush_mounted_prop()
    raw = raw_facts_for(s.level, s.index, "Room", s.defaults)
    point_relations = {f.relation for f in raw.facts if f.dst in ("Keypad", "Ghost", "Bracket")}
    assert point_relations <= {"encloses"}
```

- [ ] **Step 2: Run them**

`bin/test -k "raw_line_shows_the_brush_kind or raw_tier_never_reports_overlaps_meets_or_coincides_for_a_point_actor"`
→ PASS with no code change (Task 10 already produces this). If either fails, Task 10's implementation
has a bug — fix it there, not here.

- [ ] **Step 3: Commit**

```bash
git add uedcli/tests/test_actor_survey.py
git commit -m "Pin raw tier's kind-label display and point-actor relation restriction"
```

---

## Task 12: output shape — drop csg-tier magnitudes and the per-line tier prefix

Owner ruling (2026-09-27): no new marker replaces the dropped prefix — fixed order (raw block, then
csg block) plus the existing blank-line separator is the only signal, confirmed because the two
tiers' relation names are already disjoint (raw: `encloses`/`overlaps`/`meets`/`coincides`; csg:
`touches`/`crosses`/`occupies`/`carves`/`connects`) so every line self-identifies by its verb alone.
Step 7 below implements this (this plan's Option A) directly; Option B is not built.

**Files:**
- Modify: `uedcli/actor_survey.py:704-711` (`CsgFact` — drop `depth_uu`), `1152-1220`
  (`crosses_facts_for`/`record` — stop tracking depth, dedupe on existence only), `2212-2220`
  (`format_csg_line` — bare, no `crosses(...)` annotation, no `csg ` prefix), `2249-2257`
  (`format_lines` — Step 7, blocked), `uedcli/cli/parsers/actor_survey.py` (stale help string:
  `contains` → `occupies`, Step 7)
- Test: `uedcli/tests/test_actor_survey.py` — delete
  `test_csg_line_carries_a_depth_on_crosses_and_nothing_on_the_others` (tests the removed field); fix
  the four other `depth_uu`-referencing tests below (Step 3);
  `uedcli/tests/test_cli_actor_survey.py` — fix `test_survey_prints_raw_lines_and_a_stderr_summary`
  (currently lines 35-41) and `test_survey_prints_raw_block_then_csg_block_then_a_two_number_summary`
  (currently lines 57-68), both keyed off the literal `"raw "`/`"csg "` prefix this task removes
  (Step 7 — verify current line numbers with `grep -n` before editing, they may have drifted)

**Interfaces:**
- Consumes: `penetration_depth` (existing, unchanged internally — still used to DECIDE the predicate,
  per spec "keep `penetration_depth`'s straddle+footprint logic... drop only the reported number").
- Produces: `CsgFact(src: str, dst: str, relation: str)` (drops `depth_uu`),
  `format_csg_line(fact: CsgFact, nodes: dict) -> str` (bare).

- [ ] **Step 1: Write the failing tests**

```python
def test_csg_fact_carries_no_depth_field():
    fact = CsgFact(src="A", dst="B", relation="crosses")
    assert not hasattr(fact, "depth_uu")


def test_csg_line_never_carries_a_depth_annotation():
    s = survey_scenarios.room_with_a_flush_mounted_prop()
    ctx = build_context(s.level, s.index, "Keypad", s.defaults)
    facts = crosses_facts_for(ctx)
    nodes = {ctx.name: actorgraph._node_tag(ctx.surveyed, ctx.class_index),
             "Room": actorgraph._node_tag(s.level.actors["Room"], ctx.class_index)}
    lines = [format_csg_line(f, nodes) for f in facts]
    assert not any("(" in line for line in lines)
```

- [ ] **Step 2: Run them, confirm they fail**

`bin/test -k "csg_fact_carries_no_depth or csg_line_never_carries_a_depth"` → FAIL

- [ ] **Step 3: Implement**

```python
@dataclass(frozen=True)
class CsgFact:
    """One csg-tier line. Bare -- no relation in this tier carries a magnitude (spec, Output
    shape); `crosses` becomes a boolean predicate, deciding existence off `penetration_depth`'s own
    straddle+footprint logic without reporting the number."""
    src: str
    dst: str
    relation: str
```

In `crosses_facts_for` (`actor_survey.py:1152-1220`), change `record`/the dict value to track
presence only (still needs `penetration_depth`'s return value internally, to decide whether a fact
exists at all — only the STORED fact drops it):

```python
def crosses_facts_for(ctx: SurveyContext) -> list[CsgFact]:
    """... (unchanged docstring, prose about depth removed from the fact) ..."""
    facts: dict = {}
    if ctx.probe.solidity is None:
        return []

    def record(src, dst):
        facts[(src, dst)] = CsgFact(src=src, dst=dst, relation="crosses")

    if crosses_source_eligible(ctx.surveyed, ctx.class_index, ctx.defaults):
        cells = _source_cells(ctx, ctx.surveyed)
        if cells:
            for face in ctx.faces:
                if face.owner == ctx.name:
                    continue
                target = ctx.level.actors.get(face.owner)
                if target is None or not crosses_target_eligible(target, ctx.class_index):
                    continue
                if penetration_depth(ctx, cells, face) is not None:
                    record(ctx.name, face.owner)

    if crosses_target_eligible(ctx.surveyed, ctx.class_index):
        own_faces = [f for f in ctx.faces if f.owner == ctx.name]
        if own_faces:
            for other in ctx.near:
                if not crosses_source_eligible(other, ctx.class_index, ctx.defaults):
                    continue
                cells = _source_cells(ctx, other)
                if not cells:
                    continue
                for face in own_faces:
                    if penetration_depth(ctx, cells, face) is not None:
                        record(other.name, ctx.name)
            for p in ctx.points:
                if not crosses_source_eligible(p, ctx.class_index, ctx.defaults):
                    continue
                cells = _source_cells(ctx, p)
                if not cells:
                    continue
                for face in own_faces:
                    if penetration_depth(ctx, cells, face) is not None:
                        record(p.name, ctx.name)

    return [facts[k] for k in sorted(facts)]
```

```python
def format_csg_line(fact: CsgFact, nodes: dict) -> str:
    """One csg-tier line -- bare, no annotation of any kind, no tier-token prefix (see
    `format_raw_line`'s docstring for why; same open question, `format_lines` owns the answer)."""
    return (f"{fact.src} {actorgraph._node_bracket(nodes[fact.src])} --{fact.relation}--> "
            f"{fact.dst} {actorgraph._node_bracket(nodes[fact.dst])}")
```

Delete `test_csg_line_carries_a_depth_on_crosses_and_nothing_on_the_others`. Also update
`test_no_csg_line_ever_carries_an_idx` and any other existing format test that asserts on a literal
`"csg "`/`"raw "` prefix substring — change the assertion to check the bare grammar instead (`" --"`
appears, no leading tier token).

**Four more `depth_uu` references this change breaks, verified by `grep -n depth_uu
uedcli/tests/test_actor_survey.py` (none of these overlap Task 3's `shelf_pokes_through_a_niche_wall`
rewrites — different fixtures):**

- `test_crosses_fires_for_a_flush_mounted_collision_extent_with_a_measured_depth`
  (`test_actor_survey.py:644-660`): drop the range assertion
  (`assert 4.0 < next(f for f in facts if f.dst == "Room").depth_uu < 12.0`), replace with
  `assert any(f.src == "Keypad" and f.dst == "Room" and f.relation == "crosses" for f in facts)`.
  Trim the docstring's depth-motivated paragraph (the ~8uu-median reasoning is `actor relation`'s
  concern now, not survey's) and rename the test to
  `test_crosses_fires_for_a_flush_mounted_collision_extent` (it no longer measures anything).
- `test_crosses_fires_for_a_point_actor_whose_location_is_outside_the_surveyed_brush`
  (`:663-682`): delete the last line (`assert 20.0 < fact.depth_uu < 28.0`) — the existence check the
  line above it already makes (`assert fact is not None and fact.relation == "crosses"`) is sufficient.
- `test_touches_fires_between_the_surveyed_actor_and_a_face_it_is_flush_against` (`:715-722`): delete
  the last line (`assert all(f.depth_uu is None for f in facts)`) — nothing replaces it, the field is
  simply gone.
- Task 3 Step 12's new `test_crosses_fires_for_a_semisolid_partially_overlapping_an_add` (added earlier
  in this plan, correct at the time Task 3 lands since `CsgFact` still has `depth_uu` then): delete its
  last line (`assert 25.0 < fact.depth_uu < 35.0`) here in Task 12 — the `assert fact is not None,
  f"surveying {surveyed}"` line above it already covers existence.

- [ ] **Step 4: Run, confirm pass**

`bin/test -k "csg_fact_carries_no_depth or csg_line_never_carries_a_depth or crosses or touches"` →
PASS (the `touches` term is needed for `test_touches_fires_between_the_surveyed_actor_and_a_face_it_is_flush_against`, one of the four `depth_uu` fixes above)

- [ ] **Step 5: Commit**

```bash
git add uedcli/actor_survey.py uedcli/tests/test_actor_survey.py
git commit -m "Drop the crosses depth annotation; csg lines are fully bare"
```

- [ ] **Step 6: Run the full `format_lines`/CLI test set to find every remaining tier-prefix assertion**

`bin/test -k "actor_survey or cli_actor_survey"` — fix any test still asserting a literal `"raw "`/
`"csg "` line prefix (there should be few left after Steps 1–5; `format_lines` itself, Step 7 below,
is the last piece).

- [ ] **Step 7: rewrite `format_lines`; fix every remaining literal-prefix test and the stale CLI help string**

`format_lines` (`actor_survey.py:2249-2257`):

```python
def format_lines(result: SurveyResult) -> list:
    """Every stdout line of a survey: the raw block, a blank separator when both tiers have
    something, then the csg block. No per-line tier prefix (relation names are unique across
    tiers, so each line self-identifies by its verb) and no other marker -- the two groups are
    "authored" and "resolved" by fixed order alone."""
    lines = [format_raw_line(f, result.nodes) for f in result.raw]
    csg_lines = [format_csg_line(f, result.nodes) for f in result.csg]
    if lines and csg_lines:
        lines.append("")
    return lines + csg_lines
```

Three CLI tests key off the literal `"raw "`/`"csg "` prefix this step removes — verify current line
numbers with `grep -n` before editing (they may have drifted from the numbers below):

- `test_survey_prints_raw_lines_and_a_stderr_summary` (`test_cli_actor_survey.py:35-41`) —
  `raw = [ln for ln in out.out.splitlines() if ln.startswith("raw ")]` no longer selects anything.
  Change the selector to the known raw relation-name set instead of the prefix, e.g.:
  `raw = [ln for ln in out.out.splitlines() if any(f" --{r}--> " in ln for r in
  ("encloses", "overlaps", "meets", "coincides"))]`.
- `test_survey_prints_raw_block_then_csg_block_then_a_two_number_summary`
  (`test_cli_actor_survey.py:57-68`) — same fix, selecting `csg` lines by the csg relation-name set
  (`"crosses"`/`"occupies"`/`"carves"`/`"touches"`/`"connects"`) instead of the `"csg "` prefix; the
  `min(csg) > max(raw)` block-order assertion stays as-is (the ORDER guarantee doesn't change, only
  how the test finds each block).
- `test_survey_every_line_starts_with_its_tier_token` (currently at `test_cli_actor_survey.py:71`,
  tests the OLD prefix behavior) — replace with a test asserting no line starts with `raw `/`csg `
  and the block order/blank-separator hold.

Also fix the stale CLI help string: `uedcli/cli/parsers/actor_survey.py`'s `add_survey_subparser`
still reads `"...what it touches, contains, carves, connects to, and crosses into"` — `contains` is
retired in favor of `occupies` by this item. Change it to:
`"every raw and CSG-resolved spatial fact about one actor (brush or not): what it touches, occupies, "
"carves, connects to, and crosses into"`.

Run `bin/test -k "format_lines or survey_every_line or survey_prints_raw"`, confirm pass, then commit:

```bash
git add uedcli/actor_survey.py uedcli/cli/parsers/actor_survey.py uedcli/tests/test_actor_survey.py \
        uedcli/tests/test_cli_actor_survey.py
git commit -m "Drop the raw/csg per-line prefix from actor survey output"
```

---

## Task 13: `--json` — DROPPED (owner ruling, 2026-09-27)

Not part of this item: no `--json` for now. Plain-text lines only (`format_lines`, Task 12). Skip this
task entirely.

---

## Task 14: cross-relation de-duplication and csg symmetric left-anchoring — verification pins

`spec.md`'s "cross-relation de-duplication" section: `crosses`/`touches` stay mutually de-duped
(unchanged, `actor_survey.py:1749`); `occupies`+`crosses` and `occupies`+`touches` are explicitly
**kept** (both fire, not de-duped) — this is already the natural behavior of Tasks 4–6's
`occupies_facts_for` (it shares no de-dup logic with `crosses_facts_for`/`touches_facts_for`), so this
task pins it rather than changing code.

Also pins the csg tier's half of the spec's directionality rule ("Symmetric relations... render with
the surveyed actor on the left"): `touches_facts_for` (`actor_survey.py:1722-1758`) and
`connects_facts_for` (`1939-1971`) already build every `CsgFact` with `src=ctx.name` — the surveyed
actor always leads — so, like Task 11's raw-tier pass, this is verification only, no code change. (The
raw tier's own left-anchoring is new code, covered by Task 9/10's own tests — this task is the csg
tier's half of the same rule.)

**Files:**
- Test: `uedcli/tests/test_actor_survey.py`

**Interfaces:**
- Consumes: `occupies_facts_for`, `crosses_facts_for`, `touches_facts_for`, `connects_facts_for`,
  `csg_facts_for`.

- [ ] **Step 1: Write the failing tests**

```python
def test_occupies_and_crosses_both_fire_for_a_point_actor_that_sits_in_a_void_and_pokes_through():
    # A point actor seated in a Subtract's void AND reaching, via its collision cylinder, past the
    # void's far wall into real solid -- both facts are true and both must be reported (spec: "both
    # kept, they say genuinely different things"). Not a brush source: `shelf_pokes_through_a_
    # niche_wall`'s Additive4/Subtract3 pair -- this test's original fixture -- IS the
    # resolved-matter crosses bug this item removes (review round 4), so post-fix it no longer
    # crosses at all (see Task 3 Steps 9-11). `room_with_a_flush_mounted_prop`'s Keypad sits well
    # inside Room's void (occupies, `_occupies_point_exists`) and its collision cylinder reaches
    # 8uu into Room's wall (crosses, already pinned by
    # `test_crosses_fires_for_a_flush_mounted_collision_extent_with_a_measured_depth`, untouched by
    # the crosses fix -- `_source_cells`' non-brush branch is unfiltered) -- an existing, unaffected
    # fixture that genuinely demonstrates both at once.
    s = survey_scenarios.room_with_a_flush_mounted_prop()
    ctx = build_context(s.level, s.index, "Keypad", s.defaults)
    facts = csg_facts_for(ctx)
    relations = {(f.src, f.dst, f.relation) for f in facts if f.src == "Keypad"}
    assert any(r[2] == "crosses" for r in relations)
    # Keypad also sits in Room's own void alongside the crossing -- both must be present:
    assert ("Keypad", "Room", "occupies") in relations


def test_occupies_and_touches_both_fire_for_an_add_flush_against_its_own_carved_walls():
    # an_add_inside_an_enclosing_subtract(clearance=0): Room 2048^3 Subtract at (0,0,0); Shelf 64^3
    # Add at (-992,0,0), x in [-1024,-960] -- pushed flush against Room's own -X wall (x=-1024), the
    # fixture's own documented contrast case ("the shelf pushed back against the wall, which IS a
    # contact, and on the Subtract's own carve boundary").
    #
    # Confirmed against the CURRENT code (`pair_touches`/`resolved_matter_of`/`_was_solid_before`,
    # run directly, not hand-waved): `pair_touches(ctx, Shelf, Room)` is already `True` today at
    # clearance=0 (`touches_facts_for` already reports `Shelf --touches--> Room`), and separately,
    # walking `ctx.csg_order` backward excluding `Shelf` from the shelf's own centroid
    # `(-992, 0, 0)` finds `Room` (a Subtract) as the last writer there -- void once Shelf is
    # excluded. So all three of `_occupies_matter_exists`'s conditions hold at that point: (i)
    # `resolved_matter_of(Shelf, p)` is `True` (nothing later carves Shelf, the last actor in trunk
    # order); (ii) `_was_solid_before(Room, p)` is `True` (the default-solid `MAP NEW` world, before
    # Room's own carve, with no earlier writer at all); (iii) `_is_void_excluding(p,
    # exclude="Shelf")` is `True` (Room is the last writer reaching `p` once Shelf is excluded) --
    # `occupies(Shelf, Room)` fires too. Both facts are genuinely true of the same pair at once.
    s = survey_scenarios.an_add_inside_an_enclosing_subtract(clearance=0)
    ctx = build_context(s.level, s.index, "Shelf", s.defaults)
    facts = csg_facts_for(ctx)
    relations = {(f.src, f.dst, f.relation) for f in facts if f.src == "Shelf"}
    assert ("Shelf", "Room", "occupies") in relations
    assert ("Shelf", "Room", "touches") in relations
```

```python
def test_touches_leads_with_the_surveyed_actor():
    # subtract_stops_flush_against_a_wall: Room (subtract) stops exactly at Wall's -X face --
    # a real touches fact, Room leading.
    s = survey_scenarios.subtract_stops_flush_against_a_wall()
    ctx = build_context(s.level, s.index, "Room", s.defaults)
    facts = touches_facts_for(ctx)
    assert facts and all(f.src == "Room" for f in facts)
    assert any(f.dst == "Wall" for f in facts)


def test_connects_leads_with_the_surveyed_actor():
    # redundant_nested_subtract: Shell(add), OuterRoom(subtract), InnerCarve(subtract) entirely
    # inside OuterRoom's already-void space -- surveying OuterRoom reports connects to InnerCarve.
    s = survey_scenarios.redundant_nested_subtract()
    ctx = build_context(s.level, s.index, "OuterRoom", s.defaults)
    facts = connects_facts_for(ctx)
    assert facts and all(f.src == "OuterRoom" for f in facts)
```

- [ ] **Step 2: Run them**

`bin/test -k "occupies_and_crosses or occupies_and_touches or leads_with_the_surveyed_actor"` — these
should already PASS with no code change (Tasks 4–6/12's `occupies_facts_for` shares no de-dup logic
with the other two; `touches_facts_for`/`connects_facts_for` already set `src=ctx.name`). If any fails,
some behavior leaked that must be fixed at its source (`occupies_facts_for` for the first two,
`touches_facts_for`/`connects_facts_for` for the last two), not patched here.

- [ ] **Step 3: Commit**

```bash
git add uedcli/tests/test_actor_survey.py
git commit -m "Pin occupies co-firing and csg symmetric-relation left-anchoring"
```

---

## Task 15: update `docs/reference/actor/survey.md`

**Depends on Task 12 being complete** — the exact example transcript can't be written correctly until
the output shape (Task 12 Step 7) has landed. Do Steps 1-4 below only after that.

**Files:**
- Modify: `docs/reference/actor/survey.md` (full rewrite of the relation table, example output, and
  the `level graph` cross-reference section)

**Interfaces:** None — documentation only, checkable against the CLI's actual behavior from Tasks
1–12, 14.

- [ ] **Step 1: Rewrite the example transcript**

Run the CLI against a real scenario (or build a small T3D level by hand) that exercises at least one
`raw encloses`, one `raw overlaps`, one `csg occupies`, and one `csg crosses` line, and replace the
existing example block (lines 14-24) with real, current output — do not hand-write output that has
not actually been produced by the built CLI.

- [ ] **Step 2: Rewrite the relation table**

Replace the "Two tiers, and the line grammar" and "The relations" sections (lines 26-74) with:

- The two-tier framing from `spec.md`'s own "The two tiers" section (raw = pure authored geometry,
  ignores CsgOper/order/Mover; csg = resolved matter, only tier that cares about CsgOper) — in this
  doc's own plain-language style, not copied verbatim from the internal spec.
- A raw-relations table: `encloses` (encloser leads), `overlaps` (symmetric), `meets` (symmetric),
  `coincides` (symmetric) — one line of meaning each, matching `spec.md`'s own table.
- A csg-relations table: `crosses` (intruder leads), `occupies` (occupant leads), `carves` (subtract
  leads), `touches` (symmetric), `connects` (symmetric) — one line of meaning each.
- Explicitly note relation names are now unique across tiers (no more `raw`/`csg` relation-name
  overlap) and that lines are bare (no `:idx`, no magnitudes, no `--json`) — metrics are `actor
  relation`'s job (`spec.md`'s "Metrics are `actor relation`'s job"). Replace the current doc's "grep
  for `^csg `" advice (line 29, pre-rewrite) — that string no longer appears once the prefix is dropped
  (Task 12 Step 7). Write the replacement advice as: grep by relation word (every relation name is
  unique to its tier, so e.g. `grep -E 'occupies|carves|connects'` still isolates csg-tier lines).

- [ ] **Step 3: Update the `level graph` cross-reference section**

The existing "`level graph` prints the carve the other way around" section (lines 76-82) described
raw `carves`, which Task 10 removes entirely from `actor survey`. Rewrite it to say `actor survey`'s
raw tier no longer has a `carves` relation at all (that reasoning moved to the csg tier's `carves`,
which still leads with the Subtract) — `level graph`'s own `carved_by` (Add leading) is unrelated to
anything `actor survey` prints in its raw tier now, and only the CSG-tier `carves` vs. `level graph`'s
`carved_by` naming difference remains worth noting.

- [ ] **Step 4: Read the whole file once more against `spec.md` and the actual CLI output**

Confirm no stale relation name (`contains`, raw `carves`, `touches(<area>)`, `crosses(<depth>)`)
remains anywhere in the file, including the "Errors" section's prose.

- [ ] **Step 5: Commit**

```bash
git add docs/reference/actor/survey.md
git commit -m "Update actor survey docs for the two-tier reshape"
```

---

## Final check

- [ ] Run the whole suite once: `bin/test`
- [ ] Read the full diff (`git diff master...HEAD` from the worktree) end to end
- [ ] Confirm every relation name in `spec.md`'s two tables appears in `actor_survey.py`'s code and in
  `docs/reference/actor/survey.md`, and that no relation name from the OLD scheme (`contains`, raw
  `carves`, `fills`) remains anywhere in `uedcli/` or `docs/`
- [ ] Confirm `grep -rn "depth_uu\|matched_pair\|area_estimate" uedcli/actor_survey.py
  uedcli/tests/test_actor_survey.py` returns nothing (the four pre-existing tests plus Task 3 Step 12's
  new one, all fixed in Task 12)
- [ ] Confirm `grep -rn "CARVE_AREA_EPS" uedcli/` returns nothing (fully replaced by `CARVE_VOLUME_EPS`)
- [ ] Confirm `grep -rn "classify_pair\|build_graph" uedcli/actor_survey.py` returns nothing — the raw
  tier must not have re-acquired a dependency on `actorgraph`'s CSG-order classifier anywhere
- [ ] Confirm `grep -rn '"\-\-json"' uedcli/cli/parsers/actor_survey.py uedcli/cli/commands/actor/survey.py`
  returns nothing — Task 13 is dropped, no `--json` flag should exist on this verb
- [ ] Confirm `grep -rn "contains" uedcli/cli/parsers/actor_survey.py` returns nothing — Task 12's help
  string fix landed
- [ ] Confirm `grep -rn "test_crosses_reports_the_reverse_direction_when_the_surveyed_actor_is_the_target\|test_crosses_fires_for_an_add_poking_through_a_niche_wall_and_names_only_the_immediate_owner" uedcli/`
  returns nothing (Task 3 Steps 10-11 renamed/deleted them) and that no test anywhere still asserts
  `Additive4 --crosses--> Subtract3` (`grep -rn "Additive4.*crosses\|crosses.*Additive4" uedcli/tests/`)
  — the fixed bug's own behavior, pinned as a fact
- [ ] Confirm `grep -rn "xfail" uedcli/tests/test_actor_survey.py` no longer matches
  `test_touches_fires_for_a_blind_pockets_carve_victim` (Task 3 Step 7) and
  `dev/docs/board/inbox/crosses-fires-on-a-subtract-s-carve-victim/` no longer exists (moved to
  `done/`, Task 3 Step 8)
- [ ] Confirm `test_crosses_fires_for_a_semisolid_partially_overlapping_an_add` (Task 3 Step 12) exists
  and passes — the suite's first genuine brush-sourced `crosses` regression
- [ ] One subagent review of the whole worktree diff, per `dev/docs/rules/building-features.md`
