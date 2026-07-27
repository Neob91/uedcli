+++
priority = "p2"
kind = "unknown"
summary = "`actor preview` — on-face number overlap: minimal reshuffle + white keyline + lower opacity"
+++

# `actor preview` — on-face number overlap: minimal reshuffle + white keyline + lower opacity

—
BUILT 2026-07-23. p2. When two numbers overlap on screen (incl. two faces of one brush), `_resolve_decals`
applies a TINY nudge — shrink ≤10%, move ≤10% of the number's diagonal (`_onface_candidates` offers only
near-full sizes; no rotation, no deep shrink) — and `_draw_overlap_keyline` draws a constant 1-screen-px
WHITE ring just outside the strokes wherever they still overlap, so shapes stay readable. Number opacity
dropped ~20% (`_decal_opacity` 0.70→0.56, floor→0.12). `--breakdown` (per-brush grid) is the default
preview. Iterated heavily with Andrzej on renders; supersedes the elaborate 20%-tolerance/60%-floor/
cap-rotation resolver of the same day. Decision `2026-07-23 19:05 UTC` (supersedes `15:22`/`16:03`);
spec `specs/2026-07-23-decal-anti-overlap.md` now historical. Follow-up `2026-07-23 20:03 UTC`:
numbers are sized in a fixed 2-digit SLOT (`_text_bitmap` widens+centres a short number to
`_DECAL_SLOT_DIGITS`=2), so a lone `5` scales like `12`. Follow-up `2026-07-24 05:27`/`06:43 UTC`: breakdown DITCHES the legend
AND all overview labels — the SCENE pane is a plain CSG map (`labels="none"`), brushes identified by
their captioned per-brush panes — and frames every pane with a minimal 16px border (`_BREAKDOWN_PAD`,
`render_brushes_pgm(frame_pad=)`). The intermediate on-face-name overview was tried then removed.
