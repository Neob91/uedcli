# Offline BSP/CSG/collision engine — design spec

**Status:** spec (ephemeral — folds into `architecture.md` + `unrealed/*.md` on implementation).
**Date:** 2026-06-24 · **Review:** 3 rounds (initial) + 3 rounds (post-reframe) applied.
**Decision it implements:** `decisions.md` 2026-06-24 09:07 + 12:40 UTC. The static `level doctor`
(`decisions.md` 2026-06-24 08:50) already shipped; this is its build-emergent-issue upgrade. **The
"fully offline" fork is RESOLVED (Andrzej, `decisions.md` 12:40): build D0+D1 now; D2 (fully
offline) is a deferred TODO — see §1/§9.**
**Grounding spikes (durable evidence):** `spikes/2026-06-24-bsp-csg-hole-mechanism-from-binary.md`,
`…-bsp-collision-solidity-movers-from-binary.md`, `…-bspbuild-partition-heuristic-from-binary.md`,
`…-offline-bsp-engine-slice1-parity.md`, `…-offline-bsp-engine-slices1b-2-3-parity.md`,
`…-offline-bsp-engine-d0-editorlog.md` (the built+validated D0).

> **What review established (the load-bearing correction):** **a *hole* is an ABSENT face**, and you
> cannot tell an absent face from correct CSG by reading the built model — an authored face
> legitimately having no built surf is the *normal* case (interior/shared/buried faces; CSG splits,
> merges, reverses, and annihilates). Knowing a face *should* exist requires re-running CSG. So:
> reading the saved build detects **presence** bugs, and the editor's own **`MAP REBUILD`
> drop-warnings are the cheapest real ground truth for dropped (absent) faces**.
>
> **Completeness correction (Andrzej, after review):** the two cheap things *together* find the
> whole issue list on the real editor build. Most of the user's hardest items — **HoM / T-junction
> cracks, invisible walls, fall-through** — are **present/structural in the built geometry**, so the
> saved-build reader (D1) *locates* them; **dropped-face holes** are confessed by the editor's
> drop-warnings (D0). So **D0 + D1 = the complete issue detector** (on a build the editor already
> made); the fully-offline engine (**D2**) is reframed as an **optional upgrade** that adds only
> "never run the editor at all" + rare *silent-absence* holes. **All D2 design notes are retained
> below** — D2 is deferred/optional, not dropped.

---

## 0. Vocabulary (read cold — no prior context assumed)

- **UnrealEd / the editor** — UnrealEngine-1's level editor (UED22, UT-lineage, under wine).
  **Crash-prone, slow, Docker-bound.**
- **CSG** — world starts infinite solid; **subtractive** brushes carve rooms, **additive** add
  solid; brushes process **in actor order** (last op wins).
- **Brush** — an authored convex/closed polyhedron (`FPoly` faces) with `CsgOper` (Add/Subtract),
  **solidity** (`Solid`/`Semisolid`/`Nonsolid`), possible `Portal`. In uedcli: an `Actor` + `Brush`.
- **`FPoly`** — UnrealEngine's convex polygon (≤16 verts, `Normal`, texture vectors, `PolyFlags`).
- **BSP** — the plane tree built from CSG: **node** = plane + **surf** (visible polygon); coplanar
  surfs chain; **leaves** = convex empty cells; **zones** group leaves. Rendering/collision/
  visibility read it.
- **Built BSP / built model** — `Nodes`/`Surfs`/`Vectors`/`Points`/`Leaves`/`Zones` the editor
  computes and writes into a saved `.dx`/`.unr`.
- **Hole vs invisible wall — the distinction this spec turns on.** A **hole** = an *absent* face
  (the build dropped an `FPoly` that should be there) → HOM + often fall-through. An **invisible
  wall** = a *present* phantom collision node where nothing renders. **Presence** (phantom nodes,
  degenerate surviving surfs) is readable from the built model; **absence** (holes) is not — it
  needs the should-vs-did comparison.
- **Build-emergent** — a hole/wall produced only *after* CSG/BSP (a sliver, a T-junction crack), not
  predictable from one authored brush. The class the static `level doctor` cannot catch.
- **Editor drop-warnings** — the editor logs each face it discards: `FPoly::CalcNormal: Zero-area
  polygon`, `FPoly::Finalize: Not enough vertices`, `BspValidateBrush linked %i of %i polys`. These
  *are* the dropped faces, as ground truth (mechanism spike §4–5).
- **Differential harness / oracle** — build a corpus in the **real editor** (oracle) and diff.
- **Float32-faithful** — round to float32 at threshold boundaries (the `rotation.py` GMath
  discipline) so 0.25-band decisions match the engine's SSE math.

## 1. Goal, deliverables, and the offline fork

**Ultimate goal.** Catch the **build-emergent** holes / fall-through / invisible walls the static
linter can't, with as little live-editor dependence as the value justifies.

Three deliverables, **ordered cheapest-capability-first** (review reordered these):

**D0 — editor drop-warning pass + the measurement (cheapest; ships first; the decider & the
oracle).** Drive `MAP REBUILD` once and capture the **drop-warnings** → the editor's confessed
dropped faces / leaks / unlinked T-points / infinitesimal nodes, on **real semisolid/portal maps**,
with **no new parser and no port**. **What D0 yields is COUNTS + per-class detail, NOT face
identity** — the log strings carry no `(brush, poly)`/coordinate (`CalcNormal: Zero-area polygon`,
`Finalize: Not enough vertices (%i)`, `BspValidateBrush linked %i of %i`). **It is high-recall but
not provably complete:** a channel can fail to flush (the 4 KB log buffer — D0's validation caught
an open box via the T-points channel *because* `BspValidateBrush` didn't flush that run), which is
exactly why D0 reads *every* channel — the union is the safety net. Two uses: (a) the
**measurement** — compare D0's *total* drop count to the static `doctor`'s per-brush predicted
count; the difference is an **upper bound on build-emergent drops** (NOT a per-face classification —
D0 has no identity to confirm overlap) → the go/no-go signal for D2; (b) the **verification oracle**
for D1/D2 (at the count/structure level, per (a)'s limitation). **D0 needs the editor once, so it is
NOT the "fully offline" product** — it's the measurement instrument, the test oracle, and an interim
author-time report.

**D1 — the built-BSP reader (`level doctor --built <map>`; the located-issue half; UNBUILT,
conditional on P0-a).** Parse the saved `.dx` built model and **locate** the present/structural
issues:
- **HoM / T-junction cracks** — a built surf edge with a neighbour surf's vertex on its interior and
  no matching vertex. *Algorithm unvalidated:* it assumes the saved arrays retain per-surf edge
  rings AND that `bspMergeCoplanars`/`bspOptGeom` didn't merge/relocate the crack away — **a spike
  (P0-b1) must confirm the `UModel` arrays carry this adjacency before D1 claims to locate it.**
- **Invisible walls** — near-zero-area blocking nodes / sliver surviving surfs.
- **Fall-through** — **a built floor surf whose `PolyFlags` carry `PF_NotSolid`/`PF_Semisolid`/
  `PF_Portal`** (the discriminator per the collision spike §4 — NOT "rendered-but-not-solid", which
  is ill-posed since collision and rendering walk the *same* nodes). A *missing*-node floor is an
  **absence**, which D1 cannot see — that falls to D0/D2.

D1 is the located-issue half (HoM, invisible walls, solidity-class fall-through — the user's hardest
items), but it is **not yet built and is gated on P0-a** (binary `UModel` parse feasibility) **and
P0-b1** (arrays carry the needed adjacency). If either fails, those rows degrade to D0's
existence/count signals.

**D0 + D1 together = the issue detector that covers every class EXCEPT silent-absence, on the real
editor build** — D0 confesses dropped (absent) faces (by count), D1 locates present/structural HoM +
collision bugs (*if P0-a/P0-b1 hold*). Coverage (D1 cells are **conditional on P0-a/P0-b1**):

| Issue | D0 (drop-warnings) | D1 (parse built model) |
|---|---|---|
| Hole = dropped face (zero-area, <3 verts) | ✅ count (`CalcNormal: Zero-area` / `Finalize: Not enough vertices`) | — (absence) |
| Hole = non-watertight leak | ✅ count (`BspValidateBrush linked X of Y`, when it flushes) | — |
| HoM = T-junction crack | ⚠️ existence count (`Processed %i T-points, linked: %i/%i sides`) | ⚠️ **located IF P0-a + P0-b1** |
| Invisible wall = phantom node | ⚠️ existence count (`bspAddNode: Infinitesimal polygon`) | ⚠️ **located IF P0-a** (near-zero-area node) |
| Fall-through | ⚠️ dropped-floor-face subset (count) | ⚠️ **located IF P0-a** (built floor surf with `PF_NotSolid/Semisolid/Portal`); *missing-node* floor → absence (D0/D2) |
| Silent absence (no warning, no trace) | ❌ | ❌ → **D2 only** |

So **D0+D1 covers every class *except* silent-absence holes** (and D1's *located* coverage is
conditional; absent that, those rows are D0 counts only). "Complete" is never used bare in this spec.

**Honest status & realistic fallback (review round 2 — read this before believing the table).**
- **D0 is built and validated.** **D1 is an UNSTARTED HYPOTHESIS**, gated on a binary `UModel` parser
  (P0-a) that **has never been spiked**, *and* on whether the built arrays even retain T-junction
  adjacency (P0-b1) — which may be **structurally unsatisfiable**: the editor's `bspOptGeom`/
  `bspMergeCoplanars` passes exist precisely to *link/clean up* T-junctions, so a crack the optimizer
  fixed leaves nothing for D1 to locate, and one it failed to link is exactly what D0's T-points
  *count* already reports. **P0-b1 must be spiked together with P0-a, before D1 is treated as real.**
- **The most likely near-term product is D0 alone + the already-shipped static `level doctor`.** Be
  blunt about what that is: D0 is a **counts-only CI regression tripwire** ("this commit went 0→7
  dropped faces / unlinked T-points") — **no locations, no brush identity, channel-flush-dependent**,
  and it **runs the editor** (its only edge over a mapper reading UnrealEd's own rebuild log is
  scriptability). It is a useful **smoke alarm**, not the "find ALL issues, located" tool. The
  genuine offline-at-inspection, located-issue value lives entirely in D1 — i.e. behind the unspiked
  parser. **The project's headline value is therefore contingent on P0-a/P0-b1; until they return
  green, the honest claim is "D0 ships as a tripwire; D1 is a maybe."**

**D2 — the fully-offline faithful engine (`level doctor --deep`; the original "fully offline" goal;
OPTIONAL UPGRADE — all design notes retained below).** A pure-Python CSG→BSP→collision build that
re-runs CSG so it *knows what should exist* — the **only fully-offline route**, and the only thing
that also catches *silent-absence* holes (the one class D0+D1 miss). Andrzej's resolution: **build
D0+D1 now; D2 is a deferred optional upgrade whose sole added value is "never run the editor at all"
(+ silent-absence).** D2 is deferred-but-fully-specified — §3a/§4/§5/§6/§7's D2 content stands as the
design for when/if it's built (gated on D0-b's measurement + the §5 budgeted bar). It *also* unlocks
cheap offline textured rendering later (built surfaces + `texture sync` texels; lighting out of scope).

**The offline fork — RESOLVED (Andrzej, `decisions.md` 12:40).** "Fully offline, but 100% accurate"
is served by **D0+D1 now** (covers every class but silent-absence, on the real build — one editor
run) with **D2 a deferred TODO** for the runtime-fully-offline end-state.

**Non-goals.** Lighting/lightmaps; a rasterizer; **bit-identical** BSP trees (gate = surviving/
dropped-face set + leaf/zone structure, §5); **mover** collision (separate per-actor system — every
deliverable's output says so loudly); D2 engine using the editor at runtime.

**D2 soundness caveat.** Until its solidity-class slice lands, D2 is **unsound on semisolid/nonsolid/
portal maps** (Add/Subtract solids only) → `--deep` refuses them until then. D0 and D1 have no such
caveat (they read the real build).

## 2. Why each deliverable (and why D0 first)

- **Static prediction only** (shipped `doctor`) can't enumerate build-emergent holes — they come
  from brushes splitting *each other*.
- **D0 (editor drop-warnings)** is the editor's own ground truth: it lists the *actual* dropped
  faces directly, on real maps, for the cost of one rebuild + a log grep — the same editor drive the
  corpus harness already does. It is the cheapest thing that delivers the headline capability and
  the only thing that can *measure* the D2 go/no-go.
- **D1 (read the saved build)** adds the *presence*-side (invisible walls) that warnings don't give,
  offline at inspection.
- **D2 (re-run CSG offline)** adds runtime-offline absence detection — the most expensive piece, so
  it goes last and conditional.

## 3. What is already known + current honest parity

### 3a. Decoded substrate (`Editor.dll`/`Engine.dll` RVAs, base `0x10000000`)
- **`FPoly` survival** (Engine): `Finalize 0x150ac0` — `Fix 0x150da0`, reject `<3` verts, reject
  ~zero-area via `CalcNormal 0x150510` (`1e-8` size² floor). `RemoveColinears 0x151090` drops
  coincident (`<1e-4`) + colinear (`9.999999e-05`). **The `appErrorf`/Critical-Error path ABORTS the
  rebuild (no model)** (distinguished by `Finalize`'s `NoError` arg). **`Finalize`/`CalcNormal`/
  `BspValidateBrush` emit the D0 drop-warnings.**
- **Plane classify/cut** (Engine): `SplitWithPlane 0x1518b0` (±`0.25`/±`0.01`; classify **and cut**)
  vs `SplitWithPlaneFast 0x151f90` (classify-only). **D2's partition path uses `SplitWithPlane`;
  exact-0.0 belongs only to the CSG leaf-filter.** `SplitWithPlane`'s **cut geometry** is not yet
  disassembled (a D2/S-1 RE task).
- **`FindBestSplit 0x335d0`** (ported): `Score=(100−Balance)·Splits+Balance·|Front−Back|`, portal
  bonus, ×16 portal-split, `Inc` step (Opt 1/Good N/10/Lame N/4), strict-`<` tie-break,
  `Balance|(PortalBias<<8)`. **Open: `0x336d2` structural-splitter skip (affects tree shape) —
  finish-decode in D2/S-1; same open item the partition spike flags.**
- **`MAP REBUILD` params** (`0x65220`): **Balance=50, PortalBias=70, Optimization=2** (in `commands.md`).
- **`bspBrushCSG 0x355e0`**: `BuildCoords`→`Transform`+`Fix`→CsgOper flag (Add 0/Subtract `0x28`)→
  leaf-filter.
- **CSG leaf-filter**: dispatcher `0x31f50` → recursive `0x32bf0` → leaf-handler `0x32030`
  (exact-0.0, per-CsgOper winding). **D2 gap #1.**
- **`SplitPolyList 0x34530`** (via `bspBuild 0x35ef0`): `FindBestSplit` → `bspAddNode` (`vtable+0x224`;
  static `0x34e80`, re-runs the infinitesimal-poly predicate — shared with `Finalize`). **Node count
  = # `FPoly`s on the tree; coplanar polys each their own node.** **D2 gap #2.**
- **Cleanup**: `bspMergeCoplanars 0x36200`, `bspOptGeom 0x36870`, `bspRefresh 0x36cd0`,
  **`bspBuildBounds 0xaace0`** (builds the per-node **collision bounding hulls** — collision-load-bearing).
- **Collision is structural** (collision spike): `LineCheck 0x1ae4c0`/`PointCheck 0x1aeba0`, no
  per-node flag test. **No console verb asks "does a trace hit?"** → collision ground truth is the
  **built structure** (D0 leaf counts / D1 parsed model), never a live trace oracle.
- **Solidity classes**: Solid cuts; Semisolid adds surfaces without re-cut; Nonsolid no node; Portal
  force `PF_Semisolid`-strip→`PF_NotSolid` (`csgRebuild 0x4a800`).
- **Log channels that flush under `MAP REBUILD`**: the drop-warnings (D0) + `Nodes: %i -> %i`,
  `BspMergeCoplanars reduced %i->%i`, `bspBuildBounds: Generated %i bounds, %i hulls`,
  `Found %i zones`, `Portalized: … %i leaves, %i nodes`. (`bspBuild built …` does NOT flush.)
- **No console oracle for node *planes*** (`bspNodeToFPoly 0x365b0` is internal) → per-plane data
  needs a **binary `UModel` parse** of the saved `.dx` (new RE, version-61 wrinkle; `dxpkg` parses
  only package headers, not the Model). This is **D1's feasibility gate (P0-a)**, and Tier-S's oracle.

### 3b. Current parity — honest (corrects an over-claim; do not cite "2/5 exact")
Committed `_scratch/bspspike/corpus_result.json`: **only `single_box` is exact**, and it has no real
splits (confirms plumbing, not the heuristic/CSG). The port computes **several disagreeing count
candidates** and **has drifted from the captured JSON** (`abutting_subtracts` reads 11≠editor 10);
its `merge_coplanars`/`*_nodes` are **count-fitting placeholders to discard**. So D2's first task
pins **one** node-count metric (= editor's `Nodes:`/`Portalized:`), re-runs, re-freezes the fixture.
The slice-1b "2/5 exact" claim is **stale/unreproducible** and is not cited as progress here.

## 4. Architecture — module layout (`uedcli/`, model-side)

| Module | Deliv. | Owns | Key |
|---|---|---|---|
| `bsp/editorlog.py` | **D0** | drive `MAP REBUILD`, parse drop-warnings → drop **counts + per-class detail** (NO face identity) + the count-level measurement | `parse_build_log(text)→BuildLog`, `capture_build_log(driver)→BuildLog`, `measure_build_emergent(maps)` (names match the built spike; do NOT rename) |
| `bsp/model.py` | D1 | the built `Model` (**frozen, kw-only**) | `Node`/`Surf`/`Vector`/`Point`/**`Vert`** (the `iVertPool` FVert array — where node edge geometry lives)/`Leaf`/`Zone`/`Model` |
| `bsp/umodel_read.py` | D1* | binary `UModel` parser (conditional on P0-a) | `parse_model(dx_bytes) -> Model \| UModelParseError` |
| `bsp/report.py` | D1 | **located-issue** analysis over a built `Model` | `analyze_built(model) -> list[Finding]`: T-junction/HoM cracks (edge adjacency reconstructed from `Nodes[].iVertPool`→`Vert`→`Point`/`Vector`), phantom/sliver invisible-wall nodes, fall-through (**built floor surf whose `PolyFlags` carry `PF_NotSolid/Semisolid/Portal`** — NOT a "collision probe"; collision+rendering share nodes, §3a), leaf/zone summary — NO authored-vs-built *absence* diff (that's D0/D2) |
| `bsp/fpoly.py` | D2 | frozen `FPoly` + survival/split (+ crash fork) | `fix`,`remove_colinears`,`calc_normal`,`finalize`,`split_with_plane`,`split_with_plane_fast` |
| `bsp/f32.py` | D2 | float32-faithful arithmetic | `f32`,`f32_dot`,`f32_plane_dot` |
| `bsp/csg.py` | D2 | `bspBrushCSG` + leaf-filter + solidity classes | `brush_csg`, `_filter_world_through_brush` |
| `bsp/build.py` | D2 | `bspBuild`/`SplitPolyList`/`FindBestSplit`/`bspAddNode` | … |
| `bsp/passes.py` | D2 | cleanup (`build_bounds`=collision hulls) | `merge_coplanars`,`opt_geom`,`refresh`,`build_bounds` |
| `bsp/portal.py` | D2 | portalize + leaf/zone + model-side collision probe | `portalize`,`line_check`,`point_check` |
| `bsp/rebuild.py` | D2 | top-level `csgRebuild` | `rebuild(brushes,*,balance,portal_bias,optimization) -> BuildResult` |

*(Module table: the `Deliv.` column gates scope — only the **D0** row is near-term; **D1** rows are
gated on the P0 spike; all **D2** rows are deferred design, not plan steps.)*

**Result types (errors-as-values; all frozen kw-only).** *(Only D0's `BuildLog` is near-term; the D1
`Model`/parse types and the D2 `BuildResult`/`DroppedFace`/`Optimization` contract are deferred
design — listed here so the contract is recorded, NOT to be built near-term.)*
- D0: `capture_build_log()/parse_build_log() -> BuildLog` (the built spike's type — counts +
  per-class detail, no identity). Errors → a clean `EditorError` value, never an exception.
- D1: `parse_model(bytes) -> Model | UModelParseError`. `analyze_built() -> list[Finding]`.
- D2: `rebuild() -> BuildResult` where **`BuildResult = BuiltOk | WouldCrashCsg`** (an
  errors-as-values union, matched with `match`): `BuiltOk(model: Model, dropped: tuple[DroppedFace,
  ...])` or `WouldCrashCsg(brush: str, reason: str, coord: Vec3)` (no model — the Critical-Error fork
  aborts). **`DroppedFace(brush: str, poly: int, reason: str, coord: Vec3)`** — its identity is used
  D2-internally and for the count-gate only, NEVER matched per-face against D0 (which has no
  identity). (Rejected: exception/None for the crash fork — loses the "which brush GPFs" payload.)
- **`class Optimization(enum.IntEnum): LAME=0; GOOD=1; OPTIMAL=2`** — the *values* are load-bearing
  (they index `FindBestSplit`'s `Inc` = N/4 / N/10 / 1; partition spike).

**Build params** required on `find_best_split`/`split_poly_list`; only `rebuild()` defaults to
Balance=50/PortalBias=70/`Optimization.OPTIMAL`. The spike `balance=15` default is a bug.

**CLI surface (resolves the editor-dependence ladder — R2-C1/C2).** Three tiers, three
editor-dependence profiles — stated loudly so users aren't surprised:
- **`level doctor`** (shipped, static) — **no editor**, per-brush prediction. Unchanged; its
  `Finding`/severity/exit-code model is the template the others reuse.
- **`level doctor --rebuilt`** (D0) — **drives the editor** (`MAP REBUILD` on the session level or
  `--dx <path>`) and reports the drop-warning counts. Emits **brush-less `Finding`s** (`brush=None`,
  `coord=None`) — per-channel severity: zero-area / not-enough-verts / not-watertight → ERROR;
  unlinked-T-points / infinitesimal-node → WARN. Exit non-zero on any ERROR (CI tripwire). **Not**
  on the editor-free `level doctor` path — it's a distinct editor-driving verb.
- **`level doctor --built --dx <path>`** (D1) — parses a **saved, already-built** `.dx` (no rebuild,
  no editor at analysis time) and reports *located* `Finding`s (with `coord`). Takes an explicit
  `--dx` (it does not read `main/`; it needs a built artifact). Conditional on P0-a/P0-b1.
- (`level doctor --deep` (D2) — the deferred fully-offline engine.)

**Performance (D2 strategy gate).** `FindBestSplit` O(n²)/node; a real map (~10⁴ post-CSG `FPoly`s) is
**plausibly minutes–hours** in pure Python (editor: ~1 s in C++). D2's first slice produces a
back-of-envelope on a **real map's** FPoly count; a bad number makes `--deep` **batch/CI, not
interactive** (stated as such). Per-zone bounding is **circular** for a first full build; `numpy`
buys ~5–20×, not the 100×+ needed — don't assume it rescues interactivity. (D0/D1 are
O(file/log), fast.)

## 5. The accuracy gate — precise + bounded

Per-face product → compare **face/structure identity**, not scalar counts.

1. **Tier-C — counts (internal smoke; NEVER a correctness gate, including the kill criterion).**
   Equal counts ≠ equal geometry. A cheap regression signal during D2 dev only.
2. **Tier-S — surf/face identity (THE ship gate for any hole/absence claim).** Diff two keyed sets
   vs the editor's truth (D0 drop-warnings for the dropped set; the parsed `Model` for the surf set):
   - **Surf key** = (plane, signed-normal winding, cleaned vertex-coord set). **Plane equality:**
     normals within `THRESH_NORMALS_ARE_SAME=2e-5`, offset `w` within `THRESH_POINTS_ARE_SAME=0.002`
     (engine constants). Winding is in the key (signed normal) — a face vs its flip are distinct (the
     invisible-wall bug). **Texture vectors excluded** (recomputed floats; hole detection doesn't
     need them).
   - **Dropped faces — COUNT-level only** (D0 carries no `(brush, poly)` identity, R1-C1). D2 infers
     its own dropped set (authored faces with no matching built surf); the editor side is **D0's
     total drop count**, so the gate is "D2's dropped-count == D0's confessed drop count" (a strong
     but not per-face check — per-face dropped identity is genuinely unavailable from the editor, so
     it is explicitly **not** part of the gate). The *surf* set (above) is the per-face check.
   - *Pass* = the surf sets match exactly **and** the drop counts match.
3. **Tier-K — collision (structural + known-answer; NO live trace oracle exists).** Editor side = the
   parsed leaf/zone structure (D1) + leaf/zone counts (D0); model-side `line_check`/`point_check`
   validated against **hand-authored known-answer probes** on constructed phantom/missing-node cases.
   "Leaf parity is a corollary of build parity" is a **hypothesis** these probes confirm.

**Bounded ship bar (D2).** `--deep` ships when **Tier-S is exact on a FROZEN discriminating corpus**
(convex, off-grid, semisolid, portal, merge-active, degenerate — fix the size once at **10 cases**),
each captured **≥3× cross-container and asserted byte-stable** before freezing (§7). Real-map
behavior is reported with a **per-finding `confidence` (`verified`|`heuristic`)** and does **NOT**
gate the ship (this removes the unbounded "classify every real-map diff" obligation review flagged):
a real-map diff surfaces as a `heuristic` finding, not a release blocker. **Accuracy floor:** a
`--deep` run is labelled "verified" only if **100% of its findings on that map are Tier-S-backed**;
otherwise it self-labels "advisory" — so `confidence` can't be a fig leaf for "doesn't work."

**Kill criterion.** If D2's first slice is not **Tier-S-exact on the convex+off-grid corpus subset**
(not Tier-C — counts can't verify correctness) within a fixed effort box, **stop D2; D0+D1 remain
the shipped deliverables.**

## 6. Sequencing

> **WHAT THE NEAR-TERM PLAN ACTUALLY BUILDS (read first — the rest of §6 is the deferred design,
> not the plan).** The plan covers exactly: **(1)** promote D0's validated parser+capture to
> `uedcli/bsp/editorlog.py` with golden tests (schema-stable; safe regardless of D1); **(2)** the
> **P0-a/P0-b1 feasibility spike** (one session — decides whether D1 is real); **(3)** *then* design
> and wire the `level doctor` verb surface **once**, knowing whether it's one tier (D0) or two
> (D0+D1); **(4)** D0-b, the measurement. **D1-b and every D2 slice are OUT of the near-term plan**
> — they are the deferred design below. Do NOT plan the D2 slices.

**Step ordering rationale (review-set R3):** promote the parser BEFORE wiring the CLI verb, because
the `level doctor` `Finding` schema + tier set are **shared** and D1's existence changes them
(coords? a second verb?). Run the one-session P0 spike between, so the verb is designed once against
a known answer — not built for D0 then reshaped for D1.

**D0 — DONE + validated** (`spikes/…-d0-editorlog.md`); `bsp_editorlog.parse_build_log`/
`capture_build_log` yield drop **counts + per-class detail**, **no brush/poly identity** (R1-C1).
- **D0-a (plan step 1)** — promote `_scratch/bspspike/bsp_editorlog.py` → `uedcli/bsp/editorlog.py`
  (parser+capture only — **schema-stable**); golden tests on synthetic logs + one integration test.
  Wiring the `--rebuilt` verb is **deferred to plan step 3** (after the P0 spike answers the tier
  question). `measure_build_emergent` is **NEW** (D0-b), not yet in the spike.
- **D0-b (plan step 4) — the measurement, reframed (R3): it gates D1's *value*, NOT D2's.** Run D0
  over the gitignored real DeusEx maps; report per map the drop counts + how many the static `doctor`
  already predicted (`degenerate`/`watertight` ERRORs — both categories exist in the shipped
  `doctor`). The **excess of confessed build-emergent drops over what the static tier predicts** tells
  us whether *located* detection (D1) is worth building — it is a fuzzy upper bound (D0 has no
  identity to confirm overlap, so it can over/under-count). **It does NOT gate D2:** D2's
  differentiator is *silent-absence* holes, which are **unmeasurable offline by construction**
  (they're silent). **So D2's go/no-go is an explicit judgment call, not a measurement** — state that
  plainly; don't promise a measurement that can't exist.

**D1 (deferred design — UNBUILT; gated on the P0 spike at plan step 2).**
- **P0-a — `UModel`-parse feasibility.** Parse the built `Model` from a saved `.dx`. **Minimum "go" =
  `Surfs` (incl. `PolyFlags`) + `Vectors` + `Points` + the `Vert`/`iVertPool` array AND `Nodes` +
  `Leaves`.** RE from `UModel::Serialize`/`FBspNode<<`/`FBspSurf<<` (the `pefile`/`capstone` harness)
  + a `.dx` hexdump; version-61 wrinkle. **New** parsing, NOT `dxpkg` reuse. **Time box: 1 session.**
- **P0-b1 — adjacency (spike WITH P0-a). Expected to FAIL for located-HoM (R3 — pre-concluded).** A
  T-junction edge would come from `Nodes[].iVertPool`→`Vert`→`Point`/`Vector`, but **both outcomes
  collapse D1's located-HoM value:** if `bspOptGeom` *linked* the T-junction it's gone from the built
  model; if it *failed* to link, that's already D0's T-points count. So **plan on D1's located-HoM
  row degrading to a D0 count**; P0-b1 only confirms. **D1's genuinely-viable rows need only P0-a:**
  invisible walls (near-zero-area nodes) and fall-through (built floor surf with
  `PF_NotSolid/Semisolid/Portal`). Distinguish these from the doomed HoM row when scoping D1.
- **D1-b** — `umodel_read.parse_model` + `report.analyze_built`: T-junction/HoM cracks (edge
  adjacency, *if P0-b1*), invisible-wall phantom/sliver nodes, fall-through (built floor surf with
  `PF_NotSolid/Semisolid/Portal`; *missing-node* floor = absence → D0/D2), leaf/zone summary. **No
  authored-vs-built absence diff** (that's D0/D2). Ship as `level doctor --built`. **D0+D1 = covers
  every class but silent-absence** (§1 table).

**D2 (the fully-offline engine; OPTIONAL UPGRADE — retained in full; DEFERRED — NOT in the near-term
plan; built only on an explicit owner judgment call, then behind the §5 budgeted Tier-S bar).** The
following S-* slices are the deferred design, not plan steps. S-1a faithful CSG leaf-filter
(`0x32bf0`) + fix `split()` + decode `0x336d2` + pin the metric + the perf back-of-envelope; S-1b
faithful `SplitPolyList`/`bspAddNode` (+ an off-grid case exercising `f32_plane_dot`); S-2 solidity
classes (+ semisolid/portal cases; until then `--deep` refuses such maps); S-3 cleanup passes
(replace the placeholder; + a merge-active case); S-4 Tier-S wiring (uses D1's parser as oracle) + an
early Tier-K probe; S-5 portalize/leaf-zone + the Tier-K battery; S-6 float32 breadth + a degenerate
case (oracle = a captured `Critical Error`, validating `WouldCrashCsg` + harness crash-recovery);
S-7 meet the **bounded ship bar** → promote `_scratch/bspspike/` → `uedcli/bsp/` (whole package, with
goldens) → wire `--deep` (gated on **Tier-S**). Each slice's gate is **Tier-S on its corpus subset**,
never Tier-C.

**Stale-string cleanup (do on D0/D1 landing):** `doctor.py`'s `_FOOTER`/docstring say "Phase 2" — a
now-stale label; update them to point at `--built`/`--deep` (the repo's no-stale-doc rule). Avoid
user-visible phase numbers; "D0/D1/D2" are spec-internal.

## 7. Verification & testing

- **Offline golden tests** (committed; CI gate): freeze corpus geometry + the editor's captured
  Tier-S surf sets / D0 drop sets as a tracked fixture; assert reproduction. Mirror the existing
  **`test_builder_parity.py` golden + `_capture` (integration re-bless)** template. Names
  `test_it_<verb>_<scenario>`.
- **Oracle determinism (before freezing anything):** capture each case **≥3× in independent fresh
  editors**, assert **byte-stable**; exclude any unstable field as known-noise (like
  `normalize.COMPUTED_PROPS`) with a documented reason. The fixture **records the substrate/image
  id**; re-bless asserts the live capture still matches.
- **Integration-gated live differential** (`-m integration`, deselected): fresh ephemeral editors per
  `parallel-editors.md` (fresh container+volume, poll ready, settle, **tear down in `finally`**,
  never touch standing containers, cap concurrency, hard timeouts, dismiss the GC dialog, **EDIT
  PASTE** for brushes). `Editor.log` is 4 KB-buffered → a missing count/warning is a **hard
  failure**, never a pass.
- **Crash-tolerant capture (named invariant):** per-case incremental checkpointing; on a crash
  `--force-recreate`, **retry N times**, resume skipping captured cases, mark un-blessable cases. A
  case whose oracle outcome *is* a crash records `Critical Error`.

## 8. Open questions / risks (ranked; flag for Andrzej)

1. **Runtime-fully-offline (D2) — RESOLVED (Andrzej): build D0+D1 now; D2 deferred TODO.** D0+D1
   covers every class but silent-absence; D2 adds only "never run the editor" + silent-absence.
2. **D1 is UNBUILT and its located coverage is the load-bearing risk** — gated on P0-a (`UModel`
   parse) + P0-b1 (arrays retain T-junction adjacency). If either fails, HoM/walls/fall-through
   degrade to D0's existence counts. *The "D0+D1 covers everything but silent-absence" claim assumes
   P0-a/P0-b1 hold — the biggest near-term unknown.*
3. **D0-b measurement** — how common are silent-absence holes (the only class D0+D1 miss)? Cheap;
   gates whether D2 is ever worth building. Note it's a **count-level** upper bound (D0 has no
   identity), not a per-face classification.
4. **D2 current parity is 1/5, not "mechanical volume yet."** The committed `corpus_result.json` is
   exact only on `single_box` (no real splits); the port **regressed** from the slice-1b narrative
   and its `merge_coplanars`/`*_nodes` are count-fitting placeholders. D2/S-1 must **re-pin the metric
   + re-freeze the fixture first**, then the leaf-filter/`SplitPolyList` ports — "located gaps,
   mechanical" only holds after the re-pin. Risk #1 if D2 proceeds; budgeted, Tier-S kill criterion.
5. **D2 performance** — minutes–hours likely (unmeasured back-of-envelope, S-1); go/no-go on
   interactive framing.
6. **Float32-faithfulness is a designed-for property, not yet established** — no off-grid/boundary
   case has been run (the ±0.25-band open/closed convention at exactly ±T is unpinned); it's gated
   on the S-1b off-grid corpus case, not proven.
7. **Oracle determinism** — proven (§7, ≥3× byte-stable) before freezing. **D0 reliability** —
   channel-flush-dependent; high-recall union, not provably complete (R1-I1).
8. **Solidity/portal faithfulness (D2/S-2)**; **movers** out of scope (said loudly in output).

## 9. Decisions captured (cross-ref `decisions.md`)

Direction: `decisions.md` 08:50 (static-first) + 09:07 (offline-faithful-port + editor-as-oracle +
"diff every node/surf/vertex / 0 face-collision diffs"). **This spec materially revises 09:07 and
those revisions need their own ledger entry (with rejected alternatives) on sign-off — named
explicitly:**
- **RESOLVED (Andrzej): build D0+D1 (covers every class but silent-absence; D1 gated on P0-a/P0-b1)
  to BUILD; D2 (fully-offline) is an OPTIONAL
  upgrade, retained fully-specced.** This revises 09:07's "fully offline" framing — completeness now
  comes from D0+D1 on the real editor build (one editor run), not from the multi-week port; D2's only
  added value is removing that run + rare silent-absence holes. *The most consequential revision —
  log it.*
- **Reading the built model LOCATES the present/structural issues (HoM/T-junctions, invisible walls,
  fall-through) — NOT just "presence-side small prize."** D1 is co-equal with D0; only *pure
  dropped-face absence* needs D0's warnings or D2. (Corrects an earlier draft that undersold D1.)
- **Tier-S (per-face identity) is the D2 ship gate; the 09:07 "0 diffs on the corpus" is implemented
  as Tier-S-exact-on-a-frozen-corpus + real-map findings carried as `heuristic` confidence (NOT a
  ship blocker)** — a bounded bar, with the unbounded "classify every diff" obligation removed.
- **`BuildResult` sum type** (`BuiltOk`|`WouldCrashCsg`), **Tier-S key** (signed-normal winding;
  texvecs excluded; 2e-5/0.002 tolerances), and the **`balance=15`→required-params** fix are
  load-bearing API/semantic choices — fold into the same entry.

Everything else (module layout, slice order, corpus size) is plan detail. Until Andrzej signs off,
all of the above are proposals in this (ephemeral) spec.
