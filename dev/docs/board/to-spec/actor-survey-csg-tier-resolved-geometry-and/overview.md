+++
priority = "p1"
kind = "implement"
summary = "actor survey: two clean tiers (raw=geometry, csg=resolved), distinct relation names, bare output"
+++

# actor survey: resolved csg tier, geometric raw tier, bare output

Reshape `actor survey` into two tiers with disjoint semantics and disjoint relation names:

- **raw** = pure authored geometry (`encloses`, `overlaps`, `meets`, `coincides`; ignores CsgOper,
  order, Mover).
- **csg** = resolved matter (`touches`, `crosses`, `occupies`, `carves`, `connects`; csg `contains`
  removed, replaced by `occupies`).

Names are unique across tiers, so the `raw`/`csg` prefix drops. Output lines are bare topology; all
metrics move to `actor relation`.

This is one item covering the whole reshape, including the `crosses` resolved-matter false-positive
(the correctness-critical, build-first part — worked example at the end of `spec.md`). See `spec.md`
for the full rulings, rejected alternatives, and sequencing.
