+++
priority = "p1"
kind = "investigate"
summary = "DONE — not an actor-vs-subtract-brush priority rule (the guessed mechanism); three.js's Raycaster sorted threshold-passing wireframe-line hits by camera depth, not screen proximity, so a farther-on-screen line could win a click over the one under the cursor. Fixed by re-ranking hits by projected screen distance. Same root cause as `wireframe-brush-selection-should-hit-test-lines`."
+++

# mover near Brush803 unclickable in wireframe/2D — subtract wins the pick

Fixed 2026-09-17, same root cause and fix as `wireframe-brush-selection-should-hit-test-lines`.
Disassembled `UEditorEngine::Click`/`UViewport::ExecuteHits` (`Editor.dll`/`Engine.dll`): UED22's own
click hit-test is screen-space (a fixed 5×5 pixel box), never a world-space/depth radius. Full
writeup: `GUI-PARITY.md`'s "Click/hit-detection algorithm" Findings.

`web/src/scene/selection.ts`'s `nearestScreenHit`, wired into `tapSelect.ts`'s `resolveTapSelect`.
Live-verified: the same 13-point click battery on `DeusExMover4`'s own outline went from 0/13 to
6/13 correct in the perspective pane, 13/13 in the ortho top pane (reproduced independently by a
review subagent). Regression: `selection.test.ts`'s `nearestScreenHit` suite.

Umbrella item `gui-click-detection-algorithm-not-re-d-against` stays open — this fixes one real
mechanism, not a full scenario-by-scenario match against a live UED22 boot.
