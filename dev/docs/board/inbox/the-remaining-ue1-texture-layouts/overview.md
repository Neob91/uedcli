+++
priority = "p1"
kind = "implement"
summary = "The REMAINING UE1 texture layouts"
+++

# The REMAINING UE1 texture layouts

(Unreal Gold `RGB32`/`RGB64`/`RGB24`/
`RGBA8`; 227 `BGRA8_LM`/`R5G6B5`/`RGB8`/`BGRA8`, and `BC4`+). Created by
board item `three-design-calls-the-native-texture-formats` decision 4 (Andrzej, 2026-07-25). The measured layouts
(P8, BC1, BC2, BC3, `CompMips`) are covered by that spec; these have **zero samples anywhere on this
machine**, and slot numbers are NOT portable between engines (Unreal Gold slot 2 = `RGB64` at 8 B/px
vs 227 slot 2 = `R5G6B5` at 2 B/px — decisions.md 2026-07-25 06:30). So this needs **sample
acquisition first** (a UT/227 content set, or a purpose-built export), then per-layout verification,
then implementation — implementing from the definitions alone would return a plausible WRONG image
(swapped channels) rather than an error. Until it lands, those slots produce the named
`unverified-format` error, so nothing is silent.
