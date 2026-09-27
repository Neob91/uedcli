+++
priority = "p1"
kind = "implement"
summary = "actor survey: two clean tiers (raw=geometry, csg=resolved), distinct relation names, bare output"
depends-on = ["actor-survey-crosses-false-positive-when-a"]
+++

# actor survey: resolved csg tier, geometric raw tier, bare output

Reshape `actor survey` into two tiers with disjoint semantics and disjoint relation names:

- **raw** = pure authored geometry (`encloses`, `overlaps`, `meets`; ignores CsgOper, order, Mover).
- **csg** = resolved matter (`touches`, `crosses`, `fills`, `carves`, `connects`; csg `contains`
  removed, replaced by `fills`).

Names are unique across tiers, so the `raw`/`csg` prefix drops. Output lines are bare topology; all
metrics move to `actor relation`.

See `spec.md` for the full rulings, rejected alternatives, and sequencing. The `crosses`
resolved-matter correctness fix is the depends-on item `actor-survey-crosses-false-positive-when-a`.
