+++
priority = "p1"
kind = "owner-question"
summary = "Texture GROUP is a first-class fact — proposed `direction/asset-catalog.md` addition"
+++

# Texture GROUP is a first-class fact — proposed `direction/asset-catalog.md` addition

Decided 2026-07-26 and already written into
`specs/2026-07-25-unified-asset-catalog.md` §4c, but absent from the direction topic, so the
decision has no durable home yet. Proposed text, to be appended to the **Identity: content hash
where content exists, name where it does not** section (verbatim, awaiting a yes):

> **A texture's GROUP is a stored fact, not just a ref component.** UE1 subdivides a package with an
> optional Group, so a texture is addressed `Package.Name` or fully `Package.Group.Name`. Ref
> assignment emits the 2-part form unless there is an intra-package name collision, which means the
> group vanishes from the output for most textures — including `CoreTexMetal.LadrBrwnMetal`, whose
> group is the reserved `Ladder`. In Deus Ex the group is what decides whether a surface is
> climbable, so the catalog must be able to answer "which textures are ladders" directly: the group
> is stored as a per-texture fact, printed by `show`, and filterable with `--group` on
> `list`/`search`. It is a fact read from the package, never a classification, so it is not
> LLM-overridable — and it is **not** part identity, since identical pixels in two groups are
> deliberately one classifiable thing.
