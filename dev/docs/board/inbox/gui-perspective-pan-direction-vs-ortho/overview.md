+++
priority = "p3"
kind = "owner-question"
summary = "Perspective LMB+RMB pan now moves the camera with the drag; ortho pan moves the content with the cursor. Which convention wins?"
+++

# Perspective pan and ortho pan disagree on direction

`camera.ts`'s `pan` (LMB+RMB) moves the CAMERA along `+right * dx`, so dragging screen-right pushes
the content screen-LEFT. `orthoCamera.ts`'s `orthoPan` deliberately does the opposite — its doc
comment states "content follows the cursor (the standard direct-manipulation grab-and-drag
convention)" — and `GUI.md` records that as the ortho convention.

The perspective pane's horizontal pan silently REVERSED when `fcfb9486`'s render mirror landed:
before it, `cameraBasis.right` drew on screen-left, so `+right * dx` moved the content WITH the
cursor, agreeing with ortho. After the mirror it moves against it. Its vertical half
(`-worldUp * dy`) never changed and has always moved the camera with the drag, so the perspective
pan is now internally consistent and externally inconsistent, where before it was the reverse.

No evidence in `dev/docs/unrealed/` pins what UED22's own perspective LMB+RMB pan does, so this is
an owner call, not a derivation. Nothing was changed either way.
