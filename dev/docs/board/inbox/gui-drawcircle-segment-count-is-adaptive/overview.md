+++
priority = "p3"
kind = "unknown"
summary = "UED22's DrawCircle picks its segment count adaptively from screen size (8 doubling to 256); our ortho radii rings are a flat 32"
+++

# UED22's `DrawCircle` segment count is adaptive, ours is fixed

Found while disassembling the radii block for `radii-overlay-color-hardly-visible-disassemble`
(2026-09-18), not chased.

`uned/UED22/render.dll`'s `URender::DrawCircle` (RVA `0x1c590`) starts at 8 segments
(`mov edi, 8`, VA `0x1001c635`) and doubles — capped at `0x100` — while a screen-size term stays
under a threshold (the loop at `0x1001c668`-`0x1001c683`). So a circle's smoothness tracks how big
it is on screen.

`web/src/scene/RadiiOverlays.tsx` uses a flat `CIRCLE_SEGMENTS = 32` for every ortho ring.

Related and still unconfirmed: that file's `CYLINDER_SEGMENTS = 8` cites a UT patch note
("an 8-sided wire cylinder"), not our binary. `URender::DrawCylinder` (RVA `0x1c9e0`) was looked at
in the same pass and its body is not a plain N-gon loop — the 8 was neither confirmed nor refuted.
