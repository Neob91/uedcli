+++
priority = "p2"
kind = "investigate"
summary = "FIXED -- vertex/local-origin dots now hold constant screen size, confirmed as UED22's own real behavior"
+++

# Vertex handles should be screen-size constant, not zoom-scaled

Vertices/handle markers should show the same on-screen (pixel) size no matter how far zoomed in or
out the viewport is, in both 2D (ortho) and 3D (perspective) views. Currently they likely scale with
world-space zoom (getting visually larger/smaller as the camera moves), the naive default for a
plain 3D-space marker.

## Why this needs UED22 confirmation

Part of `GUI-PARITY.md`'s RE campaign. Real UnrealEd editors commonly render vertex handles/gizmos at
a fixed screen size (computing a per-vertex world-space scale factor from distance-to-camera so the
rendered size stays constant) -- confirm this is genuinely what UED22 does (and the exact fixed size,
if discoverable) before implementing a guessed convention.

## Where to look

`web/src/scene/SelectionMarkers.tsx` (vertex-handle dots) and any 2D/ortho equivalent -- likely needs
a per-frame or per-render scale computed from camera distance (`THREE.Camera`'s projection, or a
`renderer.getSize()`-based constant-screen-size technique) instead of a fixed world-space radius.

## Resolution

📖 Confirmed via `fgsfdsfgs/UE1` source (`Editor/Src/UnEdRend.cpp`'s `DrawLevelBrush`): UED22 draws a
vertex handle as a literal 2D screen-space dot (`Render->Project` to screen pixels, then
`Draw2DPoint` draws a fixed `X±1` box) -- constant screen size BY CONSTRUCTION, not a coincidence.
Full detail in `GUI-PARITY.md`'s "Vertex handle screen size" Findings section.

Fixed in `web/src/scene/SelectionMarkers.tsx`: a new `VertexDot` component reuses the existing
`PivotMarker` gizmo's per-frame rescale mechanism (`worldUnitsPerPixelAt`) instead of a fixed
world-unit sprite scale, at a practical modern size (`VERTEX_DOT_SCREEN_PX = 6`, not a literal copy
of UED22's ~2px, tuned for a 1990s low-res software renderer). Applies to both per-vertex dots and
the selected brush's local-origin dot, in both viewport kinds.

🔬 Live-verified (headless Chromium, `showcase_bar`, real zoom/dolly sweeps measuring actual rendered
pixel footprint): `Brush113`'s vertex dot across a ~32x zoom range in the ortho top pane went from
shrinking to invisible (unfixed) to holding 2-6px throughout (fixed); a 10-step perspective dolly
sweep held 7-8px at every step with the fix, versus visibly shrinking without it. 328/328 frontend
tests pass.
