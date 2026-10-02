+++
priority = "p0"
kind = "debug"
summary = "FIXED -- pickHit let a farther always-on-top line steal a closer precise poly hit; resolveTapAction wrongly required Shift for genuine line hits outside wireframe mode"
+++

# Shift-modifier convention broken (poly-select regression + wrong line-hit gating)

Fixed both bugs per the owner's direct ruling (2026-09-17): "Shift is only to select BRUSHES (mover
is a brush too) by clicking on its VISIBLE POLY."

## Bug A -- root cause: `pickHit` let ANY always-on-top line beat ANY precise hit, no distance check

Not a Brush813-specific bug, and not the `flaky-masked-surface-and-sprite-picking-30pct` mechanism
(that item's own `pickHit` fix, precise-hit-wins-outright-unless-alwaysOnTop, was already landed and
is unrelated). The real bug: once `pickHit` (`selection.ts`) found an accepted always-on-top LINE
candidate (e.g. a Mover's own outline, `depthTest:false` so it's a raycast candidate in every mode),
it let that line win over ANY precise poly hit unconditionally -- with no check on which was actually
closer to the click on screen. A Mover's outline is threshold-accepted out to `lineThreshold` world
units (several screen px), so it can be a valid candidate while sitting well off to the side of a
click centered on a closer, ordinary poly right next to it.

Live-reproduced on `showcase_bar` (headless Chromium, real synthetic clicks): `Brush813`'s own poly
(the board item's originally-reported repro target) turned out to be a paper-thin, nearly edge-on
CSG_Subtract door-reveal (verified via the trunk T3D and the live scene payload -- 4 real polys exist,
but the framed camera view sees them edge-on, so a raycast there almost never lands a precise hit on
them at all). The SAME mechanism was caught red-handed one step over: clicking squarely on `Brush803`'s
own wall poly (the door-frame's next-door neighbor) at perspective-pane pixel (190,640) resolved to
`DeusExMover4` -- a real precise hit on `Brush803` existed in the same candidate set, genuinely closer
to the click, but the Mover's always-on-top outline won anyway purely because it was `alwaysOnTop`.

Fix: `pickHit` now only lets an always-on-top line beat a precise hit when the line's own screen
distance to the click is `<=` the precise hit's screen distance
(`bestLineDistSq <= preciseDistSq`). The intended case this campaign already fixed (a Mover's outline
drawn over a wall it doesn't occlude, `mover-not-selectable-via-wireframe-click`) still wins: there
the outline IS the nearest thing to the click (same ray, so both re-project to ~the same pixel), so
the distance check still passes. Pinned by a new `selection.test.ts` regression: a precise hit at the
click point vs. an always-on-top line 50px away -- precise hit must win.

Live-verified (real clicks, `showcase_bar`, before/after at the exact reported-wrong pixel (190,640)):
unfixed selects `DeusExMover4` (wrong); fixed selects `Brush803`. Also confirmed Shift+click at the
same pixel: unfixed selected `DeusExMover4`, fixed selects `Brush803` (the actor), matching the
owner's poly-select ruling. Independently reproduced by a review subagent.

## Bug B -- a genuine LINE hit never needs Shift outside wireframe mode either

`resolveTapAction` conflated two different `polyIndex: null` cases in non-wireframe mode: a genuine
hit on drawn LINE geometry (a brush/Mover outline) and an AABB-fallback hit (raycast missed
everything, fell back to ray-vs-actor-bbox). Both required Shift. Per the owner's ruling, Shift's role
is scoped to the POLY case only -- a line click has no competing poly/texture-select interpretation to
disambiguate from a camera-fly drag, so it should behave exactly like wireframe mode's own
no-modifier line-click rule. The AABB-fallback case (no specific poly OR line to key off) keeps the
old Shift gate, unchanged -- that case was explicitly out of scope per the board item.

Fix: `RawTapHit` gained `isLineHit: boolean`, set at all 6 construction sites in `tapSelect.ts`:
`false` for the merged world mesh, a Movers:on mover's own solid mesh, and the mesh-actor pick mesh
(all real poly/mesh hits); `true` for a brush/mover outline segment hit and the selected-actor bold
ring (both genuine line hits); `false` for the `pickActor` AABB fallback. `resolveTapAction` checks
`isLineHit` before the old `canSelectBrushTap` Shift gate -- a clean, mechanical distinction the code
already carried structurally, so no `AskUserQuestion` was needed per the board item's own escape
hatch.

Live-verified by isolating the mechanism: with `pickHit`'s new distance check temporarily reverted to
its old (buggy) unconditional-line-wins rule -- to reliably force a line-hit winner at a known pixel
without disturbing `resolveTapAction`'s real, already-fixed code -- a plain click (no Shift) at
perspective pixel (190,620) selected `DeusExMover4` directly (Class `DeusEx.DeusExMover`), matching
the board item's own repro step 2 verbatim. The real merged code (both fixes together) was then
re-verified via the full unit suite (`selection.test.ts`'s new `isLineHit: true` describe block,
exercising the real, unmodified `resolveTapAction` across unmodified/Ctrl/Shift) and via a direct live
re-run of the Bug A repro above. A live pixel where the FULLY fixed code (both bugs corrected
together) picks a genuine line winner in `showcase_bar`'s specific `Brush813`/`DeusExMover4` doorway
was not found by either this session or the review subagent -- the door-frame geometry is thin and
viewed near edge-on from the framed camera angle, so the Mover's outline rarely re-projects closer to
a click than the adjacent wall's precise hit once Bug A no longer lets it cheat. That's the *correct*
post-fix outcome (Bug A's fix narrowing how often a line wins is the point), not a gap in this fix;
the isolation test above is direct live proof of the exact mechanism the board item's repro step 2
needed.

## Verified unchanged

- A plain click on an ordinary brush poly (non-wireframe mode) still texture-selects, not
  actor-selects (live-verified at pixel (210,650), `Brush803:3`).
- The AABB-fallback code path (`canSelectBrushTap`/`pickActor`) is untouched -- `isLineHit: false` at
  that one construction site is the only change, and it's a no-op relative to the prior code's
  implicit behavior there. No live AABB-fallback-only repro point exists in `showcase_bar` (every
  brush in the level is `CSG_Add`/`CSG_Subtract`, no `Nonsolid`/trigger-volume brush geometry to
  reliably miss all real/line geometry against) -- relying on the unchanged code diff plus the
  existing, still-passing `resolveTapAction` unit tests for this path instead.

## Where

`web/src/scene/selection.ts` (`pickHit`, `resolveTapAction`, `RawTapHit`), `web/src/scene/tapSelect.ts`
(`isLineHit` wiring), `web/src/scene/selection.test.ts` (new/updated tests),
`dev/docs/GUI.md` "Selection & the Inspector" (corrected to match, cites the owner ruling). Also noted
(not closed) on `dev/docs/board/inbox/gui-texture-actor-click-select-modifier-rules/` -- this ruling
settles the poly-vs-line question by decree, not RE; that item's other open questions (Ctrl semantics,
the AABB-fallback gate, live UED22 confirmation) remain.
