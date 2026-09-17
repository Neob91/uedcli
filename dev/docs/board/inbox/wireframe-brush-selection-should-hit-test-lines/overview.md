+++
priority = "p1"
kind = "investigate"
summary = "in wireframe mode, brush selection should hit-test the wireframe LINES only -- polys are invisible there and shouldn't be pickable"
+++

# wireframe brush selection should hit-test lines only, not invisible polys

In wireframe mode, a brush's polys aren't drawn (only its wireframe edges are visible) but clicking
still hits the polys' invisible faces to resolve selection. In wireframe mode, only the drawn LINES
should be clickable — clicking empty space between wires (where a poly face would be, if filled)
should not select the brush.

This is very likely the same root mechanism as `mover-near-brush803-unclickable-in-wireframe-2d`
(inbox item filed alongside this one) — both are the viewport's hit-test picking an invisible/
underlying poly face over what's actually visible on screen. Consider investigating and fixing them
together rather than twice.

## Why this needs UED22 confirmation

Part of `GUI-PARITY.md`'s open "Click/hit-detection algorithm" question
(`dev/docs/board/inbox/gui-click-detection-algorithm-not-re-d-against/`). The expected behavior
(lines-only picking in wireframe) matches how a real wireframe editor viewport should work and is
almost certainly what UED22 does, but per that item's own scoping this needs the disassembly +
live-capture method to confirm the real hit-test doesn't ALSO consider polys, or has some other tie-
break, in wireframe view specifically.

## Repro

1. Switch a viewport to wireframe mode.
2. Click in empty space between a brush's wireframe edges, where a poly face would render if filled.
3. Expected: nothing selected (or whatever's actually behind it). Actual: the brush gets selected via
   its invisible poly face.

## Where to look

`web/src/scene/tapSelect.ts`/`selection.ts`'s Raycaster setup — likely needs to exclude poly meshes
(or switch to line-only raycasting with a screen-space threshold) when the active render mode is
wireframe.
