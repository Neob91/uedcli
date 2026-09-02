+++
priority = "p3"
kind = "implement"
summary = "preview label tint — palette-cycle collision at 11+ actors` — the hybrid per-actor label tints (`preview._TINT_PALETTE`, 10 hues) cycle when a scene has >10 dra"
+++

# preview label tint — palette-cycle collision at 11+ actors` — the hybrid per-actor label tints (`preview._TINT_PALETTE`, 10 hues) cycle when a scene has >10 dra

preview label tint — palette-cycle collision at 11+ actors` — the hybrid
per-actor label tints (`preview._TINT_PALETTE`, 10 hues) cycle when a scene has >10 drawn actors, so
the 11th actor shares actor #1's tint. Brush swatches (square) vs point markers (diamond) still
differ by glyph, so a brush/point collision is legible, but two BRUSHES sharing a tint is not. Only
bites very dense scenes; the legend + `--focus` mitigate. Options if it matters: grow the palette,
or perturb luminance on the second cycle. Noted from the 2026-07-22 hybrid-tint build.
