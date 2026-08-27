+++
priority = "p2"
kind = "debug"
summary = "CleanupNodes' flip test calls FPlane::operator|, a four-component dot; bspcsg.rs ports it as a three-component normal dot, so a sliver coplanar pair can transpose a whole subtree."
+++

# `bsp_cleanup`'s coplanar flip test drops the W term

`uedcli-native/src/bspcsg.rs:402` decides whether a promoted coplanar node's `iFront`/`iBack` must
swap using `normal · normal` (three components). `CleanupNodes` (`Editor.dll 0x100321b3`) calls
`Core.dll!??UFPlane@@QBEMABV0@@Z` (RVA `0x17d60`), which is a **four**-component dot — `movups`/`mulps`
over all 16 bytes of the `FPlane`, then `shufps 0xb1` + `addps` + `movhlps` + `addss`. Its sibling at
`0x17d90` is the three-component `FPlane|FVector` overload; this call site uses the former.
**[DISASM Core.dll 0x17d60, Editor.dll 0x100321b3, 2026-08-27]**

The same primitive is now documented correctly a few hundred lines away, in
`bspcsg::inherit_parent_leaf_zone`'s docstring, so the file currently spells it two contradictory
ways.

Where it could bite: a coplanar pair accepted by `THRESH_SPLIT_POLY_WITH_PLANE` whose normals differ
materially — a sliver or near-degenerate face close to the splitter plane — with `dot3`
small-positive while `w_dead * w_P` is large-negative. The editor swaps the promoted node's children,
native does not, transposing a subtree's geometry, collision hulls and leaves.

Found by review, not demonstrated on a real map, and not fixed: changing it moves BSP topology, which
needs its own measurement against a golden. Found while fixing
`native-bsp-leaf-assignment-marks-2x-the-solid`.
