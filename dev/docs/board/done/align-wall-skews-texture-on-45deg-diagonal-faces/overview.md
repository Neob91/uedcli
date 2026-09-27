+++
priority = "p1"
kind = "debug"
summary = "align wall on a 45deg diagonal wall face yields a skewed, non-square texture frame"
+++

# align wall skews the texture on 45° diagonal wall faces — RESOLVED

Not a bug: `align wall` was faithfully reproducing UnrealEd's real `WALLX`/`WALLY` `POLY TEXALIGN`
stretch on tilted faces (measured, `dev/docs/unrealed/texalign.md`). The repro's actual want was a
different UnrealEd mode, `WALLDIR` (unit axes, never stretches). Resolved by
`align-wall-walldir-style-axes-split-off-a-wall`, which redefined `align wall` onto `WALLDIR` and
added `align wall-pan` (UnrealEd's `WALLPAN`) for cross-face phase sync.
