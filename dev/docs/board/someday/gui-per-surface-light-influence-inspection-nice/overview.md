+++
priority = "someday"
kind = "feature"
summary = "GUI per-surface light-influence inspection (nice-to-have, not scheduled)"
+++

# GUI per-surface light-influence inspection (nice-to-have, not scheduled)

Owner ruling: nice-to-have (especially low priority per the owner's own words), log it, don't
build now. "Which lights hit this face" — UED22's lighting bake computes per-surface
contributing-light lists internally (`Model.Lights`/`iLightActors`, RE'd extensively in
`NATIVE-MATERIALIZE.md`); the GUI only ever shows the final baked lightmap texture. Needs a new
endpoint exposing internal bake data plus UI (large scope) — see the UED22-viewing-features
survey this item came from.
