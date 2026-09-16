+++
priority = "p2"
kind = "debug"
summary = "Root-caused to mechanism (not exact byte): GetVisibleSurfs marks world surf 616 (Brush1164, a thin CSG-subtraction sliver) dark where UED22 gives it an empty run. Live gdb capture confirms UED22 accepts it for Light431; native's own trace shows it rasterizes but gets 0 accepted px, fully claimed by earlier occluders on the same face. 2026-09-15: the 245-vs-165 rasterize-call-count gap is now sequence-diffed and settled -- 78 calls are a structurally separate block that never touches surf 616 at all, 2 are a harmless degenerate-clip counting artifact; the remaining 165-call matching chain's accept/reject verdict is now confirmed against real footprint data end to end (not just the two nodes spot-checked before). That leaves a sharper paradox: an independent live capture shows UED22 accepting this exact event, but replaying UED22's own row data through the (proven-faithful) algorithm still rejects it -- next step is verifying the span buffer's STARTING STATE via one more live capture, not yet attempted. Still not fixed."
+++

# WanChai N=201 — world Model2 body diverges

Found immediately after `wanchai-n59-mover-polys-model2-diverges` (done, fixed 2026-09-14). With
that fix, WanChai re-verified byte-exact N=1..200 — new territory past its old N=58 ceiling. Bails
at **N=201** on `BODY model model2: canonical bodies differ`.

## Repro

    dev/docs/spikes/2026-09-03-incremental-actor-parity/harness/ladder_run.py \
        --dx dev/games/deusex/Maps/06_HongKong_WanChai_Market.dx --from 201 --to 201 --keep-native

Decode `Model2` on both sides with `model_dump.py <native.dx> <ref.dx> Model2` or
`parity_gate.canon_body` directly (see other WanChai/OceanLab/NYC_Bar spikes for the idiom).

## The precise divergence

`body_token_diff.py`: token count off by 1 (`Model.Lights` 2019 vs 2020); the only other diff is a
literal-byte offset inside `LightMap`. `lmdiag.py` localizes it to record 354 (world surf 616, owned
by `Brush1164` — trunk actor 201, `CsgOper=CSG_Subtract`, a small decorative sign/awning frame; surf
616 is its `2DLoftSIDE` face, a thin diagonal quad right at the subtraction cut):

    nat=dark    (DataOffset=0, iLightActors=-1 -- no lightmap run allocated at all)
    ued=()      (an EMPTY run -- allocated, but zero lights survived the per-lumel raytrace)

`leaf_perm_diff.py` confirms `Model.Lights` region 1 (per-leaf permeating lists) is byte-identical —
the whole divergence is region 2, the per-surf gather (`light::bake`'s `gathered()` predicate,
which decides whether >=1 light earns this surf a lightmap slot at all).

## Root cause — pinned to mechanism, live-capture confirmed, not yet to the exact byte

Full writeup: `dev/docs/spikes/2026-09-15-wanchai-n201-surf616-getvisiblesurfs-miss/spike.md`.

Of the 68 lights in the N=201 subset, 8 pass `gathered()`'s special_lit/backface/plane-distance
filters for surf 616 (`harness/lm354_candidates.py`); native's `GetVisibleSurfs` port
(`visible_surfs.rs`) rejects surf 616 for every one of them (`UEDCLI_VISGATE_DUMP=1`: surf 616
appears in zero of the 68 gathered sets). A live gdb capture of the REAL editor
(`raster_order_probe.py`, breakpointing `render.dll 0x10019c1c`, `OccludeBsp`'s raster-commit test,
reused unmodified from the NYC_Bar N=153 spike) shows UED22's own raster-commit test **accepts**
surf 616 for `Light431` (`edi=1`, non-zero) on the light's straight-down cube face — so UED22's
`GetVisibleSurfs` really does include it; `dark` is native's bug.

Native's own trace for the same light (`UEDCLI_VISGATE_TRACE_SURF=616
UEDCLI_VISGATE_TRACE_LOC=-1160.745361,-807.899902,220.417908`) shows node 774 (surf 616) IS reached
and DOES rasterize to a real (if tiny — 22 rows, 59px) footprint on this face, then gets **zero**
accepted pixels: every row's span-buffer window is already fully claimed by earlier occluders. The
last large occluder visited before it is node 776 (surf 2, `PF_Unlit|PF_FakeBackdrop` — a sky
polygon); `PF_FakeBackdrop` is correctly NOT excluded from `occludes()`'s opaque mask (disassembly-
verified), so this is not a wrong-flag bug — if it traces to node 776 at all, it would be a
rasterization-footprint precision difference in `clip_bsp_surf`/`raster_setup`, narrowing a
razor-thin gap the real renderer leaves open. Not pinned exactly: that needs single-stepping
`raster_setup`'s raw scanline setup (`render.dll 0x1001b470`), which
`2026-09-06-raster-clipbspsurf-port/spike.md` already documents as **crashing the debug container
under gdb** — the same wall hit here, not re-attempted.

## 2026-09-15 update — the gdb-crash wall is DOWN; rasterizer cleared; new lead open

Full writeup: `dev/docs/spikes/2026-09-15-wanchai-n201-raster-footprint/spike.md`.

Found a way around the documented scanline-setup crash: breakpoint `OccludeBsp`'s own CALL SITE to
the scanline setup (`render.dll 0x10019a6c`/`0x10019a71`), not the routine's shared entry
(`0x1001b470`) — `OccludeBsp` itself is gather-exclusive (already proven safe for ~10,000 hits by
`raster_order_probe.py`), so the call site never fires from real-time viewport rendering. Ran a
whole `LIGHT APPLY` pass clean, no crash (`harness/raster_callsite_probe.py`).

Compared against native's own trace, the real editor's rasterized rows are BYTE-IDENTICAL to
native's on both surf 616 itself (node 774) and its suspected occluder (surf 2/node 776, an 84-row
sky quad) — the rasterizer/scanline code is not the bug, at least on these two nodes. The new,
unexplained lead: the real editor makes **245** `OccludeBsp` rasterize calls for this exact
light+face; native's own trace makes only **165** — 80 fewer. Native-side bisection
(`UEDCLI_VISGATE_SKIP_NODE`/`_SKIP_SURF`, temp probes in `visible_surfs.rs`) shows at least two
independent occluder families (the sky AND ordinary architecture, e.g. node 443) redundantly seal
this exact sliver in native, so no single node's removal alone flips the verdict.

## 2026-09-15 update — the 245-vs-165 gap is sequence-diffed and settled; a sharper paradox remains

Full writeup: `dev/docs/spikes/2026-09-15-wanchai-n201-sequence-diff/spike.md`.

`harness/diff_call_sequences.py` diffs the real editor's 245-hit capture against native's own 165-call
face-5 trace by isurf sequence (`difflib`). Clean decomposition, no more guessing:

- **2 calls**: harmless. Both are `isurf=597`, real returns an explicit empty rasterize (`ret=0`,
  `miny==maxy`); native's own trace shows the SAME 10-member coplanar chain, with native's
  `rasterize_node` returning `None` ("clipped away / degenerate") for the last 2 members instead of
  calling the shared routine at all. Same real-world outcome (zero occlusion effect) reached two
  different ways — a call-site counting artifact, not a bug.
- **78 calls**: a structurally separate leading block (`real[0:78]`), mostly disjoint from native's
  own 165-surf set. **It never touches surf 616** — `isurf=616` appears exactly once in the whole
  245-hit capture, inside the matching region. Whatever this block is (candidates: a genuine
  once-per-reachable-start-zone `OccludeBsp` re-invocation, vs. shared architecture legitimately
  visible from multiple of the light's other 5 cube faces — not distinguished here), it cannot by
  itself explain surf 616's accept/reject outcome.
- **The remaining 163 (91+74) calls match real's sequence exactly, in order** — proving native's node
  visit order, for the WHOLE relevant chain (not just node 774/776 as before), is faithful.

`harness/replay_matching_chain.py` goes one step further: feed the REAL editor's own raw per-row
rasterized windows (already captured, `raster-callsite.log`'s `ROW` lines) through a straight port of
native's own `test_and_maybe_subtract` (disassembly-verified against `FSpanBuffer::CopyFromRaster
(Update)`), in native's own call order, using each call's own `opaque` classification, and checks the
ACCEPT/REJECT verdict each call reaches (`accepted_px>0` vs `==0` — the actual downstream question,
not a literal pixel-for-pixel span comparison). Result: **zero accept/reject mismatches across all 165
calls, including surf 616 itself** (replay: `accepted_px=0`, matching native's own `accepted_px=0`
exactly). This rules out a rasterizer footprint bug, a subtraction-algorithm bug, and a
node-visit-order bug for the entire matching chain, at that accept/reject granularity.

That sharpens the paradox rather than resolving it: a SEPARATE, independent live capture
(`raster_order_probe.py`, `render.dll 0x10019c1c`, `FSpanBuffer::CopyFromRasterUpdate`'s own return
value) shows this EXACT event (matched to full float precision: isurf=616,
origin=(-1160.74536,-807.899902,220.417908), zaxis=(0,0,-1)) with `edi=1` — UED22 genuinely accepts
it. Since the algorithm and every input footprint in the matching chain are now proven faithful, the
one thing left unverified is the span buffer's STARTING STATE at the point the matching chain begins
— native seeds a fresh, fully-visible buffer per light per face; if the real engine's buffer isn't
fresh there (carries state from something else — plausibly the leading 78-call block, if it shares the
same zone buffer rather than being a separate one), that would change the outcome with no
rasterization difference needed at all. **Not settled**: needs one more live capture (dump the real
`FSpanBuffer`'s own row-interval list at the first hit of the matching chain — the struct layout is
already fully decoded, `2026-08-29-unatco-repart-live-diff/harness/mergewith_live_check.py`), not
attempted this pass.

A real harness bug was found and fixed along the way: `visible_surfs.rs`'s `UEDCLI_VISGATE_TRACE_ROWS`
TEMP probe (row-level dump) fired for every light's own gather in the parallel bake, not just the
traced one — now gated on `trace.is_some()` too. `cargo test` green; WanChai N=1..200 re-verified
byte-exact with the rebuilt binary (no regression, the fix is unreachable on the default path).

## Status: NOT FIXED

A genuine, reproducible `GetVisibleSurfs` occlusion-accumulation divergence on a razor-thin,
newly-exposed CSG-subtraction sliver surface — not a per-save-random field, so per
`NATIVE-MATERIALIZE.md`'s prime directive it must be fixed, not masked, however costly. Root-caused
much further than before (the 245-vs-165 gap is fully explained and does not itself account for the
divergence; the entire matching traversal/footprint/subtraction chain's accept/reject verdict is now
confirmed against real data, call for call) but not to an exact byte or an applied fix. Left in
`to-spike/` for a follow-on session: a
live capture of the real `FSpanBuffer`'s own content at the start of the matching chain, to settle
whether its starting state is genuinely fresh (as native assumes) or carries prior state — see the
spike's "Next step" for the exact probe to build.
