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
per-lightmap runs differ:

| LightMap | surf | node | native run | UED22 run |
|----------|------|------|------------|-----------|
| 25 | 1 | 25-28 | `spotlight21, light189` | `light189` |
| 29 | 6 | 51 | `spotlight22, spotlight21, spotlight20, light189` | `spotlight21, spotlight20, light189` |
| 34 | 37 | 59 | *(empty)* | `spotlight22, light189` |
| 77 | 54 | 29 | `spotlight22, light189` | `light189` |

Three over-inclusions and one UNDER-inclusion (of BOTH lights). Run ORDER is right everywhere
(descending actor index); only membership differs.

Reproduce the table with
`dev/docs/spikes/2026-09-06-raster-clipbspsurf-port/harness/lmdiag.py <native.dx> <ref.dx>`. Do NOT
use `2026-09-03-incremental-actor-parity/harness/lightrun_diff.py`'s `surf=` column — it mis-decodes
`FBspSurf`, reading `iBrushPoly` as `iLightMap`; its run comparison is fine.

## The rasterizer is ported, and it is NOT the cause (2026-09-06)

The 2026-09-05 scoping below said the fix was `ClipBspSurf` + the fixed-point scanline rasterizer, a
2-4 day port. **That port is done and landed** (`dev/docs/spikes/2026-09-06-raster-clipbspsurf-port/`):
`URender::ClipBspSurf` (`0x10013cf0`), its clipper (`0x10013b70`), the per-vertex transform
(`0x1001adb0`) and the scanline setup (`0x1001b470`) are disassembled in full and reproduced —
including the editor's real six gather `FCoords`, the `OccludeBsp` point-list reversal, the
`appFloor`/`cvtss2si` semantics and the pre-increment in the edge walk.

**The four divergent runs are byte-for-byte unchanged by it.** WanChai N=45's own decision counters
move by 2 out of ~1300 (`rasterized` 1298→1299, `accepted` 893→893, span-rejected 405→406): the
empirically-tuned pixel-centre stand-in was already giving UED22's answer everywhere that matters.

Ruled out along the way:

- **The fill rule / clip / projection** — ported faithfully, no change.
- **`Surf->Texture->PolyFlags`** (which the editor ORs into `PolyFlags` at `0x10019aa9` and native
  cannot see) — none of the 25 textures the N=45 subset references carries any of the relevant bits
  (`harness/texflags.py`).
- **A flipped node ring** — measured 0 flipped nodes over three UED22 goldens
  (`harness/flipnodes.py`, `harness/ringwind.py`).

Fixed on the way (a real bug, not the cause here): the editor's `CopyFromRaster` vs
`CopyFromRasterUpdate` selector is `(PolyFlags & 0x10020047) != 0 && (PolyFlags &
(PF_Portal|PF_Invisible)) != (PF_Portal|PF_Invisible) && !(PolyFlags & PF_Mirrored)`; native read the
mask alone, so every `PF_Portal|PF_Invisible` zone portal was non-occluding where the editor
subtracts it.

## What is left: front-to-back ORDER

Traces (`UEDCLI_VISGATE_TRACE_SURF=37 UEDCLI_VISGATE_TRACE_LOC=1132.843140,-1010.845642,-150.857758`):

- For **spotlight22**, node 59 is `reachable=false` on all six faces — zone 1's span buffer is
  ENTIRELY drained (`ValidLines <= 0`) before the walk reaches it.
- For **light189** (`1574.907959,-705.968018,179.389343`), node 59 IS reached, rasterizes 208-403
  rows (~200k-380k px) and accepts ZERO — every pixel already claimed.

The three surfaces trade places consistently: native accepts 6 and 54 and rejects 37, UED22 does the
reverse. That is what an order swap between nodes 29/51 and 59 looks like — whoever is reached while
the buffer still has room wins. Candidates: the near/far child choice at their common ancestor, the
coplanar-chain `IsFront` re-derivation, or the `d > 0.0` vs `>= 0` boundary.

**Next step:** capture `OccludeBsp`'s node VISIT ORDER live for spotlight22 — break at `0x100198a0`
(the per-node filter re-entry) and log `iNode`, `IsFront` and the zone buffer's `ValidLines` — and
diff it against native's traversal. `2026-09-06-raster-clipbspsurf-port/harness/raster_probe.py` is a
working template (gdb attach, `render.dll` rebased through `/proc/<pid>/maps`, guarded breakpoint
command lists), but note its own failure mode: a breakpoint on a per-node hot path kills the editor
container. Arm the breakpoints only during `LIGHT APPLY` (a first breakpoint on its entry that
`enable`s the others) rather than capping the hit count.

## Reproduce

    .venv/bin/python dev/docs/spikes/2026-09-03-incremental-actor-parity/harness/actor_parity.py \
      --dx <maps>/06_HongKong_WanChai_Market.dx native 45
    .venv/bin/python dev/docs/spikes/2026-09-03-incremental-actor-parity/harness/body_token_diff.py \
      _scratch/actor-parity/06_hongkong_wanchai_market/native_N45.dx .../ref_N45.dx
