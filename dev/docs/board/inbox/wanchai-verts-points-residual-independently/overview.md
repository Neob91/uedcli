+++
priority = "p3"
kind = "debug"
summary = "Wanchai verts residual closed to +74 by the shipped repartition_frontier fix. Points residual (+16, now identical on UNATCO and Wanchai) measured cross-level: the match is COINCIDENCE, not one mechanism -- two differently-shaped errors happen to land on the same total. No fix shipped."
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

## 2026-08-30, same day, follow-up: the specific 9 calls IDENTIFIED by real node identity, live-
## verified — and it's the same architectural dead-end as UNATCO's, at 1/30th the scale. STOPPING here
## per the coordinator's steer, not shipping.

Bounded follow-up: find the specific calls behind the +64 `repartition_frontier` share (previously
only known by histogram-bucket shape, not identity) and what's structurally different about them.

**Got real per-call editor identity — the key unlock.** The existing editor stage-log capture
(`wanchai-ed-repart-stage.log`) doesn't record the child node index per call, so it could only be
compared to native positionally (100/119 "mismatches" — pure order noise, see the section above).
Two new live-gdb captures close that:
- `prepart_tree_wanchai.py` (committed, Wanchai sibling of `prepart_tree_unatco.py`) dumps the
  editor's full pre-repartition-frontier `Model->Nodes` (11648 nodes). Diffed node-for-node against
  native's own `UEDCLI_BSPCSG_PREPART_NODES` dump: **only 22/11648 nodes structurally differ**
  (same small coplanar-chain-order-swap signature UNATCO's investigation already found, e.g. a
  handful of 2–3-node permutation clusters) — native's node INDEX directly corresponds to the
  editor's own index at this checkpoint, not just an isomorphic tree. Walking each of native's 119
  `child` values through the editor's own dump (self + `iF`/`iB`/`iP`, same rule as `make_ed_polys`)
  reproduces native's `orig_polys` **exactly, 119/119, zero mismatches** — the pre-repartition INPUT
  soup is provably identical for every one of Wanchai's 119 calls, same conclusion the UNATCO
  investigation reached for its own 209/209 (now independently confirmed on a second level).
- `repart_stage_child_wanchai.py` (committed) re-runs the stage capture but ALSO logs the real
  `child=` index (`esp+8` at `bspRepartition` entry) per group, so native's per-call table
  (`UEDCLI_REPART_PERCALL_VERTS`) can be joined by CHILD IDENTITY instead of position.

**Joined by identity: 110/119 calls match the editor's real vert growth EXACTLY. The other 9 are the
whole story, and every one is off by a small, specific amount:**

| child | orig_polys | native Δverts | editor real Δverts | diff |
|---:|---:|---:|---:|---:|
| 11633 | 15 | 60 | 52 | +8 |
| 11295 | 5 | 20 | 16 | +4 |
| 11291 | 6 | 24 | 16 | +8 |
| 11287 | 6 | 24 | 20 | +4 |
| 11283 | 7 | 28 | 20 | +8 |
| 11206 | 4 | 12 | 4 | +8 |
| 11211 | 4 | 12 | 4 | +8 |
| 11216 | 4 | 12 | 4 | +8 |
| 11201 | 4 | 12 | 4 | +8 |

(Sum of diffs = 64, exactly the whole `repartition_frontier` segment — these 9 calls, precisely
identified, are the ENTIRE +64, not a sample of it.)

**Live-verified the mechanism on the simplest case, `child=11201`.** `UEDCLI_REPART_REAL_TREE` (new,
paired with `UEDCLI_REPART_FBS_CHILD`, dumps the REAL as-shipped subtree a call actually grafted —
unlike `UEDCLI_REPART_ISOLATED_TREE`, which always merges regardless of `UEDCLI_REPART_BLANKET_MERGE`
so it doesn't show the default path's real output) shows native's real output is **4 separate
triangle nodes** (`nv=3` each), all sharing one `isurf`/plane, chained via `iPlane` — the same
"un-merged coplanar duplicate fragments left over from the ORIGINAL pre-repartition build" signature
already fully diagnosed for UNATCO's `child=6108`/`4077`/`3086`. `UEDCLI_REPART_ISOLATED_TREE` predicts
`bsp_merge_coplanars` reduces these 4 triangles to exactly 1 quad node. **`repart_child_trace.py 11201
<wanchai golden>` (live gdb, reused verbatim from the UNATCO harness) confirms the editor's REAL
subtree is exactly 1 `bspAddNode` call, `nv=4`** — the merged prediction, byte-exact plane match.
Same mechanism as UNATCO, now live-verified on Wanchai too.

**Why this isn't shippable: it's the identical "correct per-call, wrong in aggregate" contradiction
UNATCO's investigation hit, just fully accounted-for at 1/30th the scale.** `bsp_merge_coplanars` is
idempotent on a poly list with no same-surf duplicates, so "merge only where it would change something"
and "blanket-merge all 119 calls" are mathematically the SAME operation — there is no selective
half-measure to try that differs from the already-reverted blanket-merge experiment
(`unatco-verts-points-residual-after-the-zone`, "it broke Wanchai's previously node-exact match
(11648 → 11628)"). Computed each of these 9 calls' own `UEDCLI_REPART_ISOLATED_TREE` merged node
count and summed the reduction against `orig_polys`: **13,4,4,5,5,1,1,1,1 vs 15,5,6,6,7,4,4,4,4 — a
total of exactly −20 nodes**, matching the earlier blanket-merge experiment's regression
(11648 → 11628) to the digit. So the ENTIRE Wanchai node-count regression from that experiment is
fully explained by just these 9 calls (no hidden compensating deficit elsewhere, unlike UNATCO's
−625 which never balanced against its own 46-call prediction) — but it's still a regression: fixing
these 9 calls' verts by merging necessarily shrinks their own node count too, and Wanchai's CURRENT
unmerged path already lands the true FINAL aggregate at the right number (11648, matching the golden)
despite representing these 9 subtrees "wrong" (as extra unmerged fragments) locally. Why the true
final count stays right without the merge, when the merge is independently proven correct per call
(live, not just predicted) — same unresolved shape as UNATCO's "individually correct, aggregate
wrong" puzzle. Not chased further.

**Stopping here per the coordinator's steer** (bounded task: identify the calls + look at what's
structurally different — done; do not grind into the open-ended aggregate contradiction UNATCO
already spent ~2M tokens on without resolving). No fix shipped. Wanchai stays node/surf/leaf-exact
at 11648, verts +138, unchanged; `bin/test -k bspcsg` (84/84) and `regression_gate.py`'s default path
are byte-identical before/after this round's two new diagnostics (`UEDCLI_REPART_REAL_TREE`, plus the
committed `prepart_tree_wanchai.py`/`repart_stage_child_wanchai.py` harness scripts — all zero-effect
on the default path, all reusable for a future round or for the sibling UNATCO investigation, which
has never had per-call editor identity this precise before).

## 2026-08-30, resumed (per coordinator: this "correct per-call, wrong in aggregate" signature turned
## up on ~all breadth-tested OG levels, making it the highest-leverage blocker, not UNATCO-specific):
## descendant-slot check on these exact 9 calls, decisive negative result.

`wanchai_descendant_slots.py` (`dev/docs/spikes/2026-08-29-unatco-repart-live-diff/harness/`):
BFS-walked `iFront`/`iBack` from each of the 9 calls' target node AT its `bspRepartition` entry,
captured every reached node's full 64 raw bytes, re-read the SAME indices at the call's own
`bspRefresh`-return marker. First pass found "43 total slots, 0 changed" but the walk only followed
`iFront`/`iBack` — a bug, since 4 of the 9 targets (`11201/11216/11211/11206`) have
`iFront=iBack=-1` but a live `iPlane` coplanar-chain, silently unwalked. **Fixed to also follow
`iPlane`; rerun: 55 total slots across all 9 subtrees — still 0 changed, byte-for-byte, everywhere,
now covering every node reachable by any of the three link fields.** Combined with the earlier
`Nodes.Num` watchpoint result (always nets to the pre-call baseline), both obvious "where does the
editor commit this call's result" candidates are ruled out for this calibration set: no net array
growth, no in-place content rewrite anywhere reachable from the call's own target — the editor's own
call is a proven, complete no-op for all 9.

## Same day, follow-up: this no-op finding, cross-referenced against ALREADY-COMMITTED tree dumps
## (no new capture needed), corrects the per-call table above — it was measuring the wrong thing.

Cross-referenced `prepart_tree_wanchai.py`'s existing dump (the editor's full tree at `callidx==2`,
the exact moment right before `repartition_frontier`'s subtree loop begins — already committed, no
new capture): for EVERY ONE of the 9 targets, the PRE-EXISTING subtree size (BFS over
`iFront`/`iBack`/`iPlane`) exactly equals `orig_polys` from the table above (9/9 exact:
15/5/6/6/7/4/4/4/4) — the editor's persistent tree already has each original poly as one separate,
unmerged node BEFORE `repartition_frontier` touches these subtrees at all. Given the call is a
proven no-op (55/55 unchanged, this round) and the pre-existing structure is unmerged and matches
`orig_polys`, that same unmerged structure is what SHIPS — so the true persistent vertex count per
subtree is `orig_polys × verts-per-poly`. **Computed this for all 9: it exactly equals native's own
current (default, unmerged) `Δverts` column — NOT the "editor real Δverts" column in the table
above, for all 9 targets** (e.g. `child=11201`: table said editor-real=4; persistent-content
computation says 12, matching native's own 12 exactly; same exact match for the other 8).

**This means the "editor real Δverts" column above, and the whole "9 known-bad calls, summing to
exactly +64" framing built on it, measured the WRONG thing.** That column came from
`repart_child_trace.py`'s live capture of `bspAddNode` calls DURING the target's own
`bspRepartition` call — genuinely real calls (confirmed live, `bspAddNode`'s own `Model` argument
matches the persistent model,
`dev/docs/spikes/2026-08-29-unatco-repart-live-diff/harness/repart_addnode_model_trace.py`) but
whose RESULT never survives: `bspRefresh`'s own `Core.dll!FArray::Remove` call discards it every
single time (`nodesnum_watch.py`, same investigation, `native-materialize-findings.md`). So "the
editor's REAL subtree is exactly 1 `bspAddNode` call, nv=4" (this item's own earlier framing for
`child=11201`) was a misnomer — that call is real but its output is thrown away; the actual
persistent, shipped content is the pre-existing 4-node unmerged chain, which numerically matches
native's CURRENT default output exactly. **Once measured against the true persistent content, all 9
of these calls show ZERO delta, not the tabulated +4/+8s.**

**Open, not resolved by this round:** if these 9 calls' real per-call delta is zero, Wanchai's true
+138-vert residual (and the "+64 attributed to `repartition_frontier`'s 119 calls" stage-count
finding specifically) is NOT localized to these 9 calls after all — it needs re-attribution from a
clean slate. Not yet checked: whether the `UEDCLI_BSPCSG_STAGE_COUNTS` aggregate measurement that
produced "+64" used a `prepart_tree_wanchai.py`-style persistent snapshot (unaffected by this
correction) or a `repart_child_trace.py`-style live per-call capture (affected, per this finding) as
its editor-side reference for repartition_frontier's segment — that's the concrete next step, and it
determines whether the "+64" figure needs to be thrown out or was measured correctly by a different
route. The SAME methodology (`repart_child_trace.py`'s live per-call capture) was also used for
UNATCO's `child=6108`/`4077`/`3086` in the sibling item
(`unatco-verts-points-residual-after-the-zone`) — NOT independently re-checked this round, flagged
there as a re-examination risk rather than silently assumed still valid.

**Not shipped, no regression risk.** Read-only live capture and re-analysis of already-committed
logs only — no new claims requiring a fresh capture beyond the `iPlane`-walk fix above. `bin/test -k
bspcsg` (84/84) and `regression_gate.py`'s default path unchanged (Wanchai still exact at 11648;
UNATCO still 6321 vs 6314 golden) before/after.

## SHIPPED, same day, from the sibling UNATCO item: `repartition_frontier` rewritten (done/
## `unatco-verts-points-residual-after-the-zone`) — Wanchai's own verts residual improved as a
## side effect, still not closed.

The fix implementing the mechanism this item helped characterize (`bspRepartition`'s real per-call
reconstruction is discarded structurally but permanently grows Verts/Points) shipped from the UNATCO
item, not this one — see that item (now in `done/`) and `dev/docs/native-materialize-findings.md` for
the full write-up. Wanchai stays node/surf/leaf-exact throughout (unaffected, as always); verts
improved `d=+138 → d=+74` (points unchanged, `d=+16`) — a real improvement, but Wanchai's own residual
is not fully closed by this fix alone. Not investigated further here — this item's own scope (identify
the specific known-delta calls, characterize the no-op) is complete; closing Wanchai's remaining +74
verts gap would be a new, separate investigation if picked up.

## 2026-08-30, follow-up round: the Points residual (+16 on BOTH UNATCO and Wanchai, post-fix) — the
## equal size is a coincidence, not one shared mechanism. No fix shipped.

Picked because it's now the smallest, most-consistent geometry gap left (identical +16 on two
different levels, unlike the verts residual's per-level-varying size). Full per-stage measurement +
two new read-only diagnostics in `dev/docs/native-materialize-findings.md` (search "Points residual
(+16 on both UNATCO and Wanchai"); summary here.

`regression_gate.py` confirms the starting point: both levels node/surf/leaf-EXACT, points `d=+16`
both. `UEDCLI_BSPCSG_STAGE_COUNTS` (native) vs the pre-existing live-captured editor stage logs
(`repart-stage-unatco.log` / `wanchai-ed-repart-stage.log`, both dated 2026-08-26/27, post-2026-08-14
so not covered by the pre-2026-08-14 spike invalidation) breaks the +16 down by pipeline stage on both
levels. Two results directly test this item's own prior hypothesis (that the `repartition_frontier`
share, already localized here for Verts, is also where Points enters):

- **Refuted as a shared cause.** `repartition_frontier`'s own points growth is a large miss on UNATCO
  (native +10 vs editor +1464, undershoot 1454 in that one stage alone) but negligible on Wanchai
  (native +0 vs editor +7). It dominates UNATCO's error budget and is irrelevant to Wanchai's — not a
  shared mechanism.
- **The dominant SHARED mechanism is upstream of `repartition_frontier`: the world-level clear.**
  `build_geometry_bspcsg` clears `model.{nodes,surfs,verts,points,vectors}` immediately before the
  WORLD-level `bsp_build` call, and the single biggest per-stage gap on BOTH levels opens right there,
  before repartition or the zone pass even runs (UNATCO −358, Wanchai −2759, at the very first
  checkpoint). This matches, in shape, a pre-2026-08-14 (owner-flagged, not trusted at face value)
  disassembly claim in `sections/82-bspbrushcsg-port-decode.md`: `EmptyModel(0,0)` keeps
  Points/Vectors/Surfs and only unconditionally clears Nodes/Verts, and `bspRepartition`'s own
  `bspRefresh` call uses `NoRemapSurfs=1` — so the editor's CSG-phase Points/Surfs pool survives into
  the repartition while native's does not. That old write-up already flagged porting this as **high
  tree-regression risk** (entangled with `surf.pBase`/`vert.iVertex` pool indices) and never attempted
  it even on its own, smaller, pre-node-exactness test case.

**But the gap does not propagate additively** — a new `UEDCLI_REORDER_POINTS_DIAG` diagnostic
(`bspcsg.rs`, env-gated) shows the final compaction (`reorder_points_canonical`) drops only 52 points
on EACH level (52 genuine, distinct, level-specific coordinates, confirmed via a full dump — the equal
count is itself a coincidence), while the true swing between the world-level clear and the final map is
~2000+ points on both sides (UNATCO −2089→+16, Wanchai −2767→+16). So the small final residual is a
near-total cancellation of much larger, only-partly-understood errors, not evidence the pipeline is
"almost right" anywhere in particular.

**The +16=+16 match itself decomposes differently per level**, via a second new diagnostic
(`REORDER_POINTS_REACHABLE_ONLY`, recomputes what the PRE-orphan-vert-retention-fix policy would have
kept): UNATCO's "reachable-only" baseline is 10758 (already **+6** over golden, independent of the
orphan-vert-retention fix shipped in `unatco-verts-points-residual-after-the-zone`); Wanchai's is
16807, **byte-identical to its current result** — the orphan-vert-retention fix changes nothing for
Wanchai (its `repartition_frontier` phase added zero new points to retain). So UNATCO = 6 (pre-existing)
+ 10 (orphan-vert retention); Wanchai = 16 (pre-existing) + 0. Two different compositions, same total.

**No fix shipped** — both candidate levers are either entangled with a previously-flagged high-risk
area (the world-level clear, never attempted even in the old, simpler investigation) or don't touch
Wanchai at all (the orphan-vert-retention scope). Recommended next step for a future round: a live gdb
capture of the CURRENT (node-exact) UNATCO's `EmptyModel`/`bspRefresh` args and Points pool at the
world-level `bspRepartition` boundary, to re-confirm the pre-2026-08-14 claim from scratch on the
now-node-exact tree before attempting a no-clear world-level repartition — that change is real tree
surgery (like `repartition_frontier`'s own graft) and needs the same hard regression gate (both levels'
node/surf/leaf exactness) before it can be attempted.

Shipped this round: two read-only, env-gated diagnostics only (`bspcsg.rs`) — one more
`UEDCLI_BSPCSG_STAGE_COUNTS` line (`STAGE post-optgeom`) and the new `UEDCLI_REORDER_POINTS_DIAG`.
Both zero-effect on the default path: `regression_gate.py` byte-identical before/after (points `d=+16`
both levels, still node/surf/leaf-EXACT everywhere), `bin/test -k bspcsg` 85/85, full `bin/test` green
(see the commit for the exact run).
