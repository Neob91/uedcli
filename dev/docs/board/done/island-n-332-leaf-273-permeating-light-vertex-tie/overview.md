+++
priority = "p2"
kind = "debug"
summary = "DONE — the sub-ULP crossing tie was a computation-ORDER bug: `permeating_lights` recomputed the portal graph fresh at bake time, after `bspoptgeom::merge_near_points` had already remapped a `surf.pBase` the real editor's own one-time (pre-merge) portal graph never saw. Fixed by freezing the Pass-B portal list on `Model::leaf_portals`. Island re-verified byte-exact N=1..352 (was 331), no mask."
+++

# Island N=332 — leaf 273 gets one permeating light UED22 does not

Fixed 2026-09-13. Full trace, root cause, and the fix: `dev/docs/spikes/2026-09-13-portal-graph-frozen-before-optgeom/spike.md` (continues `dev/docs/spikes/2026-09-13-crossing-vertex-live-capture/`, which had narrowed this to a 1-ULP mismatch in one of the crossing's two input vertices but not yet found where it entered).

Regression: `permeating_lights::tests::leaf_portal_map_is_frozen_at_pass_b_not_recomputed_from_current_points`.
