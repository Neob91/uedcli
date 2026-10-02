# OceanLab N=48's `LightBits` — the gather never retired an emptied zone

**Result: root-caused to a missing step in `URender::OccludeBsp` and fixed faithfully. OceanLab N=48
and UNATCO N=163 both gate byte-exact with no new mask.** Native's per-light visibility gather kept
descending after the editor had already abandoned the traversal, box-testing — and so
`NF_BoxOccluded`-marking — nodes the editor never reaches. `LIGHT APPLY`'s shadow ray reads that bit,
so the extra marks turned three `PF_BrightCorners` surfaces' edge lumels from lit to shadowed.

## The divergence

`ladder_run.py --dx 14_OceanLab_Lab.dx --from 48 --to 48 --force-ref` fails on `BODY model model2`
alone. Every geometry array is byte-exact; `harness/lightbits_diff.py` (new, in the ladder harness)
localises the whole 28-byte residual to **28 lumels over 3 lightmap records** — 182 (surf 194), 183
(surf 204) and 201 (surf 209) — all at `u = 0` or `u = 1`, the left edge of each grid, native `0`
(shadowed) against UED22's `1` (lit), and the same lumels for each of the three lights listed on the
surf.

All three surfs carry `PF_BrightCorners` (`poly_flags = 0x00880000`). That flag raises the shadow
ray's `ExtraNodeFlags` from `0x04` to `0x14`, and `FBspNode::IsCsg` tests `NodeFlags & (ExtraFlags |
0x21)` — so with `0x14`, a node carrying `NF_BoxOccluded` (`0x10`) stops being solid and stops
blocking light.

## Localising it to one node

An `UEDCLI_LC_PROBE_SURF` trace of `linecheck::line_clear`'s node path for surf 194's lumel `(0,1)`
walks `[0, 112, 267, 390, 416, 426, 510, 512, …]` and then blocks. Node **512** is the only node on
that path whose `NF_BoxOccluded` differs, and rebuilding with the box-occlusion replay disabled makes
all three records byte-exact — so the bit on node 512 is the whole divergence.

## What UED22 actually has at raytrace time

The SAVED reference package is not the answer: its `NF_BoxOccluded` set is `{32, 49, 80, 209, 289,
337, 352, 385, 433, 481, 497, 529}`, and the residue-1 half of that is written by the single
`DrawWorld` that fires AFTER the last light (the counter advances 0→1 there), which also RE-tests and
mostly clears the residue-0 marks the lighting pass left. Read the state at the moment the shadow
rays run instead — `2026-09-05-lightapply-node-flags-verification/harness/counter_and_flags_probe.py`
breaks at the first `illuminateSurf`:

    UED22 at the first illuminateSurf:  NF_BoxOccluded on {32, 80, 160, 352}   (all residue 0)
    native, same build:                 {32, 48, 80, 160, 208, 240, 256, 288, 336, 352, 384, 512}

The live dump's node indices line up with the saved `Model2` (`NumVertices` matches on all 559 nodes;
only 9 nodes differ outside `0x10`, all in `NF_PolyOccluded`, which the same later `DrawWorld`
rewrites).

## Why native marked eight extra nodes

`harness/frame_probe_viewsides.py` (this spike's copy of `2026-09-06-boundvisible-port`'s frame
probe, plus a `ViewSides` dump) captures every real `BoundVisible` call of the OceanLab N=48 golden
build. That spike's own `parse_frame_probe.py` + `compare_box_tests.py`, run against native's
`UEDCLI_VISGATE_TRACE_BOX` trace: **native ran 1458 box tests
to the editor's 1218, on EVERY light.** Per face, native's test list is the editor's plus a tail —
e.g. for the last light (`Light156`, actor 41) on face `+Z` the editor tests `0, 112, 416, 528, 544,
448, 464` and stops, while native continues into `496, 512, 352, 336, 288, 384, 160, 240, 208, 256,
48, 32`. Replaying native's trace light by light shows the marked set is `{32, 80, 160, 352, 496}`
after light 15 — one node off UED22 — and blows up to the twelve above during that last light's
over-long traversal.

## The missing step — zone retire (`render.dll 0x1001a737`–`0x1001a7e5`)

At the end of a node's ACCEPTED surface path, after the portal `MergeWith` loop, `OccludeBsp` reads
the near zone's `FSpanBuffer::ValidLines` (`+8`):

```text
0x1001a720  and  byte [node+0x37], 0xf7      ; clear NF_PolyOccluded
0x1001a737  mov  eax, [ebp-0x91c]            ; &SpanBuffers[near zone]
0x1001a73d  cmp  dword [eax+8], 0            ; ValidLines
0x1001a741  jg   0x1001a7eb                  ; still has area -> chain advance
0x1001a747..0x1001a796                       ; compact the active-zone list, drop this zone
0x1001a79c..0x1001a7dd                       ; clear its bit from the active zone mask
0x1001a7e3  test edx, edx
0x1001a7e5  je   0x100193f6                  ; no zone left -> END this face's traversal
```

Only the accepted path reaches it: a node whose buffer was already empty jumps straight to the chain
advance (`0x10019965 jle`), and a rasterized-but-fully-occluded one takes the `NF_PolyOccluded` exit
(`0x10019c26`). The active-zone mask is the same one step 1 prunes subtrees with, so once a zone
retires nothing below it is visited — and in the UNZONED pass the single buffer's retire empties the
list outright and ends the face.

`visible_surfs.rs` had no retire at all: `active_mask` only ever gained bits (portal crossings). With
the retire ported — `traverse` now returns "keep going", `false` unwinding the whole face —
**native's box-test count becomes exactly the editor's 1218 and its final `NF_BoxOccluded` set becomes
exactly `{32, 80, 160, 352}`.**

## Also ported here: the frustum-cone subtree reject (step 6)

`dev/docs/board/inbox/port-occludebsp-frustum-cone-subtree-reject/` was open against the same
function and is done in the same change (it is not what fixed N=48 — it removed one stray mark, node
544 — but it is the same traversal and was measured, not assumed):

- `render.dll 0x1001979b`–`0x10019884`: `sign = IsFront ? +1 : −1`, and the node is abandoned when all
  four `sign * (Node->Plane | Frame->ViewSides[k])` are `> 0`. `FPlane::operator|` (`core.dll
  0x10017d90`) is the 3-component dot, `W` excluded. The reject's `jmp 0x100193df` pops the node's own
  stack record — the one holding its FAR child — so it abandons this node's surface, the rest of its
  coplanar chain and the far child. The NEAR child is already done: the test sits on the resume path
  at `0x10019670`, after the near subtree has run. Chain MEMBERS skip it (`0x1001a934` re-enters at
  `0x100198a0`, past the test).
- `FSceneNode::ViewSides[4]` (`+0xfc`/`+0x108`/`+0x114`/`+0x120`) is built by
  `FSceneNode::ComputeRenderSize` (`Engine.dll 0x1013295d`–`0x101329fb`): a double loop over
  `S = {-1, +1}` writing slot `2*i + j` from the view-space corner `(S[i]*FX15, S[j]*FY15, Proj.Z)`,
  `UnsafeNormal`ised (`core.dll 0x1002e0c0`: `(X*X + Y*Y) + Z*Z` in f32, reciprocal square root at
  double precision) and then `TransformVectorBy(Uncoords)` (`core.dll 0x1002dd50`,
  `(V.X*A.X + V.Y*A.Y) + V.Z*A.Z` per axis) into world space. `FX15`/`FY15` are `+0xc8`/`+0xcc` —
  the same `512.0` `BoundVisible` projects about, not `+0xc0`'s `512.500061`.

The port reproduces all 24 live-captured `ViewSides` components on all six gather faces, to the
9 significant digits the probe prints — including the three distinct f32 values (`0.57735014`,
`0.577350199`, `0.577350259`) the editor's own rounding produces.

## What moved

| level | before | after |
|---|---|---|
| OceanLab | byte-exact N=1..47, bails at 48 | see the board item / `NATIVE-MATERIALIZE.md` |
| UNATCO | byte-exact N=1..162, bails at 163 | N=163 PASSes — same cause, verified by rebuilding both sides |
| NYC_Bar | bails at 153 | unchanged (still `model2` + `model_deusexmover9`; the mover body was already failing on master, checked by rebuilding N=153 against `HEAD`) |

## Nothing is left open — the residual this section used to claim was a measurement artifact

*(Corrected 2026-09-07, `dev/docs/spikes/2026-09-07-gather-box-verdict/`.)* This section reported
that after the fix the two sides ran 1218 tests each but disagreed on 49 of 1173 matched keys, with
45 native-only and 45 editor-only keys, and read that as span-buffer over-fill. Both halves were the
comparison's, not native's:

- `compare_box_tests.py` keyed calls on `round(v, 2)` of each light coordinate. One light's Y is the
  f32 `234.255005`; native prints it shortest-roundtrip as `234.255` and the probe prints `%.9g`, so
  one light became two keys and all 45 of its calls were counted on both sides.
- `frame_probe_viewsides.py` breaks after `URender::BoundVisible` returns, which under `bUseZones`
  is half the decision — `0x100193ba`'s `cmovne eax, 0` NULLs the `FSpanBuffer*`, and `OccludeBsp`
  runs the span test itself afterwards, per active zone. The 49 were exactly the zoned span
  rejections that capture cannot see.

With the outcome sites captured (`box_verdict_probe.py`) and an f32-bit key, native matches the live
editor on **all 1218 calls of OceanLab N=48 — same set, same order, same screen rectangles, same
verdicts** (791 accept, 373 geo, 54 zone), and likewise on all 207 of WanChai N=45.

## Pinned

- `visible_surfs.rs::view_sides_match_the_live_editor_gather_frames` — the 24 live components.
- `visible_surfs.rs::an_emptied_span_buffer_ends_the_unzoned_traversal` — `ValidLines` reaching 0
  after a full-screen subtraction, which is what the retire keys on.

## Files

- `uedcli-native/src/visible_surfs.rs` — the change.
- `harness/frame_probe_viewsides.py`; `2026-09-06-boundvisible-port/harness/parse_frame_probe.py`
  and `compare_box_tests.py` read its output.
- `logs/frame-probe-n48.log` — the live capture.
- `dev/docs/spikes/2026-09-03-incremental-actor-parity/harness/lightbits_diff.py` — the per-lumel
  `LightBits` differ.
