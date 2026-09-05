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

## Scoping pass (2026-09-05) — the fix is the RASTERIZER, and it is not small

### 1. What native already has, and what it structurally lacks

`visible_surfs.rs`'s module doc calling `SpanBuf` "a per-zone boolean pixel grid" is **STALE**. It is
already run-length: `rows: Vec<Vec<(i32, i32)>>`, one sorted disjoint interval list per scanline. So
most of the "port `FSpanBuffer`" work is already done:

| Editor op | native | state |
|-----------|--------|-------|
| `CopyFromRaster` `0x1001dd10` (accept, no subtract) | `test_and_maybe_subtract(.., subtract=false)` | present |
| `CopyFromRasterUpdate` `0x1001df70` (accept + subtract) | same, `subtract=true`, selected on `PolyFlags & 0x10020047` (`0x10019b57`) | present |
| `MergeWith` `0x1001e3b0` (portal zone crossing) | `merge_into` | decoded + live-verified vs 10 real calls, Rust-tested |
| `ValidLines` (`FSpanBuffer+8`, tested `<= 0` at `0x10019961`) | `SpanBuf::valid_lines` | equivalent: editor counts interval NODES, native counts non-empty ROWS; both zero iff empty, and `> 0` is the only predicate read |

What is genuinely missing is **the rasterizer**: `ClipBspSurf` (`0x10019987`) + the scanline setup at
`0x1001b470`. Native substitutes an f32 Sutherland-Hodgman clip against four side planes followed by
a per-scanline min/max with pixel-centre inclusion (`x0 = ceil(lo-0.5)`, `x1 = ceil(hi-0.5)`). Also
unported: step 4 render-bound occlusion (`BoxIsVisible`, `0x1001932c`/`0x10019725`) and step 6's
frustum-cone reject (`0x100197b8`-`0x10019884`), and FOV=90 is an assumption, not a pinned fact.

### 2. It is maximally load-bearing

`UEDCLI_VISGATE_DUMP=1` counters on builds that are **byte-exact today**:

| build | rasterized | accepted | dropped by span test | pruned "zone buffer dry" |
|-------|-----------|----------|----------------------|--------------------------|
| WanChai N=44 (PASS) | 1120 | 769 | 351 | 19740 |
| UNATCO N=24 (PASS) | 486 | 389 | 97 | 182 |
| OceanLab N=16 (PASS) | 784 | 556 | 228 | 1297 |
| WanChai N=45 (FAIL) | 1298 | 893 | 405 | 21504 |

Every one of those already produces UED22's answer. Changing the fill rule moves all of them at once
— a far wider blast radius than the pruned-descent swap, which only touched point dedup. Worse, the
current pixel-centre rule was chosen EMPIRICALLY (`getvisiblesurfs-wanchai-run-gap-root-cause`:
WanChai byte-identical lighting records 71.3% -> 72.8%), not derived, so the faithful rasterizer has
to beat a tuned baseline on every level simultaneously.

### 3. Estimate: multi-day, do not attempt inside a ladder pass

Decode + bit-exact port of `ClipBspSurf` + the fixed-point scanline setup, then re-validation across
all five ladder levels AND the standalone lighting corpus (`parity_report.py`) to prove no net
regression: realistically **2-4 focused days**, high variance, with a real chance of an intermediate
state worse than today's 72.8%. Not something to force into a ladder pass.

**Cheaper partial, if a bounded step is wanted:** port step 4 (`BoxIsVisible` render-bound occlusion)
alone. It is a CONSERVATIVE reject, so it can only REMOVE surfs from native's set — the right sign
for three of the four diffs above, where native over-includes. It cannot fix `LM[34]`'s
under-inclusion, so it does not unblock N=45 on its own.

## Reproduce

    .venv/bin/python dev/docs/spikes/2026-09-03-incremental-actor-parity/harness/actor_parity.py \
      --dx <maps>/06_HongKong_WanChai_Market.dx native 45
    .venv/bin/python dev/docs/spikes/2026-09-03-incremental-actor-parity/harness/body_token_diff.py \
      _scratch/actor-parity/06_hongkong_wanchai_market/native_N45.dx .../ref_N45.dx
