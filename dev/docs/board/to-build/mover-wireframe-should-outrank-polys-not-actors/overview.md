+++
priority = "p0"
kind = "debug"
summary = "a Mover's always-visible wireframe should always outrank a polygon hit in non-wireframe 3D view, even when obscured by other geometry -- but never outrank another actor"
+++

# Mover wireframe should have strict priority over polys (not actors), even when obscured

Owner ruling, direct (2026-09-17): **"Mover wireframe in non-wireframe 3d view should have selection
priority over polygons (but not other actors), even if it's obscured behind level geometry."**

This is a CATEGORY-based priority rule: `actor hit > Mover wireframe hit > polygon hit`, in the
perspective (non-wireframe) pane. Critically, the Mover wireframe should win over a polygon
regardless of whether it's the visually/screen-nearest thing at the click point -- even when other
level geometry is drawn in front of it (the wireframe still renders through it via `depthTest:
false`, per `mover-wireframe-occluded-by-geometry`, done), a click landing on that rendered wireframe
line should resolve to the Mover, not to whatever poly is actually nearest the camera at that pixel.

## Tension with today's `pickHit` fix -- read before implementing, don't silently pick a side

`selection.ts`'s `pickHit` (fixed today in `shift-modifier-convention-broken-for-poly-and`,
`5cb974fc`) currently lets an always-on-top line beat a precise poly hit ONLY when the line is ALSO
at least as close to the click (in screen space) as the precise hit -- a DISTANCE-based tiebreak, not
a category priority. That fix was itself a response to a real bug: an always-on-top Mover outline
was stealing picks from an unrelated, much-closer-to-the-click precise poly hit (`Brush803`), just
because the outline was ALSO within the raycast's line-hit threshold somewhere nearby.

This new ruling appears to ask for something stronger for Mover outlines specifically: they should
win over ANY polygon hit, not just a screen-nearby one. Reconcile this carefully:

- Read `dev/docs/board/done/shift-modifier-convention-broken-for-poly-and/overview.md` in full for
  the exact bug `pickHit`'s distance tiebreak was fixing, and the live repro that proved it.
- Investigate whether "Mover wireframe always outranks polys" can be implemented WITHOUT
  reintroducing that bug -- e.g. is the distinguishing factor that the Mover wireframe hit must still
  be a genuine raycast candidate within its own hit-test threshold (so a click nowhere near the
  Mover's screen-space outline still can't accidentally resolve to it)? If so, the fix may be: among
  ACTUAL raycast candidates (already threshold-filtered), a Mover-wireframe candidate always outranks
  a polygon candidate, dropping the distance tiebreak for this specific pairing only -- while still
  requiring the click to have been a genuine hit-test candidate on that line in the first place (not
  "any click anywhere near a Mover selects it").
- If you find this ruling and the `Brush803` bug's fix are genuinely in tension in a way you can't
  cleanly resolve (e.g. the owner's own repro from that item would now regress), STOP and use
  `AskUserQuestion` to lay out the conflict precisely and ask which should win, rather than silently
  picking one.

## Scope

- Applies to: Mover wireframe vs. POLYGON hits, in non-wireframe (perspective) render mode.
- Does NOT apply to: Mover wireframe vs. another ACTOR hit (point actor, another Mover, a mesh
  actor, etc.) -- an actor hit should still win over a Mover's wireframe, per the ruling's explicit
  "(but not other actors)" carve-out.
- Not addressed by this ruling (don't assume, ask if it matters): ordinary (non-Mover) brush
  wireframe outlines vs. polys in non-wireframe mode -- the ruling is specifically about Movers.

## Where to look

`web/src/scene/selection.ts`'s `pickHit` (the distance/always-on-top tiebreak logic) and
`tapSelect.ts`'s candidate construction (to check whether a Mover-wireframe candidate is already
distinguishable from an ordinary brush-wireframe candidate at the point `pickHit` runs -- may need to
thread that distinction through if it currently isn't, similar to how `isLineHit` was added earlier
today for a different distinction).

## Repro

1. Non-wireframe (perspective) 3D view.
2. Position a Mover so its wireframe outline renders over/through other level geometry (obscured, not
   visually the frontmost thing).
3. Click exactly on the rendered wireframe line, where it's obscured by that other geometry.
4. Expected: the Mover is selected. Actual (before this fix): the polygon in front wins instead
   (assuming the current distance-based tiebreak doesn't already cover this case -- verify first).
