# actor survey: two clean tiers, distinct vocabularies, bare output

Owner rulings, 2026-09-26/27. `actor survey` today mixes authored geometry into the csg tier, annotates
lines with magnitudes, and shares relation names across tiers behind a `raw`/`csg` prefix. This
reshapes it into two tiers with disjoint semantics and disjoint vocabularies.

## The two tiers

- **raw = pure authored geometry.** Each brush is a volume, nothing more. Ignores CsgOper, trunk
  order, and Mover-ness entirely.
- **csg = resolved matter.** What the engine builds after Adds/Subtracts/Semisolids resolve in trunk
  order. Only this tier cares about CsgOper.

Every relation name is unique across the two tiers, so the per-line `raw`/`csg` prefix is dropped —
each line self-identifies its tier by its verb. The output still prints two labeled groups (authored,
then resolved) with the summary count; only the prefix goes.

**Why a raw tier at all:** it is the geometric sanity view of what was *authored*, before CSG
resolves it. So raw `overlaps` between a Subtract and the Add it carves is expected and common — not
an anomaly. Raw's value is seeing authored intent (enclosure, duplicates via `coincides`)
independent of resolution; anomaly-detection is the csg tier's job.

**Symmetric relations** (`meets`, `overlaps`, `coincides`, `touches`, `connects`) render with the
surveyed actor on the left. Directional ones (`encloses`, `crosses`, `occupies`, `carves`) keep their
fixed lead regardless of which side is surveyed.

## raw relations (geometry)

The RCC topology between two volumes. Renamed from the old `contains`/`touches` and stripped of all
kind/order logic.

| relation | meaning | direction |
|------------|-----------------------------------------------|---|
| `encloses` | one volume fully contains the other | encloser leads |
| `overlaps` | interiors intersect, neither encloses | symmetric |
| `meets` | boundaries meet, interiors disjoint (flush) | symmetric |
| `coincides` | identical volumes (duplicate / stacked brushes) | symmetric |
| (disjoint) | no shared space | — |

- **`overlaps` is new.** The old raw `touches` lumped flush contact and interpenetration together
  (SAT `cells_touch_or_overlap` returns true for both). Splitting them needs an interior-overlap test.
- **Decision procedure** (pieces exist: `_cell_intersection_volume` `actor_survey.py:519-564`,
  `authored_shape_contains` `567-609`, `cells_touch_or_overlap` `actorgraph.py:307-325`):
  - mutual full containment → `coincides` — **takes priority over `encloses`** (identical brushes
    satisfy `authored_shape_contains` both ways);
  - one-way full containment → `encloses`;
  - interiors interpenetrate (beyond the float-error guard) → `overlaps`;
  - boundaries coincide, interiors not crossing → `meets`;
  - else disjoint.
  `overlaps` vs `meets` is **binary** — the interiors either cross or they don't. Discriminator: SAT
  interpenetration *depth* (min interval overlap across `_sat_axes`, `actorgraph.py:295-325`);
  `cells_touch_or_overlap` computes the per-axis intervals but returns a bool, so a depth-returning
  variant must be written (axes/interval math exist, the depth reduction does not). The only tolerance
  is the RAW tier's own float-noise floor **`_TOUCH_EPS`** (1e-3,
  `actorgraph.py:253`) — **not** `CSG_TOLERANCE` (0.015), the resolved tier's point-dedup limit, which
  the code forbids in the raw tier (`actor_survey.py:443-446`). It absorbs float noise at an
  exactly-flush contact; it is not a minimum-thickness threshold — a genuine interpenetration past
  `_TOUCH_EPS` is `overlaps`.
- Non-brush actors: raw treats a non-brush actor as its `Location` point only — target of `encloses`
  (point-in-brush), no `overlaps`/`meets`/`coincides`; its collision extent is a runtime property, not
  authored geometry. (Owner: "1 for now.") **Future (deferred, not this item):** treat a non-brush
  actor's collision *and* static-mesh geometry as real geometry in the geometry tier — possibly in
  this command, possibly a separate one; undecided.
- **Display:** each raw line still shows the brush kind as a label (e.g.
  `Brush190 [Engine.Brush Subtract]`) for information — not used in the relation. (Owner ruling.)
- **Removed:** raw `carves` (was defined only by trunk order); the Subtract/Mover branching and the
  trunk-order "causality check" that `actorgraph.classify_pair` (`actorgraph.py:562-606`) used for the
  raw tier. All of it is CSG reasoning that has no place in the authored tier. **Scope note (owner
  ruling, 2026-09-27):** `classify_pair` itself is shared with `level graph`'s `build_graph`
  (unmentioned in this item), so it is left untouched — this item adds a new, separate pure-geometry
  classifier for the raw tier instead of rewriting `classify_pair` in place; `level graph`'s output is
  unaffected.
- Deliberately **not** split: tangential vs non-tangential enclosure (whether the enclosed brush
  touches the container wall or floats inside) — a finer RCC distinction with no authoring value.

## csg relations (resolved)

| relation | meaning | direction |
|-----------|-------------------------------------------------------------|---|
| `crosses` | source's resolved matter pokes past another's resolved face into solid it doesn't own | intruder leads |
| `occupies` | an actor sits in a Subtract's resolved void — a matter brush (adds matter) or a non-matter/point actor (just sits there) | occupant leads |
| `carves` | a Subtract removes another actor's matter — any amount, including a fully-internal cavity | subtract leads |
| `touches` | flush resolved-solid contact, no penetration | symmetric |
| `connects` | two Subtracts' voids are continuous | symmetric |

- **`crosses` must use resolved matter, not authored cells** (the bug that started this whole item;
  concrete case in the worked example at the end). `_source_cells` (`actor_survey.py:975-977`) feeds
  `penetration_depth` authored `decompose_convex` cells with no resolved filter, so an Add whose matter
  a later Subtract carved away still "crosses" an actor in that carved void
  (`Brush196 --crosses--> Brush184`). Fix: filter the source by `resolved_matter_of` as a
  **point-membership filter on the straddle points / footprint**, NOT by reshaping the source convex
  cells — `resolved_matter_of` of an Add is "authored body minus later subtracts", possibly non-convex,
  which would break `_convex_hull_2d`'s per-cell convex footprint (`actor_survey.py:986-1017`). This is
  the correctness-critical, build-first part of this item.
- **`occupies` replaces csg `contains` and covers non-matter actors too.** csg `contains` was
  `containment_winner` over *authored* shapes (`actor_survey.py:1990-2025`) — a geometric test wearing
  a csg label (why it named the outer `Brush190`). `occupies(X, S)` is the resolved relation **X sits
  inside Subtract S's resolved void**, detected per kind:
  - **Measurement basis (owner ruling: exact, not sampling).** The relation is a per-point ordered
    boolean-CSG predicate and its qualifying region is non-convex, order-dependent, multi-brush — NOT
    one actor's convex decomposition, so the existing primitives (point membership `_was_solid_before`
    1549-1560, `resolved_matter_of` 1267-1315; pairwise-convex `_cell_intersection_volume` 519-564) do
    not decide it, and the forward solidity oracle is ruled out (leading-Add shell inversion). **Build a
    per-query exact boolean-CSG evaluator:** intersect the convex cells, split by the ordered
    earlier/later brushes' half-spaces into convex sub-pieces, then test non-empty (`occupies`,
    existence) / sum volume (`carves`). No sampling. Two supporting pieces to build: **(1)** a
    full-order last-writer helper — void-at-p over all of `csg_order`, optionally excluding one actor
    (for condition (iii) and the point-actor branch); `_was_solid_before` only walks earlier-than-a-
    Subtract and can't exclude an arbitrary Add, and `resolved_matter_of` is per-actor. **(2)** a named
    volume tolerance for `carves`'s `> eps`, resolved tier (`CARVE_AREA_EPS` is an area, does not
    transfer).
  - **matter brush (Add/Semisolid) — MARGINAL (owner ruling).** X `occupies` S at a point p iff ALL of:
    **(i)** X's own matter survives at p (`resolved_matter_of(X, p)` True); **(ii)** S is still the
    reason p is empty in the resolved level — the carve currently operative there, not a carve since
    superseded by something else (a Subtract that once reached p at some earlier point in trunk
    history but is no longer what makes it void today does not count); **(iii)** p is void when X is
    excluded. Both sides matter — (i) is the "closed with X included" half the earlier one-sided
    wording dropped. **Without (i) the test over-fires the carved-away-Add bug itself:** for order
    `sub1 → A → sub2` with sub2 re-carving A, a point in `A ∩ sub1 ∩ sub2` passes (ii)+(iii) though A
    has no surviving matter there (`resolved_matter_of(A,p)` is False). **Without the "currently
    operative" reading of (ii), a Subtract earlier in trunk order can be wrongly credited too:** the
    first brush a level's world CSG resolves against carries no earlier writer of its own, so a naive
    "was p ever solid before S" test reads True for it unconditionally, regardless of whether S itself
    reaches p at all — every subsequent carve or refill at p is invisible to that reading. (i) also
    restores `carves`/`occupies` mutual exclusivity for an S-after-X pair. Per-`S` by construction (no
    `containment_winner`/authored-box fallback); catches a floating pillar.
    **Accepted consequence:** two coincident/shadowed Adds → *neither* `occupies` (the excluded side
    stays solid); pin it in a test so it stays recorded, not quietly "fixed" later.
  - **nonsolid brush (owner ruling) — by SHAPE.** A Nonsolid brush has no matter to drop, so the
    marginal test doesn't apply; it `occupies` S when its authored cells land in S's carved region
    (`nonsolid ∩ S ∩ was-solid-before(S)`). This is why a nonsolid decoration brush in a room is not
    left with zero csg facts.
  - **non-matter / point actor:** X `occupies` S iff X's `Location` is in S's carved region and still
    resolved-void there. **Derived the authored/relative way `resolved_matter_of` is, NOT an absolute
    `point_is_solid` query** — the pooled oracle inverts under the leading-Add shell
    (`resolved_matter_of` docstring `actor_survey.py:1291-1297`;
    `test_resolved_matter_ignores_the_pooled_solidity_oracle`).
  - A Mover is excluded as a matter source (outside world CSG).
  - Name: `occupies` (owner ruling, replacing the earlier `fills`).
- **`carves` moves to an exact ordered-volume measure.** Today `removed_by` (`actor_survey.py:2110-2138`)
  compares the victim's surviving *face area*, which misses a Subtract carving a fully-internal cavity
  (the Add's exterior faces don't change) — but an internal Subtract IS a carve (owner; face-area
  diagnosis confirmed against the code). Correct measure: `carves(S, victim)` iff `vol(victim ∩ S ∩
  {victim's own matter, just before S})` `> eps`. **Restrict to victim's OWN matter, not generic
  `_was_solid_before`** — the latter counts *any* Add's matter as solid-before-S, so if an intermediate
  Subtract carved victim and a *different* Add refilled p before S, those points would wrongly count
  toward `carves(S, victim)`. The retired `removed_by` got this right via a victim-specific delta;
  keep that restriction. Same non-convex ordered region as `occupies`, computed by the **same exact
  boolean-CSG evaluator** (owner ruling above) — not a single `_cell_intersection_volume` call. `eps`
  here is a **volume** tolerance: name it, resolved tier (`CARVE_AREA_EPS` was an *area* and does not
  transfer). Pin the internal-cavity case with a fixture (an Add with a Subtract fully inside it, no
  exterior poly touched).
- `carves` and `occupies` are **duals for an Add/Subtract pair**: the effective last writer is either the
  subtract (`carves`) or the add (`occupies`) — decided by resolution, not enclosure, and mutually
  exclusive per ordered pair (S-before-A → only `occupies` possible; S-after-A → only `carves`). Fires on
  partial occupancy, where `contains` was all-or-nothing. Two asymmetries mean the *kind sets* are not
  mirror images, so state them so both tiers are provably complete:
  - `carves` targets `{add, nonsolid}` and **never a semisolid** (`_CARVE_TARGET_KINDS`,
    `actor_survey.py:2078-2081`). `occupies` sources are `{add, semisolid}` (marginal test) **plus
    `{nonsolid}` (by-shape test)** — so a nonsolid `occupies` has no `carves` dual and no marginal
    semantics; the "duals/mirror-images" framing holds only for the Add/Subtract matter pair.
  - Coincident duplicate Adds each filling the same void → **no `occupies` for either** (dropping one
    leaves the other; only raw `coincides` survives). Same shadowed-add blind spot, but here it erases
    the fact entirely — note it.
  A redundant add shadowed by an outer add correctly does not `occupies`. Semisolid works:
  `occupies(Brush184, Brush269)`.
- **Composes where containment cannot.** An additive seated in a room built from two Subtracts is
  enclosed by neither alone, so `encloses` and any single-subtract containment stay silent. It reads
  as `occupies sub1` + `occupies sub2`, `crosses` neither: occupies both voids, escapes into solid past neither.
  Crossing sub1's boundary into sub2's void is void→void, so `crosses` stays silent; it fires only if
  the add reaches actual solid beyond the room. Generalizes to any number of carves. This holds only
  under the exact-volume measure above; the rejected face-area measure would fail it (a non-flush
  additive changes neither subtract's face area).
- Overlap attribution (a region both subtracts carve) inherits `carves`'s counterfactual subtlety —
  handle as `removed_by` already does.
- **`connects` reachability edge (verify with a fixture).** `_planar_void_contact`
  (`actor_survey.py:1835`) decides continuity by "is the shared cross-section void *at a coincident
  plane*," which does not verify the void is topologically *reachable* from the other subtract's main
  void. Correct for a subtract whose carve opens into the other's void (external chip, `redundant_
  nested_subtract`). But a **sealed internal bubble** — a Subtract fully buried in an Add's solid, not
  reaching the outer void — appears (from reading) to still report `connects` to the enclosing
  subtract, a false positive. Same sealed-cavity phenomenon as the `carves` face-area gap above. Pin
  with a fixture (Subtract fully inside an Add, itself inside an outer Subtract's void); if confirmed,
  `connects` needs a reachability test, not just shared-void-at-a-plane.
- **Non-matter actors keep a resolved containment fact — as `occupies` (owner ruling).** A Light /
  decoration / pathnode in a carved room contributes no matter, so it gets no `crosses` (unless its
  collision cylinder reaches solid) and no `touches` (non-brush authors no surviving face,
  `crosses_target_eligible` is False for non-brush, `actor_survey.py:828-834`). Its resolved tie to the
  room is `occupies` via the authored point-in-carve test (above) — *not* raw `encloses` against the
  Subtract's authored box, which is the authored≠resolved signal the `crosses` fix targets. This
  is why the earlier "drop csg `contains` and lose non-matter containment" option was rejected.
- **A nonsolid *brush* in a void reads `occupies` by shape (owner ruling).** A Nonsolid brush
  contributes no matter and is not a point actor, so it takes no `crosses`/`touches` and is only ever a
  `carves` victim — but it does get `occupies`, detected by its authored shape in S's carved region
  (see the `occupies` nonsolid branch above). So it is not left with zero csg facts as the plain
  matter/point split would have.

## Output

- **Bare-topology lines.** No magnitudes anywhere, no poly indices. Drop `touches(<area>)`,
  `crosses(<depth>)`, and the raw `:idx` (`Brush184:5`) — a single poly index is a silent half-answer
  (implies one touching pair when several touch). Scientific notation is moot once the numbers go.
- **`--json` deferred (owner ruling, 2026-09-27): not part of this item.** No JSON output for now —
  plain-text lines only. If added later: paired contact faces (which face meets which) are the natural
  structured extra, but per YAGNI (`conventions.md`) defer them until something actually consumes them
  — correct face-pairing is real output surface with no named consumer yet; never two flat index
  tuples per side (that loses the pairing).
- **Metrics are `actor relation`'s job.** The old `crosses`-depth rationale (telling ~6uu flush-mounts
  from ~60uu errors) was measured on **non-brush** fixtures and never applied to brushes (a flush
  brush contact is `touches`, not `crosses`); non-brush alignment precision belongs to `actor relation`.
  Extending survey with measurements later is possible but deferred (`someday/`).
- non-brush `crosses`: survey still reports the bare relation; precise alignment via `actor relation`.
- **`actor survey` is a diagnostic, not a `find`-style name producer.** It prints two labeled groups
  (fixed order — raw then csg — is what marks them; no per-line or per-block token replaces the
  dropped `raw `/`csg ` prefix, owner ruling 2026-09-27), not a clean one-name-per-line stream for
  piping into a mutating verb.
- Cross-relation de-duplication. `crosses`/`touches` are mutually de-duped (`actor_survey.py:1749-1755`).
  The other two co-firing pairs — `occupies`+`crosses` (an Add fills a void and pokes through the far
  wall) and `occupies`+`touches` (an Add fills a void and sits flush against its carved walls) — **both
  kept (owner ruling): they say genuinely different things.** Only `crosses`/`touches` stays de-duped.
- `crosses` becomes a boolean predicate: keep `penetration_depth`'s straddle+footprint *logic* (still
  needed to decide the predicate), drop only the reported number and the `depth_uu` field — no
  dual-format cruft (`conventions.md` no-back-compat).

## Rejected

- Keeping csg `contains` (authored test in the csg tier) — replaced by resolved `occupies`.
- Inline poly indices / `name:(i,j,k)` tuples on any line — misleading half-answer; a tuple per side
  also loses the pairing (which face meets which).
- Depth/area on the line — noise; its only real justification was non-brush, which is `actor relation`.
- Mirroring raw `:idx` onto csg — same half-answer problem, one tier over.
- Relation name `abuts` (for `meets`); renaming csg `touches`→`contacts` (`touches` fits solid contact).

## Sequencing (owner)

Correctness first: `crosses` resolved-matter fix and csg `contains`→`occupies`. Then raw rework +
output shape. Measurement-in-survey → `someday/`.

## Worked example — the `crosses` false positive (regression fixture)

The bug that started this item. In `19_Multiport`, `uedcli actor survey Brush184` reports:

```
raw Brush184 [Semisolid] --touches(6.554e+04uu^2)--> Brush196 [Add]
csg Brush196 [Add] --crosses(9.19e+03uu)--> Brush184 [Semisolid]
```

Expected (owner): csg **no relation** between Brush196 and Brush184; raw **Brush196 `encloses`
Brush184** (Brush196's authored volume fully envelops it).

Trunk order (confirmed from `order_value`): `Brush190 (Subtract) → Brush196 (Add) → Brush269 (Subtract)
→ Brush184 (semisolid Add)`. Brush269 is a Subtract *later* than Brush196, so it carves Brush196's
matter, and Brush269 fully encloses Brush184 (the survey's own raw containment fact). So Brush269's void
holds Brush184 and is carved out of Brush196 — in the resolved world Brush196 has no surviving matter
adjacent to Brush184, carved void lies between them. (Brush190 precedes Brush196, so it does not carve
it and is not the cause.) `crosses` fires only because `_source_cells` feeds authored cells — the fix
above (source filtered by `resolved_matter_of`) is what makes it silent. Pin this shape as the `crosses`
regression fixture.
