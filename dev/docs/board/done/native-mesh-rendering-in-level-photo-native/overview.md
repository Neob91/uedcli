+++
priority = "p2"
kind = "implement"
summary = "level photo --native renders DT_Mesh actors (decorations, items, weapons, characters), DX first"
+++

# Native mesh rendering in level photo --native

Done. `level photo --native` renders `DT_Mesh` actors (placement formula RE'd from
`UMesh::GetFrame`, `dev/docs/unrealed/mesh-transform.md`), and `--native` now errors strictly on
an unresolvable texture or mesh ref instead of a checkerboard placeholder. Reviewed in full,
including a whole-branch pass; verified against the real retail `01_NYC_UNATCOHQ.dx`.

Follow-ups: `per-actor-skins-override-in-native-mesh-render`,
`validate-native-mesh-render-against-stock`.
