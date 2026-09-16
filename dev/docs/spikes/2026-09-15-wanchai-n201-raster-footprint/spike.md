# WanChai N=201 — a crash-free rasterizer capture, and a new lead (not a fix)

Follow-on to `2026-09-15-wanchai-n201-surf616-getvisiblesurfs-miss` (root-caused to mechanism, not
fixed) and `2026-09-06-raster-clipbspsurf-port` (documented the scanline-setup gdb crash). Two results:
a working method to capture `render.dll`'s rasterizer live without the crash, and a real new
divergence it surfaced — a rasterize-call COUNT mismatch, not (for the nodes checked) a rasterizer
bug. **Not fixed.** Board item stays in `to-spike/`.

## The crash workaround

`raster_probe.py` (2026-09-06) broke at the scanline setup's own entry, `render.dll 0x1001b470`, and
crashed the debug container — that address is called from real-time viewport rendering too, so it
fires continuously even at editor idle.

`URender::OccludeBsp` calls it from exactly ONE call site: `render.dll 0x10019a6c`
(`call 0x1001b470`, confirmed live: `harness/disasm_callsite.py`,
`logs/disasm-callsite.log`). `OccludeBsp` itself is gather-exclusive — `raster_order_probe.py`
(a different spike) already ran ~10,000 hits on a deeper address in the same function for a full
`LIGHT APPLY` pass with no crash. Breakpointing the CALL SITE (before the call, and at its return,
`0x10019a6c`/`0x10019a71`) instead of the callee's own entry sees the same cdecl args
(`Pts, NumPts, Span, Frame->Y`) and the same output globals (`MinY`/`MaxY`/the raster-span array)
`raster_probe.py` wanted, without ever placing a trap inside the hot shared routine.

`harness/raster_callsite_probe.py` runs this for a whole `LIGHT APPLY` pass, gated to one light+face
(`Frame->Coords.Origin`/`ZAxis` match, same convention as `raster_order_probe.py`) to keep the log
readable. Ran clean, no crash, no truncation: `logs/raster-callsite.log` (245 rasterize calls for
Light431's straight-down face, N=201 subset).

## What it proved: the rasterizer is NOT the bug (on the nodes checked)

Comparing the real editor's captured rows against native's own trace
(`UEDCLI_VISGATE_TRACE_SURF=<n> UEDCLI_VISGATE_TRACE_LOC=-1160.745361,-807.899902,220.417908`) for two
representative nodes:

- **Surf 616 itself** (node 774, the target sliver): real editor `hit=197`, 22 rows, EVERY row's
  `Start`/`End` byte-identical to native's own computed window (e.g. `y=455 s=389 e=391` on both
  sides, through `y=476 s=365 e=368`).
- **Surf 2 / node 776** (the big `PF_FakeBackdrop` sky quad right before it, the prior spike's lead
  suspect): real editor `hit=195`, 84 rows, ALSO byte-identical to native's own computed window on
  every row (`y=409 s=350 e=655` through `y=492 s=444 e=655`).

So the scanline rasterizer reproduces the real editor exactly for both a huge quad and a
three-pixel-wide sliver — the earlier "footprint precision" hypothesis is not the mechanism, at
least not on these two nodes.

## The new lead: a rasterize-call COUNT mismatch, not yet explained

Counting `URender::OccludeBsp`'s own rasterize calls for this exact light+face:

- Real editor (`raster-callsite.log`, gated to this one light+face): **245** calls.
- Native's own trace, same face (`UEDCLI_VISGATE_TRACE_SURF=-1`, filtered to `face=5`): **165** calls.

**80 more rasterize calls on the real side, for the identical light+face.** Given the two spot-checked
nodes above are pixel-identical, the extra 80 real-editor calls are either (a) nodes native never
reaches at all — a traversal/zone-retire difference, the same bug CLASS as the already-fixed OceanLab
N=48 zone-retire gap, or (b) an artifact of how `OccludeBsp` is invoked (e.g. once per reachable start
zone, not once per light+face) that this count doesn't actually compare like-for-like. **Not
distinguished — this is the open question**, not a confirmed root cause.

## Native-side bisection (no live capture needed)

Using a temporary `UEDCLI_VISGATE_SKIP_NODE=<n>` / `UEDCLI_VISGATE_SKIP_SURF=<s>` probe added to
`visible_surfs.rs` (skips one node's or one surf's occlusion subtraction, everything else unchanged),
tested which upstream occluder is responsible for node 774's empty span test:

- Skipping node 776 alone: no change (`accepted_px` still 0) — something else independently closes
  the same window.
- Skipping ALL of surf 2 (every sky fragment) together: no change for node 774's exact window, though
  it does open OTHER area on the same rows (the remaining gap shifts from `[343,1024)` down to
  `[473,535)`, not overlapping node 774's `[365,391)`-ish columns).
- Skipping node 443 (a foreground architectural surface, NOT sky) alone: `accepted_px` goes from 0 to
  4 — a real, partial contributor.

So at least two independent occluder families (the sky AND ordinary architecture) redundantly seal
this exact sliver in native — consistent with a genuine, tiny gap the real editor leaves open that
nothing in native's traversal currently reproduces, rather than one single wrong pixel in one place.

## Status: NOT FIXED

Root-caused further than before (the rasterizer itself is cleared on two representative nodes; a
concrete 165-vs-245 call-count mismatch is now on record) but not to an exact byte or an applied fix.
Left in `dev/docs/board/to-spike/wanchai-n-201-world-model2-body-diverges/` for a follow-on session:
extend `raster_callsite_probe.py`'s gating to log EVERY node's `isurf` (not just the two spot-checked)
and diff the full 245-vs-165 sequences to find where they first diverge, or determine whether the
count difference is an `OccludeBsp`-invocation-count artifact rather than a per-node traversal gap.

## Repro

    dev/docs/spikes/2026-09-03-incremental-actor-parity/harness/ladder_run.py \
        --dx dev/games/deusex/Maps/06_HongKong_WanChai_Market.dx --from 201 --to 201 --keep-native

`harness/disasm_callsite.py` (no MAP load, static disasm) confirms the call-site address on a fresh
container. `harness/raster_callsite_probe.py --trunk <N201 subset> --origin <light xyz> --zaxis <face
axis>` runs the crash-free capture for one light+face over a whole `LIGHT APPLY` pass.
`harness/full_trace_light431.py <trunk> <project>` re-runs native's own lit build with
`UEDCLI_VISGATE_TRACE_SURF`/`_LOC`/`_ROWS` set, for the native-side comparison.
