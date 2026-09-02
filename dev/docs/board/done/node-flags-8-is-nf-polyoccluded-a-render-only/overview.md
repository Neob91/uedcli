+++
priority = "p3"
kind = "docs"
summary = "`node_flags=8` is `NF_PolyOccluded`, a render-only occlusion bit — NOT a build derivation gap; native correctly omits it"
+++

# `node_flags=8` is `NF_PolyOccluded`, a render-only occlusion bit — NOT a build derivation gap; native correctly omits it

RESOLVED` **`node_flags=8` is `NF_PolyOccluded`, a render-only occlusion bit — NOT a
build derivation gap; native correctly omits it.** DLL-confirmed 2026-07-18 (`sections/82` §10.11 +
§70 §9): `render.dll` sets `0x08` at `0x10019c26` and `0x10 NF_BoxOccluded` at
`0x100193db`/`0x10019526` (software-rasterizer occlusion walk, gated on the current camera's span);
`Editor.dll` — which holds the entire deterministic build (`csgRebuild`/`bspBrushCSG`/`bspRepartition`/
`bspRefresh`/`TestVisibility`) — sets NEITHER. The 598 saved `0x08` nodes are the editor's last
viewport-render leftover (camera-dependent, non-deterministic across saves). Confirmed-excluded, not
faked. Nothing to implement.
