+++
priority = "p1"
kind = "feature"
summary = "mobile and laptop-touchpad zoom/pan/navigation are broken or inconvenient across the GUI's viewports and layout"
+++

# Mobile and touchpad support for viewport navigation

Owner's direct ask: "I want mobile and laptop touchpad support to be convenient." Four concrete
symptoms, not a UED22-parity question -- pure web-app input/UX work:

1. **Mobile: can't pinch-zoom in the 2D (ortho) panes.** Touch zoom gesture isn't wired up (or is
   captured/blocked) for ortho viewports.
2. **3D view: moving forward is only possible by zooming in.** There's no separate forward/dolly
   gesture on mobile -- zoom is currently the only way to move into the scene, which is awkward
   compared to a proper pan/fly control.
3. **Mobile layout: the two side panes take up most of the screen.** On a small viewport, the
   org/inspector panels leave little room for the actual 3D/2D views -- needs a more compact or
   collapsible mobile layout.
4. **Laptop trackpad: can't zoom in 2D views without zooming the whole browser page.** Likely a
   missing `preventDefault()` on a `wheel` event with `ctrlKey`/pinch-zoom gesture in the ortho
   viewport, letting the browser's own page-zoom handle it instead of the app.

## Scope

No RE needed -- this is entirely about this GUI's own input handling and responsive layout, not
UED22 fidelity. Investigate and fix each symptom; they may share some input-handling code (the
viewport wheel/touch event handlers) but the layout issue (symptom 3) is a separate CSS/responsive
design concern. Use judgment on whether to fix all four in one pass or split further once the actual
code is understood -- whichever produces cleaner, more reviewable changes.

## Where to look

`web/src/scene/Viewport3D.tsx`/`OrthoViewport.tsx` (camera control / wheel+touch event handlers),
and whatever component owns the overall page layout (side panels, responsive breakpoints).
