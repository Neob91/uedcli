+++
priority = "p1"
kind = "chore"
summary = "The texture-format evidence now has a durable home; it landed before the spec holding it was deleted."
+++

# The texture-format evidence has a durable home

**DONE 2026-07-27**, by board item `native-texture-decode`, and in time: the measurements were
written down *before* the ephemeral spec and plan that held them were deleted, which was the point.

All three of its original claims are now false, which is how it was meant to end:

- `spikes/2026-07-25-native-texture-formats/` now carries `01-texture-layout-census.md` — the
  method, the roots, the enumeration rule, the 18,176-export census in both units, the three
  `ETextureFormat` dumps and where they disagree, the eleven stored `Format` properties, the
  `CompMips` measurements and the oracle tables.
- `dev/docs/unrealed/package-format.md` now covers the `UTexture` body, the property-gated
  `CompMips`, the four-slot format map and the layout-arbitration rule, and cites that spike.
- `dev/docs/rationale/texture-decode.md` holds the engineering reasoning.
