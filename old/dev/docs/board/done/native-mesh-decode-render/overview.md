+++
priority = "p?"
kind = "unknown"
summary = "Native mesh decode + render — SPIKED 2026-07-25"
+++

# Native mesh decode + render — SPIKED 2026-07-25

(`spikes/2026-07-25-native-mesh-decode/`).
The complete UE1 `UMesh`/`ULodMesh` body decodes in pure Python, verified consume-to-exact-end on
**902 meshes** (466 retail Deus Ex v68 + 436 UED22 v69), and renders textured thumbnails offline —
no editor, no container, no `umodel.exe`. Five non-guessable findings pinned by
`tests/test_mesh_decode.py`: `FMeshAnimSeq.Group` is a single FName (not a TArray) and its
serialized order puts `Notifys` before `Rate`; `UMesh` re-serializes its own bounds inline while
per-frame bounds are plain TArrays; `SpecialVerts` sit at the FRONT of each frame (wedge indices
are relative to `frame_base + SpecialVerts`); the 5-byte `ULodMesh` tail is stock UE1, not a
licensee addition. Vertex stride (DX 8-byte int16 quad vs stock 4-byte packed dword) is
**self-describing** via the TLazyArray skip offset, so ONE decoder serves both — the generic-UE1
goal. Class thumbnails resolve skins from CLASS defaults (`MultiSkins[i]`), not the mesh's own
Textures array. **Remnants:** productise the harness into `uedcli/` (rides the asset-catalog
build); `RemapAnimVerts` element layout unverified (empty everywhere in the corpus).
