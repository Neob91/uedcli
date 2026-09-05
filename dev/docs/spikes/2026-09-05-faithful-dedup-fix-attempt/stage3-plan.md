# Stage 3 plan — faithful point-dedup

## RESOLVED — the faithful fix SHIPPED (read this first; it supersedes everything below)

The pessimistic sections below ("pure-descent REFUTED as a standalone fix", the 21-regress/0-fix COST
CENSUS, "WEEKS, high risk", "keep the x=448 mask") were measured with a BUG in the descent: it walked
native's live incremental tree with the ENGINE iFront/iBack convention, but that tree is in native's
SWAPPED CSG convention (`swap_node_children` converts only at finalize). Fixing the descent to swap
near/far children (commit `42c9449`) made it faithful and the result inverted:

- The descent is now the DEFAULT dedup (no env gate); the x=448 W/base mask + the Brush-Region mask are
  REMOVED from `parity_gate.py`. UNATCO N8 and WanChai N19 gate byte-exact WITHOUT any mask.
- Full ladder re-census WITH the fix: **0 regress; the 10 previously-masked/failing cells (UNATCO N8-16,
  WanChai N19) are FIXED**; maskless full-corpus validation is **60/60 PASS** (`stage3-validate.py` /
  `validate_results.txt`).

So the standalone descent was necessary AND sufficient once the child convention was right — no
multi-week tree-wiring rewrite. One faithfulness gap remains: native still uses the linear scan for the
vertex-RING adds (R=0.015) inside CSG; the surf-base descent is what the removed mask needed. Everything
below is the historical diagnosis that led here.

## COST CENSUS (measured across the ladder; read first)

`stage3-cost-census.py` built native BOTH ways for 52 ladder cells and gated each nomask
(`census_results.txt`). With the descent ON (`UEDCLI_BSPCSG_FNV_DEDUP=1`, surf-base only):

| bucket | count | cells |
|--------|-------|-------|
| **REGRESS** (off PASS → on FAIL) | **21** | UNATCO N2-7, WanChai N2-16 |
| FIX (off FAIL → on PASS) | **0** | — |
| both FAIL (nomask, pre-existing x=448/N19) | 10 | UNATCO N8-16, WanChai N19 |
| clean (no change) | 21 | NYC_Bar N1-16, Island N8/12, OceanLab N3, UNATCO N1 |

**The regression class is POINT-TABLE ORDER, not value.** Every regressor inspected (UNATCO N2/N5/N7,
WanChai N2) has IDENTICAL node/surf/point COUNTS and values — only the `Model.Points` array and the
`Surf.pBase` indices are PERMUTED (e.g. UNATCO's first brush's z=414 corner trio added in a different
order). No node-W or soup-value divergence. So the descent is not creating wrong points; it changes the
ORDER points are first appended during incremental CSG, and `compact_points_to_surf_bases` + the
linear-scan repartition bake that perturbed order into a different final table than the editor's.

**Why this is the real cost.** Native's baseline linear scan already reproduces the editor's final
Points table (order + values) EXACTLY on every clean cell — the only thing it misses is the x=448 near-tie
(masked). The editor's final order is an emergent property native's all-linear pipeline matches for free;
the scoped incremental descent BREAKS it because native's incremental add-order under the descent ≠ the
editor's. To fix the order faithfully, native's incremental CSG must reproduce the editor's tree AND run
the descent CONSISTENTLY through repartition (not linear there) — i.e. the whole dedup pipeline, matching
the editor step for step. That is the multi-week incremental-CSG-core rework, now measured: 0 cells are
net-improved by the scoped descent, 21 regress.

**0 FIX is the headline:** even UNATCO N8 (the target) is not fixed — the descent corrects x=448's value
but the Z=240 value-class divergence AND the order permutation both land, so N8 stays FAIL. The descent as
a standalone/scoped change is strictly worse than the linear scan on this corpus.

**Distinct root causes:** two classes. (A) the order permutation — systemic, one mechanism (descent
add-order ≠ editor's), hitting ~2 ladder levels broadly (UNATCO, WanChai; NYC_Bar/Island/OceanLab immune,
their geometry doesn't trigger the reorder). (B) the value near-tie (Z=240 at UNATCO N8) — rarer, a real
tree-structure difference. Both need the same underlying fix (native tree + consistent descent = editor).

**Realistic bound: WEEKS, high risk.** The faithful fix is not a handful of local face fixes — it is
making native's incremental point-add order and near-tie decisions match the editor's across the corpus,
which the linear scan currently gets right for free. Options for the owner: (1) commit to the multi-week
consistent-descent + tree-matching rework; (2) keep the x=448 mask (the linear scan is otherwise
editor-exact) and treat WanChai N19 the same way; (3) a scoped raw-base carry for ONLY the masked near-tie
faces (previously tried, regressed siblings — but the census shows those siblings are order-only, so a
carry that touches value-not-order might be re-examinable). Recommendation: (2) unless full byte-parity on
the near-ties is worth multi-week core work.

## Z=240 root cause (deliverable 2)

The x=448-sibling that regresses under the descent (UNATCO N8): native's descent MISSES the point
`(0,-3e-5,240)` that the editor SNAPs (`d=2.16e-5`). That point is native **node 44, coplanar-chained
(iPlane) under node 23 — the FIRST Z=240 face committed, which belongs to a FAR room** (iActor 3,
surf-base XY≈(-288,-1968); `traces/n8_native_z240_tree.txt`). In a BSP all same-plane faces chain under
the first node on that plane, so actor-5's `(0,-3e-5,240)` face becomes an iPlane-successor deep in the
far-room subtree; the radius-pruned descent, heading toward the query `(0,0,240)`, prunes node 23's
subtree (query far in XY from node 23's own region) before it walks the coplanar chain to node 44. The
editor SNAPs, so its tree keeps that point reachable near the query — a **coplanar-chain placement
difference**: which Z=240 face is the chain head / where the chain sits relative to the query. Naming the
exact editor placement needs the editor's Z=240 tree (the winedbg condition on native's base bits
`x=0/y=0xb7800000/z=0x436fffff` did not fire — the editor computes a slightly different raw base for that
face, so broaden the condition to dump it). But the class is clear: it is the SAME "native incremental
tree ≠ editor" root as the order permutations, surfacing as a value miss instead of a reorder.

## Stage 3 checkpoint result (Increment 3 — MEASURED; read first)

The pruned descent was implemented (`find_nearest_vertex` in `bspcsg.rs`, `test_fnv_*` green) and
switched on for incremental surf-base adds (`UEDCLI_BSPCSG_FNV_DEDUP`, DEFAULT OFF; restricting to
surf-base tol=0.002 avoided a point-table reorder that the ring adds caused). N8 result:

- **x=448 is FIXED faithfully**: the descent MISSES at the actor-6 `-X` add (keeps 447.99985 distinct),
  so node-plane W = −447.99985 and the soup base match; `Model.Points` stays **76/76**. The stage2b
  hypothesis holds where native's tree matches the editor's.
- **BUT it REGRESSES the sibling Z=240 face** — the board's predicted "regresses siblings the editor
  legitimately snaps". At the actor-6 `+Z` add (query `(0,-1.5e-5,239.99998)`) native's descent MISSES
  the point `(0,-3e-5,240)` (`d=2.16e-5`), which the editor SNAPs. That point is native node 44,
  **coplanar-chained (iPlane) under node 23 — a FAR-room node (iActor 3, XY≈(-288,-1968))**; the descent
  prunes node 23's subtree (query far in XY) before reaching node 44's coplanar chain. The editor's tree
  reaches the same point via a different path. Native tree: `traces/n8_native_z240_tree.txt`.
- Net: `gate_nomask` and even the **masked gate now FAIL** at N8 — native's Z=240 soup base is a raw
  non-table value, so the existing tie-mask (which requires both sides to be real table points) can't
  cover it. **This is a net regression, so the switch is left DEFAULT OFF.**

**Verdict: the pure-descent hypothesis is REFUTED as a standalone fix.** The linear scan was accidentally
robust to native/editor tree differences (it finds the point regardless of tree); the descent is faithful
but FRAGILE to them — it fixes the adds where the trees already agree (x=448) and exposes the adds where
they differ (Z=240) as new divergences. So the faithful fix needs the descent AND native's incremental
tree to match the editor's at the offending adds. Better-scoped than a full rewrite (most adds already
agree — the final tree is byte-identical; N8's only offender is the Z=240 coplanar-chain placement), but
NOT the cheap "just swap the dedup" the stage2b section below hoped for. The offending difference is
concrete: native coplanar-chains the `(0,-3e-5,240)` face under a far-room Z=240 node; the editor keeps
it reachable near the query. Next step for whoever resumes: dump the editor's Z=240 tree (the winedbg
condition on native's base bits x=0/y=0xb7800000/z=0x436fffff did NOT fire — the editor computes a
slightly different raw base for that face, so broaden the condition) and localize the coplanar-chain /
`FilterWorldThroughBrush` wiring difference. Owner decision: pursue the localized tree-matching, or keep
the x=448 mask.

## What Stage 2b changed about the diagnosis (read first)

The divergence is NOT an expensive incremental-tree-wiring difference. Proven in stage2b:

- At the divergent add (actor-6 `-X` surf-base, query `(447.999847, 64.000107, 0)`, R=0.002) the
  editor's live tree and native's live tree are **structurally equivalent**: both have nodes 48/49/50
  (actor-5 `+Y`, surf-base = the corner `(448.00006, 64.00011, 0.00003)`), alive and linkage-reachable
  from root 0.
- The editor's `FindNearestVertex` MISSES anyway because its descent **prunes by the current radius R**:
  from root 0 it follows a pd-directed path and only recurses a child / tests a node's verts when the
  query is within R of the splitting plane. The query is 416 / 4.0 / 1552 uu from the planes on the way
  to node 48, so node 48's subtree is pruned and never tested — even though node 48's own plane distance
  is ~0. `descent_sim.py` reproduces this MISS over BOTH the editor's and native's dumped trees.
- Native's bug is that `bsp_add_point` uses a **linear scan over all `Model.Points`**, which finds
  `448.00006` (d=2.158e-4 < R) regardless of the tree, and SNAPS. Same tree, wrong dedup.
- The earlier reverted port (`f046d97`/`ba23319`) failed because it implemented an **UNPRUNED**
  full-tree traversal (pushes iFront/iBack/iPlane unconditionally), which visits node 48 and HITs. That
  was an implementation bug, not evidence that tree-wiring must change.

**So the primary fix is the dedup ALGORITHM: port the faithful radius-pruned `FindNearestVertex`
descent, replacing the linear scan. Native's tree is already correct at the divergent add.**

Residual risk is bounded and empirical (below), not a foregone multi-week rewrite.

## The algorithm to port (decoded, Engine.dll `0x1adb60`; see `stage2/decode_fnv_index_lifecycle.py`)

`FindNearestVertex(Model, query, tol)` descends from root iNode=0 over the live `Model.Nodes`:

```
best = -1 ; R = tol
recurse(iNode):
  while iNode != -1:
    n  = Nodes[iNode]
    pd = n.Plane.PlaneDot(query)          # n.X*qx+n.Y*qy+n.Z*qz - n.W
    if pd >= -R and n.iBack != -1:        # back half within radius
        d = recurse(n.iBack); if d>=0: best=d; R=d        # shrink R on a find
    if -R < pd < R:                       # inside the slab: test this node...
        consider(Points[Surf[n.iSurf].pBase])             # surf-base
        for v in n.iVertPool..+n.NumVertices: consider(Points[Verts[v].iVertex])
        for cop in n.iPlane-chain: consider its surf-base + vert-pool  # coplanar nodes
    iNode = (pd <= R) ? n.iFront : -1     # front half within radius (tail loop)
  return best
consider(p): d2=(dy*dy+dx*dx)+dz*dz (editor summation order); if d2<R*R: best=sqrt(d2); R=best
```

Key facts the port MUST honor (the earlier port broke the first two):
- **Prune**: recurse iBack only when `pd >= -R`; recurse iFront only when `pd <= R`; test a node's
  points only when `-R < pd < R`. This is what makes the descent MISS a within-tol point behind a far
  plane — the whole mechanism. An unpruned traversal is wrong.
- **R shrinks** to the nearest found distance as the descent proceeds (tighter pruning after a hit).
- **Threshold per call site**: surf `pBase` add uses R=0.002 (SAME); node vertex-RING add uses R=0.015
  (NEAR) — native already passes these via `bsp_add_point_tol`.
- Empty `Model.Nodes` (`Num==0`) → immediate MISS (append new).
- Coplanar iPlane-chain nodes are tested too (stage1 `decode_fnv_traversal.py`).

## Order of work

1. **Port the descent** as `find_nearest_vertex(model, v, tol) -> Option<usize>` in `bspcsg.rs`, faithful
   to the pseudocode (with the pruning). Add a cargo unit test that runs it over the two committed
   stage2b tree dumps (or a small hand-built fixture) and asserts MISS at the divergent query — reuse
   `descent_sim.py`'s logic as the oracle.
2. **Switch `bsp_add_point_tol`** from the linear scan to `find_nearest_vertex` (keep the trace behind
   the existing env). Points only — `bsp_add_vector` (Vectors pool) stays a scan; it is a different pool
   with no tree.
3. **Measure N8 immediately** (the decision gate): build native N8, diff vs `ref_N8`.
   - Point table stays **76/76** AND `gate_nomask.py` PASSES → the fix is JUST the dedup method. Done for
     N8; go to step 5.
   - Point table grows (the earlier `76→81` risk) → step 4.
4. **If the table grows**: for each surviving extra distinct point, dump native's tree at that add
   (`UEDCLI_BSPCSG_POINT_TRACE` + `_TREE`, already built) and the editor's tree at the same add (the
   stage2b winedbg recipe), and run `descent_sim` on both. Two cases per add:
   - both trees MISS but native's linear-history left a stray point → a repartition re-dedup ordering
     issue; fix the repartition to also use the descent.
   - native's tree differs from the editor's at that add (descent visits a node the editor's doesn't, or
     vice versa) → a SPECIFIC, local tree-wiring fix (`FilterWorldThroughBrush` fragment/link order or a
     `bspCleanup` splice), targeted at that add — not a wholesale rewrite. Expect a handful, if any.
5. **Extend to the ladder**: run all 5 levels N=1..current + UNATCO N8 + WanChai N19 through the gate
   with NO mask. WanChai N19 is the same class (step-face linear-snap) and should fall to the same fix.
6. **Retire the mask** (`parity_gate.py` `NODE_W_DEDUP_TOL` + `_node_w_tie`/`_poly_base_tie` + the tie
   tests) once N8 and N19 pass without it; update `NATIVE-MATERIALIZE.md`'s exclusion set. One opus
   review.

## Validating incrementally / holding the corpus green (the 76→81 trap)

- The dedup change touches **every** point add across the whole corpus, so validate per level and per N,
  not just N8. Gate each level at each N against its editor ref before advancing; keep every commit
  bisect-green.
- Run the descent at BOTH the incremental CSG dedup and the final repartition re-dedup (the earlier port
  showed a wrong final-table size, i.e. the repartition dedup matters too).
- Watch the point-table COUNT per level as the tripwire: a count change from the linear-scan baseline is
  the signal that native's tree diverges from the editor's at some add — localize with the stage2b
  probe rather than guessing.
- Keep `cargo test` green (fast); it catches gross regressions in the descent unit test immediately.

## Smallest first increment that proves the approach on N8

Implement step 1 (the pruned descent) + a cargo test that asserts, over the committed
`stage2b/traces/n8_editor_tree_dump.out` and `n8_native_tree_dump.txt`, that the descent returns MISS at
the divergent query (the current linear scan HITs). That single test — green — proves the algorithm is
faithful before any behavior switch. Then step 2 + step 3's N8 measurement is the go/no-go: if N8's table
stays 76 and the gate passes with no mask, the class is fixed cheaply; if not, step 4 scopes exactly how
much tree-wiring (likely small) remains.

## Effort / risk

- **Best case** (N8 table stays 76 after the switch): small — a self-contained dedup-algorithm change +
  gate re-verify across the ladder. Days, not weeks.
- **Worst case** (table grows at a handful of adds): each is a localized tree-wiring fix scoped by the
  probe; still far short of a full incremental-core re-derivation. The old "multi-week rewrite" estimate
  assumed the whole tree had to change — stage2b shows it does not at the divergent add.
- Main risk to watch: a table-count change rippling across the green corpus (every add re-dedups). The
  per-level/per-N gate + the point-count tripwire contain it; never merge a stage that isn't corpus-green.
