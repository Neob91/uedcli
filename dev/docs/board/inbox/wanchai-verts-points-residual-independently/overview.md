+++
priority = "p3"
kind = "debug"
summary = "Wanchai verts residual (+138, +0.08%) localized to 3 pipeline segments; repartition_frontier's +64 share traces to ~8 calls each off by a uniform +8, mechanism/fix still open"
depends-on = ["unatco-verts-points-residual-after-the-zone"]
+++

# Wanchai Verts/Points residual: independently confirmed, but its UNATCO causal story is owner-invalidated

Re-derived directly from `_scratch/wanchai-relight-2026-08-29/{native,golden}.dx` (2026-08-29, current
tree, node/surf-exact per `feeaa21`): native 16807 points / 167325 verts vs golden 16791 points /
169313 verts — native +16 points, **−1988 verts** (−1.2%). Confirms an external report's claim.

That report also called this "a known, already-diagnosed issue" matching UNATCO's residual
(`unatco-verts-points-residual-after-the-zone`: ~209 unported `csgRebuild` sub-BSP repartition calls,
`sub_49380`). Do not cite that as settled: `owner-ruling-all-native-decode-spike-findings` (ruled
2026-08-28) names this exact mechanism as "diagnosed ONLY from the old spikes → not portable from the
written spec; must be re-pinned from fresh live capture before any port" — despite the item itself
being committed 2026-08-26, its causal chain traces back to the invalidated pre-2026-08-14
disassembly. The Wanchai number above is a real, confirmed measurement; the "same missing feature"
explanation for it is not yet established.

## 2026-08-30: fresh measurement (post `repartition_frontier`+`compact_unreachable_nodes`, current
## tree); residual localized to 3 pipeline segments, one of them a clean, narrow signature

Independently re-derived from scratch (`dev/docs/spikes/2026-08-29-unatco-repart-live-diff/harness/
regression_gate.py`, current tree, `dev/games/trunks/tmp-wanchai-market` vs
`_scratch/golden_wanchai_world.dx` — provenance already confirmed in the findings ledger). The stale
numbers above are superseded (they predate the `repartition_frontier` fix); current-tree numbers:

**Wanchai: nodes/surfs/leaves EXACT. verts +138 (+0.08%), points +16, vectors −8 (new, not
previously tracked).** UNATCO (for reference, not node-exact so out of scope here): nodes +7, verts
+2443, points +14.

**Localized via `UEDCLI_BSPCSG_STAGE_COUNTS` against the live-captured editor stage log
(`dev/docs/spikes/2026-07-15-native-materialize/harness/editor-tree-oracle/logs/
wanchai-ed-repart-stage.log`, dated 2026-08-27 — post-2026-08-14, so not owner-invalidated; a
120-group `bspRepartition`-entry-breakpoint capture: 1 world-level group + 119 subtree groups,
matching native's own frontier count exactly).** The +138 final verts splits additively:

| segment | native Δverts | editor Δverts | native−editor |
|---|---:|---:|---:|
| world-level repartition (`bsp_build` from merged soup) | +43765 (abs) | +43759 (abs) | **+6** |
| zone pass (`TestVisibility`) + detail-brush loop, combined | +67227 | +67164 | **+63** |
| `repartition_frontier`'s 119 subtree calls | +2126 | +2062 | **+64** |
| `bsp_opt_geom` T-junction weld | +56333 | +56328 | +5 (negligible) |

(6+63+64+5 = 138, exact.) **The weld itself is essentially exact** (+5 out of +56328, <0.01%) — same
conclusion the UNATCO investigation already reached for its own weld; do not go looking for a weld
bug here either. The residual is entirely upstream of it, spread across three earlier stages with no
single dominant segment.

**The `repartition_frontier` share (+64) is NOT diffuse — it's concentrated in ~8 of 119 calls, each
off by exactly +8 verts, regardless of subtree size.** Added `UEDCLI_REPART_PERCALL_VERTS` (env-gated,
committed, `bspcsg.rs`) to log every call's own verts-before/after; compared the resulting 119-value
histogram against the editor log's per-call intra-block growth (`E_bsprefresh.verts −
A_entry.verts`, same log). Native's and editor's histograms are nearly identical in shape (both have
exactly one call at +196, one at +80, two at +40, etc.) — strong evidence the two engines are
processing the SAME underlying 119 subtrees, just enumerated in a different order (no direct
positional correspondence: matching call `k` to call `k` gives 100/119 "mismatches" that are pure
order noise, not real divergence). Diffing the two histograms bucket-by-bucket instead of
positionally: every discrepancy is an exact **+8** shift (four calls 4→12, two calls 16→24, one call
20→28, one call 52→60 — `4×8 + 2×8 + 1×8 + 1×8 = 64`, exactly the segment's total). This is a single
uniform per-call offset, not size-dependent noise — consistent with one extra small fragment (e.g. a
4-vertex quad counted twice, or a 2-node/8-vert split the editor doesn't make) recurring in ~8 calls,
not 8 unrelated bugs.

**Not yet done:** which specific 8 of 119 calls, and the mechanism, are unidentified — the node-index
numbering differs between engines (confirmed: no valid positional correspondence), so pinning them
needs either brush-provenance matching (`FBS_ACTORS`-style, per-call) or a live gdb differential
(`repart_child_trace.py`-style, adapted to Wanchai's golden) against several candidate calls — not
attempted this round; even a full fix here would only close +64 of +138, leaving the +6 (world-level)
and +63 (zone+detail, upstream of `repartition_frontier` entirely) segments untouched, so this is a
partial win at best, not a full close.

**Points (+16 final) and vectors (−8 final) are separate, smaller threads, not chased further.**
Points converges via near-cancellation: native is ~2767 points SHORT of the editor at the pre-weld
checkpoint (16859 vs ~19626), and the editor's own weld then discards ~2835 more points than native's
during T-junction welding — two much larger, opposite-signed errors landing close together by
coincidence, not a matched mechanism (same shape as the "EmptyModel retains entries" note already in
`unatco-verts-points-residual-after-the-zone` for UNATCO's points pool). Vectors (−8) is new — not
previously measured for Wanchai at all; `reorder_surfs_canonical`/`rebuild_vector_pool` run after the
weld and could be the site, but this needs its own investigation.

**No fix shipped.** No safe, verified change was found this round — the `repartition_frontier`
+64 lead needs per-call identification before touching code (the sibling UNATCO investigation shows
how easily a plausible-looking merge/dedup fix at this layer regresses Wanchai's node-exactness; nothing
here has been tested against that regression gate). `bin/test -k bspcsg` (84/84) and
`regression_gate.py`'s default (no-env-var) path are BYTE-IDENTICAL before/after this round's only
code change (the new diagnostic, env-gated, zero default-path effect) — Wanchai stays node/surf/leaf-
exact at 11648/…, verts +138, points +16; UNATCO stays 6321/+7 unaffected. Lighting was not
re-measured this round since no geometry-affecting change shipped.

New reusable diagnostic: `UEDCLI_REPART_PERCALL_VERTS=1` (`bspcsg.rs::repartition_frontier`) — per-call
verts/points before/after, `dev/docs/spikes/2026-08-29-unatco-repart-live-diff/harness/
wanchai_stage_diag.py` drives a build with it set for Wanchai specifically (sibling of
`regression_gate.py`, same trunk/golden pair).
