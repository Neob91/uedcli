+++
priority = "p1"
kind = "docs"
summary = "Owner-ruled process (2026-09-04): drive UNATCO+WanChai+NYC_Bar in lockstep to FULL structural/package-byte parity, one actor at a time, fixing all three exact before advancing."
+++

# Incremental lockstep full-structural-parity process

Owner ruling 2026-09-04. Drive native `level materialize` to FULL parity with UED22, three levels in
LOCKSTEP, one actor at a time.

## Levels (all three, in lockstep)

- **UNATCO** — `03_NYC_UNATCOHQ`
- **WanChai** — `06_HongKong_WanChai_Market` (assumed variant — confirm)
- **NYC_Bar** — `02_NYC_Bar` (assumed variant — confirm)

## What "parity" means

**FULL STRUCTURAL / PACKAGE-BYTE parity — NOT counts.** Every byte of the built `.dx` identical
between native and the UED22 reference: every field of every node/surf/leaf/vert/point/vector, the
name/import/export tables (set AND order), every actor body, and lighting. EXCLUDE ONLY the
owner-ruled per-save-random engine fields: 16-byte package GUID, save timestamps / LevelInfo
`TimeSeconds`, StateFrame `LatentAction`, the six Camera viewport bodies. **No content carveouts**
(movers included). Any NEW candidate exclusion → opus reviewer + owner's explicit yes first.

## The two builds compared at each step

- **UED22 reference**: `MAP NEW` → `MAP IMPORT FILE=<first-N-actors T3D, sacrificial dummy builder
  prepended as Actors[1]>` → `MAP REBUILD` → `LIGHT APPLY` → `MAP SAVE`
  (`build_ued_import_built_golden.py`, dummy on by default; UED22 excludes Actors[1] from CSG, so the
  dummy absorbs the loss).
- **native**: `level materialize` native path (`UEDCLI_NATIVE_MATERIALIZE=1`) of the same
  first-N-actors subset. Native synthesizes its own dummy builder at Actors[1] and skips it
  positionally.

## The loop — for N = 1, 2, 3, … (N = actor count, trunk order)

1. **Build** the first N actors of ALL THREE levels, BOTH ways (native + UED22 reference).
2. **Compare** each level: full package-byte diff (`byte_gate.py`/`structure_diff.py`), masking only
   the ruled per-save-random fields.
3. **Fix** every divergence on ALL THREE levels until each is byte-exact at N. Each fix goes through
   the subagent loop: one subagent builds the fix, another reviews it, the first fixes the review
   findings; then re-verify all three at N.
4. **Squash-merge** the fixes to master once all three are byte-exact at N, then **re-verify** all
   three at N against fresh master.
5. **Only then advance to N+1** (add the next actor). NEVER advance while any of the three is not
   byte-exact at N.

## Constraints

- Iterate at small N (fast builds); a full-level editor rebuild is ~24 min, so do NOT jump to full
  levels — grow N.
- Owner makes all real decisions — ask, never overrule; surface new exclusion candidates.
- Harness note: `subset_parity.py` currently subsets by BRUSH prefix + compares counts/content; it
  must be extended to (a) ACTOR-prefix subsets in trunk order and (b) full package-byte comparison
  (`byte_gate`/`structure_diff`) for this process.

Refs: `board/ued22-world-bsp-differs-per-ingest-verb-paste` (the Actors[1] cause + dummy convention),
`spikes/2026-09-03-incremental-actor-parity`, `spikes/2026-09-02-unbuilt-structure-parity` (byte tools).

## Owner ruling 2026-09-04 — consolidate to ONE parity script

`parity_gate.py` is THE canonical parity-comparison script (documented in root `NATIVE-MATERIALIZE.md`,
auto-loaded from `CLAUDE.md`). Purge the recent overlapping DRIVERS once parity_gate absorbs the
primitives it needs: delete `subset_parity.py`, `actor_parity.py`, `parity_report.py`,
`parity_compare.py`, `parity_lib.py`/`parity_pipeline.py` (fold needed bits in), `sweep_*`,
`breadth_gate.py`, and their now-orphaned tests (`test_parity_*`, `test_sweep_*`) — AFTER parity_gate
is self-contained and still passes N=1 on all three levels + `bin/test` green. Keep the reference
BUILDERS (`build_ued_import_built_golden.py` etc.) and historical spike harnesses that are cited
evidence but are not parity drivers. Do NOT delete the primitives parity_gate still imports until
they're inlined.
