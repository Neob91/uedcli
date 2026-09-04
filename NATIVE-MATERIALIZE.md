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

## Where the detail lives

- Process + rulings: `dev/docs/board/to-build/native-materialize/incremental-lockstep-full-structural-parity/`
- Cause/exclusion findings: `dev/docs/board/inbox/ued22-world-bsp-differs-per-ingest-verb-paste/`,
  `dev/docs/board/inbox/n-1-built-parity-blocked-by-map-rebuild-object/`
- Serialization foundation: `dev/docs/spikes/2026-09-02-unbuilt-structure-parity/`
- Native engine: `uedcli-native/` (Rust), `uedcli/native/` (Python bridge), `uedcli/apply.py`
  (`_materialize_native`).
