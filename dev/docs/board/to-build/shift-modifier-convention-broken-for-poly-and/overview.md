+++
priority = "p0"
kind = "debug"
summary = "Shift+LMB brush-actor select is broken on a real poly (Brush813), and wrongly required for wireframe/outline-line hits which should never need it"
+++

# Shift-modifier convention broken (poly-select regression + wrong line-hit gating)

Owner ruling, direct and explicit (2026-09-17): **"Shift is only to select BRUSHES (mover is a brush
too) by clicking on its VISIBLE POLY."** Two concrete bugs follow from this, both p0:

## Bug A: Shift+LMB on a poly doesn't select the brush actor (regression)

`Brush813`: Shift+LMB on its own poly does not select the brush. Per the EXISTING, supposedly-already-
correct convention (`dev/docs/GUI.md` lines 215-218, `selection.ts`'s `resolveTapAction`: a genuine
surface hit with `polyIndex != null` in non-wireframe mode, Shift held -> `select-actor`), this should
already work -- investigate why it's failing for this specific brush. Suspect: does the raycast on
`Brush813` actually resolve `polyIndex` at all, or does it fall through to the AABB actor-level
fallback (`pickActor`, `polyIndex: null`) for some geometry reason (thin poly, decal, etc. -- this
campaign has hit exactly this class of bug before, see `flaky-masked-surface-and-sprite-picking-30pct`
and the `tapSelect.ts` raycast-miss-falls-back-to-pickActor mechanism)? If so, this may share a root
cause with that other open item -- check before assuming they're unrelated.

## Bug B: a wireframe/outline LINE hit should NEVER require Shift (not just for Movers)

Currently `resolveTapAction`'s "anything else" branch (a hit with no `polyIndex` -- covers BOTH a
genuine line hit AND an AABB fallback with no poly to fall back to) requires Shift to select the
actor in non-wireframe mode (`canSelectBrushTap`), matching wireframe mode's genuinely-different,
correct "no modifier needed" rule only when `mode === 'wireframe'`. This conflates two different
things: a **genuine LINE hit** (a real click ON visible line geometry, e.g. a Mover's always-visible
outline in ANY mode) should behave like wireframe mode always does -- select the actor directly, no
Shift needed, since there's no competing poly/texture-select interpretation for a line click at all.
An **AABB-fallback hit** (missed all real geometry, landed only inside a brush's bounding box) is a
DIFFERENT case GUI.md's own rationale (avoiding ambiguity with an incidental camera-drag nudge) may
still justify gating behind Shift -- the owner's ruling was specifically about POLY vs LINE, and did
not address the AABB-fallback case explicitly. **Do not silently change AABB-fallback behavior** --
if the current code can't cleanly separate "real line hit" from "AABB fallback" without touching that
case too, stop and ask the owner via `AskUserQuestion` rather than guess.

Concrete repro of Bug B: clicking a Mover's always-visible wireframe outline in plain non-wireframe
mode (Movers:on off) currently requires Shift (confirmed live, `mover-not-selectable-via-wireframe-
click`, done -- but done AGAINST THE WRONG CONVENTION, since Shift shouldn't be required there at
all). This item's fix will likely touch that same code path again -- read that item's history first.

## Where to look

`web/src/scene/selection.ts`'s `resolveTapAction`/`canSelectBrushTap`, `selection.test.ts`, and
`tapSelect.ts`'s candidate construction (to check whether a "real line hit" vs "AABB fallback" is
even distinguishable at the point `resolveTapAction` is called -- may need to thread that distinction
through if it currently isn't).

## Documentation

`dev/docs/GUI.md` lines ~210-226 documents the CURRENT (buggy) convention and needs updating to match
this ruling once fixed -- this needs the owner's yes per `CLAUDE.md`'s dev/docs rule, but the owner's
own direct statement in this conversation ("Shift is only to select BRUSHES... by clicking on its
VISIBLE POLY", reiterated for emphasis) IS that yes for this specific correction. Cite it as
`(Owner ruling, 2026-09-17.)` when updating, matching this doc's existing citation convention. Also
cross-reference the still-open `dev/docs/board/inbox/gui-texture-actor-click-select-modifier-rules/`
item -- this ruling settles the poly-vs-line question directly by owner decree; note that in the item
without closing it if other parts of that question remain open.

## Repro

1. Plain non-wireframe mode. Shift+LMB on `Brush813`'s own visible poly. Expected: brush selected.
   Actual: not selected (bug A).
2. Plain non-wireframe mode (Movers:on off). Plain LMB (no Shift) on a Mover's wireframe outline.
   Expected: Mover selected. Actual: nothing happens (bug B).
