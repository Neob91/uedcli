+++
priority = "p1"
kind = "debug"
summary = "Fixed: bspAddNode's parent iZone/iLeaf seeding was never ported, so every node the detail-brush layer appends after TestVisibility read solid/zone-0. UNATCO now matches the editor exactly."
+++

# Native BSP leaf assignment marks 2× the solid slots — FIXED

`bsp_add_node` never seeded a new node's `iZone`/`iLeaf` from its parent
(`Editor.dll 0x1003524a` root/coplanar, `0x1003535b` front/back — the latter decoded 2026-08-27).
`csgRebuild` runs `TestVisibility` BETWEEN the repartition and the detail-brush loop, so the ~3300
detail nodes are never visited by Pass A/D and get their zones and leaves from `bspAddNode` alone.

UNATCO after the fix: `iLeaf == -1` slots 5424/12628 (was 11866), nodes with `iZone == (0,0)` 0 (was
3330), point actors resolving into solid 126/1437 (was 1027) — PathNode 2/228 and Light 2/193, the
editor golden's own figures; the residual is brush pivots. Pinned by
`bspcsg::tests::add_node_seeds_zone_and_leaf_from_its_parent`.

It was NOT why mesh actors do not draw — see `native-build-has-no-lighting-so-no-mesh-actor`.
