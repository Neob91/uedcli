+++
priority = "p3"
kind = "unknown"
summary = "`brush build extrude --taper S` — scale the FAR cap (the frustum/loft remnant)"
+++

# `brush build extrude --taper S` — scale the FAR cap (the frustum/loft remnant)

RE-SCOPED 2026-07-25 now that `brush build extrude` has landed, which is what the rest of the old
"`cube --taper` / wedge builder" item asked for: wedges, voussoirs and tapered blocks come
straight from a **trapezoid profile**, because that taper lives IN the profile plane, and the
`arch-voussoir.md` recipe shows it. The genuine remnant is taper **along the sweep axis** — a
frustum/loft where the far cap is a scaled copy of the near one (UED's *Extrude to
Point*/*Extrude to Bevel*), which neither `extrude`, nor `brush clip`, nor `brush build cone`
(apex-only, no `CapHeight` truncation) can produce. One flag on `extrude`, scaling the far cap
about profile `(0,0)`; note it makes the side quads non-planar unless the scaling is uniform, so
the spec must say what happens to a non-uniform case. (Blind-build test, 2026-07-25; re-scoped
2026-07-25 when extrude landed.)
