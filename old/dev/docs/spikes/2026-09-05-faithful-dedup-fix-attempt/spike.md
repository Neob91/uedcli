# Faithful point-dedup fix — attempt + wall (2026-09-05)

Timeboxed attempt at the FAITHFUL fix for the point-dedup divergence class that forces the x=448
mask (UNATCO N8) and a hard fail (WanChai N19). Outcome: **no faithful fix; keep the stopgap.** The
wall is exactly the one the board pinned (`native-n8-unatco-rotated-brush-base-fp-diverges`), now
re-confirmed from fresh builds + disasm, with one board index error corrected (the "two distinct
points" framing is accurate — keep it).

Prior full analysis: `dev/docs/board/done/native-n8-unatco-rotated-brush-base-fp-diverges/overview.md`
and `dev/docs/spikes/2026-09-04-bspaddpoint-dedup-base-provenance/`.

## The class, restated

Native's incremental `bsp_add_point` is a LINEAR scan over all `Model.Points`: a face's raw
transformed `FPoly.Base` snaps to any existing point within `THRESH_POINTS_ARE_SAME` (0.002). The
editor's dedup is `UModel::FindNearestVertex` (Engine.dll `0x1adeb0`), a descent over the CURRENT
`Model->Nodes` — so it MISSES a within-tol point that is not yet a reachable node. Two genuinely
distinct authored bases <0.002 apart: native always snaps them together; the editor sometimes keeps
them distinct (an incremental-staleness miss). Faithful fix = reproduce that incremental miss.

## Reproduced (fresh builds, this spike)

Native rebuilt from this worktree's ext; refs: cached UNATCO `ref_N8`, freshly editor-built WanChai
`ref_N19`. Gate = `2026-09-03-incremental-actor-parity/harness/parity_gate.py`.

- **UNATCO N8**: PASS with the mask; without it (`harness/gate_nomask.py`) FAIL — 2 residuals:
  `Model model2` node-plane W (nodes 29/30) and `Polys@model model2` soup base.
- **WanChai N19**: FAIL even WITH the mask. `harness/soup_base_diff.py` pins it: the whole `Model`
  is byte-identical (nodes/surfs/points/planes — 0 diffs), and ONLY the standalone `Polys@model
  model2` soup diverges, at 3 coplanar Step faces (normal `(0,0,1)`):
  - native base `(0.00061, -3072.0, z)` — a real entry of native's own `Model.Points` (SNAPPED)
  - ued base `(-0.00037, -3072.00024, z)` — raw, in no table (DISTINCT)
  - Euclidean `d = 1.0066e-3`, purely IN-PLANE (`z` identical → node plane W bit-identical, `dW=0`).
  `d` exceeds the mask's `NODE_W_DEDUP_TOL = 5e-4`, so the mask (correctly) does not hide it.

Same mechanism as N8; N19 lands in the in-plane base components because the face normal is axis-Z.

## One board index error (fresh N8 diff — `2026-09-04-.../diff_n8.py`)

The board's "two REAL, distinct Model.Points entries 2.16e-4 apart" framing (and
`NATIVE-MATERIALIZE.md`'s) is **accurate** — verified, do not touch it. The final `Points` table
(76/76, byte-identical) holds real distinct entries at BOTH x-values: `Points[29]=(448.00006,
64.0001, 3e-5)` and `Points[32]=(447.99985, -288.0002, 0)` (also `69/70/72`), `2.14e-4` apart. They
are corners of the SAME face plane (Brush418's `x=447.99985` face): the `y=64` corner deduped to
`448.00006` (Brush420 wired a `y=64` point there first); the `y=-288` corners kept the raw plane x
`447.99985`.

The board's ONLY genuine error is the pBase INDEX in its most-recent section: it says `surf.pBase=32`
"consistent with its own pBase". Fresh diff shows the diverging surf is `iSurf=36` with `pBase=29`
(= `448.00006`) on **both** sides. Every `Surf.pBase` is identical. The ONLY model diff is
`Node[29/30].plane.W`: native `-448.00006` (`= -Points[pBase]·N`, its own snapped corner), editor
`-447.99985` (`= -Points[32].x`, the plane's raw x — a real table point, but NOT this surf's pBase).
So the editor's node W is NOT `Points[surf.pBase]·N`; it froze a base whose x survives in the table
only at the face's `y=-288` corners.

Reconciled mechanism (matches the board's uniform-provenance disasm): the editor's PRE-repartition
incremental pool kept a distinct `447.99985` base point for this surf (FNV miss); `bspBuildFPolys`
copied it into the soup, `bspAddNode` stamped the node plane W from it; the FINAL repartition
re-dedups the surf's `pBase` onto `448.00006` (identical 76-point table) but the node W froze the raw
value. Native's linear scan snaps at the incremental add, so its pre-repartition soup base — and the
repartition-recomputed W — carry `448.00006`. The mask is unaffected: `_node_w_tie` accepts the
editor W because it equals a real table-point projection (`-Points[32].x`).

## New disasm: the coplanar-traversal escape is CLOSED

Candidate scoped fix considered: if `FindNearestVertex` descended only iFront/iBack and a snapped
point were reachable ONLY as a coplanar-chain node's surf-base, native could exclude coplanar
surf-bases from dedup and reproduce the miss cheaply. **Refuted by disasm** (`harness/
decode_fnv_traversal.py`, asserts the bytes): the recursive helper `0x1adb60`, after testing a
node's surf-base (`iSurf` +0x1c) + vert-pool, follows `node.iPlane` (+0x28, `0x1ade4f mov
esi,[esi+0x28]`) and loops back (`0x1ade64 jne 0x1adc80`) to re-test EVERY coplanar node's
surf-base + verts, alongside the iFront/iBack (+0x20/+0x24) descent. So a point wired as any live
node's surf-base — primary or coplanar — IS reachable. The query is an exact nearest-within-R over
the whole live subtree. No scoped descent trick exists.

## Why the faithful fix is out of reach (the wall)

The editor MISS is therefore a tree-CONTENTS fact: at the add, the editor's incremental
`Model->Nodes` does not have the snapped point as a reachable node, while native's tree does. Both
prior ports fail for this reason (measured, reverted):

- **Raw-base carry** (thread native's incremental raw W through repartition): regresses the siblings
  the editor legitimately SNAPS (Z=240, z=416) — native's incremental W is always raw, but the
  editor's final W there is the snapped `Points[pBase]·N`. To carry-raw only the miss faces, native
  must know the editor's per-face hit/miss = the tree reachability.
- **FNV-descent port** (`ba23319`): over native's tree it STILL snaps x=448 (native's tree has
  `448.00006` wired reachably) AND shifts the N8 point table 76→81 (~5 reachability mismatches from
  FWTB fragment vert-pools + `bspCleanup` splice timing). The linear scan's 76/76 is what holds the
  corpus green.

The unpinned root is the incremental-tree WIRING divergence for the subtracting brush (why the
editor's tree lacks the snapped point as a reachable node when the sibling base is added — face
order within a brush's CSG, or a cleanup splice). Pinning it needs a LIVE editor gdb spike on
`bspAddPoint 0x35430` / `bspAddNode 0x34e80` through the brush's CSG. Reproducing that wiring
bit-exactly is a re-derivation of native's ~5.4k-LOC incremental BSP core — multi-week, HIGH risk
(changes the point table across the corpus, destabilising the green N1–N7 ladder). Owner already
ruled EXCLUDE.

## Recommendation

Keep the stopgap mask; do NOT attempt the core rewrite under a timebox. The residual is
game-inconsequential (N8: a 2.16e-4 ≈ 7-ULP node-plane W offset far below the ±0.001 trace band +
one inert `Brush.Region`; N19: an in-plane soup-base offset in `Model->Polys`, editor CSG-working
state, with the runtime Model byte-identical). When the ladder reaches N19, do NOT just widen
`NODE_W_DEDUP_TOL`: it is SHARED by `_node_w_tie` and `_poly_base_tie` (gate lines 476 & 493), so
raising it to cover N19's `1.007e-3` soup-base tie would also admit node-plane-W diffs up to
`1.007e-3` — ABOVE the ±0.001 line-trace band the `5e-4` bound was chosen to stay under. N19 is a
soup-base-only diff (runtime Model byte-identical), so it wants a DECOUPLED poly-base tolerance,
not a widened shared W tolerance — or the faithful fix. An owner call.

## Harness

- `harness/gate_nomask.py` — the gate with the dedup-tie mask disabled.
- `harness/soup_base_diff.py` — identity-matched `Model->Polys` soup-base diff (found the N19 case).
- `harness/decode_fnv_traversal.py` — self-asserting disasm pin of the FNV iFront/iBack + coplanar
  traversal (closes the scoped-descent escape).
- Node/surf/point diff reused from `2026-09-04-bspaddpoint-dedup-base-provenance/harness/diff_n8.py`.
