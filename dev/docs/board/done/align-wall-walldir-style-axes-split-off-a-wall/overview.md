+++
priority = "p1"
kind = "implement"
summary = "align wall: WALLDIR-style axes, split off a wall-pan anchor verb"
+++

# align wall: WALLDIR-style axes, split off a wall-pan anchor verb — DONE

`brush poly align wall` redefined from UnrealEd's `WALLX`/`WALLY` (world-axis projection,
stretches on tilted faces) onto UnrealEd's `WALLDIR` (unit axes from the wall's own direction,
never stretches, centroid-anchored, no shared-grid guarantee across a set). New verb
`brush poly align wall-pan`, reproducing UnrealEd's `WALLPAN` (slides an existing frame's anchor
to world Z=0, touching nothing else — the one `align` mode that doesn't zero `Pan`).

New: `query.csg_sign` (exact-case CsgOper sign), `polyalign._oriented_world_normal`
(reflection-correct world normal — `wall` is sign-sensitive, unlike `floor`, so needed a normal
helper neither `_world_normal` nor `query.visible_normal` could supply directly). Spec went
through 4 revisions / 3 review rounds (each caught a real bug); plan through 2 review rounds; a
final build-diff review found nothing. Docs updated: `docs/reference/brush/poly.md`,
`polyalign.py` module docstring, `rationale/polyalign.md`, `architecture.md`,
`unrealed/texalign.md` (the last two owner-approved and fact-checked before writing).

Supersedes `align-wall-skews-texture-on-45deg-diagonal-faces` (folded into `done/`, pointing
here) — that item's repro wasn't a bug, `wall` was faithfully reproducing `WALLX`/`WALLY`; the
owner confirmed the actual want was `WALLDIR`.
