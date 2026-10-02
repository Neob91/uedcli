+++
priority = "p3"
kind = "feature"
summary = "v61 world-model (Nodes/Surfs/Verts) recursive decode not built"
+++

# v61 world-model (Nodes/Surfs/Verts) recursive decode not built

`native.umodel.parse_model_body`'s v61 (original 1998/Gold Unreal) branch
(`dev/docs/spikes/2026-09-11-unreal-gold-v61-model-format/`) records the `Vectors`/`Points`/
`Nodes`/`Surfs`/`Verts` object refs on a v61 `UModel` but does not recursively decode the exports
they point at — each is its own `UDatabase`-subclass export (`None`-terminated property list,
`i32 DbNum, DbMax`, then `DbNum` elements; `UBspNodes`/`UVerts` also carry a trailing `NumZones`+
`Zones[]` / `NumSharedSides` field). `brush_of` (the only current production reader) never needs
them — it only wants a brush's authored `Polys`.

Needed only if `level import` is later extended to reproduce a v61 map's BUILT BSP (the WORLD
model's Nodes/Surfs/Verts, not just each brush's authored polygon list) — nothing in the pipeline
calls for that today. `FBspNode`/`FBspSurf`'s v61 field layout also differs subtly from the ver>61
one this codebase already decodes (`iZone`/`NumVertices` are raw `BYTE`s, not compact indices —
`fgsfdsfgs/UE1`, `Engine/Inc/UnObj.h`), unverified against real data since nothing exercises it yet.
