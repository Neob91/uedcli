+++
priority = "p3"
kind = "debug"
summary = "the consolidated Grid control shows 'Grid  Grid Size: 16' -- redundant, should just say 'Grid'"
+++

# Grid control label is redundant

Owner report (2026-09-18, with screenshot): the consolidated Grid checkbox+dropdown control (from
`mobile-and-touchpad-zoom-pan-support`'s Grid consolidation) displays "Grid" (the checkbox label)
immediately next to "Grid Size: 16" (the dropdown's own selected-option text) -- redundant, reads as
"Grid  Grid Size: 16". Owner's exact instruction: "Just say 'Grid', nothing else."

## Root cause

`web/src/scene/QuadLayout.tsx`'s `<option>` elements render `Grid Size: {n}` as their label
(`GRID_SIZE_OPTIONS.map(...)`), so the dropdown's own visible text repeats "Grid" a second time right
next to the checkbox's own "Grid" label.

## Fix

Change the `<option>` label to just the number (`{n}`) -- the checkbox's own "Grid" label already
gives it context; the dropdown doesn't need to repeat the word. Keep `aria-label="Grid size"` on the
`<select>` itself for accessibility (that's not user-visible text, no redundancy there).

## Where to look

`web/src/scene/QuadLayout.tsx`, the `<option key={n} value={n}>Grid Size: {n}</option>` line inside
the `grid-control` div.
