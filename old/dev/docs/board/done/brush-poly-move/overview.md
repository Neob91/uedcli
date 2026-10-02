+++
priority = "p?"
kind = "implement"
summary = "`brush poly move` — translate a whole poly (all its vertices at once)"
+++

# `brush poly move` — translate a whole poly (all its vertices at once)

Done. `brush poly move BRUSH:SELECTOR… --by DX,DY,DZ` moves each selected face's welded corners
(watertight; neighbours deform), mapping the world delta per-brush via `world_to_local_delta`.
`--by` only (`--to` deferred). Follow-up: `brush-poly-move-spec-help-most-non-axis-moves`.
