# WanChai N=45, OceanLab N=93 and Island N=123 — one f32 rearrangement in the beam clip

**Result: three levels advanced, no parity-bar change.** Two open items turned out to be measurement
artifacts — nothing in `visible_surfs.rs` was ever wrong, and its box-occlusion path matches a live
UED22 capture call for call. The real bug was one line of f32 arithmetic in the permeating-light beam
clip: `FPoly::SplitWithPlaneFast` takes its crossing vertex from `FLinePlaneIntersection`, not from
an `alpha` between the two `PlaneDot`s, and the two disagree in the last ulps. Ported,
**WanChai N=45, OceanLab N=93 and Island N=123 all gate byte-exact**, and native's whole
`ActorVisibility` flood becomes identical to the live capture on every light of WanChai N=45.

## 1. "The gather still over-occludes 49 of 1218 box tests" — the probe measured half the decision

`gather-still-over-occludes-45-of-1218-box-tests` reported that after the zone-retire port native
runs the editor's exact 1218 box tests on OceanLab N=48 but 49 of 1173 shared tests disagree, every
one native-hidden/editor-visible, plus 45 native-only and 45 editor-only keys — read as span-buffer
over-fill and "the WanChai N=45 rasterizer family with a far smaller reproducer". Both halves are
artifacts of the comparison.

**The 45/45 split is a rounding artifact.** `compare_box_tests.py` keyed calls on `round(v, 2)` of
each light coordinate. One light's Y is the f32 `234.255005`: native's trace prints it
shortest-roundtrip as `234.255` (rounds to 234.25) and the gdb probe prints `%.9g` as `234.255005`
(rounds to 234.26). One light, two keys, all 45 of its calls counted twice. Keying on the f32 BITS
instead makes all 1218 keys match on both sides.

**The 49 disagreements compare native's answer to a different question.** `frame_probe_viewsides.py`
breaks at `render.dll 0x100193d7`, right after `URender::BoundVisible` returns. Under `bUseZones`
that return is only half the box-occlusion decision: `0x100193ba`'s `cmovne eax, 0` NULLs the
`FSpanBuffer*` argument (921 of the OceanLab capture's 1233 calls), so the callee cannot run the
span test at all, and `OccludeBsp` runs it itself afterwards — once per ACTIVE ZONE, at
`0x10019456`–`0x10019518`, reaching `0x10019526`'s `or byte [eax+0x37], 0x10` when every active
zone's `FSpanBuffer::BoxIsVisible` says no. Native's traced `visible` is the post-zone-loop answer;
the capture's `ret` is the pre-zone-loop one. Every zoned span rejection therefore read as "native
over-occludes".

`box_verdict_probe.py` (this spike) keeps the parent probe's IN/OUT dump and adds the three outcome
sites — `0x100193db` (geo), `0x10019526` (zone), `0x1001952f` (accept) — each printing the call's
`$hits`, so a verdict pairs with its call. An unzoned accept takes `0x10019450 je` and has no site of
its own; it is the only no-verdict case.

Re-measured against the real verdicts:

| level | box tests | keys matched | verdicts agreeing | same ORDER |
|---|---|---|---|---|
| OceanLab N=48 | 1218 / 1218 | 1218 | 1218 (791 accept, 373 geo, **54 zone**) | yes |
| WanChai N=45 | 207 / 207 | 207 | 207 | yes |

The 54 zone rejections are exactly the 49+5 "disagreements". Screen rectangles are identical
integer-for-integer on all 1218 OceanLab calls, and the whole test SEQUENCE matches, which also
exercises the traversal: near/far child choice, coplanar-chain walk, zone-mask prune, frustum-cone
reject and zone retire all reproduce the editor's own order.

## 2. WanChai N=45: `lmdiag.py` read `VClamp` where `iLightActors` is

`wanchai-n45-spotlight22-light-runs-differ-on-4` records four divergent lightmap runs (Spotlight22
over-included on surfs 6 and 54, missing on 37) and scopes the fix as a multi-day `FSpanBuffer`
rasterizer port. The four runs do not exist.

`FLightMapIndex` is `i32 DataOffset, f32 Pan[3], ci UClamp, ci VClamp, f32 UScale, f32 VScale,
i32 iLightActors` (`uedcli/native/umodel.py`), so `model_dump`'s per-record tuple is
`(raw16, u_size, v_size, tail12)` and the run start is the LAST i32 of `tail`. `lmdiag.py` walked
`Model.Lights` from field [2] — `VClamp`, a lumel count. With the real field, **native and UED22
agree on all 210 lightmap runs at WanChai N=45**, and the run membership then matches the gather
exactly: light189 gathered 121 surfs / 121 runs, Spotlight22 60 / 59, Spotlight21 35 / 35.

That inconsistency is what exposed the bug. A native trace of Spotlight22's gather
(`UEDCLI_VISGATE_TRACE_SURF=-1`, added here) never visits surf 6, 37 or 54 at all, yet the "runs"
listed Spotlight22 on 6 and 54 — and `light::bake` cannot list a light the gather omitted
(`gathered()` requires `visible_per_light[li].contains(&si)`). A run set that exceeds its own gather
set is impossible, so the decode had to be wrong.

**What actually blocks N=45.** `Model.Lights` is two arrays end to end — region 1, the per-leaf
permeating lists indexed by `FLeaf.iPermeating`, and region 2, the per-surf runs indexed by
`iLightActors` — and only region 2 was being compared. `leaf_perm_diff.py` (this spike) compares
region 1:

    leaves 91 91; Model.Lights 687 686
    leaf[20] zone=1  nat=(spotlight22, light189)  ued=(light189,)  extra=[spotlight22]
    differing leaves: 1 of 91

One over-included permeating light, in one leaf. That single extra `Model.Lights` entry shifts every
later `iLightActors` and `iPermeating` by one, which is the whole `BODY model model2` failure: all
210 lightmap records classify identically (same runs, same dark-vs-empty status), `LightBits` is
byte-identical, and leaf 20 is the only leaf whose content differs.

It is the known, documented `permeating_lights.rs` error shape — "the remaining ~4.6% are extra,
never missing, lights". OceanLab N=48 has 0 differing leaves and 0 differing runs, consistent with
it gating clean.

## 3. Root cause: the beam clip's crossing vertex came from the wrong f32 rearrangement

`actor_visibility_probe.py` (this spike) captures the editor's own flood — `Editor.dll 0x100a6d00`,
breaking at the entry convergence point `0x100a6edd` (leaf in `esi`), the mark allocation
`0x100a6f01`, and the recursive call `0x100a71c3` (target leaf and clipped beam on the stack).
`perm_flood_diff.py` diffs it against native's `UEDCLI_PERM_TRACE` log. On WanChai N=45, before the
fix: **10 of 11 lights identical, leaf for leaf and crossing for crossing**, and Spotlight22 differing
by three crossings — `(24, 25)`, and `(25, 20)`/`(20, 21)` below it. One root crossing: leaf 24 → 25,
which native takes and the editor does not.

Its inputs, from `UEDCLI_PERM_TRACE_EDGE=24-25` and the capture's own `AV_REC from=57 to=24`:

| | clip polygon entering leaf 24 |
|---|---|
| editor | `[1344,-512,-128] [1408,-512,-128] [1408,-861.19104,-128] [1343.99988,-896,-128] [1344,-896,-128]` |
| native | `[1344,-512,-128] [1408,-512,-128] [1408,-861.19104,-128] [1344,-896,-128]` `[1344,-896,-128]` |

One vertex: `1343.99988` against `1344.0`. That makes native's last clip EDGE zero-length, so
`clip_beam`'s `safe_normal` returns `None` and it **skips that constraint entirely** — the editor
still clips by the plane through it, and that plane is what would have cut the 24→25 face away.

The `1344.0` comes from native computing the crossing as `alpha = dp / (dp - ds)` between the two
`PlaneDot`s. `FPoly::SplitWithPlaneFast` does not: at `0x1015214b` it calls
`FLinePlaneIntersection` (`Engine.dll 0x101507c0`, disassembled here) with `P1 = Vertex[i-1]`,
`P2 = Vertex[i]`:

```text
D   = P2 - P1
Sc  = (W - ((P1.y*N.y + P1.x*N.x) + P1.z*N.z)) / ((D.x*N.x + D.y*N.y) + D.z*N.z)
out = Sc*D + P1
```

The same point in exact arithmetic — a different f32. The numerator is re-derived from `P1` rather
than reused from the classification pass, and the denominator dots the DIFFERENCE vector with the
normal where `dp - ds` subtracts two separately-rounded dots.

**Ported (`permeating_lights::line_plane_intersection`), all 11 WanChai N=45 lights become identical
to the capture** — every marked leaf, every crossing — and the level gates
`PARITY: YES`. It also closes **OceanLab N=93** and **Island N=123**, whose board items describe the
same one-extra-leaf shape. UNATCO N=226 and NYC_Bar N=153 still fail (see the table).

## What moved

| level | before | after |
|---|---|---|
| WanChai | byte-exact N=1..44, bailed at 45 | **N=45 PASSes** |
| OceanLab | byte-exact N=1..92, bailed at 93 | **N=93 PASSes** |
| Island | byte-exact N=1..122, bailed at 123 | **N=123 PASSes** |
| UNATCO | bailed at 226 | unchanged — still one extra permeating light, leaf 12 / `Light157`, a SECOND case of the same shape (`unatco-n-226-leaf-12-gets-a-permeating-light157`) |
| NYC_Bar | bailed at 153 | unchanged — its leaf region is clean (0/155); 3 per-surf records get `Light5` where UED22 is dark (`nyc-bar-n-153-world-model2-lightmap-runs-ued22`) |

Every level's previously-passing ceiling was re-gated after the fix and still passes (UNATCO 225,
OceanLab 92, Island 122, NYC_Bar 152, WanChai 44).

| item | before | after |
|---|---|---|
| `gather-still-over-occludes-45-of-1218-box-tests` | open, "span-buffer over-fill" | closed — measured, 0 divergences |
| `wanchai-n45-spotlight22-light-runs-differ-on-4` | parked, "multi-day rasterizer port, corpus-wide blast radius" | closed — the runs match; the real cause was the crossing-vertex rounding, now fixed |
| `island-n-123-world-model2-leaf-permeating-light`, `oceanlab-n-93-leaf-96-gets-a-permeating` | open | closed by the same fix |

## Pinned

- `permeating_lights.rs::tests::the_beam_clip_reproduces_the_editors_own_crossing_vertices` — the
  five crossing vertices the live capture shows the editor passing into WanChai leaf 24, compared on
  f32 BITS.
- `test_engine_facts.py::test_splitwithplanefast_takes_its_crossing_from_flineplaneintersection` —
  the call and the arithmetic, read out of `Engine.dll`.
- `test_engine_facts.py::test_flightmapindex_stores_ilightactors_as_its_last_i32` — the field order
  `lmdiag.py` got wrong.
- `test_engine_facts.py::test_the_box_occlusion_verdict_capture_pairs_each_call_with_its_outcome` —
  the committed capture's verdict tally, and that two spellings of one f32 must key alike.

## Files

- `harness/box_verdict_probe.py` — the box-occlusion outcome-site probe.
- `harness/actor_visibility_probe.py` — the `ActorVisibility` flood probe.
- `harness/perm_flood_diff.py` — diffs native's flood against that capture, light by light.
- `harness/leaf_perm_diff.py` — the per-leaf permeating-light differ (`Model.Lights` region 1).
- `logs/box-verdict-n48.log`, `logs/box-verdict-wanchai-n45.log`,
  `logs/actor-visibility-wanchai-n45.log` — the three captures.
- `2026-09-06-boundvisible-port/harness/parse_frame_probe.py` — parses the verdict lines and exposes
  `visible` / `has_verdicts`; `compare_box_tests.py` — f32-bit keys, compares `visible`, reports test
  order, warns on a capture that has no outcome sites.
- `2026-09-06-raster-clipbspsurf-port/harness/lmdiag.py` — the `FLightMapIndex` fix.
- `uedcli-native/src/permeating_lights.rs` — the fix, plus `UEDCLI_PERM_TRACE` /
  `UEDCLI_PERM_TRACE_EDGE`; `visible_surfs.rs` — `UEDCLI_VISGATE_TRACE_SURF=-1` traces every visited
  node and each zone retire; `light.rs` — `UEDCLI_VISGATE_DUMP` also lists every light's gather set.
