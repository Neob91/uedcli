+++
priority = "p2"
kind = "implement"
summary = "on-screen virtual joystick + up/down buttons for mobile 3D move, deferred pending owner visual-design approval"
depends-on = ["mobile-and-touchpad-zoom-pan-support"]
+++

# Mobile 3D move joystick — visual design pending owner approval

The rest of `mobile-and-touchpad-zoom-pan-support` (ortho pinch-zoom/pan, sidebar collapse, trackpad
ctrl+scroll fix, toolbar overlap fix, Grid consolidation) shipped on `gui-staging-20260918`
(`b805e7d8`, `226a7ca3`). This piece — the mobile 3D perspective-pane move control — was deliberately
held back: mid-implementation, the owner asked to review a few visual-design options for the
joystick/up-down-button widget's appearance BEFORE any code for it is written. Nothing was built,
including the underlying input-handling logic (also held back, since it wasn't cleanly separable from
committing to a specific visual in the time available).

The mechanism itself is already fully spec'd and owner-approved (not open) — see the closed item's
git history (`git log -p --follow` on `dev/docs/board/done/mobile-and-touchpad-zoom-pan-support/
overview.md`, or the `gui_selection_pick_bug_campaign` memory file, 2026-09-18): an on-screen virtual
joystick (forward/back + strafe, matching WASD), touch-only, visible only in the perspective pane, plus
a separate up/down button pair (matching Q/E, not a 3rd joystick axis). Only the widget's exact
styling/shape/placement and the up/down buttons' look are open, awaiting the owner's visual-design
choice.

Next step: once the owner has approved a visual design, implement the joystick (touch-drag → forward/
back + strafe camera movement, reusing `Viewport3D.tsx`'s existing `flyMove`/`FLY_SPEED_UU_PER_SEC`
fly mechanics) and the up/down buttons, following the approved look.
