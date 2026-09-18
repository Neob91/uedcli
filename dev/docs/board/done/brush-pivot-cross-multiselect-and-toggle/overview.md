+++
priority = "p2"
kind = "investigate"
summary = "confirm whether the selected-brush pivot cross renders per-brush under multi-select, and check/implement a UED22-style visibility toggle"
+++

# Selected-brush pivot cross: multi-select rendering + visibility toggle

DONE 2026-09-18, both parts investigation-only, no code change.

**Part 1 (own code, no RE):** confirmed correct via real headless-Chromium multi-select + screenshots
— `PivotMarker` already renders once per selected brush (not gated to a single "primary" actor); the
owner's hunch did not reproduce.

**Part 2 (RE question):** confirmed NO — UED22's own pivot marker (`UnEdCam.cpp`'s `GPivotShown`) is
a single global crosshair, shown only for 2+ selected actors or a live grid-snap drag, never via a
manual toggle. No toggle button added (no basis to reproduce).

Full findings, citations and confidence tiers: `GUI-PARITY.md` "Pivot-cross multi-select rendering +
visibility toggle". A related but out-of-scope divergence (UED22 hides the cross for a single
selection; ours always shows it) filed separately:
`dev/docs/board/inbox/pivot-cross-shown-for-single-select-ued22-shows/`.
