+++
priority = "p3"
kind = "debug"
summary = "A texture stored in the level's own package is rewritten to MyLevel. and then assembled as a package import the engine refuses. Latent — no shipped DX map does this."
+++

# Self-package rewrite turns a map-embedded texture into a bogus `MyLevel` import

`native/unbuilt.rewrite_self_package_refs` requalifies every occurrence of the level's own package
name to `MyLevel.`, including a brush poly's `Texture=`. For a texture stored inside the map package
itself (`03_NYC_UNATCOHQ.MyTex`) that yields `MyLevel.MyTex`, and `tex_ref` then takes its
`"." in name` branch and asks the resolver for `Texture'MyLevel.MyTex'` — which emits a package
IMPORT named `MyLevel`, exactly the "Can't import private object" failure the rewrite exists to
prevent. An intra-package texture needs an export ref, the way `_internal_ref` handles an intra-level
actor ref.

Not a regression: the T3D-text rewrite this replaced (in `apply._materialize`) produced the same
`MyLevel.MyTex`. Latent because no shipped Deus Ex map stores textures in the map package — found by
review, never observed. Filed rather than fixed because fixing it changes behaviour the owner has not
been asked about.

Found while moving the rewrite into `assemble_unbuilt`
(`editor-free-native-world-bsp-map-assembly`).
