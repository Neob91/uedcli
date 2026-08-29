+++
priority = "p2"
kind = "debug"
summary = "class preview mirrors mesh horizontally (ATM renders as MTA)"
+++

# class preview mirrors mesh horizontally (ATM renders as MTA)

`class preview` renders every mesh horizontally mirrored. `DeusEx.ATM` shows its front
label as "MTA" and its screen text backwards; flipping the PNG left-right makes "ATM" and
"WELCOME" read correctly. Confirmed on Barrel1/ammocrate/ATM (only text-bearing meshes show
the symptom by eye).

## Cause

`meshrender.py:166`, the view projection:

    return (x, -z, y)     # screen x, screen y (down), depth

UE1 world is left-handed (X fwd, Y right, Z up). This maps world-X straight to
screen-right and world-Y to depth with no axis negation, so the left-handed world is drawn
into the image's right-handed frame as a mirror. Inherited verbatim from the frozen spike
renderer `dev/docs/spikes/2026-07-25-native-mesh-decode/harness/render.py`. Landed in
`e64bd22` (class arm C2).

## Fix (proposed — needs owner yes)

Negate one screen axis to convert handedness, e.g. `return (-x, -z, y)`. Side effects to
check, not assume:
- The Lambert normal `n` is built from view-space edges (`meshrender.py:180-185`); a bare
  screen-X negation flips `n`'s sign and would darken lit faces / light dark ones. The
  triangle winding / normal sign must be corrected in the same change.
- `azimuth_uu` (the reported mesh-local yaw) may need its sign reconciled so the number
  still matches the un-mirrored view.

Pin with a regression test: render a mesh with known asymmetric UV text and assert a fixed
pixel-column ordering, or check the sign of the projected X for a known vertex.
