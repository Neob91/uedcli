+++
priority = "p3"
kind = "unknown"
summary = "`brush build revolve`: allow a profile TOUCHING the revolve axis (solids of revolution)"
+++

# `brush build revolve`: allow a profile TOUCHING the revolve axis (solids of revolution)

v1 requires every profile vertex strictly off-axis (`u > 0`), because a vertex ON the
axis degenerates its swept quads to zero width — they need collapsing to triangles. That restriction
rules out spheres/cones of revolution, the natural use for a full-turn revolve.
(`specs/2026-07-25-brush-profile-generators.md` §4.7; cold review, 2026-07-25.)
