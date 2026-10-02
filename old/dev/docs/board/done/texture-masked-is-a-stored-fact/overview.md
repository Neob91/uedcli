+++
priority = "p1"
kind = "owner-question"
summary = "Texture `masked` is a stored fact — proposed `direction/asset-catalog.md` addition"
+++

# Texture `masked` is a stored fact — proposed `direction/asset-catalog.md` addition

Decided 2026-07-26, written into `specs/2026-07-25-unified-asset-catalog.md` §4d and
`unrealed/quirks.md`, but not yet in the direction topic. Proposed text (verbatim, awaiting a yes):

> **`masked` is a texture fact, read from the package.** `Masked` is a property of the *texture
> object*, set by the `Masked` checkbox when the texture is imported into UnrealEd; UE1 then ORs a
> texture's own flags into every surface it is applied to. So a masked texture punches its
> palette-index-0 pixels into see-through holes on any surface, with no surface polyflag set — which
> makes it invisible to any audit of surface flags, and a hole into unbuilt space wherever it lands
> on a solid face. The catalog therefore stores `masked` as a per-texture fact **read from the
> export's stored flag, never inferred** from the palette or from derived colours: inference is
> forbidden by the governing principle, and a texture may carry an index-0 colour without being
> imported masked. Filterable with `--masked`; not part of identity.
