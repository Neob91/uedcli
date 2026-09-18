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

**Part 2 (RE question): RE-DONE FOR REAL 2026-09-18, ✅ confirmed against our own `Editor.dll`.** The
prior conclusion was retracted for resting on a third-party source; this pass re-derives it from
scratch by disassembling our own `uned/UED22/Editor.dll` (`pefile`+`capstone`). Confirmed: no manual
toggle exists, and UED22 genuinely hides the pivot cross for a single ordinary selected actor —
`?SetPivot@UEditorEngine@@...` (RVA `0x46060`) computes a global `GPivotShown = (SnapCount>0) ||
(Count>1)` from the level's own actor array, and the draw site inside `?Draw@UEditorEngine@@...`
(RVA `0x3c440`, VA `0x1003e7a0`) skips the entire pivot draw + `HGlobalPivot` hit-proxy registration
whenever that global is 0. Same conclusion as the retracted pass, now on real evidence. Full trace:
`GUI-PARITY.md` "Pivot-cross multi-select rendering (closed) + visibility toggle (closed 2026-09-18,
real RE)" — includes an honest note on a supplementary live-screenshot probe that did NOT cleanly
corroborate this (most likely caught a different, ungated per-brush marker instead), not smoothed
over. The related item is updated with the same confirmed answer:
`dev/docs/board/inbox/pivot-cross-shown-for-single-select-ued22-shows/`.
