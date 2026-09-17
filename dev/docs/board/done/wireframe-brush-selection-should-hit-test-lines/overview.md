+++
priority = "p1"
kind = "investigate"
summary = "DONE — the literal invisible-poly-face claim didn't reproduce (the fill mesh is already unmounted in wireframe mode); the real bug was three.js's Raycaster sorting threshold-passing line hits by camera depth, not screen proximity. Fixed by re-ranking hits by projected screen distance (`nearestScreenHit`). Same root cause as `mover-near-brush803-unclickable-in-wireframe-2d`."
+++

# wireframe brush selection should hit-test lines only, not invisible polys

Fixed 2026-09-17, same root cause and fix as `mover-near-brush803-unclickable-in-wireframe-2d`. Full
disassembly + live-capture writeup: `GUI-PARITY.md`'s "Click/hit-detection algorithm" Findings.

`web/src/scene/selection.ts`'s `nearestScreenHit`, wired into `tapSelect.ts`'s `resolveTapSelect`.
Regression: `selection.test.ts`'s `nearestScreenHit` suite.
