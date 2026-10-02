# WanChai N=201 — world Model2 LightMap[354] (surf 616) dark vs empty-run

Closes investigation for `dev/docs/board/inbox/wanchai-n-201-world-model2-body-diverges/` (not yet
fixed — see Status). WanChai was byte-exact N=1..200 after the N=59 repartition-frontier fix landed
2026-09-14; bails at N=201 on `BODY model model2: canonical bodies differ`.

## The actor

Trunk actor 201 = `Brush1164`, `CsgOper=CSG_Subtract`, a small decorative sign/awning frame (three
`2DLoft*` polys). Its Item=2DLoftSIDE face becomes world surf 616 (`node_dump.py`/`lmdiag.py`:
`nat surf 616: flags=0x0 actor=brush brush1164 nodes=[774]`), texture
`nycbar.wood.boathousewood_b`, base `(-533.6, 1408.0, 370.67)`, normal
`(-0.6594, -5.8e-8, -0.7518)` — a thin diagonal quad, one edge of a subtraction cut.

## The precise divergence (not a guess from the raw byte diff)

`body_token_diff.py`: the only real content difference is `Model.Lights`, count 2019 (native) vs
2020 (UED22). `lmdiag.py` localizes it to LightMap record 354 (surf 616):

    nat=dark            (DataOffset=0, iLightActors=-1 — no run allocated at all)
    ued=()              (an EMPTY run — allocated, zero lights survived the raytrace)

`leaf_perm_diff.py` confirms `Model.Lights` region 1 (per-leaf permeating lists) is byte-identical
(0 differing leaves) — the whole divergence is region 2, the per-surf gather (`light::bake`'s
`gathered()` predicate deciding whether >=1 light even earns this surf a lightmap slot at all,
`finalize_offsets`'s dark-vs-empty-run split, per the WanChai N=8 fix already on file).

## Root cause, pinned to the mechanism (not yet to the exact byte)

`gathered()` has 4 filters: special_lit match, backface (`light_in_front`), `GetVisibleSurfs`
membership, and perpendicular plane-distance <= `WorldLightRadius`. Checked against every light in
the N=201 subset (`harness/lm354_candidates.py`, fed native's own `UEDCLI_VISGATE_DUMP=1` light
list): **8 lights** pass special_lit+front+plane-distance (li 25,26,31,32,34,35,38,67), so `dark`
can only be correct if `GetVisibleSurfs` (`visible_surfs.rs`) genuinely rejects surf 616 for ALL of
them. Native's own `visible_per_light` sets confirm this: surf 616 appears in **zero** of the 68
lights' gathered sets (`UEDCLI_VISGATE_DUMP=1`, grepped for `, 616` — no hits).

**Live gdb capture of the REAL editor settles which side is right.** Reused
`dev/docs/spikes/2026-09-13-nycbar-n153-mover-occlusion/harness/raster_order_probe.py` unmodified
(breakpoint `render.dll 0x10019c1c`, `OccludeBsp`'s raster-commit accept/reject test, in VISIT
ORDER, for the whole `LIGHT APPLY` run) against the N=201 subset trunk. Grepping the capture for
`isurf=616` finds it hit 4 times; one hit is decisive:

    V hit=9632 isurf=616 edi=1 origin=-1160.745361,-807.899902,220.417908 zaxis=0,0,-1

`edi=1` (non-zero) = **ACCEPTED** — the real editor's raster-commit test for `Light431`
(`loc=(-1160.745361,-807.899902,220.417908)`, li=38 in the candidate list above), looking straight
down (`zaxis=(0,0,-1)`), finds surf 616 NOT fully occluded. So UED22's `GetVisibleSurfs` really does
include surf 616 for `Light431` — `dark` is native's bug, not a UED22 anomaly.

**Native's own trace for the same light pins WHERE it diverges**, not just that it does
(`UEDCLI_VISGATE_TRACE_SURF=616 UEDCLI_VISGATE_TRACE_LOC=-1160.745361,-807.899902,220.417908`, the
`visible_surfs.rs` trace already wired in for this exact purpose):

    node=774 surf=616 near_zone=1 reachable=true front_ok=true poly_flags=0x0
    node=774 rasterized rows=22 raster_px=59 accepted_px=0 opaque=true

Node 774 (surf 616) DOES get reached, DOES rasterize to a real (if tiny — 22 rows, 59px) footprint
on this exact face, and then gets **zero accepted pixels**: every row's span-buffer window is
already fully claimed by earlier-visited opaque surfaces on this face by the time node 774 is
tested (`buf_row=[]` for every one of its 22 rows). The last large occluder visited on this face
before node 774 is **node 776 / surf 2**, `poly_flags=0x400080` (`PF_Unlit | PF_FakeBackdrop`) — a
sky/backdrop polygon, `rasterized rows=84 raster_px=21685 accepted_px=7020`.

**Not chased to an exact byte-level cause.** `PF_FakeBackdrop` (0x80) is not in
`visible_surfs.rs::occludes`'s `PF_NONOCCLUDING` mask (0x1002_0047, disassembly-verified against
`render.dll 0x10019b57`), so native correctly treats it as opaque per the ported mask — the
divergence, if it traces to node 776 at all, would have to be a rasterization-FOOTPRINT precision
difference (native's `clip_bsp_surf`/`raster_setup` claiming a slightly wider screen-space window
for node 776, or an equivalent difference for one of the other ~40 occluding nodes on this face,
narrowing a razor-thin gap the real renderer leaves open) — not a wrong-flag or wrong-order bug.
Pinning that exactly needs single-stepping `raster_setup`'s own per-pixel scanline setup
(`render.dll 0x1001b470`), which `2026-09-06-raster-clipbspsurf-port/spike.md` already documents as
**crashing the debug container under gdb** — the same wall that spike hit. Not re-attempted here.

## Status: NOT FIXED — root-caused to mechanism, not to the exact byte

This is a genuine `GetVisibleSurfs` occlusion-accumulation divergence on a razor-thin, newly-exposed
CSG-subtraction sliver surface, confirmed by both native's own trace and a live capture of the real
editor — not a per-save-random field, so per `NATIVE-MATERIALIZE.md`'s prime directive it must be
fixed, not masked, however costly. No fix attempted here: the only lead (node 776's rasterized
footprint) needs a finer live capture than this sandbox can currently take (documented gdb crash on
the raw scanline setup). Left in `dev/docs/board/inbox/wanchai-n-201-world-model2-body-diverges/`
for a follow-on session with either a way around the scanline-setup gdb crash, or a fresh idea for
narrowing which of the ~40 occluding nodes on this face over-claims.

## Repro

    dev/docs/spikes/2026-09-03-incremental-actor-parity/harness/ladder_run.py \
        --dx dev/games/deusex/Maps/06_HongKong_WanChai_Market.dx --from 201 --to 201 --keep-native

Then `body_token_diff.py`/`lmdiag.py`/`leaf_perm_diff.py` (all in
`2026-09-03-incremental-actor-parity/harness/` or `2026-09-07-gather-box-verdict/harness/`) to
localize; `UEDCLI_VISGATE_TRACE_SURF=616 UEDCLI_VISGATE_TRACE_LOC=<light xyz>` to trace one light's
gather for this surf; `raster_order_probe.py --trunk <subset>` for the live editor capture.
