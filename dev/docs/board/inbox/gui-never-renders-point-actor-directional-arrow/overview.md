+++
priority = "p1"
kind = "investigate"
summary = "GUI never renders point-actor directional arrow gizmo (C_ActorArrow)"
+++

# GUI never renders point-actor directional arrow gizmo (C_ActorArrow)

Owner-flagged (2026-09-16, p1). `C_ActorArrow` (`UnEdCam.cpp`, RGB `(163,0,0)`, `GUI-PARITY.md`
"Radii overlay colors") is UED22's color for a per-actor directional-facing ARROW gizmo drawn in the
3D viewport -- the name itself says so, and the same color constant is separately reused for the
collision/light radii circles (already implemented, `RadiiOverlays.tsx`). This GUI currently has no
equivalent: `web/src/scene/SelectionMarkers.tsx` draws vertex dots + a pivot marker for a selected
BRUSH only; point actors get their class-icon sprite (`PointActorMarker.tsx`) and nothing else --
no facing/rotation indicator at all.

## What's needed before implementing

RE how UED22 actually draws this (geometry, size, always-on vs. selection-gated, which actor kinds
get it) -- `UnEdCam.cpp` around `C_ActorArrow`'s other use sites (`Draw3DLine`/similar calls near the
radii code, `UnEdCam.cpp:1486,1532,1584-1588` per this session's earlier read — several
`Draw3DLine(... C_ActorArrow.Plane() ...)` calls in that same function look like exactly this arrow's
own geometry, not yet decoded). Not investigated yet.
