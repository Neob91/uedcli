+++
priority = "p1"
kind = "debug"
summary = "Area51 Entrance's entire +85 node/+51 leaf residual live-localized to Brush1852; live-traced to classify-BSP over-fragmentation (26 vs 17 terminal fragments), NOT a keep/discard bug (disassembly-verified). `angr` decompiler round located FilterEdPoly/FilterLeaf/SplitWithPlane by address and ruled out a float-epsilon-flip; exact split-divergence mechanism still not pinned. Training Final open, static lead only."
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

## Training Final — open, static lead only

Residual (nodes native=11227 golden=11122 `d=+105`, surfs exact, leaves `d=+13`) not live-localized
this round. Static per-brush node-owner attribution is diffuse (297/764 brushes differ, no dominant
outlier — same "wrong level of attribution" trap as everywhere else), but flags a lead: 4
near-consecutive small (6-poly `CSG_Add`) brushes `Brush907`/`909`/`911`/`915` (world-CSG idx 660-668)
carry large, partially-offsetting diffs (`+71`/`+71`/`-52`/`+77`). Needs its own live prefix binary
search (same harness, adapted) to confirm or refute before trusting this lead.

## Harness

Committed under `dev/docs/spikes/2026-09-01-area51-training-final-residual/harness/`:
`area51_attrib.py`/`tf_attrib.py` (static per-brush node-owner attribution), `area51_prefix_search.py`
(prefix binary search), `area51_remove1852.py` (decisive removal test), `area51_subset.py` (N-brush
editor golden builder), `area51_addfunc_oracle.py` (live gdb trace of the editor's
`AddBrushToWorldFunc`), `area51_native_leaf_dump.py` (native's matching classify trace),
`area51_compare_tail.py` / `area51_frag_diff.py` (tail-diff and fragment comparison),
`find_addfunc_callers.py` (static caller-scan used to locate `FilterEdPoly`), `area51_dist_threshold_probe.py`
(the split-threshold-margin diagnostic).

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
