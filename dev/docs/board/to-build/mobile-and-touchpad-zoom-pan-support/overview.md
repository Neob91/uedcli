+++
priority = "p1"
kind = "feature"
summary = "mobile/touchpad navigation, collapsible sidebars (spec'd), toolbar overlap bug, and Grid control consolidation"
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
   collapsible mobile layout. Full spec below (owner-approved, not left to implementer judgment).
4. **Laptop trackpad: can't zoom in 2D views without zooming the whole browser page.** Likely a
   missing `preventDefault()` on a `wheel` event with `ctrlKey`/pinch-zoom gesture in the ortho
   viewport, letting the browser's own page-zoom handle it instead of the app.
5. **Toolbar buttons (`Movers`/`Grid Size`/`Radii`/`Grid`) overlap the org panel.** ROOT-CAUSED, not
   just observed (owner screenshot, 2026-09-18): all four are `position: absolute` in
   `web/src/index.css` with hardcoded `right: <N>px` offsets, but they're positioned relative to
   `.quad-layout-root` -- which is the FULL row containing BOTH the quad grid AND the 220px-wide
   `.org-panel` sidebar, not just the quad grid they're meant to overlay (each comment in the CSS
   says "top-right of the whole quad", but "whole quad" was conflated with "whole
   `.quad-layout-root`"). Any button whose `right` offset is smaller than the org-panel's width lands
   INSIDE the org panel instead of over the quad viewport -- `.grid-toggle` (right:4px), `.radii-
   toggle` (right:84px), and `.grid-size-select` (right:172px) all fall inside the 220px sidebar;
   `.mover-solid-toggle` (right:300px) mostly escapes it, matching the screenshot exactly (Movers sits
   separately to the left, the other three overlap the org panel's search box). Fix: position these
   relative to `.quad-layout` (the grid itself) instead of `.quad-layout-root`, so they stay correct
   regardless of the org-panel's width (including once it's collapsible, see below) -- either move
   them to be DOM children of `.quad-layout` (needs `.quad-layout` to be a positioning context,
   `position: relative`), or otherwise decouple their anchor from the org-panel's width. This bug is
   independent of symptom 3's responsive work but touches adjacent code; fix both together, in either
   order.
6. **Consolidate the Grid controls.** Owner ruling (2026-09-18): merge the `Grid: on/off` toggle and
   the `Grid Size: N` dropdown into ONE control -- a checkbox (grid on/off) paired with the size
   dropdown. **The dropdown stays visible but disabled (grayed out) when the checkbox is off** --
   explicit owner choice, not a guess -- so there's no layout shift on toggle and the last-chosen size
   stays visible. This reduces the toolbar's button count from 4 to 3 (Movers, Radii, the new combined
   Grid control), which also shrinks how much of `.quad-layout-root`'s width these controls need,
   easing (but not replacing the need to fix) symptom 5's positioning bug.

## Sidebar collapse -- owner-approved spec, not left to implementer judgment

The current layout has TWO independently fixed-width sidebars that never collapse or resize:
`.org-panel` (220px, folder tree + find, rendered inside `QuadLayout`) and `.inspector-pane` (280px,
selection details, rendered in `App.tsx`) -- 500px combined, with zero responsive breakpoints anywhere
in `index.css`. On a modest laptop window this is already a large fraction of the width; on mobile it
would dominate the screen entirely.

Owner-approved mechanism (`AskUserQuestion`, 2026-09-18), implement exactly as specified:

- **Each sidebar gets its own toggle button** that hides it, giving the freed width back to the
  viewport area (`.viewport-pane`/`.quad-layout`) when collapsed. The two sidebars toggle
  independently, not as one combined show/hide.
- **Responsive default**: below a reasonable mobile/narrow-window breakpoint, each sidebar defaults to
  COLLAPSED; above it, defaults to OPEN (today's always-on behavior). Pick a sensible breakpoint value
  (e.g. matching a common mobile/tablet cutoff) -- this specific pixel number was left to
  implementation judgment, not owner-specified.
- **Persistence**: once a user manually toggles a sidebar, that choice is remembered via
  `localStorage` and overrides the responsive default on subsequent loads on that device/browser. The
  responsive default only applies before any manual toggle has ever been recorded.
- Toggle button placement/icon is an implementation detail (match existing UI conventions in this
  codebase, e.g. the existing toggle-button styling already used for Grid/Radii/Movers) -- not
  owner-specified, use judgment.

## Scope

No RE needed -- this is entirely about this GUI's own input handling, layout, and toolbar
organization, not UED22 fidelity. Investigate and fix each symptom; they may share some input-handling
code (the viewport wheel/touch event handlers) but the layout/toolbar items (3, 5, 6, and the sidebar
spec above) are separate CSS/component concerns. Use judgment on whether to fix all of this in one
pass or split further once the actual code is understood -- whichever produces cleaner, more
reviewable changes. The sidebar-collapse mechanism and the Grid-control consolidation are NOT open
design questions -- implement exactly as specified above, they've already been decided.

## Where to look

`web/src/scene/Viewport3D.tsx`/`OrthoViewport.tsx` (camera control / wheel+touch event handlers),
`web/src/scene/QuadLayout.tsx` + `web/src/index.css` (toolbar buttons, org-panel), `web/src/App.tsx`
(inspector-pane, overall layout), and whatever component owns the overall page layout (side panels,
responsive breakpoints).
