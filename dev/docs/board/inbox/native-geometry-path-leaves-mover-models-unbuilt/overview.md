+++
priority = "p2"
kind = "implement"
summary = "REOPENED 2026-09-05: still real, now with bytes. NYC_Bar N=59 shows mover private Model.Bounds 6 vs 0 and Polys iLink/iBrushPoly unlinked vs linked when real world CSG exists."
+++

# The editor-free build path leaves mover models unbuilt

Closed 2026-09-05 as "superseded" (this file's old text: "folded into
`native-light-apply-bake-where-it-stands-and`... not re-confirmed as still open against the current
tree") -- WRONG. Re-confirmed as a live NYC_Bar N=59 divergence while fixing the other N=59 clusters
(Region zone-actor, mover base pose, pawn Foot/HeadRegion -- all fixed, see
`nyc-bar-n-59-brush-region-zone-and-ued22`).

At N=59 (the level's first world CSG brush), each mover's private `Model` diverges from UED22's:
`Bounds` 6 vs 0, and `Polys` `iLink`/`iBrushPoly` unlinked (`iLink` = own index, `iBrushPoly` = -1)
vs linked. Native doesn't build this geometry when real world CSG exists; the old "MAP REBUILD now
runs in the editor-free path" closure reasoning didn't hold once a level actually has a first real
world brush to trigger it.

See `nyc-bar-n-59-brush-region-zone-and-ued22` for the full N=59 context and the other clusters
already fixed. Not fixed here; needs its own build pass.
