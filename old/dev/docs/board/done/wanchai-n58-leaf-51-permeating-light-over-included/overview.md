+++
priority = "p1"
kind = "debug"
summary = "DONE — same computation-ORDER bug as Island N=332/UNATCO N=226: `permeating_lights` recomputed the portal graph after `bspoptgeom::merge_near_points` had already remapped a `surf.pBase`. Fixed by freezing the Pass-B portal list on `Model::leaf_portals`. WanChai re-verified byte-exact N=1..58 (was 57); now bails at a new, unrelated N=59 mover-Polys divergence."
+++

# WanChai N=58 — leaf 51 gets one permeating light UED22 does not

Fixed 2026-09-13, same root cause and fix as `island-n-332-leaf-273-permeating-light-vertex-tie`:
`dev/docs/spikes/2026-09-13-portal-graph-frozen-before-optgeom/spike.md`.

Regression: `permeating_lights::tests::leaf_portal_map_is_frozen_at_pass_b_not_recomputed_from_current_points`.

Next blocker: `dev/docs/board/inbox/wanchai-n59-mover-polys-model2-diverges/` (new, unrelated).
