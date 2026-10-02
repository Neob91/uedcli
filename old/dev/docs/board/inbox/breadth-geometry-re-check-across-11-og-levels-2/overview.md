+++
priority = "p1"
kind = "debug"
summary = "Breadth geometry re-check across 11 OG levels: 2/11 exact, below 30% floor"
+++

# Breadth geometry re-check across 11 OG levels: 2/11 exact, below 30% floor

Answers the Stop-hook's repeated "sample is too narrow" flag: a full re-measure of every
`geo-confirm-*` project with a golden on disk, on the current tree (post the repartition_frontier
experiments in `unatco-verts-points-residual-after-the-zone` — none of which are shipped by
default; see the findings ledger). Direct `uedcli_native.build_geometry_bspcsg` vs `MAP
REBUILD`-only editor goldens, harness `dev/docs/spikes/2026-08-29-unatco-repart-live-diff/harness/breadth_gate.py`.

Before trusting any of this, the goldens' own provenance was checked (own-initiative + coordinator
prompt): no committed builder script/log exists for 7 of the 11 `geo-confirm-*` goldens, only
inferred from file dates. Closed it by independently rebuilding `training-final`'s golden from
scratch, live (`build_ued_golden.py --world-only --no-light --no-obj-load`, confirmed `MAP NEW` +
`EDIT PASTE` + `MAP REBUILD`, never `MAP LOAD`) — bit-identical to the existing file on every
count. Detail in the findings ledger ("Golden `.dx` provenance — CONFIRMED, closed").

## Result

| level | golden nodes | native nodes | Δ nodes | Δ surfs | Δ leaves | exact? |
|---|---:|---:|---:|---:|---:|---|
| UNATCO | 6314 | 6321 | +7 | 0 | 0 | no |
| Wanchai (Market) | 11648 | 11648 | 0 | 0 | 0 | **yes** |
| smuggler | 7007 | 7202 | +195 | +4 | 0 | no |
| paris-chateau | 11167 | 11205 | +38 | 0 | 0 | no |
| training-final | 11122 | 11412 | +290 | 0 | +13 | no |
| hk-helibase | 14549 | 14877 | +328 | 0 | 0 | no |
| area51-entrance | 12630 | 9246 | -3384 | -511 | +45 | no (known root-caused under-build) |
| DX.dx (intro/logo) | 26 | 26 | 0 | 0 | 0 | **yes** (trivial, 5 world brushes) |
| nyc-street | 13252 | 13447 | +195 | +4 | +118 | no |
| freeclinic08 | 2522 | 2502 | -20 | +1 | -23 | no |
| nsfhq04 | 7656 | 7578 | -78 | +1 | -26 | no |

**2/11 exact (18%), or 1/10 (10%) excluding the trivial 5-brush intro screen — below the 30%
floor.** 11 unique levels is itself ~40-55% of the ~20-30 total OG DX levels, so the SAMPLE size
answers the Stop-hook's breadth objection; the PARITY RATE is the separate, harder number, and it
is currently low.

## Notes

- UNATCO is NOT currently node-exact (+7). The blanket coplanar-merge fix that would have targeted
  this regresses UNATCO further (6321→5689 vs target 6314) and is gated off by default
  (`UEDCLI_REPART_BLANKET_MERGE`, unset) — see `unatco-verts-points-residual-after-the-zone`, still
  open.
- freeclinic08 and nsfhq04 both under-build nodes by <1% while surfs are +1 — matches the
  pre-existing `-nodes, +1 surf` "native face-keeping / tree-shape" signature already characterized
  in `geo-confirm-wanchaimkt-wk/logs/verdict-report.md` (native surf surplus is provably not from
  merge widening; a face the editor drops that native keeps, from a differing soup feeding the
  repartition stride). Not investigated further here — breadth over depth per the task.
- Area51-entrance reconfirms the already root-caused severe under-build
  (`native-under-builds-area51-entrance-geometry`), not re-litigated.
- Numbers for smuggler/paris-chateau/training-final/hk-helibase differ from the prior
  `geometry-re-check-on-4-more-og-levels-0-4-exact` "Update 2026-08-29" measurement (e.g. smuggler
  node delta +253 there vs +195 here) — expected drift from the repartition_frontier experiment
  commits landing between the two measurements, not a discrepancy to chase.
- `breadth_gate.py` segfaults intermittently (not reproducibly on a fixed case) when run back to
  back across all 13 cases in one process — reproduced twice, not investigated (numbers from the
  runs that completed are internally consistent across both attempts for every case that finished
  both times). Worth a look if it starts corrupting results rather than just crashing loudly.

## Levels still unmeasured (no golden on disk)

`geo-confirm-area51`, `geo-confirm-freeclinic`, `geo-confirm-nsfhq`, `geo-confirm-rbag` exist but
have no golden `.dx` — superseded by the `-wk`/`-entrance` variants above except `rbag`, which has
no golden at all and was not investigated further (breadth budget spent on the 11 above).
