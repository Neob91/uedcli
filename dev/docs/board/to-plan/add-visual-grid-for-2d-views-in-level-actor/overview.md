+++
priority = "p2"
kind = "implement"
summary = "Draw an actual world-space gridline overlay for orthographic (2D) panes in level actor preview."
depends-on = ["remove-numbering-grid-from-level-actor-preview", "move-the-preview-background-off-pure-black-to"]
spikes = ["dev/docs/spikes/2026-08-30-unrealed-ortho-grid-density/"]
+++

# Add visual grid for 2D views in level actor preview

Level actor preview's orthographic/2D panes carry no gridline overlay, so nothing on the image says
how big the geometry is or where it sits — the only addressing is the A1 label gutter, which is
image-space and moves with the camera.

A faithful port of UnrealEd's `DrawGridSection` (recovered by disassembly): the step doubles until
lines are ~4 px apart, every 8th line is the strong tier, and odd lines fade as they approach being
dropped so the grid never pops. Plus a `--grid-size` override and the framed region's world extent as
a bbox line at the top of each pane. `top`/`front`/`side` only; `iso` gets none.
Spec: [`spec.md`](spec.md).

Two dependencies, both narrow. `remove-numbering-grid-…` is placement-only — where the bbox line sits
when the gutter is also on. `move-the-preview-background-…` gates only the two grey values (§4): the
background is changing to `#404040`, and the grid greys have to be picked against the final palette.
Everything else here — the step selection, the flag, the caption — is independent of both.
