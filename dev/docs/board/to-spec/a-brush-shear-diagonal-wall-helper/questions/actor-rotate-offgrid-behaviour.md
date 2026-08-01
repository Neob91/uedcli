# When `actor rotate` pushes a brush's vertices off the grid, what should it do?

## Context

A non-axis rotation (a 45° yaw) scales grid coords by ~0.707, landing the brush's world vertices
off-grid → CSG cracks/leaks. The item asked for a warning, and floated snap-to-grid or suggesting the
vertex-shear path as alternatives.

Options:

- **Warn only (recommended).** Emit the same newly-off-grid stderr warning `brush build --rotate`
  already emits; write the rotation exactly as asked. Does not alter geometry, matches the existing
  generator behaviour, and false-positive-free (GMath rotator noise is ~170× below the threshold).
- **Warn + point at the grid-align path.** Same, but the message names `brush shear` / build-to-grid
  as the on-grid alternative. (A message tweak on top of warn-only.)
- **Snap to grid.** Silently round the rotated vertices back onto the grid. Rejected as a default: it
  alters authored geometry without a request, can drag an on-grid brush off its own grid, and touches
  the load-bearing `Rotation`/`PrePivot` transform — it must never be a side effect of `rotate`.

Recommendation: warn only (with the message pointing at the shear/build-to-grid path). Never snap
inside `actor rotate`.

## Answer

<!-- Empty = open. -->
