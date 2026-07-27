+++
priority = "p2"
kind = "implement"
summary = "bspcsg `bsp_build_fpolys` walks the node ARRAY; the engine's `MakeEdPolys` (0x33bb0) walks the TREE recursively (front/back/iPlane DFS)"
+++

# bspcsg `bsp_build_fpolys` walks the node ARRAY; the engine's `MakeEdPolys` (0x33bb0) walks the TREE recursively (front/back/iPlane DFS)

p2 bspcsg `bsp_build_fpolys` walks the node ARRAY; the engine's `MakeEdPolys` (0x33bb0)
walks the TREE recursively (front/back/iPlane DFS). This reorders the repartition soup, and since
`FindBestSplit` ties break by order it can shift deeper splits. NOT the current first-divergence
(the cospatial surplus face above blocks first — it changes soup CONTENT, not just order, so a
walk-order port cannot fix N=2 while that face survives). Port `MakeEdPolys` as a tree DFS ONLY after
the cospatial residual lands and node-for-node parity is still short. (spec §"Secondary residuals" #2.)
