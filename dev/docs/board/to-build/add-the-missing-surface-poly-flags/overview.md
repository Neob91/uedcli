+++
priority = "p3"
kind = "implement"
summary = "Add the missing surface poly-flags to the settable `--add-flag`/`--remove-flag` set (`PF_NAMES`)"
+++

# Add the missing surface poly-flags to the settable `--add-flag`/`--remove-flag` set (`PF_NAMES`)

`query.py PF_NAMES` exposes 16 poly-flags by name, but `kb/textures.md`'s catalog documents
five more real `PF_*` bits that `decode_flags` can READ yet no verb can SET: `brightcorners` (0x80000),
`smallwavy` (0x2000), `bigwavy` (0x1000), `highshadowdetail` (0x800000), `lowshadowdetail` (0x8000). Spec
adding them to `PF_NAMES` (which also feeds the CLI `choices=`), deciding whether ALL are safe / round-trip
clean to author (shadow-detail changes lightmap resolution; small/big-wavy are render distortions) or only
a subset, plus a regression that the settable set matches the catalog, and updating `kb/textures.md`'s
"these are the `--add-flag` names" claim to match. (Surfaced 2026-07-20 level-design docs review.)
