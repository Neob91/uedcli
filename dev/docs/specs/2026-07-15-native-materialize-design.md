# Native `level materialize` — full offline `.dx` build WITHOUT UnrealEd (design spec)

**Status:** spec (ephemeral — folds into `architecture.md` + `unrealed/*.md` on implementation).
**Date:** 2026-07-15. **Produced autonomously overnight; cold-reviewed (2 reviewers, findings folded,
§ throughout).** **Decisions PROPOSED, NOT yet ratified** — §9 lists the calls this spec asks Andrzej
to make; until he signs off they are proposals and are **NOT** written into `decisions.md` (flagged in
`board/inbox.md`). If accepted, they would supersede the "lighting/paths are the second/third long
pole, defer to an optional editor final-bake" disposition of
`spikes/2026-06-27-decontainerize-uedctl/05-lighting-and-paths.md` — the lighting bake turned out to
be **1-bit visibility masks, not a light-transport port**, which collapses that long pole.

**Grounding (durable evidence — this spec is a synthesis of three deep RE sections):**
- [`spikes/2026-07-15-native-materialize/sections/10-bsp-csg-build.md`](../spikes/2026-07-15-native-materialize/sections/10-bsp-csg-build.md) — CSG→BSP geometry build (both D2 gaps closed; 33/33 checks).
- [`spikes/2026-07-15-native-materialize/sections/20-lighting-bake.md`](../spikes/2026-07-15-native-materialize/sections/20-lighting-bake.md) — `LIGHT APPLY` lightmap bake (format double-proven).
- [`spikes/2026-07-15-native-materialize/sections/30-ulevel-paths-assembly.md`](../spikes/2026-07-15-native-materialize/sections/30-ulevel-paths-assembly.md) — ULevel body, actor bodies, reachspecs, GUID mint, assembly (100/100 byte-exact).
- Prior proven pieces it builds on: `spikes/2026-06-27-decontainerize-uedctl/03-native-package-write.md`
  (package container, byte-exact), `spikes/2026-06-28-umodel-serialize-byte-exact.md` (`UModel`
  serialize, byte-exact), `07-native-actor-bodies.md` / `10-native-upolys-fpoly.md`,
  `specs/2026-06-24-uedctl-offline-bsp-engine-design.md` (the D2 CSG design this completes).
- Harness (all in `spikes/2026-07-15-native-materialize/harness/`, reproducible): `verify_csg_build.py`
  (33/33), `lightmap_reconcile.py` (byte format proof), `level_roundtrip.py` (100/100 ULevel),
  `guid_generations.py` (100/100 GUID/gen).

---

## 0. What this is, in one paragraph

Today `level materialize` (`apply.py`) drives an **ephemeral UnrealEd** to turn the git-tracked T3D
trunk into a `.dx` map file: it re-imports the actors, runs CSG (`MAP REBUILD`), bakes lighting
(`LIGHT APPLY`), and `MAP SAVE`s. This spec specifies an **editor-free native replacement** — plain
`level materialize`, **the editor DITCHED entirely** (no `--native` flag, no fallback editor path) —
that does the same build with **no editor, no wine, no container**: it runs CSG/BSP natively, bakes
the lightmap visibility masks, (optionally) builds AI reachspecs, and writes the `.dx` package
byte-by-byte from the proven serializers. The three hard unknowns that blocked this — *how CSG builds
the BSP*, *how `LIGHT APPLY` computes lightmaps*, and *what the ULevel/paths/package glue is* — are now
**all reverse-engineered** (sections 10/20/30). The remaining work is a faithful **port**, not more
discovery — **but see §8: a measured performance check showed pure CPython MISSES the build-time target
on big maps, so the two hot loops (CSG classify/split + BSP `LineCheck`) are implemented in **Rust** (a
PyO3 extension), with Python keeping the proven serializers + orchestration. Nuitka bundles the Rust
`.so` like it already bundles Pillow.**

## 1. The decisive findings (why this is now buildable)

1. **CSG/BSP is fully decoded — both D2 gaps closed** (§10). The leaf-filter (`bspBrushCSG` →
   `FilterEdPoly` → the keep/discard/reverse FilterFuncs) and the node emission (`bspBuild` →
   `SplitPolyList` → `FindBestSplit` → `bspAddNode`) are byte-decoded with every constant, the exact
   pass order, and the mapping onto the proven `UModel` arrays. The old port's only real parity bug
   (`abutting_subtracts` 11-vs-10) is diagnosed as an un-annihilated interior face (a facing-sign
   routing miss), not a heuristic error.
2. **Lighting is 1-bit visibility masks, not light transport** (§20). `LIGHT APPLY` stores, per lit
   surface per reaching light, a `USize×VSize` **shadow bitmask** (`1`=clear line-of-sight AND within
   radius). Brightness/hue/saturation/attenuation/`LE_Negative` are applied by the **game at render
   time** from the light actors (already in the T3D). A native baker needs only: the lumel grid
   formula, the radius test `R=(LightRadius+1)×25`, and a per-lumel `UModel::LineCheck` against the
   built BSP. The byte format is double-proven (`N×ceil(USize/8)×VSize` == the light-run length, zero
   exceptions across 3 maps).
3. **The package glue is proven or decoded** (§30 + priors). The package container, `UModel` serialize,
   actor property bodies, and now the **whole ULevel body** (100/100 byte-exact round-trip), the
   **StateFrame** prefix, **GUID/generation minting** (random GUID + one generation = final export/name
   counts, 100/100), and the **reachspec** format+build algorithm are all pinned. Export order is not
   load-bearing; only the `ULevel.Actors` array order is.

**Net:** the editor's last and hardest role — `MAP REBUILD` + `LIGHT APPLY` + `MAP SAVE` — is
specified for offline reproduction end-to-end. The critical path has **no serialize/format discovery
unknowns** left, and the one **algorithm** discovery item still open (zones/`TestVisibility`
portalization, §10.8) has a valid single-zone first cut. The real remaining risk is not *discovery* but
**faithful reproduction**: the CSG port must hit editor parity where the prior port failed, and float32
threshold-boundary parity is designed-for but unproven — see §5 for the calibrated candor and §6/§7 for
how each is gated.

## 2. The full native pipeline

Input: the git-tracked T3D trunk (`<project>/uedctl/maps/<level>/`) — the same input the editor path
reads. Output: a game-loadable `.dx` (or `.unr`). Steps:

```
level materialize --out <file>:            # native — NO editor, NO --native flag (editor ditched)
 1. read_level(trunk)                      # existing TrunkLevelSource — actors + brushes + order_value
 2. resolve packages / textures            # existing composed search path (config); no OBJ LOAD needed —
                                            #   textures/classes are IMPORTED by ref, never embedded (§30 5.2)
 3. CSG/BSP BUILD (§10):                    # native (hot loop — lang TBD, §8), replaces MAP REBUILD
      empty model
      for brush in actor-order (structural: Solid, then Portal-forced-notsolid):
          bspBrushCSG  → FilterEdPoly leaf-filter → carve solid/void (keep/reverse rules §10.4)
      bspBuildFPolys → bspMergeCoplanars → bspBuild(SplitPolyList/FindBestSplit/bspAddNode) → bspRefresh
      TestVisibility → leaves + zones + FZoneProperties
      pass B: semisolid Add detail brushes → bspBrushCSG again → re-partition subtree
      bspOptGeom → bspBuildBounds (collision hulls; may ship empty w/ iCollisionBound=-1 first cut)
      → produces Vectors/Points/Nodes/Surfs/Verts/Leaves/Zones + bound arrays
 4. LIGHTMAP BAKE (§20):                    # native (hot loop — lang TBD, §8), replaces LIGHT APPLY; downstream of step 3
      for each lit surf:
          grid = grid_formula(surf.PolyFlags, texture-space extent)   # USize/VSize/UScale/VScale/Pan
          lights = level lights reaching surf (radius cull + BSP visibility)
          for light, for lumel: bit = (dist²<R²) and Model.LineCheck(lumel+Normal*4, light) clear
          pack bits → LightBits; append FLightMapIndex; surf.iLightMap = idx; Lights += run + NULL
 5. PATHS BUILD (§30.4) — OPTIONAL:         # native, replaces PATHS BUILD; downstream of step 3
      gather NavigationPoints; for pairs within ~800uu: cylinder-trace reachability (walk/fly/swim/jump)
      → FReachSpec[]; fill per-node Paths/upstreamPaths; Prune (1.2×) → bPruned
      (FIRST CUT: emit ReachSpecs.Count=0 — map loads + is human-playable; AI nav added later)
 6. ASSEMBLE THE PACKAGE (§30.5):           # proven container + serializers
      synthesize name table + import table (classes/packages/textures by ref)
      serialize bodies: actors (StateFrame+props), brush UModels+Polys, the level UModel (step 3),
                        lightmaps (step 4) into the level UModel, LevelSummary, ULevel (Actors/URL/
                        ModelRef/ReachSpecs/trailing)
      mint GUID (random 16B) + 1 generation record = (exportcount, namecount)
      layout: header → names → bodies(record SerialOffset) → imports → exports@EOF → back-patch
 7. SELF-CHECK (§6, ALWAYS-ON, OFFLINE — no editor):   # re-parse the written package to EOF;
      assert surf.iLightMap/DataOffset/iLightActors/ReachSpec refs resolve + in-bounds;
      assert Actors[0]=LevelInfo, Actors[1]=Brush, PlayerStart present   # replaces editor H3 post-verify
      → atomic swap to --out (refuses overwrite w/o --overwrite, as today)
```

Steps 4 and 5 are **strictly downstream of step 3** (they consume the built BSP: lightmaps attach to
built surfs and trace shadows through built nodes; reachspecs trace collision through built nodes).

## 3. Module layout — RUST compute core + PYTHON glue (the §8 decision)

Two artifacts. The **Rust crate `uedctl-native`** owns everything CPU-bound (the D2 `uedctl/bsp/`
plan, now in Rust); the **Python package `uedctl/native/`** owns orchestration + the already-proven
byte-exact serializers. The FFI boundary is the built `UModel` body (§8.1): Python → `build_geometry`
→ `bytes`.

**RUST — `uedctl-native/src/` (compute; pure-Rust core, `cargo test`-able, no PyO3 except `lib.rs`):**

| Module | Owns | Ref |
|---|---|---|
| `f32.rs` | float32/SSE-faithful arithmetic — *native `f32`, the parity win over CPython's f64* | §10.2–3 |
| `fpoly.rs` | `FPoly` + survival/split (`Fix`/`RemoveColinears`/`CalcNormal`/`Finalize`/`SplitWithPlane`) incl. **Scale/SheerRate Transform** | §10.2–3 |
| `csg.rs` | `bspBrushCSG` + `FilterEdPoly` leaf-filter + the 4 CsgOper keep/reverse rules + solidity classes | §10.4–5 |
| `build.rs` | `bspBuildFPolys`/`bspBuild`/`SplitPolyList`/`FindBestSplit`/`bspAddNode` + pooling (`bspAddVector`/`bspAddPoint`) | §10.6 |
| `passes.rs` | `bspMergeCoplanars`/`bspOptGeom`/`bspRefresh`/`bspBuildBounds` | §10.7 |
| `zones.rs` | `TestVisibility` → leaves + zones + FZoneProperties (single-zone first cut) | §10.8 |
| `linecheck.rs` | `UModel::LineCheck`/`FastLineCheck` BSP ray test (shared by light + paths) — **no editor oracle; Tier-K battery (§6)** | §20.5 |
| `light.rs` | lightmap bake: grid formula, radius+LineCheck raytrace, bit packing (`rayon` per-surf) → FLightMapIndex/LightBits/Lights | §20 |
| `paths.rs` | reachspec build: scout cylinder-trace, `findBestReachable` sweep, `Prune`, `FReachSpec` + per-node index arrays | §30.4 |
| `model_write.rs` | serialize the built `UModel` body bytes (Nodes/Surfs/Verts/…/lightmap) — **dev-pinned byte-identical to Python `umodel_serialize.py`** | §20.8 |
| `lib.rs` | **THIN** `#[pymodule]` shim: PyO3 in → core structs, core → `bytes`. `build_geometry(brushes, lights, params) -> (model_body, summary)` | §8.1 |

**PYTHON — `uedctl/native/` (glue + the proven serializers, all unchanged in language):**

| Module | Owns | Ref |
|---|---|---|
| `native/pkg_write.py` | promote `decontainerize/harness/package_rw.py`: header/names/imports/exports/layout/back-patch + GUID/gen mint | §30.3, §30.5 |
| `native/pkgref.py` | **the import/name RESOLVER** (§30.6): every class → defining package, every texture/sound/mesh → its `(ClassPackage, ClassName, PackageIndex-chain, ObjectName)` incl. sub-package outers; reuses `uprops.py`'s class→package walk + the `texture-catalog`. Real work (not "no OBJ LOAD"); an **N-3 deliverable** | §30.6 |
| `native/actor_write.py` | StateFrame + `FPropertyTag` property-list writer (promote `prop_writer.py`) + struct value layouts + the `UPolys` writer | §30.2 |
| `native/level_write.py` | the ULevel body writer (Actors array, FURL, ModelRef, ReachSpecs, trailing) | §30.1 |
| `native/assemble.py` | object-graph → name/import synthesis (via `pkgref`) → **splice the Rust `model_body`** → assembly order → offset recompute; **synthesizes the mandatory `Actors[0]` LevelInfo + `Actors[1]` Default Brush + `UModel` when the trunk lacks them; asserts a `PlayerStart` is present** (see below) | §30.5–6 |
| `native/materialize.py` | top-level `run_materialize_native(level, out)` orchestrator (step 2→7): read trunk → build brush/light inputs → `uedctl_native.build_geometry(...)` → assemble → **always-on self-check (§6 gate 1)** → atomic swap | §2 |

**Where each RE section's serialize work lives (no duplication):** the Rust `model_write.rs` emits the
`UModel` body; the Python `umodel_serialize.py` (promoted) is retained as the **dev oracle** the Rust
serialize is pinned to byte-for-byte, and is *not* on the runtime path. Everything else Python-side is
promoted from the already-byte-exact harnesses.

**Mandatory `Actors[0]`/`Actors[1]` (a from-scratch-file gap the editor hid).** The editor path
relies on `MAP NEW` to supply a default `LevelInfo` (replaced by the trunk's imported singleton) and
the "red builder brush" is an editor artifact — so the trunk may carry **neither**. A native file
whose `ULevel.Actors[0]` is not **exactly class `LevelInfo`** or whose `Actors[1]` is not a `Brush`
(with a `Brush=`→`UModel` shape) may not load. `native/assemble` MUST therefore, when the trunk lacks
them: put the trunk's `LevelInfo` (or synthesize a minimal **engine `LevelInfo`** with `Level`→self)
at `Actors[0]`, and synthesize a Default Brush + a trivial builder-cube `UModel` at `Actors[1]`. Assert
this invariant before assembly. **`Actors[0]` must be class `LevelInfo` (engine) — NOT `DeusExLevelInfo`,
which is a *separate* metadata actor (its `Super` is `Info`, not `LevelInfo`; ✅ verified on real maps —
`LevelInfo0` is always the class-`LevelInfo` singleton, and `DeusExLevelInfo` sits elsewhere in the
array).** A **`PlayerStart`** is also required — not for bare *load*, but for the game to *spawn* the
player (present in all 100 retail maps, ✅). It is trunk-authored content (not an editor artifact), so
`assemble` asserts its presence as a **pre-flight precondition** (clear error if absent) rather than
synthesizing one — a map with no `PlayerStart` loads but fails the §6 gate-4 spawn check, and where the
player should start is an authoring decision, not something to invent. (`LevelSummary` is conventional
but **omittable** — `LevelInfo.Summary`=`None` still loads; §30.2.3 — so it is NOT in this invariant.)

**Brush `Scale` application (a gap the rest of uedctl punts).** `bspBrushCSG` transforms brush polys
via `BuildCoords()` = Location/Rotation **/Scale** (`MainScale`/`PostScale`/`SheerRate`; §10.4.1) —
but existing uedctl model-side code deliberately does **not** apply Scale (`architecture.md`/`quirks`
"Pivots"). Native CSG cannot punt it: `native/fpoly.Transform` must implement Scale + SheerRate to
match the editor's world geometry. **First cut may reject scaled brushes** (`MainScale`/`PostScale`≠
identity) with a clear error rather than silently mis-building — but this must be an explicit scoped
limitation, not an omission.

`apply.run_materialize` calls `native.materialize.run_materialize_native` **as its only path** — the
editor driver is removed, not branched-around; everything else (`--out`, `--overwrite` guard, atomic
swap, project/level resolution) is unchanged.

## 4. CLI surface — the editor is DITCHED, not a flag (decision 2026-07-14, Andrzej)

There is **no `--native` and no `--verify` flag, and no editor build path at all.** `level materialize`
**is** the native build — the editor is gone as a runtime dependency, permanently, not toggled. The
CLI grammar is unchanged from today's user's view:

- `level materialize [--out <path>] [--overwrite]` — build the trunk into a `.dx`/`.unr`, native, no
  editor. Same guards (refuse overwrite w/o `--overwrite`, atomic swap) as today.
- Optional iteration toggles (not verification flags): `--no-light` (emit an unlit model — every surf
  `iLightMap=-1`; loads, renders black — for fast geometry iteration) and `--no-paths` (skip the
  reachspec build; a map is human-playable with zero paths). These trim *build output*, they don't
  change correctness of what they do emit.

**Correctness is checked ALWAYS, inline, and OFFLINE — never via a flag and never via the editor**
(§6): every `materialize` re-parses its own written package and asserts self-consistency before the
atomic swap (the offline replacement for today's editor H3 post-verify). Comparing against the editor
is a **development-time** activity only (frozen golden fixtures captured once during the port — §6);
the shipped tool and its CI never invoke UnrealEd.

*(The old `05-lighting-and-paths.md` "keep an optional editor final-bake" disposition is fully
retired: lighting and paths are native too, so there is no residual editor step.)*

## 5. What is proven vs decoded-but-unported vs residual

| Piece | Status | Evidence |
|---|---|---|
| Package container (header/names/imports/exports/layout/offsets) | ✅ **PROVEN byte-exact** (real `.dx`) | 03-native-package-write |
| `UModel` (BSP) serialize — **Python** (dev oracle) | ✅ **PROVEN byte-exact** (72419/72419) | 2026-06-28-umodel-serialize-byte-exact |
| `UModel` (BSP) serialize — **Rust `model_write.rs`** (the RUNTIME/shipped path) | ⚠️ a **fresh re-port** — the Python proof does NOT transfer; pinned byte-identical to Python by **§6 gate 5** (agreement ≠ inherited proof) | §8.1 |
| ULevel body (Actors/URL/ModelRef/ReachSpecs/trailing) | ✅ **PROVEN byte-exact** (100/100) | §30, `level_roundtrip.py` |
| GUID + generation mint | ✅ **PROVEN** (100/100) | §30.3, `guid_generations.py` |
| Lightmap byte format (FLightMapIndex + LightBits + Lights) | ✅ **PROVEN** (double-measured, 3 maps) | §20, `lightmap_reconcile.py` |
| Actor bodies (StateFrame + property tags + struct layouts) | ✅ measured / round-trips | §30.2, 07-native-actor-bodies |
| CSG leaf-filter + node emission (both D2 gaps) | 📖 **byte-decoded, 33/33 checks** — port pending (Subtract pair + per-CsgOper Add/Intersect/Deintersect funcs, §10.4) | §10, `verify_csg_build.py` |
| `SplitWithPlane` cut geometry, cleanup passes | 📖 byte-decoded — port pending | §10.3/7 |
| Zones / `TestVisibility` portalization | ⚠️ **output-format decoded; ALGORITHM a scoped follow-on** (single-zone first cut) | §10.8 |
| Lightmap bake algorithm (grid formula, radius, shadow ray) | ✅ formula+constants proven; sub-lumel sample AA 🔬 | §20.4–6 |
| Reachspec build algorithm | 🔬 decoded (scout sizes, trace, prune, flags 5/7 confirmed) | §30.4 |

**What "the RE is done" does and does NOT mean (calibrated candor — the headline is rosier than the
body, so read this).** Every *byte layout* is specified and the serialize/ULevel/lightmap-format/GUID
pieces are **round-trip-proven** (reader/writer symmetry on real files). But two honest gaps remain in
the *algorithm* half: (a) the CSG **port** is unproven-in-reproduction — the prior port existed and was
*wrong* (the 11-vs-10 abutting-subtracts bug), the facing-sign fix is a *diagnosed hypothesis* the N-1
differential must prove, and node-plane bit-identity is explicitly gated on that differential (§10.10);
(b) zones/`TestVisibility` is only **output-format** decoded — the portalization/zone-flood algorithm is
not yet instruction-level (§10.8), a genuine remaining discovery item (scoped to single-zone first cut,
§7 N-2). A further standing risk is **FP parity** — but its worst case is now **retired (spike 41,
`spikes/…/41-fp-model-x87-vs-sse.md`)**: the UED22 substrate is **not** a 1999 x87 binary but a **2022
MSVC `/arch:SSE2` rebuild** — the CSG math (`SplitWithPlane`/`…Fast`/`CalcNormal`/`PlaneDot`) is **pure
SSE scalar `f32`, zero x87 arithmetic, zero `fldcw`, zero FMA**. So **bit-exact parity IS reachable
with native Rust `f32`** (no extended-precision emulation — that would *diverge*). What remains is
deterministic **operation-ORDER fidelity** (replicate `PlaneDot`'s pairwise reduction tree; forbid
`mul_add`/FMA in the Rust core) plus simply *running* an off-grid/±0.25-boundary case (validation not
yet done, but no longer a fundamental unknown). The remaining live risk is **game-load of a from-scratch
file**
("loadable by construction" is an argument, not a test — the round-trip proofs reproduce *existing*
bytes; N-3's smoke is the first test of *synthesized* values). None are blockers; all are gated (§6/§7).

**Residuals (non-blocking, enumerated per section):**
- Add/Intersect/Deintersect FilterFunc keep-sets — the funcs are **per-CsgOper** (`cmove`-selected
  `0x31770`/`0x339e0`, not "the same two callbacks"); decoded statically in §10.4; confirm live with one
  differential `MAP REBUILD`.
- Zones — `TestVisibility` portalization/zone-flood **algorithm** (not just output format); single-zone
  first cut is valid for a carved room (§10.8, §7 N-2).
- `bspOptGeom` T-junction-linking internals — needed for crack-free *surf* parity, not solid/void
  correctness; bounded follow-on disasm (§10.7).
- `bspBuildBounds` hull packing — a first cut ships empty bound arrays (`iCollisionBound=-1`); collision
  is **assumed** to fall back to a plane-walk (correct, slower) — *plausible but unverified until N-3's
  game-load* since both the native shadow ray and runtime collision go through `LineCheck`. Regenerable
  build output (§10.7).
- Lightmap: sub-lumel sample offset = shadow-edge AA only (cosmetic); the lumel→world **inverse-basis**
  = systematic, a *shadow-correctness* residual — validate one baked surface before trusting shadows
  (§20.6, N-4 gate).
- `R_DOOR`/`R_PLAYERONLY` reachflag values (2 of 7 inferred) + NavigationPoint 16-int static-array tag
  encoding — validate at paths bring-up; not needed for an empty or walk/fly/swim/jump path set (§30.4).

## 6. Verification strategy (the differential gate)

The editor is a **development-time test oracle ONLY** — invoked during the port to capture **frozen
golden fixtures**, then never again: the **shipped tool never runs UnrealEd**, and `materialize`
itself has no editor step and no `--verify`. At runtime the sole check is gate 1 (always-on, offline,
self-consistency). Gates 2–5 are **dev-test gates** against once-captured, committed goldens.

**Runner reality (there is NO CI today — the repo has none).** These gates are, for now, an explicit
**local-runner responsibility**: a single documented command (or pair) must drive **both** the Rust
`cargo test` goldens **and** the Python `pytest` suite. Because the Python suite must run without a
built extension (docs-only / pure-Python changes), every test that needs `uedctl_native` carries a
`pytest.importorskip("uedctl_native")` guard so `pytest` **degrades gracefully** rather than hard-fails
when the `.so` isn't built. Standing up real CI (building Rust + Python + eventually Nuitka) is its own
board item; until then "CI-able" below means "scriptable + a human/routine actually re-runs it".

(The crux, from both review passes: geometry parity is checkable against the editor, but two consumers
have NO editor oracle — `linecheck`, since no console verb answers "does a trace hit?", D2 §3a; and the
lightmap bake, whose format is provable but whose *correctness* no format check catches — so each gets
its own gate; and the **dual Rust/Python `UModel` serializer** must be pinned or it drifts silently.)
Five gates, extending D2's Tier-C/S/K:

1. **Self-consistency (ALWAYS-ON, at every materialize, offline — the ONLY runtime check).** The
   written package re-parses to EOF (existing `umodel_parser`/`package_rw`), `surf.iLightMap` indices
   resolve, `DataOffset`/`iLightActors` ranges are in-bounds, ReachSpec refs resolve, and the
   `Actors[0]=LevelInfo`/`Actors[1]=Brush`/`PlayerStart`-present invariants hold. No editor. This is
   the offline replacement for the editor H3 post-verify and runs on every build ("check that when
   building / after building"). ⚠ **Measure its cost:** a full pure-Python re-parse to EOF of a big
   level (UNATCO-Island: 13k nodes / 207k verts) could eat a real slice of the ≤20 s budget the Rust
   decision exists to hit — if it's significant, make gate 1 a partial/structural check or move the
   re-parse into Rust too. *(Positive: re-parsing Rust-written bytes with the **Python** `umodel_parser`
   is a genuine cross-language independent read-back — the split strengthens this check.)*
2. **Tier-K — LineCheck known-answer battery (gates `native/linecheck.py`, BEFORE it feeds light or
   paths).** `UModel::LineCheck`/`FastLineCheck` is substantial new BSP-ray code shared by the baker
   and the tracer, and it is **not differentially checkable against the editor** (no trace-result
   console verb — D2 §3a). Port it against a **hand-authored known-answer suite**: constructed rooms
   (a box, a box with a pillar, a subtract touching a subtract, an off-grid wedge) with asserted
   hit/miss + hit-fraction for a battery of rays. A sign-inverted or off-by-a-node LineCheck silently
   corrupts BOTH lighting and paths, so this gate runs at N-4 start and is a hard prerequisite for both
   consumers. (This is the Tier-K probe D2 defined; it was dropped from the first draft of this §6 and
   is reinstated here.)
3. **Structural parity vs frozen editor goldens (the geometry ship gate — DEV/CI, no runtime editor).**
   During the port, build a discriminating corpus once in an ephemeral editor
   (`MAP REBUILD`+`LIGHT APPLY`+`MAP SAVE`), parse the `UModel`s, and **freeze** the results as tracked
   golden fixtures; CI then asserts the **native** build reproduces them (editor never runs in CI).
   Compare the **Tier-S surf/face set** (plane + signed-normal winding + cleaned
   vertex set; texture vectors excluded) **and leaf/zone STRUCTURE — membership, not counts** (which
   leaf sits in which zone; equal counts never prove equal zoning — D2 was emphatic that counts are
   never a correctness gate). Freeze a discriminating corpus (convex, off-grid, semisolid, portal,
   merge-active, degenerate) as golden fixtures per the existing `test_builder_parity` template, each
   captured ≥3× byte-stable before freezing. **A LIGHTING correctness fixture rides here too:** a
   pillar-casts-a-shadow case where the native shadowed-lumel set must overlap the editor's baked mask
   within tolerance — so the bake has a real *correctness* gate, not just the format/consistency check.
   (Lighting, paths, and collision bounds are otherwise **build output — never byte-compared**;
   regenerable, never hashed — only presence + internal consistency + this one shadow-overlap check.)
4. **Game-load smoke (the ultimate acceptance — AUTOMATED).** Load a native-built `.dx` in the actual
   game and confirm it spawns, renders lit, collides, and is walkable — the decisive test that a
   *from-scratch* file with a *natively built* Model is engine-valid (the one composite never yet
   exercised; §30 residual 4). **Automate it via the existing headless game-driving infra** (the
   in-game preview TCP link / uplayctl-style boot — `decisions.md` 2026-07-13): assert the game boots
   to port 7777 with no load error, the player spawns, and a `Screenshot` renders non-black lit
   geometry — a specified CI-able gate, not a manual eyeball. Start with a hand-trivial carved room,
   then a real trunk.
5. **Dual-serializer cross-check (MANDATORY, every dev-test run — the anti-drift gate).** The single
   most byte-sensitive, most-proven component (`UModel` serialize, 72 419/72 419) now exists in **two
   languages**: the runtime Rust `model_write.rs` and the proven Python `umodel_serialize.py` (kept as
   oracle). Nothing in gates 1–4 compares them — so without this gate they drift silently the moment the
   format understanding evolves (a new lightmap field, a compact-index tweak — exactly the fiddly,
   variable-width parts that drift), and the Rust one is what ships. **Gate:** over the golden corpus,
   build the arrays, serialize in **both** Rust and Python, assert **byte-identical**. This is what makes
   "the Python serializer stays the oracle" (§8.1) real rather than prose.

**Kill criterion (inherited from D2):** if the CSG port is not Tier-S-exact on the convex+off-grid
corpus subset within a bounded effort box, native geometry stalls and the editor path remains default —
but the lighting/paths/assembly pieces (all proven/decoded independently) still stand and can attach to
an editor-built Model. **The pieces are decoupled** (a genuine strength: N-3 assembly, N-4 lighting,
and N-5 paths each ship value even if the CSG port is slow to reach parity).

## 7. Sequencing (implementation slices)

The RE is done; these are **port** slices, each gated on the §6 differential (not counts).

- **M0 — glue / toolchain / game-load proof (FIRST, before any hard CSG).** Stand up the Rust crate +
  PyO3/maturin build + the `_venv.sh`/`bin/test` integration (§8.3). (Nuitka-bundling + FP-model are
  already de-risked — spikes 40/41.) Cross the FFI with a **trivial hand-built (or editor-built)
  `Model`** → Python
  `assemble` → **the `.dx` game-loads and the player spawns**. This proves toolchain + FFI boundary +
  package assembly + the always-on self-check *before* N-1, so a plumbing failure isn't debugged tangled
  with CSG parity. (Natural because §6's kill-criterion already makes the pieces decoupled — assembly
  can attach to an editor-built Model; the board's pure-Python `[spike]` "Native Model GAME-load gate"
  IS this M0.)
- **N-1 — CSG/BSP core.** `f32`/`fpoly` (incl. **Scale/SheerRate** Transform — a scaled brush N-1
  cannot yet match is **rejected with a clear error, never silently mis-built**; §3) /`csg` (all four
  CsgOper filter funcs, §10.4) /`build` + `model_write`. Gate: Tier-S-exact on convex +
  off-grid + a single subtract/add + an add-in-subtract. This is the D2 long pole (and exactly where
  the prior port was *wrong* — the 11-vs-10 abutting-subtracts bug; the facing-sign fix is a diagnosed
  hypothesis this slice must *prove* via the differential, not assume).
- **N-2 — solidity + cleanup + zones.** `passes`/`zones` + semisolid/portal cases. Gate: Tier-S on the
  semisolid/portal/merge corpus + correct leaf/zone **membership** (not counts). **Zone first cut =
  single-zone (zone 0 everywhere)** — valid for a carved room and unblocks N-1..N-4; full
  `TestVisibility` portalization/zone-flood is only *output-format* decoded today (§10.8, honest per
  review) and multi-zone is a bounded follow-on RE (`TestVisibility 0xaa940` instruction-level decode).
- **N-3 — package assembly (unlit, no paths).** `pkg_write`/`actor_write`/`level_write`/`assemble` +
  **`pkgref` import/name resolver** (real work — §3) + GUID mint + the `Actors[0]`/`Actors[1]` synthesis
  invariant. Gate: a `materialize --no-light --no-paths` `.dx` **game-loads** and is walkable (the
  first end-to-end editor-free map). Byte *layouts* here are proven, but note these are **round-trip**
  proofs (reproduce existing bytes); N-3's game-load smoke is the FIRST test of *from-scratch
  synthesized* values (0-filled tails, fresh masks, minted GUID) — so it is the real acceptance, not a
  formality. Lowest-*code*-risk slice; highest-*novelty* in that it's the first synthesized file.
- **N-4 — lightmap bake.** `linecheck` FIRST (its **Tier-K known-answer battery**, §6 gate 2, is a hard
  prerequisite — a wrong LineCheck corrupts light AND paths silently), then `light` + the `model_write`
  lightmap encoders. Gate: the §6 pillar-shadow differential fixture (shadowed-lumel overlap vs editor)
  — plus the lumel→world **inverse-basis** validated against one real baked surface (§20.6 item 2, a
  *correctness* residual, not cosmetic) — and native lit map game-loads rendering non-black.
- **N-5 — paths.** `paths` reachspec build. Gate: AI navigates a native-built map; the NavigationPoint
  static-array tag encoding validated against a real `.dx` (§30 residual 3). (Ships last; an empty
  ReachSpecs set is valid throughout N-1..N-4 — a native map is human-playable with zero paths.)

**Honest effort framing.** N-3 is small and low-risk (proven layouts). N-1/N-2 is the multi-week
faithful-port-with-differential the D2 design already scoped (§ that spec's §4–7) — the RE that gated it
is now *complete*, which is the change this spec lands. N-4 is small (visibility raytrace + packing).
N-5 is moderate and optional. **"Ready by morning" delivered the complete reverse-engineering + this
implementation-ready spec; the port itself is the scoped multi-slice build above, not an overnight
task** — and is now unblocked end-to-end for the first time.

## 8. Performance & implementation language — MEASURED; CPython misses → RUST (decided)

**Target (Andrzej):** a UNATCO-sized level should materialize in **≤ 2 min, ideally ≤ 20 s**. Much
longer than 2 min ⇒ reconsider pure Python (e.g. Rust). **This was measured early** (harness:
`spikes/2026-07-15-native-materialize/harness/perf_probe.py` + `bench.py`; reproduce with system
`python3.12`).

**Real workload (parsed from the retail built maps):**

| Level | brushes (CSG in) | built nodes | surfs | lightmap rays (1/lumel/light) |
|---|---|---|---|---|
| `01_NYC_UNATCOHQ` | 721 | 5 174 | 3 570 | ~3.0 M |
| `01_NYC_UNATCOIsland` | 1 415 | 13 212 | 6 821 | ~31 M |

**Measured pure-CPython throughput (single core):** plane-classify (CSG/`SplitWithPlaneFast` atom)
≈ **1.6 µs/call** (0.62 M/s); BSP line-descent (`LineCheck` shadow-ray atom) ≈ **9.9 µs/ray**
(101 k/s). **Extrapolated build time (both estimates OPTIMISTIC — tuple atoms, `2·N²` CSG floor,
straddle-simplified `LineCheck`):**

| Level | CSG (`~2·N²` classifies) | lighting (rays) | **TOTAL** |
|---|---|---|---|
| UNATCO-HQ | ~25 M → **~41 s** | ~3 M → **~30 s** | **~71 s** |
| UNATCO-Island | ~93 M → **~151 s** | ~31 M → **~307 s** | **~458 s ≈ 7.6 min** |

**Verdict: pure CPython MISSES the target.** HQ (~71 s) already blows the 20 s ideal; **Island
(~7.6 min) is far past the 2 min ceiling** — the explicit "much longer than 2 min → rethink Python"
trigger. And the real numbers are **worse** than this floor (OO attribute access, `SplitWithPlane`
*cut* geometry on top of classify, the cleanup passes, and split-recursion in `LineCheck` all add
cost; the CSG `2·N²` model is a floor). CPython + `numpy` + multiprocessing might reach ~10–20 s (HQ)
/ ~60–120 s (Island) — *borderline for the 2 min ceiling, never the 20 s ideal, and fragile* (D2
already noted "numpy buys ~5–20×, not the 100×+ needed").

### 8.1 ✅ DECIDED (Andrzej, 2026-07-14): the compute goes in RUST, as a PyO3 extension

The two hot loops — (a) CSG classify/split and (b) BSP `LineCheck` (shared by lighting + paths) — go
in **Rust**, exposed to Python as a **PyO3 / maturin native extension module `uedctl_native`**. A
Rust core makes ≤ 20 s realistic even for UNATCO-Island, and `rayon` gives real multi-core lighting
with no GIL. **FP parity — RESOLVED in Rust's favour (spike 41).** The substrate is a **2022 MSVC
`/arch:SSE2` rebuild**, not a 1999 x87 binary: the CSG math is pure SSE scalar `f32` (`movss/subss/
mulss/addss/comiss`), **zero x87 arithmetic, zero `fldcw` rounding tricks, zero FMA**. So native Rust
`f32` reaches **bit-exact** — do NOT emulate extended precision (it would diverge). Two invariants the
Rust core must hold: **(i)** replicate `FPlane::PlaneDot`'s pairwise (`mulps`+shuffle) reduction ORDER
— f32 summation order is not associative; **(ii)** forbid `mul_add`/FMA (`a*b+c` must round twice, as
the non-FMA SSE build does). This is deterministic operation-order work, not an open unknown — it
retires §5's former "#1 FP risk".

**The boundary — drawn at the built `UModel` body, crossed a handful of times with BULK data (never
per-op).** Rust owns *compute*; Python keeps the *already-proven byte-exact serializers* and
orchestration. The API exposes the pipeline **stages** (so `--no-light`/`--no-paths` and the
N-3-before-N-4 order fall out, and paths — which serialize into the *Python* ULevel/actor bodies, not
the Model — have a defined return):

```
uedctl_native.build_geometry(brushes, params)          -> Result<Built, BuildError>   # CSG→BSP→zones
uedctl_native.bake_lighting(handle, lights)            -> Result<(), BuildError>       # fills lightmap arrays (rayon)
uedctl_native.build_paths(handle, navpoints, scout)   -> Result<PathData, BuildError> # reachspecs (for Python level_write)
uedctl_native.serialize_model(handle)                 -> bytes                          # the UModel body
  Built/handle: an opaque Rust-owned build (nodes/surfs/verts/…); summary = counts + surf→iLightMap map
  brushes[{polys[flat f32 buffers], csg_oper, polyflags, loc,rot,scale,prepivot}]  # flat buffers, NOT nested PyO3 objects
  PathData: FReachSpec[] + per-navpoint Paths/upstreamPaths/prunedPaths index arrays → Python serializes
```

Inputs are small (hundreds–thousands of brushes, marshalled as **flat float buffers**, not per-element
PyO3 objects); the **output is `bytes`, not 200k node/vert objects** (UNATCO-Island: 13k nodes / 207k
verts). The opaque-`bytes` splice is safe **only because the `UModel` body is fully position-independent
— no whole-file offsets** (established byte-exact: all refs are array *indices*, `DataOffset` is
array-relative — `spikes/2026-06-28-umodel-serialize-byte-exact.md` note 2; `assemble` must assert
this before splicing). Rust emitting the Model body is mechanical and **pinned to the proven Python
`umodel_serialize.py` by a MANDATORY cross-check gate (§6 gate 5)** — not just a dev nicety — so the
runtime Rust serializer cannot silently drift from the proven Python one.

**FFI mechanics (repo-rule-load-bearing — the spec had omitted these):**
- **Error contract:** the core returns `Result<_, BuildError>`; the `lib.rs` shim maps `Err` to a
  dedicated Python `uedctl_native.BuildError` carrying the offending value (brush name, coord) — so a
  degenerate/`GeometryError` brush, a scaled-brush rejection, or a CSG failure surfaces as a clean
  exit-2 message, **never a traceback** (the repo's hard "no exception reaches the CLI user" rule).
- **Panics:** keep `panic = "unwind"` (never `abort`, which kills the Python process); the shim
  **catches and translates** any core `panic!`/`unwrap` into `BuildError` (near-certain during CSG
  bring-up on bad polys) so it can't reach the user as an opaque `PanicException`. Prefer `Result` over
  `unwrap` in the core.
- **GIL:** the heavy compute runs under `Python::allow_threads(|| …)` — GIL released for the whole
  multi-second/minute call, so it stays **interruptible** (Ctrl-C / signals / a Python watchdog) per the
  repo's long-running-work discipline, and `rayon` coexists with the runtime cleanly.

Python's `pkg_write`/`level_write`/`actor_write`/`assemble`/`pkgref` splice the body + reachspecs into
the package they assemble — all unchanged, all proven.

### 8.2 Crate shape — pure-Rust core + thin PyO3 shim

```
uedctl-native/                       (Rust crate, in the uedctl tree)
  src/lib.rs      ← #[pymodule] shim ONLY: PyO3 in → core structs, core out → bytes. THIN.
  src/{f32,fpoly,csg,build,passes,zones,light,linecheck,model_write}.rs   ← pure Rust core, NO PyO3
  tests/          ← cargo golden tests: frozen editor Tier-S surf sets + shadow masks (no Python, no editor)
```
Keeping PyO3 out of the core means `cargo test` runs the goldens with no Python, the compute stays
portable, and a standalone sidecar `main.rs` remains possible later if ever wanted.

**Determinism invariant (goldens require it):** parallelism (`rayon`) is confined to the
**embarrassingly-parallel per-surf lighting**, and results are placed **by surf index, not completion
order**. It is **never** applied to the BSP build and **never** to a floating-point reduction
(nondeterministic summation order changes `f32` rounding and would flake the byte/Tier-S goldens). No
`rayon` worker calls back into Python (would force per-thread GIL reacquisition).

### 8.3 Packaging — Nuitka ships; the venv is dev-only

**The shipped artifact is the Nuitka build**; the dev venv exists only for iteration. A PyO3 `.so` is
an ordinary CPython **extension module** — the same kind of artifact as the `Pillow` uedctl already
bundles — so Nuitka `--standalone`/onefile *should* include it via the exact mechanism that already
ships Pillow (auto-detected on `import uedctl_native`; belt-and-suspenders `--include-module=uedctl_native`).
In-process, no sidecar to locate at runtime, one coherent app.

> **✅ PROVEN end-to-end (spike 40, `spikes/…/40-nuitka-pyo3.md`).** A trivial `abi3-py312` PyO3 module
> built with maturin, frozen with Nuitka: **both `--standalone` AND `--onefile` bundle the `.so` and
> run correctly from an empty environment** (`env -i`). The `.so` is **auto-detected on import** —
> `--include-module` is optional — i.e. the exact "like Pillow" mechanism. (Caveat unchanged: ditching
> the editor removes only *materialize's* Docker need; **`level preview` (headless game) + stub-build
> still need Docker** — "editor gone" ≠ "whole tool container-free". And this is **Linux/x86_64 only**;
> the multi-platform matrix is separate — `dev-runtime.md`'s deferred Nuitka release stands as a wider
> item, but the *PyO3-bundling* question it depended on is now closed.)

Gotchas the "like Pillow" line glosses — now MEASURED (spike 40), design them in:
- **Python-ABI coupling** — use PyO3 **`abi3` (`abi3-py312`)** so the `.so` decouples from the exact
  CPython patch/minor (confirmed working under Nuitka).
- **glibc floor = the build host's** — measured **2.34** on the spike host (glibc 2.35); **build
  releases on the oldest supported glibc**.
- **`patchelf` is required** for Nuitka `--standalone` on Linux (pip-installable, no root) — add it to
  the release-build deps.
- **maturin needs `VIRTUAL_ENV` set + a `project.version` in `pyproject.toml`** (dev-flow papercuts).
- **Per-platform Rust toolchain** — the "generic UE1 tool, one binary" direction implies a
  multi-platform matrix; cross-compiling a PyO3 extension is materially harder than pure Python — each
  target needs its own toolchain/build (out of scope for the Linux/x86_64 first cut).
- **Dev flow, concretely:** `maturin develop` builds `uedctl_native.so` into the auto-managed venv —
  but `bin/_venv.sh` currently builds nothing Rust and short-circuits on a pip-marker string, so it
  needs real changes: **detect `cargo`, run `maturin develop` gated on a Rust-source hash/mtime marker
  (a `.rs` edit must trigger a rebuild — the pip marker won't), and make it OPTIONAL/skippable so a
  docs-only or pure-Python change still runs `pytest` without a Rust build.** `bin/test` (or a sibling)
  must also drive `cargo test`. Add `cargo`/`rustc` to the tool `CLAUDE.md` prereqs and `_venv.sh`'s
  toolchain fast-fail (like `python3.12` today). *(These `_venv.sh`/`bin/test`/`CLAUDE.md` edits are
  M0 setup — NOT done here, since a `maturin develop` with no crate yet would break the venv.)*

**Rejected: a subprocess sidecar binary.** The honest tradeoff is **in-process packaging risk (the
PyO3+Nuitka+ABI gotchas above) vs. process/deploy complexity (sidecar)** — the sidecar would in fact
have *sidestepped* the untested Nuitka+ABI risk (its one real edge is no Python-ABI coupling). PyO3-first
is chosen because it's in-process (fastest, no runtime sidecar-location) and because **the pure-core
crate shape keeps the sidecar open** if the Nuitka spike goes badly — so the decision is reversible.
(The earlier "coherence" / "tempts Rust to own the `.dx` write" framing was weak: transport doesn't
dictate that discipline — you can pipe bulk arrays over a sidecar too.)

*Everything else in this spec — the RE, the byte layouts, the pipeline, the CLI, the verification — is
language-agnostic and unchanged by this decision.*

## 9. Decisions PROPOSED (pending Andrzej sign-off — flagged in `board/inbox.md`; NOT in `decisions.md`)

These are the calls this spec asks Andrzej to make. Per the repo rule "record every decision *I* make,"
these are recorded here as **proposals** and will be appended to `decisions.md` (with rejected
alternatives) **only on his sign-off** — an autonomous overnight run does not ratify decisions on his
behalf.

- **The whole native-materialize pipeline is reverse-engineered and buildable** — CSG/BSP (leaf-filter
  + node emission decoded; zones' output format decoded, portalization algorithm a scoped follow-on),
  lighting (visibility-mask bake), and ULevel/paths/assembly (proven byte-exact). Would supersede the
  "lighting = 2nd long pole / paths = 3rd, defer to optional editor final-bake" disposition.
- **Lighting is a 1-bit shadow-mask bake, not a light-transport port** — the load-bearing finding that
  collapses native lighting from "port the engine's illumination" to "port a per-lumel BSP ray test".
- **The editor is DITCHED entirely — `level materialize` IS the native build (no `--native`, no
  `--verify`, no fallback editor path).** *(Andrzej, 2026-07-14.)* Correctness is an **always-on,
  OFFLINE self-consistency check** run on every build (re-parse + resolve refs + assert the
  `Actors[0]/[1]`/`PlayerStart` invariants — §6 gate 1), NOT a flag. The editor survives ONLY as a
  **development-time golden-capture oracle** (frozen fixtures, §6); the shipped tool and CI never invoke
  UnrealEd. Byte-exactness is the DEV gate for **geometry** (Tier-S surf set, vs frozen goldens);
  lighting/paths/bounds are build output, checked for presence+consistency only, never byte-compared.
- **The compute goes in RUST (PyO3 extension); Python keeps the proven serializers.** *(Andrzej,
  2026-07-14 — §8.)* Measured: pure CPython misses the ≤2 min / ≤20 s target (UNATCO-Island ~7.6 min).
  Decision: the two hot loops (CSG classify/split + BSP `LineCheck`) are a Rust crate `uedctl-native`
  exposed via **PyO3/maturin**; the FFI boundary is the `UModel` body (bulk `bytes`, never per-op);
  Python retains orchestration + the byte-exact package/ULevel/actor/import serializers; **Nuitka
  bundles the `.so` like Pillow** (ship = Nuitka, venv = dev only). Rejected: subprocess sidecar
  (no ABI edge when the ship artifact is the Nuitka app). Adds a Rust toolchain to the dev/CI env.
- **GUID is random-minted, one generation = final export/name counts** — the from-scratch header rule.
- **Reachspecs (and an empty set) are valid build output** — a native map ships human-playable with zero
  paths; AI nav is an N-5 enhancement.

## 10. Durable-doc reconciliation (do on landing / already done here)

Facts this work *verified about the editor/format* belong in the durable `unrealed/*` docs (they
describe "what IS"), independent of whether the native port ships:
- **`unrealed/leveldesign/lighting.md`** — corrected: `LIGHT APPLY` bakes **1-bit visibility masks**,
  not intensities/colours; brightness/hue/saturation/attenuation are render-time. *(Done in this
  change.)*
- **`unrealed/commands.md` + `t3d.md`** — corrected: **`PATHS BUILD`** builds reachspecs;
  **`PATHS DEFINE`** only spawns auto-marker NavigationPoints. *(Done in this change.)*
- **`bspspike/umodel_parser.py`** — the `FBspSurf` field at `+0x18` is **`iLightMap`** (parser
  mislabels it `i_actor`); `+0x24` is the brush `Actor`. Noted in §20; fold the rename in at N-4.
- On implementation, the module map + write pattern land in `architecture.md`; the CSG/lighting/paths
  algorithm facts stay cited to the `spikes/2026-07-15-native-materialize/sections/` (durable evidence).
