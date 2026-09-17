+++
priority = "p1"
kind = "debug"
summary = "mover wireframe should always render, unoccluded by other geometry, even in non-wireframe mode"
+++

# Mover wireframe gets occluded by other geometry

Movers should always draw their wireframe outline, in every render mode -- including non-wireframe
(solid) mode -- as an always-visible control cage regardless of what else is in front of it.
Currently that wireframe is hidden behind other geometry: normal depth-testing lets an opaque wall/
floor rendered in front of the mover hide its wireframe outline.

## Repro

1. Set up a scene where a Mover sits behind (or partially behind, from the camera's view) other solid
   geometry (a wall, floor, etc.) in a non-wireframe/solid render mode.
2. Observe: the Mover's wireframe outline is invisible where other geometry occludes it.
3. Expected: the Mover's wireframe always renders on top, unoccluded.

## Where to look

The Mover wireframe overlay's material/render settings (likely near
`web/src/scene/BrushOutlines.tsx`/`Viewport3D.tsx`/`OrthoViewport.tsx` or wherever Mover-specific
wireframe geometry is drawn) -- probably needs `depthTest: false` (or an explicit `renderOrder` high
enough to always composite last) on the Mover's wireframe line material specifically, without
affecting normal brush wireframe depth-testing.
