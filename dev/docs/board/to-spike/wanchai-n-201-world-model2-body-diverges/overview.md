+++
priority = "p2"
kind = "debug"
summary = "Root-caused to mechanism (not exact byte): GetVisibleSurfs marks world surf 616 (Brush1164, a thin CSG-subtraction sliver) dark where UED22 gives it an empty run. Live gdb capture confirms UED22 accepts it for Light431; native's own trace shows it rasterizes but gets 0 accepted px, fully claimed by earlier occluders on the same face. Not fixed — the exact occluder/precision cause needs a finer capture than this sandbox can currently take."
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

## Status: NOT FIXED

A genuine, reproducible `GetVisibleSurfs` occlusion-accumulation divergence on a razor-thin,
newly-exposed CSG-subtraction sliver surface — not a per-save-random field, so per
`NATIVE-MATERIALIZE.md`'s prime directive it must be fixed, not masked, however costly. No fix
applied: the only lead (node 776's footprint, or another of the ~40 occluding nodes on this face)
needs a finer live capture than this sandbox could take this session (the scanline-setup gdb
crash). Left in `inbox/` for a follow-on session with a way around that crash, or a different
narrowing approach (e.g. bisecting occluders by disabling them one at a time in native and re-
checking `accepted_px`).
