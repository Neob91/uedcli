# Plan — faithful incremental-BSP-core point-dedup

High-risk core rewrite; stage it so each stage is independently verifiable and never regresses the green
corpus. Work in an isolated worktree; do not merge a stage until all 5 levels (originals N=1..16, Island
N8/N12, OceanLab N3) + UNATCO N8 + WanChai N19 gate byte-exact.

## Stage 1 — Instrument + pin the divergence (foundation)
- Stage-gated trace of native's incremental `bsp_add_point` calls (base queried, added-vs-snapped, target
  idx, tree-node context) for UNATCO N8 + WanChai N19.
- Decode + reproduce the editor's `FindNearestVertex` spatial-index CONTENTS at each query, from the
  disasm (Engine.dll `0x1adeb0` / helper `0x1adb60`, index at `Model+0x5c`).
- Deliverable: the exact set of `(query base, native-snap vs editor-miss)` divergences WITH the tree-state
  reason for each — the reachability facts the port must reproduce. Committed harness under the spike dir.

## Stage 2 — Port the FindNearestVertex spatial index
- Implement the editor's `Model+0x5c` index (build / insert / query) in the Rust core, faithful to disasm.
- Gate: on the UNATCO N8 tree AS-BUILT, the index returns the editor's hit/miss for the divergent bases.

## Stage 3 — Reproduce the incremental tree wiring the index depends on (the hard part)
- Make native's incremental CSG surf-base / vert-pool / live-dead / front-back reachability byte-match the
  editor at every `bspAddPoint`, so the point table stays 76/76 (no 76→81 blow-up) AND x=448 stays distinct.
- Gate incrementally per level/N; keep the corpus green at EVERY commit (bisect-friendly).

## Stage 4 — Retire the mask + regression-pin
- Remove the x=448 mask + tie-code from `parity_gate.py`; confirm UNATCO N8 passes WITHOUT it and WanChai
  N19 passes. Add cargo + gate regression tests. Update `NATIVE-MATERIALIZE.md` exclusion set (drop the
  stopgap entry). One opus review; fix findings.

## Stage 5 — Resume the ladder past N=18
- With the class fixed, advance the lockstep ladder from N=19.

## Notes
- The 2026-09-05 spike already pinned the wall; start from its harness (`gate_nomask.py`,
  `soup_base_diff.py`, `decode_fnv_traversal.py`) on branch `worktree-agent-a3ff91a08729fc046`.
- Correct the x=448 board done-item's stale detail when convenient: diverging surf is `iSurf=36, pBase=29`
  (editor W = −Points[32].x, a real point but not this surf's pBase).
