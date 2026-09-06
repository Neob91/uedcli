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
as a claude.ai Artifact: **"Parity Ladder"**, <https://claude.ai/code/artifact/f5662f6e-b17e-45f9-9451-818b0e3d0b34>
(`db` capability, collection `levels` keyed by level slug: `unatco`, `wanchai`, `bar`, `island`, `oceanlab`).

**Whenever a level's highest verified N changes, or its blocking divergence changes, update the
artifact in the same pass** — `Artifact` tool, `action: "write_db"`, `collection: "levels"`, the
level's slug as `doc_id`, fields `{name, codename, highest_n, total_actors, status
("advancing"|"blocked"), blocker, board, updated}`. This is not optional bookkeeping: the artifact is
how the owner reads ladder state without re-deriving it from board items or chat scrollback. Find its
URL via `Artifact` `action: "list"` if it isn't already in context.

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
  `actor_parity.py`, `ladder_run.py`).

## Open blockers per level (2026-09-05) — read before pushing that level further

Each is scoped/root-caused, none masked. Pick one up by reading its board item first.

- **UNATCO, N=29** (was N=26, closed 2026-09-06): `URender::BoundVisible` + `FSpanBuffer::BoxIsVisible`
  are ported (`dev/docs/spikes/2026-09-06-boundvisible-port/`,
  `dev/docs/board/done/port-urender-boundvisible-box-occlusion-test/`), so the box-occlusion
  `NF_BoxOccluded` bits the shadow-ray walker reads now match; N=1..28 gate byte-exact. The new bail
  at N=29 is a world `Model2` geometry diff —
  `dev/docs/board/inbox/unatco-n-29-world-model2-vert-rings-reference/` (identical nodes and Points,
  391 of 860 `FVert`s naming different Points). Also open, found by the same work:
  `dev/docs/board/inbox/port-occludebsp-frustum-cone-subtree-reject/` — native still box-tests 51
  subtrees per UNATCO N=26 build that UED22's step-6 frustum-cone reject discards.
- **WanChai, N=45**: `dev/docs/board/inbox/wanchai-n45-spotlight22-light-runs-differ-on-4/` — PARKED,
  multi-day rasterizer port (`FSpanBuffer`'s `ClipBspSurf` + fixed-point scanline setup), corpus-wide
  blast radius measured (~20k already-correct decisions per level would move at once).
- **NYC_Bar, N=59**: `dev/docs/board/inbox/nyc-bar-n-59-brush-region-zone-and-ued22/` — Region
  zone-actor, mover base pose, and pawn Foot/HeadRegion all FIXED; two native-geometry gaps remain:
  world-node `NF_IsFront`/`NF_IsBack` (accumulates across multiple CSG-time descents, not a single
  pass) and mover private `Model` geometry not built when real world CSG exists (reopened:
  `dev/docs/board/inbox/native-geometry-path-leaves-mover-models-unbuilt/`).
- **Island, N=5 / OceanLab, N=13**: same residual class — `dev/docs/board/to-spike/
  island-n5-n12-pre-existing-model2-orphan-vert-4/`, `dev/docs/board/to-spike/
  oceanlab-n13-csg-soup-split-vertex-1-ulp/` — 1-5 ULP split-vertex values in the world `Model2`;
  walk order, summation order, plane provenance, and colinear removal all ruled out by disassembly;
  cause not yet found. See also `dev/docs/board/inbox/corrupt-trunk-cache-silently-passes-the-ladder/`
  — a cached trunk extraction can be silently truncated; verify actor COUNT against the level's known
  scale before trusting a ladder result either way.
- Live status + these same blockers, kept current: the **Parity Ladder** artifact (see above).
