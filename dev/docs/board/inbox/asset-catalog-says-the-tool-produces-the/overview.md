+++
priority = "p2"
kind = "owner-question"
summary = "packages.md states the texture-decode limit without the scope that makes it true; proposed wording inside."
+++

# [OWNER — confirm] `packages.md` states the decode limit unscoped, and one half of it is false

**Nothing under `dev/docs/direction/` has been touched.** This is a proposal awaiting a yes, parked
here per `CLAUDE.md` "Direction docs".

*(Corrected 2026-07-27 after a build review. The first version of this item claimed
`direction/asset-catalog.md` "promises a picture unconditionally" and proposed adding the limit
there. **That was wrong** — `asset-catalog.md` already carries the limit, under "Produce the
picture, or a named error — never a wrong pixel", and it is owner-confirmed. The real gap is in
`packages.md`, and it is not a missing statement but an inaccurate one.)*

## The sentence

`dev/docs/direction/packages.md`, in the paragraph beginning "The limit this leaves is stated
wherever the universality claim is made":

> **a block-compressed 16-byte chain that no code resolves does not decode.** BC2 and BC3 have
> identical block sizes and identical chains and differ only inside the alpha half; nothing in the
> data separates them. **A code-less BC1 file decodes**, and so does P8, and so does any chain
> fitting exactly one layout. Never a wrong pixel.

The first half is exactly right. **"A code-less BC1 file decodes" is not.**

## Why that half is false, in plain terms

A texture's layout is worked out from the sizes of its mip levels. Block-compressed formats store
whole 4×4 blocks, so their levels stop shrinking once they hit one block; uncompressed ones keep
scaling. That usually separates them — but not always.

BC1 stores 8 bytes per 4×4 block. Plain 8-bit palettized data (P8) stores 1 byte per pixel. For a
64×2 image those come to the same number: `16 × 1 × 8 = 128` and `64 × 2 = 128`. Whenever a
dimension is not a multiple of 4, the two sizes can coincide, and the mip chain cannot tell them
apart.

When that happens, the tie is broken by the texture's numeric format tag — and a *code-less* file
has no tag, so the engine's own rule applies: an absent property equals its class default, which
for the format tag is 0, which means P8. **So a code-less BC1 file of that shape decodes as P8 — a
confident wrong image, not a decode.**

**Measured, and this is not hypothetical.** Of the 1,137 ambiguous mip chains in the tracked
`uned/UED22` corpus, **48 fit both P8 and the 8-byte block layout** — for example
`DeusExUI.u:HUDItemsBorder_Center` (64×2) and `:HealthButtonNormal_Center` (2×16). The remaining
1,089 fit both P8 and the 16-byte block layout.

What IS true is the scoped version: a code-less BC1 file **whose chain fits the 8-byte layout
uniquely** decodes.

## Proposed change — the exact text

Replace the sentence "A code-less BC1 file decodes, and so does P8, and so does any chain fitting
exactly one layout." with:

> A code-less BC1 file decodes **when its chain fits the 8-byte block layout uniquely**; where the
> chain *also* fits P8 — which happens whenever a dimension is not a multiple of 4, and which 48 of
> the 1,137 ambiguous chains in `uned/UED22` do — the implied `Format = 0` names P8 and it decodes
> as P8 instead. P8 decodes, and so does any chain fitting exactly one layout.

Nothing else in the paragraph changes, and the 16-byte half stays exactly as it is.

## Why it is your call, not mine

It is your tree, and the sentence is a claim about what the tool guarantees. The options:

- **Take the correction (recommended).** The doc stops over-promising. Cost: one more clause to read.
- **Take a shorter correction** — just delete "A code-less BC1 file decodes," and let "any chain
  fitting exactly one layout" carry it. Cost: loses the BC1-vs-BC2/BC3 contrast that makes the
  16-byte limit feel proportionate rather than arbitrary.
- **Leave it.** Cost: the doc states something the tool does not do, in the one paragraph whose
  whole job is to state the limit honestly.

## Answer

<!-- Empty = open. Write the decision here. -->
