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

## `CopyFromRaster`/`CopyFromRasterUpdate` decoded 2026-08-29 (cause 1 narrowed, not closed)

Both disassembled (`render.dll 0x1001dd10` / `0x1001df70`, `rdis.py dis Render <addr> <len>`).
**`FSpanBuffer` is NOT a pixel grid** — each row (`Index[y]`, `y` in `[StartY,EndY)`) is the head of
a sorted, disjoint singly-linked list of 12-byte interval nodes `{X0: i32 @0, X1: i32 @4, Next: ptr
@8}`, heap-allocated via `FMemStack::PushBytes(this->Mem /* @+0x10 */, 0xc, 4)`. This port's boolean
per-pixel grid (`visible_surfs.rs`'s `SpanBuf`) is a DIFFERENT representation, only assumed
behaviorally equivalent — cause 1 above is therefore plausible, not just "maybe."

**`CopyFromRaster(this, Update, Y1, Y2, Spans)`** (read-only, used for masked/translucent/non-
occluding surfaces): rows outside `[Y1,Y2)` get zeroed in `this`. For `y` in `[Y1,Y2)`: `Update`'s
row list at `y` (the caller's per-row rasterized footprint, walked as a proper sorted interval
list, NOT a simple bounding span) is intersected against `Spans[y]` (a flat `[X0,X1)` pair array,
8-byte stride, `arg4`) — skip nodes entirely left of `Spans[y].X0`, clip the first overlapping node's
left edge to `Spans[y].X0`, accept subsequent nodes UNCLIPPED as long as their `X1 <= Spans[y].X1`,
clip and STOP at the first node whose `X1` exceeds `Spans[y].X1` (relies on the list being X-sorted
and disjoint — a single per-row clip window can only ever intersect one contiguous run). Every
accepted/clipped node is pushed as a NEW node onto `this`'s row list (`this` starts row-empty here,
so this REPLACES, not merges). Returns `this->ValidLines` incremented at least once (i.e. "was
anything written") as the accept/reject boolean.

**`CopyFromRasterUpdate`** starts with a bounds check native's `CopyFromRaster` doesn't have
(`this->StartY <= Y1 && this->EndY >= Y2`, else early-out) — `this` here must ALREADY span the
range, i.e. `this` is the PERSISTENT buffer (not fresh scratch), consistent with "subtracts its
spans" being an in-place edit of the caller's own long-lived span state. Same per-row walk/clip
structure as `CopyFromRaster` as far as decoded (cut off mid-function, "the removal" half — the code
after the first accepted-node push — not yet traced).

**Implication for a fix:** a faithful port likely needs `visible_surfs.rs`'s `SpanBuf` rewritten as
a per-row sorted interval list (mirroring the real struct) instead of a boolean grid, so the
accept/clip/stop-at-first-right-edge-overshoot logic above can be ported directly rather than
approximated. `MergeWith` (`0x1001e3b0`, the portal-merge-into-far-zone operation) and
`CopyFromRasterUpdate`'s removal half are still undecoded.
