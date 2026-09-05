# Native `level materialize` — full byte parity with UnrealEd (UED22)

This is the single source of truth for the native-materialize parity campaign: the goal, the
reference we compare against, the exact parity bar, the method, and the ONE script that checks it.
Read this before doing any native-materialize parity work so you don't re-derive it.

## Goal

`level materialize` builds the git-tracked T3D trunk into a `.dx`/`.unr` map file. Two build paths
exist: the **editor-driven** path (drives UED22) and the **native** path (`UEDCLI_NATIVE_MATERIALIZE=1`,
a Rust `uedcli-native` CSG/BSP/lighting engine, no editor). The campaign goal is that the **native
build is byte-identical to UED22's build of the same trunk** — full package bytes, not just counts.

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
- **Point-dedup near-tie** on an axis-aligned node-plane `W`, its CSG-soup `FPoly.Base`, and the one
  downstream `Brush` `Region` it flips (owner-directed + second opus review, 2026-09-05; board
  `native-n8-unatco-rotated-brush-base-fp-diverges`). An editor incremental-dedup-staleness artifact:
  a rotated brush's face base lands between two REAL, distinct `Model.Points` entries `2.16e-4` apart
  (≈7 f32 ULP at x=448); the editor's incremental pool keeps the un-snapped point, native's
  linear-scan dedup snaps to the sibling — so native's `W`/soup-base carry the snapped point's value.
  What the mask hides is BOUNDED to be inconsequential (not proven identity-exact): a `W`/base diff
  masks ONLY when `|dW| ≤ 5e-4` — sub-band, below the engine's ±0.001 zero-extent line-trace band and
  far below the box-collision band, so no trace/point-check/zoning result can change — AND both values
  sit within `1e-4` of a real byte-identical-table-point projection (a plausibility bound, not an
  anchor: a fabricated sub-band value near a real projection would also mask, but is still sub-band).
  A plane SWAP (wrong face) still FAILS: the node **normal** is byte-compared and a wrong-face `W` is
  orders above the band. The one downstream `Brush` `Region` flip is masked separately, resting on the
  disasm that EVERY brush's `Region` is discarded at load (LoadMap `SetActorZone(actor,1,1)`
  recomputes+overwrites it, Engine.dll `0x158930`/`0x161e10`), not on the tie; non-`Brush` `Region`
  stays compared. Faithful fix = a multi-week incremental-CSG-core rewrite (owner-ruled out). Negative
  tests: `test_n8_dedup_tie_mask.py`.

Any NEW candidate exclusion needs an opus review confirming inconsequence + the owner's explicit yes
before it counts. No content carveouts (Movers included — native must build their private models).

## The method — lockstep ladder, one actor at a time

Drive three levels in LOCKSTEP: **UNATCO `03_NYC_UNATCOHQ`**, **WanChai `06_HongKong_WanChai_Market`**,
**NYC_Bar `02_NYC_Bar`**. For N = 1, 2, 3, … (N = actor count, trunk order):

1. Build the first N actors of all three levels BOTH ways (native + the UED22 reference).
2. Compare each with the parity gate (below).
3. Fix every divergence on all three until each is byte-exact at N. Each fix: one subagent builds it,
   another reviews it, the first fixes the review findings; then re-verify all three.
4. Squash-merge once all three pass at N; re-verify against fresh master.
5. Only then advance to N+1. Never advance while any of the three isn't byte-exact at N.

N=1 is LevelInfo only (empty world) — native builds it (empty world Model). Iterate at small N;
a full-level editor rebuild is ~24 min, so grow N, don't jump.

## THE parity script (do not reinvent)

**`dev/docs/spikes/2026-09-03-incremental-actor-parity/harness/parity_gate.py`** is the single
canonical parity-comparison entry point. It encodes the exact bar above (identity/permutation-based,
the exclusion set, the surviving-Actors assertion) and gives a PASS/FAIL. Use it; do not write a new
comparison from scratch. `actor_parity.py` (same dir) drives the first-N-actors subset build + gate.

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

- Process + rulings: `dev/docs/board/to-build/native-materialize/incremental-lockstep-full-structural-parity/`
- Cause/exclusion findings: `dev/docs/board/inbox/ued22-world-bsp-differs-per-ingest-verb-paste/`,
  `dev/docs/board/inbox/n-1-built-parity-blocked-by-map-rebuild-object/`
- Serialization foundation: `dev/docs/spikes/2026-09-02-unbuilt-structure-parity/`
- Native engine: `uedcli-native/` (Rust), `uedcli/native/` (Python bridge), `uedcli/apply.py`
  (`_materialize_native`).
