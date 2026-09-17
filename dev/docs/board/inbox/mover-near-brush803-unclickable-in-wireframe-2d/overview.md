+++
priority = "p1"
kind = "investigate"
summary = "mover near Brush803 can't be clicked in wireframe/2D mode -- an overlapping subtract wins the pick instead"
+++

# mover near Brush803 unclickable in wireframe/2D -- subtract wins the pick

Near `Brush803` there's a Mover actor. In wireframe mode or a 2D (ortho) view, clicking on/near the
Mover always resolves to a Subtract brush instead — the Mover cannot be picked at all from this
viewport state.

## Why this is a pick-priority question, not (only) a hit-test-shape question

This is part of `GUI-PARITY.md`'s open "Click/hit-detection algorithm" question
(`dev/docs/board/inbox/gui-click-detection-algorithm-not-re-d-against/`) — how UED22 resolves a click
when candidates overlap. A Mover and a Subtract brush occupying near-the-same space is exactly the
overlap case that item flags as unverified. UED22 almost certainly prioritizes an Actor (the Mover)
over a Subtract brush's wireframe when both are hit — Subtracts are typically not meant to steal picks
from actors sitting in their volume. Needs the disassembly + live-capture method that item already
scoped (no visual signature to eyeball; the fix has to be verified against the real hit-test).

## Repro

1. Open the level containing `Brush803` and its nearby Mover, in wireframe or a 2D/ortho viewport.
2. Click on/near the Mover.
3. Expected: the Mover gets selected. Actual: the overlapping Subtract brush gets selected instead.

## Where to look

`web/src/scene/tapSelect.ts`/`selection.ts` (current three.js-Raycaster nearest-hit convention, per
`GUI-PARITY.md`). Consider whether this folds into (or should be worked as part of) the existing
click-detection-algorithm item rather than being fixed in isolation — a priority-ordering fix here
that isn't grounded in UED22's real rule risks just flipping which wrong-order case fails.
