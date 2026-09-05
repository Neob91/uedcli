+++
priority = "p1"
kind = "debug"
summary = "WanChai N45 spotlight22 light runs differ on 4 lightmaps"
+++

# WanChai N45 spotlight22 light runs differ on 4 lightmaps

The lockstep ladder's next stop after WanChai N=44. Blocks N>=45 on that level.

## What diverges

Actor 45 is `Spotlight22` (`LightCone=90`, `LightRadius=32`, `Rotation=(Pitch=-15280)`,
`Location=(1132.84, -1010.85, -150.86)`). Actors 43/44 are its siblings `Spotlight20`/`21` and both
gate clean, so this is not "spotlights are unmodelled".

The whole `Model` matches except `Model.Lights`: native 687 entries, UED22 686, and exactly FOUR
per-lightmap runs differ (`_scratch/lightrun_diff.py` in this session's scratch; the walk is 20 lines
over `parity_gate`'s `Ident`):

| LightMap | surf | native run | UED22 run |
|----------|------|------------|-----------|
| 25 | 1 | `spotlight21, light189` | `light189` |
| 29 | 6 | `spotlight22, spotlight21, spotlight20, light189` | `spotlight21, spotlight20, light189` |
| 34 | 37 | *(empty)* | `spotlight22, light189` |
| 77 | 54 | `spotlight22, light189` | `light189` |

Three over-inclusions and one UNDER-inclusion. Run ORDER is right everywhere (descending actor
index); only membership differs.

## Cause: the known `GetVisibleSurfs` span-buffer residual

`UEDCLI_VISGATE_TRACE_SURF=37 UEDCLI_VISGATE_TRACE_LOC=1132.843140,-1010.845642,-150.857758` on a
native N=45 build reports, on every one of the six cube faces:

    VISGATE_TRACE node=59 surf=37 near_zone=1 reachable=false front_ok=true ...
    VISGATE_TRACE result: surf 37 REJECTED

So the surf is back-face-OK and in the view zone; it is dropped because **zone 1's span buffer is
already exhausted** by the time the traversal reaches node 59. That is the residual
`visible_surfs.rs`'s own module doc names: the port models `FSpanBuffer` as a boolean pixel grid and
skips the frustum-cone reject and render-bound occlusion, so accept/subtract areas differ at the
margins. Same family as `done/zone-crossing-getvisiblesurfs-gap-invisible` and
`done/getvisiblesurfs-self-occlusion-regresses-missed`.

## What the faithful fix needs

The pieces the original decode left open (board
`to-build/native-materialize/port-urender-getvisiblesurfs-so-each-light-gets`, "Still to decode for
bit-exactness on marginal cases"): `FSpanBuffer::CopyFromRaster` (`render.dll 0x1001dd10`),
`CopyFromRasterUpdate` (`0x1001df70`) and `MergeWith` (`0x1001e3b0`), plus the scanline rasterizer
(`0x1001b470`). Porting those run-length semantics in place of the boolean grid is the way to close
this class — not a per-case adjustment.

## Reproduce

    .venv/bin/python dev/docs/spikes/2026-09-03-incremental-actor-parity/harness/actor_parity.py \
      --dx <maps>/06_HongKong_WanChai_Market.dx native 45
    .venv/bin/python dev/docs/spikes/2026-09-03-incremental-actor-parity/harness/body_token_diff.py \
      _scratch/actor-parity/06_hongkong_wanchai_market/native_N45.dx .../ref_N45.dx
