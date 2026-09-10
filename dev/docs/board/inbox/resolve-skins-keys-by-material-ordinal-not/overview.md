+++
priority = "p3"
kind = "implement"
summary = "resolve_skins keys skins by material ordinal, not UMesh's own texture index"
+++

# `resolve_skins` keys by material ordinal, not `UMesh`'s own texture index

Found while RE'ing the `MultiSkins`-vs-`Skin` precedence for
`per-actor-skins-override-in-native-mesh-render` (`dev/docs/spikes/2026-09-10-multiskin-skin-precedence/`).

The real engine's `UMesh::GetTexture(Count, Owner)` indexes `MultiSkins[Count]`/`Textures[Count]` by
the mesh's OWN texture index (`URender::DrawLodMesh` loops `Count` over `Mesh->Textures.Num()`, and a
triangle separately maps its material to a `Count` via `Materials[tri.MaterialIndex].TextureIndex`).

`uedcli/meshrender.py::resolve_skins` instead loops over `mesh.materials` and keys its `skins` dict
by the MATERIAL list's own ordinal (`mi`, from `enumerate(mats)`), using `mats[mi][1]` (the
material's `TextureIndex`) only to look up the mesh's own texture, not as the `MultiSkins`/`skins`
dict key. This is pre-existing — predates the per-actor-override fix, which built on top of it
without changing it.

The two only diverge when a mesh's `Materials[i].TextureIndex != i` (a material's texture index
isn't equal to its own ordinal — plausible for meshes with multiple materials sharing one texture,
or texture/material lists in different orders). Not confirmed to matter for any mesh in the DX
corpus; not reproduced as a live bug. A faithful fix needs `resolve_skins`/its callers to key by
`Materials[i].TextureIndex` (the real `Count`) instead of the material loop ordinal, end to end
(the `skins` dict, the actor override merge, and `preview_native.py`'s triangle-to-skin lookup all
currently share the material-ordinal assumption).
