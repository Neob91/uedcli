+++
priority = "p1"
kind = "implement"
summary = "Faithful incremental-BSP-core point-dedup: reproduce UED22's FindNearestVertex so native's point table + node-plane W + soup FPoly.Base byte-match, retiring the x=448 stopgap mask and fixing WanChai N19. Owner-committed 2026-09-05 ('honor literally')."
+++

# Faithful incremental-BSP-core point-dedup rewrite

Owner ruling 2026-09-05 ("honor literally", prime directive): the point-dedup divergence class is fixed
by reproducing UED22's algorithm, NOT by masking. This retires the x=448/N8 stopgap mask in
`parity_gate.py` and fixes WanChai N19. The lockstep ladder HOLDS at N=18 until this lands. Widening the
mask (incl. a decoupled poly-base tolerance for N19) is ruled out.

## The divergence (one class, two live cases)

Native `bsp_add_point` dedups points with a LINEAR SCAN that snaps a face's raw transformed `FPoly.Base`
onto a nearby already-present `Model.Points` entry. The editor uses an INCREMENTAL spatial index
`UModel::FindNearestVertex` (Engine.dll `0x1adeb0`, helper `0x1adb60`, index at `Model+0x5c`) whose
hit/miss depends on which points were added so far in the incremental CSG tree walk — so two genuinely
distinct authored bases ~2e-4 apart get MERGED by native but kept DISTINCT by the editor.

- UNATCO N8 (`Brush74`): node-plane W + soup base diverge 2.16e-4. Masked today (stopgap).
- WanChai N19 (`Brush405`, 3 coplanar Step faces): soup base diverges 1.007e-3 in-plane (dW=0). FAILS.

## Why it is a core rewrite (spike 2026-09-05)

`spikes/2026-09-05-faithful-dedup-fix-attempt/` re-confirmed with fresh disasm: FindNearestVertex
traverses the whole live subtree (iFront/iBack + coplanar iPlane chain, no liveness prune), so the miss
is a tree LINKAGE/CONTENTS fact, not a descent-algorithm one. Both prior ports fail — raw-base carry
regresses the siblings the editor legitimately snaps; the FNV port over native's CURRENT tree still snaps
x=448 and shifts the point table 76→81. The fix must reproduce the editor's incremental tree wiring
(surf-base / vert-pool / live-dead / front-back reachability) bit-exact at every `bspAddPoint` — a
re-derivation of the ~5.4k-LOC incremental BSP core. Multi-week, HIGH regression risk to the green corpus.

## Bar

Native's `Model.Points` table AND every node-plane `W` / soup `FPoly.Base` byte-match the editor with NO
gate mask, across the 5-level ladder (N=1..current), UNATCO N8, and WanChai N19; cargo green; the x=448
mask + tie-code removed from `parity_gate.py`. Staged (see `plan.md`); never merge a stage that isn't
corpus-green.
