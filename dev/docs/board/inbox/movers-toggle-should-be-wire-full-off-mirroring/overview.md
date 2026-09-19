+++
priority = "p2"
kind = "investigate"
summary = "Movers: on/off toggle should be a 3-state wire/full/off control mirroring UED22 -- needs RE first"
+++

# Movers toggle should be wire/full/off, not on/off

Owner request: the current "Movers: on/off" toggle (`Viewport3D.tsx`'s `showMoverSolid`,
`QuadLayout.tsx` line 212) should become a three-state "Movers: wire/full/off" control, mirroring
real UED22's own convention.

## Current behavior (code-confirmed)

- "off" (today's default/only non-solid state): Movers render wireframe-outline-only, in EVERY
  pane (perspective and ortho) -- `Viewport3D.tsx` line 461's comment: "wireframe-outline-only by
  default in every mode."
- "on": the outline stays, PLUS the Mover's own solid mesh renders additionally on top of it --
  perspective-pane only. `OrthoViewport.tsx` line 187: "Ortho panes never render the Movers:on
  solid-mesh overlay (perspective-only toggle)."

So today's "off" already corresponds to what a "wire" state would mean, and today's "on" to what a
"full" state would mean. A literal "off" (Movers not rendered at all) does not exist today.

## Open questions, owner-flagged

1. **Does this toggle (in any of its states) affect the 2D/ortho panes in real UED22?** Not
   determined -- needs RE against `uned/UED22/Editor.dll`/`render.dll` (disassembly and/or a live
   capture), per `GUI-PARITY.md`'s method and its hard rule: own-binary evidence only, never a
   third-party UE1 source. Today's ortho panes always show the wireframe outline regardless of this
   toggle (see above) -- confirm whether that's what real UED22 does too, or whether UED22's own
   mover-rendering setting has a real effect in ortho that this GUI is missing.
2. **Does an "off" state (Movers not rendered at all) make sense for 2D views?** Owner's own
   hunch: probably not -- if true, "off" may need to be a perspective-only concept, with ortho
   panes continuing to always show *something* (the wire outline) regardless of the toggle's state.
   This is a real design question if RE confirms UED22 has no true "hide movers" concept in ortho at
   all, not just a nice-to-avoid.
3. **If "off" genuinely doesn't apply to ortho, how should the UI convey that?** Options to consider
   once (1)/(2) are answered: grey out/disable the "off" option while an ortho pane is focused;
   show a tooltip/hint that off is perspective-only; or simply accept that "off" is a real,
   perspective-only state and ortho panes silently ignore it (as today's "on" already does) --
   whichever matches what real UED22 actually presents, not an invented convention.

## What to do, when picked up

RE against our own `uned/UED22/` binaries first (mirrors this whole campaign's existing "Radii
overlay colors"/pivot-cross/mesh-selection RE work): find UED22's own mover-rendering view setting,
confirm its real states and whether/how it's scoped to perspective vs. ortho. Only then design the
three-state control and its cross-pane UI treatment, matching whatever the disassembly shows -- not
guessing at a plausible-sounding convention.

## Where to look

`web/src/scene/QuadLayout.tsx` (the toggle control), `web/src/scene/Viewport3D.tsx`/
`OrthoViewport.tsx` (`showMoverSolid` consumption), `GUI-PARITY.md` (RE method + where the findings
belong once confirmed).
