# Spec: granular `--labels` selection + density-aware label placement

**Status:** ephemeral design scratch. Durable record → `docs/usage.md` + `architecture.md`;
load-bearing choices → `decisions.md` (2026-07-22 09:54 UTC). Goes stale once built.

**Board:** raised by Andrzej 2026-07-22 (mid-`actor preview` polish). Two coupled parts in ONE spec
(same code: `preview.py` label pipeline + `cli.py`/`dispatch.py` wiring). Buildable in two commits
(A = grammar+kinds, B = placement) but reviewed together.

**Confirmed by Andrzej 2026-07-22:**
- Grammar = **one comma-set**, colon filters, fully composable **union**. A **bare kind means ALL of
  that kind**; each filter **narrows** it; multiple filters on one selector **intersect**; commas
  **union** the pieces (`poly:vis,poly:hi` = visible OR highlighted; `name:brush:hi,name:point` =
  highlighted-brush-names ∪ all-point-names).
- `vis` = **front-facing** (the cheap backface cull the renderer already computes) — ships now, NOT
  true occlusion. (True occlusion is an optional future refinement, decoupled from this grammar.)
- **Default** (flag omitted) = `poly:vis,poly:hi,name` — front-facing + highlighted face indices +
  all names. Reproduces today's poly labeling exactly, plus the new brush names.
- Placement = **density-grid cost minimization**, **moderate drift cap** (leader length weighted
  high so labels hug their anchor, drifting only when the local area is genuinely crowded).

**Revised 2026-07-22** — reworked to the orthogonal "bare kind = ALL, filters narrow, commas union"
model (Andrzej); `vis` = front-facing and ships (no parse-reject); default is the ordinary value
`poly:vis,poly:hi,name`. Earlier two-cold-reviewer findings still folded: brush-name anchor snaps to
the nearest projected edge (B2); cost terms normalized + labels kept out of the density grid; full
signature-ripple enumerated; `highlighted-brush` defined; `highlighted`-alias honesty; deterministic
placement order; grid as a concrete type.

---

## Part A — granular `--labels` grammar

### A1. The model

`--labels` takes a **comma-separated set of selectors**; the labels drawn are the **union** of all
selectors. Each selector is `KIND[:FILTER[:FILTER…]]`. Tokens are **normalized** — each is
whitespace-stripped and lower-cased before matching (`poly, Name` == `poly,name`).

- **A bare kind means EVERYTHING of that kind.** `poly` = every brush face (front AND back);
  `name` = every actor name (brush AND point).
- **Filters NARROW.** Each filter drops part of the set; **multiple filters on one selector
  intersect** (AND); they are an **order-independent set** (`name:brush:hi` ≡ `name:hi:brush`).
- **Commas UNION.** `poly:vis,poly:hi` = front-facing OR highlighted faces.

**Kinds & filters:**

| Kind   | Filters | Meaning |
|--------|---------|---|
| `poly` | `vis`   | face is **front-facing** (normal toward the camera — the backface cull already computed) |
| `poly` | `hi`    | face is **highlighted** (in `highlight_polys`) |
| `name` | `brush` | name belongs to a **brush** actor |
| `name` | `point` | name belongs to a **point** actor |
| `name` | `hi`    | actor is **highlighted** |

`highlighted` is accepted as a synonym for the `hi` filter (matches the `highlighted` keyword, keeps
it guessable).

**Worked examples:**

| Value                     | Draws |
|---------------------------|---|
| `poly`                    | face indices on EVERY face (front + back) |
| `poly:vis`                | indices on front-facing faces only |
| `poly:hi`                 | indices on highlighted faces only |
| `poly:vis:hi`             | indices on faces that are front-facing AND highlighted |
| `poly:vis,poly:hi`        | front-facing OR highlighted (**this is the default's poly part**) |
| `name`                    | all names (brush + point). ≡ `name:brush,name:point` |
| `name:brush`              | brush names only |
| `name:point`              | point-actor names only |
| `name:hi`                 | highlighted actors' names (brush + point) |
| `name:brush:hi`           | highlighted brush names only |
| `name:brush:hi,name:point`| highlighted brush names ∪ all point names |

**Whole-value keywords** (stand alone — an error if combined with any other token):
- `none` = nothing.
- `all` = `poly,name` (EVERY face + EVERY name — the maximal set; note back-facing indices pile onto
  front ones in projection, so `all` is deliberately busier than the default).
- `highlighted` = `poly:hi,name:hi` — convenience alias (highlighted faces + highlighted names).

**Default** (flag omitted): the ordinary value **`poly:vis,poly:hi,name`** — front-facing OR
highlighted face indices, plus all names. The `cli.py` default is literally that string, parsed like
any other (no special default path).

**New-capability note (honesty):** brush-name labels do not exist today (only point actors get name
labels). So any value whose `name` part covers brushes now draws brush names — including the default
(`name` = all names) and `highlighted` (`name:hi` → highlighted brush names). Poly-index and
point-name behavior under the default is unchanged; the brush names are the new surface. Called out in
`usage.md`.

**Empty / zero-token input:** after skipping empty tokens (`poly,,name` → `poly,name`; `--labels ""`,
`","`, `"  "` → zero tokens), **zero effective tokens ⇒ `none`**.

### A2. `LabelSpec` model (union of filtered category sets)

Because a bare kind is the full set, a filter is an intersection, and commas union, the natural
representation is: for each kind, the **set of element categories that get a label**. Two boolean
attributes per element give four categories per kind; a selector picks a subset, and the spec is the
union across selectors. This makes union/intersection plain set algebra (no fold-order subtlety) and
trivially assertable.

```python
@dataclass(frozen=True, kw_only=True)
class LabelSpec:
    # selected poly-face categories, each (is_front, is_highlighted)
    poly: frozenset[tuple[bool, bool]]
    # selected name categories, each (is_brush, is_highlighted)
    name: frozenset[tuple[bool, bool]]

    def draws_poly(self, *, is_front: bool, is_highlighted: bool) -> bool:
        return (is_front, is_highlighted) in self.poly

    def draws_name(self, *, is_brush: bool, is_highlighted: bool) -> bool:
        return (is_brush, is_highlighted) in self.name

    @classmethod
    def parse(cls, text: str) -> "LabelSpec": ...   # wraps parse_label_spec
    @classmethod
    def default(cls) -> "LabelSpec": ...            # parse("poly:vis,poly:hi,name")
    @classmethod
    def all(cls) -> "LabelSpec": ...
    @classmethod
    def none(cls) -> "LabelSpec": ...
    @classmethod
    def highlighted(cls) -> "LabelSpec": ...
```

**Parsing (`parse_label_spec(text) -> LabelSpec`):** for each selector, start from the kind's four
categories and intersect per filter:
- `poly`: full = `{(F,F),(F,T),(T,F),(T,T)}` over `(is_front, is_highlighted)`; `vis` keeps
  `is_front`; `hi` keeps `is_highlighted`.
- `name`: full = the four `(is_brush, is_highlighted)`; `brush` keeps `is_brush`; `point` keeps
  `not is_brush`; `hi` keeps `is_highlighted`.

Union the per-selector sets into `poly`/`name`. So `all` = both full; `none` = both empty;
`highlighted` = poly `{(*,T)}` ∪ name `{(*,T)}`; default `poly:vis,poly:hi,name` = poly
`{(T,*)} ∪ {(*,T)}` = `{(T,F),(T,T),(F,T)}` (everything except back-and-unhighlighted — exactly
today's `front or is_hi`), name = full.

### A3. Where parsing lives

- **`parse_label_spec`** lives in `preview.py` (the label domain), raising a clear `ValueError` naming
  the offending token.
- **`cli.py:136` `--labels`** drops `choices=`, becomes a free `str` with default
  `"poly:vis,poly:hi,name"`; help lists the model + examples.
- **Parse in DISPATCH** (mirrors actor-preview/ergonomics "validate selectors in dispatch"): the two
  preview callers (`dispatch.py:504`, `:509`) call `LabelSpec.parse(args.labels)` and convert the
  `ValueError` into the existing clean preview-error path (no traceback, exit non-zero). `args.labels`
  stays a plain string in the namespace (verified: `test_cli.py:174-184` asserts `ns.labels` is a
  string — still passes).
- **Render functions take a `LabelSpec`** — see B4 for the full call-site ripple.

### A4. `vis` = front-facing; true occlusion is a separate future filter

`vis` selects **front-facing** faces — `_is_front(...)` (the `front` boolean already computed per face
in `render_brushes_pgm`). This is the honest meaning of "visible" in a wireframe (you can see through
everything anyway) and needs no new machinery. **Nothing is deferred or rejected at parse.**

*True occlusion* (don't label a face whose centroid is hidden behind other geometry) is a **possible
future refinement** — either tightening `vis` or a new filter — needing a z-buffer/painter pass. It is
NOT part of this spec and NOT a blocker. Tracked as an optional `[implement] p3` on `board/inbox/`.

### A5. Error cases (all → clean named error, no traceback, exit non-zero)

- Unknown kind (`foo`); unknown filter for a kind (`poly:brush`, `name:vis`, `poly:xyz`).
- `brush` and `point` on one `name` selector (contradiction — the intersection is empty; that's just
  `name`, so it's a user error, not silently all-names).
- `all` / `none` / `highlighted` combined with any other token.

`parse_label_spec` raises `ValueError` naming the token; dispatch renders it as a clean exit.

## Part B — density-aware label placement

**Goal (Andrzej):** make it visually unambiguous which label belongs to what — put labels OUTSIDE
areas where multiple polys overlap and away from nearby actors, leaning on a leader line + anchor dot
for association.

### B1. Today's placement + its gap

`_place_labels` (`preview.py:340`, signature `(anchors, scale, size)`) anchors each label at its
face/actor centroid, then a greedy ring search picks the **first** offset whose box doesn't collide
with **already-placed label boxes**; a leader + dot tie it back. It is **blind to the wireframe
underneath** — a `2` lands happily in a four-face overlap knot or on top of a pathnode marker.

### B2. Occupancy grid + cost minimization

Build one coarse **occupancy grid** — a concrete, test-constructible type:

```python
@dataclass(frozen=True, kw_only=True)
class DensityGrid:
    cells: list[int]      # row-major counts, len == n_cols * n_rows
    n_cols: int
    n_rows: int
    cell_px: int          # CELL, ≈ 8
    def add_segment(self, p0, p1) -> None: ...       # rasterize an edge into cells (mutable build)
    def add_box(self, rect) -> None: ...             # markers / sprite / overlay footprints
    def avg_density_in_box(self, rect) -> float: ... # MEAN count per covered cell
```

Populated BEFORE label placement from everything destined for the canvas: wireframe edges (front +
back — where "overlaps multiple polys" shows up as high counts), point-actor markers, sprite
footprints, range/collision overlays (where "other actors nearby" shows up). **Labels are NOT stamped
into this grid** — label-vs-label avoidance is owned solely by the `k2` term below, so the grid stays
pure *geometry* density and is never double-counted.

`_place_labels` scores every candidate ring position and picks the **minimum cost**, all three terms
normalized to comparable ranges so "k3 high / k1 moderate" is tunable (raw grid-counts vs box-counts
vs pixels otherwise differ ~100× and the weights fight the units):

```
cost = k1 * grid.avg_density_in_box(box)     # MEAN geometry count per covered cell (not a raw sum,
                                             #   so it doesn't scale with box area / label scale)
     + k2 * label_overlap_count             # placed boxes this candidate still intersects (near-hard)
     + k3 * (leader_px / cell_px)            # leader length in CELLS, not raw px
```

`k2` high enough that labels effectively never stack (today's no-overlap guarantee); `k3` high per the
**moderate drift cap** (labels hug their anchor, drifting only when forced); `k1` moderate (flee
geometry when cheap). Candidate clamped inside the frame; returned `anchor` stays the true unclamped
centroid so the leader points at the real spot. **`k1/k2/k3` + `cell_px` tuned at build against the
50-scene showcase**; record the final constants in a comment. Keep today's ring radii (densify only if
tuning shows a need).

**Deterministic order:** place labels in a fixed order — **descending anchor grid-density** (crowded
anchors first, while clear space is plentiful), tie-broken by a **stable key** (actor name, then poly
index) — so results are reproducible and goldens stable.

### B3. Unify all label kinds into ONE placement pass

Point-actor names are drawn today WITHOUT de-collision, directly in `_draw_point_overlay`
(`preview.py:574-584`). Route **all three label kinds** (poly indices, brush names, point names)
through the single `_place_labels` pass:

- `_place_labels` takes anchors that each carry their **own scale + metadata** (color, kind), since
  poly indices (`size//128`) and names (`size//256`) differ in size; returns positions + passthrough
  metadata. Ring step keys off a base scale.
- `_draw_point_overlay` keeps drawing the marker/sprite/brackets but **no longer draws the name text**
  — the name joins the unified list. This **moves existing point-name positions**; point-name goldens
  regenerate (B4/Testing).
- Brush names render at point-name styling (scale `size//256`, MARKER grey knockout box + text; the
  brush's **vivid CSG hue** when the brush is highlighted).
- **`highlighted brush` defined** (no brush-level highlight set exists today): a brush is highlighted
  **iff any of its polys is in `highlight_polys`** — which `_resolve_highlights` already populates
  (`--highlight Name` puts all polys in; `--highlight Name:2` puts one in; either counts). Used for
  `draws_name(is_brush=True, is_highlighted=…)`.
- **Brush-name anchor snaps to visible geometry.** The naive 2-D vertex centroid of a concave/hollow
  brush (subtract room, L-shape, ring) falls in the hollow or outside the hull — a low-density void
  the cost minimizer would then *keep* the label in, leader pointing at nothing. So the anchor is the
  **nearest projected point on that brush's own wireframe** (nearest edge/vertex to the centroid) —
  the dot always lands ON the brush. Add a concave-brush placement test.

### B4. Signature ripple (full enumeration)

Replacing the render `labels` param from `Literal[str]` to `LabelSpec` touches, and the plan must
convert, all of:

- **Label-decision sites in `render_brushes_pgm`:** `want_label` (`preview.py:473`, `front or is_hi`)
  → `spec.draws_poly(is_front=front, is_highlighted=is_hi)`; the point-name `show_lbl`
  (`preview.py:513`) → `spec.draws_name(is_brush=False, is_highlighted=…)`; new brush-name gating →
  `spec.draws_name(is_brush=True, is_highlighted=brush_hi)`.
- **The `labels:` params on all three entry points:** `render_brush_pgm` (`:395`), `render_brushes_pgm`
  (`:406`), `render_quad_pgm` (`:636`) → `LabelSpec`. `render_quad_pgm` renders each sub-view via
  `render_brushes_pgm` (`:648`), so each pane builds its own `DensityGrid` — placement follows for
  free.
- **`_place_labels`** (`:340`): new anchors-carry-scale+metadata shape + the `DensityGrid` + weights;
  update its 3 direct unit tests (`test_preview.py:106/116/125`).
- **~17 string call sites in `test_preview.py`** (`labels="all"/"none"` at lines 50, 56, 57, 66, 67,
  77, 89, 90, 153, 154, 156, 175, 184, 201, 202, 224, 250) and **the 2 dispatch callers**
  (`dispatch.py:504, 509`). The `LabelSpec.all()/.none()/.default()/.highlighted()/.parse()`
  constructors keep these mechanical.
- **Point-overlay label tests** and any **point-name / brush-name / showcase goldens** — regenerate
  (point names now de-collide; brush names are new).

## Testing

**Part A (grammar) — assert the FULL `LabelSpec` (both frozensets) per the full-object rule:**
- Bare kinds: `poly` = all 4 poly categories; `name` = all 4 name categories.
- `poly:vis` = `{(T,F),(T,T)}`; `poly:hi` = `{(T,T),(F,T)}`; `poly:vis:hi` = `{(T,T)}`;
  `poly:vis,poly:hi` = `{(T,F),(T,T),(F,T)}`.
- `name:brush`, `name:point`, `name:hi`, `name:brush:hi`; union `name:brush:hi,name:point`.
- Keywords: `all` = both full; `none` = both empty; `highlighted` = poly `{(*,T)}` ∪ name `{(*,T)}`;
  default `poly:vis,poly:hi,name` = poly `{(T,F),(T,T),(F,T)}`, name full.
- Order independence (`name:hi:brush` == `name:brush:hi`); `hi`/`highlighted` synonyms equal;
  case/whitespace normalization (`poly, NAME` == `poly,name`).
- Errors → `ValueError` naming the token, end-to-end → clean exit NO traceback: unknown kind, unknown
  filter per kind, `name:brush:point`, `poly:brush`, `all,poly`, `none,name`. Zero-token inputs (`""`,
  `","`, `"  "`) ⇒ `none`.
- Render honors the spec: `--labels name:brush` draws brush names, NO indices, NO point names;
  `--labels poly` numbers EVERY face incl. back-facing (distinct from `poly:vis`); `--labels poly:vis`
  omits back faces; `--labels none` blank; a highlighted-only kind draws only for highlighted
  elements. (Use `_nonbg`/pixel-presence helpers.)
- **Default pin:** the default value labels front-facing OR highlighted faces (a highlighted
  back-facing poly IS numbered; a plain back face is NOT) + all names — matches today's poly behavior.
- Back-compat: `--labels highlighted` still draws highlighted poly indices + highlighted point names,
  **plus** highlighted brush names (asserted, not silent).

**Part B (placement):**
- **Regression the gap (assertable via the concrete `DensityGrid`):** synthetic scene with a dense
  poly-overlap knot + a nearby marker; assert the chosen box's `avg_density_in_box` is below the
  anchor cell's — it moved toward clearer space.
- **Concave-brush anchor:** a subtract (hollow) brush's name-anchor dot lands ON the wireframe, not in
  the hollow (guards B3's nearest-edge snap).
- Leader + dot drawn iff the label is offset; none when it stays put.
- Moderate cap: labels stay near anchors in an uncrowded scene.
- No label-label overlap still holds — extend
  `test_place_labels_avoids_overlap_for_several_close_anchors`.
- Determinism: same scene placed twice → identical positions (guards the sort order).
- Brush name de-collides with poly indices and point names (unified pass) — a showcase pillar hall
  doesn't stack a name on an index.

## Docs to update

- `decisions.md` (2026-07-22 09:54 UTC entry) — reconcile to the final model (`vis` = front-facing,
  default `poly:vis,poly:hi,name`, bare-kind-is-all) + rejected alternatives.
- `docs/usage.md` — the `--labels` model (bare = all, filters narrow, commas union, keywords,
  examples, the new-brush-names note); the placement note. (Occlusion not advertised.)
- `dev/docs/architecture.md` — `LabelSpec` (category-set) + `parse_label_spec`; `DensityGrid`
  cost-minimizing placement; unified label pass (point names leave `_draw_point_overlay`); brush-name
  anchor snap.
- `dev/docs/unrealed/rendering.md` — reconcile any label-placement note.
- `docs/leveldesign/` — if a preview/label section references `--labels {none,all,highlighted}`.
- Board: move this item forward; keep the optional `[implement] p3` true-occlusion TODO in `board/inbox/`.

## Out of scope

- True-occlusion label filtering (A4) — optional future, decoupled from `vis`.
- Leader-crossing avoidance / global label layout optimization — greedy density pass is v1; a
  crossing-minimization pass is a possible fast-follow.
- Peripheral/margin callout layout (brainstorm approach B) — rejected in favor of in-place density
  (recorded in `decisions.md`).

## Open questions

1. Final `k1/k2/k3` weights + grid `cell_px` — resolved empirically at build (B2); not a blocker.
2. Brush-name color: vivid CSG hue only when highlighted (spec's pick, consistent with point names)
   vs always the brush's CSG hue. Revisit if it reads poorly in the showcase.
