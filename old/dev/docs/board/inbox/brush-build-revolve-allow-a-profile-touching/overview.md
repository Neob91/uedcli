+++
priority = "p3"
kind = "unknown"
summary = "`brush build revolve`: allow a profile TOUCHING the revolve axis (solids of revolution)"
+++

# `brush build revolve`: allow a profile TOUCHING the revolve axis (solids of revolution)

v1 requires every profile vertex strictly off-axis (`u > 0`), because a vertex ON the
axis degenerates its swept quads to zero width — they need collapsing to triangles. That restriction
rules out spheres/cones of revolution, the natural use for a full-turn revolve.
(board item `brush-build-cylinder-cone-sides-has-no-upper` §4.7; cold review, 2026-07-25.)
