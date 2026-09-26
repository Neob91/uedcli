+++
priority = "p2"
kind = "debug"
summary = "actorgraph._cell_vertices can emit a spurious, unbounded vertex from a near-parallel plane triple, silently inflating cell_volume/authored_volume and causing authored_shape_contains false negatives"
+++

# authored volume poisoned by unbounded plane-triple intersections

Found during code review of Task 15 (`actor_survey.cell_volume`/`authored_volume`/
`authored_shape_contains`, `.superpowers/sdd/2026-09-23-actor-survey-and-relation/`).

## Root cause (verified by reading, not touched)

`actorgraph.decompose_convex` turns each solid BSP leaf's half-space set into vertices via
`_cell_vertices` (`uedcli/actorgraph.py:201-213`): for every TRIPLE of the leaf's own half-spaces,
`_intersect_three_planes` solves the 3x3 linear system by Cramer's rule and the point is kept if it
satisfies every OTHER half-space within `_VERTEX_EPS` (`0.001` uu, `_SPLIT_EPS * 10`).

`_intersect_three_planes` (`uedcli/actorgraph.py:186-198`) only guards against an exactly-singular
system (`abs(det) < _SINGULAR_EPS`, `1e-9`). As three planes approach parallel/coplanar without
crossing that threshold, `det` shrinks toward (but stays above) `1e-9` and the solved intersection
point's distance from all three planes grows without bound — a well-known numerical-conditioning
property of solving a near-singular linear system, not specific to this codebase.

`_cell_vertices` has no check on the RESULTING POINT's magnitude or its distance from the cell's own
geometry — only that it satisfies the OTHER half-spaces within `_VERTEX_EPS`. A spurious point far
from the true cell can still pass that check (e.g. lying almost exactly on several other planes'
own far extensions), and once accepted becomes one of `ConvexCell.vertices`, which `cell_volume`
(Task 15) then feeds into its tetrahedra-from-centroid sum — one absurdly distant vertex inflates
that sum by orders of magnitude.

This is a property of decomposing a NON-CONVEX brush at certain rotations: a non-convex decomposition
introduces internal SPLIT planes (`ConvexCell.half_spaces` includes these, not just authored faces —
see `contact_planes`'s own docstring on this), and an internal split plane can end up near-parallel to
an authored face or another split plane for particular rotation angles, which a purely axis-aligned
brush (the overwhelming majority of this project's own fixtures) never exercises.

## Consequences

1. **`cell_volume`/`authored_volume` (Task 15)** — a poisoned cell reports a wildly wrong (typically
   enormous) volume instead of the true one.
2. **`authored_shape_contains`'s volume-coverage check (Task 15, round-2 fix for the separate
   vertex-vs-volume finding below)** — reasoned, not yet independently confirmed live: if the
   TARGET's own decomposition is poisoned, `cell_volume(target_cell)` inflates far past the sum of
   its real intersections with the container's (unpoisoned) cells, so the coverage check
   (`covered == tc_volume`) fails and `authored_shape_contains` reports **False for a target that is
   genuinely, fully contained** — a false negative on the `contains` primitive Task 16 builds on. The
   symmetric case (a POISONED CONTAINER cell) was not analyzed — flagging as an open question for
   whoever picks this up, not asserting a direction for it.

## Repro attempts (bounded effort, not exhaustive)

- Swept the project's own `_l_shaped_brush`-shape (one reentrant corner, decomposes to exactly 2
  cells, 1 internal split plane) through 0.25-degree rotation steps from 0 to 90 degrees about Z:
  **no blow-up found** — worst observed ratio to the true volume was `1.0000000067` (float noise) at
  7.25 degrees. So the single-internal-split-plane case appears robust across rotation; the failure
  mode most likely needs a shape with 2+ internal split planes that can each end up near-parallel to
  something.
- A hand-built T-shaped brush (3 internal split planes) hit a construction bug in the throwaway
  repro harness itself (a self-intersecting/degenerate `PolyList` from a winding mistake, not this
  bug) and was not debugged further to stay inside this task's own "file and move on" directive.

No live numeric blow-up is pinned in this item yet. The mechanism above is confirmed by reading the
code; a concrete triggering rotation/shape is still open.

## Why not fixed now

Foundational, already-shipped code (`actorgraph.decompose_convex`/`_cell_vertices`) used well beyond
this plan (`level graph`, `touches`, `connects`, `crosses` all depend on it). Owner ruling: file, do
not touch `actorgraph.py` in this build.

## Possible direction (not authorized, for whoever picks this up)

A bounds sanity check on each candidate vertex before the half-space check — reject a candidate
outside the LEAF's own half-space-derived bounding box (grown by `_VERTEX_EPS`) — mirrors the fix
`actor_survey._cell_intersection_volume` applies locally for its own (separate) triple-intersection
loop over TWO cells' combined half-spaces (Task 15 round 2). Not proposed as the definitive fix here,
just the nearest precedent in this codebase.
