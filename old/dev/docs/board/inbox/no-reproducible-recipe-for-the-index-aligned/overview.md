+++
priority = "p2"
kind = "debug"
summary = "The UNATCO golden the BSP-parity work is measured against (6314 nodes, index-aligned with native) lived in /tmp and is gone; `level materialize` produces a 6254-node tree in a different node order, so node-for-node parity can no longer be re-checked."
+++

# The index-aligned UNATCO golden cannot be regenerated

Every node-for-node parity claim about the native BSP is measured against
`/tmp/UEDGolden_unatco_full.dx` — 6314 nodes / 762 leaves / 7 zones, index-aligned with native's
build over 5646 nodes (`native-bsp-leaf-assignment-marks-2x-the-solid`'s measurement table,
`bspcsg-core-apply-scaled-brushes` and the `2026-07-15-native-materialize` spike). That file was
never committed and no longer exists, and nothing records how it was produced.

A plain `bin/uedcli … level materialize --tree level/unatco` (assemble unbuilt → `MAP LOAD` →
`MAP REBUILD` → `LIGHT APPLY`) does NOT reproduce it: measured 2026-08-27 on the same trunk it gives
**6254** nodes / 776 leaves / 3705 surfs, and its node array is in a different order — only 91 of
6314 indices carry a matching plane, though 5601 planes match as a multiset. So the trees are
substantively the same geometry laid out differently, and every index-keyed comparison against it
reads as a total mismatch.

Consequences:

- The topology-parity claim ("0 of 5646 aligned nodes differ in `iFront`/`iSurf`/`NumVertices`") is
  no longer re-checkable, so a regression in it would go unnoticed.
- The same is true of the `iLeaf` per-node check. `harness/leaf_solid_census.py` in the
  `2026-08-26-editor-free-native-materialize` spike works around it by pairing nodes on their PLANE
  instead of their index (838 nodes pair uniquely; 42 disagree on solidity, 0 of them swapped), but
  that covers only the uniquely-planed minority.

Wanted: a committed, scripted recipe for the golden — which verbs, in which order, on which input —
and either the golden itself or a frozen digest of it, so parity is a test rather than a remembered
number. Whether the 6314-vs-6254 gap is the recipe or a real difference is unresolved and is the
first thing to settle.
