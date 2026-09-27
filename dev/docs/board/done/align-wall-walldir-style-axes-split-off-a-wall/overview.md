+++
priority = "p1"
kind = "implement"
summary = "align wall: WALLDIR-style axes, split off a wall-pan anchor verb"
+++

# align wall: WALLDIR-style axes, split off a wall-pan anchor verb

Spec: `spec.md`.

Supersedes the diagnosis on `to-build/align-wall-skews-texture-on-45deg-diagonal-faces`: that
item's repro (a diagonal ramp face skewing under `align wall` + `scale`) is not a bug — `align
wall` faithfully reproduces UnrealEd's real `WALLX`/`WALLY` `POLY TEXALIGN` stretch, pinned by
`test_polyalign.py` and measured in `dev/docs/unrealed/texalign.md`. What the item actually wants
is a different UnrealEd mode, `WALLDIR` (unit axes, never stretches, direction from the wall's own
plane rather than a world axis) — confirmed with the owner in chat 2026-09-27: `align wall` should
have worked like `WALLDIR` from the start. This item redefines `align wall` accordingly and adds
`align wall-pan` (UnrealEd's `WALLPAN`) as a separate, composable anchor verb — the owner's own
suggestion, and it mirrors how UnrealEd itself splits the two.

Once this ships, fold `align-wall-skews-texture-on-45deg-diagonal-faces` into `done/` pointing here.
