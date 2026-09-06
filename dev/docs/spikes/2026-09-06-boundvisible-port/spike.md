# Porting `URender::BoundVisible` — UNATCO N=26 closed, faithfully

**Result: the box-occlusion visibility test is ported, and UNATCO's ladder moves from N=25 to N=28
with no new mask** (N=1..28 all gate byte-exact; the walk now bails at N=29 on an unrelated world
`Model2` body diff). `dev/docs/board/done/port-urender-boundvisible-box-occlusion-test/` is the task;
the two 2026-09-05 `lightapply-node-flags` spikes are the diagnosis this builds on.

## Why the test had to be ported at all

`URender::OccludeBsp`'s render-bound step writes `NodeFlags |= NF_BoxOccluded (0x10)` when a node's
box is not visible, and that bit PERSISTS in `Model.Nodes`. `LIGHT APPLY`'s shadow-ray walker reads
it: `FBspNode::IsCsg` is `NumVertices > 0 && (NodeFlags & (ExtraNodeFlags|0x21)) == 0`, and a
`PF_BrightCorners` surface's rays pass `ExtraNodeFlags = 0x14`, so a marked node stops occluding at a
crossing. UNATCO N=26's whole divergence was one such node (UED22 listed `Light155` on three
`Brush420` surfaces; native, whose nodes were all zero, blocked all 341 rays).

The bit itself is excluded from the parity gate's byte compare. What is compared — the lightmap — is
not.

## What the live probe pinned

`harness/boundvisible_frame_probe.py` breaks at the call site (`render.dll 0x100193d5`) and right
after it, dumping the `FSceneNode` fields `BoundVisible` reads, the `FBox`, the `FSpanBuffer*`, the
return value and the `FScreenBounds` written. One full UNATCO N=26 golden build
(`logs/boundvisible-frame-probe.log`, 229 calls, 225 of them from the gather):

| fact | value |
|---|---|
| gather viewport | `X = Y = 1024`, `FX = FY = 1024` |
| projection centre `BoundVisible` uses (`FSceneNode+0xc8`/`+0xcc`) | `512.0` — NOT `+0xc0`'s `512.500061` |
| `Proj.Z` (`+0xdc`) | `511.999969` (`0x43ffffff`) |
| the four clip slopes (`+0xec`…`+0xf8`) | all `1.00000012` (`0x3f800001`) |
| `FSpanBuffer*` argument | NULL exactly when `Frame->ZoneNumber != 0` (36 of 225 calls) |
| nodes box-tested | 0, 16, 32, 48, 64 only — the `iNode % 16 == 0` residue, as predicted |
| node 48's final gather verdict | `ret = 0` → `NF_BoxOccluded` — the N=26 divergence, measured directly |

The editor's own six gather frames use a different in-plane axis pair from this port's `Face`
(face 0 is `XAxis = +Y`, `YAxis = +X`, where the port has `right = +X`, `up = −Y`). That is a rigid
90°/reflection relabelling of the same square screen: the box rectangle and the span content it is
tested against move together, so accept/reject is unchanged.

## The algorithm (`render.dll 0x10012100`, 0x1bf0 bytes, disassembled in full)

1. `Min`/`Max` relative to `Frame->Coords.Origin`. A "region" code sums `+1`/`+2` (X), `+3`/`+6` (Y),
   `+9`/`+0x11` (Z — the editor's own asymmetric constant); `0` means the origin is inside the box,
   which returns the full screen at once, without consulting the span buffer.
2. Reject when all six `ZAxis.c * Min.c` / `ZAxis.c * Max.c` products are negative (whole box behind
   the camera).
3. Per corner (bit 0 = X, 1 = Y, 2 = Z selects `Max`), view-space `(X, Y, Z)` as `(ax + ay) + az`,
   then a 4-bit outcode: `clip*Z + X < 0`, `clip*Z − X < 0`, `clip*Z + Y < 0`, `clip*Z − Y < 0`.
   Reject when the AND over all 8 corners is non-zero.
4. Screen rect: corner 0 seeds min = max; each bit set in the OR of the outcodes REPLACES that seed
   with the screen edge (0 or `Frame->X`/`Y`); corners 1..7 then extend it with the editor's
   `else if` shape, not an independent min/max. `FScreenBounds` clamps to `[0, X] × [0, Y]` and
   carries `max(min corner Z, 0)`.
5. `FSpanBuffer::BoxIsVisible` (`0x1001dc10`) on the UNCLAMPED rect — but only in the unzoned pass.
   With zones the CALLER (`0x10019456`–`0x10019518`) runs it per ACTIVE zone whose bit is in the
   node's `ZoneMask`, on the clamped `FScreenBounds`, and one hit is enough.

`BoxIsVisible` itself: clamp `[Y1,Y2)` into `[StartY,EndY)`, and answer yes at the first still-
unclaimed span in any of those rows that overlaps `[X1,X2)`.

## Evidence the port is right

- `uedcli-native/testdata/boundvisible_live_calls.csv` — all 225 gather calls as
  `(view FCoords, FBox) → (ret, FScreenBounds, exit path)`. The exit path comes from a breakpoint on
  each exit's own stat-counter `inc`, which turns every row into a two-way pin: 83 `outcode` rows
  must be rejected by geometry alone, and the other 142 (`inside` 48, plain `accept` 87, `span` 7)
  must be accepted with that exact rectangle — the editor writes `FScreenBounds` before consulting
  the span buffer, so even its span rejects pin a rectangle. Rust test
  `bound_visible_matches_the_real_editor_on_every_live_call`: **225 of 225 rows match**, first try.
  (`depth` never fires on this level's boxes.)
- `harness/compare_box_tests.py` diffs a native build's `UEDCLI_VISGATE_TRACE_BOX` trace against the
  live capture, matched on (light origin, view forward, node). **225 of 225 shared tests agree**,
  including node 48's reject and node 0/16/32/64's accepts.
- `harness/compare_light_order.py`: `NF_BoxOccluded` is last-write-wins across lights, so the replay
  depends on native baking lights in UED22's order. A single-threaded native build
  (`RAYON_NUM_THREADS=1`, so the trace order is the slice order) matches the live capture's light
  sequence **12 for 12**.
- `harness/node_flags_dump.py` on the built packages: native now carries `NF_BoxOccluded` on node 48.
- `ladder_run.py --dx 03_NYC_UNATCOHQ.dx --from 1`: N=1..28 PASS, bails at N=29.

## The one gap left: step 6, the frustum-cone subtree reject

Native runs 276 box tests where the editor runs 225. The 51 extra are on subtrees the editor never
reaches, because `visible_surfs.rs` still does not port `OccludeBsp`'s step 6 — the frustum-cone
reject at `render.dll 0x100197b8`: with `sign = IsFront ? +1 : −1`, pop the node when all four
`sign * (node->Plane | Frame->ViewSides[k])` are `> 0`. Native descends instead, and box-tests nodes
the editor's traversal already discarded.

Consequence today: native marks node 64 `NF_BoxOccluded` where UED22 leaves it clear. It changes no
lightmap at N=26 (the gate passes) and the bit is gate-excluded, but it is a real divergence.
Board item: `dev/docs/board/inbox/port-occludebsp-frustum-cone-subtree-reject/`.
