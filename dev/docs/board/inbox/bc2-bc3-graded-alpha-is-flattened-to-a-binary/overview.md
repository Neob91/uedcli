+++
priority = "p3"
kind = "implement"
summary = "The decoder's transparency mask is one byte per texel, 1 or 0, so BC2/BC3 partial alpha is lost."
+++

# BC2/BC3 graded alpha is flattened to a binary mask

**Recorded while building board item `native-texture-decode` (slice S5), so the loss is written
down rather than discovered later.**

## What the mask is

Every decoded texture comes back with a `mask`: one byte per texel, **1 = opaque, 0 =
transparent**. Callers use it to skip texels — a sprite billboard does not occlude the geometry
behind its transparent corners, and a masked wall face shows what is behind its cut-outs.

That binary shape is the pre-existing contract and every caller reads it that way.

## What is lost

P8 and BC1 only ever carry two states, so binary loses nothing:

- **P8** has no alpha channel at all; the convention is that palette index 0 is a hole.
- **BC1** has one transparency bit per texel (its "punch-through" mode).

**BC2 and BC3 are different: they carry a real alpha VALUE per texel** — BC2 an explicit 4-bit
value, BC3 an interpolated 8-bit one. A texel at alpha 128 is half-transparent in the engine,
and the decoder reports it as fully opaque, because the flattening threshold is "not zero".

## Why it was built this way

Widening `mask` to carry 0..255 would change the meaning of a field every existing caller
already reads, in a slice whose job was adding two pixel formats. Existing callers test the byte
for truthiness, so they would keep working by accident while the documented contract silently
changed underneath them — the kind of change that should be made deliberately, not as a side
effect.

Measured scope of the loss today: **zero**. Every BC2/BC3 sample on this machine is in the
gitignored Unreal Gold install, and the only real ones measured (`DmRiot.unr`'s BC3 posters) are
uniformly opaque. Nothing in the Deus Ex substrate is BC2 or BC3 at all.

## What a fix would look like

Either widen `mask` to a real 0..255 alpha channel and re-point every caller, or add a separate
`alpha` field beside it and leave `mask` as the cheap binary question. The first is cleaner; the
second does not touch existing callers. Worth doing when something actually renders graded
alpha — a preview that composites, or a texture-catalog thumbnail that keeps it.
