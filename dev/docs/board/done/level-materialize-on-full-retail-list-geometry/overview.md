+++
priority = "p1"
kind = "debug"
summary = "level materialize wedged every retail map: the typed MAP SAVE raced a slow MAP REBUILD. FIXED by batching the write drive into one EXEC <file>; geometry gate downgraded to warn. Verify texture-match bug remains (tracked separately)."
+++

# `level materialize` on the full retail map list — two blockers, FIXED

Goal: `level import` every OG Deus Ex map to a trunk, then `level materialize` back to a `.dx`, across
all 88 shipped maps. All 88 import cleanly. Two blockers found and fixed (owner decisions 2026-08-23):
(1) the pre-import geometry gate refused 48/89 levels' non-planar retail brushes — downgraded to WARN
(`validate_brush(planar_fatal=False)`), matching `doctor`'s existing severity; (2) `MAP SAVE` on a
retail-scale re-import raced a slow `MAP REBUILD` and the GUI editor dropped the keystroke — fixed by
batching the whole write drive (`OBJ LOAD`s → `MAP NEW` → `MAP IMPORTADD` → `EDIT PASTE` →
`MAP REBUILD` → `LIGHT APPLY` → `MAP SAVE`) into one `EXEC <file>`, which runs through the engine's own
exec loop instead of racing async keystrokes. Live-verified on `02_NYC_Bar` and
`06_HongKong_WanChai_Garage` matching spike ground truth. Two residuals: the post-verify texture-match
gap is tracked separately (`materialize-verify-qualify-level-textures`); a lighting Camera/save-fault
noted in an earlier spike was not observed here and stays untouched.
