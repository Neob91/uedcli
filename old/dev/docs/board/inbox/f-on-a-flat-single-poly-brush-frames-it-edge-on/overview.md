+++
priority = "p?"
kind = "debug"
summary = "F frames a bbox from the current view direction, so a one-poly flat brush ends up edge-on or back-facing and appears to vanish"
+++

# F on a flat single-poly brush frames it edge-on and shows nothing

Found while live-verifying the surface-selection stipple
(`../../done/surface-selection-highlight-color-disassemble/`), unrelated to that change.

`showcase_bar`'s `Brush111` and `Brush42` (the "Red Star" and "Heller" wall signs) are each a
SINGLE flat quad — one poly, four verts, confirmed from the scene payload. Finding one in the org
panel and pressing `F` leaves it invisible: `F` frames the actor's bounding box from whatever
direction the camera already faces, and a zero-thickness quad seen from anywhere but its own front
is either edge-on (a line) or back-facing (nothing). In a live session ~450 aimed and grid clicks
never landed on either sign, and selecting the brush or any of its poly indices changed zero
pixels.

Not a selection or rendering bug — the same session's masked-surface check passed cleanly once it
switched to a six-sided brush. The question is whether `F` should orient toward a flat actor's own
face (or pull back to a distance where an edge-on sliver is at least visible) rather than only
position the camera.
