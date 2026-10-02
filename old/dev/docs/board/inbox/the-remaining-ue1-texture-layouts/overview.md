+++
priority = "p1"
kind = "implement"
summary = "The REMAINING UE1 texture layouts"
+++

# The REMAINING UE1 texture layouts

The layouts uedcli still cannot read: Unreal Gold `RGB32`/`RGB64`/`RGB24`/`RGBA8`; 227
`BGRA8_LM`/`R5G6B5`/`RGB8`/`BGRA8`, and `BC4` upward. An owner decision, 2026-07-25.

**The measured layouts have LANDED** *(updated 2026-07-27)*: P8, BC1, BC2, BC3 and the second
`CompMips` array all decode natively. What is left is this list, and every one of these slots
already produces the named **`unverified-format`** error rather than a wrong picture or a silent
miss — the decoder reports what it detected and refuses. Nothing here is silent today; the item is
about turning those refusals into pixels.

**Sample acquisition comes first**, because implementing from the definitions alone would return a
plausible WRONG image (swapped channels) rather than an error, and there are **zero samples anywhere
on this machine**. Slot numbers are not portable between engines — Unreal Gold slot 2 is `RGB64` at
8 B/px while 227 slot 2 is `R5G6B5` at 2 B/px — so a definition read out of one engine's enum is not
evidence about another's file. Get a UT/227 content set or a purpose-built export, verify per layout,
then implement.

Format facts and the arbitration rule: `dev/docs/unrealed/package-format.md`. The measurement behind
the non-portability claim: `dev/docs/spikes/2026-07-25-native-texture-formats/01-texture-layout-census.md`.
