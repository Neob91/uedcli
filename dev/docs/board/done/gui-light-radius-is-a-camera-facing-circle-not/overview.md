+++
priority = "p3"
kind = "implement"
summary = "UED22 draws the light radius as a camera-facing DrawCircle in every pane, including perspective; our GUI draws a 3-ring wire sphere there"
+++

# GUI light radius is a camera-facing circle, not a sphere

Fixed 2026-09-18: `RadiiOverlays.tsx`'s `LightSphere3D` (three fixed world-space rings) replaced with
`LightRadiusCircle3D`, a real per-frame camera-facing billboard ring, matching `render.dll`'s
`DrawCircle`. Ortho panes needed no change (already flat in the pane's own view plane). See
`GUI-PARITY.md` "Radii light-radius shape" for the full writeup and verification.
