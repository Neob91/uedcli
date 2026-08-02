+++
priority = "p?"
kind = "implement"
summary = "`brush poly move` — translate a whole poly (all its vertices at once)"
+++

# `brush poly move` — translate a whole poly (all its vertices at once)

Builds
on vertex move: select a poly `(brush, poly index)`, translate every vertex by `--by DX,DY,DZ`
(v1 = `--by` only; `--to` centroid-target deferred). Moves shared corners consistently (deforms neighbours);
`validate_brush` must still pass (most non-axis moves rejected — document the constraint).
Pipeline: mutate PolyList → `validate_brush` → `record_mutation` (model-side). Decide selector ergonomics.
