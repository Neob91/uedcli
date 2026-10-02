+++
priority = "p1"
kind = "implement"
summary = "SHIPPED — actor survey reshaped into raw (geometry) / csg (resolved) tiers, bare output, a new exact boolean-CSG evaluator backing occupies/carves. 8 real bugs found and fixed during implementation/review, each verified against the native solver; see plan.md."
+++

# actor survey: resolved csg tier, geometric raw tier, bare output

Shipped. `raw` = pure authored geometry (`encloses`/`overlaps`/`meets`/`coincides`); `csg` = resolved
matter (`touches`/`crosses`/`occupies`/`carves`/`connects`, csg `contains` replaced by `occupies`).
Names unique across tiers, no per-line prefix, no magnitudes. `docs/reference/actor/survey.md`
updated. Full design and the 8 bugs found/fixed along the way (each confirmed live against the
native solver, not just hand-traced): `spec.md`, `plan.md`.
