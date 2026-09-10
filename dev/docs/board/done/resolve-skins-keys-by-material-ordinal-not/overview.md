+++
priority = "p3"
kind = "implement"
summary = "resolve_skins now keys MultiSkins/Skin by UMesh's own texture index, not material ordinal"
+++

# `resolve_skins` keys by `UMesh`'s own texture index, not material ordinal

Done. Was not cosmetic: confirmed live on `DeusExCharacters.GM_Trench` (Joseph Manderley) —
materials 3-6 of 7 have `TextureIndex != their own ordinal`, so the old keying gave each a
neighboring material's skin, visibly wrong on render. Rewritten: `resolve_skins` resolves once per
texture index a material actually references, then re-keys by material via its own `TextureIndex`.
Pinned by `test_resolve_skins_keys_multiskins_by_texture_index_not_material_ordinal`
(`uedcli/tests/test_meshrender.py`), verified to fail under the reverted (ordinal-keyed) code.
