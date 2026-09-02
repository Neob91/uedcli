+++
priority = "p2"
kind = "debug"
summary = "Vandenberg Gas's near-exact node count (d=-6 with RING_NEAR) was error cancellation: shipping the live-confirmed editor-faithful f32 scaled-brush transform chain (editor_vector_xform/editor_point_xform, 2026-09-02) swings it to d=+659 while 17 other levels improve or stay byte-identical. With per-poly world inputs now live-proven bit-identical to the editor's, a large compensating divergence must exist further down Vandenberg's build. Mechanism unknown."
+++

# Vandenberg count parity was error cancellation

The 2026-09-02 per-brush Pass-1 trace round (`native-materialize-findings.md`, search "UNATCO live
per-brush Pass-1 tree-shape trace") shipped the editor-faithful all-f32 `ABrush::BuildCoords`
transform chain for scaled brushes. Live-gdb validations on Vandenberg's own `Brush54` (412-poly
dome): all 412 post-`FPoly::Transform` normals and 339/412 Base values match ONLY the new chain's
predictions (0 match only the old double compose; the editor's Transform input normal is
`calc_normal(local)`, 119/119 decidable).

Despite bit-exact per-poly world inputs, Vandenberg's counts move AWAY from its golden:

| | nodes | surfs | leaves | plane-exact |
|---|---|---|---|---|
| old (double chain) | -6 | +0 | -56 | 50/10677 |
| new (f32 chain) | +659 | +7 | +309 | 7/10683 |

Same shape as nsfhq04's `Brush8321` precedent: the near-exact count was two errors cancelling. The
remaining divergence is downstream of the transform (filter/split/merge on this level's 318 scaled
+ mirror brushes; the mirror path is still native-approximated — ring-reverse + `calc_normal` —
rather than the editor's `Orientation`-flip + VectorXform normal, a candidate). Not chased in that
round (UNATCO-scoped task); no fudge/revert per the standing rule.

Next step: per-brush Pass-1 count trace on Vandenberg (`pass1_brush_trace_unatco.py` already
accepts its golden — the k=0..8 normal-probe capture is in
`_scratch/pass1-trace/pass1-normal-probe-golden_vandenberg-gas.log` of the 2026-09-02 worktree;
logs also under `dev/docs/spikes/2026-08-29-unatco-repart-live-diff/logs/`) to find the first
diverging brush the same way UNATCO's was cleared.
