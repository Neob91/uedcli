# `--labels` granularity + density-aware placement — Implementation Plan

> **For agentic workers:** implement task-by-task; each task ends green + committed. Steps use
> checkbox (`- [ ]`) syntax for tracking. TDD: failing test first, minimal code, green, commit.

**Goal:** Replace the `actor preview` renderer's single `--labels {none,all,highlighted}` switch with
a composable colon-filter grammar, add brush-name labels, and place all labels by geometry-aware cost
minimization so it is visually clear which label belongs to what.

**Architecture:** A pure `parse_label_spec` builds a frozen `LabelSpec` (per-kind sets of element
*categories* that get a label). The renderer asks `spec.draws_poly(...)` / `spec.draws_name(...)` per
element. All three label kinds (poly indices, brush names, point names) route through one
`_place_labels` pass that minimizes a normalized cost over a coarse geometry `DensityGrid`.

**Tech stack:** Python 3.12, stdlib-only renderer (`uedcli/preview.py`), `Pillow` only for PPM→PNG.
Tests via `bin/test` (host-native pytest in the dev venv).

**Spec:** board item `true-occlusion-label-filter`.
**Decision:** `dev/docs/decisions.md` 2026-07-22 09:54 UTC.

**Build split:** Tasks 1–3 = Part A (grammar + kinds), one commit each. Tasks 4–5 = Part B
(placement). Post-build two-cold-reviewer gate after Part A and again after Part B (per dx_lum
`CLAUDE.md`).

**Conventions reminder:** commit only touched files by explicit pathspec (never `git add .`/`-a`); no
AI attribution; every flag has a real `help=`; no Python exception reaches the CLI user (errors name
the offending value); update `docs/usage.md` + `architecture.md` in the same change.

---

## File structure

- **`uedcli/preview.py`** — `LabelSpec`/`PolyLabels`… → the category-set `LabelSpec` + `parse_label_spec`
  + `DensityGrid`; `_place_labels` reworked; `render_brush_pgm`/`render_brushes_pgm`/`render_quad_pgm`
  take a `LabelSpec`; `_draw_point_overlay` stops drawing name text.
- **`uedcli/cli.py:136`** — `--labels` becomes a free `str`, default `"poly:vis,poly:hi,name"`, new help.
- **`uedcli/dispatch.py:504,509`** — parse `args.labels` via `LabelSpec.parse`, clean error on failure.
- **`uedcli/tests/test_preview.py`** — parser table, render-honors-spec, placement tests; convert ~17
  `labels=` string call sites to `LabelSpec` constructors.
- **`uedcli/tests/test_cli.py`, `test_actor_preview.py`** — flag default + end-to-end error tests.
- **`docs/usage.md`, `dev/docs/architecture.md`** — grammar + placement docs.

---

## Task 1: `LabelSpec` + `parse_label_spec` (pure grammar)

**Files:**
- Modify: `uedcli/preview.py` (add near the top-level dataclasses)
- Test: `uedcli/tests/test_preview.py`

- [ ] **Step 1: Write the failing parser tests.** Add to `test_preview.py` (import `LabelSpec`,
  `parse_label_spec`). Categories: poly `(is_front, is_highlighted)`, name `(is_brush, is_highlighted)`.

```python
FULL_POLY = frozenset({(False, False), (False, True), (True, False), (True, True)})
FULL_NAME = frozenset({(False, False), (False, True), (True, False), (True, True)})

def test_it_parses_bare_kinds_as_everything():
    s = parse_label_spec("poly,name")
    assert s.poly == FULL_POLY
    assert s.name == FULL_NAME

def test_it_narrows_poly_with_vis_and_hi_filters():
    assert parse_label_spec("poly:vis").poly == frozenset({(True, False), (True, True)})
    assert parse_label_spec("poly:hi").poly == frozenset({(True, True), (False, True)})
    assert parse_label_spec("poly:vis:hi").poly == frozenset({(True, True)})

def test_it_unions_comma_selectors():
    # default poly part: front OR highlighted
    assert parse_label_spec("poly:vis,poly:hi").poly == frozenset(
        {(True, False), (True, True), (False, True)})

def test_it_narrows_names_by_subkind_and_hi():
    assert parse_label_spec("name:brush").name == frozenset({(True, False), (True, True)})
    assert parse_label_spec("name:point").name == frozenset({(False, False), (False, True)})
    assert parse_label_spec("name:hi").name == frozenset({(True, True), (False, True)})
    assert parse_label_spec("name:brush:hi").name == frozenset({(True, True)})

def test_it_treats_filters_as_an_order_independent_set():
    assert parse_label_spec("name:hi:brush") == parse_label_spec("name:brush:hi")

def test_it_accepts_highlighted_as_a_synonym_for_hi():
    assert parse_label_spec("poly:highlighted") == parse_label_spec("poly:hi")

def test_it_normalizes_case_and_whitespace():
    assert parse_label_spec("poly, NAME") == parse_label_spec("poly,name")

def test_it_expands_the_whole_value_keywords():
    assert parse_label_spec("all") == LabelSpec(poly=FULL_POLY, name=FULL_NAME)
    assert parse_label_spec("none") == LabelSpec(poly=frozenset(), name=frozenset())
    assert parse_label_spec("highlighted") == parse_label_spec("poly:hi,name:hi")

def test_it_maps_the_default_value_to_todays_poly_behavior():
    s = parse_label_spec("poly:vis,poly:hi,name")
    assert s.poly == frozenset({(True, False), (True, True), (False, True)})  # front OR hi
    assert s.name == FULL_NAME

def test_it_treats_zero_effective_tokens_as_none():
    for text in ("", ",", "  ", "poly,,"):
        assert parse_label_spec(text) == LabelSpec(poly=frozenset(), name=frozenset()) or \
            parse_label_spec("poly,,").poly == FULL_POLY  # 'poly,,' keeps poly; '' → none

import pytest

@pytest.mark.parametrize("text,bad", [
    ("foo", "foo"), ("poly:brush", "brush"), ("name:vis", "vis"), ("poly:xyz", "xyz"),
    ("name:brush:point", "point"), ("all,poly", "all"), ("none,name", "none"),
])
def test_it_rejects_invalid_tokens_naming_the_offender(text, bad):
    with pytest.raises(ValueError) as e:
        parse_label_spec(text)
    assert bad in str(e.value)
```

  (Fix the `zero-token` test to two clean asserts: `""`/`","`/`"  "` → empty spec; `"poly,,"` →
  `FULL_POLY`. The inline `or` above is a placeholder — split it when writing.)

- [ ] **Step 2: Run, verify failure.** `bin/test -k label_spec -x` → FAIL (name not defined).

- [ ] **Step 3: Implement.** Add to `preview.py`:

```python
@dataclass(frozen=True, kw_only=True)
class LabelSpec:
    poly: frozenset[tuple[bool, bool]]   # (is_front, is_highlighted)
    name: frozenset[tuple[bool, bool]]   # (is_brush, is_highlighted)

    def draws_poly(self, *, is_front: bool, is_highlighted: bool) -> bool:
        return (is_front, is_highlighted) in self.poly

    def draws_name(self, *, is_brush: bool, is_highlighted: bool) -> bool:
        return (is_brush, is_highlighted) in self.name

    @classmethod
    def parse(cls, text: str) -> "LabelSpec":
        return parse_label_spec(text)

    @classmethod
    def all(cls) -> "LabelSpec":
        return parse_label_spec("all")

    @classmethod
    def none(cls) -> "LabelSpec":
        return parse_label_spec("none")

    @classmethod
    def default(cls) -> "LabelSpec":
        return parse_label_spec("poly:vis,poly:hi,name")

    @classmethod
    def highlighted(cls) -> "LabelSpec":
        return parse_label_spec("highlighted")


_ALL_POLY = frozenset((f, h) for f in (False, True) for h in (False, True))
_ALL_NAME = frozenset((b, h) for b in (False, True) for h in (False, True))
_POLY_FILTERS = {"vis", "hi", "highlighted"}
_NAME_FILTERS = {"brush", "point", "hi", "highlighted"}
_KEYWORDS = {"all", "none", "highlighted"}


def parse_label_spec(text: str) -> "LabelSpec":
    tokens = [t.strip().lower() for t in text.split(",")]
    tokens = [t for t in tokens if t]
    if not tokens:
        return LabelSpec(poly=frozenset(), name=frozenset())
    if any(t in _KEYWORDS for t in tokens):
        if len(tokens) != 1:
            bad = next(t for t in tokens if t in _KEYWORDS)
            raise ValueError(f"--labels: {bad!r} is a whole-value keyword and cannot be combined")
        kw = tokens[0]
        if kw == "all":
            return LabelSpec(poly=_ALL_POLY, name=_ALL_NAME)
        if kw == "none":
            return LabelSpec(poly=frozenset(), name=frozenset())
        return _union([_selector("poly:hi"), _selector("name:hi")])  # highlighted
    return _union([_selector(t) for t in tokens])


def _selector(token: str):
    kind, *filters = token.split(":")
    if kind == "poly":
        cats, axis_hi = set(_ALL_POLY), 1
        for f in filters:
            if f not in _POLY_FILTERS:
                raise ValueError(f"--labels: unknown filter {f!r} for kind 'poly' (in {token!r})")
            if f == "vis":
                cats = {c for c in cats if c[0]}           # is_front
            else:                                          # hi / highlighted
                cats = {c for c in cats if c[1]}
        return (frozenset(cats), frozenset())
    if kind == "name":
        cats = set(_ALL_NAME)
        seen_sub = None
        for f in filters:
            if f not in _NAME_FILTERS:
                raise ValueError(f"--labels: unknown filter {f!r} for kind 'name' (in {token!r})")
            if f in ("brush", "point"):
                if seen_sub and seen_sub != f:
                    raise ValueError(f"--labels: {token!r} names both 'brush' and 'point'")
                seen_sub = f
                cats = {c for c in cats if c[0] == (f == "brush")}   # is_brush
            else:
                cats = {c for c in cats if c[1]}
        return (frozenset(), frozenset(cats))
    raise ValueError(f"--labels: unknown kind {kind!r} (in {token!r})")


def _union(parts):
    poly = frozenset().union(*(p[0] for p in parts))
    name = frozenset().union(*(p[1] for p in parts))
    return LabelSpec(poly=poly, name=name)
```

- [ ] **Step 4: Run, verify pass.** `bin/test -k label_spec` → all green.

- [ ] **Step 5: Commit.**

```bash
git commit -m "Add LabelSpec + parse_label_spec for granular --labels grammar" \
  -- uedcli/preview.py uedcli/tests/test_preview.py
git push origin uedcli-impl
```

---

## Task 2: Thread `LabelSpec` through the render + CLI + dispatch (behavior-preserving)

The default must reproduce today's output exactly (poly labels on `front OR hi` faces + point names).
Brush names are NOT added yet (Task 3).

**Files:**
- Modify: `uedcli/preview.py` (`render_brush_pgm:395`, `render_brushes_pgm:406`, `render_quad_pgm:636`,
  `want_label:473`, `show_lbl:513`); `uedcli/cli.py:136`; `uedcli/dispatch.py:504,509`
- Test: `uedcli/tests/test_preview.py`, `test_cli.py`, `test_actor_preview.py`

- [ ] **Step 1: Convert the ~17 string call sites + 3 signatures.** Change the `labels:
  Literal["none","all","highlighted"]` params to `labels: LabelSpec` on the three render functions.
  Replace the two decision sites:
  - `want_label` (`:473`): `want_label = labels.draws_poly(is_front=front, is_highlighted=is_hi)`.
    Anchor filter `if (f or hi)` at `:519` stays (it is a *drawing* declutter, independent of the
    spec) — but now a face is only in `poly_labels` when `want_label`, so a back face with
    `draws_poly` True (e.g. `--labels poly`) must still anchor. **Change `:519`** to include any
    labeled poly: `anchors = [(to_px(c), t, hi) for f, c, t, hi in poly_labels]` (drop the `if
    (f or hi)` — membership already reflects the spec).
  - `show_lbl` (`:513`): `show_lbl = labels.draws_name(is_brush=False, is_highlighted=actor.name in
    highlight_points)`.
  - In `test_preview.py`, replace every `labels="all"` → `labels=LabelSpec.all()`, `labels="none"` →
    `labels=LabelSpec.none()` (lines 50, 56, 57, 66, 67, 77, 89, 90, 153, 154, 156, 175, 184, 201,
    202, 224, 250). The 3 `_place_labels` tests (106/116/125) don't use `labels=` — leave.

- [ ] **Step 2: CLI + dispatch.** `cli.py:136` → free `str`, default `"poly:vis,poly:hi,name"`, new
  help (below). `dispatch.py:504/509` parse before render:

```python
try:
    label_spec = LabelSpec.parse(args.labels)
except ValueError as exc:
    raise _SelectionExit(str(exc))       # same clean-exit path as the other preview selectors
...
data = preview.render_..._pgm(actors, ..., labels=label_spec, ...)
```

  `cli.py` help:
```python
pp.add_argument("--labels", default="poly:vis,poly:hi,name",
                help="which labels to draw: a comma-set of selectors (union). A bare kind = ALL of "
                     "it; filters narrow; commas union. Kinds: poly (face indices), name (actor "
                     "names). poly filters: vis (front-facing), hi (highlighted). name filters: "
                     "brush, point, hi. e.g. 'name:brush' (brush names only), 'poly:vis' "
                     "(front-facing indices), 'poly:vis,poly:hi' (front OR highlighted). Keywords: "
                     "none, all (=poly,name), highlighted (=poly:hi,name:hi). Default: front-facing "
                     "or highlighted indices + all names")
```

- [ ] **Step 3: Add the default-behavior + error tests.**

```python
def test_it_defaults_to_todays_poly_and_name_labeling():
    # front-facing index present, back-only-unhighlighted index absent, point name present
    ...  # assert via _nonbg pixel presence on a known scene (reuse an existing fixture scene)

def test_it_rejects_a_bad_labels_value_with_a_clean_error(capsys):
    # actor preview --labels poly:bogus  → exit != 0, stderr names 'bogus', NO 'Traceback'
    ...
```

  For `test_cli.py:174-184`: `ns.labels` is still a string (default now `"poly:vis,poly:hi,name"`) —
  update the asserted default value; the round-trip still holds.

- [ ] **Step 4: Run the suite.** `bin/test -k "preview or cli or actor_preview"` → green. Then full
  `bin/test` (expect only the 2 pre-existing `utexture_decode` failures).

- [ ] **Step 5: Docs + commit.** Update `docs/usage.md` `--labels` section to the new grammar (see
  Task 5 for the full doc block — do the grammar half now). Commit:

```bash
git commit -m "Thread LabelSpec through preview render + --labels grammar" \
  -- uedcli/preview.py uedcli/cli.py uedcli/dispatch.py \
     uedcli/tests/test_preview.py uedcli/tests/test_cli.py uedcli/tests/test_actor_preview.py \
     docs/usage.md
git push origin uedcli-impl
```

---

## Task 3: Brush-name labels + unified label pass (greedy placement)

Add the new brush-name kind, and route ALL three label kinds through one `_place_labels` pass (point
names leave `_draw_point_overlay`). Placement stays greedy (Task 4 adds density). Anchor snap +
highlighted-brush logic land here.

**Files:**
- Modify: `uedcli/preview.py` (`render_brushes_pgm` label collection + the `_place_labels` call;
  `_draw_point_overlay:574-584`; `_place_labels:340` to carry per-item scale + metadata)
- Test: `uedcli/tests/test_preview.py`

- [ ] **Step 1: Extend `_place_labels` to carry per-item scale + metadata.** New anchor tuple
  `((ax, ay), text, scale, meta)`; returns `((ax, ay), (lx, ly), text, scale, meta)`. `meta` is an
  opaque passthrough (color + kind). Ring `step` keys off a passed `base_scale`. Update the 3 direct
  tests (106/116/125) to the new shape (they can pass a single scale + `meta=None`).

- [ ] **Step 2: Write brush-name tests.**

```python
def test_it_labels_brush_names_when_name_kind_shown():
    # a single named brush, --labels name:brush → the brush's NAME pixels present, no poly indices
    ...

def test_it_marks_a_brush_highlighted_when_any_poly_is_highlighted():
    # --highlight Brush:2 + --labels name:brush:hi → brush name drawn (>=1 poly highlighted)
    ...

def test_it_anchors_a_hollow_brushs_name_on_its_wireframe_not_the_hollow():
    # subtract cube; assert the name-anchor dot pixel coincides with a projected edge, not the centroid void
    ...
```

- [ ] **Step 3: Implement.** In `render_brushes_pgm`, per brush accumulate its projected verts;
  compute `brush_hi = any((actor.name, idx) in highlight_polys ...)`; if
  `labels.draws_name(is_brush=True, is_highlighted=brush_hi)`, compute the vertex centroid then
  **snap** to the nearest projected point on the brush's own edges; append a name anchor (scale
  `size//256`, meta = MARKER grey or the brush's vivid CSG hue when `brush_hi`). Move the point-name
  text out of `_draw_point_overlay` into a name anchor (same scale/color as today). Feed poly-index
  anchors (scale `size//128`) + all name anchors into ONE `_place_labels` call; draw each with its
  own scale + meta color.

- [ ] **Step 4: Run.** `bin/test -k preview` → green.

- [ ] **Step 5: Commit + Part-A review gate.**

```bash
git commit -m "Add brush-name labels; unify all label kinds into one placement pass" \
  -- uedcli/preview.py uedcli/tests/test_preview.py
git push origin uedcli-impl
```

  **STOP for the post-Part-A build review** — at the headcount `CLAUDE.md` **Review gates** specifies
  (not restated here, so it cannot go stale): over the Task 1–3 diff (grammar correctness + render
  behavior). Fold findings before Part B.

---

## Task 4: `DensityGrid` + cost-minimizing placement (Part B)

**Files:**
- Modify: `uedcli/preview.py` (`DensityGrid` type; `render_brushes_pgm` builds + populates it;
  `_place_labels` cost function + deterministic order)
- Test: `uedcli/tests/test_preview.py`

- [ ] **Step 1: `DensityGrid` unit tests.**

```python
def test_density_grid_counts_segment_and_box_hits():
    g = DensityGrid(cells=[0]*16, n_cols=4, n_rows=4, cell_px=8)  # 32x32 px
    g.add_segment((0, 0), (31, 0))         # top row of cells
    assert g.avg_density_in_box((0, 0, 31, 7)) > 0
    assert g.avg_density_in_box((0, 24, 31, 31)) == 0.0
```

- [ ] **Step 2: Placement-cost tests.**

```python
def test_it_moves_a_label_out_of_a_dense_region():
    # build a grid with a hot cell at the anchor; assert chosen box avg_density < anchor cell density
    ...

def test_placement_is_deterministic():
    # same anchors+grid twice → identical output
    ...
```

- [ ] **Step 3: Implement `DensityGrid`** (`cells`/`n_cols`/`n_rows`/`cell_px`, `add_segment` via a
  cheap DDA step, `add_box`, `avg_density_in_box` = mean count over covered cells). In
  `render_brushes_pgm`, after computing edges + point/overlay footprints and before placing labels,
  build the grid and populate it (edges + markers + sprite/overlay boxes; **NOT** labels). Pass it +
  weights into `_place_labels`.

- [ ] **Step 4: Rework `_place_labels` to cost-minimize.** For each anchor (processed in the
  deterministic order — descending anchor grid-density, tie-break actor-name then poly-index), score
  every ring candidate `cost = k1*grid.avg_density_in_box(box) + k2*label_overlap_count +
  k3*(leader_px/cell_px)`; pick the min; record its box in `placed` (for `k2`); keep frame clamping +
  leader/dot. Seed `k1=?, k2=?, k3=?` (tuned in Task 5) — start `k1=1.0, k2=50.0, k3=3.0`.

- [ ] **Step 5: Run.** `bin/test -k "preview or place or density"` → green.

- [ ] **Step 6: Commit.**

```bash
git commit -m "Place labels by cost minimization over a geometry DensityGrid" \
  -- uedcli/preview.py uedcli/tests/test_preview.py
git push origin uedcli-impl
```

---

## Task 5: Tune, re-render showcase, docs

**Files:**
- Modify: `uedcli/preview.py` (final `k1/k2/k3` + `cell_px` constants + a comment); `docs/usage.md`;
  `dev/docs/architecture.md`
- Scratch: `_scratch/gen_showcase.py` (re-run only)

- [ ] **Step 1: Tune weights against the showcase.** Run `.venv/bin/python _scratch/gen_showcase.py`
  at a few `(k1,k2,k3,cell_px)` settings; eyeball 3–4 tiles (pillar hall, arena, doorway) for: labels
  out of overlap knots, hugging anchors otherwise, no stacking. Lock the constants + a one-line
  rationale comment. (`k3` high = hug; `k2` high = never stack.)

- [ ] **Step 2: Finalize `docs/usage.md`.** Full `--labels` grammar block: bare-kind-is-all, filters
  narrow, commas union, the selector table, keywords, default, the new brush-name note, the
  placement one-liner. Do NOT document `poly:vis` as occlusion (it's front-facing) and do NOT mention
  the deferred occlusion filter.

- [ ] **Step 3: Update `dev/docs/architecture.md`.** The `LabelSpec` category-set model +
  `parse_label_spec`; the `DensityGrid` cost-minimizing placement; the unified label pass (point
  names no longer in `_draw_point_overlay`); brush-name anchor snap.

- [ ] **Step 4: Board.** Move the spec item to `board/done/` tail; keep the optional true-occlusion
  `[implement] p3` in `board/inbox/`.

- [ ] **Step 5: Commit + Part-B review gate.**

```bash
git commit -m "Tune label placement weights; document --labels grammar + placement" \
  -- uedcli/preview.py docs/usage.md dev/docs/architecture.md dev/docs/board/done/
git push origin uedcli-impl
```

  **STOP for the post-Part-B build review** (headcount per `CLAUDE.md` **Review gates**). Fold findings. Then re-render + send the 50
  showcase tiles individually (per the standing showcase workflow), spot-checking a `name:brush`, a
  `poly:vis`, and a crowded pillar-hall tile.

---

## Self-review (done at plan-write time)

- **Spec coverage:** A1 grammar → Task 1; A2 `LabelSpec` → Task 1; A3 parse-location → Task 2; A4
  `vis`=front-facing (no reject) → Task 1 (`vis` filter narrows on `is_front`); A5 errors → Task 1;
  B1/B2 grid+cost → Task 4; B3 unify + anchor snap + highlighted-brush → Task 3; B4 ripple → Task 2+3;
  Testing → each task; Docs → Task 2 (grammar half) + Task 5. No spec section unmapped.
- **Placeholder scan:** the Task-1 zero-token test has an inline `or` flagged to split when writing;
  weight seeds in Task 4 are explicit starting values, finalized in Task 5. No other TBDs.
- **Type consistency:** `LabelSpec.poly`/`.name` frozensets, `draws_poly(is_front=,is_highlighted=)`
  / `draws_name(is_brush=,is_highlighted=)`, `parse_label_spec`, `DensityGrid.avg_density_in_box` —
  used identically across Tasks 1–5.
