+++
priority = "p2"
kind = "debug"
summary = "a selected brush's/Mover's own bold selection ring isn't a click target in perspective mode"
+++

# Selected brush/Mover's own bold ring unclickable in perspective mode

Found reviewing `mover-wireframe-should-outrank-polys-not-actors` (not caused by it, not fixed
there). `BrushOutlines.tsx`'s `BoldRing` (a selected brush's or Mover's own undimmed outline) lives
inside `groupRef`, which `Viewport3D.tsx`/`OrthoViewport.tsx` only wire into the raycast candidate
set when `mode === 'wireframe'`. In the perspective pane's non-wireframe modes, once a brush/Mover is
selected, its own highlighted ring is not a click target -- a click there falls through to whatever's
behind it instead of re-selecting/deselecting via the ring.

Not investigated further; no repro steps beyond the code read above.
