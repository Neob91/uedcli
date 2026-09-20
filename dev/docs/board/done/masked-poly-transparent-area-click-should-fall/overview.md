+++
priority = "p2"
kind = "bug"
status = "fixed"
summary = "a click on a masked poly's transparent texel selected the poly instead of falling through"
+++

# a click on a masked poly's transparent texel selected the poly instead of falling through

FIXED. `tapSelect.ts`'s new `isMeshHitTransparent` generalizes the existing point-actor sprite
alpha-picking mechanism (`isSpriteHitTransparent`) to the merged scene mesh (`meshObject`) and a
Mover's own solid mesh (`moverMeshObject`): a raycast hit on a masked (`alphaTest > 0`) poly whose
sampled atlas-canvas alpha is below the cutoff is dropped before ranking, falling through to
whatever's behind it (or a genuine miss) — same as the sprite case, combined into the same
`resolveTapSelect` filter. Unmasked polys (`alphaTest <= 0`, the overwhelming majority) are never
sampled at all. Regression: `tapSelect.test.ts`'s "masked-poly alpha-aware picking on the merged
mesh" suite (opaque/transparent/miss/unmasked/UV-wrap/Mover cases).
