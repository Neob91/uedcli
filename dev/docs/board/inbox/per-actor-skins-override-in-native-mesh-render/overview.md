+++
priority = "p1"
kind = "implement"
summary = "Native mesh render honors a placed actor's own Skins[] override, not just class defaults"
depends-on = ["native-mesh-rendering-in-level-photo-native"]
+++

# Per-actor Skins[] override in native mesh render

`native-mesh-rendering-in-level-photo-native`'s v1 resolves skins only from the mesh's own
`Textures[]` and the actor's class defaults (`MultiSkins`/`Skin`) — the same chain
`uedcli/meshrender.py::resolve_skins` already uses for `class preview`. A placed actor instance that
overrides its own `Skins[]` (reskinned individually, distinct from its class) renders with the
class's default skin instead. Deferred out of v1 by owner ruling (2026-09-06), filed here at p1 so
it isn't lost.

Needs: read the actor's own `Skins[]` property (per material index) ahead of the class-default
chain in the mesh-instancing code the parent item adds.
