+++
priority = "p2"
kind = "debug"
summary = "FindBestSplit divergence forensic dive: 17 real tree-split points, root cause is bspMergeCoplanars fragment-shape drift, not FindBestSplit itself"
+++

# FindBestSplit divergence forensic dive: 17 real tree-split points, root cause is bspMergeCoplanars fragment-shape drift, not FindBestSplit itself

Follow-up to `front-2-re-characterized-diffuse-repartition` and
`editor-unatco-repartition-soup-size-unknown`, which left the ~448-node / ~260-plane UNATCO
repartition gap characterized as "diffuse, no dominant culprit" — genuinely ambiguous between a
`FindBestSplit` logic bug and upstream float noise. This item resolves the ambiguity with concrete
data: it is neither. The candidate-selection algorithm (stride, eligibility, score formula,
tie-break) is confirmed correct against real editor choices; the divergence traces to specific,
small, NAMEABLE `bspMergeCoplanars` fragment-shape differences (8 of 1633 source surfaces) plus a
handful of local reorder perturbations, whose effect on `SplitPolyList`'s inherently-approximate
GOOD-mode scoring is amplified into the visible node-count gap.

## Method: tree-STRUCTURAL comparison, not flat plane-multiset

Built native's full 734-brush UNATCO (`nodes=6366`, matches the prior session's post-candidate-fix
state) and parsed the real editor golden `/tmp/UEDGolden_unatco_full.dx` (`nodes=6314`) with the
same `uedcli.native.umodel` parser both sides already use. Instead of the flat plane-multiset diff
the prior items used (which can't tell "260 independent bad picks" from "a few bad picks whose
subtrees cascade into 260 descendant differences"), this pass reconstructs both trees from
`(i_front, i_back, i_plane)` and walks them SYNCHRONIZED from the root: at each pair of
corresponding nodes, if the planes match (tol), recurse into the coplanar chain then both children;
if they don't, record a divergence ORIGIN and stop descending that branch (everything below is
input to a different splitter, not comparable node-for-node).

**Result: only 17 independent divergence origins in the entire tree**, not 260+. Of those, **11 are
not real choice differences at all** — same `NumVertices`, and the plane differs by ~1e-5 in the
normal and ~0.01-0.02 units in the offset (Deus Ex units, so this is millimeter-scale). These come
in two exact, repeated value-families — `(0.7071030…, 0.7071099…)` vs `(0.7071091…, 0.7071045…)`
(a 45° wall, ×3) and `(0.5546910…, 0.8320559…)` vs `(0.5547001…, 0.8320503…)` (a 2:3-slope wall,
×5) — meaning this is a genuine but SEPARATE, already-small precision drift in a rotated brush's
CSG-computed normal (not sub-ULP — roughly 100 ULPs at f32 — bigger than the already-characterized-
negligible residual from the earlier normal-twin campaign, so worth a future look, but it is NOT
what drives the node-count gap: raising the comparator tolerance to 0.05 (still far below any real
geometric feature) makes all 11 vanish and the matched-node count rises 4582→4751 with the same max
matched depth (68) — they were never blocking real structural comparison).

**That leaves exactly 6 real divergence origins**: 2 where native and the editor pick outright
different splitter planes (at tree depth 2 and 3 — i.e. very early, so each origin's subtree can be
large), and 4 where a node's OWN splitter matches but the length of its coplanar chain differs by
one entry (one side has an extra exactly-coplanar poly the other doesn't).

## The 2 real splitter-choice divergences: NOT a FindBestSplit bug

Instrumented `find_best_split_exact`/`split_poly_list` (`uedcli-native/src/bspcsg.rs`) with a new
`UEDCLI_REPART_FBS_DUMP` env var (follows the existing `UEDCLI_BSPCSG_*` dump pattern) that logs
every repartition `SplitPolyList` call's full candidate table — one row per stride slot, with the
resulting `i_node` so a specific divergence point can be pulled out by array index. Pulled the two
real divergences:

- **Depth 2 (`root→Back→Front`, native `i_node=812`, `NumPolys=570`)**: native's full candidate
  table contains the plane the real editor actually chose at this exact tree position
  (`(0,1,0,594.0002)`, at candidate slot 252) — bit-identical, not approximate. Its native-computed
  score is **24.0**. Native's own pick (`(1,0,0,-1616)`, slot 280) scores **12.0** — genuinely
  better by native's own byte-verified formula, not a near-tie.
- **Depth 3 (`root→Front→Back→Back`, native `i_node=1492`, `NumPolys=321`)**: same pattern, sharper.
  The editor's actual chosen plane (`(1,0,0,-1904)`, slot 16) scores **24.0**. Native's pick
  (`(1,0,0,-1500.0027)`, slot 256) scores **0.0** — a perfectly balanced split (front=10, back=10,
  zero splits).

In both cases the editor's real choice IS present in native's candidate list, at a correctly-
sampled stride slot (no re-run of the already-fixed slot-scan bug), with a plane that matches
bit-for-bit — so this is not eligibility, not stride, not tie-break, not the score formula's
operand order (all already independently disassembly-verified in the prior session). Native's
algorithm, run on native's own soup, provably finds the objectively better-scoring candidate by a
wide margin (2x and infinite ratio, not float noise). The only way the real editor still picked the
worse-by-native's-formula candidate is that **the editor's own soup, at this exact point in the
tree, differs from native's** enough to change the front/back/splits tally for these same two
candidate planes — i.e. the bug (to the extent it is fixable at all) is upstream of
`FindBestSplit`, in what poly list reaches this call.

## Traced upstream: the root repartition soup, poly-for-poly

New oracle `harness/editor-tree-oracle/repart_soup_full_unatco.py` (same breakpoint VA `0x1004a041`
as the existing `editor_polys_oracle.py`/`repart_numpolys_unatco.py`, extended to dump every poly's
full `Base`/`Normal`/`NumVertices`/`iLink`/`PolyFlags`, not just the count) captured the editor's
real 2514-poly root soup at full UNATCO scale — the ONE thing no prior session had (`logs/repart-
soup-full-unatco.log`). Compared poly-for-poly against native's own soup dump
(`UEDCLI_BSPCSG_SOUP_ORDER`, 2504 polys):

- **The set of source surfaces (`iLink`) is IDENTICAL**: 1633 distinct ilinks on both sides, 0
  only-native, 0 only-editor. No missing/extra source face anywhere — the soup-COMPOSITION-gap
  worry from the prior item is refuted at the surface-identity level.
- **The VISIT ORDER is 99.9% identical.** Deduplicating each array into its sequence of distinct
  ilinks-in-order and diffing: 2101 (native) vs 2104 (editor) entries, similarity ratio 0.9988, only
  5 non-equal diff opcodes total (one small local delete/insert cluster near visit-index 441-451,
  one single insert near 1545). This rules out any wholesale reordering.
- **The entire +10-poly count gap (2514 vs 2504) traces to exactly 8 of the 1633 shared surfaces**
  where `bspMergeCoplanars` groups the SAME source face's fragments differently: 4 with a different
  FRAGMENT COUNT (e.g. `iLink=1144`: native fuses a flat Z=560 face into ONE 10-vertex polygon;
  the editor keeps it as FOUR separate 4-vertex quads at the identical plane — `iLink=1163`: native
  1 fragment vs editor 5) and 4 with the same fragment count but different total vertex sum (e.g.
  `iLink=300`, the first anomaly in array order, position 37: native nv=5, editor nv=4, same plane,
  same `iLink`).

## Conclusion

`FindBestSplit`/`SplitPolyList` (`bspcsg.rs`) is not the bug. Given the same input it picks the
objectively best-scoring candidate by its own byte-verified formula, and the editor's actual
choices are present, correctly sampled, in native's own candidate table. The 448-node/260-plane
gap is the diffuse-looking DOWNSTREAM shadow of a small, concrete, named set of `bspMergeCoplanars`
grouping differences (8 of 1633 surfaces, e.g. `iLink=1144`/`1163`/`300` above) plus ~5 tiny local
reorder perturbations — amplified by GOOD-mode's own approximate, strided scoring (spec §5.2
already documents this heuristic as sample-sensitive by design; a poly landing on one side of a
stride boundary vs the other can flip which candidate wins even on a near-identical soup). This
also means the 17-origin structural-divergence count, not the 448/260 flat-multiset count, is the
right way to size this class of gap going forward.

**Not fixed here** — out of this item's scope (a `FindBestSplit` forensic dive; the actual lever is
`bsp_merge_coplanars`/`try_to_merge`/`merge_group_pred`, a different function, and CLAUDE.md's
"measure, stop, report, wait for the yes" applies to opening that as new work). A secondary,
smaller, independent finding (11 of the original 13 flagged plane divergences, before the tree-
structural narrowing): a real but small (~100 ULP, not sub-ULP) normal-precision drift on rotated
brushes at exactly two repeated slope families (45° and 2:3), inherited from wherever that brush's
CSG normal is computed — separate from the merge-shape issue, also not chased further here.

## Tooling landed (env-gated, follows the existing `UEDCLI_BSPCSG_*` pattern; `cargo test --release` 54/54, unchanged)

- `uedcli-native/src/bspcsg.rs`: `UEDCLI_REPART_FBS_DUMP` — dumps every repartition `SplitPolyList`
  call's full candidate table (`find_best_split_trace`), tagged with the resulting `i_node` so a
  specific divergence point can be pulled out of the ~6366-call log by array index.
- `harness/editor-tree-oracle/repart_soup_full_unatco.py` — live gdb capture of the editor's real
  root repartition soup (all 2514 polys, full geometry+flags, full UNATCO scale); cached at
  `logs/repart-soup-full-unatco.log`.

## Repro (offline, no live editor needed once the two model dumps exist)

1. Native: `uedcli_native.build_geometry_bspcsg(brushes)` over the `/tmp/bsp-parity-proj/maps/unatco`
   trunk (734 world-CSG brushes; see `build_native_unatco.py` for the pattern, paths need
   environment-specific substitution — the original hardcoded `/home/neob91/...` paths in that
   script are stale for this environment) → `uedcli_native.serialize_model` →
   `uedcli.native.umodel.parse_model_body`.
2. Editor: `uedcli.native.umodel.parse_model_body` directly on `/tmp/UEDGolden_unatco_full.dx`'s
   largest `Model` export (no live editor needed to READ a golden that already exists).
3. The tree-structural synchronized walk and the soup poly-for-poly comparison are both ~50-line
   throwaway scripts over the two parsed `Model` objects — not committed (pure analysis, no
   reusable oracle infrastructure beyond the two items above).
