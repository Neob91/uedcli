+++
priority = "p1"
kind = "debug"
summary = "Front 2 re-characterized: diffuse repartition-order divergence amplified by T-junction orphan-garbage inflation, not axis-aligned over-split"
+++

# Front 2 re-characterized: diffuse repartition-order divergence amplified by T-junction orphan-garbage inflation, not axis-aligned over-split

Resumed from `unatco-detail-brush-pass-staging-generalized` (Front 1, closed) and
`PARITY-STATUS.md`'s "Front 2" pointer, which characterized the post-repartition gap (pre-Front-1)
as an **axis-aligned repartition OVER-split** (+57 nodes) and flagged it "large, oracle-driven, no
known static castle-safe fix." Task: re-measure fresh (the old number is stale — Front 1 flipped the
sign) and determine bisectability. No code changed; this is a scoping item only.

## Fresh measurement (this session, full 734-brush UNATCO, native `build_geometry_bspcsg` vs a
freshly-built real-editor golden `/tmp/UEDGolden_unatco_full.dx`, same bare-`MAP REBUILD` basis
`build_ued_golden.py` documents)

Raw array-size deltas confirm the numbers already in the Front-1 done item: nodes 6247 vs golden
6314 (-1.1%), surfs 3616/3616 (exact), verts 93187 vs golden 76488 (**+21.8%**), points 10691 vs
golden 10752 (-0.6%).

**The +21.8% Verts figure is misleading — it is not a geometry divergence.** Both engines' `Verts`
pool is append-only and never compacted after `bspOptGeom`'s T-junction pass (`insert_ring_vertex`,
`uedcli-native/src/bspoptgeom.rs:442` — old ring slots are orphaned in place, by design, matching
the editor). Decomposing the pool into LIVE slots (`sum(node.num_vertices)`, i.e. the vertex count
actually referenced by the final tree) vs orphaned garbage:

| | nodes | live verts (Σ NumVertices) | live points referenced | Verts pool (on-disk) | orphaned |
|---|---|---|---|---|---|
| native | 6247 | 28506 | 8444 | 93187 | 64681 (69.4%) |
| golden | 6314 | 28785 | 8513 | 76488 | 47703 (62.4%) |
| delta | -1.1% | **-1.0%** | **-0.8%** | +21.8% | **+35.6%** |

Average live vertices/node is **4.56 in both** (2-decimal match). The editor's own pool is *also*
62.4% orphan garbage — this is expected, editor-faithful behavior, not a native bug in itself. The
entire +21.8% Verts residual is orphan-count inflation, not a live-topology difference: the actual
built geometry (node count, live vertex count, live point count) is within ~1% of golden across the
board, tightly clustered — not the diffuse blow-up the raw Verts % suggests.

## Is the residual bisectable? No — it is genuinely diffuse

Order-independent plane-multiset diff of the two FINAL (post-repartition, post-optgeom) trees
(key = splitting plane rounded to 1e-2, matching `node_diff.py`'s method): **5824 shared / 423
only-native / 490 only-editor**, spread across **264 distinct only-native plane keys and 266
distinct only-editor plane keys** — no dominant culprit. The single largest discrepancy is one
plane appearing x28 more on the editor side (`z=96`, a floor/ceiling); most are x1-x10. Both
axis-aligned AND rotated/angled planes appear on both sides (e.g. `(0.0, 0.86, 0.51, -312.81)
only-editor` — a ramp/stair face), so this is not purely the "axis-aligned" pattern the old +57
characterization named; that description is stale.

~7% of nodes (423/6247 native, 490/6314 editor) sit on a plane the other side's multiset doesn't
match, scattered across 260+ distinct planes map-wide. This rules out a Front-1-style bisection
(walk an N-brush prefix to the first diverging brush): there is no single first divergence to walk
to — `bsp_build`/`SplitPolyList`/`FindBestSplit` is making a large number of small,
locally-plausible-but-different split choices throughout the whole repartition, not one wrong
decision that compounds forward. This matches the task's diffuse-divergence hypothesis, not the
bisectable one.

## Why the live-topology gap (~1%) becomes a Verts byte-gap (+21.8%)

`eliminate_tjunctions` (`bspoptgeom.rs:184`) walks `model.nodes` once in tree order; T-junction
eligibility per edge depends on a **live** shared-vertex table that mutates as earlier nodes in the
walk get spliced (`bspoptgeom.rs:308-317`, "LIVE table update" comment). So a small, diffuse
difference in which nodes exist and in what order (the ~1% repartition residual above) changes
*which* edges the dup-guard (`edge_shared_elsewhere`) treats as already-shared at the point each is
visited — this can trigger extra/differently-timed `add_point_link` splice events even when the
final live ring content converges close to the editor's. Because every splice event reallocates
and orphans a whole ring copy (`insert_ring_vertex`, never in-place), a modest, diffuse split-order
difference gets non-linearly amplified into a much larger orphaned-Verts count. This was verified
native-side only (`UEDCLI_OPTGEOM_DEBUG=1`: 4406 unshared-edge triggers, 3536 total ring-insert
events over the full map) — there is no live-editor equivalent counter yet; getting one needs a new
gdb probe inside `bspOptGeom`/`AddPointLink` (editor-tree-oracle's existing probes all target the
FIRST incremental CSG phase, not this second pass), a genuinely new decode task.

## Read on tractability

**Not a quick, isolated fix.** Two independent, compounding problems, both real:
1. `bsp_build`'s repartition still disagrees with the editor's `FindBestSplit` at ~7% of nodes,
   diffusely (264+ distinct planes, no dominant brush/region) — this is the `sections/92-*.md`
   §36/§53 "deep lever," now confirmed genuinely diffuse rather than a single large defect, and
   confirmed NOT purely axis-aligned.
2. `eliminate_tjunctions`'s append-only, order-sensitive design (itself editor-faithful and
   correctly reproducing the *shape* of the editor's own orphan-garbage behavior) turns that
   diffuse ~1% residual into oversized byte-level noise in the Verts array specifically.

Closing (1) fully would need matching `FindBestSplit`'s exact scoring/tie-break behavior across
264+ separate node-choice disagreements — the "oracle-driven, no known static fix" character
`PARITY-STATUS.md` already flagged, just now precisely bounded (small % of nodes, not a
systemic +57 overshoot). Closing (2) without (1) is not possible: the orphan-count gap is a
downstream artifact of (1)'s ordering, not an independent bug to patch.

**Not pursued further here** (out of this item's scope, per the task's "scope it, don't force a
fix" instruction). Superseded, in scope, the stale board item
`dev/docs/board/inbox/next-divergence-the-repartition-over-splits` (older, smaller-scale numbers
predating Front 1 — 1251 vs 1156 nodes, a different test basis, not full UNATCO); leaving that item
in place since it documents a real prior finding, but this item is the current fresh read on the
full 734-brush map.

**If picked back up**, the next concrete step is a live gdb probe inside `bspOptGeom` (editor
`AddPointLink`, `0x325e0`) to get the editor's own splice-event count/order at UNATCO scale, to
confirm whether the amplification hypothesis is right or whether the editor's own optgeom pass is
*also* order-sensitive in a way that happens to match its own repartition order exactly (i.e.
whether orphan-count parity is achievable at all without first closing the ~7% split-choice gap).
