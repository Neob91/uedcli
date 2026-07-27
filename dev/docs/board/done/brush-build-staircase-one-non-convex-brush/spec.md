# Spec: `brush build` emits ONE brush actor + `doctor` T-junction-aware watertight

**Status:** ephemeral design scratch. The durable record of what gets built lands in
`architecture.md` (builder module + doctor) and `docs/usage.md`; the load-bearing *choice* + rejected
alternatives live in `decisions.md` **2026-07-21 12:06 UTC** (linked). Stale once implemented.

**Board:** `to-spec.md` `[spec] p2` "brush build should emit ONE brush actor". Reverses `decisions.md`
2026-07-18 20:09 UTC (box-per-step).

**Revised 2026-07-21 after the two-reviewer gate.** Both cold reviewers converged: A1 (staircase
geometry) is sound and matches the pinned UED `Brush5` face taxonomy; Part B had two real defects
(branch precedence, inadequate anti-masking tests); the native CSG core assumes convex brushes; and
the **spiral (formerly A2) is scope creep and is split out** (see below). This spec now covers the
**staircase + the doctor rework only** — the clean, offline-verifiable half.

---

## Scope decision (post-review): staircase + doctor here; SPIRAL split out

Per both reviewers, the spiral redo is **removed from this spec** and tracked as its own `[spec]`/
`[spike]` (board item re-opened). Rationale: the spiral is net-new geometry (wedge treads + central
column), carries an **undiagnosed** defect (the 2026-07-21 mirrored-V — geometry bug at
`builders.py:340` vs a preview artifact, unresolved), its rotated non-axis-planar faces raise a live
CSG-validity question entangled with the native-convex-assumption break (below), and its parity
golden needs a live editor. Folding all that in endangers the clean staircase+doctor change.

The `decisions.md` 2026-07-21 direction ("all multi-brush builders emit one brush") **still holds** —
the spiral WILL become one brush; it just gets its own design pass. **This spec's changes must not
block on the spiral, and A1 must not depend on it.**

---

## Problem / goal

`brush build staircase` currently emits **one brush ACTOR per step** — `builders.staircase` returns a
`list[Brush]` (one convex box per step; `builders.py:295`), which `dispatch.py:2671` wraps into N
actors. A 10-step staircase is 10 actors. **Goal:** emit **ONE brush actor** carrying the whole
staircase.

Box-per-step was chosen (2026-07-18) so each box is a clean convex solid and `level doctor` reports
zero findings. A single brush reintroduces **T-junctions** that the static `watertight` check
false-flags as "open edge" holes (~60 on a staircase). Per Andrzej this is fixed **properly, in the
same spec**, by making the watertight check T-junction-aware.

## Decision summary (full rationale in `decisions.md` 2026-07-21 12:06 UTC)

- `builders.staircase` returns a single non-convex `Brush`; the CLI already emits one actor for a
  single `Brush` (`dispatch.py:2678`), so the plumbing change is minimal (A3).
- Faces stay **convex** — tiled per-step convex side strips, NOT one non-convex stepped side face (a
  non-convex FPoly is a genuine CSG defect; `check_convex` is correct to reject it).
- The resulting T-junctions are handled by a T-junction-aware `watertight` check (Part B), not by
  decomposition.
- Keep the 2026-07-18 floor-anchoring (first tread at `z=rise`, whole solid at/above `z=0`).

---

## Part A — `builders.staircase` returns a single `Brush`

### A1. Geometry (reviewer-confirmed sound; matches the UED `Brush5` face taxonomy `2 + 4n`)

Return **one non-convex `Brush`** = the UED-faithful stepped-wedge outer hull (the CSG union of
today's filled-column boxes, emitted as one brush with only the OUTER faces):

- **Base** (`-Z`): one quad on the floor, `X∈[0, steps*depth] × Y∈[0, breadth]` at `z=0`.
- **back** (`+X`): one full-height quad at `x=steps*depth`, `Z∈[0, steps*rise]`.
- Per step `k` (`0..steps-1`): a **Step** tread quad (`+Z` at `z=(k+1)*rise`) and a **Rise** riser
  quad (`-X` at `x=k*depth`, `Z∈[k*rise,(k+1)*rise]`). First tread at `z=rise` (climb one riser onto
  step 0).
- **Side** (`±Y`): the stepped silhouette on each side, **tiled into per-step convex quads** (one
  rectangle per step column, `X∈[k*depth,(k+1)*depth] × Z∈[0,(k+1)*rise]`) — NOT a single non-convex
  polygon.

Face count: Base 1 + back 1 + Step n + Rise n + Side 2n = **`2 + 4n`**, which is exactly the pinned
`LinearStairBuilder` taxonomy asserted over `Brush5` (`test_builders.py:214`
`test_ued_linear_stair_reference_is_one_nonconvex_brush`). **Strengthen that test** into a
builder-vs-UED *equivalence* assertion (the new single-brush output should now match the fixture
taxonomy), not a passive engine-fact note. Build every face through `_face(ring, outward, …)` (Newell
flip, CCW-from-outside), keep the `Step`/`Rise`/`back`/`Side`/`Base` ItemName vocabulary.

The T-junctions live where a Side strip's boundary meets the tread/riser/base edges (strip `k`
shorter than strip `k+1`; the base's long edge opposed by the collinear chain of strip-bottom edges).

### A2. Native CSG blast radius (was missing — reviewer HIGH)

A single non-convex brush is mis-handled by the **native** CSG core, which assumes convexity:
`uedcli-native/src/csg.rs:60` `point_in_convex` tests "behind every face" (the convex hull, not the
true solid), and `bspcsg.rs:1866` documents a convex-only world seed. A stepped brush's concave
notches would classify as solid → the profile mis-builds/fills. Affected paths: `level preview
--native` (`preview_native.py:366`) and native `level materialize` (default `bspcsg` core).

**This is acceptable and confined**, but must be written down (not silent):
- The **default** `level materialize` drives **UnrealEd**, which builds this non-convex brush
  natively — it is literally `LinearStairBuilder`'s own output — so the default build is correct.
- The **default** `level preview --game` renders in the real engine — correct.
- Only the **native/experimental** paths (`--native`, native materialize) mis-build it; this joins
  the already-documented ~11% native solidity divergence on "walls/steps" (`architecture.md:1141`).

**Actions:** add a note to `decisions.md`/`architecture.md` that the `csg.rs:61` "DX brush builders
emit convex brushes, so this is exact" invariant is now **falsified** for builder output, with a
follow-up board item to decompose non-convex brushes into convex pieces on the native path (or guard
+ warn). **Validation of A1 uses `brush preview` (the `preview.py` WIREFRAME renderer — convex-
agnostic, a valid check), NOT `level preview --native`** (the convex-broken Rust rasterizer).

### A3. Dispatch — KEEP the multi-actor branch (spiral still uses it)

`_build_brushes` returning a single `Brush` already routes to the single-actor path
(`dispatch.py:2678`), naming the actor `Staircase` (or `--base-name`) — that's all `staircase` needs.
**⚠ Correction (2026-07-21, caught at build-planning): do NOT remove the `len(list) > 1` multi-actor
branch (`dispatch.py:2671`).** The earlier "no shape uses it" claim assumed BOTH staircase and spiral
became single-brush, but the **spiral was split out** and `spiral_staircase` STILL returns a
`list[Brush]` (one slab per step, len > 1) — so the branch is **still live for spiral**. Removing it
would break `brush build spiral`. The dead-branch removal moves to the **spiral build** (when spiral
also becomes one brush). Update only the stale part of the `_build_brushes` docstring
(`dispatch.py:41-42`) to say "staircase → one brush; spiral → one slab per step" — don't delete the
branch.

---

## Part B — `level doctor` watertight becomes T-junction-aware

**Only `check_watertight` changes** (`doctor.py:242`). The other five checks (`degenerate`, `convex`,
`solidity`, `csg_order`, `scale`) are orthogonal to T-junctions and stay exactly as they are.
`_is_closed_solid_brush` (`doctor.py:113`) already gates the single staircase brush IN (solid
`Engine.Brush`, no `PF_NotSolid/Portal`), so the rework applies to it as intended.

### B1. Why the current check false-flags

`check_watertight` welds vertices, keys each undirected edge by its welded corner **pair**
(`doctor.py:261`, exact Decimal — no tolerance), and flags an edge used by one face (open), >2
(non-manifold), or twice same-direction (back-wound). A T-junction breaks exact-pair keying: a long
edge `P→Q` shares no key with the collinear chain `P→M→Q`, so all three look "used by one face" →
false "open edge".

### B2. New algorithm — per-edge-line directed-interval parity

Replace exact-pair matching with directed-interval parity along each supporting line:

1. Collect every directed edge `(a→b)` (welded corner coords). **Skip zero-length edges** (`a==b`,
   as `doctor.py:259` does today) so a welded coincident pair doesn't create a zero-width interval.
2. Group edges by their **supporting line** (see B3 for the canonical key + tolerance — this is the
   load-bearing part). Two edges share a line iff collinear and spatially coincident (any
   overlap/offset).
3. Within each line, project endpoints to the line parameter `t`; sign = with (+) / against (−) the
   line's canonical direction. Split at every distinct `t` into atomic sub-intervals.
4. For each atomic sub-interval count forward `f` and backward `b`, and classify **in this
   precedence** (the branches are NOT mutually exclusive — order matters; this fixes the reviewer's
   HIGH branch-precedence defect):
   1. `f == 0 and b == 0` → not on the surface; ignore.
   2. `f + b > 2` → **non-manifold** overlap.
   3. `f + b == 2` **same direction** (`f==2,b==0` or `f==0,b==2`) → **back-wound face**.
   4. `f == 1 and b == 1` → **healthy** (closed seam, T-junction or not) — no finding.
   5. otherwise (any other imbalance, e.g. `1/0`, `2/1` after the above, net flow ≠ 0) → **open edge /
      hole**.

   Checking non-manifold and same-direction *before* the net-flow catch is what keeps a back-wound
   `2/0` from being mislabeled "open edge" — so `test_it_flags_reversed_face_as_winding_error`
   (`test_doctor.py:86`) still passes. Report at the offending sub-interval's coords.

   This subsumes the current three branches (a normal edge = one atomic sub-interval `1/1`) and stays
   silent on T-junctions (`P→Q` forward + `P→M`,`M→Q` backward → every sub-interval `1/1`).

### B3. The canonical line key + tolerance (the real risk — must be specified, not deferred)

Grouping infinite lines under tolerance is the bug-prone core (too-tight bucketing → false "open
edge"; too-loose → **masks** a real hole). Specify concretely:
- **Key:** normalize direction `d = (b−a)`, sign-canonicalize (flip so the first non-zero component is
  positive), then the line's closest point to origin `a − (a·d̂)d̂` — quantize both to a grid tied to
  `WELD` (`builders.py:38`, `1e-3`). Because coords are cleaned to a Decimal grid, axis-aligned
  staircase edges key exactly; the epsilon only matters for slanted/rotated edges.
- **Document the epsilon** and pin it with a regression (below). Note hash-bucketing under tolerance
  is non-transitive; use a canonical quantized key (not fuzzy pairwise comparison) so it's a clean
  dict grouping.

### B4. Tests (must prove non-masking — the whole point)

Add (`tests/test_doctor.py` or a new module), and KEEP every existing `check_watertight` test
unchanged (cube, 0.707-fractional box, reversed-face, etc. — the fractional box now also stresses the
new line-canonicalization):
- **Real T-junction, closed → zero findings:** the new single-brush staircase; a minimal hand-built
  T-junction box (one side split, the other not).
- **Anti-masking — the case that actually fails (reviewer HIGH):** a **real open edge whose supporting
  line coincides with a healthy seam** (a hole collinear with an unrelated closed edge, partial `t`
  overlap) → MUST still flag "open edge" on the uncovered sub-segment. This is the test the old
  exact-pair keying couldn't need and the new algorithm can get wrong.
- **Back-wound → still caught** (the `2/0` precedence test), **non-manifold → still caught** (`2/2`).
- **Non-axis-aligned regressions (currently ABSENT):** `cone` and `cylinder` (slanted edges) must
  still report clean — the new float line-grouping could regress them silently; `test_doctor.py` has
  no cone/cylinder watertight case today. Add one each.
- **Epsilon regression** pinning the chosen collinearity/`t` tolerance vs `WELD`.

---

## Goldens & parity harness (reviewer MED — the harness is incompatible, not just the values)

- **Value re-bless:** `stair_*` in `fixtures/builder_parity.json` freezes the multi-box output and
  changes to single-brush. Axis-aligned integer staircase coords reconstruct identically in the
  editor (same basis as `cube_*`), so **offline re-bless is legitimate** (`python -m
  uedcli.tests.builder_parity_cases`).
- **⚠ Live-capture harness incompatibility (must decide):** `builder_parity_cases.py:30-32` captures
  the spiral **per-slab** *because* a combined non-convex cavity makes the editor invent interior
  vertices; `capture_world_verts` reconstructs via `BRUSH FROM DEINTERSECTION` and the `regenerate`
  path refuses to bless on builder/editor disagreement (`:203`). A single non-convex staircase brush
  is exactly that excluded regime, so `test_builder_parity_capture.py` + live re-bless will FAIL on
  `stair_*`. **Confirmed (Andrzej 2026-07-21): drop `stair_*` from the LIVE (editor-driven) parity
  suite** (keep the offline value goldens, which need no editor); a non-convex capture mode is
  separate work. (Byte-identity is trunk-relative, so this doesn't affect the native-parity bar.)

## Breaking tests + docs (part of the change, not follow-ups — reviewer MED)

Tests to rewrite (asserting box-per-step / multi-actor):
- `test_builders.py:151` (returns-one-box-per-step), `:163`, `:182` (disjoint-in-x/stack), `:196`
  (`test_staircase_passes_doctor_clean` — now coupled to Part B; must assert zero findings on the
  single brush via the new check).
- `test_generators.py:81` `test_brush_build_spiral_outputs_n_actors` — **UNCHANGED** (spiral is split
  out and still emits N actors); add a new staircase test asserting ONE actor.
- `test_dispatch.py:384` `test_dispatch_build_staircase_writes_one_actor_per_step` → one actor.

`help=` strings the repo mandates be accurate: `cli.py:681` "one brush per step" (staircase), and
verify `:595/:601` `--at` per-step-index notes.

Docs: `docs/usage.md` (`brush build staircase` → one actor named `Staircase`/`--base-name`; per-face
addressing via `brush poly`; the native-path caveat), `docs/leveldesign/`, `architecture.md` (single
non-convex brush; tiled convex sides; interval-parity watertight; the falsified `csg.rs:61` invariant
+ native blast radius), `decisions.md` (native-convex caveat + spiral-split addendum).

## Out of scope

- The **spiral** redo (split to its own `[spec]`/`[spike]` — see Scope decision).
- Real build-emergent **T-junction crack** detection (deferred to the Phase-2 offline BSP engine,
  `to-build.md` #7). This spec only stops the STATIC check from false-flagging a closed brush.
- Fixing the native CSG core's convex assumption (its own board follow-up).

## Open questions

1. ~~Remove the dead dispatch branch?~~ **Reversed (2026-07-21): do NOT remove — spiral still returns
   `list[Brush]`>1, so the branch stays live until the spiral build. Removal deferred to the spiral.**
2. ~~Drop `stair_*` from live parity?~~ **Resolved (Andrzej 2026-07-21): drop from the live suite;
   keep the offline value goldens.**
3. Native-convex-assumption fix — scope the follow-up board item (decompose-to-convex vs guard+warn).
   Tracked as an `inbox.md` `[implement]` item.
