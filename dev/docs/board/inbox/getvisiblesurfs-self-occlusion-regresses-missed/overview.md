+++
priority = "p2"
kind = "debug"
summary = "GetVisibleSurfs self-occlusion regresses missed pairs 7->1110, kept disabled"
depends-on = ["port-urender-getvisiblesurfs-so-each-light-gets"]
+++

# GetVisibleSurfs self-occlusion regresses missed pairs 7->1110, kept disabled

`visible_surfs.rs` (this session) ports the editor's per-light cube-map rasterization gather, but
with real opaque-surface self-occlusion (`SUBTRACT_OCCLUSION = true`) it OVER-occludes: on UNATCO,
extra (surf,light) pairs drop 618→189 (good) but missed pairs explode 7→1110 and per-record
byte-identical regresses 2518→2457/3345 — a net loss. Shipped instead with occlusion OFF
(zone-reachability + backface + frustum + `PF_Invisible` only): extra 618→447, missed 7→119,
byte-identical improves 2518→2557/3345. A real but partial gain — the light-run selection gap
(`port-urender-getvisiblesurfs-so-each-light-gets`) is NOT closed.

## Diagnostic evidence

`dump_debug_counters` (`UEDCLI_VISGATE_DUMP=1`) shows the "occluded by a nearer opaque surface"
rejection (`empty_after_test`) dominating by a wide margin when occlusion is on. Two candidate
causes, neither pinned:

1. This port's boolean-grid span buffer (near-to-far DFS order, painter's-algorithm accept/subtract)
   is not bit-identical to the real `FSpanBuffer` run-length scanline semantics
   (`CopyFromRaster`/`CopyFromRasterUpdate`/`MergeWith`, `render.dll 0x1001dd10`/`0x1001df70`/
   `0x1001e3b0` — undecoded past the functional description in the board item).
2. Native's own zone graph (6 zones on UNATCO) may be coarser or structurally different from the
   editor's, so screen-space occlusion computed against OUR zoning rejects surfaces the editor's
   zoning would still reach.

## Next step

Needs a live differential: dump per-face rasterized footprints for one light with a known missed
surface, compare pixel-for-pixel against a real editor capture (or narrow via `light_geomatch.py`-
style surface-by-surface attribution) to tell which of the two causes above is responsible before
re-enabling `SUBTRACT_OCCLUSION`.
