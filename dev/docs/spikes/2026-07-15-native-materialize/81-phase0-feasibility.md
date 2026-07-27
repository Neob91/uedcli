# 81 — Phase-0 feasibility: is a byte-identical native `.dx` reachable? — 2026-07-17

**Status:** Phase-0 (decode + feasibility) COMPLETE. **Verdict: GO** (literal `UModel`-body +
name/import/export-table byte-identity is reachable for the castle; GUID/timestamps excluded).
Instruction-level evidence: `re-raw-zones/fp-classification-sites.md`,
`re-raw-zones/bspbuild-splitpolylist-decode.md`, `41-fp-model-x87-vs-sse.md`, `42-bspoptgeom-decode.md`.
Confidence legend: ✅ uedcli-used/live-verified · 🔬 live-probed (disassembly) · 📖 binary-extracted.

This section converts the four Phase-0 unknowns in board item `native-bsp-exact-topology-parity-byte-identical`, §Phase 0, into
verdicts. It does NOT start the port.

---

## 0. TL;DR — the four gates

| Gate | Question | Verdict |
|---|---|---|
| **1 Input identity** | Does the native world-space brush vertex set equal what the editor's `bspBrushCSG` consumes? | **PASS (castle).** All 95 castle brushes are identity-scale / zero-rotation / zero-sheer / zero-prepivot ⇒ world transform is a **pure `v + Location` translation**, bit-trivial in `f32`. Rotated brushes (UNATCO) are a **gated future blocker** (editor `BuildCoords` uses a sine TABLE). 🔬 |
| **2 Per-site FP** | Is the CSG classification/pool hot path SSE-scalar (bit-reachable in Rust `f32`) or x87/rsqrt? | **PASS.** Every classification, split-param division, dedup and surf-normal site is **SSE-scalar** (or f64-`sqrtsd`+f32-`divss`). No x87 on the surf path, no `rsqrt`. 🔬 |
| **3 Editor determinism** | Is the editor's own build reproducible (mask GUID/timestamps)? | **PASS (static).** Deterministic tree-walk + array-append pool emission; no RNG/hash-order/pointer-sort; only GUID+timestamp vary (excluded). Empirical double-build recommended as corroboration, not run (crash-prone editor). 🔬 |
| **4 Four missing decodes** | Pool ORDER, `NumSharedSides`, normal provenance reproducible? | **PASS.** dedup = `FindNearestVertex` (deterministic nearest); `bspRefresh` = reachability-GC compaction; `NumSharedSides` = `bspOptGeom` T-junction tally (serialized field, portable); **normal provenance = PRESERVE authored T3D normal**. 🔬📖 |

---

## 1. Gate 1 — input identity (castle bit-trivial; rotation is the future blocker)

Dumped all brush `actor.t3d` under `_scratch/castle/uedcli/maps/foobar/actors/` (95 brush actors):
- `Rotation=(…)`: **0 brushes** (absent ⇒ zero).
- non-zero `SheerRate`: **0**. `PrePivot=(…)`: **0**. explicit `MainScale`/`PostScale` `Scale=(X..)`
  vector: **0** — every brush's scale block is `(SheerAxis=SHEER_ZX)` ⇒ default identity `(1,1,1)`.
- The only non-trivial per-brush field is `Location`. The diagonal-wall normal
  `(-0.707107,+0.707107,0)` is **baked into the T3D poly data**, not produced by a rotation.

`fpoly.rs::FPoly::transform(rot, prepivot, location)` with `rot = I`, `prepivot = 0` computes
`rx = 1·x + 0·y + 0·z + Location.x`. In `f32`, `0·y` and `0·z` vanish **exactly** and `1·x == x`
exactly, so the result is a single `f32` add `x + Location.x` — associativity-independent and
**bit-identical** to the editor's identity-frame transform. **Castle input identity holds.** ✅(static)

**Rotated-brush blocker (out of castle scope, tracked).** `materialize.py::_build_brush_input`
already **rejects** non-identity `Rotation` with a clear `BuildError` ("not yet supported by the
native transform"). Reproducing rotated input bit-exactly requires porting UnrealEd's
`Actor::BuildCoords` FRotator→matrix, which uses the engine's **`GMath` sine/cosine LOOKUP TABLE**
(`FGlobalMath`), *not* libm `sinf` — so calling `f32::sin` would diverge. This is a real precondition
for UNATCO-class content and is filed in `board/inbox/`; it does not affect the castle GO.

> **UPDATE 2026-07-17 — rotation is now ENABLED (functional).** The rejection is removed.
> `_build_brush_input` builds `R` from the URU Pitch/Yaw/Roll via `rotation.actor_matrix`
> (→ `euler_to_matrix_uu`), which **already reads the ported `GMath` sine table**
> (`rotation.gmath_sin`/`gmath_cos`, `(field>>2)&16383` truncation) — not libm — so the
> "port the table" precondition was already satisfied by `rotation.py`. The convention is the
> editor-verified one from `2026-06-19-frotator-convention.md` (yaw = Rz; pitch/roll sin-flipped;
> compose Rz·Ry·Rx). Verified by `harness/verify_rotated_brush.py`: a native single-box CSG build
> under pure/combined/arbitrary Yaw/Pitch/Roll matches `rotation.world_vertices` exactly (and the
> geometric anchor −90° Yaw sends `+X(256,0,0) → (0,−256,0)`). The full 762-brush UNATCO trunk
> (283 rotated brushes) now materializes to a clean self-checked `.dx`. **Scale is still dropped**
> (identity) — `_build_brush_input` can't read the nested `MainScale=(Scale=(…))` form and the Rust
> rejects a non-identity `scale` tuple, so ~90 UNATCO brushes with a non-1.0 `PostScale` build at
> unit size (boarded; functional-pass gap). Byte-identity of `euler_to_matrix_uu` vs `BuildCoords`
> remains folded into the `bspcsg` port, not a functional blocker.

## 2. Gate 2 — per-site FP (the crux): SSE-scalar throughout

Full per-site table + disassembly excerpts: **`re-raw-zones/fp-classification-sites.md`**. Summary:

- **Build provenance settled:** the UED22 DLLs are a **2022 MSVC/VS2022 rebuild** (linker 14.32,
  TS 2022-10-29), and the container that builds the golden ships the **MD5-identical** binaries.
  32-bit MSVC ⇒ `/arch:SSE2` ⇒ true-32-bit scalar float, no 80-bit x87 intermediates. This
  **overturns the reviewer's "1999 MSVC6/x87" premise** — the observed `movss/mulss/…` are the
  compiler's default scalar codegen, not localized FVector intrinsics.
- **Classification** (`SplitWithPlane`/`SplitWithPlaneFast`/`PlaneDot`, the ±0.25 band): SSE-scalar
  `subss/mulss/addss` + `comiss`. 🔬
- **Split vertex** (`t = num/den`, `P = A + t·(B−A)`): **`divss`** + `mulss/addss` — IEEE division,
  == Rust `f32/f32`. Stored verbatim as `f32`. 🔬
- **Surf normal** (`CalcNormal`→`NormalizeSlow`): `|n|²` f32 → `sqrtsd` f64 → f32 → `1.0f/s` `divss`.
  **No `rsqrt`, no x87.** Reproducible as `(sumsq as f64).sqrt() as f32` reciprocal. 🔬
- **Pool dedup** (`bspAddPoint`→`FindNearestVertex`): SSE squared-distance, thresh `0.002`. 🔬
- **`FindBestSplit` score:** integer-dominant + `PortalBias/100.0` via `divss`; no x87. 🔬
- **Only x87 site near geometry:** `FVector::Normalize` (core `0x24940`) uses an x87 `fdivrp`
  reciprocal — **but `CalcNormal` does not call it** (it calls `NormalizeSlow`). Residual: xref during
  the port to confirm no CSG-build caller reaches `0x24940`; the Tier-S differential catches it if so.

**Consequence:** literal bit-exact `f32` parity is reachable. The remaining work is **operation-ORDER
fidelity** (match `PlaneDot`'s pairwise horizontal reduction and each dot's left-to-right shape),
proven per-site by a differential trace — an engineering task, not a precision-emulation problem.

## 3. Gate 3 — editor determinism (static PASS)

The build emits the pool/nodes by a deterministic BSP tree-walk with array appends; `FindBestSplit`
is min-score-with-first-tie-break; `FindNearestVertex` returns the unique nearest point; `bspRefresh`
compacts by a fixed reachability DFS. No RNG, no hash-map iteration order, no pointer-address
ordering, no uninitialized-slack serialization (arrays serialize by `.Num`). The **only** per-save
non-determinism is the package **GUID** (`appCreateGuid`, random 16 bytes at file offset 36, not
echoed elsewhere) and the **TimeDateStamp** — both **excluded from scope**. Therefore editor-vs-editor
byte-identity of `UModel` body + tables holds by construction. Empirical double-build (mask the GUID)
recommended as corroboration; not run to avoid the crash-prone editor eating the spike budget.
See `re-raw-zones/fp-classification-sites.md §Editor determinism`.

## 4. Gate 4 — the four missing decodes

- **(a) `bspAddPoint`/`bspAddVector` dedup MECHANISM** — `UModel::FindNearestVertex` (Engine
  `0x1adeb0`), a **recursive BSP descent** (by `PlaneDot` sign): descent pruning is on **squared**
  distances, and the winning candidate's returned distance is `appSqrt`'d (core `0x31720`, `sqrtsd`
  f64→f32) so the accept test is `real_dist ≤ thresh` (`0.002` worldspace / `0.015` local — a real,
  non-squared distance); the **nearest** point wins; new points appended by array `Add`. **Not** a
  flat linear scan and **not** a separate spatial hash. (Port note: apply f64-sqrt before the
  threshold compare — don't compare a squared distance to a squared threshold.) The
  Points/Vectors ORDER is a pure function of node-emission order ⇒ Phase-B byte-identity is gated on
  Phase-A node order + these thresholds. 🔬 (`fp-classification-sites.md §7`.)
- **(b) `bspRefresh` (`0x36cd0`)** — dead-node/surf GC: `MarkReachable` DFS from node 0
  (`+0x20/+0x24` children, `+0x28` coplanar chain), then **compacts** `Nodes`/`Surfs`/`Verts`/
  `Vectors`/`Points`, dropping unreachable and remapping indices. The pool **survives and compacts**
  deterministically; a `SplitPolyList`-produced node is always reachable so it is kept. 📖 (decoded in
  `42-bspoptgeom-decode.md §2`.)
- **(c) `NumSharedSides`** (`UModel+0xfc`; castle = 2739; native emits 0) — produced by `bspOptGeom`
  (`0x36870`): reserves side ids 0–3, then walks shared T-junction edges assigning `FVert.iSide` and
  bumping `NumSharedSides++` per new shared side. A **serialized field**; reproducible once
  `bspOptGeom` is ported (or emitted as `iSide=-1`/`NumSharedSides=4` first-cut, which is NOT
  byte-identical). 📖 (`42-bspoptgeom-decode.md §1`.)
- **(d) normal provenance** — **PRESERVE.** `FPoly::Finalize` (Engine `0x150ac0`) keeps the authored
  T3D `Normal` byte-for-byte whenever it is non-zero; it recomputes via `CalcNormal` **only** for a
  zero normal. So the surf `vNormal` is the parsed `0.707107`, not a recomputed `0.70710677`; the
  native `FPoly::new` already preserves it. Same rule for `pBase`/`vTextureU`/`vTextureV`. 🔬
  (`fp-classification-sites.md §Normal provenance`.)

---

## 5. GO / NO-GO / CANONICALIZE verdict

**GO — literal byte-identity is reachable** for the castle-class trunk, at the scope *`UModel` body
+ Name/Import/Export tables identical, GUID + timestamps excluded* (Q1). Every precondition holds:

1. Input identity holds bit-exactly (castle = pure translation). ✅(static)
2. All classification-path FP sites are SSE-scalar / f64-sqrt-f32-recip — no x87, no rsqrt on the
   surf path. ✅🔬
3. Pool ORDER (`FindNearestVertex` nearest), `NumSharedSides` (`bspOptGeom`), and normal provenance
   (PRESERVE) are all reproducible. ✅🔬📖
4. Editor build is deterministic modulo the excluded GUID/timestamp. ✅(static)

**The reachability is a FEASIBILITY verdict, not an achievement.** GO means "no known wall makes
byte-identity impossible", so the expensive port is justified. Achievement still requires the port to
(a) reproduce the incremental `bspBrushCSG` topology (the coupled node+pool milestone — see spec §3),
and (b) match each dot/normalize's **operation order** bit-for-bit, proven by the Tier-S differential.

**When CANONICALIZE would apply (it does not, here).** If a *classification-affecting* site had been
x87/rsqrt-bound and unemulatable, a 1-ULP split vertex could flip a `bspAddPoint` dedup or reclassify
a poly — a topology cliff a snap pass cannot fix — so the honest fallback would be "abandon literal
byte-identity, keep structural + functional parity", NOT a snap. No such site was found on the surf
path, so this fallback is not triggered for the castle.

**Residual open items (do not block GO; tracked in `board/inbox/`):**
- Rotated-brush input identity (sine-table `BuildCoords`) — precondition for UNATCO-class content.
- xref `FVector::Normalize` (core `0x24940`, x87 reciprocal) against the CSG-build call graph.
- Empirical editor double-build (GUID-masked) as determinism corroboration.
- `FindBestSplit` full score-loop op-order and `bspMergeCoplanars` (`0x36200`) instruction decode —
  needed for the port, not for the GO verdict (spec §Phase 0 item 1 residuals).
