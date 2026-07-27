+++
priority = "p1"
kind = "unknown"
summary = "`POLY TEXALIGN` semantics spike — DONE"
+++

# `POLY TEXALIGN` semantics spike — DONE

(2026-07-26, was `p1 [spike]` on `inbox.md`). Measured
all nine of UnrealEd 2.2's surface-alignment modes live (44 faces × 9 modes twice — from a zero pan
and from an authored non-zero one — plus eight one-wedge levels bracketing the guard thresholds,
all via `MAP EXPORT` readback) and diffed them against `brush poly align`. Write-up +
committed harness + a golden of every measured frame:
`dev/docs/spikes/2026-07-26-unrealed-texalign-semantics/`; durable engine facts: `dev/docs/unrealed/texalign.md`
(new) and the rewritten `POLY` section of `dev/docs/unrealed/commands.md`; six regressions in
`test_engine_facts.py::test_texalign_*`. Headline findings: **nine** mode tokens not six
(`DEFAULT`/`WALLPAN`/`WALLCOLUMN` were missing from the doc); **`ONETILE` and `WALLCOLUMN` are
no-ops** in UED22, so the editor has no fit-a-tile-to-a-face mode at all; `TEXELS=` is parsed and
ignored; no mode ever changes texel density. The remaining REMNANT is not spike work — it is the
four spec decisions the findings raise, which are the owner's and are filed as an
`[OWNER — decide]` item on `inbox.md`.
