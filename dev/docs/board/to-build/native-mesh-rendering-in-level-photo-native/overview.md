+++
priority = "p2"
kind = "implement"
summary = "level photo --native renders DT_Mesh actors (decorations, items, weapons, characters), DX first"
+++

# Native mesh rendering in level photo --native

`level photo --native` renders BSP world geometry and mover polys but no `DT_Mesh` actors at all
today — decorations, items, weapons, characters render as nothing. Mesh decode is already solved
and in production (`uedcli/umesh.py`, substrate-generic for Deus Ex v68 and stock Unreal/UT v69;
`uedcli/meshfacts.py` resolves skins via mesh `Textures[]` / class `MultiSkins`/`Skin`, already used
by the asset-catalog class-thumbnail renderer). This item wires that into `--native`'s scene
composition so still shots show meshes, not just brushes.

See `spec.md`.
