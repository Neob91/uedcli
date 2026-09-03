+++
priority = "p3"
kind = "debug"
summary = "Under the gated UEDCLI_BSPCSG_INCREMENTAL_POINTS diagnostic, bsp_refresh_points_vectors remaps orphan-only iVertex to -1 and merge_near_points later indexes remap[v.i_vertex as usize] unguarded -- a latent panic; default path unaffected."
+++

# Gated incremental-points path can panic on a -1 orphan iVertex

Found by the 2026-09-03 verts/points review. `passes.rs::bsp_refresh_points_vectors` remaps ALL
verts, writing `-1` into orphan verts whose point it drops; under the off-by-default
`UEDCLI_BSPCSG_INCREMENTAL_POINTS` path that GC runs per-brush BEFORE `bsp_opt_geom`, whose
`merge_near_points` applies `remap[v.i_vertex as usize]` with no `>= 0` guard — `-1 as usize`
panics. Also now semantically inconsistent with the default path's editor rule (orphan `iVertex`
left numerically untouched, `reorder_points_canonical`). Fix when the gated path is next touched:
guard the index and align the orphan semantics.
