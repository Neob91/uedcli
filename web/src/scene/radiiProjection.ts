// Pure ortho-projection math for the collision-cylinder / light-reach overlays (RadiiOverlays.tsx) --
// ports `uedcli/preview.py`'s `_draw_cylinder`/`_draw_sphere` 1:1 (not re-derived): a collision
// cylinder is upright and world-axis-aligned regardless of the actor's own rotation, so its ortho
// silhouette depends only on which axis is looking down it; a sphere silhouettes to a circle of its
// own radius under ANY parallel projection, in every axis. Framework-free -- `grid.ts`'s pattern.

export type OrthoShape = { kind: 'circle'; radius: number } | { kind: 'rect'; halfWidth: number; halfHeight: number }

/** Collision-cylinder ortho silhouette for one axis (`preview.py`'s `_draw_cylinder`): TOP looks
 * straight down the cylinder's own axis, seeing its circular cap (`radius`); FRONT/SIDE see it
 * edge-on, a `2*radius x 2*halfHeight` rect (`halfHeight` is the HALF-height -- the cylinder spans
 * `location.z +/- halfHeight`). */
export function collisionOrthoShape(axis: 'top' | 'front' | 'side', radius: number, halfHeight: number): OrthoShape {
  return axis === 'top' ? { kind: 'circle', radius } : { kind: 'rect', halfWidth: radius, halfHeight }
}

/** Light/sound-reach sphere ortho silhouette -- a circle of the sphere's own radius, in every axis
 * (`preview.py`'s `_draw_sphere` doc comment: true under any parallel/orthographic projection; the
 * `iso_scale` factor it applies is for that renderer's non-orthogonal ISO view only, which this
 * app's three true single-axis ortho panes don't have). */
export function sphereOrthoShape(radius: number): OrthoShape {
  return { kind: 'circle', radius }
}
