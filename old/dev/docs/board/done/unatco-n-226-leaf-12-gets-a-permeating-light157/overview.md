+++
priority = "p2"
kind = "debug"
summary = "DONE — same computation-ORDER bug as Island N=332: `permeating_lights` recomputed the portal graph after `bspoptgeom::merge_near_points` had already remapped a `surf.pBase`, unlike the real editor's one-time pre-merge portal graph. Fixed by freezing the Pass-B portal list on `Model::leaf_portals`. UNATCO re-verified byte-exact N=1..242 (was 225), no mask."
+++

# UNATCO N=226 — leaf 12 gets a permeating `Light157` UED22 leaves out

Fixed 2026-09-13, same root cause and fix as `island-n-332-leaf-273-permeating-light-vertex-tie`:
`dev/docs/spikes/2026-09-13-portal-graph-frozen-before-optgeom/spike.md`.

Regression: `permeating_lights::tests::leaf_portal_map_is_frozen_at_pass_b_not_recomputed_from_current_points`.
