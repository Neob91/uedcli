+++
priority = "p3"
kind = "implement"
summary = "level graph --from/--hops only filter output, not compute"
+++

# level graph --from/--hops only filter output, not compute

`level graph`'s `--from NAME --hops N|all` only filters which edges of the ALREADY-fully-computed
graph get printed (`actorgraph.scoped_edges`, called after `build_graph` has already run pairwise
SAT over every brush pair in the level). `--from`/`--hops` buys nothing on wall-clock: a level with
hundreds of actors pays the full O(N^2) pairwise cost whether or not scoping flags are given.

Documented as a known limitation in `docs/reference/level/graph.md` (`--from`/`--hops` section).
This item tracks the real fix, not attempted in the branch that added `level graph` per owner
ruling (2026-09-20 review) to keep the cheap AABB-broadphase + `_cell_edge_directions` cache fix
separate from a larger scoping change.

## What real incremental scoping would need

- `build_graph` (`uedcli/actorgraph.py`) would need to build only the pairs actually reachable
  from `seed` within `hops`, instead of the full N^2 pairwise sweep — a frontier-expansion BFS that
  interleaves "which brush pairs to test" with "which nodes are in scope," rather than the current
  two-phase "compute everything, then filter" shape.
- The awkward part: edge classification for a Subtract/Add pair depends on `order_index` (global
  CSG order across the WHOLE level), so even a scoped build still needs the full `level.order`
  ranking computed up front — only the pairwise geometric test (the expensive part: SAT +
  decomposition) is actually avoidable per-pair, not the order bookkeeping.
- `decompose_convex`'s cache is currently owned per `build_graph` call. A frontier-expansion
  version would still only decompose a brush the first time it's touched by the frontier, so the
  memoization shape carries over unchanged.
- Containment edges (brush -> non-brush actor) are currently a separate pass over ALL point actors
  x ALL ok brushes — scoping this would need `point_in_brush` restricted to only the brushes in
  the current frontier, and only points that are candidates for being IN scope at all (a point
  actor has no adjacency of its own until it's found to be contained by a brush already in scope).

## Not chased here

This is a real architecture change (a different `build_graph` shape, not a local tweak) — bigger
than the cheap AABB-broadphase + per-cell `_cell_edge_directions` caching fix landed alongside this
item, which cuts wall-clock on the FULL graph but doesn't change what `--from`/`--hops` compute.
