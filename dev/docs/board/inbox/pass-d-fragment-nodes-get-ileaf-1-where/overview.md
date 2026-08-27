+++
priority = "p3"
kind = "debug"
summary = "zones.rs builds Pass D's zone-split fragments with iLeaf = (-1,-1); the editor builds them through bspAddNode(NODE_Plane), which copies the chain tail's real leaf pair."
+++

# Pass D's fragment nodes are created with `iLeaf = -1` instead of inheriting it

`uedcli-native/src/zones.rs:964` constructs each Pass-D zone-split fragment directly, with
`i_leaf: [-1, -1]` and an explicitly computed `i_zone`. Spec §7.4 step 3 says the editor creates them
via `bspAddNode(Model, iNode, NODE_Plane, …, poly)` — which, per the `bspAddNode` seeding block now
ported as `bspcsg::inherit_parent_leaf_zone`, copies the coplanar chain tail's `iLeaf` pair (swapped
when the normals oppose). Pass D runs after Pass A, so those leaves are real, not -1.

Why it may matter rather than being cosmetic: Pass D splices its fragments onto the owner's `i_plane`
chain (`zones.rs:966`), and every later `NODE_PLANE` add walks to that chain tail
(`bspcsg.rs:221`). So a detail-layer face coplanar with a Pass-D-split surf inherits `[-1, -1]`
(solid) instead of the real pair, and `bsp_cleanup` case A can promote such a fragment into a real
front/back tree slot, where `PointRegion` reads it.

Counter-evidence, which is why this is filed rather than fixed: after the `bspAddNode` fix the UNATCO
`iLeaf == -1` slot count lands exactly on the editor golden's 5424/12628, so on that map the
discrepancy is either absent or self-cancelling. Changing it without a golden to measure against
would be a guess. Found by review of
`native-bsp-leaf-assignment-marks-2x-the-solid`.
