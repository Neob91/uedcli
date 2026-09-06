+++
priority = "p2"
kind = "debug"
summary = "UNATCO's ladder passes N=1..115 and bails at N=116: the world Model2's per-lightmap light RUNS differ on 13 of 214 lightmaps, both directions (native-only lights, ued-only lights, and one lightmap where native has none and UED22 has seven)."
+++

# UNATCO N=116 — world `Model2` light runs differ on 13 lightmaps

`ladder_run.py --dx 03_NYC_UNATCOHQ.dx --from 101` passes to N=115 and bails at N=116 with
`BODY model model2: canonical bodies differ`. Uncovered by closing the N=29 blocker
(`unatco-n-29-world-model2-vert-rings-reference`); the geometry is not implicated.

`harness/lightrun_diff.py` on `native_N116.dx` vs `ref_N116.dx`: `Model.Lights` 941 vs 940 entries,
214 lightmaps both sides, 13 differing. Both directions:

| lightmap | native | UED22 |
|---|---|---|
| 15, 84, 94 | one light each (`light322` / `light178` / `light198`) | empty |
| 70, 72, 78, 80 | `light199` prepended to a run of 3 both sides agree on | the 3 |
| 85 | empty | 7 lights (`light339 338 332 331 177 172 207`) |
| 100 | `light312` prepended to a run of 2 | the 2 |

`body_token_diff.py` reports 12 differing tokens: one literal span (a lightmap record's light-run
COUNT byte, 0x44 vs 0x43) and the `Model.Lights` object refs that follow.

Same family as `wanchai-n45-spotlight22-light-runs-differ-on-4` (a run-membership divergence, not a
lighting VALUE one — `LightBits` was not reported as differing). Whether it shares that item's
`FSpanBuffer` rasterizer root cause is unmeasured; lightmap 85 (empty vs seven) looks larger than a
per-light visibility tie.

Reproduce:

```
.venv/bin/python dev/docs/spikes/2026-09-03-incremental-actor-parity/harness/actor_parity.py \
  --dx dev/games/deusex/Maps/03_NYC_UNATCOHQ.dx diff 116
```
