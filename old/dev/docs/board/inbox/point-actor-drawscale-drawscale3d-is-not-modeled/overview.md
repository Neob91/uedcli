+++
priority = "p?"
kind = "owner-question"
summary = "Point actors' DrawScale/DrawScale3D are not modeled anywhere — in scope for any renderer, or someday?"
+++

# Point actors' `DrawScale`/`DrawScale3D` are not modeled anywhere

Split out of `render-the-full-transform-stack-in-the-textured` (owner: "defer to its own item",
2026-08-31) — brush transforms (scale/shear/mirror/rotation) now render correctly everywhere
(`actor diagram`, `level photo`, `brush intersect`/`deintersect`); this is the non-brush half that
was explicitly left out.

`DrawScale`/`DrawScale3D` (a point actor's own scale, distinct from a brush's `MainScale`/
`PostScale`) has no typed field anywhere (`model.py`) — nothing parses or stores it. The point-actor
sprite footprint in `preview.py` takes a bare `draw_scale` scalar (line ~339 as of 2026-08-05), not
derived from any authored property.

Open question for the owner: is this worth modeling at all, and if so where — sprite/marker
footprint in `actor diagram`, mesh scaling in `level photo --game` (the real game backend, which may
already honour it via the engine — unverified), both, neither? Needs scoping before a spec.
