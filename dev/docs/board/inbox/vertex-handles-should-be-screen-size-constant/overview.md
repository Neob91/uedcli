+++
priority = "p2"
kind = "investigate"
summary = "vertex/handle markers should render at a constant on-screen size regardless of zoom, in both 2D and 3D views -- RE UED22 to confirm"
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
