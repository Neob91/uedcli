+++
priority = "p2"
kind = "investigate"
summary = "how does mesh-actor selection work in UED22's 2D and 3D wireframe modes -- our GUI may differ"
+++

# Mesh selection in 2D/3D wireframe mode vs UED22

Owner's hunch: our GUI's mesh-actor selection behavior in wireframe mode (both 2D/ortho and 3D/
perspective) differs from real UED22 somehow -- not yet specified exactly how, needs investigation.

## Why this needs UED22 confirmation

Part of `GUI-PARITY.md`'s RE campaign -- confirm what UED22 actually does for mesh-actor
selection/hit-testing specifically in wireframe render mode (both viewport kinds) via disassembly
and/or a live capture, per that doc's method section, then compare against this GUI's current
behavior and file/fix any real divergence found.

## Where to look

`web/src/scene/tapSelect.ts`/`selection.ts` (current mesh-actor pick logic), cross-referenced against
whatever the RE work finds. This may overlap with the already-open
`gui-click-detection-algorithm-not-re-d-against` item -- check it first.
