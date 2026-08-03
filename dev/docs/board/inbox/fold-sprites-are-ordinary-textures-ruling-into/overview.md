+++
priority = "p2"
kind = "owner-question"
summary = "[OWNER — confirm] fold sprites-are-ordinary-textures ruling into direction/asset-catalog.md"
+++

# [OWNER — confirm] fold sprites-are-ordinary-textures ruling into direction/asset-catalog.md

The texture-arm spec (`unified-asset-catalog/spec.md` §2) records an owner ruling from 2026-08-02
that has no durable home:

> Editor-icon sprites are ordinary textures — no icon-group detection; counted honestly as
> unclassified until classified.

The texture arm implements it as given (sprites enumerate, decode, and classify like any other
`Engine.Texture` descendant — no special case). The spec is ephemeral and is deleted when the item
lands, so the ruling would be lost. `direction/asset-catalog.md` is owner-gated, so this is parked
for a yes rather than written.

**Proposed addition to `dev/docs/direction/asset-catalog.md`**, as a bullet under "The tool does not
infer" (verbatim):

> - **Editor-icon sprites are ordinary textures.** A sprite (`S_Animal`, `S_Bot`, …) is enumerated,
>   decoded, previewed and classified exactly like any other texture — no icon-group detection, no
>   special case. It reads unclassified until an LLM classifies it, counted honestly.

If approved, the commit adding it carries a `Confirmed: asset-catalog` trailer.
