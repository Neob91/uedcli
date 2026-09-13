# Native `level materialize` — full byte parity with UnrealEd (UED22)

This is the single source of truth for the native-materialize parity campaign: the goal, the
reference we compare against, the exact parity bar, the method, and the ONE script that checks it.
Read this before doing any native-materialize parity work so you don't re-derive it.

## Goal

`level materialize` builds the git-tracked T3D trunk into a `.dx`/`.unr` map file. Two build paths
exist: the **editor-driven** path (drives UED22) and the **native** path (`UEDCLI_NATIVE_MATERIALIZE=1`,
a Rust `uedcli-native` CSG/BSP/lighting engine, no editor). The campaign goal is that the **native
build is byte-identical to UED22's build of the same trunk** — full package bytes, not just counts.

## Prime directive — fix toward UnrealEd's algorithm

Close every divergence by making native's algorithm match what UED22 actually does: reproduce the
editor's CSG/BSP/lighting/dedup step (decoded from the binaries, or measured by an editor probe) so
the bytes agree at the source. Prefer the faithful fix even when it is larger, or when a mask would
pass the gate today — a mask is a deferral, not a solution, and it erodes what the gate proves.

An exclusion is a LAST RESORT, only for a divergence that is NOT a reproducible algorithm difference:
a per-save-random engine field, or editor bookkeeping no reader consumes. A divergence caused by
native's algorithm differing from the editor's — a different BSP split, point-dedup, or lighting run
— is fixed, not masked, however costly. Any mask still standing over an algorithmic divergence is a
stopgap owed a faithful fix, recorded as such. *(Owner ruling, 2026-09-05.)*

**Standing direction: keep going.** Fixing issues and pushing the ladder further is the DEFAULT
mode of this campaign, not something that needs asking for each time. When a divergence is found,
root-cause it and fix it faithfully; when it's fixed, keep pushing N; when a fix turns out to be
large, scope it, park it as a board item if it doesn't fit the current pass, and continue on the
other levels — don't stop the whole campaign to ask permission to keep working. Bring the owner a
real decision only when one actually exists (a new exclusion candidate, a reference-methodology
question, something that changes what's being measured) — not "should I keep fixing things?".
*(Owner ruling, 2026-09-06.)*

## The reference we compare against (how UED22 "builds" a trunk)

`build_ued_import_built_golden.py`: `MAP NEW` → `MAP IMPORT FILE=<trunk T3D, with a sacrificial
dummy builder brush prepended as Actors[1]>` → `MAP REBUILD` → `LIGHT APPLY` → `MAP SAVE`.

Why this exact recipe (all established 2026-09-04, evidence in `dev/docs/board/…/ued22-world-bsp-differs-per-ingest-verb-paste`):

- **The editor carves a different world BSP per ingest verb.** Same brushes: `EDIT PASTE` → 6314
  nodes (native reproduces this exactly); whole-file `MAP IMPORT`/`MAP IMPORTADD FILE=` → 6270; `MAP
  LOAD` → 6254. We use MAP IMPORT because native's package *serialization* already matches it (the
  2026-09-02 unbuilt-structure-parity work) and it imports Movers with their models.
- **The dummy builder brush is mandatory.** UED22 excludes whatever sits in `Actors[1]` from CSG at
  every rebuild. Without a sacrificial builder there, the first *real* brush lands in `Actors[1]` and
  is silently dropped (the defective 6270 tree). Native synthesizes the same dummy at `Actors[1]`
  (`uedcli/native/unbuilt.py` `_BUILDER`) and skips `Actors[1]` positionally.
- **The shipped retail `.dx` is NOT a valid reference.** Its tree (e.g. UNATCO 5188 nodes / 2266
  leaves) is a GUI-`OPTIMAL OPTGEOM ZONES` rebuild accreted over the designers' authoring history —
  unreproducible from the trunk by any single command. Always compare against a self-built golden.

## The parity bar — FULL structural / package-byte

Byte-identical package modulo a **closed, evidence-backed exclusion set**. The comparison is
**identity/permutation-based, not raw-byte**: every `ObjRef` (Actors entries, `Base`/`Owner`/`Level`/
`Region`, `UModel` refs) is resolved by class + outer-chain and remapped across the two export
orders; every identity-matched object BODY must be byte-identical; name/import table CONTENT must
match; the surviving (non-`None`) `Actors` set AND order must match (Actors order = CSG precedence).

**Excluded (and ONLY these):**

- Per-save-random engine fields: 16-byte package GUID, save timestamps / LevelInfo `TimeSeconds`,
  StateFrame `LatentAction`, the six Camera viewport bodies.
- Editor MAP REBUILD object-table GC bookkeeping (opus-confirmed render/gameplay/runtime/savegame
  inconsequential, 2026-09-04): object auto-counter **names** (`Polys4` vs `Polys6`), Level `Actors`
  array **`None`-holes**, export-table **order** / freed-slot reuse. Shipped retail maps normally
  carry `None`-holes (29–329) and export-order≠actor-order, and the game plays them.
- Orphan-vert **`iVertex`** — a `Model` `FVert` whose slot is in no live BSP node's
  `[iVertPool, iVertPool+NumVertices)` ring (two opus reviews + owner, 2026-09-04). Nothing
  dereferences it: UED22's own build stores an out-of-range orphan `iVertex` and its maps ship/play.
  Masked with **dynamic per-build liveness** (only verts outside every live ring; `iSide` and all
  live verts stay compared) — divergent liveness changes the node rings, which are still compared.
- `FName` CASE in name/import tables (owner + opus, 2026-09-04). UE1 `FName` is case-insensitive but
  case-preserving; the editor's spelling comes from its boot-order global name pool (e.g. `sky` vs
  native's `.utx`-faithful `Sky`), not the trunk. The gate compares names, import paths, and every
  identity **casefold-equal** — a genuine wrong name still FAILS. Game-inconsequential (lookups are
  case-insensitive).
- BSP node `node_flags` bits **`NF_PolyOccluded` (0x08)** + **`NF_BoxOccluded` (0x10)** (two opus
  reviews + owner, 2026-09-04). Per-frame renderer occlusion scratch: the shipping game's
  `URender::OccludeBsp` clears+recomputes them every frame from the camera, and `IsCsg` collision
  strips 0x10 before testing — no reader consumes the persisted bits. The gate masks `node_flags &
  ~0x18`; every other node-flag bit (NotCsg/NotVisBlocking/IsFront/…) stays compared.
*(The **point-dedup near-tie** — the UNATCO x=448 node-plane `W` / CSG-soup `FPoly.Base` / `Brush`
`Region` divergence, and the same-class WanChai N19 case — was a STOPGAP mask and is now FIXED FAITHFULLY,
not excluded. Native's incremental CSG dedups points with the editor's radius-pruned `FindNearestVertex`
descent over the live world tree (`bspcsg.rs::find_nearest_vertex`), walked in native's live child
convention; the missing piece was that native's incremental tree carries the CSG iFront/iBack convention
(swapped vs the engine), so the descent must swap near/far. With that, UNATCO N8 and WanChai N19 gate
byte-exact with NO mask — node `W`, soup base, and `Brush` `Region` all match. Spike
`spikes/2026-09-05-faithful-dedup-fix-attempt/`; the gate's tie mask + `_BRUSH_MASKED_PROPS` Region entry
are removed; regression `test_n8_dedup_faithful_fix.py`.)*

Any NEW candidate exclusion needs an opus review confirming inconsequence + the owner's explicit yes
before it counts. No content carveouts (Movers included — native must build their private models).

## The method — lockstep ladder, one actor at a time

Drive FIVE levels in LOCKSTEP: **UNATCO `03_NYC_UNATCOHQ`**, **WanChai `06_HongKong_WanChai_Market`**,
**NYC_Bar `02_NYC_Bar`**, **Island `01_NYC_UNATCOIsland`** (outdoor/statues), **OceanLab
`14_OceanLab_Lab`** (underwater/movers). For N = 1, 2, 3, … (N = actor count, trunk order):

1. Build the first N actors of all five levels BOTH ways (native + the UED22 reference).
2. Compare each with the parity gate (below).
3. Fix every divergence on all five until each is byte-exact at N — with a faithful fix that moves
   native's algorithm toward UED22's (prime directive), never a mask. Each fix: one subagent builds
   it, another reviews it, the first fixes the review findings; then re-verify all five.
4. Squash-merge once all five pass at N; re-verify against fresh master.
5. Only then advance to N+1. Never advance while any of the five isn't byte-exact at N.

N=1 is LevelInfo only (empty world) — native builds it (empty world Model). Iterate at small N;
a full-level editor rebuild is ~24 min, so grow N, don't jump.

### Re-verifying N=1..NX after a core change

Any change to native's CSG/BSP/lighting core (not a gate-only change) can, in principle, move an
already-passing N — re-verify N=1..NX per level with **`ladder_run.py`** (below), not a subagent
driving `actor_parity.py`/`parity_gate.py` by hand one N at a time.

Run the re-verification **in the background and do not let it block forward ladder work**: if the
fix is expected to hold (it passed its own targeted N8/N19-style validation), start extending the
ladder past the current NX while the N=1..NX back-verification runs in parallel, rather than gating
all further work on it finishing first. Only stop forward progress if the back-verification actually
reports a bail — then treat that bail as a real regression and stop to fix it before going further.

### Pushing NX forward: script until it bails, agent only to diagnose (owner ruling, 2026-09-05)

Mechanically walking N, N+1, N+2, … forward when nothing is failing costs no judgment and should cost
no agent tokens: run **`ladder_run.py`** as a plain background script (no LLM in the loop) to extend a
level past its current NX. It builds, gates, and bails at the first non-parity N on its own.

Dispatch a subagent ONLY once the script reports a bail — scoped to diagnosing and fixing that one
divergence (root cause + faithful fix + re-verify from where it bailed), not to babysit the sweep.
Never dispatch an agent whose job is "push N forward and see what happens" — that is exactly what the
background script is for. An agent asked to push a range may find real failures and fix them in the
same pass (good — do not stop it mid-diagnosis just because it also ran some sweeping); the ruling is
about not STARTING an agent for the mechanical part, not about interrupting one that has found real work.

### The Parity Ladder artifact — MUST be kept current (owner ruling, 2026-09-05)

The campaign's live status — highest byte-exact N per level, and what blocks the next N — is published
as a claude.ai Artifact: **"Parity Ladder"**, <https://claude.ai/code/artifact/f5662f6e-b17e-45f9-9451-818b0e3d0b34>.

**It is a plain static page, rendered from data — NOT the `db` capability.** An earlier version used
`write_db` against a `levels` collection with a live in-page read; the owner ruled that out
(2026-09-06) after the live read proved unreliable across viewing contexts and a subagent's stale
`write_db` call silently clobbered good data. **Never call `write_db`/`read_db` on this artifact.**

**Whenever a level's highest verified N changes, or its blocking divergence changes, in the same pass:**
1. Edit `dev/docs/spikes/2026-09-03-incremental-actor-parity/harness/parity_ladder_data.json` — one
   object per level, keyed by `slug` (`unatco`, `wanchai`, `bar`, `island`, `oceanlab`), fields
   `{name, codename, highest_n, total_actors, status ("advancing"|"blocked"), blocker, board, updated}`.
2. Render it: `render_parity_ladder.py -o <path>.html` (same dir; reads the JSON + the
   `parity_ladder_template.html` template — never hand-edit the template's embedded `SNAPSHOT`).
3. Publish `<path>.html` with the `Artifact` tool, `action: "publish"`, the URL above as `url`.

This is not optional bookkeeping: the artifact is how the owner reads ladder state without
re-deriving it from board items or chat scrollback. If a subagent found this file before this
correction landed and still calls `write_db`, that call is a no-op on a page nothing reads from
anymore — check for it and switch to the JSON+render+publish flow instead.

## THE parity script (do not reinvent)

**`dev/docs/spikes/2026-09-03-incremental-actor-parity/harness/parity_gate.py`** is the single
canonical parity-comparison entry point. It encodes the exact bar above (identity/permutation-based,
the exclusion set, the surviving-Actors assertion) and gives a PASS/FAIL. Use it; do not write a new
comparison from scratch. `actor_parity.py` (same dir) drives the first-N-actors subset build + gate.

**`ladder_run.py`** (same dir) is the canonical SEQUENTIAL runner: `--dx <shipped.dx>
[--dx <shipped2.dx> ...] [--from N] [--to N]` walks N ascending per level and **bails at the first
non-parity N** for that level (moving on to the next `--dx`), printing a running log and a final
per-level summary. It always rebuilds native (cheap) and reuses a cached editor ref unless
`--force-ref` (the editor build is the slow half); it deletes each N's native build + subset scaffold
right after gating, pass or fail, so a long walk does not accumulate disk. Use it for the whole-ladder
re-verification above and for any "does this still hold N=1..NX" question — do not write a new N-sweep
loop from scratch.

## Testing (project rule, owner 2026-09-04)

Tests must NOT block the parity work. For this project specifically:

- **Run only the FEW tests relevant to the change — never the whole `pytest` suite.** This applies to
  subagents AND the main session. The full suite is slow and crashes on the shared `/tmp` (512 MB,
  other sessions churn it). Relevant files are typically `uedcli/tests/test_native_roundtrip.py`,
  `test_materialize_defaultbrush.py`, `test_materialize_verb.py`, `test_normalize.py`, and
  `test_board.py` (only when board items changed).
- **Always in a STABLE repo dir**, never the shared `/tmp`: `TMPDIR=$PWD/_scratch/pttmp` and
  `pytest -p no:cacheprovider -o cache_dir=_scratch/pttmp/pc`. Never pipe `bin/test`/`pytest` through
  `tail` (it masks the exit code).
- **Run tests in PARALLEL with the build/fix work, not as a gate** — they don't hold up a build or a
  merge. **Bake any needed test fix into the same subagent change** that touches the code.
- `cargo test` (the native core goldens) is fast and runs via the build image; keep it green, but it
  is not the bottleneck — pytest is.
- Pre-existing reds on master unrelated to this work: `test_doc_links`, `test_native_lit_room_ships_light_export_refs`.

## Where the detail lives

- Process + rulings: `dev/docs/board/to-build/native-materialize/incremental-lockstep-full-structural-parity/`,
  `dev/docs/board/to-build/native-materialize/faithful-incremental-bsp-dedup-rewrite/` (the point-dedup
  fix, landed).
- Cause/exclusion findings: `dev/docs/board/inbox/ued22-world-bsp-differs-per-ingest-verb-paste/`,
  `dev/docs/board/inbox/n-1-built-parity-blocked-by-map-rebuild-object/`
- Serialization foundation: `dev/docs/spikes/2026-09-02-unbuilt-structure-parity/`
- Native engine: `uedcli-native/` (Rust), `uedcli/native/` (Python bridge), `uedcli/apply.py`
  (`_materialize_native`).
- Parity harness: `dev/docs/spikes/2026-09-03-incremental-actor-parity/harness/` (`parity_gate.py`,
  `actor_parity.py`, `ladder_run.py`, `prune_ref_cache.py` — caps the cached-editor-ref cache at a
  size budget, LRU-by-creation-time, always keeps each level's highest-N ref; run it if `_scratch/`
  disk usage becomes a problem, never by hand-deleting refs).

## Open blockers per level (2026-09-07) — read before pushing that level further

Each is scoped/root-caused, none masked. Pick one up by reading its board item first.

Ceilings, all re-verified from N=1 against the current binary (2026-09-07): **UNATCO 225,
NYC_Bar 152, OceanLab 202, Island 331, WanChai 57.** Two of the five next blockers are the SAME
shape — one leaf gets a permeating-light run entry UED22 leaves out (UNATCO 226, WanChai 58) — so
the permeating flood is where the campaign's leverage is.

- **UNATCO**: N=163 is FIXED
  (`dev/docs/board/done/unatco-n-163-world-model2-lights-and-lightbits/`) — the 7 extra
  `Model.Lights` entries and 217 extra `LightBits` bytes came from the missing ZONE RETIRE described
  under OceanLab below, not from anything UNATCO-specific. Byte-exact **N=1..225** (was 162); bails
  at **N=226** on one leaf's permeating-light run —
  `dev/docs/board/inbox/unatco-n-226-leaf-12-gets-a-permeating-light157/`. Root-caused 2026-09-12: a
  live gdb capture of the editor's own flood (same method as Island N=332 below) confirms the SAME
  unresolved mechanism — native's `FLinePlaneIntersection` lands a beam-clip crossing bit-for-bit on a
  shared portal vertex (a true tie, collapsing the edge to zero and dropping it as a no-op constraint),
  while the editor's own capture of the identical crossing lands ~1 ULP off it. Second confirmed
  reproducer of the Island N=332 tie; not fixed, no mask. That investigation also found Island's
  "x87 vs SSE" hypothesis very likely wrong — `spikes/2026-07-15-native-materialize/41-fp-model-x87-vs-sse.md`
  already showed this build's `Engine.dll`/`Editor.dll` are SSE2-only with zero x87 control-word use —
  so the real cause is more likely an unreplicated operation-order effect, still needing a register-level
  gdb single-step to pin down. 2026-09-13: the follow-on candidate — `FVector::SafeNormal`'s x87
  precision-control field running at PC=`11` (extended) instead of the PC=`10` (double) native's `f64`
  model assumes — is REFUTED by a live `fctrl` probe (measured `0x027f`, i.e. PC=`10`, exactly matching
  native's model). `dev/docs/spikes/2026-09-12-safenormal-fpu-precision/spike.md`. No code change; the
  real mechanism is still open.
  N=116 needed no fix and was never a real divergence
  (`dev/docs/board/done/unatco-n-116-world-model2-light-runs-differ-on/`): the 941-against-940
  `Model.Lights` bail came from a STALE wheel. Cargo decides freshness by mtime, so a crate restored
  with older timestamps is not rebuilt — six builds labelled with six different commits all ran one
  binary. Fixed in `bin/_venv.sh`; `dev/docs/board/done/native-ext-binary-not-stable-across-builds/`,
  `dev/docs/spikes/2026-09-07-native-ext-build-staleness/`. Codegen was ruled out by measurement:
  `-C opt-level=1 -C codegen-units=1` and `-C target-cpu=native` leave the whole leaf-9 margin trace
  byte-identical, and four from-scratch builds are sha256-equal. The N=29
  blocker is FIXED
  (`dev/docs/board/done/unatco-n-29-world-model2-vert-rings-reference/`) — the divergence was one
  surf's `Texture` ref, not the vertex rings (all 91 live node rings were coordinate-identical; the
  391 differing `FVert`s were gate-excluded orphan slots). An untextured poly shipped
  `brush_marshal`'s per-brush texture dedup ordinal as an object ref, because
  `unbuilt._patch_native_surf_refs` only overwrote `texture_ref` when the poly named a texture.
  Diagnosing a `Verts` diff: run `harness/ring_diff.py` FIRST — `model_dump.py` reports every
  orphan slot as a difference, which is what sent the N=29 item down the vertex-ring path. The
  step-6 frustum-cone reject the N=26 work left open is ported too
  (`dev/docs/board/done/port-occludebsp-frustum-cone-subtree-reject/`).
- **WanChai N=45, OceanLab N=93, Island N=123 are all FIXED** (2026-09-07,
  `dev/docs/spikes/2026-09-07-gather-box-verdict/`) — one f32 rearrangement in the permeating-light
  beam clip. `FPoly::SplitWithPlaneFast` takes its crossing vertex from `FLinePlaneIntersection`
  (`Engine.dll 0xa07c0`), not from an `alpha` between the two `PlaneDot`s; the two agree in exact
  arithmetic and differ in the last ulps, and a crossing landing exactly on a grid coordinate
  collapses the next hop's clip edge to zero length, which `clip_beam` then skips as degenerate while
  the editor still clips by it. Root-caused against a live `FEditorVisibility::ActorVisibility`
  capture: before the fix 10 of WanChai N=45's 11 lights already matched the editor leaf for leaf and
  crossing for crossing; after it, all 11 do.
  Two long-standing items closed as MIS-MEASUREMENTS in the same pass, both worth knowing before
  trusting a lighting diff:
  - `lmdiag.py` read `FLightMapIndex.VClamp` where `iLightActors` is, inventing WanChai's "four
    divergent Spotlight22 runs" and a multi-day rasterizer port that was never needed. Fixed.
    `Model.Lights` is TWO arrays: `lmdiag.py` covers region 2 (per-surf runs) only — check region 1
    (per-leaf permeating lists) too, with
    `2026-09-07-gather-box-verdict/harness/leaf_perm_diff.py`.
  - the box-test probe captured `URender::BoundVisible`'s return, which under `bUseZones` is half the
    decision (`0x100193ba` NULLs the span pointer; `OccludeBsp` runs the span test per active zone
    afterwards). Captured properly, native's box occlusion matches the editor on every call of
    OceanLab N=48 and WanChai N=45 — same set, same ORDER, same rectangles, same verdicts.
  WanChai then advanced to byte-exact **N=1..57** and bails at **N=58** —
  `dev/docs/board/inbox/wanchai-n58-leaf-51-permeating-light-over-included/`. Root-caused 2026-09-13:
  a THIRD confirmed instance of the Island N=332 / UNATCO N=226 one-ULP `FLinePlaneIntersection`
  crossing tie (a beam-clip vertex lands exactly on a grid coordinate in native, one ULP off it live),
  this time one hop upstream of the leaf-51 symptom — the `45->55` beam's own closing vertex — and for
  the first time changing which PORTAL a beam-clip survives (`SP_Back` vs `SP_Split`), not just which
  vertex a permeating flood carries. Not fixed; still needs the register-level single-step the other
  two also stopped short of.
- **UNATCO, N=226**: `dev/docs/board/inbox/unatco-n-226-leaf-12-gets-a-permeating-light157/` — a
  SECOND, independent case of the same shape, NOT closed by the above: leaf 12 still carries
  `Light157` where UED22 leaves it out (measured after the fix; `Model.Lights` 2953 vs 2952, per-surf
  runs 0 differing).
- **NYC_Bar**: N=59 is FIXED (`dev/docs/board/done/nyc-bar-n-59-brush-region-zone-and-ued22/`) —
  its last three residuals (world-node `NF_IsFront`/`NF_IsBack`, the mover models' `LightMap`, and
  the mover `Polys`' `iLink`/`iBrushPoly`) were one thing: the moving-brush half of
  `shadowIlluminateBsp`, which bails when the world `Model` has no nodes and so only appears once a
  level has its first world brush. Ported as `unbuilt.light_apply_movers`
  (`dev/docs/spikes/2026-09-06-nycbar-n59-light-apply-movers/`); `native-geometry-path-leaves-mover-
  models-unbuilt` is closed with it — the models were built all along. N=70 is fixed too
  (`dev/docs/board/done/nyc-bar-n-70-zone-actor-bound-to-the-alphabetically/`): `resolve_zone_actors`
  walked the name-keyed `level.actors` dict, so `ZoneInfo17` beat `ZoneInfo5` to the zone they share.
  N=113 is fixed too (`dev/docs/board/done/nyc-bar-n-113-brush69-region-lands-outside-the/`) — the
  point-region descent evaluated the node plane in f64 where `FPlane::PlaneDot` is single-precision
  SSE, so a pivot lying ON a node plane took the wrong child; same fix as Island N=10
  (`dev/docs/spikes/2026-09-06-pointregion-planedot-f32/`). N=119 is fixed too
  (`dev/docs/board/done/nyc-bar-n-119-world-model2-lightmap-array-order/`) — UnrealEd's lightmap
  allocate walk (`Editor.dll 0x100a4a90`) allocates a record only at a node with `NumVertices != 0`,
  and a vertex-less node does not CLAIM its surf either, so a surf sitting on both gets its record at
  the later non-empty node; native claimed at the first node it saw
  (`dev/docs/spikes/2026-09-06-lightmap-alloc-zero-vert-gate/`). N=151 is fixed too
  (`dev/docs/board/done/nyc-bar-n-151-world-model2-leaf-permeating-light/`) — the permeating-light
  beam clip built `FPlane(Light, ClipPoly[j], ClipPoly[jPrev])` from an UNNORMALIZED cross product,
  so `SplitWithPlaneFast`'s 0.25 epsilon was divided by that cross product's length (~1e4 at room
  scale) and stopped gating anything; the flood then carried slivers the editor rejects whole
  (`dev/docs/spikes/2026-09-06-permeating-beam-plane-normalize/`). Byte-exact **N=1..152** (was 118);
  bails at **N=153** on the world `Model2`'s PER-SURF light runs — three `LightMap` records get an
  `iLightActors` run UED22 leaves at -1 (`Lights` 484 vs 478, `LightBits` 6003 vs 5891), with the
  leaf permeating region clean. Root-caused 2026-09-12, not yet fixed: `Light5` sits beside a closed
  door (`DeusExMover9`, a `Mover`) standing exactly in the world-BSP opening between it and 3 stair
  treads; native's world-level `GetVisibleSurfs`/raytrace never sees the mover's geometry, so it
  lights the treads straight through the closed door AND (the mirror-image half, `model
  model_deusexmover9` also fails N=153) fails to light the door's own face with the same light. This
  is the `visible_surfs.rs` "moving-brush filter (step 3)" gap the port flagged as "assumed to never
  fire" — confirmed here to fire. The real fix unifies the world and mover light bakes into one scene
  (per `unbuilt.light_apply_movers`'s own docstring, UED22's `FMovingBrushTracker` mirrors each mover
  poly into a transient world surf for the bake) — a structural change, scoped as follow-up, not a
  local patch —
  `dev/docs/board/inbox/nyc-bar-n-153-world-model2-lightmap-runs-ued22/`.
- **Island**: N=6, N=10 and N=93 are all FIXED. N=6 was the Vectors pool — native keeps
  the incremental pool across the repartition instead of rebuilding it from the surviving surfs
  (`dev/docs/spikes/2026-09-06-island-n6-vector-pool/`,
  `dev/docs/board/done/island-n6-vector-pool-order/`). N=10 was `Brush1359`'s `Region` iLeaf, the
  same f32 `FPlane::PlaneDot` fix as NYC_Bar N=113
  (`dev/docs/spikes/2026-09-06-pointregion-planedot-f32/`,
  `dev/docs/board/done/island-n-10-brush1359-region-ileaf-13-vs-18/`). N=93 was
  `resolve_zone_actors` picking zone actors by class-NAME suffix, which skipped `DeusEx.WaterZone`
  (a real `Engine.ZoneInfo` subclass) and let its zone fall back to the LevelInfo; it now decides by
  ancestry, `ULevel::SetActorZone`'s own `IsA(AZoneInfo) && !IsA(ALevelInfo)`
  (`dev/docs/board/done/island-n-93-zone-actor-missed-resolve-zone/`). Byte-exact **N=1..122** (was
  92); bails at **N=123** on the world `Model2`'s LEAF light runs — native gives leaf 26 a
  permeating-light run UED22 leaves empty (1 leaf of 163; `Lights` 1729 vs 1727, every other array
  byte-exact). Two root causes have now been RULED OUT by measurement
  (`dev/docs/spikes/2026-09-06-island-n123-portal-graph/`). It is not the NYC_Bar N=151 beam-plane
  bug, and it is not the PORTAL GRAPH either: Pass B is now a faithful port of `MakePortals` /
  `MakePortalsClip` / `BuildInfiniteFPoly` (the `WORLD_MAX` surf-plane quad, `FindBestAxisVectors`,
  the ancestor stack, `SplitWithNode(VeryPrecise=1)` with its `SP_Coplanar` drop, and `AddPortal`
  with native's invented `MIN_AREA` gate removed), and the editor's own `Portalized:` log line reports
  **580 portals / 163 leaves / 427 nodes**, exactly what native builds. The flood's every gate,
  `SplitWithPlaneFast` and `ActorVisibility`'s clip loop are re-verified instruction-exact; the
  decisive constraint reduces to a 1.90-unit clearance between the 27→26 portal quad and node 344's
  plane, measured on model points that are byte-identical in both builds. The last unfaithful piece
  of the beam clip is gone too and did not move it: `clip_beam` now takes `FPlane(A,B,C)`'s own
  winding-derived orientation instead of forcing it by a sign-sum over the clip poly
  (`dev/docs/spikes/2026-09-07-permeating-beam-plane-winding/`) — provably the same thing on convex
  clip polys, different only on degenerate edges, and no level's ceiling moved. **N=123 is now FIXED
  too** — the crossing VERTEX, not the gates: `SplitWithPlaneFast` takes it from
  `FLinePlaneIntersection`, whose f32 differs from `alpha = dp/(dp-ds)` in the last ulps, and a
  crossing landing exactly on a grid coordinate collapses the next hop's clip edge (see the WanChai
  bullet above). Island then ran clean past 298 (where it previously ran out of cached refs) up to
  byte-exact **N=1..331**; the OceanLab N=153/N=155 fixes below carried it past 123 with no
  Island-specific work. Bails at **N=332** on a NEW, different-mechanism case of the same shape
  (`dev/docs/board/inbox/island-n-332-leaf-273-permeating-light-vertex-tie/`): leaf 273 carries
  `Light124` where UED22 leaves it out, root-caused to a genuine vertex COINCIDENCE — a portal
  vertex shared exactly with an adjacent portal, where one `FLinePlaneIntersection` crossing lands
  a hair below the shared point in native and a hair above it in a live editor capture, same
  formula and same inputs, opposite sign of a sub-ULP residual. Suspected x87-vs-SSE
  double-rounding, unconfirmed — the disassembly-verified formula reproduces native's own output
  bit-for-bit by hand, so this is not a wrong formula to correct, only an unresolved
  register-level effect. Not fixed; no mask added. Island's ladder cannot advance past N=332 until
  this closes — see the board item for the full trace and the next step (single-step the editor's
  real `SafeNormal`/`FLinePlaneIntersection` under `gdb` at this exact crossing). 2026-09-13: the
  `SafeNormal` x87-extended-precision candidate is REFUTED by a live `fctrl` probe (measured `0x027f`,
  PC=`10`/double, exactly matching native's `f64` model) —
  `dev/docs/spikes/2026-09-12-safenormal-fpu-precision/spike.md`. No code change; the register-level
  single-step is still the open next step.
- **OceanLab**: N=46 is FIXED
  (`dev/docs/board/done/oceanlab-n46-world-model2-bounds-leafhulls-and/`,
  `dev/docs/spikes/2026-09-06-passd-kill-split-original/`) — Pass D's zone SPLIT must KILL the
  original chain node and append every fragment as a new node, so the post-Pass-D `bspCleanup`
  promotes the dead node's coplanar successor (inheriting its children, mirrored on opposite
  facing); native reused the original in place, which left it heading two chains and diverged every
  `Bounds`/`LeafHulls`/`LightMap` walk after it. Byte-exact **N=1..47** (was 16, then 33, 43, 45
  across three earlier fixes this session: a native texture resolver no longer guessing a package
  when none is loaded, the point-dedup repartition fix below, and the gather pass's plane test now
  gating the raytrace loop —
  `dev/docs/board/done/oceanlab-n44-world-model2-lights-array-has-2/`). N=48 is FIXED too
  (`dev/docs/board/done/oceanlab-n48-world-model2-lightbits-differ-on/`,
  `dev/docs/spikes/2026-09-07-oceanlab-n48-lightbits/`) — and so, by the same fix, is UNATCO N=163.
  The gather never retired a zone whose span buffer had emptied (`URender::OccludeBsp`
  `render.dll 0x1001a737`–`0x1001a7e5`: `FSpanBuffer::ValidLines <= 0` drops the zone from the
  active set, and an empty set ends the face's traversal), so native kept descending into subtrees
  the editor had abandoned and wrote `NF_BoxOccluded` on nodes UED22 never box-tests. That bit is
  gate-excluded but NOT inert: a `PF_BrightCorners` shadow ray passes `ExtraNodeFlags = 0x14`, so a
  marked node stops being solid and stops shadowing. Live probe at the first `illuminateSurf`:
  UED22 carries the bit on `{32, 80, 160, 352}`; native carried it on twelve nodes, one of which
  (node 512) unshadowed three surfaces' edge lumels. With the retire ported — plus step 6, the
  frustum-cone subtree reject — native runs exactly the editor's 1218 box tests and ends with
  exactly its flag set. **N=93 is FIXED too** — one leaf's permeating-light run, the crossing-vertex
  rounding in the WanChai bullet above. **N=153 and N=155 are FIXED too**
  (`dev/docs/board/done/oceanlab-n-153-world-model2-split-vertex-29-ulp/`,
  `dev/docs/board/done/oceanlab-n-155-zone-connectivity-misses-zone-0/`,
  `dev/docs/spikes/2026-09-07-oceanlab-n153-temp-brush-rsp/`), both faithful ports of routines the
  campaign had already decoded but never wired up. N=153: `bspBrushCSG` builds the temp brush BSP
  with `RebuildSimplePolys=1` (`0x35b85`), so a COPLANAR face SHARES the splitter's surf and
  allocates no `pBase`/`vNormal`/texture axis of its own; native gave each face its own surf, which
  let a coplanar sibling's authored texture axis (`3f3504e6`,`3f350508`) into the temp `Vectors`
  pool ahead of a later face's normal (`3f3504f4`,`3f3504f4`) — and `bspAddVector(exact)` deduped
  the normal onto the axis. Every world edge that asymmetric plane cuts lands 29 ULP off
  (`152.0002` vs `151.99976`). N=155: Pass F (`FEditorVisibility::BuildConnectivity`, `0xa7960`) is
  a NODE walk over `PF_Portal` surfs reading `Node.iZone[0]/[1]`, zone 0 included; native walked the
  Pass-B portal FRAGMENT list filtered by the zone-barrier set and skipped every pair touching zone
  0, leaving zones 0 and 1 mutually unconnected. Byte-exact **N=1..202** (was 93); bails at **N=203**
  on the world `Model2`'s `points` array — a genuine 2-ULP value pair (`x` off by
  `2·2^-15`), not an index/order shift (full multiset diff confirms). Neither the raw brush
  transform nor a single-hop `line_plane_intersection` against the obvious candidate plane
  reproduces either side's stored value, and live crossing-vertex instrumentation found no
  `split_with_plane` crossing that emits the divergent bits directly — likely the same point-pooling
  bug CLASS as the fixed N=13/WanChai-N40 `MergeNearPoints` issue, but not the same cause; not
  closed. `dev/docs/board/to-spike/oceanlab-n-203-world-model2-split-vertex-ulp/`.
- **Standing stopgaps, all levels**:
  `dev/docs/board/inbox/repartition-point-dedup-still-uses-a-linear/` — repartition dedups points
  with a linear pool scan; the editor descends and appends on a miss (`AddThing(..., !FastRebuild)`
  with `FastRebuild = 1`). And `dev/docs/board/inbox/portal-graph-builds-self-portals-from-stale/` —
  Pass B drops a portal whose two leaves are the same, where `AddPortal` has no such test; without
  it the permeating-light flood loops forever on WanChai N=35. Both owed a faithful fix.
- A cached editor ref goes stale two ways — a truncated trunk extraction, and a change to the golden
  recipe under it. Run `harness/verify_refs.py` before trusting a ladder result built on an inherited
  cache (`dev/docs/board/inbox/corrupt-trunk-cache-silently-passes-the-ladder/`).
- Live status + these same blockers, kept current: the **Parity Ladder** artifact (see above).
