+++
priority = "p1"
kind = "debug"
summary = "Area51 Entrance's entire +85 node/+51 leaf residual live-localized (removal test) to Brush1852. The 'classify-BSP over-fragmentation, 26 vs 17 terminal fragments' MECHANISM claim is now doubted: a coordinator cross-check + evidence (own trace collision, confirmed MAP-REBUILD repartition contamination, and — bigger — native's OWN pipeline discards the CSG-incremental tree and rebuilds from a poly soup before final Nodes/Surfs/Verts) all point at the wrong pipeline stage having been measured. Full-level node-owner attribution shows Brush1852 not even in the top 40 of 548 differing brushes (diffuse, same class as NSFHQ04/UNATCO/Training Final). No fix shipped; traversal-order hypothesis abandoned as premature. Training Final open, static lead unconfirmed — a live-search attempt was blocked by a reproducible build_ued_golden.py operational stall (missing GC-dialog dismissal + borderline CPU-idle threshold), not level content."
+++

# Area51 Entrance residual localized to Brush1852; Training Final still open

Breadth-sweep check (per the standing worst-first queue): does the shipped `CsgOper::Active` fix
(`528e602`) retroactively close any of Area51 Entrance's or Training Final's residual? **No** — neither
level's first world-CSG brush (or any brush) lacks a `CsgOper=` property; both are pure Add/Subtract.
Full detail, live evidence, and the decisive removal test: `dev/docs/native-materialize-findings.md`,
search "Area51 Entrance / Training Final breadth check".

## Area51 Entrance — localized, mechanism open

Live prefix binary search (reusing `dev/docs/spikes/2026-09-01-fc08-nsfhq04-csgactive/harness/
prefix_search_lib.py`, the method that found FreeClinic08's `Brush586`/NSFHQ04's `Brush8321`)
localizes Area51's entire `d_nodes=+85 d_leaves=+51` (surfs already exact) residual to ONE brush:
prefix n=506 (`Brush1851`) is byte-exact; n=507 (adding `Brush1852`) diverges.

**Decisive test, live-verified**: removing `Brush1852` from the FULL 1343-brush level closes the
residual to **d_nodes=+0 d_surfs=+0 d_leaves=+0** on both native (in-process) and a fresh
`build_ued_golden.py --world-only --no-light --no-obj-load` editor rebuild. One brush fully explains
the level's entire structural residual — same shape as FreeClinic08's `Brush586`.

**Not yet root-caused at the full-level scale, but narrowed live this round (2026-09-01).** Adding
`Brush1852` (`CsgOper=CSG_Add`, 6 polys, `Rotation=(Yaw=-49152)`, no mirror scale) to the 1342-brush
base: native gains +135 nodes/+51 leaves, the real editor gains only +50 nodes/+0 leaves. It is one of
4 placements of an identical-shape prop (`Brush1849`/`1850`/`1851`/`1852`); the first 3 (different
`Location`s) build byte-exact, so the divergence is not the brush's own geometry but something
position/context-dependent about how it CSGs against the accumulated world tree.

Live gdb-traced this round (real editor's `AddBrushToWorldFunc`, `Editor.dll` RVA `0x31770`, vs
native's `bspcsg.rs::leaf_func`) at the n=506→507 prefix transition (Brush1852 is the last brush of
the exact n=507 prefix, so its own incremental CSG call is cleanly isolated). Result:
**the keep/discard decision logic is disassembly-confirmed byte-identical** (same `Filter==0/2` add
unconditionally, `Filter==5` add-unless-`PF_Semisolid` gate, same `bspAddNode` call signature). The
divergence is instead that **native's classify-BSP descent produces 26 terminal fragments for
Brush1852's 6 polys against the n=506 world, vs the editor's 17** (14 kept/12 discarded vs 13
kept/4 discarded) — over-fragmentation during `FilterEdPoly`'s split, not the leaf callback. One
authored poly (`i_brush_poly=4`) alone accounts for 10 of native's 26 fragments. The "editor absorbs
with 0 new leaves" full-level number is NOT reproduced at this reduced prefix scale (editor keeps 13
fragments here, not 0) — that number is apparently specific to the much larger accumulated 1343-brush
context. No fix shipped — the exact node/plane where the two descents first disagree (Front/Back/
Split/Coplanar) is not pinned; needs a `FilterEdPoly`-loophead-level trace (like `editor_descent.py`)
on both sides, correlated finer than Base/Normal (full vertex list or split-path). See
`dev/docs/native-materialize-findings.md`, search "OVER-FRAGMENTATION" for full detail, including a
sandbox infrastructure fix (`docker cp` is broken here whenever a `:ro` mount is present; use `docker
exec -i ... cat` instead — affects `editor_tree_oracle.py`/`editor_descent.py` too).

## Training Final — open, static lead still unconfirmed; live-search attempt BLOCKED by infra, not content (2026-09-02)

Residual (nodes native=11227 golden=11122 `d=+105`, surfs exact, leaves `d=+13`) not live-localized
yet. Static per-brush node-owner attribution is diffuse (297/764 brushes differ, no dominant
outlier — same "wrong level of attribution" trap as everywhere else), but flags a lead: 4
near-consecutive small (6-poly `CSG_Add`) brushes `Brush907`/`909`/`911`/`915` (world-CSG idx 660-668)
carry large, partially-offsetting diffs (`+71`/`+71`/`-52`/`+77`).

**Attempted the live prefix binary search this round (2026-09-02, fresh worktree off `master`
`b23de44`); could NOT get a second live data point.** n=764 (full prefix) built and matched the
known residual exactly on the first try. Every OTHER prefix size tried — n=1 (2x), n=660 (2x), n=650
(1x) — timed out in `build_ued_golden.py`'s `_wait_idle`. Live-diagnosed (not just retried blind):
`wmctrl -l` inside the stalled container found the documented "Cleaning up..." GC `xmessage` dialog
present and blocking (`unrealed/quirks.md` "Stability") — `build_ued_golden.py` doesn't defensively
dismiss it, unlike `qualify.dump_obj_dependencies`. Manually dismissing it unblocked the dialog
symptom but the SAME container then sat borderline at the 30% CPU idle threshold for 25+ more
minutes without resolving — a second, distinct flakiness source, plausibly host contention from
this session's several other long-lived `uned-*` containers. Recurred across 3 unrelated prefix
sizes, ruling out a size/content-specific `MAP NEW` hang. Full detail: `dev/docs/
native-materialize-findings.md`, search "Training Final live prefix search: BLOCKED".

**The static lead (`Brush907`/`909`/`911`/`915`) is therefore still unconfirmed — neither
strengthened nor refuted this round.** Next attempt should either patch `build_ued_golden.py`'s
`_wait_idle` to call `Driver.dismiss_blocking_dialog()` defensively each poll (mirroring
`qualify.dump_obj_dependencies`), or run when this host has fewer concurrent agent sessions/editor
containers. Harness added this round (targeted `tf_probe.py` + generalized `tf_prefix_search.py`)
is ready to reuse once the build reliably completes.

## Harness

Committed under `dev/docs/spikes/2026-09-01-area51-training-final-residual/harness/`:
`area51_attrib.py`/`tf_attrib.py` (static per-brush node-owner attribution), `area51_prefix_search.py`
(prefix binary search), `area51_remove1852.py` (decisive removal test), `area51_subset.py` (N-brush
editor golden builder), `area51_addfunc_oracle.py` (live gdb trace of the editor's
`AddBrushToWorldFunc`), `area51_native_leaf_dump.py` (native's matching classify trace),
`area51_compare_tail.py` / `area51_frag_diff.py` (tail-diff and fragment comparison),
`find_addfunc_callers.py` (static caller-scan used to locate `FilterEdPoly`), `area51_dist_threshold_probe.py`
(the split-threshold-margin diagnostic), `tf_prefix_search.py` (generalized `prefix_search_lib.py`
binary search adapted for Training Final's 764-brush set), `tf_probe.py` (targeted single-prefix
probing with retry, for testing a specific window like the static lead without a full search).

## `angr` decompiler round (2026-09-01) — mechanism still open

Full detail: `dev/docs/native-materialize-findings.md`, search "angr decompiler tried on Brush1852".
Summary: `angr`'s decompiler is usable on `Editor.dll` (readable pseudo-C for a large self-recursive
SEH-wrapped function in seconds, though variable names are generic and a few instructions need raw
disassembly to trust). Located `FilterEdPoly` (`Editor.dll` `0x32bf0`) and `FilterLeaf` (`0x33130`) via
a static caller-scan for `AddBrushToWorldFunc`'s address-as-immediate (the call turned out to be
INDIRECT, so a `call`-target scan found nothing — scanning for the raw VA bytes as an immediate
operand found the one real reference instantly). Both addresses match what `bspcsg.rs`'s existing doc
comments already cite — independent confirmation, not a new function. Located `FPoly::SplitWithPlane`
directly via `Engine.dll`'s export table (`0x1518b0`, no caller-chase needed) and disassembly-confirmed
its two threshold constants (`0.25` default, `0.01` "VeryPrecise") match `fpoly.rs` exactly, and that
`FilterEdPoly` always uses the default. Live-measured Brush1852's `i_brush_poly=4` descent
(47 nodes traced) and found every classify margin from the `±0.25` threshold is `>= 0.25` — **ruling
out a float-precision epsilon-flip as the mechanism**. No fix shipped; the remaining lead is a
traversal-order/tie-break difference among coplanar-grouped nodes, not a classify or threshold bug —
needs the loophead-level dual trace the prior round already flagged as the next step.

## Full decompile round (2026-09-01) — port confirmed exact; narrows the traversal-order lead

Full detail: `dev/docs/native-materialize-findings.md`, search "coplanar `iPlane` node-chain is
NEVER read". Decompiled both `FilterEdPoly` and `FilterLeaf` in full (not just located them) and
checked every branch (vertex-overflow pre-split order, Front/Back tail recursion, the `Split` case's
front-before-back order, the out-of-place-coplanar rare path, the facing-test/`Coplanar` branch, and
`FilterLeaf`'s 3-way dispatch + 4-way cospatial truth table) against `bspcsg.rs` line-by-line — **no
divergence found in either function's own logic**. New fact: neither function ever reads a node's
`iPlane` (coplanar-sibling chain) field — the chain is walked only at INSERT time inside
`bsp_add_node`, never during classify, on either side. This means the leading "traversal-order among
coplanar nodes" hypothesis has no mechanism to act through inside `FilterEdPoly` itself — if real, it
must come from tree SHAPE (which node occupies a slot), not from the classify function choosing among
chain siblings. Corroborates the parallel `freeclinic08`/`nsfhq04` thread's independent "poly-list
ORDER, not scoring" finding: both threads now point upstream, at tree-build/insertion order, not at
the classify function. No fix shipped. Harness + saved pseudo-C:
`dev/docs/spikes/2026-09-01-filteredpoly-full-decompile/harness/`.

**Caveat flagged by the concurrent NSFHQ04 thread, unverified here**: `native-materialize-findings.md`
("NSFHQ04 6th continuation") reports this item's own "native kept: 26" `NADD`-based fragment count for
`Brush1852` may be inflated — the raw `NADD` dump is not per-brush-scoped (it also captures the
one-time world-level repartition's own node-seeding), where NSFHQ04's `LEAF add=true`-only count came
out 3.5x smaller than its own `NADD`-tail count for the analogous `Brush842` case, which then live-gdb
traced as BYTE-EXACT. Re-checking Area51's 26-vs-17 figure against a `LEAF`-only count (not attempted
this round) may show `Brush1852` is likewise exact, and the real residual lives in the one-time
world-level `bspBuildFPolys`/`bspMergeCoplanars`/`bspBuild` repartition — the same open class as
UNATCO's and freeclinic08/nsfhq04's residuals.

## Coordinator cross-check REDIRECTS this whole thread: the "26 vs 17" mechanism is likely measuring the wrong pipeline stage (2026-09-01)

Dispatched to run the loophead-level dual trace the previous entry flagged as next. A mid-session
coordinator cross-check (prompted by NSFHQ04's Brush842 turning out classify-BSP-EXACT once properly
scoped — their own raw count had been 3.5x-inflated by unscoped world-level repartition activity) asked
to re-verify this thread's scoping before continuing. It does not hold up, for three independent
reasons — full detail: `dev/docs/native-materialize-findings.md`, search "Brush1852 '26 vs 17
over-fragmentation' framing is very likely a wrong-pipeline-stage measurement".

1. A new properly-scoped-attempt editor trace (`area51_filteredpoly_descent.py`, `FilterEdPoly`
   loophead + `EdPoly->Normal` correlator) reproduced the SAME contamination class directly: a clean
   false-positive collision with an unrelated early brush sharing Brush1852 poly 4's exact face normal.
2. `build_ued_golden.py`'s own docs confirm `MAP REBUILD` = per-brush CSG + a GLOBAL, poly-count-
   sensitive `bspRepartition` pass (`stride=NumPolys/20`) — the prior round's editor "17" figure
   (`area51_compare_tail.py`, a raw AFUNC line-count delta between two separate builds) is exposed to
   exactly this.
3. **Bigger:** native's own `bspcsg.rs::build_geometry_bspcsg` (the real `level materialize` path)
   throws away the CSG-incremental tree (what this whole thread has been tracing) and rebuilds the
   final Nodes/Surfs/Verts from a flattened poly soup via a separate `bsp_build` repartition call.
   "Terminal classify-BSP fragment count" does not directly determine the final tree shape.

Full-level node-owner attribution (`area51_attrib.py`, path-fixed and re-run this round) shows
Brush1852 NOT in the top 40 of 548 differing brushes (abs-sum=2095 vs net=+85 — diffuse, massive
cancellation) — the same shape as NSFHQ04/Training Final, not a localized-to-one-brush shape. This does
NOT overturn the removal test (Brush1852's presence still closes the residual to exactly `+0/+0/+0`
when removed) — it overturns the INTERPRETATION that Brush1852's own CSG logic is the bug; a
brush-count-sensitive threshold in the LATER repartition stage crossing exactly when Brush1852 is added
would produce the same removal-test result with nothing wrong in Brush1852's own classify logic.

**No fix shipped. The traversal-order/tie-break hypothesis is abandoned as premature** — it targets the
same CSG-add stage this round's evidence says is not what determines the final tree. Next steps for
whoever picks this up: compare the POLY-SOUP stage (`bsp_build_fpolys`/`UEDCLI_BSPCSG_SOUP_ORDER`) for
Brush1852's own contribution, not the CSG classify-fragment count; if that matches, the divergence is
in the repartition stage's poly-order/threshold sensitivity — the same open class as UNATCO/NSFHQ04/
Training Final.

Harness added: `area51_filteredpoly_descent.py` (collected but flagged contaminated — kept for its
method), `area51_fep_seq_compare.py` (native/editor plane-sequence pairing, ready for a clean trace).
Fixed stale hardcoded worktree paths (pointing at now-deleted ephemeral sessions) in `area51_subset.py`,
`area51_addfunc_oracle.py`, `area51_frag_diff.py`, `area51_native_leaf_dump.py`,
`area51_compare_tail.py`, `area51_attrib.py` to self-resolve via `Path(__file__)`.

**Traversal-order hypothesis independently RULED OUT (not just deprioritized).** A parallel session's
full decompile read of `FilterEdPoly`/`FilterLeaf` (master `b23de44`) confirms the port is exact and
that neither function ever reads a node's `iPlane`/`iLink` coplanar-sibling chain during classify —
only `bsp_add_node`'s insert-time tail-walk touches it. Both sides are structurally blind to that chain,
so a coplanar/`iLink` traversal-order difference cannot be the mechanism, full stop. The same session
disproved NSFHQ04's analogous Brush842 hypothesis by live gdb trace (byte-exact, 19 vs 19) — the same
diffuse, no-dominant-outlier shape as this round's Area51 node-owner attribution. Open question for
whoever picks this up: is Brush1852 the SAME diffuse world-level-repartition-poly-order class Brush842
turned out to be? Not yet checked directly (needs either a same-session incremental single-brush-add
live trace or the poly-soup/repartition-stage comparison already flagged above) — the next concrete
step, not yet taken.

## Independent full-pipeline decompile pass (2026-09-02) — ring-pool threshold root-caused, but Area51/Training-Final NOT moved by it

A second, independent pass `angr`-decompiled EVERY function in the CSG/BSP build chain (not just
`FilterEdPoly`/`FilterLeaf`) and read each against `bspcsg.rs`. Full detail:
`native-materialize-findings.md`, search "INDEPENDENT PASS — full-breadth decompile".

The whole pipeline is faithful except ONE thing: the real editor pools a node's own vertex RING at
0.015 (NEAR) — `bspAddPoint arg_2=0` at `bspAddNode 0x352fd` — while pooling the surf pBase at 0.002
(SAME); native pooled both at 0.002. (Native's `try_to_merge`-neighbour=0.015 turns out to be a
symptom-patch for this — all three `TryToMerge` coincidence tests call `FPointsAreSame`/0.002 in the
binary.) A gated `UEDCLI_BSPCSG_RING_NEAR` fix preserves every exact level and improves Vandenberg's
node count, but has **ZERO effect on Area51's or Training Final's residual** (and none on nsfhq/747/
oceanlab): those are rotated-brush levels whose ring vertices sit at exact positions, never in the
0.002–0.015 gap. So the ring-pool threshold is NOT the Brush1852 / Training-Final lever — that
world-repartition node-over-build remains open. NOT shipped (gated off, `cargo test` 102/102).

## `bsp_add_node`'s own insertion logic fully decompiled and checked — closed off as a candidate; a real but INERT gap found and fixed (2026-09-02)

Picked up the `bsp_add_node`'s-own-linkage-decisions half of the "next step" named above (the other
half, the poly-soup/repartition-stage comparison, still untaken). Full `angr` decompile of
`bspAddNode` (`Editor.dll 0x10034e80`, ~10.8 KB pseudo-C, cross-checked against raw `capstone`
disassembly for every non-obvious line) against `bspcsg.rs::bsp_add_node`: the `NODE_PLANE` tail-walk
order, the surf alloc/reuse gate, the `>16`-vertex split-in-half, and — independently re-deriving the
existing 2026-08-27 disassembly finding via a different method — the Front/Back/Plane parent-linkage
and zone/leaf-inheritance formulas ALL match, with zero observable-effect differences. `bsp_add_node`
is now closed off as a candidate mechanism for Area51's (or NSFHQ04's) residual, the same way the prior
full `FilterEdPoly`/`FilterLeaf` decompile closed off the classify descent.

One real divergence WAS found — a post-loop "wrap trim" (drop a ring's redundant closing vertex if it
duplicates its first vertex after consecutive-only dedup, plus a degenerate-<3-vertex guard) that
`bsp_add_node` didn't implement — disassembly-confirmed twice (pseudo-C + raw capstone) and FIXED
(pinned by 2 new unit tests). But measured, via the offline `/tmp/uedcli-parity-cache` oracle
(`parity_report.py`, no live editor needed), to have **ZERO effect** on Area51 Entrance specifically
(native/golden nodes 12715/12630 `d=+85`, surfs 6058/6058 `d=+0`, leaves 3315/3264 `d=+51` — byte-
identical with the fix on vs off) and on 5 other levels including NSFHQ04. Shipped anyway as a faithful-
port fix (zero regression), but it does NOT explain Brush1852's residual. Full detail:
`native-materialize-findings.md`, search "Full `bspAddNode` decompile".

**Narrows the remaining surface for whoever picks this up next**: both `bspAddNode`'s own insertion
logic and `FilterEdPoly`/`FilterLeaf`'s classify descent are now fully checked and exact. The
unexamined piece is `bsp_brush_csg`'s own `AddFunc`/`leaf_func` dispatch (which decides WHETHER/WHEN to
call `bspAddNode` at all, per brush) and the world-brush processing/poly-soup order feeding it — not
yet decompiled or live-traced at this level of detail.
