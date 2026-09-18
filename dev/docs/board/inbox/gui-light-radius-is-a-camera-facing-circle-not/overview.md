+++
priority = "p3"
kind = "unknown"
summary = "UED22 draws the light radius as a camera-facing DrawCircle in every pane, including perspective; our GUI draws a 3-ring wire sphere there"
+++

# GUI light radius is a camera-facing circle, not a sphere

Found while disassembling the radii block for `radii-overlay-color-hardly-visible-disassemble`
(2026-09-18), not chased — that item was scoped to the COLOR.

`uned/UED22/Editor.dll`'s radii block calls `URender::DrawCircle` for the light radius on every
branch, with no ortho/perspective split (call site VA `0x1003d932`). `render.dll`'s `DrawCircle`
(RVA `0x1c590`) builds its ring from the scene node's own camera axes (`FSceneNode+0x40..0x54`, read
at `0x1001c5c9`-`0x1001c62d`) — a camera-facing circle, not a world-plane one. `URender::DrawSphere`
exists in the vtable (`+0x9c`, RVA `0x1ce50`) but this block never calls it.

`web/src/scene/RadiiOverlays.tsx`'s `LightSphere3D` draws three orthogonal world-space rings in the
perspective pane instead. Its silhouette from any angle is close to the real thing, so this may not
be worth changing — but it is a divergence, and it is currently undocumented as one outside
`GUI-PARITY.md`.

Decide: reproduce the camera-facing circle, or record the sphere as a deliberate departure.
