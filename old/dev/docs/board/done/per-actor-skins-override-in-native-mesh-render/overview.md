+++
priority = "p1"
kind = "implement"
summary = "Native mesh render honors a placed actor's own MultiSkins/Skin override, not just class defaults"
depends-on = ["native-mesh-rendering-in-level-photo-native"]
+++

# Per-actor MultiSkins/Skin override in native mesh render

Done. `meshrender.py::resolve_skins` now merges an actor's own stored `MultiSkins`/`Skin` ahead of
its class defaults (`ChainMap`, per texture slot), and reproduces the real engine's precedence
among `MultiSkins`/`Skin`/the mesh's own texture (RE'd, `dev/docs/spikes/2026-09-10-multiskin-skin-precedence/`,
recorded in `dev/docs/unrealed/rendering.md`). Also fixed a texture-cache collision
`preview_native.py::_TextureTable.index_for_decoded` would otherwise hit once skins vary per actor.

The keying-by-material-ordinal gap this surfaced (`resolve-skins-keys-by-material-ordinal-not`) is
also fixed, same day — `resolve_skins` now keys by the mesh's own texture index throughout.
