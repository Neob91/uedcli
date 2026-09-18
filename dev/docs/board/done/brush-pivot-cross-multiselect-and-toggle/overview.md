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

**Part 2 (RE question): RETRACTED, not settled.** The original conclusion ("no toggle exists") was
based entirely on a third-party UE1 engine source (`fgsfdsfgs/UE1`) — owner ruling 2026-09-18: never
cite or use a third-party source for GUI-PARITY RE, only the actual UED22 binary counts as evidence.
No toggle button was added, and that part of the finding stands only because nothing was implemented
on a false basis — but the underlying question ("does UED22 have a visibility toggle for this
marker?") is OPEN again, not answered. Part 1 (own-code multi-select rendering) is unaffected — that
was live-verified against our own app, not the third-party source.

Full findings, citations and confidence tiers: `GUI-PARITY.md` "Pivot-cross multi-select rendering
(closed) + visibility toggle (RE-OPENED 2026-09-18)". The related out-of-scope divergence claim (UED22
hides the cross for a single selection) is also retracted, same reason:
`dev/docs/board/inbox/pivot-cross-shown-for-single-select-ued22-shows/`.
