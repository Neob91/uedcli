# 92 — Real-level (UNATCO) CSG byte-parity: attribution + staged port plan

**Date:** 2026-07-19. **Status:** SCOPING + PLAN (no production `.rs`/`.py` changed). This section pins
where native's UNATCO build diverges from the editor at the surface level, **corrects the parity basis
§91 §9 used**, and lays out the staged work to close it. Harness (throwaway, `_scratch/`): brush-composition
+ face/surf-set diffs over the cached `_scratch/uedgolden/` builds; the durable diagnostics used are the
committed `vectors_attribution.py` and `soup_diff.py`.

### Confidence legend
✅ decode/measurement-exact against real `.dx` bytes this session · 🔬 cross-checked against the §82/§91 decode.

---

## 0. TL;DR — the "large lever" is TWO cleanly-separated residuals, and one of them is a BASIS ARTIFACT

The incremental-`bspBrushCSG` port (§82 §10.9–§10.20) is **DONE and byte-exact for the 95-brush castle**
(soup 853/853, node tree 1156/1156 planes, surfs 485/485, vectors 26/26, whole-body 43.6%). The task's
premise — that the real-level gap is "the deferred large incremental-`bspBrushCSG` port" still to be
written — is **stale**: the pipeline exists and works. UNATCO exercises it at ~8× scale (370
solid-structural + 363 detail brushes + 29 movers vs the castle's 91 + 4) and two residuals remain,
which §91 §9.4 reported as one
tangled "−6% nodes / +2.3% surfs / +24% vectors":

1. **The node-count gap (native 6425 vs the §91 golden's 6859, "−6.3%") is NOT a native defect — it is a
   PARITY-BASIS MISMATCH.** ✅ The §91 golden is built with `MAP REBUILD; **BSP REBUILD OPTIMAL** OPTGEOM
   ZONES`. The `BSP REBUILD OPTIMAL` step **re-partitions the whole BSP with OPTIMAL optimization**
   (stride 1), which native does **not** model — native models only `csgRebuild` (= what a bare `MAP
   REBUILD` runs: `bspRepartition` with `Opt=GOOD, Balance=12, stride=NumPolys/20`, §82 §5/§10.10).
   Against the **single-`MAP REBUILD`** golden (the GOOD/csgRebuild tree native targets) native is
   **+111 nodes (+1.8%)**, and the sign FLIPS — native slightly OVER-produces, it does not
   under-produce. The −1067 solid-node gap decomposes (§2, §92's own breakdown — §91 §9.4 reported only
   the aggregate −6.3% and §91 §9.5 already noted `BSP REBUILD OPTIMAL` re-partitions) into the OPTIMAL
   step adding +1230 solid splits over a base native is +163 above. **This re-baselines the node-tree
   residual from a scary −6% to +1.8%** — though "1× golden is native's exact basis" itself rests on the
   still-open assumption that bare `MAP REBUILD` == native's GOOD partition (§2 option b).

2. **The surf/vector over-production (+82 surfs / +146 vectors) is REAL and BASIS-INDEPENDENT.** ✅ Both
   goldens (1×-`MAP REBUILD` and 2-step-OPTIMAL) carry **3616 surfs / 599 vectors**; native carries
   **3698 / 745** against either.
   > **⛔ CORRECTED 2026-07-19 (see §12 banner):** the **+82 surfs is STALE** — the "3698" native surf
   > count came from cached pre-current-core `.dx`; a fresh mover-clean build is **3609 vs golden 3616 =
   > −7 (under-production)**. Only the **vector figure survives**: native 745 vs golden 599 = **+146,
   > still current**, and it is entirely texture axes on native's extra/differently-partitioned surfaces
   > (`vectors_attribution.py`), not a coplanar surf over-count. "BASIS-INDEPENDENT" held; "over-production"
   > did not.
   Surfs are built in the incremental-CSG phase and KEPT by any `BSP
   REBUILD` (`EmptyModel(0,0)`, §82 §10.16), so OPTIMAL-vs-GOOD does not touch them. This is the one
   genuine CSG-partition residual — the same incremental-CSG phase that is byte-exact on the castle,
   diverging by +82 at UNATCO scale.

**Bottom line for the plan:** the real remaining work is (a) FIX THE BASIS so the node tree is graded
against a GOOD-repartition golden (stage 0, a harness/measurement change — no `bspcsg.rs`), then (b)
pin-and-close the +82-surf residual with the **editor-tree oracle applied to UNATCO subsets** — the exact
gdb-on-`bspAddNode` method that cracked the castle (§82 §10.7–§10.9). There is **no clean, castle-safe,
provable one-line merge-rule fix in reach** (the divergence is bidirectional, not a pure under-merge —
§3), so per the report-don't-force gate no `bspcsg.rs` change is made this pass.

---

## 1. UNATCO vs the castle — what is different (✅)

| | castle | UNATCO |
|---|---:|---:|
| solid-structural brushes (oper, non-detail) | 91 | **370** |
| **detail brushes** (`PF_NotSolid\|PF_Semisolid`) | **4** (flat water quads) | **363** |
| movers (`DeusExMover`, no CsgOper) | 0 | 29 |
| CsgOper split (over solid+detail) | — | 519 Add / 214 Subtract |
| zones | 4 | 9 |

*(detail brushes are a SUBSET of the oper'd brushes — they carry an Add/Subtract CsgOper too; the
519/214 Add/Subtract split spans both the 370 solid and 363 detail brushes.)*

The castle's 4 detail brushes are **flat, single-poly water sheets that carve nothing** — so the castle
barely exercises the **semisolid second incremental layer** (§82 §9, the `bspBrushCSG` pass over detail
brushes AFTER repartition, not re-merged). UNATCO runs that layer **363 times over carving detail
geometry**. That layer, plus ~4× the solid-structural brushes (more near-coincident grid-vs-octagon plane pairs
— the §82 §10.6 `0.042` grid-snap family — and more FP accumulation), is what the castle cannot reveal.

## 2. The node-count residual is a basis artifact — measured (✅)

> **⚠️ Note (2026-07-19 reconcile — see §12 banner):** the surf/vector rows in the table below use the
> **stale pre-current-core native (3698 surfs)** and, where sourced from `unatco_subset.py`, the
> **mover-confounded** subset basis (fixed `cd56c1ae2`). The node-count basis analysis (GOOD `MAP
> REBUILD` vs OPTIMAL re-partition) still stands; the surf DELTAS quoted alongside do not — current
> mover-clean native is **3609 surfs (−7 vs golden 3616)**. Byte parity remains low (19.07%); the
> live picture is in `PARITY-STATUS.md` and `_scratch/baseline-reconcile/`.

Node counts by surf class (solid = structural, semi = detail-layer), from the cached
`_scratch/uedgolden/` builds:

Node counts by surf class (solid = structural; semi = detail-layer; other = notsolid+portal — the three
columns sum to Nodes):

| model | rebuild path | nodes | solid | semi | other | surfs | vectors | verts | leaves |
|---|---|---:|---:|---:|---:|---:|---:|---:|---:|
| **native** | `csgRebuild` (GOOD/12) | 6425 | 3033 | 3306 | 86 | **3698** | **745** | 94766 | 2759 |
| **golden 1×** | `MAP REBUILD` (GOOD/12) | 6314 | 2870 | 3396 | 48 | **3616** | **599** | 76488* | 762* |
| golden 2-step | `…;BSP REBUILD OPTIMAL OPTGEOM ZONES` | 6859 | 4100 | 2698 | 61 | **3616** | **599** | 98152 | 2934 |
| shipped retail | incrementally authored | 5188 | 2890 | 2251 | 47 | 3589 | 596 | 82487 | 2266 |

\* the 1× golden's `Verts`/`Leaves` are the stale/under-built arrays (§91 — a lean `MAP REBUILD` never
runs `AssignLeaves`/Pass-D on the final tree), so it is un-usable for Leaves/Verts parity; but its
**Nodes/Surfs/Vectors are trustworthy** (those sections are complete after `MAP REBUILD`).

**Read the table by column:**
- **Nodes/solid:** native 3033 vs golden-1× 2870 (**+163, +5.7%**); vs golden-2-step 4100 (−1067). The
  1230-node solid swing (2870→4100) is the `BSP REBUILD OPTIMAL` re-partition — native never runs it, so
  grading native's solid tree against the OPTIMAL golden grades against a finer partition native doesn't
  model. Against the GOOD basis native **over**-produces solid nodes by +163 (a real, if small, residual),
  the OPPOSITE sign to the −1067 the OPTIMAL basis suggests. *(That the GOOD 1× golden is native's exact
  basis assumes bare `MAP REBUILD` reproduces native's `csgRebuild` GOOD partition — well-motivated by
  §82/§90 but NOT proven this session; §2 option b, `Editor.dll 0x65220`'s Balance/stride, is undecoded.
  So +163 is a node-count-proximity residual, not a proven tree-identity gap.)*
- **Semi:** native 3306 vs golden-1× 3396 (−90) vs golden-2-step 2698 (+608). The 698-node semi swing is
  again the OPTIMAL rebuild re-doing the detail layer. Native's detail-layer residual vs GOOD is **−90**.
- **Surfs / Vectors:** **3616 / 599 on BOTH goldens** — invariant to OPTIMAL. Native +82 / +146 is real.

So the correct fresh-rebuild basis for the **node tree** is the **1×-`MAP REBUILD` (GOOD) golden**, against
which native is +111 nodes total (+163 solid, −90 semi, +38 other) — a small residual, opposite sign to
§91's −6%.
(The **shipped** retail map — 5188 nodes — is NOT a fresh-rebuild basis: it is incrementally authored over
a long edit session, so it carries fewer nodes than any fresh csgRebuild; §91 already noted this. It is
the right basis only for confirming refs/leaf == 1.0, not node count.)

**Basis tension the plan must resolve (stage 0).** A complete `Leaves`/`Verts` array needs a `BSP REBUILD
… ZONES`/`OPTGEOM` pass (§91 §9), but *any* `BSP REBUILD` re-partitions the tree away from the csgRebuild
tree native models. So Leaves-parity and node-tree-parity currently want *different* goldens. Options,
to be decided in stage 0:
- (a) grade **node tree** against the 1×-`MAP REBUILD` (GOOD) golden and **Leaves/Verts** against the
  2-step golden + native's §70 invariants (accept two bases); OR
- (b) build a **`MAP REBUILD; BSP REBUILD GOOD ZONES`** golden and check whether `BSP REBUILD GOOD`'s
  repartition matches native's `bspRepartition` (both GOOD — but the interactive parser is a *separate*
  entry point, `Editor.dll 0x65220`, whose Balance/stride to `bspBuild` is **not yet decoded**; it may
  not be Balance=12); OR
- (c) port `BSP REBUILD OPTIMAL` into native as a final re-partition so native targets the 2-step golden
  directly (largest scope; only worth it if byte-identity to a GUI-rebuilt map is the goal).

*(A `MAP REBUILD; BSP REBUILD GOOD ZONES` golden build was attempted this session; the editor wedged
silently — the known crash-proneness — so (b)'s empirical check is deferred to stage 0.)*

> **STAGE 0 RESOLUTION — see §8 (executed 2026-07-19): option (a) is adopted; option (b) is
> EMPIRICALLY REJECTED.** The `MAP REBUILD;BSP REBUILD GOOD OPTGEOM ZONES` golden was built
> successfully (generous idle barriers, no wedge) and measures **7273 nodes** — MORE than even the
> OPTIMAL 2-step (6859), so `BSP REBUILD GOOD` does NOT reproduce native's csgRebuild partition. The
> **bare `MAP REBUILD` golden (6314) is native's node/surf/vector basis** (native +111 / +82 / +146).

## 3. The +82-surf / +146-vector residual — attribution (✅)

`vectors_attribution.py` + a geometric surf-set diff (`surf_class_diff.py`, key = `(vNormal@1e-3,
plane-offset@1e-2, polyflag-class)`), native vs the 2-step golden (surf-count invariant to basis):

- **Surf normals are identical** (distinct vNormal 257/257/257) — the entire +146 vector excess is
  **texture axes** (distinct `vTextureU` +105, `vTextureV` +50; these do NOT sum to +146 — ~99 native
  vectors serve a dual U/V role, so the role sets overlap, §91 §10.2), carried by native's **extra
  surfaces** (§91 §10, decode-proven; not a sign/convention bug — matched surfaces agree exactly, 0 negated).
- **The +82 net surfs is BIDIRECTIONAL, not a pure under-merge:** **174 surf-instances only-native, 92
  only-editor** (net +82; `surf_class_diff.py`). Native both over-keeps faces the editor merges/drops AND
  mis-clips faces the editor keeps whole. (The independent `vectors_attribution.py` geo-key diff
  corroborates the direction: 319 native-only vs 215 golden-only `(base,normal)` keys — bidirectional.)
- **By polyflag class** (the mechanism split the task asked for):

  | class | native surfs | golden surfs | net | only-native | only-editor |
  |---|---:|---:|---:|---:|---:|
  | solid (structural CSG) | 1594 | 1556 | **+38** | 71 | 33 |
  | semisolid (detail layer) | 2059 | 2013 | **+46** | 103 | 57 |
  | notsolid | 44 | 45 | −1 | — | — |
  | portal | 1 | 2 | −1 | — | — |

  So **~half the surf excess is structural (+38) and ~half is the detail layer (+46)**. The detail-layer
  half is largely **downstream of the structural divergence**: the 363 detail brushes filter through
  native's already-slightly-different structural tree (§1), so they fragment differently — fixing the
  structural surf set should pull most of the detail-layer excess with it.

**Which CSG stage.** Surfs are allocated in the **incremental `bspBrushCSG` phase** (surf-share seeding,
§82 §2) and only *compacted* by `bspRefresh`; `bspBuild`/`SplitPolyList`/`bspOptGeom` re-tile *nodes*
over the existing surf pool and never add surfs (proven: OPTIMAL vs GOOD → identical 3616 surfs). So the
+82 is born in **`FilterWorldThroughBrush` clip-selection + `bspMergeCoplanars`/`TryToMerge`** — the
SAME routines that are byte-exact on the castle. The residual is therefore the **generalization** of the
§82 §10.6/§10.8 cumulative-tree-order divergence: near-coincident-plane clip selections (the `0.042`
grid-snap-gap family, far more numerous at UNATCO) that the castle's `bspCleanup` reconciliation (§82
§10.9) does not fully absorb at scale, each producing a differently-clipped face that then merges
differently. **Bidirectional ⇒ NOT closeable by forcing a merge** (§82 §10.6 showed forcing regresses).

**Not attributable to `bspOptGeom SplitPolyList`** (surf-count-invariant), and **not to a texture-axis
formula** (§91 §10.4: native-only axes are collinear-with-golden at a different texture *scale*, i.e.
carried by genuinely differently-partitioned surfaces, not a mapping bug).

## 4. Staged port plan (each stage: castle-byte-identity gate + real-level count-delta gate)

**Castle byte-identity gate (every stage MUST hold it):** `build_native_castle.py` → nodes 1156 /
surfs 485 / vectors 26 / leaves 384 / zones 4 / soup 853/853 / `compare_trees.py 32` identical /
whole-body 43.6% — all UNCHANGED. **Real-level gate:** native UNATCO surfs → 3616, vectors → 599, and
(against the *correct* basis) nodes → the GOOD golden's count, monotonically.

### Stage 0 — FIX THE BASIS (harness/measurement only; NO `bspcsg.rs`). *Highest leverage, lowest risk.*
The single most valuable step: stop grading native's node tree against the OPTIMAL golden. Concretely:
1. Add a `refs/leaf==1.0`-clean golden at **GOOD** repartition — resolve §2's basis tension (option a/b):
   build `MAP REBUILD; BSP REBUILD GOOD ZONES` and diff its node structure vs native and vs the 1×
   golden; decide whether `BSP REBUILD GOOD` == native's `bspRepartition` (decode `Editor.dll 0x65220`'s
   Balance/stride if ambiguous).
2. Re-run the §91 headline table against the corrected basis and annotate §91 §9.4 (whose aggregate
   "Nodes −6.3%" against the OPTIMAL golden reads as a native deficit; §92 decomposes it into the OPTIMAL
   re-partition's +1230 solid splits over a native +163 base — §91 §9.5 already flagged that OPTIMAL
   re-partitions, this just makes the node-count consequence explicit).
3. `bsp_health_check.py` already asserts refs/leaf==1.0; add a basis label so a golden's rebuild-cmd is
   recorded with it.
**Gate:** none in `bspcsg.rs`; deliverable is the corrected measurement + the decision on which golden is
the node-tree basis. **Effort:** ~½ day + 1–2 bounded editor runs. **Payoff:** the node "residual"
collapses from −6% to +1.8% total — a genuine but small **over**-production (+163 solid / +5.7%, −90
semi) that then joins the surf residual as the actual work, instead of a phantom −1067 deficit.

### Stage 1 — Build the editor-tree oracle for UNATCO (harness). *Enables everything downstream.*
Port the castle oracle (`editor-tree-oracle/`, §82 §10.7) to UNATCO: cache incremental subset goldens
(`golden{N}.dx` for a growing brush prefix), run the gdb `bspAddNode` breakpoint under `dx-lum-uned-dbg`,
and `compare_trees.py`/`soup_cmp.py`/`surf_diff.py` the LOOP-2 add streams + post-merge soup native-vs-editor
to find the **FIRST brush N where native's surf set diverges**. UNATCO has ~730 solid+detail brushes, so
this needs a bisection over N (not a full 1..N sweep). **Gate:** oracle reproduces the editor stream through
the first matched prefix. **Effort:** ~2–4 days (infra exists; UNATCO scale + subsetting is the work).
**Payoff:** converts "+82 surfs somewhere" into "brush N, face F, plane P, this clip/merge decision."

### Stage 2..k — Pin-and-close each divergence CLASS (decode → port → castle-gate). *The bulk.*
Each first-divergence found by stage 1 is decoded to instruction level against `Editor.dll` (as §82
§10.6/§10.8/§10.9/§10.10 did for the castle), ported to `bspcsg.rs`, and gated on castle byte-identity +
a monotone UNATCO surf/vector move. Expect a SMALL NUMBER of divergence classes (the castle proved the
core rules; these are the next-order cases it doesn't hit) — likely the near-coincident-plane
clip-selection family (§82 §10.6) generalized, and the detail-layer's interaction with it. Each class is
one decode+port+gate cycle. **Effort:** days-to-weeks *per class*, unknown class count until stage 1 —
this is the genuine "large lever."

### Stage 3 — Detail-layer residual (only if it survives stage 2). *Likely downstream, re-measure.*
Re-measure the semisolid +46 after the structural surf set matches; if it persists, trace the detail
brushes' second-incremental-layer filtering against the (now-matching) structural tree. **Gate:** UNATCO
semi-surfs → golden.

### Stage 4 (optional) — `BSP REBUILD OPTIMAL` re-partition, IF byte-identity to a GUI-rebuilt map is the
target. Port the OPTIMAL partition (stride 1) as a final re-partition. Only pursue if stage 0 decides the
2-step golden is the parity target; otherwise the GOOD tree native already builds is the correct target.

## 5. Highest-leverage first stage + honest effort

**Highest-leverage first stage = Stage 0 (basis fix).** It is cheap (harness + a bounded editor run), it
CANNOT regress the castle (no `bspcsg.rs` change), and it re-baselines the node tree from a scary "−6%"
to "+1.8%", exposing that the ONLY genuine body residual is the +82 surfs. Doing it first stops the
project chasing a phantom node deficit that is really the OPTIMAL re-partition.

**Honest total effort — this is the large lever, dominated by stages 1–2, and it is WEEKS of staged
work, not a few merge-rule fixes.** Rationale: the castle *already implements every known
clip/merge/split rule byte-exactly* (soup 853/853, surfs 485/485), so the UNATCO surf residual is *by
construction* the next-order divergences the castle doesn't exercise — each must be found by the oracle
(stage 1) and decoded from the binary (stage 2), the same expensive loop that produced the ~12 castle
commits in §82 §10.9–§10.20. The good news §92 adds: the node-tree half is **mostly a basis artifact**
(stage 0 removes the phantom −6%, leaving a small +1.8% / +163-solid over-production to fold in with the
surf work), and the surf half is a **clean, basis-independent, bounded +82**
with a proven method to attack it. There is **no shortcut merge-rule fix** — the divergence is
bidirectional and forcing regresses (§82 §10.6 negatives), so the oracle-driven pin-and-port loop is the
only faithful route.

## 6. Why no `bspcsg.rs` stage-1 code fix this pass (report-don't-force gate)
The task authorized a stage-1 `bspcsg.rs` fix "if a clean stage-1 fix is in reach (e.g. a specific
`bspMergeCoplanars`/`TryToMerge` coplanar-merge rule the editor applies and native doesn't)." The
evidence says none is: (1) the divergence is **bidirectional** (174 only-native / 92 only-editor) — not a
missing merge; forcing a merge over-fuses and regresses the castle (§82 §10.6 proved this twice). (2) The
node-count half is a **basis artifact**, not a code defect. (3) The surf half's exact first-divergence is
**not yet pinned** (needs stage 1's UNATCO oracle) — any change now is a blind tweak, and every blind
tweak in §82 regressed. So the faithful deliverable is this plan + the basis correction (a real,
measured, castle-safe result), not a forced code change.

## 7. Reproduce
```
cd Tools/uedcli
# the surf/vector residual is basis-independent (both goldens = 3616 / 599):
.venv/bin/python dev/docs/spikes/2026-07-15-native-materialize/harness/vectors_attribution.py \
  _scratch/uedgolden/Native_unatco.dx _scratch/uedgolden/UEDGolden_unatco_world_zones.dx \
  /home/neob91/Games/LutrisDX/drive_c/DX/Maps/03_NYC_UNATCOHQ.dx
# the node-count gap is the OPTIMAL re-partition (compare the two goldens' solid-node counts):
#   golden 1x MAP REBUILD  -> _scratch/uedgolden/UEDGolden_unatco_world.dx   (nodes 6314, solid 2870)
#   golden 2-step OPTIMAL  -> _scratch/uedgolden/UEDGolden_unatco_world_zones.dx (nodes 6859, solid 4100)
#   native (GOOD/csgRebuild) -> _scratch/uedgolden/Native_unatco.dx           (nodes 6425, solid 3033)
```

## 8. STAGE 0 EXECUTED — basis fixed; option (a) adopted, option (b) rejected (✅ 2026-07-19)

**The editor built the GOOD golden — it did NOT wedge this time.** The two prior wedges (§2 note,
`build_good_zones{,2}.log`) were a FALSE-IDLE artifact, not an inherent `BSP REBUILD GOOD` crash: the
default 8-quiet-read barrier fired during an inter-phase CPU lull, so `MAP SAVE` ran against a
still-churning/half-dead editor and the container vanished. Re-run with a **generous barrier**
(`--quiet-reads 30 --rebuild-min-seconds 45`) the `MAP REBUILD;BSP REBUILD GOOD OPTGEOM ZONES` build
completed cleanly (CPU 4.6% at the rebuild-idle barrier — editor ALIVE, not the 0.0% dead-container of
the crashed run) and wrote `_scratch/uedgolden/UEDGolden_unatco_good_zones.dx` (7273 nodes, refs/leaf
== 1.0, zones 7). **Editor-stability finding to pin: BSP-REBUILD goldens at UNATCO scale REQUIRE
`--quiet-reads ≥ 30`; the 8-read default mis-detects an inter-phase lull as idle and corrupts/loses
the save.** (`build_ued_golden.py` keeps 8 as the arg default but its `--quiet-reads` help already
warns; the §92 canonical basis command below passes 30.)

**Measured node counts by rebuild path** (all from the SAME uedcli UNATCO trunk; surfs/vectors shown
to prove invariance):

| build | rebuild path | nodes | Δ vs bare `MAP REBUILD` | surfs | vectors | refs/leaf |
|---|---|---:|---:|---:|---:|---:|
| **native** | `csgRebuild` (GOOD/12) | **6425** | **+111 (+1.76%)** | **3698** | **745** | 1.00 ✓ |
| **golden — bare `MAP REBUILD`** | csgRebuild GOOD/12 | **6314** | — (basis) | **3616** | **599** | 9.45 ✗ (stale) |
| golden — `BSP REBUILD GOOD OPTGEOM ZONES` | interactive re-partition | 7273 | +959 (+15.19%) | 3616 | 599 | 1.00 ✓ |
| golden — `BSP REBUILD OPTIMAL OPTGEOM ZONES` | interactive re-partition | 6859 | +545 (+8.63%) | 3616 | 599 | 1.00 ✓ |

**Conclusions (canonical basis, replaces §91 §9.4's OPTIMAL grading):**
1. **§2 option (b) is REJECTED.** `BSP REBUILD GOOD` produces **7273** nodes — MORE than even OPTIMAL
   (6859) and +15% over the bare `MAP REBUILD` (6314). It is a SEPARATE interactive-parser entry
   (`Editor.dll 0x65220`) whose Balance/stride is NOT csgRebuild's GOOD/12, so it does **not**
   reproduce native's partition. No `BSP REBUILD` variant does.
2. **§2 option (a) is ADOPTED — two bases:** the **NODE/SURF/VECTOR basis is the bare `MAP REBUILD`
   golden** (`_scratch/uedgolden/UEDGolden_unatco_world.dx`, 6314 / 3616 / 599), against which native
   is **+111 nodes (+1.76%), +82 surfs, +146 vectors**. The node "residual" is a small **over**-
   production (opposite sign to §91's phantom −6.3%, which was the OPTIMAL re-partition). The
   **refs/leaf==1.0 LEAF/VERT property basis** is a separate `…OPTGEOM ZONES` golden (its node count
   is re-partitioned, not native's — use its leaf/vert SHAPE only). native carries both correctly at
   once; the editor only produces them across two different rebuild paths.
3. **Surfs (3616) and vectors (599) are INVARIANT across all four rebuild paths** — native's +82 / +146
   is real and basis-independent, now confirmed a fourth way. This is the ONE genuine CSG residual and
   the target of stage 1.

**`build_ued_golden.py` default is now a bare `MAP REBUILD`** (native's node/surf/vector basis);
`--rebuild-cmd "MAP REBUILD;BSP REBUILD GOOD OPTGEOM ZONES"` is the opt-in clean-leaf variant.
`bsp_health_check.py`'s refs/leaf==1.0 assertion still (correctly) flags a bare golden's stale leaves —
that now means "don't use its LEAVES for parity", NOT "its nodes are wrong". Both harness docstrings
carry the two-basis note.

**Canonical native-parity measurement command (GOOD basis, generous barrier):**
```
cd Tools/uedcli
# node/surf/vector basis — bare MAP REBUILD (native's exact csgRebuild target):
.venv/bin/python dev/docs/spikes/2026-07-15-native-materialize/harness/build_ued_golden.py \
  --out _scratch/uedgolden/UEDGolden_unatco_world.dx --overwrite --world-only --no-light
# clean-leaf property basis (opt-in) — MUST use --quiet-reads 30 or the editor save corrupts/wedges:
.venv/bin/python dev/docs/spikes/2026-07-15-native-materialize/harness/build_ued_golden.py \
  --out _scratch/uedgolden/UEDGolden_unatco_good_zones.dx --overwrite --world-only --no-light \
  --rebuild-cmd "MAP REBUILD;BSP REBUILD GOOD OPTGEOM ZONES" --quiet-reads 30 --rebuild-min-seconds 45
```

## 9. STAGE 1 EXECUTED — first surf over-production PINNED to Brush755 (a dome subtract), N=105 (✅ 2026-07-19)

**The first divergence is a 78-poly tessellated DOME subtracted at UNATCO scale — a curved-surface
near-coincident-plane case the castle never exercises.** Pinned with a new subset differential
(`harness/unatco_subset.py`, the UNATCO analog of the castle `subset_diff.py`): build the first-N brush
prefix BOTH ways (native `build_geometry_bspcsg` surfs vs an editor `golden{N}.dx`) and binary-search
the smallest N whose surf multisets diverge. Cached goldens: `_scratch/unatco-subset/golden{N}.dx`.

**METHOD FINDING (why NOT `soup_cmp`, and why the metric is only-NATIVE):**
- On UNATCO a full editor rebuild DISCARDS the brush Polys soup (the golden's `Model.Polys` export is a
  near-empty 78 vs the castle's 853), so `soup_cmp.py`'s soup key can't bisect here — the pin uses the
  FINAL `Model.Surfs` (retained by any rebuild, §3), keyed `(normal@1e-3, offset@1e-2, class)`.
- UNATCO's first 20 brushes are all `CSG_Subtract` (rooms carved into the void; first `CSG_Add` at
  N=21). A lone/early subtract makes the editor keep the room's inner faces as surfs while native emits
  them only once enclosing solid arrives, so at small N native UNDER-produces (`only-editor`≈5,
  `only-native`=0) — a **subset artifact of the subtract-into-void convention, NOT a bug** (at full
  scale native has MORE surfs, not fewer). The unconfounded signal for the +82 OVER-production is
  therefore **`only-native > 0`** (native emits a face the editor lacks): 0 through N=104, first
  positive at **N=105**, then monotonically growing (105:28 → 121:29 → 213:36 → 396:380 → 762:534).

**THE PIN.** Adding brush index 104 = **`Brush755`**, `class=Brush CsgOper=CSG_Subtract`, **78 polys**
(a tessellated dome/sphere: a full azimuth ring × several elevation rings of sloped facets + 9×(0,0,1)
and 9×(0,0,−1) horizontal cap rings), at loc (540,1204,276), flips the surf sets from clean to
divergent: `only-native 0→28`, `only-editor 5→25` — **BIDIRECTIONAL at the very first divergence**
(native both over-fragments AND mis-drops), exactly §3's characterization. The 28 over-produced surfs
are the dome's own facets — dominated by **8× the single cap plane `(0,0,1)@268`** (native keeps 8
coplanar fragments of one dome cap ring where the editor `bspMergeCoplanars`-merges them) plus one each
of the sloped facet planes `(±0.731,±0.159,0.664)`, `(±0.977,±0.212,0)`, `(±0.893,±0.194,0.406)`,
`(0,±0.923,0.385)`… — i.e. native clips/keeps the dome's near-coincident facet planes against the
prior 104-brush tree differently than the editor and under-merges the resulting coplanar cap fragments.

**Divergence CLASS (the Stage-2 target).** This is the §82 §10.6 near-coincident-plane clip-selection +
`bspMergeCoplanars`/`TryToMerge` coplanar-merge family, GENERALIZED to a **curved (dome/cylinder)
subtract** — many facet planes at small mutual angles, which the castle's box/octagon geometry never
produces. It is **bidirectional** (28 only-native / 20 net-new only-editor), so per §6 / §82 §10.6 there
is **no clean merge-forcing fix** (forcing over-fuses and regressed the castle twice). Closing it needs
the exact `FPoly::SplitWithPlane` + `TryToMerge` decisions at the N=104→105 boundary decoded to
instruction level against `Editor.dll` — the gdb `bspAddNode` ADD-stream oracle (§10.7) applied to the
`golden104`→`golden105` step. **Per the report-don't-force gate, no `bspcsg.rs` change is made** (the
decode is Stage 2, spec in board item `92-stage-2-done`).

**Reproduce.**
```
cd Tools/uedcli
.venv/bin/python dev/docs/spikes/2026-07-15-native-materialize/harness/unatco_subset.py diff 105
# -> N=105 only-native=28 (first over-production); brush index 104 = Brush755, 78-poly dome subtract
.venv/bin/python dev/docs/spikes/2026-07-15-native-materialize/harness/unatco_subset.py bisect 98 109
# -> *** FIRST onlyN DIVERGENCE at N=105 (N=104 clean) ***
```

## 10. HONEST remaining effort (post stage 0+1)

Stage 0 (basis) and Stage 1 (first pin) are DONE. What remains is the genuine large lever:
- **Stage 2 (this first class):** gdb-decode the `Brush755` dome clip/merge at N=104→105 to instruction
  level, port the `SplitWithPlane`/`TryToMerge` fix to `bspcsg.rs`, gate on castle byte-identity + a
  monotone UNATCO `only-native` drop. Days, and the dome is only the FIRST class.
- **Stages 3..k:** each subsequent first-divergence (re-bisect after Stage 2 lands) is another
  decode+port+gate cycle. The `only-native` count (534 at full) is the score to drive to 0; expect a
  handful of classes (dome/cylinder curved subtracts, then the detail-layer interaction, §3). Weeks.
- The node-tree residual is now known-small (+111 / +1.76% on the correct GOOD basis) and largely folds
  in with the surf work; the OPTIMAL "−6%" phantom is retired.

## 11. Stage 2 RESULT — the dome cap was a MISSING `bspValidateBrush` link phase, not a `SplitWithPlane`/`TryToMerge` divergence (LANDED 2026-07-19)

The §9 hypothesis (a `SplitWithPlane`/`TryToMerge` clip-selection divergence) was WRONG for the
dominant sub-class. The gdb-oracle decode of the N=104→105 boundary against `Editor.dll 0x37290`
(spec in board item `92-stage-2-done`) found the real cause: the editor runs
**`bspValidateBrush`** when a brush is built — a per-brush pre-pass that assigns each poly an `iLink`
so that **COPLANAR + same-facing + same-texture + same-axes + same-flags faces of ONE brush share a
single `FBspSurf`**. `bspMergeCoplanars` then fuses the shared-surf fragments. Native re-ingesting the
T3D never ran this phase, so each of the dome's 9 `(0,0,1)` cap facets seeded its OWN surf and nothing
downstream could merge them — the 8× cap over-production.

**Fix (in `bspcsg.rs::bsp_brush_csg`):** port the `bspValidateBrush` link loop. Faithful to the
decode — the geometry gate uses each face's FINALIZED (winding-derived) normal + on-plane base (the
editor links AFTER `FPoly::Finalize`; a stale/projected authored normal must not decide coplanarity),
the exact `TextureU`/`TextureV` axis gate is kept, and the brush-poly→`temp` index remap survives a
dropped degenerate face. NO `SplitWithPlane`/`TryToMerge` change was needed.

**Gate result:** UNATCO N=105 `only-native` **28→20** (the 8 cap fragments fuse); castle byte-identity
UNCHANGED (485 surf / 1156 node / 26 vec / soup 853/853 / 43.04%); N=104 still clean; `bisect 30 105`
still clean below 105. Regression `bspcsg::tests::validate_brush_links_fuses_coplanar_same_facing_faces`
(the coplanar-link fact re-asserted against a hand-built dome-cap brush). Two cold reviewers resolved
(an index-space desync when LOOP 1 drops a face + the pre-finalize-normal gate — both fixed before
commit). Durable choice: `decisions.md` 2026-07-19 08:58 UTC.

**Remaining at N=105 — NOT over-production (corrected 2026-07-19, two-agent verified §12).** The 20
residual `only-native` at N=105 are the dome's sloped facets but they are **precision twins, not extra
surfs**: each pairs 1:1 with an `only-editor` surf at the SAME normal + polyflag-class, differing only
in plane OFFSET by 0.005–0.044 units (coarsening the offset key collapses `only-native` 20→5→1). The 5
genuinely-unpaired `only-editor` surfs at N=105 are the pre-dome N=104 axis-aligned subtract-into-void
baseline (harness-flagged not-a-bug), so the dome adds ZERO net surf over-production. Stage 2's cap fix
IS the real dome parity win; the twins are a sub-grid position delta (editor vertex grid-snap vs
native's exact authored floats — the existing "Vectors 1–3 ULP FP" byte residual, lower priority).

## 12. Stage 3 target REDIRECTED — axis-aligned structural clip over-production in (213, 396] (scoped 2026-07-19)

> **⛔ SUPERSEDED — 2026-07-19 (later same-day reconcile, 2-agent cross-verified).** The whole §12
> premise is an ARTIFACT of a `unatco_subset.py` **mover confound**: the subset harness fed 28
> DeusExMovers through the world CSG, injecting +221 phantom surfs and producing the bogus
> "leftover-only-native `N=396→170, N=762→215`, axis-aligned over-production" ladder. The confound is
> FIXED in commit `cd56c1ae2`. With movers excluded, a full mover-clean `build_native_unatco.py` gives
> **native 3609 surfs vs golden 3616 = −7 (slight UNDER-production), NOT +82/+170/+215 over**. The "+82
> surf / +146 vector over-production" the plan below chases was additionally measured against **stale,
> pre-current-core `.dx`** (all 3698 surfs) that does not reproduce. **There is no axis-aligned
> over-production to bisect or gdb-decode; Stage 3 as written is retired.** Current baseline:
> `_scratch/baseline-reconcile/`; live status: `PARITY-STATUS.md` "Surf-count parity is essentially
> CLOSED". Prose kept below for history only.

Two-agent scoping + adversarial verification (independent code, cached goldens) established the real
`only-native` structural residual is **NOT the dome / not curved**. Under a **1:1 normal+class cancel**
metric (leftover-only-native = genuine over-production after precision twins are matched away):
`N=105→0, N=213→0, N=396→170, N=762→215` — and **every leftover surf is AXIS-ALIGNED** (each normal is
±1 on one cardinal axis; 0 oblique/curved at N=396 and N=762). Net sign FLIPS: native slightly
UNDER-produces at N≤213 (−5/−7 axis-aligned surfs the editor keeps) and OVER-produces at N≥396
(+170/+215). So the +82 net-surf residual (§3) is a **structural axis-aligned near-coincident-plane
clip-fragmentation** (§82 §10.6 grid-snap family generalized to the detail-brush-heavy region), born in
some brush in **(213, 396]** — unrelated to `Brush755`.

**Bisect methodology (corrected).** `bisect 105 762` on the plain `only-native` metric is DEGENERATE:
`dv(105)=bool(20)=True`, the precondition `dv(lo)==False` never holds, so it converges to a bogus
"N=106, N=105 clean". The correct scout is a **leftover-only-native** metric bisected over **[213, 396]**
(`dv(213)=False`, `dv(396)=True`, well-posed). This needs NEW intermediate editor goldens in (213,396]
— the expensive editor-driving step.

**Stage 3 plan:** (1) add the leftover-only-native (1:1 normal+class cancel) metric to `unatco_subset.py`;
(2) characterize the 170 axis-aligned leftovers already visible in the cached `golden396` (cluster by
plane/position → the repeated detail-brush pattern); (3) bisect [213,396] for the first over-producing
brush; (4) gdb `bspAddNode` decode of its near-coincident axis-plane clip; (5) `bspcsg.rs` port +
castle-byte-gate. Stages 4..k repeat for the next class.

## 13. What the UNATCO byte residual ACTUALLY is (2026-07-19, two-agent reconcile) — no cheap win remains

After the mover confound (§12) and the stale-`.dx` correction, the fresh mover-clean UNATCO baseline is
**native 3609 surfs / 745 vectors vs golden 3616 / 599; compiled byte-parity 19.07%**. Two independent
deep passes (node-partition scout + vector-precision root-cause) pin what the remaining gap is — and it
is a SINGLE root with no tractable static/castle-safe fix:

**(1) The +146 vectors are ALL texture axes and a DOWNSTREAM SYMPTOM of CSG fragmentation, not a bug.**
Classifying native's 745 vectors vs the golden pool: 553 bit-equal, 35 near-twins (1e-5..1e-2 FP delta →
fail to pool), **157 orphans (≥1e-2), every one a texture axis** (0 orphan plane-normals — vNormals are
257==257). 118/157 orphan axes ride **native-only surfaces** (geo-keys the golden lacks); the ~39 on
"common" keys are collisions with a DIFFERENT `texture_ref` (2–3× magnitude) = physically different face
pieces. So the +146 is derived from the partition/fragmentation difference; a texture-axis-formula or
grid-snap fix would be WRONG (dome facet texture axes are bit-identical, 0/61 differ).

**(2) The surf residual is FRAGMENTATION, not over-production.** Level-wide **leftover-only-native = 0**
(every only-native surf pairs 1:1 with an only-editor surf under (normal@1e-3, polyflag-class)); the pairs
differ in base-point / offset / texturing, not orientation. Net is **−7** (7 genuinely-missing editor
surfs). Native produces the right plane-normal *distribution* but fragments/positions the pieces
differently than the editor.

**(3) The ~0.02 base-point twins are a SPLIT-SEQUENCE (order), not an arithmetic, divergence.** For the
dome (Brush755, N=105) native vs golden104/105: normals identical to 4dp, texture axes bit-identical, only
the base-point/plane-offset differs (native −46.044 vs golden −46.055, ~0.011; 20/61 facets >2e-3).
Brush755 has integer Location (540,1204,276), no Rotation, unit scale → **NOT grid-snap** (a snap would
perturb the normal too). Native's `FPoly::SplitWithPlane` is **castle-byte-exact**, so the interpolation
FORMULA is right; the divergence is WHICH plane clips the facet in WHAT order — the incremental
`bspBrushCSG` ADD-stream sequence — which lands the clipped vertex on a slightly different (but
equally-valid) float that `bspAddPoint` (tol 0.015) pools without collapsing onto the editor's value.

**Conclusion / next instrument.** The remaining UNATCO byte residual = the incremental `bspBrushCSG`
ADD-stream **order + surface fragmentation** at scale. There is NO static, castle-safe one-line fix left
(both agents, task-4 "report don't force"). Closing it requires the gdb `bspAddNode` **editor-tree-oracle**
(§82 §10.7) repointed from the castle to UNATCO (swap default golden → `golden104/105.dx`; repoint asset
mounts + engine-ini Paths to UNATCO's composed search dirs, per §92 §1; the `bspAddNode` RVA 0x34e80 +
loop-head are DLL-level, unchanged), to pin the FIRST diverging incremental ADD at the golden104→golden105
boundary and decode the editor's `SplitWithPlane`/clip routing that native resolves to a different piece.
This is the genuine "weeks, one decode+port+castle-gate cycle per class" grind — now correctly targeted
(the +82 over-production and the (213,396] axis-aligned targets were both measurement artifacts).

## 14. The precision residual DECODED: editor stores `CalcNormal` over the WELDED brush-model winding (`bspBuildFPolys`), not the authored T3D normal (2026-07-19, oracle+disasm confirmed)

The §13 "base-point twins / +146 texture-axis vectors" residual is now root-caused to a single missing
native stage. **Feasibility first: the editor's normal/base path is pure scalar SSE f32** (`FPoly::CalcNormal`
`Engine.dll 0x150510`; `FVector` cross `core 0x17cf0`; `NormalizeSlow 0x249d0` does the magnitude sqrt in
f64 then narrows — provably bit-identical to a direct f32 `sqrtss`, 0 diffs over 261k mantissas). **No x87
80-bit intermediates** → byte-identity is reachable in principle; native's `calc_normal` op-order already
matches.

**What native is missing.** UnrealEd computes each stored surf normal by `CalcNormal` over the brush's
**welded brush-model winding**, produced by a `bspBuildFPolys` reconstruction at the single `Finalize` call
site `Editor.dll 0x10015e83` — an `Init`-zero → refill-verts-from-node-data → `Finalize`→`CalcNormal` loop
that runs at **brush-model build, BEFORE world CSG**. Oracle proof (`editor-tree-oracle` UNATCO N=105,
`logs/oracle-105.log`): the dome facet (Brush755) is already recomputed + base-snapped **in the brush's own
model** (`N=0.73059,-0.15852,0.66417`, base `(51.46443,-2041.66101,0.02321)`, nv=4) — before any world clip.
Native instead **trusts the authored T3D `Normal=`** and never rebuilds/welds the brush model. The tiny
normal delta (~1e-6..6e-6) is then **amplified by the surf base-snap `d = base·normal`** at d≈2000 uu on
far-from-origin loft faces (`bspcsg.rs:265`) into the observed ~0.02 pBase offset twins. This is ALSO the
castle's un-closed residual: castle golden vectors 0-5,7 (axis) match authored byte-exact, but 6,8,9,10-25
(curved) differ 1-3 ULP = the welded-winding recompute native doesn't do.

**Why the naive fixes fail the gate (measured, all reverted).** always-recompute(raw winding) and
welded-recompute+re-snap BOTH regress castle 43.04%→41.81% AND UNATCO diff-105 20→24. Decisive hex evidence
(`_scratch/fpolyspike/hexcmp105.py`, native vs `golden105.dx` matched by base): native's `calc_normal`
differs from the editor's stored normal by **~1e-6..6e-6 in inconsistent ± directions** — NOT a systematic
ULP a heuristic can correct. Recompute fixes far-off twins (surf541) but breaks faces the editor kept
authored-exact (surf556, whose authored==editor exactly). The editor is not "selective by threshold":
surf556's welded winding happens to reproduce the authored normal exactly, surf541's does not. The editor's
value equals **neither** native-authored **nor** native-`calc_normal` — it is the welded-winding value whose
**point-pool + winding-reconstruction ORDER** native's ad-hoc temp-BSP weld does not reproduce (that weld
found zero merges to apply).

**The fix (next build item, larger port).** Port `bspBuildFPolys` FAITHFULLY: build each brush's BSP via
native's **existing editor-faithful `bsp_build`** (the world ADD stream is already byte-identical N≤105 per
§13 oracle — so its `bspAddPoint` order is the right pool), reconstruct each poly from its **node winding**,
`CalcNormal`+base-snap from THAT, then feed world CSG — NOT an ad-hoc weld-lookup. Gate: castle byte-% must
**improve** (curved-vector ULPs resolve) with counts held 485/1156/26; UNATCO diff-105 twins must drop.
Accepting the ~1e-6 deltas as "and similar" is NOT valid — they are deterministic, hence in-scope for
byte-identity. Harness: `_scratch/fpolyspike/` (gitignored; the durable evidence is `oracle-105.log`).

## 15. The residual is the editor's brush-model VERTEX POOL, not CalcNormal op-order (2026-07-19, fork settled)

§14 proposed the fix was recomputing normals over the welded brush winding. A de-risk + op-order
brute-force REFUTED that and settled the fork to **(B): UnrealEd computes each brush face over slightly
DIFFERENT vertices than native**, produced by its brush-model `bspAddPoint` point pool.

**(A) f32-op-order is conclusively RULED OUT.** For the dome facet (Brush755, `i_brush_poly=44`, nv=4),
brute-forcing every plausible native f32 SSE variant — cross-accumulation order, 4 normalize modes
(incl. `NormalizeSlow`'s f64-widened magnitude), base-snap dot in f32/f64, offset in f32/f64 — over
native's EXACT transformed T3D verts: every unit-normal variant lands at plane offset **|B·N|=361.2568**.
float64-**exact** over those same verts = **361.25684**. The editor stores **361.25892**, which
**overshoots the infinite-precision ceiling by +0.00208 (~70 ULP)**. No f32 rounding of a well-conditioned
unit-normal reduction can exceed the exact answer by 70 ULP ⇒ the editor's inputs are different vertices,
not different arithmetic. (Idealized f64 sits *between* native-f32 361.25677 and editor 361.25892 — a red
herring; the exact-over-native ceiling is the decisive bound.)

**(B) characterized (cheap, no editor).** Native and the golden import the SAME T3D subset trunk (`MAP
IMPORT`+`REBUILD`), and the T3D's shared dome verts are byte-consistent across faces — so identical vertex
TEXT feeds both. Grid-snap is ruled out (no grid `g` reproduces `N.x=0.73059`; `g=1/32→0.730110`). But the
offset is highly sensitive: a single **~1e-5..1e-4 per-vertex** shift moves `|B·N|` by the observed 0.002
(a 0.002 vertex nudge shifts it up to 0.61). That per-vertex magnitude is the signature of the editor's
brush-model **`bspAddPoint` pool-welding** each vertex to a slightly-different POOLED coordinate — a shared
pool across the brush's tessellated facets, where near-coincident shared verts collapse to one pooled value.
Native's convex `build_brush_temp_bsp` finds **zero merges** here (welded==unwelded), so it keeps the exact
T3D verts and diverges.

**Why this matters beyond the dome.** The brush-model vertex pool is UPSTREAM of world CSG, so a ~1e-5
per-vertex shift propagates sub-ULP differences into every downstream stored coordinate (node plane
offsets, Verts, Points, Surf bases) — a plausible contributor to the level-wide positional byte divergence
(UNATCO 19.07%), not merely the 20 dome twins. The world ADD *routing* stays byte-identical (sign-based
classification is robust to 1e-5), which is why the oracle saw identical routing yet the stored bytes differ.

**Fix direction + next data.** Reproduce the editor's brush-model `bspAddPoint` pool (shared across the
brush's polys, exact tolerance + add-ORDER) so native's brush verts weld to the editor's pooled coordinates
before CalcNormal/CSG. Pinning the exact tolerance/order needs the DECISIVE missing datum: a gdb dump of the
editor's brush-model pooled `Verts` for Brush755 (Finalize site `0x10015e83` / model `0xe8a26cc`) vs
native's transformed T3D verts, per-vertex. That is the next probe (one guarded editor run). NOT an
`fpoly.rs` op-order change. Harness: `_scratch/fpolyspike/{oporder_bruteforce,perturb_sensitivity}.py`;
evidence `logs/oracle-105.log`.

## 16. CORRECTED (supersedes §14 & §15): the residual is native's `CalcNormal` f32 OP-ORDER, ~1 ULP off Engine.dll — verts are byte-identical (direct gdb dump)

§14 ("editor recomputes over the WELDED winding") and §15 ("(B) editor computes over DIFFERENT verts")
were both wrong inferences. A **direct gdb dump of the editor's brush-model FPoly `Verts`** (Brush755
ib=44, model `0xd831dcc`, decoded as big-endian f32 bit patterns) settles it with hard evidence:

**The editor's brush-model pooled verts are BYTE-IDENTICAL to native's transformed T3D verts** — all four,
bit-for-bit (editor order `[V0..V3]` = native `[D,C,B,A]` reversed): V0 `43ff745c,44978000,4387999a` == D,
etc. Shared verts DID collapse to one pooled coord across 4 adjacent dome facets (vertex A `43ffad0d`), but
that pooled coord EQUALS native's transformed vertex byte-exact — the weld is a no-op because the T3D's
per-face duplicate verts are already byte-consistent. So the editor's `bspAddPoint` pool reproduces exactly
native's verts. **§15's (B) is falsified; §14's welded-winding premise is moot (welding changes nothing).**

**The real residual is (A): native's `calc_normal` f32 op-order is ~1 ULP off Engine.dll `FPoly::CalcNormal`
(`0x150510`).** Feeding native's f32 `CalcNormal`+base-snap the editor's EXACT verts yields normal
`N.x=0.7305843` vs editor `0.730585` (~7e-7, 1 ULP). The base twin is DOWNSTREAM of this: the base-snap
lever arm is large (the texture Origin sits ~3300 uu from the verts, `d=N·(V0−Origin)`), so the ~1e-6 normal
error magnifies into the visible `base.x` Δ0.0027 / plane-offset ~2e-3. Fix the normal and the base follows.
An empirical 48-variant op-order search (cross-accumulation orders, 4 normalize modes incl. NormalizeSlow's
f64 mag, base-snap/offset in f32 vs f64) over the identical verts did NOT contain the editor's order — so
the exact reduction/normalize sequence must be read from the `0x150510` disassembly, not guessed.

**The complete fix is two coupled parts:**
1. **Match Engine.dll `CalcNormal` (0x150510) op-order byte-exact** in `uedcli-native/src/fpoly.rs::calc_normal`
   — so native's recomputed normal equals the editor's for BOTH curved faces (dome 0.730585) AND axis faces.
   This is the missing piece that made §14's naive recompute regress: native's 1-ULP-off `calc_normal` gives
   axis faces `-0.99999994` where the editor stores exact `-1.0`; a byte-exact `CalcNormal` should yield the
   editor's exact axis value too.
2. **Then STORE the recomputed normal (discard the authored T3D `Normal=`)**, as the editor does — native
   currently keeps the authored normal (the `dot<0.9999` heuristic rarely fires). Only valid AFTER part 1.

Feasibility stands: pure SSE f32, no x87 (§14) — reachable; bounded to ONE function's instruction-level
op-order. Gate: castle byte-% must hold/improve (485/1156/26) and UNATCO `diff 105` twins drop from 20.
Evidence: `verts-logs/oracle-105.log` (the vert dump); scratch `_scratch/fpolyspike/{vert_byte_compare2,
find_editor_oporder}.py`. NEXT: disassemble `Engine.dll 0x150510` instruction-by-instruction and port.

## 17. CONSOLIDATED (supersedes §16; confirms §15's mechanism at the WORLD model): the residual is the editor's `bspAddPoint` WORLD-model vertex pool — `CalcNormal` op-order is byte-correct

This residual flip-flopped across §14→§17 as each probe refined the site; §17 is the consolidated,
hard-evidence conclusion. Two facts are now DISASSEMBLY/DUMP-certain:

**FACT 1 — `CalcNormal` op-order byte-MATCHES Engine.dll (§16 REFUTED).** Disassembled `FPoly::CalcNormal`
(`Engine.dll 0x150510`) instruction-by-instruction: the triangle-fan cross accumulation (pivot V0, X=aY·bZ−
aZ·bY etc., left-to-right `operator+=`) is bit-identical to native `fpoly.rs::calc_normal`. The ONLY real
difference was the normalize: Engine.dll's `NormalizeSlow` (`core.dll 0x249d0`) does `(f32)sqrt((f64)mag2)`,
not a direct f32 `sqrtss` — now matched in native (committed, faithful, castle-byte-identical, +2 regression
tests: axis quad → exact `1.0`; dome facet op-order pin). So §16's "op-order is the residual" is WRONG, and
its claimed axis "−0.99999994" does not reproduce (native gives exact `1.0`).

**FACT 2 — the editor's stored surf plane is computed over DIFFERENT (world-pooled) verts (§15 confirmed,
at the WORLD model).** Feeding native's now-byte-faithful `CalcNormal` the editor's BYTE-IDENTICAL
brush-model verts (§16 gdb dump, bit-for-bit) gives dome N.x = `0xbf3b0791` (0.7305842). golden105.dx STORES
`0x3f3b07a5` (0.7305854) — **~20 ULP away, and unreachable by ANY op-order/vertex-ordering** (brute-forced;
tops out at 0.7305842). Decisive: native's four sibling dome-facet normals (`078c/0791/07d6/07fe`) are a
WHOLLY DIFFERENT SET from the editor's four stored (`0797/079e/07a4/07a5`). Same verts + proven-same
arithmetic ⇒ the editor is not computing the stored surf plane from the brush/T3D verts. It recomputes over
its **`bspAddPoint`-POOLED world-model verts**, which differ from the exact T3D verts by ~1e-4; the surf
base-snap's ~3300 uu texture-origin lever arm amplifies that into the ~0.02 base-point twins (diff-105 = 20).

**Why §16's brush-model dump didn't catch it:** that dump proved the BRUSH-model verts match — but the stored
surf plane is reconstructed DOWNSTREAM, at the world model (post-CSG), over a different pool. The world ADD
*routing* stays byte-identical (§13 oracle) because classification is sign-robust to 1e-4; only the stored
coordinates diverge.

**Open caveat (epistemic honesty):** this residual has revised four times as probes deepened, so FACT 2's
"world-model pool" site is strongly inferred (native-can't-reach-it + different-sibling-set) but not yet
directly dumped. The DECISIVE next datum is a gdb dump of the editor's **world-model** pooled `Verts` for
Brush755's surfs (Editor.dll `bspAddPoint 0x34924`/world-model reconstruction), compared to native's
post-CSG surf verts — to see the ~1e-4 shift directly and pin the pool tolerance/add-order. THEN the fix is
to reproduce that world-vertex pool in native's `bspcsg.rs` so surf verts weld to the editor's coordinates
before the plane/base are stored. NOT a `calc_normal` change (that is now correct). Evidence:
`verts-logs/oracle-105.log`, `_scratch/fpolyspike/{dis_by_rva,brute,allfacets,nt2}.*`; the fpoly regressions
are committed (`92cb59ea8`).

## 18. REFRAME (Points characterization): the DOMINANT byte residual is pool/build ORDER, not the §14–§17 value-twins

A level-wide value-level diff of the **Points** pool (native `NativeUnatco_fresh.dx` vs golden762, bare
MAP REBUILD — Points is the one large section the bare golden builds comparably) reframes the whole target.
The §14–§17 thread chased the dome base-point **value** twins; this shows they are a MINORITY of the byte
residual.

**Native 10836 Points vs golden 10752 = +84 (count divergence).** Of native's 10836:
- **80.3% (8704) are BYTE-EXACT values present in both pools — but only 0.27% (29) positionally match.** A
  near-total **POOL-ORDER PERMUTATION** from index 0. Native reproduces golden's coordinates bit-for-bit for
  most points, INCLUDING 2988 off-grid *computed* points (not just trivial grid brush-verts) — so native's
  CSG arithmetic is right; it just serializes the pool in a different ORDER.
- **7.9% (861) are ~1e-4 VALUE twins** — the §17 world-pool base-snap shift (median 1.22e-4, tail to 4.5e-2,
  level-wide on far-from-origin surf base points). REAL but secondary.
- **11.8% (1271) structural** — +84 net-extra / differently-partitioned geometry (moved >0.05uu or no
  counterpart).

**VERDICT (HIGH confidence):** the dominant Points byte residual is **pool add-ORDER permutation of
byte-exact points (80%)** + the **+84 structural** delta — a DIFFERENT mechanism from the §17 value-twins,
which explain only ~8%. Fixing the twins alone leaves ~92% of the Points residual untouched. Ruled out:
coincidental grid matching (2988 off-grid points match byte-exact), insertion-shift masquerading as
permutation (positional=29 from index 0).

**Consequence for the plan.** The §14–§17 CalcNormal/vertex-pool-value thread is now known to be a ~8%
secondary residual (its faithful `NormalizeSlow` fix + regressions are committed `92cb59ea8`; the dome
value-twin is `bspAddPoint` world-pool, §17 — still true but minor). **The high-leverage lever is BUILD/EMIT
ORDER:** the order native adds points to `Model.Points` (and, downstream, the Nodes/Verts emit order — Verts
is the 381 KB section indexing into Points, so Points-order parity cascades into it). This is the §82b "Node
serialization ORDER / Points pool order" residual, at UNATCO scale.

**Apparent tension to resolve next.** The §13 editor-tree-oracle showed the world **bspAddNode ADD stream**
byte-identical native↔editor through N=105 — yet the full-level Points pool is permuted from index 0. So
either (a) `bspAddPoint` (vertex) add-order differs from `bspAddNode` (node) order — native pools vertices at
a different point in the build than the editor — or (b) the order diverges beyond N=105 and the permutation
is dominated by the 106–762 brushes. **Next probe:** compare native's vs the editor's `bspAddPoint` call
order (extend the oracle to log point-adds, or compare the two Points arrays as ordered sequences to locate
the first index where the byte-exact subsequence diverges), and characterize the +84 structural extras. Then
the fix is to match the editor's point/node emit order — far higher byte-% leverage than the dome twins.
NOT a `calc_normal` change (that is byte-correct, §17).

## 19. ROOT-CAUSED (HIGH confidence): the dominant residual is native's `bspBuild` FindBestSplit picking a different ROOT SPLIT than UnrealEd — the whole node/Points/Verts ORDER cascades from it

The §18 Points pool-ORDER permutation (80% byte-exact values, 0.27% positional) is root-caused to the BSP
**build/emit traversal**, and it diverges at index 0:

- **Points are pooled in node-emit order** (native 97.4% / golden 88.1% point-index↔first-referencing-node
  monotonic), and the **node-emit order itself diverges from index 0**. Node-plane sequence positional match
  2.5%, matching prefix 0.
- **The ROOT split differs outright:** native root plane `(-0.977,0.212,0)@-305.37` (a slanted wall) vs
  golden `(0,0,1)@240` (horizontal). golden's point[0] `(448,64,416)` isn't even in native's pool at [0]
  (`(0,0,192)`).
- **But 89.9% of node planes are a SHARED multiset** (5679 shared / only-nat 794 / only-gold 635). Same
  geometry, DIFFERENT partition + emit traversal. The permutation map is structured (Pearson 0.55, 79.6%
  adjacent-increasing, monotonic runs up to 383) = subtrees keep internal order but are visited in a
  different sequence — the signature of a different `FindBestSplit` root/recursion, not scattered noise.
- **Reconciles §13 (no contradiction):** the oracle matched the INCREMENTAL `bspAddNode` ADD stream during
  world CSG (brushes ≤105); the SERIALIZED arrays come from the SUBSEQUENT full `bspBuild` REBUILD
  (`csgRebuild`), which re-partitions from a fresh root and emits depth-first in a different traversal.
  Incremental-add parity ≠ serialized-array-order parity. The permutation is dominated by the rebuild
  traversal from the ROOT, not by brushes 106–762.

**VERDICT (HIGH confidence): (a) node-EMIT-ORDER divergence; the Points/Verts permutation follows it.**
Falsifies the alt "independent `bspAddPoint` order with node order matching" — node order does NOT match
(root split differs). Also: **Verts +25% (native 95942 vs golden 76488)** and the **+84 Points / +159 nodes**
structural deltas are a partition/fragmentation difference to resolve alongside the ordering.

**Fix target (supersedes the §14–§18 value-thread as the DOMINANT lever): match UnrealEd's `bspBuild`
partition selection + node emit traversal** — specifically **`FindBestSplit`** (`build.rs`/`bspcsg.rs`): the
root split already diverges, so a scoring / tie-break / candidate-iteration / stride difference vs the
editor's `csgRebuild` (`Opt=GOOD, Balance=12, stride=NumPolys/20`, §92 §2) mis-selects the root and cascades
into the entire tree + Points/Verts order. Native's `FindBestSplit` already makes the 95-brush CASTLE
byte-exact (node set 1156/1156), so the divergence is a scale-exposed subtlety in the scoring/tie-break, not
a wholesale mismatch. This is the §82b "Node serialization ORDER" residual, now localized to the root split
— the highest byte-% lever (it gates Nodes 328 KB + Verts 381 KB + Points). NOT a `calc_normal`/vertex-pool
change (§17: that is byte-correct and only ~8% of Points). Next: decode WHY native scores the slanted-wall
root above the editor's horizontal `(0,0,1)@240` — compute native's `FindBestSplit` scores for both root
candidates and disasm the editor's `FindBestSplit` scoring/stride — then port + castle-gate.

## 20. The root split is decided by the pre-repartition SOUP order/count — `FindBestSplit` scoring is byte-correct; the dominant lever is the `bspBuildFPolys`+`bspMergeCoplanars` soup

Decoded native's ROOT `FindBestSplit` vs the editor's (RVA `0x335d0`, `re-raw-zones/findbestsplit-params-decode.md`,
live-verified). The scoring is **byte-identical**: `Score = 12·|F−B| + 88·Splits`, PortalBias=0, GOOD stride
= `NumPolys/20` (`imul 0x66666667; sar 3`). Native's `find_best_split_exact` matches it (proven: castle
byte-exact, 1156/1156). **So the root divergence is NOT a scoring/param/tie-break bug.**

**Measured at the UNATCO root (NumPolys=2449, stride=122):**
- Native picks idx 1220, slanted wall `(-0.977,0.212,0)@-305`: on the sparse strided sample F=9 B=11
  splits=0 → score **24**. Editor's root `(0,0,1)@240`: native DOES sample it (idx 1830 etc.) but F=9 B=10
  splits=1 → score **100** → native ranks it worse.
- **Full stride-1 scores INVERT the ranking:** slanted wall F=1421 B=951 splits=76 → **12328** (globally a
  terrible splitter); `(0,0,1)@240` F=1161 B=1208 splits=24 → **2676** (globally excellent, 4.6× better).

So the slanted wall wins ONLY because the GOOD 1/20 stride happens to sample it favorably. Since scoring is
identical, the editor picks the horizontal only because ITS soup presents different polys at the strided
indices. **Root cause: the pre-repartition SOUP (the poly list fed to the final `bspBuild` repartition —
`make_ed_polys` tree-walk + `bsp_merge_coplanars`) diverges in ORDER and COUNT from the editor's at scale**,
and the sparse stride amplifies any soup difference into a different root → a different whole-tree traversal →
the §18/§19 Points/Verts/Nodes order permutation.

**Why no castle-safe `FindBestSplit` fix:** scoring is already editor-faithful. Forcing `(0,0,1)@240` (e.g.
OPTIMAL stride-1) would fix UNATCO but flips the CASTLE root away from the editor's GOOD-stride pick →
regresses castle 1156/1156. Any scoring/stride/tie-break change trades castle for UNATCO. Confirmed via an
env-gated `UEDCLI_FBS_ROOT_DUMP` diagnostic (inert on normal builds; castle 485/1156/26 held).

**The dominant lever (supersedes §19's "match FindBestSplit"): match the editor's SOUP — the ORDER and COUNT
of `bspBuildFPolys` (`make_ed_polys`) + `bspMergeCoplanars` output at scale.** This single target gates BOTH:
(i) the ORDER permutation (root → whole traversal → Points/Verts/Nodes serialization), AND (ii) the
STRUCTURAL deltas (+84 Points / +159 nodes / **+25% Verts** = native's `bsp_merge_coplanars` under-merges /
fragments the soup differently than the editor at scale — the original "coplanar merge" theme, now correctly
located in the soup, not a surf over-count). NOT a `FindBestSplit`/`calc_normal`/vertex-pool change.

**Next:** dump native's pre-repartition soup (order+count, in-process) and the editor's soup (gdb dump of
`Model->Polys` at the `bspBuild` entry, right after `bspMergeCoplanars` — the §92 §3 dump script) and diff
them: where does the order/count first diverge — a `make_ed_polys` tree-walk order difference, a
`bspMergeCoplanars` merge order/count difference, or a deeper CSG-tree divergence beyond N=105? That pins the
port. (Aside: the FindBestSplit diagnostic run measured castle compiled parity **44.05%** vs the recorded
43.04% — verify whether the committed `NormalizeSlow` fix `92cb59ea8` genuinely improved the castle.)

## 21. CONVERGENCE — the entire chain bottoms out at an incremental `bsp_brush_csg` near-coincident-plane clip divergence, reproducible at N=8

The §18/§19/§20 order-permutation → root-split → soup chain is now root-caused, decisively, to the incremental
CSG world model — NOT the soup machinery. Two facts settle it:

**`make_ed_polys` + `bsp_merge_coplanars` are BYTE-FAITHFUL.** Control on the castle (N=33, byte-exact final):
native's post-merge soup == the editor's LIVE `bspBuild`-entry soup — count 199/199, multiset 0/0, **order
prefix 199/199** (`polys_order_diff.py 33`; the saved subset goldens' `Model.Polys` are a validated order
oracle — castle golden33 == live editor-polys-33 log, 199/199). So when the incremental tree matches, native's
soup matches byte-for-byte. Do NOT touch `make_ed_polys`/`bsp_merge_coplanars`.

**The incremental world model diverges from the first ~8 brushes.** Native soup vs editor golden soup
(mover-clean, order-preserving):

| N | editor | native | Δ | onlyEd | onlyNat |
|--|--|--|--|--|--|
| 8 | 45 | 39 | −6 | 7 | 1 |
| 30 | 190 | 184 | −6 | 7 | 1 |
| 75 | 534 | 525 | −9 | 17 | 8 |
| 105 | 836 | 826 | −10 | 25 | 15 |

First divergence at **N=8, ordered index 0**. It is BIDIRECTIONAL with DIFFERENT planes (native-only slanted
`(-0.7,0.2,0.7)`; editor-only **axis-aligned** `(0,0,±1)@±416`) — so NOT a walk-order shuffle and NOT an
under/over-merge of the same planes. The earliest only-editor faces are a **thin box** (x∈{448,452},
z∈{414,416}: 2–4-unit gaps = the §3/§12 near-coincident-plane family) whose faces native **DROPS** — native net
**UNDER-produces** the soup. Because `make_ed_polys` is faithful, a divergent soup ⇒ a divergent incremental
world model: native's `bsp_brush_csg` / `FilterWorldThroughBrush` **clip-selection over-discards faces at
near-coincident planes** that the editor keeps. That wrong world model (i) yields the different soup multiset
and (ii) walks in a different order, which the sparse GOOD stride (NumPolys/20) amplifies into the different
root split → the whole Nodes/Points/Verts permutation (§18–§20).

**Corrections to earlier sections:** §20 said native "under-merges → more soup" — WRONG; native UNDER-produces
(fewer). The full-scale **+25% Verts is repartition-side fragmentation from the wrong root split**, not a bigger
soup. This also unifies the whole effort: the §3 "+82-surf bidirectional", the §12 "axis-aligned structural
clip in (213,396]", and now the byte-order permutation are ALL the SAME root — the incremental near-coincident
clip-selection — just measured at different downstream stages. (The §13 oracle's "ADD stream matches ≤N=105"
tracked node routing, not which faces survive the filter, so it's consistent with a face keep/drop divergence.)

**Port target (the real one, small + reproducible): fix native's incremental `bsp_brush_csg`/
`FilterWorldThroughBrush` clip-selection so the near-coincident thin-box faces survive as the editor keeps
them — decode at N=8 (a thin box, ~8 brushes; golden8 soup is cached, so it's static/in-process, no live
editor).** Once the incremental world model matches, the soup order+count, the root split, and the entire
byte-order cascade follow automatically. Castle-gate (must stay 485/1156/26/43.04%). This is the dominant
byte-parity lever, finally localized to a tiny reproducible case. Probe: `_scratch/unatco_soup_probe.py`.

## 22. DEFINITIVE root-cause (corrects §21): an Add-brush Outside-propagation error (§10.8), NOT a clip tolerance — no castle-safe local fix; the residual is systemic incremental-tree divergence

§21's "near-coincident clip / `FilterWorldThroughBrush` over-discard" is REFUTED by decisive isolation at N=8.

**The N=8 soup residual (native 39 vs editor 45) is ONE brush's Add contribution.** golden8 (editor build of
exactly these 8 brushes, cached) vs native: shared 38, onlyEditor **7**, onlyNative 1 — and all 7 belong to
**Brush74** (the first-added brush, `CsgOper=None`→Add, a thin 4×112×2 bar at x[448,452] y[−48,64] z[414,416]):
5 protruding faces native NEVER emits (x=452 `(-1,0,0)`, z=416 `(0,0,-1)`, z=414 `(0,0,1)`, y=±`(0,±1,0)`),
plus 2 that are the room's x=448 east wall split around the nub (native keeps it as 1 whole face = the lone
onlyNative).

**Native's SUBTRACT CSG is byte-faithful.** Built `golden_no74.dx` (the 7 subtracts, no Brush74): native's
7-subtract soup == editor's **39/39 byte-exact, zero divergence**. So the world partition before Brush74 is
identical — the nub region is VOID in native too. The ENTIRE residual is Brush74's Add.

**It is NOT ordering.** Feeding native the editor's exact CSG order (golden8 iActor 82,777,480,420,418,527,74,
324) → shared 38; Brush74 strictly last → shared 40 (native emits the 2 wall-split faces but STILL none of the
5 protruding). No permutation reaches 45.

**The actual fault: Add-descent Outside-propagation.** Native's world is identical to the editor's ⇒ same
solid/void ⇒ the nub is void. Yet when Brush74's Add filters down native's tree, its 5 protruding faces
classify **F_INSIDE** and are dropped — the `Outside` flag arrives "solid" at the leaves despite the region
being void. This is the **§10.8 systemic Outside-propagation residual** in `filter_ed_poly`'s Add descent
(`bspcsg.rs:568`), exposed by a late Add against the coincident x=448 subtract wall. `FilterWorldThroughBrush`
and the subtracts are byte-exact — the fault is the **Add leaf classification**, driven by native's incremental
tree/Outside STATE diverging from the editor's (even where node ADDs match, §13 — the Outside flags are not in
the ADD stream).

**Why no castle-safe local fix (the known wall).** Native's `is_csg_filter` dead-node clause (§8.1) that flips
this Outside flag is LOAD-BEARING for castle parity (474→485 surfs); it is a HEURISTIC that is castle-correct
but diverges from the editor's exact Outside-propagation on Brush74's coincident-wall configuration. Changing
it regresses the castle (the "forced it, regressed castle twice" family, §3/§92 §6). Reordering makes UNATCO
worse. No local lever closes it castle-safe.

**Unification + re-scoped lever.** This is the SAME root as §3/§12/§18–§21, now definitively named: the
dominant byte residual is native's incremental **Add-brush Outside-propagation** diverging from UnrealEd's
exact `bspBrushCSG` Add leaf-classification — systemic from the first brushes — which drops/keeps different
faces → different soup → (via the sparse GOOD stride) different root split → the whole Nodes/Points/Verts byte
order + the +84/+159/+25%-Verts. The lever is NOT a tolerance, ordering, `FindBestSplit`, `make_ed_polys`,
`bsp_merge_coplanars`, or `calc_normal` (all proven faithful/byte-correct) — it is the exact editor
Outside-flag descent in Add CSG. Next: disassemble UnrealEd's Add filter Outside-propagation
(`bspBrushCSG`/`FilterEdPoly` Add leaf func) and replace native's castle-tuned heuristic dead-node clause with
the editor's EXACT rule — a deep, castle-gated re-implementation (not a one-liner), the true remaining port.
Probes: `_scratch/{n8_diff.py,build_no74.py}`.

## 23. DEFINITIVE (corrects §22): the residual is native's incremental BSP TREE STRUCTURE (coplanar chain-head orientation), not Outside logic — editor 101 nodes vs native 52 at N=8; castle-load-bearing (§10.9)

§22's "Outside-propagation bug / nub is void / is_csg_filter clause" is refuted by a live editor tree dump +
a solidity oracle. The true root, decoded:

**The x=448 chain-head orientation flips the whole classification.** Native drops Brush74's 5 protruding
faces because they descend to **native node 33 = the x=448 wall with normal (−1,0,0)** via BACK, arriving
`outside=0` (solid) → `outside && !csg = 0` → dropped. The editor's incremental tree (LIVE gdb dump at
`bspBuildFPolys`, `_scratch/editor-struct-unatco-8.log`, no wedge — **101 nodes vs native's 52**) carries the
SAME x=448 plane with the **OPPOSITE normal (+1,0,0)** (editor node 3, dead/pass-through), so Brush74's bar
(x∈[448,452]) is **FRONT**, keeps its earlier `outside=1` (void-side), and all 6 bar faces are kept as editor
root nodes 0–5. **Editor Outside=1, native Outside=0 — forced purely by the flipped x=448 splitter
orientation.** This is the §10.8/§10.9 coplanar-chain-head orientation flip (same plane, opposite normal →
swapped front/back → opposite Outside), generalized to UNATCO.

**Two §22 claims REFUTED with hard evidence:**
1. **"The nub is void" — FALSE.** Bar center (450,8,415) is **SOLID**: the editor's `golden_no74.dx`, native's
   BSP, AND an independent half-space oracle all three agree (room void is x<448; the bar at x>448 is buried
   in solid). So **native CORRECTLY drops the buried faces; the editor OVER-KEEPS them** (its dead (+1,0,0)
   chain-head leaves the bar nominally FRONT/void). The parity target is to reproduce the editor's
   (byte-identical) output regardless — so native must reproduce the over-keep.
2. **"is_csg_filter dead-node clause governs Brush74" — FALSE.** Brush74's descent path has NO dead nodes (all
   nv=4); the clause is never exercised on it. §22's named lever is a dead end (restoring it changes nothing
   for Brush74 and regresses the castle, §8.6).

**Why no castle-safe local fix (the real wall).** The divergence is the whole incremental tree STRUCTURE —
editor 101 vs native 52 nodes at N=8: WHICH coplanar x=448 face becomes the BSP **chain-head splitter**, its
ORIENTATION (+1 vs −1), and its live/dead status. This is §10.9's `bspCleanup`/`bspAddNode` `NODE_Plane`
chain-head selection + dead-node retention, which is **castle-load-bearing** (§10.9 made the 95-brush castle
byte-exact; gate 485/1156/26/leaves384/zones4 confirmed HOLDING this session). Native's chain-head rule is
tuned so the castle matches; UNATCO's coincident x=448 subtract-wall + late Add exposes a case where it picks
the opposite representative/orientation. Flipping it to the editor's is a deep structural change with no
castle-safe lever — the "regressed the castle twice" family (§3/§92 §6). Per report-don't-force, no code
change; nothing committed.

**This is the definitive, unified root** of §3/§12/§18–§22: native's incremental `bspAddNode`/`bspCleanup`
builds a structurally LEANER coplanar-chain tree than UnrealEd (52 vs 101 at N=8), so a coincident-plane
chain-head takes the opposite orientation → opposite Outside → different face keep/drop → different soup →
(via the sparse GOOD stride) different root split → the entire Nodes/Points/Verts byte-order permutation +
the +84/+159/+25%-Verts. It is NOT clip tolerance, ordering, FindBestSplit, make_ed_polys, bsp_merge_coplanars,
calc_normal, Outside-logic, or the dead-node clause (all proven faithful/not-the-cause). The remaining port is
**§10.9 coplanar chain-head selection parity** — replicate the editor's exact `bspAddNode` NODE_Plane
chain-head/promotion + dead-node retention so native's incremental tree matches node-for-node (52→101),
castle-gated. Deep, multi-cycle, known-hard. Next instrument: `tree_struct_diff` native↔
`editor-struct-unatco-8.log` to decode the exact chain-head/promotion rule. Harness: `_scratch/{n8_trace,
n8_solid,n8_diff,editor_struct_unatco}.py`, `editor-struct-unatco-8.log`.

## 24. THE ROOT (corrects §23): native hardcodes `Model->RootOutside=false`; UnrealEd's is effectively 1 for UNATCO → native drops the level's leading Add and every downstream node cascades

§23's "chain-head orientation flip / 52 vs 101 nodes" had an ordering confound and is superseded. Decoded
cleanly (evidence committed `4c10ec7b3`: editor N=8 tree dump + `tree_struct_diff.py`):

**Matched TRUNK order (Brush74 first, as the editor golden processes it — §23 built native in saved-`.dx`
`iActor` order with Brush74 7th), native = 69 nodes vs editor = 101.** The editor's nodes 0–5 ARE Brush74's
six bar faces: **it keeps the leading Add**. Native drops it entirely — `build_geometry_bspcsg([Brush74])`
alone = **0 nodes**.

**The SOLE rule difference is `Model->RootOutside`.** The empty-tree filter is byte-identical
(`bspFilterFPoly 0x31f50`: `Func(…, RootOutside==0, F_ROOT)`; native `bspcsg.rs:711`). Native hardcodes
**`root_outside=false`** (`bspcsg.rs:2009`), so the empty world classifies **F_INSIDE**, and `leaf_func::Add`
(which adds only on F_OUTSIDE / F_COPLANAR_OUTSIDE) DROPS all 6 bar faces. The editor's **`RootOutside=1`**
for this level → **F_OUTSIDE** → the bar is kept. Those +6 leading nodes (a kept bar = a permanent solid
divider) cascade into the +32 downstream node gap → the different soup → (sparse GOOD stride) the different
root split → the entire Nodes/Points/Verts byte-order permutation + the +84/+159/+25%-Verts. **This single
property is plausibly the fundamental root of the WHOLE byte residual.**

**Corrects §23:** after `bspCleanup`, BOTH trees' reachable x=448 splitter is `(−1,0,0)`; the editor's
`(+1,0,0)` bar-face node is dead/unreachable garbage — there is NO reachable orientation flip. The robust,
reproducible difference is the 6 kept bar faces, caused by RootOutside.

**Why castle-hard (report-don't-force).** `root_outside=false` is REQUIRED for the castle: its first brush is
`World_7e9y81` = **Subtract**, kept only on F_INSIDE — flip it and the castle breaks. UNATCO merely LEADS
WITH AN ADD. A `root_outside = (first world brush is Add)` heuristic is castle-trivially-safe (castle's
Subtract-lead → unchanged) but NOT proven editor-yielding: `root_outside=true` re-polarizes every subtract's
classification and, unverified, likely does not reproduce the editor's 101-node tree / may worsen UNATCO.
UnrealEd's ACTUAL per-level `RootOutside` determination is undecoded — the agent flags an **excluded
"world-shell" Add** brush (a large enclosing additive that native drops, which FWTB would re-add) as the
likely mechanism: with the shell present the world is solid and RootOutside semantics resolve; native's
exclusion of it forces the wrong polarity.

**Next (the real, now-tractable target): decode UnrealEd's `RootOutside` / world-shell handling.** WHAT sets
`Model->RootOutside=1` for UNATCO (a `LevelInfo`/`ZoneInfo` flag? the presence of a world-shell Add? a
`csgRebuild` default?); WHY does native's build exclude the world-shell Add; and does including it / setting
RootOutside per the editor's exact rule (a) yield native's leading Add kept + the 101-node tree, AND (b) keep
the castle byte-exact (castle has no such shell / is subtractive). If yes, this ONE fix may cascade-close the
whole byte-order residual. Disasm `bspBrushCSG`/`csgRebuild` RootOutside init + inspect the UNATCO trunk for
the world-shell Add. Evidence: `logs/editor-struct-unatco-8.log`, `tree_struct_diff.py`, `_scratch/n8_*.py`.

## 25. §24 REFUTED (RootOutside is 0 for BOTH levels) — the lever is the incremental Outside-propagation (§22/§23 core); honest scoping of the remaining work

§24's "editor RootOutside=1 for UNATCO / excluded world-shell Add" was an inference from the editor keeping
Brush74, and it is WRONG. Decoded, not inferred:

- **On-disk RootOutside = 0 for BOTH the UNATCO golden and the castle golden** (read from the serialized Model
  trailer). UnrealEd's build-time RootOutside is identical to native's `false`.
- **No world-shell Add exists.** UNATCO's first world-CSG brush (trunk order) is Brush74 itself (a tiny
  CSG_Add bar); the large Adds are ordinary room details at csgidx 263+. Native's `_in_world_csg` excludes
  nothing structural.
- `bspFilterFPoly` @`0x31f50` decode: the non-empty descent's Outside seed IS `Model->RootOutside` (+0xf0) —
  native `bspcsg.rs:711/:718` are byte-faithful. So RootOutside is NOT the divergence.
- Fix test (env-gated `root_outside=true`, then removed): N=8 → **6 nodes** (drops all subtracts, void world),
  NOT the editor's 101; and it **regresses the castle** (926/491/26, leading Subtract breaks). Refuted.

**The true lever (back to §22/§23, refined):** under identical RootOutside=0, the editor keeps Brush74's Add
faces (F_OUTSIDE) while native drops them (F_INSIDE) — in BOTH processing orders. Since native's SUBTRACT CSG
is byte-faithful (§22, no74 soup 39/39) and the FINAL bar region is solid (§23, three oracles), the divergence
is the **incremental Outside STATE** at the moment Brush74 is filtered: after the leading subtracts, native's
incremental world classifies the bar region SOLID where the editor's classifies it VOID. This is the §10.8
incremental Add leaf-classification / tree-state divergence — castle-load-bearing (the clause that governs it
is required for castle byte-exactness).

**Concrete NEW lead (the `RO=true` side-signal).** With a void Outside seed, native's full-UNATCO counts nearly
MATCH the editor: Vectors 572 vs golden 599 (was +24% at RO=false), Verts 77172 vs 76488 (was +25%), nodes
6796. So the §91 "+24% Vectors / +25% Verts over-production" is **tied to Outside-seed POLARITY** — the editor
behaves "void-like" for the over-production despite RootOutside=0, which native's solid seed does not
reproduce. (Not a usable fix — it's a global flip that breaks the castle and drops subtracts — but it pins the
over-production to the incremental Outside handling, unifying it with the keep/drop divergence.)

**Honest scoping (5 cycles, §21–§25, have circled this core).** The residual is the deepest part of the CSG
core — native's incremental Outside-propagation / tree-state diverging from UnrealEd's under identical inputs
+ RootOutside — and it is entangled with castle byte-exactness (every attempted flip regresses the castle).
Single-cycle probes keep pinning-then-refuting specific mechanisms (clip → Outside-logic → chain-head →
RootOutside → back to incremental Outside-state), which indicates this needs a careful, MULTI-cycle
differential re-analysis, not a one-shot fix. Proven NOT the cause and not to be re-chased: clip tolerance,
FilterWorldThroughBrush, ordering, FindBestSplit, make_ed_polys, bsp_merge_coplanars, calc_normal,
RootOutside, the is_csg_filter dead-node clause. **The one open lever: the exact editor incremental Add
leaf-classification / Outside-seed-per-brush during the subtract sequence.** Next (surgical): trace native's
solid/void of the bar point (450,8,415) after EACH leading subtract vs the editor's incremental state (needs
an editor incremental gdb trace or per-N goldens) to pin the FIRST brush where they diverge — the minimal
root. Harness: `_scratch/{read_rootoutside,full_build,castle_build,nstruct_order}.py`.

## 26. CONVERGED (hard-measured): first divergence = K=7 Brush74 Add; native routes the bar SOLID at the LIVE x=448 (−1,0,0) node, editor routes it VOID — the §10.9 coplanar chain-head, no cheap castle-safe fix

Surgical first-divergence pin (in-process K-series, editor CSG order 82,777,480,420,418,527,**74**,324):

| K | last | op | nodes/surfs | bar (450,8,415) | Brush74 faces kept |
|--|--|--|--|--|--|
| 1–6 | …527 | Sub | 6→35 | SOLID | — |
| 7 | **Brush74** | **Add** | 38/36 | SOLID | **1 of 6** |
| 8 | 324 | Sub | 42/40 | SOLID | 1 |

Editor goldens (cached): **golden_no74 (7 subtracts) = 39/39 == native's no74 (39/39)** — the pre-Add world is
BYTE-IDENTICAL. golden8 = 45/44: Brush74 ADDS 5 new surfs + the x=448 wall-split = **6 kept**; the editor
lands the bar in a real void zone (leaf 3, zone 4), native leaves it undifferentiated solid (leaf −1).

**First divergence = K=7, Brush74's Add — NOT a subtract-carving divergence** (pre-Add world identical). Hard
trace of the bar descending native's pre-finalize tree: `outside` flips to **F_INSIDE at node 33 = the x=448
subtract wall, normal (−1,0,0), LIVE (nv=4)** — bar (x=450) is on its BACK, so `no = outside && !csg = false`
→ routed SOLID → faces buried → dropped. The editor keeps them ⇒ its incremental tree routes the bar VOID.

**This CONFIRMS §23 (coplanar chain-head orientation at the coincident x=448 plane) and REFUTES §22 (node 33
is LIVE — the `is_csg_filter` dead-node clause is not exercised) and §24 (RootOutside=0 for both).** Native's
incremental BSP carries the coincident x=448 plane as a **(−1,0,0)** chain-head CSG splitter (bar on BACK/
solid); the editor's routes the bar FRONT/void.

**OPEN TENSION (must resolve before porting):** §25 read the editor's post-`bspCleanup` reachable x=448
splitter as ALSO (−1,0,0) with the (+1,0,0) node dead; §26's mechanism needs the editor to route the bar VOID
(via a (+1,0,0) live node or an extra coplanar-cascade node). These disagree. The editor side is INFERRED
from §23's earlier gdb dump, not re-verified at K=7. **Decisive next datum: a fresh editor incremental gdb
dump at K=7 (right after Brush74's Add) showing exactly which node/orientation/live-status routes the bar to
void** — this pins the editor's exact §10.9 chain-head/coplanar-cascade rule.

**Fix = §10.9 coplanar chain-head selection parity** (`bspAddNode` NODE_Plane chain-head + coplanar-cascade +
`bspCleanup`): make native's incremental tree carry the coincident x=448 plane as the editor does so the bar
routes void. **NOT castle-safe as a local flip** — the same chain-head rule makes the 95-brush castle
byte-exact (485/1156/26), and every flip attempted across §21–§26 regressed it. It is a deep, castle-gated
re-implementation, not a one-liner. Definitive scoping after 6 convergent cycles: **no cheap castle-safe byte
win remains; the remaining byte-parity work is the §10.9 incremental chain-head-parity port** — decode the
editor's exact rule (fresh K=7 dump + `bspAddNode` disasm), then re-implement native's coplanar chain-head to
match node-for-node while holding the castle. PROVEN-NOT-cause (do not re-chase): clip tolerance, FWTB,
ordering, FindBestSplit, make_ed_polys, bsp_merge_coplanars, calc_normal, RootOutside, dead-node clause.
Probes: `_scratch/{kprobe,struct_trace}.py`; editor evidence `harness/editor-tree-oracle/logs/editor-struct-unatco-8.log`.

## 27. §26 orientation-flip REFUTED by direct dumps; §25 confirmed — the divergence is native's leaner 52-node tree dropping Brush74's Add box; concrete lever = the §8.1 `is_csg` nv-clause deviation

Both bar (450,8,415) descents dumped directly (editor `editor-struct-unatco-8.log`; native N=8 editor-order):

- **EDITOR → VOID.** Path `0→1→2→51→4→5→leaf`: ND2 (x=452,−1,0,0) FRONT; **ND51 (x=448,−1,0,0, LIVE nv=4)** BACK
  → SOLID; **ND4 (y=−48,0,1,0, live)** FRONT → VOID; ND5 (y=64) FRONT → VOID. The deciding nodes are Brush74's
  OWN kept y-faces (ND4/ND5) inside ND51's back subtree; editor nodes 0–5 ARE Brush74's full 6-face box at the
  tree root. ND3 (x=448,**+1,0,0, nv=0 DEAD**) is UNREACHABLE (no parents).
- **NATIVE → SOLID.** Path ends at the live x=448 (−1,0,0) node (bar on BACK → solid); Brush74 contributes NO
  bar faces (its box was dropped). (§26's "node 33" is now the dead chain-head; the live decider is node 44 —
  index drift, `bspcsg.rs` is uncommitted-modified.)

**§25 vs §26 RESOLVED: §25 right, §26 WRONG.** Both trees' reachable x=448 splitter is **(−1,0,0), live,
bar-on-BACK — identical**; the (+1,0,0) node is dead on BOTH sides. There is **NO x=448 orientation flip, no
live +1 node, no extra coplanar cascade** (§26 refuted). The editor routes VOID solely because it **KEEPS
Brush74's leading-Add box** (its 6 faces classify F_OUTSIDE → 6 root nodes enclosing the bar); native **DROPS**
it (F_INSIDE) against its structurally **leaner 52-node pre-Add tree** (editor 101) → no box → subtract-world
routes the bar SOLID.

**So the root is the 52-vs-101 STRUCTURAL divergence — native's incremental tree retains fewer coplanar-chain
nodes than UnrealEd — which flips Brush74's Add leaf-classification.** This is the §22/§25 Add-leaf-class
divergence, driven by tree leanness; NOT a chain-head orientation (§23/§26) and NOT RootOutside (§24).

**CONCRETE decoded lever (the most testable yet, confidence MEDIUM):** native's `is_csg` uses a **§8.1
nv-INDEPENDENT heuristic — a deliberate deviation from UnrealEd's real `IsCsg`, which requires `nv>0`**
(`csg = flag && nv>0`). This deviation was introduced to make the 95-brush castle byte-exact (485/1156/26) and
may be exactly what makes native's tree LEANER (dropping/merging coplanar-chain nodes the editor keeps live).
NOTE: the bar's own descent touches only nv>0 nodes, so the nv-clause is not the *direct* decider on that path
— it is a broad structural lever that could grow native's tree toward the editor's 101 and thereby flip
Brush74's classification.

**Next (cheap test):** make native's `is_csg` FAITHFUL to the editor (`csg = flag && nv>0`), rebuild, and
measure: (a) does native's N=8 tree grow toward 101 / keep Brush74's box (soup 39→45)? (b) does the FULL-level
root split / Points positional-match improve? (c) **does the castle stay byte-exact 485/1156/26/43.04%?** If
the faithful rule holds the castle AND helps UNATCO, it is the fix (the §8.1 deviation was a castle-overfit).
If it regresses the castle, the deviation is load-bearing and the fix is the deeper §10.9 chain-head/coplanar-
retention re-implementation (the "regressed castle twice" wall). Either way this is the decisive test of the
last concrete lever. Confidence HIGH on the verdict/outcomes (direct dumps), MEDIUM on the nv-clause being the
portable fix. Probes: `_scratch/{descend_editor_bar,descend_native_bar,native_tree_struct}.py`.

## 28. `is_csg` nv-clause is INERT (dead weight); tree cleaned + baseline reconfirmed; the concrete lever is `bsp_cleanup` dead-node RETENTION (native splices what the editor keeps)

Tested making native's `is_csg_filter` (`bspcsg.rs:437`, `(node_flags & 0x21)==0`) FAITHFUL to UnrealEd's real
`FBspNode::IsCsg` (which additionally requires `nv>0`). Result: **byte-IDENTICAL Model body on castle
(485/1156/26/43.04% held), N=8, and full UNATCO** — zero change. Instrumentation showed the two rules diverge
on 18/396/788 dead (nv==0) nodes, yet all bodies are byte-identical, because the §10.9 `bsp_cleanup` dead-node
splicing (added after the 2026-07-17 §8.1 note) now removes dead nodes per-brush, making the nv-independence
REDUNDANT. So the §8.1 deviation is **neither a fix nor load-bearing — it is dead weight** (candidate for a
later cleanup). NOT the residual.

**Housekeeping:** reverted the accumulated uncommitted diagnostic scaffolding (`dump_root_fbs`,
`debug_brush_model_reconstruct`, +290 lines, env-gated/inert) from `bspcsg.rs`/`lib.rs` — it was causing
measurement drift across cycles. Clean-HEAD baseline reconfirmed: **castle 485/1156/26/43.04%**. (Note the
earlier "19.07%" vs a later "14.81%" UNATCO byte-% gap was golden/build-method drift; re-baseline UNATCO
cleanly before trusting any % going forward.)

**The concrete lever, newly localized: `bsp_cleanup` dead-node RETENTION.** The editor's N=8 incremental tree
keeps **101 nodes INCLUDING dead/pass-through ones** (e.g. ND3 x=448 (+1,0,0) nv=0 DEAD, unreachable, still
serialized); native's `bsp_cleanup` SPLICES dead nodes per-brush → a leaner 39–52-node tree. That leanness is
what drops Brush74's leading-Add box (§27) and cascades into the whole byte-order + node/vert counts. So the
divergence is **which dead/coplanar-chain nodes UnrealEd RETAINS that native's `bsp_cleanup` removes.** But
native's `bsp_cleanup` splicing is itself the castle 474→485 win — so its retention rule is castle-load-bearing
(the "regressed castle twice" tension).

**Diagnostic phase COMPLETE (§13–§28).** Every concrete, testable lever is now eliminated with hard evidence.
PROVEN-NOT-cause (exhaustive — do NOT re-chase): stale-`.dx`/mover-confound (+82/+170 were artifacts), clip
tolerance, `FilterWorldThroughBrush`, brush/CSG ordering, `FindBestSplit` scoring, `make_ed_polys`,
`bsp_merge_coplanars`, `calc_normal` (byte-correct; `NormalizeSlow` fix committed `92cb59ea8`), the vertex pool
(brush-model verts byte-identical), `RootOutside` (=0 both), `is_csg` nv-clause (inert). **THE residual = the
§10.9 incremental tree STRUCTURE: `bsp_addnode` coplanar-chain linking + `bsp_cleanup` dead-node retention
producing a leaner tree than UnrealEd**, which flips the leading-Add classification → the whole
Nodes/Points/Verts byte-order + the +count/+25%-Verts. This is a DEEP, castle-load-bearing re-implementation,
NOT a single-cycle fix (confirmed across §21–§28's pin-then-refute cycles).

**Next (decode toward the port):** compare native's `bsp_cleanup` dead-node output to the editor's 101-node
retention at N=8 (`editor-struct-unatco-8.log`) — pin exactly which dead/pass-through coplanar nodes the editor
KEEPS that native splices, and decode UnrealEd's `bspCleanup` retention rule (disasm) — then re-implement
native's retention to match node-for-node while holding the castle. This is the frontier; treat as a scoped
multi-cycle port, not a quick win.

## 29. STAGE CORRECTION (fixes a §26–§28 confound): the "101 vs 52 leaner tree" was a stage mismatch — the lever is Brush74's incremental Add face-classification, NOT bsp_cleanup retention (§28 refuted)

**Load-bearing correction.** The editor's 101-node N=8 tree (`editor-struct-unatco-8.log`) is dumped at
`bspBuildFPolys` on golden8.dx = **post-`csgRebuild`/repartition**. §26/§27/§28 compared it against native's
**PRE-repartition incremental** tree (52/39) — a STAGE MISMATCH. Stage-fair node counts:

| tree | no74 (7 sub) | N=8 (+Brush74) |
|--|--|--|
| editor (post-repart) | 39 | **101** |
| native post-repart | **39 (== editor, byte-identical §26)** | 42 |
| native pre-repart (incr) | 49 | 52 |

**The 101-vs-42 gap is NOT dead-node retention (§28 REFUTED).** Editor N=8 = 96 live / 5 dead / 4 unreachable.
Plane-multiset diff (editor vs native-post): native lacks ZERO planes; the 59-node gap is **live
duplicate-plane iF/iB tree-FRAGMENTS (iP=−1)** — e.g. x=112 ×9 vs ×1, z=−416 ×9 vs ×4 — NOT iP coplanar-chains
and NOT dead nodes. `bsp_cleanup` (splices only nv=0) can touch ≤5 of the 59 → not the residual.

**Causal verdict: EGG-first (upstream Add-drop), HIGH confidence.** The pre-Add world is identical (both 39,
byte-identical §26; first divergence pinned to K=7). Brush74's Add then adds **+62 nodes in the editor vs +3
in native**. Native keeps only 3 of Brush74's 6 box faces; the other 3 classify **F_INSIDE (the bar is buried
in solid behind the x=448 wall) → never emitted**. The editor keeps all 6 (bar → void leaf), and those box
planes fragment the surrounding walls into ~54 live duplicate-plane nodes. So the lever is the **incremental
Brush74 Add face-classification (`bsp_filter_fpoly` Outside-propagation)** — partially reviving §22, refuting
§28's dead-node framing and §26/§27's "leaner-tree/chain-head" framing.

**The sharp remaining question (needs the editor's INCREMENTAL, pre-repartition tree):** does native drop
Brush74's 3 faces because of (a) pure Add-Outside-logic on an tree IDENTICAL to the editor's at K=7, or (b) a
native incremental tree that already differs from the editor's before Brush74? Native's incremental no74 = 49;
the editor's incremental count is UNVERIFIABLE statically (the golden is post-repartition). **Decisive datum:
a live editor gdb dump of the INCREMENTAL (bspBrushCSG, pre-repartition) tree straddling Brush74's Add at
K=7** — if it is also 49 nodes and node-identical to native's pre-Add, the pure-Add-logic hypothesis is
confirmed (a specific `bsp_filter_fpoly` classification to decode); else it is a tree-structure divergence.

**Castle-safety tension UNCHANGED (the persistent wall).** The fix requires native to KEEP faces it currently
— GEOMETRICALLY CORRECTLY — drops as buried solid. The castle is byte-exact (485/1156/26) precisely BECAUSE
native drops such faces, and every flip across §21–§28 regressed it. So even the exact Add-classification rule
must KEEP Brush74's buried faces yet DROP the castle's analogous buried faces — i.e. UnrealEd's rule must
differ between the two configs on some decodable property. Finding that property (or confirming there is none
and the divergence is deeper incremental-tree state) is the frontier. This is a deep, castle-load-bearing
re-implementation, not a single-cycle fix — consistent with §28's "diagnostic complete" scoping, now with the
lever corrected to the Add face-classification. Probes: `_scratch/{n8_struct_dump,n8_preopt_dump,no74_and_pre,
tree_taxonomy,tree_counts}.py`.

## 30. The first-brush is a dropped CSG_Add (confirmed); a `root_outside` POLARITY flip is the WRONG fix (§25 tradeoff, reverted); the faithful mechanism is seeding the first brush's faces as ROOT NODES with RootOutside=0

**Confirmed root (static oracle + in-process):** UNATCO's first in-world brush (`csg_order[0]`, actor
"Brush74", trunk idx 0) is a **CSG_Add** thin bar on an EMPTY world. Native's empty-model filter branch
(`bspcsg.rs:709-716`) classifies the empty world **F_INSIDE** (root_outside=false) → `leaf_func::Add` (emits
only on F_OUTSIDE) → **drops all 6 faces** (`build([Brush74])` = 0 nodes). This dropped seed cascades into the
whole UNATCO byte-order divergence. The §23–§29 "buried face / leaner tree / chain-head / dead-node" arc was
a REORDERED golden8-SUBSET artifact (Brush74 processed 7th there); in real trunk order it is FIRST.

**A `root_outside` polarity flip is NOT the fix (tested, REVERTED).** Seeding `root_outside` from the first
brush's oper (Add→true) to keep all 6 faces **void-polarizes the world exterior**, so the CSG_Subtract rooms
right after it classify F_OUTSIDE and DROP: surfs 3609→**3432** (golden 3616), nodes 6473→6793, root split
(0,1,0)@488 (golden (0,0,1)@240 — still wrong), byte-% 14.81→16.47 (barely moves). Verts 95942→77124 and
vectors 745→572 improve toward golden (the §25 side-signal), but net it reproduces §25's global-`root_outside=
true` behavior (6793/77124/572 ≈ §25's 6796/77172/572) — the first Add's void polarity propagates
structurally; restoring the flag doesn't undo it. Castle HELD (485/1156/26, byte-identical — Subtract-led
never fires the branch). **A single RootOutside polarity cannot keep BOTH the leading Add and the subtracts.**

**The faithful mechanism (from oracle-105.log):** UnrealEd adds Brush74's 6 Add faces as **world-tree ROOT
NODES 0-5** (`parent=0 place=3`=NODE_ROOT + a `place=1` front-chain) into the empty model — a `bspAddNode`/
`bspBuild`-style SEED — while keeping the world SOLID (RootOutside=0). The faces are retained as structural
splitters even though internally-solid at first; as later subtracts carve rooms AROUND the bar, they become
room-facing/visible. So the editor does NOT flip polarity — it SEEDS the first brush's faces as nodes and
keeps RO=0. Native instead FILTER-classifies the first brush and drops an Add's faces.

**NEXT (the untested faithful fix): seed the first brush's polys as root nodes (bspAddNode/bspBuild) with
RootOutside=0 UNCHANGED**, so an Add's faces are retained as splitters AND subtracts still carve (no void
polarity). Castle-safety RISK: for a first SUBTRACT (castle `World_7e9y81`) the seed must produce the SAME
tree native's current filter does (byte-exact 485/1156/26) — verify carefully; a bspBuild-seed that differs
for a Subtract would regress the castle. Even if it keeps the first Add, whether the WHOLE tree then matches
the editor's 6314 nodes / (0,0,1)@240 root is the real test (§29's richer tree may need more than the seed).
If the seed is not castle-safe or doesn't cascade, the residual is the deep incremental-tree re-implementation
(editor's per-region tree that native's filter-CSG doesn't reproduce) — a major multi-cycle port. Probes:
`_scratch/{parse_oracle,native_probe}.py`; failed-fix diff captured in this session's task output.

## 31. LANDED (`080dbf4a5`): seed the first brush per-op so a leading CSG_Add is retained — castle byte-identical, UNATCO counts cascade toward golden (necessary, not sufficient)

The §30 finding is fixed and committed. `bsp_filter_fpoly`'s empty-tree branch (first brush into the empty
world) now chooses the leaf filter PER-OP for the DX solid world (`root_outside == false`): **Add → F_OUTSIDE
(retained; was F_INSIDE → dropped), Subtract → F_INSIDE (byte-identical to before)**. `root_outside` is left
false (no §25 void-polarity flip); a `root_outside==true` world keeps the old op-independent `F_OUTSIDE`.

**Genuine correctness bug fixed:** native was silently dropping a level's ENTIRE leading CSG_Add — UNATCO's
first in-world brush (actor "Brush74") built to **0 nodes**. Now retained.

**Gates (all green):** castle `485/1156/26 / 43.04%` **byte-identical** to pre-fix HEAD (the fix never fires
for the castle's Subtract-first seed); `cargo test` 44; `bin/test` 1899 passed. Two cold reviewers resolved:
(1) the regression test was a FALSE GREEN — `Model::default()` sets `root_outside=true`, where the old buggy
code also passed; fixed to run at `root_outside=false` (the real build + bug condition); (2) the
`root_outside==true` sub-case is now guarded (per-op only for `false`); (3) the open faithfulness question
(exact editor mechanism for retaining a leading Add at RootOutside=0) is documented in-code — validated
empirically, not proven byte-faithful.

**UNATCO effect (mover-clean vs golden762 6314/76488/599/10752, byte-% 14.81→15.30, +0.49pp):**
nodes 6473→**6265** (gap 159→49), verts 95942→**89461**, vectors 745→**696** (gap 146→97), surfs 3609→3570
(**subtract rooms KEPT**, not the §25/§30 drop to 3432), points 10836→10434. Several count dimensions cascade
toward golden. BUT **Points positional-match regressed 0.27%→0.02%** and the repartition **root split stays
divergent** (native oblique/axis vs golden `(0,0,1)@240`). So the fix is **necessary but NOT sufficient**: it
corrects one real bug (the dropped leading Add) that gated the cascade, but the DOMINANT residual — the
Points/Verts pool-ORDER permutation driven by the wrong repartition root split (§18/§19) — is a function of
the WHOLE incremental soup, not just brush 0.

**Remaining byte-parity work = the deep incremental `bspBrushCSG`/`FilterWorldThroughBrush` re-implementation
so native's incremental tree matches UnrealEd's node-for-node** (the §29 richer per-region tree). All localized
levers are now exhausted and committed (§13–§31): stale/mover artifacts, clip tolerance, ordering,
FindBestSplit, make_ed_polys, bsp_merge_coplanars, calc_normal, RootOutside/polarity, is_csg nv-clause,
bsp_cleanup retention, and the leading-Add seed (this fix). The residual is the incremental tree STRUCTURE —
a major, castle-gated port, not a single-cycle fix. Next concrete sub-target: re-bisect the FIRST post-Brush74
incremental divergence now that the leading Add is retained (the soup/root-split should have moved) and decode
that clip/routing against the editor's incremental ADD stream.

## 32. Re-bisect on the seed-fixed build: §31 keeps only 1 of the 6 leading-Add faces; the faithful mechanism is `bspBuild`-seeding the first brush as a CONVEX tree (not filter, not void-flip)

On the §31 seed-fixed build, the first divergence is STILL N=1 — Brush74 (the leading CSG_Add). §31 retained
only **1 of the bar's 6 faces** (the z=416 top); the editor keeps all 6. Native soup vs editor golden
(order-independent): N=8 shared 34 / onlyN 2 / **onlyE 11** (Brush74's other 5 protruding faces + the
ceiling/x=448-wall fragments they would split); N=30 onlyE 25.

**Why §31 stops at 1 face (in-code):** face 0 seeds a 1-node tree via `leaf_func` with `NF_IS_NEW`, so
`is_csg_filter` (mask 0x21) is **false**. Faces 1–5 then descend that 1-node tree; `outside` never flips off
`root_outside=false` (front `outside||false`, back `outside && !false`) → they reach an **F_INSIDE** leaf →
the Add func (emits only on F_OUTSIDE) drops them.

**Two rejected ways to keep all 6:** (a) seed all 6 with `outside=true` (RootOutside=1 semantics) — TESTED,
castle held but the void polarity LEAKS into every following subtract → rooms drop, surfs 3570→3432, nodes/
verts/vectors = §30's rejected global-`root_outside=true` (6793/77124/572). Reverted. (b) A single RootOutside
value cannot keep BOTH the leading Add and the subtracts (§24–§30, re-confirmed).

**The faithful mechanism (editor oracle §26): `bspBuild` the first brush's 6 polys into a CONVEX seed tree.**
UnrealEd adds the leading Add's 6 faces as world-tree ROOT nodes 0–5 (`parent=0 place=3`=NODE_ROOT + a
`place=1` chain) — i.e. it constructs the brush's convex BSP as the seed, keeping `RootOutside=0` (solid
exterior). The bar box is solid-in-solid; its faces are retained as structural nodes and become visible as
later subtracts carve around them. This is NEITHER native's filter-one-then-filter-rest (keeps 1) NOR a
polarity flip (breaks subtracts) — it is a structural convex-seed build that keeps all 6 AND keeps the
exterior solid.

**Verdict: no tractable §31-style per-brush fix CHAIN; the residual is the deep incremental `bspBrushCSG`
re-implementation** — and its first concrete, editor-evidenced piece is **bspBuild-seeding the first brush as a
convex tree** (native has `bsp_build` for the world repartition; apply it to the first brush's polys in the
empty-tree path, `root_outside=0` unchanged). Gate: castle 485/1156/26/43.04% (castle's first brush is a
Subtract — its convex seed must reproduce the current byte-exact result) + UNATCO keeps all 6 Brush74 faces AND
the subtract rooms (surfs ≥3570, NOT 3432). If the convex-seed structure matches the editor's node chain, the
soup/root-split should move materially. This is the next step of the deep port; the §31 single-face seed
remains the committed castle-safe floor (`080dbf4a5`). Probe `_scratch/unatco_soup_probe.py`; seed at
`bspcsg.rs:709`, `bsp_build`/`bsp_add_node` for the convex seed.

## 33. LANDED (`218fd22fd`, 2-cold-reviewed): convex-seed the leading CSG_Add → repartition ROOT SPLIT now matches golden exactly; the dominant §18/§19 lever is CLOSED

The §32 faithful mechanism is implemented and committed. For the FIRST brush into an empty world, if it is a
CSG_Add, `bsp_brush_csg` now bspBuild-seeds all its polys as a **NODE_ROOT + NODE_FRONT chain, each
`Reverse()`d (inward-facing)** — node-for-node identical to UnrealEd's oracle block 0 (parents 0,0,1,2,3,4;
places 311111; ilinks 0–5; bases+normals exact). A leading Subtract / non-empty world keeps the per-poly
filter path (the §31 empty-tree per-op arm is now a dead-but-defensive fallback, comment reconciled).

**Impact (mover-clean UNATCO vs golden762 6314/76488/599/10752, surfs 3616):**
- **Repartition ROOT SPLIT: native `(-1,0,0)@-320` → `(0,0,1)@240` == golden.** This is the §18/§19 DOMINANT
  lever — the whole node/Points/Verts serialization ORDER cascades from the root split; it is now correct.
- Pre-repartition SOUP byte-perfect: N=8 **45/45**, N=30 **190/190** (was onlyE 11 / 25).
- Surfs 3570→**3614** (golden 3616, gap **2**). Nodes 6265→6275 (golden 6314). Points positional-match
  0.03%→**0.58%**.
- **Castle byte-identical** (485/1156/26/43.04%, body 245234 bit-for-bit — the seed fires only for a leading
  Add; the castle leads with a Subtract). `cargo test` 45, `bin/test` 1912. hkmarket/catacombs build clean.
- Two cold reviewers: sound, no correctness defect; their fixes applied (dead-arm comment, gate-negative +
  translated-box-inwardness + root-topology test assertions, convex-only contract documented).

**Honest scope:** byte-% is 15.64% (not a jump) — because the leading-Add drop is now fixed and the remaining
residual is cleanly ISOLATED and no longer entangled with it: the **§91 verts/vectors OVER-production**
(verts 93747 vs 76488 = +23%; vectors 745 vs 599 = +146, texture axes) + the Points/Verts pool **ORDER**
downstream of the (now-correct) root split. That is the NEXT target. This closes the leading-Add / root-split
class; the two committed real-level fixes this session are the leading-Add seed (§31, 1 face) → convex-seed
(§32/§33, all 6 + root split).

**NEXT:** re-characterize the verts/vectors over-production now that the root split matches — is it the §13–§17
texture-axis-on-extra-surfaces fragmentation (native still fragments some faces the editor merges), or a
Points/Verts pool ORDER permutation now that counts are close (surfs gap 2, nodes gap 39)? Bisect the first
verts/vectors over-production brush on the fixed build; decode + fix per the same decode→port→castle-gate loop.

## 34. LANDED (`1da1f3f0d`, 2-cold-reviewed): scaled-brush texture axes are COVECTORS — `(L⁻¹)ᵀ` pre-cancel closes the +146 UNATCO vector over-production EXACTLY

The §13–§17 "+146 vectors" residual is root-caused and fixed. Texture axes (TextureU/TextureV) are
**covectors**: the editor transforms them by the inverse-transpose `(L⁻¹)ᵀ` (mirrored in `transform.bake`'s
`NT`), but the native Rust core applied the SAME forward vertex map `L = PostScale·R·MainScale`
(`FPoly::transform`→`rot_only`) — so a non-identity scale SQUARES into the axis magnitude (UNATCO Brush420
PostScale.x=1.4167 → native texU.x = 1.4167² = 2.0069 vs the editor's 1.4167/1.4167 = 1.0). Those squared
axes never dedup in the Vectors pool → the +146 over-production.

**Bisect (overturns the §13–§17 "extra fragmentation" read):** dVec turns positive at **N=8** while surf
counts AND normals are IDENTICAL at every N (44/44, 500/500, vNormal 257==257). The excess is PURE texture
axes on geometrically-identical surfaces — the first two SCALED brushes (Brush420, Brush418). Attribution:
of native's 745 vectors, 565 exact-shared, 57 near-twins, 123 orphans — orphans 100% texture axes (texU
79 / texV 34 / both 10, zero normals).

**Fix (`materialize.py::_build_brush_input`, gated on `scaled`):** pre-multiply authored texture axes by
`tex_cov = (LᵀL)⁻¹ = L⁻¹(L⁻¹)ᵀ`, so Rust's later `L·(tex_cov·v) = (L⁻¹)ᵀ·v` — the editor's covariant axis.
Unscaled brushes (all castle brushes) keep `tex_cov=None` → identity path byte-for-byte. Reviewer fixes
applied: singular-L guard (`abs(det3(L))<1e-12` → `BuildError` naming the brush, no bare `ZeroDivisionError`)
and 4 regression tests (`tests/test_native_scale.py`: end-to-end `vTextureU==1/s`, the algebraic identity
`L·(LᵀL)⁻¹·v==(L⁻¹)ᵀ·v`, unscaled pass-through, singular-guard error).

**Result:** UNATCO **vectors 745→599 EXACT (dVec +0 at every N 1…762)**; geometry untouched (surfs 3614,
nodes 6275, verts 93747). **Castle byte-identical** (0 scaled brushes; Vectors array bit-identical; 485/1156/26).
`bin/test` 1916 passed; `cargo test` 45. Scope: closes the vector COUNT residual (round-tripped axes dedup
within `bsp_add_vector`'s 0.001 tol); `L·(LᵀL)⁻¹·v` is not bit-identical to a direct `(L⁻¹)ᵀ·v` (sub-tol FP
drift) — full axis-value byte-parity is separate.

**THREE real-level fixes landed this session:** leading-Add convex-seed (§32/§33, root split→golden) +
this texture-covector (§34, vectors→599). **Remaining residual = the byte-level Node/Vert/LeafHull partition
ORDER + the −2 surf delta** (surfs 3614 vs golden 3616; native slightly UNDER-produces 2 surfs now). verts
93747 vs golden762 76488 is partly a golden under-build artifact (bare `MAP REBUILD` under-builds Verts, §2)
— re-measure verts against a ZONES-basis golden before chasing. NEXT: the −2 surf delta (a decodable
merge/drop) and the Points/Verts serialization ORDER now that the root split + soup are correct.

## 35. Post-fix characterization: the −2 surfs are castle-load-bearing coplanar sheets (skip); the dominant residual is the EMIT ORDER, now localized to node 56 (root prefix matches)

With the root-split + covector fixes landed, the UNATCO residual (native 6275 nodes / 3614 surfs / 10603
points / 599 vectors vs golden762 6314/3616/10752/599) is two threads:

**(1) The −2 surfs — DECODED, but SKIP (castle-load-bearing).** Net class delta = exactly 1 portal + 1
notsolid (solid 29/29, semisolid 56/56 are bidirectional precision-twins that cancel). Both are single-poly
`CSG_Add` SHEET brushes coplanar with a pre-existing surf of DIFFERENT polyflags:
- portal **Brush344** (idx 105, plane (0,1,0)@1152, pf 0x4000109) — native has only the semisolid at that
  plane; golden has semisolid + portal.
- notsolid **Brush699** (idx 191, plane (-1,0,0)@1120, pf 0x88010c) — native has only solid; golden has solid
  + notsolid.
UnrealEd keeps a coincident non-solid/portal sheet as a DISTINCT `FBspSurf` (coplanar iPlane chain); native
merges/drops it. This is the §3/§82 §10.6 coplanar-merge family — forcing a coplanar KEEP is the merge-forcing
direction that regressed the castle twice. **Not worth risking the 485/1156/26/43.04% gate for 2 surfs.**

**(2) The EMIT ORDER — the dominant byte residual (~90% of it), now cleanly localized.** The root-split fix
(§33) moved the matching node-plane PREFIX from **0 → 56** (the root `(0,0,1)@240` coplanar chain now matches
node-for-node). Node-plane positional match 2.5%→**3.31%**; Points positional 0.58% (90.3% of native points are
byte-exact values in golden's pool, PERMUTED). **First plane divergence @ node 56:** native picks
`(1,0,0)@-432` (vertical wall), golden `(0,0,-1)@-416` (horizontal floor) — a downstream **FindBestSplit
subtree pick just past the root chain**. §20 proved FindBestSplit SCORING is byte-exact + GOOD-stride
(NumPolys/20), so this is a **soup ORDER/COUNT difference at node 56's subtree**: the poly subset routed to
that subtree (via `SplitPolyList` through nodes 0–55) is ordered/counted differently than the editor's, so the
sparse stride samples a different splitter. Node-plane multiset 5425 shared / 850 onlyN / 889 onlyE (86%
shared) — same geometry, permuted emit.

**Verdict: emit-order is the next target (gates Nodes 328 KB + Verts 381 KB + Points), but it is GATED on
full-scale soup byte-identity** — the node-56 subtree soup still differs because the full soup has residual
differences (the −2 coplanar sheets + the solid/semisolid precision-twins). So the emit order won't fully
converge until those soup residuals close, and they sit in the castle-load-bearing coplanar-merge + precision
families. **Next decode:** the node-56 `SplitPolyList` poly-ORDER convention (native vs editor) — is native's
front/back append order or coplanar-routing at a split different from UnrealEd's (a decodable ordering
convention, static from `Editor.dll` `bspBuild`/`SplitPolyList`), OR does node 56's subtree soup differ by a
poly (the coplanar-sheet/twin residual)? If ordering-convention → possibly castle-safe (nodes 0–55 already
match); if soup-content → gated on the hard coplanar residuals. THREE fixes landed this session (§33 root
split, §34 vectors, §11 dome cap); this is the remaining frontier.

## 36. Node-56 emit-order fork = SOUP-CONTENT (gated), not ordering; `SplitPolyList` convention is byte-exact. Emit-order needs the incremental-fragmentation gdb oracle.

Decoded the node-56 emit divergence (§35). **Native's `bspBuild`/`SplitPolyList` ordering is byte-identical to
UnrealEd's** (`Editor.dll 0x34530`, `bspbuild-splitpolylist-decode.md`): FrontList/BackList append in iteration
order; coplanar → `bspAddNode(NODE_Plane)` chained on iPlane; Split → front-frag→Front + back-frag→Back;
recurse **Front first** (0x34824) then Back (0x34841); FindBestSplit strict-`<`-min, first candidate wins.
Native `split_poly_list` (bspcsg.rs:1259-1301) matches every clause — the castle's byte-identity (485/1156/26)
already proves the convention. **NOT an ordering fix.**

**Empirical pin (in-process, HEAD):** node-plane prefix matches to exactly 56 (the root `(0,0,1)@240` chain);
node 56 = the root's FRONT child, front list = 1195 polys, GOOD stride = 1195/20 = 59. The editor's winning
plane `(0,0,-1)@-416` **IS in native's front list at idx 0 and IS scored** — F=10 B=9 S=0 → 12.0 — but LOSES to
idx 177 `(1,0,0)@-432` F=10 B=10 S=0 → **0.0** (perfect balance in the sparse strided sample). Since scoring is
byte-exact (§20), the editor's plane winning for the editor but losing for native ⇒ **native's front-list
CONTENT differs**. Hard content signals: node 52 nv=6 vs golden 8, node 53 nv=9 vs 10 (faces fragmented
differently); whole-tree plane multiset only-native 634 / only-golden 673 (bidirectional, 86% shared). This is
the incremental-`bspBrushCSG` ADD-stream + coplanar-merge FRAGMENTATION residual (§13/§35) — closeable only by
the gdb `bspAddNode` editor-tree-oracle repointed to UNATCO, NOT a static ordering fix.

**Current HEAD basis (recompute — supersedes stale §-figures):** native **6275 nodes / 3614 surfs / 599
vectors** vs golden762 6314 / 3616 / 599 (−39 / −2 / 0). Vectors now EXACT (§34). Node-plane positional match
3.31%, prefix 56; Points positional 0.58% (90% byte-exact values, permuted).

**Secondary castle-safe gap (flagged, not blind-fixed):** native's **repartition** `split_poly_list` Split arm
OMITS the editor's `if(frag NumVertices >= 14) SplitInHalf` (`Editor.dll 0x34716/0x3475f`). Native DOES
`SplitInHalf` in the CSG-filter paths (bspcsg.rs:578/1036, csg.rs:318) but not in the final `bspBuild`
repartition. Rare (≥14-vert repartition fragments; the castle never hits it, so it's castle-safe-passing) but
it changes fragmentation content downstream — a genuine faithfulness gap. A targeted fix (add the ≥14-vert
SplitInHalf to `split_poly_list`) is castle-safe by construction; worth trying as a small content-parity step,
though it likely won't move node 56 (whose faces are nv<14).

**Remaining frontier = the incremental fragmentation residual (§13/§35):** native fragments/merges some faces
differently than UnrealEd's incremental `bspBrushCSG`, so the full-scale soup content diverges (−2 coplanar
sheets §35 + the fragmentation), which permutes the emit order past node 56. This is the dominant remaining
byte residual (Nodes/Verts/Points order) and needs the gdb `bspAddNode` oracle at UNATCO to decode the exact
incremental ADD/clip that fragments differently. THREE fixes landed this session (§11/§33/§34); this is the
deep, editor-driving remainder.

## 37. First soup divergence (post-fixes) = Brush336 poly4 T-junction at N=75 — native nv=5 vs editor nv=4 (near-collinear vertex just over THRESH_COLINEAR)

With the §33/§34 fixes, native's pre-repartition soup is byte-perfect through **N=30** (45/45, 85/85, 190/190).
Under a FULL face key (plane + sorted vertex set, so nv/fragmentation counts), the first divergence is **N=75**
(finer than the surf-metric's N=105, which rounds away nv): onlyN 1 / onlyE 1, the same single face through
N=104; the dome (Brush755) adds 5 more at N=105.

**The diverging face (case c — different nv, same plane, count-neutral):** one face on plane **x=-768**.
- Editor: **nv=4** clean rectangle {z=408,416}×{y=320,576}.
- Native: **nv=5** — an extra vertex **(-767.9998, 319.9999, 413.9999)** on the y=320 edge.
It is Brush336's OWN poly (`i_actor=57, i_brush_poly=4`), first emitted at **N=58 = Brush336** (N=30→57 clean),
and it SURVIVES to native's final output (real, not a pipeline-stage artifact).

**Why native keeps it:** the trio (z=408 → 414 → 416) is *almost* collinear but sits at **1.34e-4 >
THRESH_COLINEAR (1.0e-4)**, because the 414 and 408 verts are float-perturbed (x=-767.9998) while the 416
corner is exact (-768.0) — the 414 point shares the 408 corner's x,y rather than lying on the 408→416 edge (a
PERPENDICULAR T-junction clip, not an on-edge split). So `remove_colinears` correctly declines; the editor's
x=-768 walls are uniformly nv=4 (oracle-105).

**Class: tractable incremental clip/fragmentation difference — NOT the §35 coplanar-sheet family** (that is surf
keep/drop; this is nv within ONE face) and NOT a golden-basis/OPTGEOM artifact (the SOUP is pre-repartition,
pre-OPTGEOM). Brush336 is the FIRST of the fragmentation divergences that make the full-scale plane multiset
634/673 (§35) and permute the emit order past node 56 (§36). A blind THRESH_COLINEAR bump risks the castle
gate — the fix must match the editor's actual clip of Brush336 poly4.

**FORK to resolve (statically first — N=58 ≤ 105, so it's in the committed `harness/editor-tree-oracle/logs/
oracle-105.log`):** does the editor (i) NEVER insert the (y=320, z=414) T-junction vertex — a CLIP-DECISION
difference (native's `filter_world_through_brush`/`split_with_plane` clips Brush336 poly4 where the editor
doesn't) — or (ii) insert then REMOVE it — a COLLINEAR/precision difference (the editor's verts are exact so
the trio IS collinear, or its threshold differs)? Check oracle-105 for the editor's Brush336 incremental face
on x=-768 (base ≈ (-768,576,408)): its nv + whether a z=414 vertex ever appears. (i) ⇒ decode the clip
routing; (ii) ⇒ the perturbation is native's earlier-CSG FP (the split-vertex precision residual) making an
otherwise-collinear vertex survive. Either way it is the next incremental-fragmentation decode. Probe:
`_scratch/unatco_soup_bisect.py`, `find_culprit.py`, `dump_face.py`.

## 38. Brush336 T-junction is a SYMPTOM of the incremental world-tree ORDER (same §36 lever), not a clip/precision bug — and the soup is nearly clean (6 onlyN, not 634)

Fork resolved (i) CLIP-DECISION, from `oracle-105.log` batch#57 (K=58=Brush336, i_actor=57):
- **The editor emits all 6 of Brush336's faces as clean nv=4 world nodes** (poly4 at B=-767.99976,575.99988,408
  **nv=4**, line 1785) — it NEVER fragments poly4, never inserts a z=414 vertex.
- Native emits **nv=5**: the same 4 corners + `(-767.99976, 319.99988, 413.99997)`.
- **The extra vertex is NOT a split-FP residual:** the editor golden's 4 poly4 corners are **byte-identical** to
  native's — including the asymmetric authored perturbation (the (320,416) corner exact -768.0, the other three
  -767.999756). Perturbation is authored/shared by both engines; native's SOLE divergence is the inserted vertex.
- **Born in `bsp_merge_coplanars`, not `split_with_plane`:** the descent trace shows every split fragment stays
  nv=4 (`f_nv=4 b_nv=4`); poly4 ends in ≥3 coplanar x=-768 leaves (nodes 902/904/905). Native's incremental world
  tree ROUTES poly4 through horizontal z-splitters and FRAGMENTS it, then merge re-fuses the bands; the y=320 seam
  vertex survives `remove_colinears` (1.36e-4 > THRESH_COLINEAR 1e-4) only via the asymmetric corner (the y=576
  seam IS collinear → removed). The editor's tree routes poly4 to a SINGLE x=-768 coplanar leaf → no fragment,
  no seam.

**PER-FACE, not systematic:** the pre-repartition SOUP at N=105 diverges by only **6 onlyN / 6 onlyE** — 1 is this
T-junction, the other **5 are the known Brush755 dome facets** (§9/§11, non-axis normals). No other T-junction
over-production in the measurable soup. **The §35 "634/673 only-native planes" is the DOWNSTREAM final-tree
emit-order PERMUTATION (§36), NOT soup content** — an important correction: the soup is nearly byte-perfect
(6 diffs), so the dominant byte residual is purely the repartition EMIT ORDER, plus this 1 incremental
fragmentation.

**No castle-safe fix; the ROOT is the incremental world-tree node ORDER** (the §36 lever): brushes 1–57 produce
an identical soup MULTISET but a PERMUTED incremental tree, which at N=58 routes Brush336 poly4 to horizontal
z-splitters where the editor routes it to one x=-768 coplanar leaf first. A THRESH_COLINEAR bump is wrong (the
vertex shouldn't exist) + castle-risky. **This unifies the Brush336 T-junction and the §36 node-56 emit-order
divergence into ONE lever: native's incremental `bsp_brush_csg` tree ORDER diverges from UnrealEd's past the
(now-correct §33) root.** Reconciles with §13's "ADD stream matches ≤105" only if the match was coarser than the
full internal node order — which the next decode must check.

**NEXT decode (the dominant remaining lever): reconstruct both incremental trees at N=58** — native
`UEDCLI_BSPCSG_TREE_STRUCT`/`TREE_DUMP` vs the editor `oracle-105.log` batch#57 ADD stream — node-by-node, and
find where native's walk inserts a horizontal z-splitter that fragments poly4 before reaching the x=-768
coplanar leaf, vs the editor's order. Decode the editor's `bspAddNode`/`bspBrushCSG` node-emit order past the
root and match it. This is the deep incremental-tree-order port (the §23–§29 residual past the root the
convex-seed §33 only fixed AT the root). THREE fixes landed this session (§33/§34 + faithfulness); this is the
remaining frontier.

## 39. §13/§38 RESOLVED: the incremental tree diverges at brush 7 = Brush480 FilterWorldThroughBrush — native's graze classifier rolls back 10 coplanar fragments the editor KEEPS (near-coincident graze-vs-cut, §82 §10.6). This ONE brush is the origin of the whole emit-order residual.

**§13 was coarse.** It aligned only the 81 clean `phase=ADD` (F_OUTSIDE Add) leaf-adds under a plane-key,
counting SUB/FWTB only — those 81 Adds are geometrically identical (ilink editor==native+6). The FULL persisted
world-tree ADD stream matches node-for-node **through brush 6**, then **diverges at brush 7 = `Brush480`**
(CSG_Subtract, loc (−272,1008,240)).

**Method caveat (for the resumer):** native's `trace_node_add` (bspcsg.rs:970) fires BEFORE
`filter_one_world_node`'s graze rollback (line 899), so the raw FWTB trace (5538 lines) is dominated by
rolled-back grazes and gives a SPURIOUS "first divergence at brush 2 pos 22". Filter to KEPT adds (FWTB
5538→180): net trees match at brush 2 (N=3 native 22 live == editor 22); the true first divergence is brush 7.

**What differs (geometry-gated, NOT order convention):** in the FilterWorldThroughBrush re-add substream for
Brush480, native keeps **0** FWTB re-adds; the editor keeps **10** coplanar (`place=2`) split-fragments of
existing world faces (planes x=128 @ B=**127.99998**, z=240, z=416). BOTH engines generate the SAME candidate
fragments — native's graze classifier (`g_discarded == 0`, bspcsg.rs:897) ROLLS THEM ALL BACK; the editor
commits the cut and keeps the outside pieces. Per-brush kept-FWTB: b6 native 3 == editor 3 ✓; **b7 native 0 vs
editor 10 ✗**. It is the near-coincident-plane GRAZE-vs-CUT family (§82 §10.6; the 127.99998 is a grid-snap
perturbation), the interior/`g_discarded` test — NOT front/back/coplanar emit order (that is byte-identical).

**Reconciles §37/§38:** the editor's 10 extra fragments are COPLANAR with the faces they cut, so
`bsp_merge_coplanars` re-fuses them into the same whole faces native keeps UN-split → the alive-face SOUP stays
byte-identical through N=30 (§37) and diverges only at Brush336/N=58 (§38, a downstream fragmentation of that
divergent tree), while the TREE STRUCTURE diverges at brush 7 and drives the §36 repartition emit-order
permutation. **So Brush480 (brush 7) is the SINGLE origin of the §36/§38 "incremental world-tree order diverges
past root" lever — the entire remaining byte residual.**

**No castle-safe fix (report-don't-force).** The `g_discarded==0` rollback is LOAD-BEARING for the castle's true
grazes; forcing keep regresses the castle (§82 §10.6 "regressed twice"). The fix requires native's interior/
`g_discarded` classification to match UnrealEd's EXACTLY at Brush480's near-coincident planes — keep the 10 cut
fragments there while still rolling back genuine castle grazes. **NEXT decode (the last lever): gdb
`bspAddNode`/FilterWorldThroughBrush oracle at Brush480 (brush 7)** — dump the editor's `SplitWithPlane` routing
+ interior test for the x=128@127.99998 / z=240 / z=416 fragments, and decode the exact `g_discarded`/interior
rule (why the editor commits the cut where native grazes it). Then match native's `filter_one_world_node`
(bspcsg.rs:897/899) interior test, castle-gated. This is the §82 §10.6 graze-vs-cut family, now pinned to ONE
brush + 10 specific fragments — the most precise the whole-effort residual has ever been localized. THREE fixes
landed this session (§33/§34 + faithfulness); this is the final frontier.

## 40. §39 REFUTED (raw-vs-kept measurement artifact): the committed incremental tree is BYTE-IDENTICAL through N=8 (incl. Brush480); `g_discarded` rule is bit-identical to UnrealEd. First real tree divergence is in brushes 9–57.

§39 pinned the first incremental divergence to brush 7 = Brush480's FWTB (native keeps 0 vs "editor keeps 10").
That is an **apples-to-oranges artifact**: §39 (and the af95ff73 stream-compare) matched the editor's
**pre-rollback RAW** re-adds (logged before reconcile) against native's **post-rollback KEPT** stream. Corrected:

- **Native's `g_discarded` rule is CORRECT.** For Brush480 (bi=7), native's 16 raw fragments all land on re-add
  codes (filter 0/2, F_OUTSIDE / F_COPLANAR_OUTSIDE), never a discard code (1/3/5) → per node `g_discarded==0` →
  rollback all → keep 0 (`bspcsg.rs:897`).
- **UnrealEd's rule is IDENTICAL** (disasm `FilterWorldThroughBrush 0x33250`): per straddling node `GDiscarded`
  reset (0x3343f), `bspFilterFPoly` leaf, discard-path `inc GDiscarded` (0x349ee), reconcile at **0x3348b**:
  `GDiscarded!=0` → commit (delete original), `==0` → rollback (`Nodes.Remove` 0x34050), PER NODE. The editor's
  brush-7 raw re-adds are also 10 all place=2 (coplanar_outside, re-add codes) → editor ALSO `g_discarded==0` →
  ALSO rolls back → ALSO keeps 0. NONE of (a) threshold / (b) side-class / (c) accumulation differs.
- **DECISIVE binary proof:** the committed incremental tree at **N=8 (through Brush480) is BYTE-IDENTICAL**
  native↔editor — **101 nodes, every `(plane,iF,iB,iP,nv,isurf)` matches** (isurf delta 0), LOOP-2 Add stream
  81/81 (`editor-struct-unatco-8.log`). Brush480 originates NO divergence; no fix needed or possible there.

**Measurement lesson (pin for resumers):** compare COMMITTED (post-rollback) trees, NOT raw ADD logs. Native's
`trace_node_add` fires PRE-rollback (bspcsg.rs:970 before the graze rollback at :899); the editor's oracle logs
raw NADD too. Any node-order/divergence claim MUST filter both to kept/committed nodes (or use the
`editor-struct-*` committed dump), else grazes create phantom divergences. This trap produced §39's wrong pin
AND the af95ff73 "brush 7" pin AND §26–§29's earlier confusions.

**The real residual (unchanged target, correctly re-localized):** the committed incremental tree matches through
N=8; the §36 repartition emit-order permutation (node 56) + §38 Brush336 N=58 nv=5 are driven by a committed
incremental-tree divergence that first appears in **brushes 9–57**. NEXT: bisect the COMMITTED incremental tree
over N∈(8,58] — native `UEDCLI_BSPCSG_TREE_STRUCT` (committed nodes only) vs the editor's committed tree
(reconstruct from `oracle-105.log` applying the rollback, or `editor_struct_unatco.py` per-N) — pin the FIRST
committed node that differs, then decode that brush's incremental clip/routing against the editor. Guard against
the raw-vs-kept trap throughout. THREE fixes landed this session (§33/§34 + faithfulness); this is the frontier.

## 41. THE ROOT (reframes §36–§40): the residual is PRECISION, not emit-order — first committed divergence is a 1-ULP GMath trig-table twin at N=22 (Brush639, first yaw-rotated brush)

Bisecting the COMMITTED incremental tree (native `UEDCLI_BSPCSG_TREE_STRUCT` NOREPART vs editor
`editor_struct_unatco.py` gdb dumps; method validated — N=8 = 101 nodes byte-identical, no raw-vs-kept
contamination):

**First committed divergence = N=22, `Brush639`** (22nd world brush, FIRST yaw-rotated: `Rotation=(Yaw=32768)`
= 180°, loc (408,352,32)). Both trees 326 nodes; **nodes 0–314 byte-identical**; first differing node = **315**
(Brush639's +y face, world plane `(0,-1,0)`): offset native **−312.0 (exact)** vs editor **−311.99997** =
`nextafter(−312,0)` = **exactly 1 float32 ULP**. iF/iB/iP/isurf/nv all identical — ONLY the plane `w` differs.

**All divergences (8,30] are the same class — 1-ULP TRANSFORM TWINS, ZERO topology/emit-order/nv divergence:**
N=15 identical (190 nodes); N=22 = 3 twins (Brush639 y=312/x=472); N=30 = 10 twins on the yaw-180 brushes
(Brush639/Brush368: exact-int vs 1-ULP) + the scaled brushes (Brush562/578: both non-integer, differ ~1e-4).

**Root cause = the GMath float32 trig-table floor.** Native transforms Brush639 with `gmath_cos(32768)` =
double `math.cos(π)`→f32 = **−1.0 exact** → verts on integer 312.0/472.0. The EDITOR reads its float32
`FGlobalMath::TrigFLOAT[]` table (`CosTab/SinTab[8192]`, ~1 ULP off native's double-reconstruction) → verts
1 ULP low. This is the documented "~1e-5uu table floor" (spike `2026-06-19-group-rotate-exact-parity`) and the
§17/§18 "precision-twin plane offsets" family — now pinned to the EARLIEST and SIMPLEST case (a rotated box,
N=22, vs the dome Brush755 at N=105).

**This reframes §36–§40:** the committed incremental tree is NOT permuted through N=30 — it is NODE-FOR-NODE
identical except for 1-ULP plane offsets. Those tiny offset twins are what §20 showed the sparse GOOD stride
amplifies: different plane `w` → different `FindBestSplit`/soup order at repartition → the §36 node-56 emit-order
permutation + §38 Brush336 nv=5. **So the ENTIRE remaining byte residual is downstream of transform PRECISION:
(1) the yaw/rotation GMath TrigFLOAT[] table (1 ULP), (2) a parallel scale-transform floor (~1e-4 on scaled
brushes).** Not graze-vs-cut (§39, refuted §40), not emit-order convention (§36, byte-exact scoring §20), not
coplanar-merge.

**Fix (concrete, castle-SAFE, high-leverage — the last lever):** drive native's `gmath_sin`/`gmath_cos` from the
editor's ACTUAL float32 `TrigFLOAT[8192]` bytes instead of double-reconstructing (native's double→f32 does NOT
reproduce the editor's `nextafter(−1,0)` — verified). Castle-safe by construction (castle has 0 rotated + 0
scaled brushes → no-op there; but therefore the castle can't validate it — gate on the UNATCO twins directly).
NEXT: (a) check spike `2026-06-19-group-rotate-exact-parity` for the table bytes/analysis; (b) gdb-dump the live
editor `FGlobalMath::TrigFLOAT[8192]` (cos idx 12288 for yaw-180) float32 bytes; (c) embed + use them in native's
gmath; (d) gate: Brush639 node-315 offset → −311.99997, N=22/N=30 twins vanish, committed-tree prefix extends,
and MEASURE the downstream cascade (emit-order / byte-%). A parallel scale-transform-floor fix closes the scaled
twins. THREE fixes landed this session (§33/§34 + faithfulness); this precision root is the tractable finale.

## 42. LANDED (`e44d13d17`, 2-cold-reviewed): native brush rotation now uses UnrealEd's float32 GMath `TrigFLOAT[]` table — closes the ROTATION precision-twin class exactly

The §41 precision root is fixed for rotation. Native's `gmath_sin/cos` (`rotation.py`) now reproduce UnrealEd's
`FGlobalMath::TrigFLOAT[8192]` bit-exactly: `_TRIG[k] = f32(sin(f32(k·2π/16384)))` (the angle is cast to f32
BEFORE `sin` — the load-bearing subtlety; matters for 8973/16384 entries), `gmath_sin(uu)=_TRIG[(uu>>2)&16383]`,
`gmath_cos(uu)=_TRIG[((uu>>2)+4096)&16383]` (verbatim UE1 `CosTab(i)=TrigFLOAT[((i>>2)+N/4)&mask]`). So
`sin(180°)=−8.742278e-08` (not double's ~0) — the float32-table fingerprint. Previously native double-reconstructed
(`math.sin(π)`), 1 ULP off, causing the §17/§18 precision-twin plane offsets.

**Impact (UNATCO committed incremental tree, mover-clean):** Brush639 node-315 offset −312.0 → **−311.99997** ==
editor; **N=22 committed tree now IDENTICAL** (twins 3→0, whole 326 nodes); N=30 twins 10→4; committed
first-divergence node 315 → **359**. Byte-parity vs golden762: whole **18.79% → 19.11%**, Nodes 19.2→20.3%,
**Vectors 66.4 → 71.1%**. **Castle byte-identical** (485/1156/26/43.04%; `gmath` fires 0× — 0 rotated/scaled
brushes). `bin/test` 1938 passed / 0 failed; `cargo test` 46.

**Scope (honest, per review):** the trig SOURCE is bit-identical to the editor; SINGLE-AXIS rotations are
bit-exact (Brush639). Multi-axis composes `matmul` in Python DOUBLE (not UE f32 `FCoords`), so it is
ULP-approximate IN GENERAL — but every multi-axis rotated brush in DX content is CARDINAL (0/90/180/270°, e.g.
UNATCO Brush253 Yaw=32768,Roll=49152), and all 63 cardinal combos were verified to compose bit-identically
(double-matmul→f32 == pure-f32, 0 delta). The ULP gap bites only a genuine NON-CARDINAL multi-axis FRotator,
which NO DX level exercises (documented known gap; regression pins the cardinal literals + the UE1-formula
decode, not a non-cardinal level datum).

**⚑ FLAG FOR ANDRZEJ (preview re-bless):** the fix re-blessed `test_preview_native`'s 90°-yaw golden. The now
game-faithful `cos(90°)=−8.742278e-08` (vs double 0.0) flips a knife-edge, exactly-90° edge-on face's
front/back-facing in the `--native` PREVIEW. Both reviewers deem the re-bless defensible (the GAME builds
geometry from the same −8.74e-8, so it is what the player sees), and the 0° frame stays byte-identical. But it
IS a visible preview change on a degenerate case — if you prefer the preview NOT reproduce the game's
table-floor edge-flip (a "cleaner" preview), revert the golden. Byte-parity itself is unaffected either way.

**NEXT = the SCALE-transform floor (the remaining precision class).** The 4 remaining N=30 committed-tree twins
are SCALED brushes (Brush420/418/562/578, ~1e-4 — larger than the 1-ULP rotation twins). Their transform never
touches GMath: it is a SEPARATE `MainScale`/`PostScale` FP path (`rotation.py::actor_linear`→`fscale_matrix`,
Python-double vs the editor's f32 scale arithmetic). Fix it the same way (match the editor's f32 scale ops), then
the committed incremental tree should be twin-free through N≥58, at which point §36's node-56 emit-order divergence
can finally be judged — is it now converged, or a genuine FindBestSplit fork on some still-divergent input?
FOUR real byte-parity fixes landed this session (§11/§33/§34/§42) + NormalizeSlow + SplitInHalf faithfulness.

## 43. The scaled-brush twin is a COUPLED normal+vertex FCoords effect, not a surgical scale-multiply — needs a faithful `ABrush::BuildCoords` port (RVA 0x111390)

§42's "match the f32 scale multiply" hypothesis is too shallow. Tracing the 4 N=30 committed-tree twins to
Brush578 (nodes 359-362, pure PostScale (1.0625,0.625,1), L=diag(s)) and Brush562 (scale 1.625), the twin is a
COUPLED pair of 1-ULP effects that CANCEL on some faces and not others:

- **(i) node-plane NORMAL.** Native drops the authored normal for scaled brushes and recomputes `calc_normal`
  over the WORLD winding. A brush-LOCAL-symmetric face (x=±128) becomes ASYMMETRIC after non-uniform PostScale
  (x∈{16,288}) → `calc_normal` = **0.99999994** (1 ULP under unit); then `w = base·normal` on a far face
  (base.y≈1952) loses ~1.3e-4 → the twin. The editor `CalcNormal`s in the brush LOCAL frame (§14-§17), then
  covariant-transforms via `VectorXform` + `SafeNormals` → exact unit normal.
- **(ii) VERTEX transform cross-terms.** Brush562's editor verts are `nextafter(320,0)=319.99997`,
  `nextafter(−96,0)=−95.99999` (1 ULP toward zero). The x=−96 face is at local x=PrePivot.x so the scale
  multiplies ZERO — yet it is STILL shifted → NOT scale-factor rounding; it is tiny (~1e-7) OFF-DIAGONAL
  cross-terms in the editor's `FModelCoords.PointXform`.

**The editor's exact transform = `ABrush::BuildCoords` (Engine.dll RVA 0x111390):** builds `PointXform`/
`VectorXform` as a CHAIN of `FCoords` operator `*`/`/` over `GMath.UnitCoords`, `MainScale`, `Rotation`,
`PostScale` (the `FScale` worker DIVIDES, §3 scale spike). That chain injects the cross-terms native's clean
`diag(s)·v` omits — and produces the exact normal via `VectorXform`+`SafeNormal`.

**Naive fix reverted.** Implementing (i) faithfully (local `CalcNormal`→`VectorXform`→`SafeNormal`) fixed
Brush578 (359-362→0) but BROKE Brush562 (349-356: +8 twins) — native's non-unit normal had been COINCIDENTALLY
CANCELLING effect (ii) on integer-coord faces. Net 4→8. Reverted; tree at clean HEAD (4 twins, first divergence
node 359). Castle-safe (gated on `scaled`, 0 castle scaled brushes → no-op).

**§36 node-56 still UN-JUDGEABLE** — gated behind a twin-free committed tree through N≥58; twins unresolved, so a
precision cascade vs a genuine FindBestSplit fork cannot yet be distinguished. This is the pivotal open question
(§41): whether the ENTIRE residual is downstream of transform precision.

**Scope reframe + NEXT:** the scale twins need a faithful port of the `FModelCoords` construction — BOTH
`PointXform` (verts) AND `VectorXform`+`SafeNormal` (normals), which are COUPLED (fixing one alone regresses).
Decisive next datum: a FULL-PRECISION editor node dump (normal BITS + w BITS) for Brush562/578 (the existing 5dp
dump can't confirm the normal-vs-vertex split), then port `ABrush::BuildCoords 0x111390`'s FCoords chain +
`PointXform`/`VectorXform`/`SafeNormal` into native's `rotation.py::actor_linear`/`fpoly.rs::transform` +
scaled-normal handling, matching the editor's f32 op-order. Gate: 4 twins→0 (Brush578 AND Brush562), castle
byte-identical, committed tree twin-free through N≥58 → THEN judge node-56. FOUR real fixes landed this session
(§11/§33/§34/§42); the scale-FCoords port is the last precision lever before the node-56 verdict.

## 44. DECODED + LANDED (uncommitted, for review): the DIAGONAL scaled twin is the FACE NORMAL — `calc_normal(world)` vs the editor's covariant `SafeNormalSlow((L⁻¹)ᵀ·N_local)`. Brush578 N=30 twins→0, bit-exact. Rot+scale is a SEPARATE VERTEX-PointXform residual; node-56 UNCHANGED.

**Decode (Engine.dll `ABrush::BuildCoords` 0x111390 + core.dll FCoords ops, all disassembled).** `BuildCoords`
fills a `FModelCoords{PointXform, VectorXform}`: `PointXform = ((UnitCoords * PostScale) * Rotation) * MainScale`
and `VectorXform = Transpose(UnitCoords / MainScale / Rotation / PostScale)`. `FPoly::Transform` (0x152360)
then maps **verts** `V' = (V−PrePivot).TransformVectorBy(PointXform) + Location`, and the **face normal**
`N' = SafeNormalSlow(N_local.TransformVectorBy(VectorXform))` (covariant; texture axes too — confirms §34).
`FCoords::operator*(FScale)` MULTIPLIES each axis per-column by Scale (0x18180); `operator/(FScale)` DIVIDES
per-axis via `divss` (0x18bb0); `TransformVectorBy` (0x2dd50) = `(V·XAxis, V·YAxis, V·ZAxis)`; `SafeNormalSlow`
(0x27180) = `inv = 1.f/(f32)sqrt((f64)SquareSum)` (the SAME f64-widened normalize as `CalcNormal`).

**The mechanism (validated against a gdb `Model->Nodes` bit-dump of golden30/golden105).** For a diagonal
`L=diag(PS)` brush, `VectorXform = diag(1/PS)`. Native dropped the normal and ran `calc_normal` over the
L-warped WORLD winding → `0x3f7fffff` (0.99999994, 1 ULP under unit) on a face made asymmetric by non-uniform
scale (Brush578 ±x/±y, N=30 nodes 359-364). The editor covariant-maps the brush-LOCAL axis normal + renormalizes
→ EXACT `0x3f800000`. §43's "(ii) vertex cross-terms" is **refuted** for these — the verts are bit-identical;
the WHOLE twin is the normal. §43's "naive fix regressed Brush562" was `ROT.inverse`'s adjugate/det giving a
1-ULP-off `1/1.625` that `SafeNormalSlow` renormalizes back to `0.99999994`; the fix uses a **clean per-axis
f32 reciprocal** `diag(1/PS)·R·diag(1/MS)` (the editor's `divss`).

**Port (uncommitted).** `bspcsg.rs::bsp_brush_csg` LOOP-1: for a scaled brush (new `BrushInput.vec_xform =
(L⁻¹)ᵀ`, threaded through the PyO3 tuple's last nested triple), recompute the face normal as
`safe_normal_slow(transform_vector_by(local_winding_normal, vec_xform))` instead of `calc_normal(world)`
(`fpoly.rs` gains `safe_normal_slow`/`transform_vector_by`). `native/materialize.py` builds `(L⁻¹)ᵀ` from clean
f32 reciprocals. Unscaled + mirror-scaled keep the exact old path (castle no-op; no DX mirror-scaled brush exists).

**Results.** Castle byte-identical (485/1156/26; the fix is a provable no-op — 0 scaled brushes; `vec_xform=None`).
UNATCO committed incremental tree (native NOREPART vs editor gdb dump): **N=30 TWIN-FREE** (417/417 node-for-node
identical, was 6 twins). `cargo test` 48 (+2 engine-fact regressions pinning the covariant normal == editor bits
& `SafeNormalSlow`), `bin/test` 1938. **N=105: 94 twins remain (down from a 115+ baseline) — ALL from the 25
ROTATED+scaled brushes** (first Brush173, idx48). Of those, 6 have BIT-IDENTICAL normals but a 1-ULP `w` → the
VERTS twin: native's `rot = actor_linear` (double `matmul`) ≠ the editor's f32 `PointXform` op-order under
scale+rotation. So the covariant-normal port is COMPLETE for the diagonal class (the §43 target) and closes the
NORMAL for rot+scale too; the remaining lever is a faithful f32 **PointXform** for rot+scale VERTS (and the
matching f32 rotation-compose op-order for the VectorXform of slanted faces) — a bounded FCoords-chain port.

**§36 NODE-56 VERDICT — UNRESOLVED and NOT YET CLASSIFIABLE.** `node_subset_diff diff 762`: first emit-order
divergence is **STILL index 56** (native `(1,0,0)@-432` vs editor `(0,0,-1)@-416`), unchanged by this fix; node-plane
set shared 5640 / only-native 635 / only-editor 674. The verdict (precision-cascade vs genuine `FindBestSplit`
fork) **cannot be rendered yet**: the level's VERTS are still built at native precision (double `matmul` forward-`L`,
not the editor's f32 `PointXform`), so the remaining rot+scale VERTS-twin class (94 at N=105, §44 above) still perturbs
the repartition input. A precision fork therefore **cannot be excluded** until that vertex-PointXform twin also lands.
What this fix DID establish: the DIAGONAL-scale NORMAL twin is NOT the driver of node-56 (closing it left node-56
untouched, and it changed only ~361 sub-key bytes at N=762 — the deduped Vectors pool absorbs most of it: native's
exact-vector match to golden762 rose 358→361/599). The next required datum is the rot+scale vertex-PointXform port;
only then can node-56 be classified. Brush336 (N=58 nv=5, §37) is downstream of the same rot+scale/fragmentation
residual, not the diagonal class this fix closes.

**Scope/effectiveness note (measured, honest):** this fix's byte-parity effect is SMALL by construction — the final
`.dx` node plane is rebuilt at repartition from the deduped **Vectors** pool, and a scaled AXIS-face normal dedups
against the exact axis vectors that unscaled brushes already seed (so at N=30 the final output is byte-IDENTICAL with
or without the fix; the twin lives only in the pre-repartition committed tree). It becomes byte-visible only where a
scaled normal does NOT dedup (N=105: 19 bytes; N=762: 361 bytes, +3 exact Vectors vs golden). The fix's real value is
**faithfulness of the incremental tree** (N=30 now bit-matches the editor's `bspAddNode` stream) + the correct
covariant mechanism now in place for when the vertex-PointXform port lands; it is not, on its own, a large byte-parity
mover.

## 45. LANDED (uncommitted, for review): rot+scale VERTEX precision closed — editor f32 `FCoords` PointXform + authored-Origin base. The §44 "94 twins ALL rot+scale" is REFUTED (only 8 are scaled; 86 are UNSCALED dome/wedge NORMAL twins). NODE-56 VERDICT = PRECISION CASCADE, not a structural FindBestSplit fork.

**Full-precision editor datum (the bit-exact target).** Extended `editor_struct_unatco.py` to dump the
editor's incremental world-tree `Model->Nodes` plane BITS (hex) at `bspBuildFPolys` entry for UNATCO
**N=105** (MAP LOAD `golden105.dx`; guarded/bounded; `_scratch/ptx/editor_struct_105.py` →
`editor-struct-unatco-105.log`, 1637 ND lines).  Native's committed NOREPART tree
(`UEDCLI_BSPCSG_NOREPART=1 UEDCLI_BSPCSG_TREE_STRUCT=1`) also has **1637** nodes.

**LINCHPIN (the whole verdict rests on this): the N=105 committed incremental tree is STRUCTURALLY
IDENTICAL native↔editor.** All 1637 nodes match INDEX-FOR-INDEX on `(iFront, iBack, iPlane, iSurf, nv)`
— **zero** structural mismatches, **zero** only-native/only-editor nodes.  The ONLY differences are
**94 precision-twin PLANES** (normal/`w` bits).

**§44's "94 twins ALL from the 25 rot+scale brushes" is REFUTED.**  Mapping each twin node → `iSurf` →
`iActor` → brush, the 94 decompose as:
- **8 rot+scale VERTEX twins** (`w`-only, normal bit-identical): Brush359/750/48/236 — the actual
  scaled class.
- **86 UNSCALED slanted-face NORMAL twins**: the **dome Brush755 (72)** + wedge/T-junction
  Brush745/678/768/336/382/691 (14).  These are `rot=identity, PostScale=identity` faces whose
  `calc_normal` over the incrementally-clipped world winding differs ~1–30 ULP from the editor's — the
  §14–§17 CalcNormal residual (a SEPARATE, "do-not-re-chase" precision family), NOT the rot+scale lever.

**Decode (`ABrush::BuildCoords` 0x111390 + FCoords ops, per §44; mechanism refined by the §45 review).**
`PointXform = ((UnitCoords·PostScale)·Rotation)·MainScale`; a vertex is
`V' = (V−PrePivot).TransformVectorBy(PointXform) + Location`.  Effective element
`M[i][k] = f32( f32(PostScale_i · R[i][k]) · MainScale_k )` — PostScale scales row `i`, `R` is the GMath
matrix (`M_Rotation=Rᵀ` so the compose = `diag(PS)·R`), MainScale scales column `k`.  Two things the
double matmul gets wrong: **(a) the DOMINANT lever for DX — the editor stores `FVector Scale` as float32,
so it multiplies by `f32(PostScale)` where `rotation.actor_linear`'s `fscale_matrix` multiplies by the
raw double**; on the cardinal cross-term `R[0][1]=-sin(180°)=8.742278e-08`, `f32(f32(0.249997)·8.74e-8)`
= `0x32bbbc9b` vs the double's `0x32bbbc9a` (1 ULP, amplified by a ~2000uu vertex into the node-`w`
twin); **(b) the intermediate f32 round after `PostScale·Rotation` before `·MainScale`** — a genuine
second rounding that bites ONLY when PS and MS both cross the same off-axis.  **EVERY DX rot+scale brush
has MainScale=identity, so (a) is the whole effect** and (b) is unexercised (reproduced for generality;
pinned by a synthetic PS×MS test).  In-range at N=105 NO brush hits even (a) (the cross-term brushes
Brush541/348 are idx 464/473); the
8 N=105 `w`-twins were instead the **base point**: native DROPPED the scaled brush's authored Origin
(`base := verts[0]`), but the editor stores the TRANSFORMED authored Origin as `pBase`, and a scaled
face's covariant normal has tiny non-axis components → `w = Normal·Base` differs 1 ULP between the two
base points.

**Fix (uncommitted, materialize.py — Python-side only, Rust unchanged; scaled-brush-GATED so castle is a
provable no-op):** (i) build the scaled brush's vertex transform `R` via `_pointxform_f32` (the editor's
f32 two-stage op-order) instead of the double `L`; (ii) KEEP the authored per-poly Origin for scaled
brushes (`if scaled or not have_all_origins` → `if not have_all_origins`) so `FPoly::transform` maps it
to the editor's `pBase`.  `L` (double) stays for the tolerance-level det/inverse/mirror/covariant math.
The §45 review also HOISTED the SheerRate-reject guard out of the `if not mirror` block (both the vertex
`_pointxform_f32` and the covariant normal map are diagonal-scale only, so a mirror-scaled sheared brush
must reject too — unexercised by DX but no longer a silent mis-build), and pinned the `_pointxform_f32`
WIRING into `tup[6]` (reverting it must trip a test).

**Results (N=105 committed tree, native NOREPART vs editor bit-dump).**
- **8 rot+scale VERTEX/`w` twins → 0** (Brush48/236/359/750 now bit-identical).  94 → **86** (all 86 are
  the unscaled dome/wedge NORMAL twins, unchanged — out of scope).
- Committed tree **twin-free through N=42**; first remaining twin = **Brush745 (idx 42, UNSCALED slanted
  face)**, NOT a rot+scale brush.  **Brush336 (idx 57, N=58) does NOT resolve** — it is an unscaled
  T-junction/normal twin (§37/§38 family), not the scaled class.
- **N=762 FINAL output (`node_subset_diff diff 762`):** **Points 10603 → 10762** (editor 10752; the
  authored-Origin base points ARE the editor's orphan `pBase` points — |Δ| 149 → **+10 overshoot**, a
  large net Points-POOL gain but NOT yet identical: native now emits ~10 base points the editor's pool
  does not, a POOL-content gap, not a node-structure gap).  Surfs 3614, Vectors 599 unchanged.  The
  L-composition fix targets Brush541/348 at N=762 (validated by the pinned editor bit `0x32bbbc9b`; not
  separately editor-dumped).
- **Castle byte-identical** (0 scaled brushes; both changes strictly `scaled`-gated; build 1156 nodes /
  485 surfs, unchanged).  `bin/test` 1941 passed / 0 failed; `cargo test` 49; +2 regressions
  (`test_native_scale.py`: editor-bit-pinned PointXform op-order, scaled-brush authored-base).

**§36 NODE-56 VERDICT — PRECISION CASCADE, not a genuine structural FindBestSplit fork (HIGH confidence).**
`node_subset_diff diff 762` first emit-order divergence is STILL index 56 (native `(1,0,0)@-432` vs editor
`(0,0,-1)@-416`) — the vertex fix does not move it, because node-56 is driven by the **86 unscaled
dome/wedge NORMAL twins** perturbing the repartition soup, not the (now-closed) vertex class.  But the
divergence is **precision**, not structure: the N=105 **incremental committed tree is byte-structurally
IDENTICAL** (1637/1637 nodes, index-for-index `iF/iB/iP/iSurf/nv`, zero only-* nodes), so native's
`bsp_brush_csg` builds the editor's EXACT tree topology — there is no structural fork in HOW native
partitions.  The final-tree node-56 pick differs only because repartition (`bsp_build`, byte-exact
`FindBestSplit` scoring §20) consumes a soup carrying the twinned plane VALUES; the "only-editor slanted
planes ×8–11" (`(0,0.857,0.514)@-312.81` etc.) are downstream repartition FRAGMENTS spawned by the
perturbed split order (the dominant only-editor planes are in fact AXIS-aligned fragmentation-count
differences, not slanted forks).  **So the entire remaining residual IS transform/normal PRECISION →
byte-parity is in reach.**

**Remaining precision levers (the whole residual is now these two — both PRECISION, not structure):**
1. **The UNSCALED slanted-face `calc_normal` twin** — dome Brush755 (×72) + wedge/T-junction brushes
   (×14) = the 86 N=105 normal twins; the §14–§17 family.  DOMINANT (perturbs the repartition soup at
   node-56).
2. **The covariant-normal `vec_xform` is STILL built in Python DOUBLE** (`_build_brush_input`'s
   `ROT.matmul(_recip_diag(PS), ROT.matmul(R_only, _recip_diag(MS)))`, `float(x)`), NOT the editor's f32
   `VectorXform = Transpose(UnitCoords / MainScale / Rotation / PostScale)`.  `SafeNormalSlow`
   renormalizes it so AXIS faces stay exact (why N=30 is twin-free) and it did not surface as an
   incremental-tree twin — but its ~1e-7 direction drift on scaled NON-AXIS faces is the likely source
   of the **+10 Points-POOL overshoot** (10762 vs 10752): a slightly-off covariant normal base-snaps the
   authored Origin to a slightly-different `pBase`, emitting a pool point the editor's does not.  Porting
   `vec_xform` to the f32 `FCoords` op-order (as `_pointxform_f32` now does for the vertex `PointXform`)
   is the next precision step — NOT done this cycle.

Neither is a structural `FindBestSplit` divergence.  Harness (committable, under
`harness/editor-tree-oracle/`): `editor_struct_unatco_bits.py` (editor gdb bit-dump),
`native_noropart_struct.py` (native NOREPART dump), `twin_compare.py`, `struct_compare.py`.

## 46. ROOT-CAUSED (overturns §16/§17): the 86 unscaled normal twins = the editor's `CalcNormal` runs over the brush-model's own LOCAL winding, NOT the world winding. Naive raw-local recompute closes 86→32 but REGRESSES the castle (+14013 B) — the true fix is the brush-model `bspBuildFPolys` reconstruction/weld.

**The exact 1-ULP source, pinned bit-for-bit (offline, no editor).**  For the wedge **Brush745**
(node 702, unscaled, identity rotation, `PrePivot=(88.000168,-95.999924,72)`,
`Location=(368,-1040,80)`) and the dome **Brush755** (nodes 1500/1522/1556/1578), native STORES the
**authored T3D `Normal=`**; the editor STORES **`CalcNormal` over the brush-LOCAL (pre-transform)
winding**, bit-exact:
- Brush745 node 702 editor outward normal `0xbe372dbe,0x3f7bdee6,0` == `calc_normal(LOCAL winding)`
  EXACTLY.  Native's authored `0xbe372da1,0x3f7bdee8,0`; `SafeNormalSlow(authored)` == authored (a
  no-op — so the task's "SafeNormalSlow(N_authored)" hypothesis is **REFUTED**); `calc_normal(WORLD
  winding)` = `0xbe372dc0` (2 ULP off, also wrong).
- Brush755 dome facets ib=3/20/44/61 → editor nodes 1500/1522/1556/1578, all three components match
  `calc_normal(LOCAL winding)` bit-exact (`0x…079e/07a4/07a5/0797`); `calc_normal(WORLD)` gives the
  native-family `0x…077d/0791` set.  **This is exactly §16's observation that the editor's four stored
  dome normals (`0797/079e/07a4/07a5`) are "a WHOLLY DIFFERENT SET" from native's (`078c/0791/07d6/
  07fe`)** — §16/§17 only ever ran `CalcNormal` over the WORLD winding (large ~1000uu coords, which
  round differently) and wrongly concluded "unreachable / world-vertex-pool"; the LOCAL winding
  (small coords) matches to the bit.  Probe: `_scratch/normprobe/{probe745,probe_all755}.py`.

**Why the editor does this.**  `FPoly::Finalize` on the brush's OWN `Brush->Polys` (the §14 `Init`-zero
→ refill-verts → `Finalize`→`CalcNormal` reconstruction at `Editor.dll 0x10015e83`, run at brush-model
build BEFORE `bspBrushCSG`) recomputes each normal via `CalcNormal` **in brush-LOCAL space**, then
`FPoly::Transform` ROTATES it to world (a no-op for these identity-rotation brushes).  So the stored
node normal is `R·CalcNormal(local winding)`, not the authored `Normal=` and not `CalcNormal(world)`.

**The AXIS exception (why "always calc_normal(local)" fails).**  `CalcNormal` of a large NON-SQUARE
axis rectangle double-rounds to `0.99999994` (the doubled area `2·w·h > 2^24`, its f32 `1/sqrt`
reciprocal-multiply is 1 ULP under unit — e.g. Brush777's 656×256 floor, node 12), yet the editor
stores the EXACT `±1`.  So the editor's brush-model reconstruction yields exact axis normals where a
raw-winding `CalcNormal` would not.  Gating the recompute on `!is_unit_axis(authored)` (two components
exactly `0.0`, one `±1.0`) restores the axis faces.

**Measured result of the naive raw-local recompute (`bspcsg.rs` LOOP-1, unscaled, non-axis → seed
`calc_normal(p.verts)` before transform).**
- UNATCO N=105 committed NOREPART tree: **86 → 32 twins**, and the remaining 32 shrink from ~33 ULP to
  **1-2 ULP** (they are the §14/§15 brush-model VERTEX-WELD residual: the editor's `bspAddPoint` pool
  collapses shared dome verts to a common coord, so `CalcNormal` over the WELDED winding differs 1-2
  ULP from `CalcNormal` over the raw T3D winding for facets that share a welded vertex; facets with no
  shared-vert weld — ib=3/20/44/61 — match exactly).
- **CASTLE REGRESSES: native body +14013 B vs the HEAD baseline (259247 vs 245234), first diff in
  Vectors, cascading through Nodes/Verts.**  NOT castle-safe.  Cause: of the castle's 80 non-axis
  unscaled faces, **48 differ from `calc_normal(raw local)` by only 3-5 ULP** — the editor keeps these
  as authored (native is byte-identical to golden by keeping them authored), because the editor's
  brush-model reconstruction/weld reproduces the AUTHORED normal for them (§14's "surf556's welded
  winding happens to reproduce the authored normal exactly").  The raw-local recompute changes those
  3-5 ULP and flips graze-vs-cut at coincident subtract planes → the +14013 cascade.  (Probe:
  `_scratch/normprobe/castle_faces.py`; before/after native castle diff via `ground_truth_bytediff.py`.)

**Verdict.**  The mechanism is now DECODED (editor = `CalcNormal` over the brush-model reconstructed/
welded LOCAL winding, rotated).  A raw-local recompute is a **cheap proxy that closes 86→32 but is NOT
castle-safe** — the castle's slanted faces need the reconstructed/welded winding (where `CalcNormal`
== authored), not the raw T3D winding.  A ULP threshold to separate them is a guess §14 already
warned against and is fragile across levels.  **The correct, castle-safe fix is to port the
brush-model `bspBuildFPolys` reconstruction + `bspAddPoint` weld** (§14/§15's larger port): build each
brush's own BSP with native's editor-faithful `bsp_build`, reconstruct each poly from its node winding
(`bspNodeToFPoly`), and `CalcNormal`+base-snap over THAT — which yields exact `±1` for axis, authored
for the castle's welded slanted faces, and `07a5/0xbe372dbe` for the dome/wedge, all from ONE faithful
rule (no threshold).  Reverted to HEAD (`a97205a01`) this cycle; probes preserved in
`_scratch/normprobe/` + `native_local_normal_probe.py` under `harness/editor-tree-oracle/`.  The
`is_unit_axis` guard and the local-winding-`CalcNormal` match are the two reusable pieces for that port.

## 47. De-risk of the normal-weld port: FAILS the castle → the final residual is the editor's per-face normal DECISION (keep-authored vs recompute), not a CalcNormal rule (§46 hypothesis refuted)

Ran native's REAL `build_brush_temp_bsp` + `bsp_node_to_fpoly` reconstruction on the actual castle BastionDNE
brush + UNATCO dome Brush755, plus an exhaustive offline `CalcNormal` scan (`derisk-normal-weld/` harness).

- **(a) castle slanted (45°) face — reconstruction does NOT reproduce authored.** BastionDNE min inter-vertex
  distance 65 uu ≫ weld tol 0.002 → the `bspAddPoint` weld is a VALUE-no-op (can only reorder a winding).
  `CalcNormal(welded local)` = `0x3f3504f3`; authored = `0x3f3504f7` (√2/2), 4 ULP low. Brute-forced every
  cyclic rotation/reversal — NONE reach authored. Storing the recompute flips all 48 castle slanted faces
  f7→f3 = the §46 +14013 B regression. (Bonus: large axis SIDE faces reconstruct to `0x3f7fffff`, not exact 1.0
  → `is_unit_axis(authored)` guard required regardless.)
- **(b) dome facet — reconstruction DOES reproduce the editor bits** (`079e/07a4/07a5/0797` for ib3/20/44/61,
  bit-exact vs §46), differs from native's kept-authored `077d` (the twin). A store-the-recompute WOULD close
  the 86 dome/wedge twins — but breaks the castle (a).

**The precise obstacle (refutes §46/§14's "weld reproduces authored"):** the castle 45° face and the dome facet
are the SAME KIND of face (unscaled, non-axis, distinct-vert quad); the weld changes NO vertex value for either;
`CalcNormal(local)` gives the RECOMPUTED value for BOTH (f3 / 07a5). Yet the editor STORES **authored f7 for the
castle** but **recomputed 07a5 for the dome**. **No single CalcNormal-over-welded-winding rule produces that
split** — it is NOT a face-geometry property. Also refuted (`pool_seed.py`): across all 80 castle 45° faces,
`CalcNormal(raw local)` never lands on f7 (only f3/f4), so the editor's stored f7 is the AUTHORED value,
un-recomputed — not a pooled CalcNormal output.

**So the final residual is the editor's per-face normal DECISION rule** — for a given face, does UnrealEd store
the imported authored `Normal=` or a `CalcNormal` recompute? Authored for the castle bastion, recompute for the
dome. This is context/provenance-dependent (plausibly: builder-generated brushes like the dome's 2DLoftSIDE
lathe carry a stale authored normal that Finalize overwrites, vs a hand-drawn brush whose authored normal
Finalize leaves; OR a per-brush/per-poly flag; OR the editor's brush-model point-pool order differs for the two
so its CalcNormal INPUT differs — native's reconstruction matches the dome but not the castle, i.e. native's
brush-model winding ≠ the editor's for the castle bastion = the deep §16 point-pool-order residual). **Not
resolvable offline; not castle-safe by any ULP threshold (§14/§46 warned).**

**NEXT (the final decode): gdb the editor's per-face normal decision at the surf-creation site** (`bspAddNode`/
`alloc_surf`/`FPoly::Finalize` 0x10015e83) for a castle bastion 45° face vs a dome facet — does it CalcNormal
and keep the result, keep the imported authored normal, or is its CalcNormal INPUT (brush-model welded winding)
different from native's? That rule is the last thing between HERE (incremental tree topology byte-identical,
1637/1637; §45) and byte-parity. Reusable: `is_unit_axis(authored)` guard; native's `build_brush_temp_bsp`/
`bsp_node_to_fpoly` faithfully reconstruct the welded LOCAL winding (dome match proves it). Harness committed:
`derisk-normal-weld/`. SIX real fixes landed this session (§11/§33/§34/§42/§43/§45); this ~1-2-ULP normal
decision is the sole remaining lever.

## 48. RESOLVED (the per-face normal DECISION is the CSG OP): CSG_Subtract recomputes the normal over the LOCAL winding; CSG_Add keeps authored — castle-safe, twins 86→33 (uncommitted, for review)

The §47 "editor stores authored `f7` for the castle bastion but recomputed `07a5` for the dome — SAME kind of
face, no CalcNormal rule produces that split" question is answered: **the split is the CSG OPERATION.**
UnrealEd's `bspBrushCSG` filters the RECONSTRUCTED brush-model polys (`bspBuildFPolys` → `FPoly::Finalize` →
`CalcNormal` over the brush-**LOCAL** winding) for a **CSG_Subtract** brush, but the transformed **authored**
polys for a **CSG_Add** brush. So a subtract face's stored normal is `CalcNormal(local)`; an add face keeps its
authored `Normal=`. This is neither the task's (a) "point-pool/winding order" nor a keep-vs-recompute *threshold*
— it is a clean per-brush **op-code** gate.

**Evidence (offline, decisive — the flip-flop is over).**
- Castle bastion (`BastionDNE`, kept `f7`) is **CSG_Add**; all 80 castle 45° slanted faces are on Add brushes
  (`_scratch/normrule/classify.py`).
- Dome (`Brush755`, recomputed `07a5`), wedge (`Brush745`), T-junction (`Brush336`) — the ONLY brushes carrying
  the 86 N=105 committed-tree normal twins — are all **CSG_Subtract** (`Brush639`, the one Add twin, was the §42
  ROTATION twin, already fixed). `calc_normal(LOCAL winding)` reproduces the editor's stored dome bits
  (`079e/07a4/07a5/0797`) for the no-weld facets bit-exact.
- **Why §46's raw-local recompute regressed the castle (+14013 B): it recomputed ADD faces too.** Gating on
  Subtract is exactly what makes it castle-safe — the castle has **ZERO** subtract non-axis faces (its 102
  subtract faces are all axis; its 80 slanted faces are all Add), so no castle surf is touched.
- The editor's own gdb captures already show this: `oracle-105.log` (bspAddNode) has the dome (subtract) normals
  already recomputed to `0.73059` at brush-model build; and native (which kept ALL authored) matches the editor
  on 1637−86 nodes, twinning ONLY the 86 subtract-slant faces (§45). No fresh editor run was needed — the golden
  files ARE the editor's decision.

**Fix (uncommitted, `bspcsg.rs::bsp_brush_csg` LOOP 1).** For `oper == Subtract && !is_unit_axis(authored) &&
rot_is_pure_rotation(brush.rot)`: recompute `ed.normal = R · calc_normal(p.verts_LOCAL)` (the large WORLD coords
lose f32 precision — world winding → `…077d`, local → the editor's `…07a5`; §46). Guards: `is_unit_axis` keeps
the exact `±1` on axis faces (`CalcNormal` of a large axis rect is `0.99999994`); `rot_is_pure_rotation` skips
scaled/mirror brushes that bake their linear map `L` (e.g. `diag(-8,8,8)`) into `rot` with `vec_xform=None` —
those are handled by the covariant `vec_xform` path or the existing winding recompute (this guard fixed a
mirror-subtract regression the naive version caused). Add/scaled paths unchanged.

**Measured.**
- **Castle Model body BYTE-FOR-BYTE IDENTICAL** before/after (HEAD build vs fixed build; only the 16-byte package
  GUID differs). Counts 1156/485/16163 unchanged.
- **UNATCO N=105 committed tree: normal twins 86 → 33**, structure still 1637/1637 (zero only-native/only-editor),
  `w-only=0`. The remaining **33 are the brush-model VERTEX-WELD residual** (facets sharing a `bspAddPoint`-welded
  vertex → `calc_normal(raw local)` is 1-2 ULP off the editor's welded-winding value; §46 predicted "86→32,
  1-2 ULP"; the ~23-ULP max is the `w=base·N` amplification of a 1-2 ULP normal).
- `cargo test` 51/51 (added `is_unit_axis_and_rot_pure_rotation_guards`,
  `subtract_recomputes_slant_normal_while_add_keeps_authored`); `bin/test` 1944 passed.

**Does the emit-order CONVERGE = byte-parity? NOT YET.** The committed tree is not fully twin-free (33 residual),
so the sparse-stride repartition emit-order (§20/§36) still permutes. Closing the last 33 needs the **brush-model
`bspBuildFPolys` reconstruction + `bspAddPoint` weld** on subtract brushes (`build_brush_temp_bsp` +
`bsp_node_to_fpoly` — §47 PROVED these reproduce ALL dome bits bit-exact): reconstruct each subtract poly from its
brush-BSP node winding and `CalcNormal` over THAT welded LOCAL winding, instead of the raw T3D winding. That is the
one remaining, well-scoped, castle-safe lever (castle unaffected — still no subtract non-axis faces). This §48 pass
is the castle-safe bulk close (86→33); the weld port is the finisher (33→0 → tree twin-free → emit-order converges).
Harness: `harness/derisk-normal-weld/op_axis_census.py` (op×axis face census + castle-safety proof).

## 49. The §48 "weld finisher" is a PROVEN DEAD-END — the 33 residual is a ~1e-4 vertex-VALUE perturbation inside the editor's own FPoly pipeline, NOT a winding-order/weld effect (offline reconstruction is exhausted; needs a live surf-creation vertex trace)

Implemented the §48 finisher exactly as scoped — reconstruct each subtract face's LOCAL winding via the brush's own
temp BSP (`build_brush_temp_bsp`+`bsp_node_to_fpoly`), key by `i_brush_poly`, 1:1-match-or-fall-back, and
`CalcNormal` over THAT winding instead of the raw T3D winding. **It closes 33→33 (ZERO change); reverted to HEAD
`345d36d0a` (clean, `git diff` empty).** Three independent refutations kill the whole "welded winding" premise:

1. **The reconstruction reproduces the RAW winding, not a welded one.** Env-gated dump over the full N=105 build:
   **330 reconstructed subtract faces, 329 clean 1:1 matches, 0 where `recon_normal ≠ §48 raw-local`.** Native's
   `bsp_node_to_fpoly` is arithmetically identical to the raw T3D winding everywhere — so it changes nothing.
2. **The dome has NO weldable vertices.** Brush755's 88 unique verts are ALL pairwise ≥ 0.002 apart (0 near-dup
   pairs under the `bspAddPoint` tol) → no per-brush weld is possible in native OR the editor. §46/§47/§48's "the
   weld REORDERS the winding" is FALSE; §47 only ever verified the *no-weld* facets (ib 3/20/44/61), which raw-local
   already matches — it never checked a TWIN facet.
3. **The twins are UNREACHABLE by any winding reorder.** Brute-forced every cyclic rotation + reversal of every
   dome poly (LOCAL and WORLD) against the editor's stored normals: **21 of 22 dome targets are unreachable by ANY
   ordering of the exact T3D verts.** So the residual is NOT a winding-order effect at all.

**The real residual (the honest limit):** the editor stores `CalcNormal` over verts that are ~**1e-4 OFF** the exact
T3D winding — a VALUE perturbation the editor introduces inside its own FPoly pipeline (`bspBuildFPolys`
reconstruction / world point-pool), yielding a normal 1-2 ULP off. Native's byte-identical *tree topology* does not
reproduce those perturbed VALUES. This is precisely §47's flagged "gdb the editor's per-face normal DECISION at the
surf-creation site" — but the question is now sharpened from *which normal* (§48 answered: the CSG op) to **which
VERTS** (the ~1e-4 source). Not resolvable by any offline reconstruction — which is why no castle-safe offline lever
closes it. **NEXT:** a live gdb trace of the exact FPoly verts (bits) the editor feeds `CalcNormal` for ONE dome
Brush755 twin facet at the Finalize site (`0x10015e83`), to pin the ~1e-4 SOURCE (3-plane intersection in
`bspBuildFPolys`? point-pool quantization? `FPoly::Transform`?) and decide reproducible-offline vs
editor-internal-CSG-state (the true limit). Probes (throwaway): `_scratch/normfin/{twincmp,cyclic_probe2,neardup}.py`.

**Where the effort stands:** SEVEN real byte-parity fixes landed (§11/§33/§34/§42/§43-44/§45/§48); **CASTLE Model-body
is BYTE-IDENTICAL**; **UNATCO tree TOPOLOGY is byte-identical (1637/1637)**; the entire remaining UNATCO gap is 33
sub-ULP normal twins from this one engine-internal ~1e-4 vertex perturbation + its sparse-stride emit-order
amplification. Byte-parity is achieved on castle and reduced to a single, precisely-characterized, gdb-only
precision residual on UNATCO.

## 50. §49's "~1e-4 vertex perturbation / gdb-only" verdict is OVERTURNED — a LIVE CalcNormal gdb capture proves the editor feeds the EXACT T3D verts in IDENTICAL order; the 33 residual is DOWNSTREAM of the brush-model CalcNormal (world-CSG / `bspAddNode` / `bspAddVector`), fully offline-characterizable

A gdb trace INSIDE the editor's `FPoly::CalcNormal` (Engine.dll RVA `0x150510`, breakpoint on `ecx=this`,
dumping `Vertex[]`/`NumVertices`) during the dome Brush755 `EDIT PASTE` captured all **78 CalcNormal calls
(one per brush poly)** with their exact input verts (`harness/derisk-normal-weld/calcnormal_trace.py` →
`calcnormal.log`). Three offline comparisons against native's exact T3D verts (`cmp_inputs.py`, `cmp_order.py`,
`local_vs_world.py`) settle it:

1. **The editor's CalcNormal inputs are 100% BIT-IDENTICAL to native's T3D verts** — all 88 distinct dome verts
   match bit-for-bit, 0 perturbed, max L1 delta **0.0**. §49's "editor feeds ~1e-4-perturbed verts to CalcNormal"
   is **FALSE**.
2. **In IDENTICAL ORDER** — 78/78 captures are the same vertex sequence as native's T3D poly (0 cyclic-rotations,
   0 reversals, 0 other permutations), and native's `calc_normal` gives the SAME bits on the editor's order as on
   native's. So the twin is NOT winding-order and NOT a `calc_normal` arithmetic/op-order bug either (native's
   fan-sum + f64-widened `NormalizeSlow` port, §16, is byte-faithful — proven here against the live inputs).
3. **Brush755 is IDENTITY-transform** (no `Rotation`, MainScale/PostScale = 1, just a translation to world
   (540,1204,276)). So `rot·calc_normal(local)` (the §48 fix) == `calc_normal(local)` == the editor's captured
   brush-model CalcNormal, EXACTLY. Native matches the editor at the brush-model stage bit-for-bit.

**Therefore the 33 residual twins arise strictly DOWNSTREAM of the brush-model CalcNormal**, in the world-CSG /
`bspAddNode` / `bspAddVector` stage — NOT in the brush verts, their order, or `calc_normal`. `calc_normal` over the
WORLD winding (local + the large (540,1204,276) offset, f32) differs from the LOCAL winding on **64/78** faces
(~1e-4, `local_vs_world.py`) — the large-offset f32 precision loss is the physical ~1e-4 SOURCE. Two concrete,
OFFLINE-testable downstream candidates remain (need the golden per-face normal to disambiguate — from the §45
editor 1637-node struct dump, no live editor required):
- **(a) world-frame node plane:** the editor's stored surf normal = `CalcNormal`/`FPlane` over the WORLD-space
  FPoly (post-`FPoly::Transform`), not the local brush-model normal — §48-local matched 53/86 (the offset-
  insensitive faces) and leaves 33 (the offset-sensitive ones). If so, native should build the subtract node
  plane from the world winding. Castle-safe check: castle subtract faces are all axis (offset-insensitive) → no-op.
- **(b) `bspAddVector` pool dedup:** the normal is shared via the vector pool (`FastFindVectorAddDup`,
  THRESH_NORMALS_ARE_SAME); a face gets assigned a NEIGHBOUR's pooled normal, and native's pool order/threshold
  differs → the 1-2 ULP twin is a pool-assignment artifact, not the face's own CalcNormal (the §16/§18 pool residual
  applied to VECTORS). If so, match the editor's `bspAddVector` dedup order/tolerance.

**This is a genuine, castle-safe, OFFLINE lever — not the gdb-only limit §49 declared.** NEXT: pull the golden
Brush755 per-face normals from the §45 editor struct dump; for each twin face compare against `calc_normal(local)`,
`calc_normal(world)`, and the neighbour-pooled vector to decide (a) vs (b); implement the matching rule in
`bspcsg.rs` (subtract, gated), gate castle byte-identical + UNATCO 33→0 + measure node-56/byte-% convergence.
Probes committed: `harness/derisk-normal-weld/{calcnormal_trace,cmp_inputs,cmp_order,local_vs_world}.py`.

## 51. §50's candidates (a)+(b) are BOTH hard-refuted by the golden bits — the residual is the world-CSG `bspAddPoint` pool, and my §50 capture was the WRONG build stage (EDIT PASTE, not MAP REBUILD)

Decoded the golden Brush755 per-face normals offline from the full-level UnrealEd golden
(`_scratch/uedgolden/UEDGolden_unatco_world.dx`, 3616 surfs / 599 vectors), anchored each dome face on native's
ACTUAL N=105 stored surf normal (the §48 `R·calc_normal(local)` emit), matched golden surf by direction+offset,
compared exact bits (`harness/derisk-normal-weld/golden_normal_rule.py`). **native==golden on 59/78 dome faces; 19
twins**, each a **±1-2 ULP scatter** off `calc_normal(local)` (Δ over nonzero comps: +2×23, +1×15, -2×8, -1×2):

- **(a) WORLD-frame plane — REFUTED 0/19.** `calc_normal(world = local+offset)` is **hundreds of ULP** off golden:
  dome local coords are tiny (max |coord| 32) so `calc_normal(local)` is well-conditioned, but adding (540,1204,276)
  then subtracting v0 in f32 catastrophically cancels → world normal far wrong. **The golden tracks LOCAL, not
  world** — so the surf normal is NOT computed over the world-transformed FPoly.
- **(b) `bspAddVector` pool dedup — REFUTED 0/19.** Every twin's golden normal has **goldshare==1** (its own
  dedicated vector) — none is a shared/pooled neighbour value.
- **(c) CONFIRMED:** golden = a non-systematic ±1-2 ULP scatter off `calc_normal(local)`; no accumulation/normalize
  variant (fan/Newell × f32/f64-inv/div) over the EXACT local verts reaches it (all 0-2/19). The perturbation is in
  the VERTS the editor feeds CalcNormal, but — crucially — **NOT at EDIT PASTE** (§50 proved those are the exact
  T3D verts). **The golden comes from `MAP REBUILD`**, whose `bspBrushCSG`→`Finalize`→`CalcNormal` runs over the
  brush model reconstructed from the world-CSG **`bspAddPoint` point pool** (§15/§16/§17): verts that round-tripped
  through the f32 world pool (stored at large world magnitude, read back / re-localized) carry a ±1-2 ULP scatter
  vs the exact local verts. §50's capture broke at CalcNormal during `_re_add` (PASTE) = the brush-model build,
  which is the WRONG stage — it necessarily saw exact verts. The golden-producing CalcNormal is the REBUILD one.

**So the residual is TRIPLY-confirmed as the editor's world-CSG `bspAddPoint` vertex pool** (a ±1-2 ULP scatter on
19+14=33 of 1637 node normals) — the same §15/§16/§17 pool residual, reached independently by §16, §49, and §50/§51.
It is NOT a world-frame rule, NOT a vector-pool-dedup rule, NOT a calc_normal arithmetic rule (all refuted with
exact bits). **The one correct remaining decode: gdb-break CalcNormal (RVA 0x150510) during `MAP REBUILD` (NOT
EDIT PASTE) for a Brush755 twin face** — capture the ±1-2-ULP-perturbed input verts THERE and trace their source in
the `bspAddPoint` pool. Then either port that pool faithfully (large; the GATE — castle byte-identical + UNATCO
33→0 — is the offline correctness check, even though deriving the exact rule needs the trace) or accept it as the
gdb-only precision floor. Probe: `harness/derisk-normal-weld/golden_normal_rule.py` (reproduces the a/b/c verdict
from the golden `.dx`). No `bspcsg.rs` change (report-don't-force: no castle-safe rule the golden supports yet).

## 52. §51 REFUTED (the residual is NOT a vertex pool) — the twin is a DROPPED SECOND `SafeNormalSlow` in `FPoly::Transform`; landed castle-safe, twins 22→2 (uncommitted, for review)

The §14–§51 "world-CSG `bspAddPoint` vertex pool" conclusion is **wrong**. Three live-gdb captures (proven-stable
oracle path — `harness/derisk-normal-weld/`) settle the mechanism with hard bits:

1. **`MAP REBUILD` calls `FPoly::CalcNormal` ZERO times** (`rebuild_calcnormal_capture.py`: MAP LOAD golden105 +
   MAP REBUILD under gdb, UNCONDITIONAL breakpoints — **5878 `bspAddNode` calls, 0 `CalcNormal` calls**). So the
   twin is NOT produced by any rebuild-stage CalcNormal over pooled verts — §51's "the golden comes from the
   REBUILD CalcNormal" is refuted. (The rebuild's `bspAddNode` FPolys carry the twin normal *already set*; their
   polygon verts are world-CSG-clipped ~40-64 ULP off local and `calc_normal` over them does NOT reproduce the
   stored normal — the normal is carried, not recomputed.)
2. **The paste brush-model `CalcNormal` OUTPUT is EXACT `nl`** (`paste_cn_output.py` = `calcnormal_trace.py` with
   the **tail bp fixed to RVA `0x150620`** — §50's `0x150643` was the degenerate/error branch `jne 0x1015065d`
   at `0x150622` skips on every valid face, which is why it never fired; `0x150620`, right after `NormalizeSlow`
   returns with `edi=this`, is the correct output-read site): the editor's per-facet brush-model CalcNormal output
   equals native `calc_normal(local)` **byte-for-byte, 78/78**. So the once-normalized normal is exact for ALL
   dome facets — the golden's ±1-2 ULP twin (19 non-axis facets) is introduced DOWNSTREAM of CalcNormal, WITHOUT
   another CalcNormal.
3. **The twin = a SECOND `SafeNormalSlow`.** `FPoly::Transform` (applied to every brush during `bspBrushCSG`)
   re-normalizes the finalized normal — dot in f32, sqrt via f64, reciprocal-multiply (`fpoly.rs::safe_normal_slow`,
   core.dll `0x27180`). `CalcNormal` already normalized once (→`nl`); the transform normalizes AGAIN
   (→`safe_normal_slow(nl)`), and since `|nl|²` is `0x3f7fffff`/`0x3f800001`-ish (not exactly 1.0) the re-scale
   shifts 1-2 ULP. **OFFLINE PROOF: `calc_normal(f32 dot / f64 sqrt renorm)` == golden on 19/19 non-axis dome
   twins** (the other 4 dome "twins" are axis faces handled by `is_unit_axis` authored-keep). Native's §48 subtract
   path stored only the once-normalized `nl` — the missing second renorm IS the twin.

**Fix (`bspcsg.rs::bsp_brush_csg` LOOP 1, §48 pure-rotation subtract path):** `ed.normal =
safe_normal_slow(&(R·calc_normal(local))).unwrap_or(...)` — the same `SafeNormalSlow` the SCALED path already
applies (line ~1744) and the editor's `FPoly::Transform` applies to all faces. **Castle byte-IDENTICAL** (with-fix
vs no-fix `NativeCastle.dx` Model body = **100.00%, first-diff None** — the path is `!is_unit_axis`-gated and
`safe_normal_slow` is a no-op on exact axis normals, so the castle's zero non-axis subtract faces are untouched;
counts 1156/485/26/384/4 unchanged). **UNATCO node-plane NORMAL twins 22→2** (N=105 world-only golden105 basis,
`harness/derisk-normal-weld/node_normal_twincount.py`); Brush755 dome **19→0** (`golden_normal_rule.py` vs the
full golden). `cargo test`
**52/52** (`subtract_recomputes_slant_normal_while_add_keeps_authored` updated to pin `safe_normal_slow`, plus
`subtract_slant_normal_rotates_then_renormalizes_with_correct_index_order` added — a 90°-yaw fixture that pins the
production `R·nl` multiply index order so a transpose bug goes RED, per the 2-reviewer gate), `bin/test` 1944 passed.
**2-cold-reviewed** (correct + castle-safe confirmed; the one actionable finding — the identity-`rot` fixture left
the `R·nl` multiply unpinned — is addressed by the added rotated regression).

**Residual (2 twins, NOT closed):** both are **CSG_Add** coincident-plane faces (Brush678 Add coincident with
Brush768 Subtract; Brush691 Add) — the editor's `FPoly::Transform` renormalizes Add faces too, but the golden
normal there is **neither `authored` NOR `safe_normal_slow(authored)`** (both refuted with bits) — a coincident
Add/Subtract surf-normal-SOURCE case (which brush's face owns the shared surf). Extending the fix to the Add path
would touch the castle's 80 Add slanted faces (castle-safety RISK, un-verified), and no simple derivable rule
reproduces the golden bits — so per report-don't-force + castle-safety-non-negotiable it is left as a characterized
residual for review, not forced.

Harness (durable, `harness/derisk-normal-weld/`): `rebuild_full_capture.py` / `rebuild_calcnormal_capture.py`
(oracle-path MAP REBUILD bspAddNode+CalcNormal full-bit capture — the crash-free pattern; per-call position filters
CRASH the rebuild, UNCONDITIONAL logging is stable), `paste_cn_output.py` (fixed-tail paste CalcNormal-output),
`analyze_an.py`/`analyze_cn.py`. §51's `golden_normal_rule.py` a/b/c verdict stands as the REFUTED candidates; the
actual answer is (d) the dropped second `SafeNormalSlow`.

## 53. PIVOTAL REFRAME (overturns §45's "byte-parity in reach"): the normal-twin campaign (§42–§52) is PARITY-IRRELEVANT for UNATCO — the dominant byte gap is a STRUCTURAL, AXIS-ALIGNED BSP fragmentation born in brushes (105, 213], invisible to the N=105-limited verification

Measured the whole-map convergence at HEAD `96ca1d2b6` (native rebuilt, cargo 52/52) vs `golden762.dx` (bare
`MAP REBUILD` basis). **Hard result: the entire 8-fix normal campaign moved the whole-Model byte-% by ~0.**

- **Whole Model `persec_bytematch` = 19.06%** — FLAT vs §42's 19.11% and §45-era ~19%. Per-section positional match:
  Vectors 74.3% (599/599 count-exact, ORDER permuted), Points 35.6%, Nodes 20.3%, Surfs 16.0% (Verts 3.5% / Leaves
  23.3% are deflated by the bare-rebuild basis UNDER-building golden Verts — a basis artifact, not real divergence).
- **Node-56 emit-order STILL PERMUTES** (native `(1,0,0)@-432` vs editor `(0,0,-1)@-416`), byte-identical to §45's
  PRE-twin-fix state. **Closing 86→2 normal twins moved node-56 by ZERO.** The node-plane SET diverges 611 only-native
  / 645 only-editor at N=762 (was 634/673 at §36 — the whole twin campaign closed only ~23/28 planes).
- **The 2 sub-ULP twins round to SHARED node-plane keys → they contribute 0 to the set-diff and 0 to the byte gap.**
  Closing them (even if a rule existed) yields ZERO parity movement — proven, not assumed.

**WHERE the divergence is actually born (the reframe):** bisecting the incremental tree — **at N=105 the full tree is
byte-IDENTICAL** (shared 974, only-native 0, only-editor 0, emit-order identical) **WITH the 2 twins present** — so
§45's "precision cascade / topology byte-identical / parity in reach" was an **N=105-limited illusion** (everything it
checked matches). The tree first diverges STRUCTURALLY in **(105, 213]** (at N=213: 141 only-native / 81 only-editor,
the root split FLIPS), growing to 611/645 by N=762. **The divergent planes are overwhelmingly AXIS-ALIGNED** (top-12
at N=213: zero slanted) → this is a STRUCTURAL FRAGMENTATION family (native builds a different set of axis wall-
fragments than the editor for brushes 105-213), NOT the slant-normal-twin family (§14-§52) and NOT a precision cascade.
This re-opens the §20/§23/§29 "soup/tree structural divergence" thread, now sharply pinned to brushes **(105, 213]**.

**The 2 Add-coincident twins (§52 residual), decoded + REVERTED:** golden = `safe_normal_slow(calc_normal(local))`
(the §52 double-normalize) on the ADD face's own winding (Brush678 coincident w/ Sub Brush768; Brush691). Castle-safe
(castle has 0 Add non-axis faces coincident with a subtract face, of 120; UNATCO has 6) — BUT no uniform static rule
reproduces the bits: a blanket Add-recompute fixes Brush678/1277 but BREAKS Brush439 (golden keeps authored +Y; the
winding recompute gives an opposite −Y — a DIRECTION diff, not precision) — it's an incremental surf-OWNERSHIP decision
(which brush's face owns the shared `FBspSurf`, §11 texture/flag-gated), order-dependent, not statically derivable.
Left UNFIXED (report-don't-force) — AND parity-irrelevant per the SHARED-key finding above. Probes: `_scratch/twin2/`.

**NET, honest state:** EIGHT real byte-parity fixes landed (§11/§33/§34/§42/§43-44/§45/§48/§52), all castle-BYTE-
IDENTICAL and all genuine engine-faithfulness corrections (the UNATCO normals ARE now editor-correct). **Castle is
byte-identical; UNATCO's normal VALUES are right but its TREE STRUCTURE diverges from N>105** — so the whole-map
byte-% is dominated by the axis-aligned structural fragmentation in brushes (105,213], which the twin work does not
touch. **The correct next lever = repoint the `bspAddNode` editor-tree-oracle to the FULL UNATCO build and decode the
structural divergence born in (105,213]** (why native builds different axis wall-fragments there — the incremental
`bsp_brush_csg`/`FilterWorldThroughBrush` keep/discard or the coplanar chain-head orientation, §23/§29 family, at
those brushes). The normal-twin family is CLOSED and, for UNATCO whole-map parity, a dead end — do not re-chase it.

## 54. FIRST (105,213] structural divergence PINNED + FIXED (uncommitted): it is NOT §23/§29 coplanar chain-head — it is a PASS-STAGING bug (native defers PORTAL brushes to the post-repartition semisolid layer; UnrealEd processes them structurally, pre-repartition)

§53's guess that the (105,213] divergence is the "coplanar chain-head orientation §23/§29 family" is **WRONG
about the mechanism** — it is far simpler and CLEANLY FIXABLE. Committed-tree bisection (native NOREPART
`UEDCLI_BSPCSG_TREE_STRUCT` vs editor `editor_struct_unatco_n.py` gdb dump at `bspBuildFPolys` entry, both
POST-rollback per §40; new comparator `committed_tree_diff.py` that ignores index-label drift and w-twins):

- **N=105 committed tree = byte-IDENTICAL (1637/1637, 0 structural nodes).** Confirmed from the cached
  `_scratch/ptx/editor-struct-unatco-105.log`.
- **FIRST structural divergence = N=106 = `Brush344`** (world-brush idx 105): editor 1639 committed nodes,
  native 1637. Nodes 0..1636 intrinsically identical; the editor's 2 extra nodes (1637,1638) are BOTH
  Brush344's face `(0,1,0)@1152` isurf=571 nv=4 in a coplanar chain; native emits ZERO committed nodes for it.
- **Brush344 is a single-quad CSG_Add PORTAL sheet** (pf `0x4000109` = PF_Portal|PF_TwoSided|PF_NotSolid|
  PF_Invisible), coplanar-antiparallel to node 809 = `Brush365`'s wall face (pf `0x800000`, `(0,-1,0)@-1152`).
  It is **the FIRST detail brush in the whole level** — all 105 prior brushes are structural (why N=105 matches);
  the first non-portal semisolid (`Brush416`) is later at idx 111.

**The mechanism (decoded, ground-truth from oracle-106.log + a reversible native `leaf_func` trace):** native's
`leaf_func::Add` is byte-faithful to `AddBrushToWorldFunc` (adds on {0,2,5&!semisolid}) — and native's leaf
DOES add the portal (filter=2 F_COPLANAR_OUTSIDE, twice at node 809 place=2, IDENTICAL to the editor's two
`ret=0x100317df` adds). The divergence is **not** in the clip/leaf/Outside logic at all. It is a PIPELINE STAGE
bug: native's `build_geometry_bspcsg` routes every non-solid brush (portal included, via `eff_flags`→NotSolid +
`is_detail`) into the **PASS-2 semisolid second layer, which runs AFTER `bsp_build` repartition** (`bspcsg.rs`
~2174). So native adds the portal, but only post-repartition — it never enters the repartition SOUP. UnrealEd
processes a PORTAL in the **structural (pass-1) phase, BEFORE `bspBuildFPolys`** (proven: the portal is in the
editor's pre-repartition dump; and `FindBestSplit` keeps a `0x28` candidate iff `PF_Portal`, §82 §4 /
`bspcsg.rs:1178` — a portal is a valid repartition splitter). Native's TREE_STRUCT dump fires at the end of
pass-1 (pre-repartition), so the deferred portal is simply absent from it → the N=106 "divergence".

**FIX (LANDED, uncommitted, castle-gated — `bspcsg.rs::build_geometry_bspcsg`):** route PORTAL brushes to
PASS 1 (structural), keeping only genuine semisolid/nonsolid in the deferred pass (`detail_pass = pf&0x28 &&
!PF_Portal`). A portal in pass 1 is added as a NON-CSG splitter (`derive_nf` sets NF_NotCsg for NotSolid, so it
carves nothing) and enters the repartition soup — exactly the editor.

**GATE RESULTS:**
- **Castle Model body BYTE-IDENTICAL** (NativeCastle pre-fix vs with-fix differ in exactly the 16 GUID bytes,
  offsets 37–52; nodes 1156/surfs 485/leaves 384/zones 4 unchanged). Castle has 0 portal + 0 detail brushes, so
  `detail_pass ≡ is_detail` there — byte-identical by construction.
- **UNATCO committed prefix EXTENDED 1637 → 1764** (N=106 now byte-identical 1639/1639; the new first
  divergence is node 1764, native `(0,0,1)@30` vs editor `(0,1,0)@-834`, born in brushes (106,159] — the next
  detail/portal or semisolid, to bisect next).
- `cargo test --release` **53 passed** (added `portal_brush_enters_pass1_repartition_soup`, teeth-verified RED under
  a `detail_pass→is_detail` revert in both debug and release); `bin/test` 1944 passed / 0 failed.
- **Whole-map byte-% vs `UEDGolden_unatco_world.dx` (bare MAP REBUILD basis): 19.06% → 18.88% (−0.18pp).**
  The coarse metric SLIGHTLY REGRESSED even though the committed tree improved: native's repartition of the
  portal-containing soup over-splits (nodes 6280 → 6371, overshooting golden's 6314 by +57), inflating the
  section denominators. That over-split is the SEPARATE downstream repartition-order lever (§36) the portal soup
  now exposes — NOT a defect of this fix; matched-byte count actually rose (203913 → 204077). Like §31/§33's
  leading-Add seed, this is a NECESSARY, castle-safe committed-tree correction that is not yet sufficient for the
  coarse byte-%.

**RESOLUTION (post-review — the fix is a genuine STRUCTURAL improvement, committed as a §31/§33-style prerequisite):**
A first 2-reviewer gate SPLIT (A: commit-as-prerequisite; B: hold — root cause unpinned, possible double-representation,
zero portal test, latent Subtract-portal). A follow-up investigation resolved ALL of B's blocking concerns:
- **Q1 — NOT double-representation; it is the downstream repartition lever.** N=106 committed tree is byte-identical
  (native 1639 == editor 1639); Brush344 produces EXACTLY the editor's 2 nodes; pass-2 correctly skips the portal
  (`detail_pass` false → the `if !detail_pass` continue skips it). The +57 final-tree surplus is **broad axis-aligned
  wall planes** ((0,1,0)@-256 ×27, (0,0,1)@284 ×16, …), **NOT the portal plane** (0,1,0)@1152 — which is in the SHARED
  set. The portal is represented exactly once; the +57 is the pre-existing §53 axis-aligned repartition-fragmentation
  lever *shifted* by feeding a more-correct soup. Portal split-scoring is faithful (§82 §5: `pbias=0` inert, ×16
  split-weight; the portal plane is absent from the surplus).
- **Q1 net (the TRUE metric moved forward):** shared node-planes **5669 → 5753 (+84 editor planes now reproduced)**,
  only-editor **645 → 561**, only-native **611 → 618 (+7)**, matched bytes **+164**. The committed prefix 1637→1764.
  The coarse positional-% regressed only because the +57 node-COUNT overshoot shifts array positions — the underlying
  agreement improved.
- **Q2 — Subtract portals cannot occur:** across ALL 120 shipped DX maps, 978 brush-level portal brushes are **all
  CSG_Add, zero Subtract** — the `not_poly_flags=0x28` NotSolid-strip edge is unreachable; and the path faithfully
  mirrors UnrealEd's `bspBrushCSG` (`Add?0:PF_Semisolid|PF_NotSolid`), so a native-only guard would risk UN-faithfulness
  — correctly none added.
With B's three objections resolved (double-rep refuted, Subtract-portal unreachable, regression added) and the fix a
genuine structural gain (+84 shared planes, +164 matched bytes), it is COMMITTED as a correct-but-insufficient
committed-tree prerequisite (§31/§33 pattern). The −0.18pp coarse regression is a denominator artifact of the separate
§53/§36 axis-aligned repartition over-split lever — filed as the next lever, NOT a defect here.

**Harness (durable, committed under `harness/editor-tree-oracle/`): `editor_struct_unatco_n.py` (parameterized
editor committed-tree dump at any N, auto-builds golden{N}), `committed_tree_diff.py` (intrinsic structural vs
w-twin comparator).** Throwaway probes in `_scratch/treebisect/`.

**NEXT:** bisect (106,159] for the node-1764 brush; if it is the 2nd portal (`Brush362`, idx 107) it should
already be fixed — re-check — else it is a semisolid (`Brush416`) and the question becomes whether UnrealEd ALSO
puts semisolids in the pre-repartition tree (would move native's whole pass-2), or the downstream repartition
over-split. Also: add a committed regression asserting a PORTAL brush contributes to the pre-repartition
(pass-1) committed tree, before commit + the two cold-review gates.
