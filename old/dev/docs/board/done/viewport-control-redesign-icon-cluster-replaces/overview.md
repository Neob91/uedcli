+++
priority = "p2"
kind = "implement"
summary = "Viewport control redesign: icon cluster replaces joystick/arrows"
+++

# Viewport control redesign: icon cluster replaces joystick/arrows

Done. Deleted the touch joystick, up/down buttons, always-visible shading-mode row, and top-right
movers/grid/radii toolbar; replaced with a 3-icon vertical cluster (`ControlCluster.tsx` inside
`Viewport3D.tsx`: move-mode toggle + shading-mode tray; `MiscOptions.tsx` inside `QuadLayout.tsx`:
movers/radii/grid toggles + grid-size select), a mode-aware camera-drag dispatch (`camera.ts`), and
a shared hover/hold-tooltip mechanism (`useHoldTooltip.ts`). Design chosen via an interactive mockup
artifact after 3 options; spec and plan each converged through several review rounds before build.
