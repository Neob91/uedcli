# Porting `ClipBspSurf` + the scanline rasterizer — done, and it is NOT what blocks WanChai N=45

**Result: the gather's polygon pipeline is now a faithful port, and the WanChai N=45 divergence is
unchanged by it.** The board item
`inbox/wanchai-n45-spotlight22-light-runs-differ-on-4` scoped the fix as "the rasterizer, and it is
not small" (2-4 focused days). The rasterizer is now ported — `URender::ClipBspSurf`
(`render.dll 0x10013cf0`), its clipper (`0x10013b70`), the per-vertex transform (`0x1001adb0`) and
the fixed-point scanline setup (`0x1001b470`), all disassembled in full — and WanChai N=45 fails on
exactly the same four lightmap runs, with the same three over- and one under-inclusion. So the
scoping was wrong: the empirically-tuned pixel-centre stand-in was already producing the editor's
answer everywhere it mattered, and the real cause is somewhere else in the gather.

## What the disassembly says

The gather turns one BSP node into screen spans in two calls from `URender::OccludeBsp`:
`ClipBspSurf` (`0x10019987`) and the static scanline setup (`0x10019a6c`), with a point-list reversal
between them.

### Frame constants (live, `2026-09-06-boundvisible-port/logs/boundvisible-frame-probe.log`)

`X = Y = 1024`, `Proj.Z (+0xdc) = 511.999969`, the four clip slopes (`+0xec`…`+0xf8`) all
`1.00000012`. The polygon pipeline projects about `+0xc0`/`+0xc4` = `512.500061` — NOT `+0xc8`/`+0xcc`
= `512.0`, which is what `BoundVisible` uses. Two different centres on one frame.

The six gather frames' `FCoords` are `GMath.ViewCoords` (`XAxis=+Y, YAxis=−Z, ZAxis=+X`) turned by
the six rotators, e.g. the `+X` face is `XAxis=[0,1,0] YAxis=[0,0,−1] ZAxis=[1,0,0]`. `XAxis` is
screen right, `YAxis` is screen DOWN, `ZAxis` is the view direction. This used to be a free choice —
the old rasterizer was isotropic — and is not any more, because the real one fills scanlines.

### `URender::ClipBspSurf` (`0x10013cf0`)

Per vertex, `0x1001adb0` computes `P = V.TransformPointBy(Frame->Coords)` and four plane distances,
folded into an outcode through the byte tables at `0x10036af4`…`0x10036b00`
(`{0,0x04},{0,0x08},{0,0x10},{0,0x20}`, each bit set when `0 > dist`, strictly):

| bit | distance | slope field |
|------|-----------|---------|
| 0x04 | `Z*c + X` | `+0xec` |
| 0x08 | `Z*c − X` | `+0xf4` |
| 0x10 | `Z*c + Y` | `+0xf0` |
| 0x20 | `Z*c − Y` | `+0xf8` |

The AND over every vertex (seeded `0x3c`) rejects the node outright; the OR picks which planes get a
Sutherland-Hodgman pass, in that bit order. A vertex with a non-zero outcode is NOT projected
(`0x1001ae84`) — only fully-inside and clip-generated points carry `ScreenX`/`ScreenY`/`IntY`, which
is exactly the set that survives.

Projection: `RZ = Proj.Z/Z`, `ScreenX = X*RZ + 512.500061`, `ScreenY = Y*RZ + 512.500061`,
`IntY = appFloor(ScreenY)` — the engine's `appFloor(F) = appRound(F − 0.5)`, an SSE `cvtss2si`
(round-half-to-even) of `ScreenY − 0.5`.

The clipper (`0x10013b70`) keeps a vertex when its distance's SIGN BIT is clear: the editor compares
the float's raw bits as an INTEGER (`cmp dword ptr [...], 0; jl`), so `−0.0` is dropped and `+0.0`
kept, and it emits a crossing when consecutive sign bits differ (`xor; jge`), at
`alpha = d_prev/(d_prev − d_cur)` from `prev` toward `cur`.

`ClipBspSurf` also runs an optional near-plane clip against `Frame->NearClip` (`+0x24`) when its `W`
(`+0x30`) is non-zero. Not ported: `NearClip` is written by `CreateChildFrame` (portals and mirrors)
and the gather builds master frames only, so `W` is 0 for the whole pass. That one rests on the call
graph, not on a live read — see "What could NOT be obtained" below. Likewise `Frame->Mirror` (`+0x20`),
which the reversal below reads.

### The point-list reversal (`0x100199af`–`0x10019a34`)

`OccludeBsp` reverses the clipped list when
`(Frame->Mirror == −1) != (!IsFront && (PolyFlags & (PF_TwoSided|PF_Portal)))`. `Mirror` is `+1` on a
gather frame, so it reduces to the right half: a two-sided or portal surface seen from BEHIND its
plane — the only surface the back-face cull lets through from behind — is reversed.

That is load-bearing now. The scanline setup takes a row's `Start` from upward edges and its `End`
from downward ones, which is only right while the projected ring runs CLOCKWISE on screen (x right,
y down). Without the reversal a back-viewed two-sided poly would come out with `End <= Start` on
every row and `CopyFromRaster` would drop the whole surface.

### The scanline setup (`0x1001b470`)

`__cdecl f(FTransform** Pts, INT NumPts, FSpanBuffer* Span, INT Frame->Y)`:

1. Screen bounds: `MinY`/`MaxY` straight from `IntY`, `MinX`/`MaxX` from `appFloor(ScreenX)`, both
   accumulated as `if (v < min) … else if (v > max)`, not an independent min and max.
2. Y clamp: when `MinY < 0` or `MaxY > Frame->Y`, clamp both into `[0, Frame->Y]` **and rewrite every
   point's `IntY` to its clamped value and its `ScreenY` to `(float)IntY`**. When neither bound is
   out of range the whole pass is skipped and `ScreenY` keeps its fractional value — so a polygon
   that poked off the top or bottom of the screen has its edge slopes distorted by the rewrite and
   one that did not, does not. The asymmetry is the editor's.
3. `FSpanBuffer::BoxIsVisible` on that box, but only when the caller passed a span buffer, which it
   does only for a node already carrying `NF_PolyOccluded` (`0x10019a54`). Not ported: it tests the
   polygon's own bounding box against the same buffer `CopyFromRaster` is about to intersect with,
   so it can only reject where that intersection would have been empty anyway.
4. Edge walk over the ring `(last→first), (first→second), …`, skipping `A.IntY == B.IntY`. `P1` is
   the endpoint with the smaller `IntY`; `flag = (B.IntY > A.IntY)` picks the field, so a DOWNWARD
   edge writes `End` and an upward edge writes `Start`. In 16.16 fixed point:
   `DX = (X2−X1)*65536/(Y2−Y1)`, `X = appFloor(X1*65536 + DX*(IntY1 − Y1))`, `DXi = appFloor(DX)`,
   then for each row `y ∈ [IntY1, IntY2)`: **`X += DXi` FIRST, then store `X >> 16`**.

The pre-increment is not a misreading — `0x1001b725` is `add ecx, edi` and `0x1001b72f` the store
that follows it, in both the 4x-unrolled and the tail loop. Every row records the x one step DOWN
its own edge. Both edges of a row carry the same bias.

The float work is genuinely `f32`: `X1*65536` reaches ~2²⁶ for a right-edge vertex, where the f32
grid is 4 wide, so `appFloor` there discards low bits.

`CopyFromRaster` (`0x1001dd10`) then reads `FRasterSpan {INT Start, End;}` per row and skips a row
whose `End <= Start` (`0x1001de05`) — half-open, matching what `test_and_maybe_subtract` already
assumed.

### A second, unrelated bug the same routine exposed

`0x10019b4f`–`0x10019b9c` picks `CopyFromRaster` (no subtract) over `CopyFromRasterUpdate`
(subtract) as:

```text
no-subtract  iff  (PolyFlags & 0x10020047) != 0
               && (PolyFlags & (PF_Portal|PF_Invisible)) != (PF_Portal|PF_Invisible)
               && (PolyFlags & PF_Mirrored) == 0
```

`visible_surfs.rs` read only the mask. A zone portal is near-universally
`PF_Portal | PF_Invisible`, and `PF_Invisible` is inside the mask — so every zone portal was
non-occluding in native where the editor subtracts it like any opaque surface. Fixed with the rest
(`occludes`).

The editor also ORs `Surf->Texture->PolyFlags` in first (`0x10019aa9`). Native builds without
textures loaded and cannot see those bits. Ruled out as WanChai N=45's cause: every one of the 25
textures the N=45 subset references carries none of the relevant flags (`harness/texflags.py` over
`CoreTex*`/`HK_*`), so the OR is a no-op there. Still a real gap on other content.

## What the port changed, measured

`UEDCLI_VISGATE_DUMP=1` on a WanChai N=45 native build, before → after:

| counter | pixel-centre stand-in | faithful port |
|---|---|---|
| rasterized | 1298 | 1299 |
| accepted | 893 | 893 |
| dropped by the span test | 405 | 406 |

Two decisions out of ~1300 move. The empirically-tuned `x0 = ceil(lo−0.5)` / `x1 = ceil(hi−0.5)`
rule was, in practice, the editor's answer — which also means the port is not wildly wrong: a wrong
winding or a wrong screen basis would have moved thousands.

## Why N=45 is still blocked, and where to look next

Unchanged: `Model.Lights` 687 vs 686, four runs differing, three over- and one under-inclusion.

| LightMap | surf | node | native run | UED22 run |
|---|---|---|---|---|
| 25 | 1 | 25-28 | `spotlight21, light189` | `light189` |
| 29 | 6 | 51 | `spotlight22, spotlight21, spotlight20, light189` | `spotlight21, spotlight20, light189` |
| 34 | 37 | 59 | *(empty)* | `spotlight22, light189` |
| 77 | 54 | 29 | `spotlight22, light189` | `light189` |

(`harness/lmdiag.py`. NOTE: `2026-09-03-incremental-actor-parity/harness/lightrun_diff.py` mis-decodes
`FBspSurf` — it reads `iBrushPoly` as `iLightMap` — so its `surf=` column is wrong; the run
comparison itself is fine.)

Traces (`UEDCLI_VISGATE_TRACE_SURF=37`):

- For **spotlight22**, node 59 is `reachable=false` on all six faces — zone 1's span buffer is
  ENTIRELY drained (`ValidLines <= 0`) before the walk gets there.
- For **light189**, node 59 IS reached, rasterizes a huge footprint (208–403 rows, ~200k–380k px)
  and accepts ZERO of it — every pixel already claimed.

So native claims the whole screen with nearer surfaces where UED22 leaves node 59 a gap. Two
candidates ruled out, two still open:

- **Ruled out — the fill rule.** The port above.
- **Ruled out — texture `PolyFlags`.** No N=45 texture carries any.
- **Open — front-to-back ORDER.** The three surfaces trade places consistently: native accepts 6 and
  54 and rejects 37; UED22 does the reverse. That is what an order swap between nodes 29/51 and 59
  looks like — whoever is visited while the buffer still has room wins. Candidates: the near/far
  child choice at their common ancestor, the coplanar-chain `IsFront` re-derivation, or the
  `d > 0.0` vs `>= 0` boundary.
- **Open — an occluder native subtracts that the editor does not**, beyond the `occludes` rule now
  fixed.

The decisive next probe is a live capture of `OccludeBsp`'s node VISIT ORDER for spotlight22 —
break at `0x100198a0` (the per-node filter re-entry) and log `iNode`, `IsFront`, and the zone
buffer's `ValidLines` — and diff it against native's traversal. `harness/raster_probe.py` here is a
working template for exactly that (gdb attach, `render.dll` rebased through `/proc/<pid>/maps`,
breakpoint command lists guarded against bad pointers).

## The node-ring winding invariant, measured

`raster_setup` takes a row's `Start` from upward edges and its `End` from downward ones, so it needs
the projected ring to run clockwise on screen. Measured on the UED22 goldens for WanChai N=45,
UNATCO N=116 and NYC_Bar N=113 (`harness/ringwind.py`, `harness/flipnodes.py`):

- every one of 391 / 297 / 500 node rings winds WITH its own node plane (`FPoly::CalcNormal` vs
  `Node->Plane`), none against;
- every node's plane agrees in sign with its surf's `vNormal` — **0 flipped nodes**.

Together those give: light in front of the plane → ring clockwise on screen; behind → counter-
clockwise, and the only surfaces reachable from behind are two-sided/portal, which is exactly the set
`OccludeBsp` reverses. Two hand-built Rust fixtures
(`an_invisible_portal_still_propagates_visibility_into_its_far_zone`,
`coplanar_chain_is_walked_before_far_child_not_interleaved_with_it`) violated the invariant — their
walls carried a `+X` node plane with a `−X` `vNormal` and a `+X` ring — which the old isotropic
rasterizer could not notice. Both were corrected to the measured invariant, not to the code.

## Evidence the port itself is right

- Full disassembly of all four routines (above), plus the frame constants and the six real gather
  `FCoords`, both live-captured.
- `raster_setup_pre_increments_the_fixed_point_x_before_storing_each_row` — a hand-derived pin on a
  quad whose f32 arithmetic is exact at every step, so the expected `Start`/`End` come from the
  decoded formula rather than from the implementation. It fails for a truncating `appFloor` and for
  a "sample the row at its own scanline" walk.
- The ladder re-verification (`ladder_run.py --from 1 --to 116` over all five levels): every level
  bails at exactly the N it bailed at before, so no already-byte-exact build moved.

  | level | re-verified | bails at | blocker |
  |---|---|---|---|
  | Island | 1-9 | 10 | Brush1359 `Region` `iLeaf` (unchanged) |
  | WanChai | 1-44 | 45 | this item (unchanged) |
  | OceanLab | 1-45 | 46 | Brush1427 Bounds/LeafHulls (unchanged) |
  | NYC_Bar | 1-112 | 113 | Brush69 `Region` (unchanged) |
  | UNATCO | 1-32 | not reached yet | its own N=116 light-run item |

  UNATCO's leg was still walking when this landed — its per-N native build is the slowest of the
  five. Finish it with
  `ladder_run.py --dx <Maps>/03_NYC_UNATCOHQ.dx --from 33 --to 115` before trusting N=33-115.

- WanChai N=45's own decision counters move by 2 out of ~1300.

### What could NOT be obtained: a live rasterizer fixture

`harness/raster_probe.py` (committed, and a working template for the next probe) breaks at the
rasterizer's entry and exits and dumps `(points, Frame->Y) → (bounds, per-row Start/End)`. It does
not survive: the editor container dies shortly after gdb attaches, with no breakpoint output, on
four attempts (with and without a second breakpoint, with every read guarded, at 60 and 250 hit
caps). The site is orders of magnitude hotter than the `BoundVisible` call site the same machinery
handles fine — every node of every viewport paint passes through it — and gdb's stop-per-hit
overhead appears to be what kills it. A future attempt needs the breakpoint armed only during
`LIGHT APPLY` (e.g. a first breakpoint on the `LIGHT APPLY` entry that `enable`s the others), not a
smaller hit cap.
