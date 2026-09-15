+++
priority = "p1"
kind = "implement"
summary = "GUI Slice 2: quad layout, ortho views matching actor diagram, org panel, level picker"
+++

# GUI Slice 2: quad layout, ortho views matching actor diagram, org panel, level picker

Completes the P1 viewer per the main spec's "P1 GUI — settled details" section: quad layout,
ortho viewports, shading modes, organization panel, level picker, grid, theme. Adds one new
requirement (owner, 2026-09-14): ortho views must match `actor diagram`'s CSG-colored brush
rendering and selected-brush highlight — see `spec.md`, which found this needs no new backend
field (`SceneActor.brush` is already computed for every brush actor, not just the selected one).
