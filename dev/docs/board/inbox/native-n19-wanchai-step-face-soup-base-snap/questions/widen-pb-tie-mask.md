# Widen the PB-tie mask to cover an in-plane-only base snap?

## Context

WanChai N=19 fails the parity gate on 3 `Step` soup-FPoly bases snapped by native's linear-scan
dedup — the same base-dedup class ruled EXCLUDE at N8
(`done/native-n8-unatco-rotated-brush-base-fp-diverges`), but `d = 1.007e-3` exceeds the implemented
`5e-4` PB-tie mask (`parity_gate.py` `_poly_base_tie` / `NODE_W_DEDUP_TOL`). Here the face normal is
`(0,0,1)`, so `dW = base·normal = 0` (base.z identical); the node plane is bit-identical and there is
no node-W residual. So this is strictly more inconsequential than the N8 case you excluded (which had
a real `dW = 2.16e-4`): the only diff is the in-plane X,Y of the persisted CSG-soup FPoly.Base
(rebuild scratch), and native's base is a real own-Model.Points entry.

Proposed options:

- **(A)** Raise the PB-tie tolerance only (keep NW at `5e-4`) to ~`1.1e-3`, still gated on "native
  base is a real own-Model point". Simplest; matches the N8 ruling's `±0.001`-band spirit.
- **(B)** Mask a PB tie when `dW = base·normal` is ~0 (in-plane-only snap) regardless of Euclidean
  `d`, still requiring native base ∈ own-Model.Points. Tighter to the actual inconsequence (plane
  unaffected), independent of the `d` constant.

Either is an exclusion-set change and needs your yes plus an opus inconsequence review (per
NATIVE-MATERIALIZE.md). Not self-authorized. The alternative is the multi-week `bspcsg.rs` CSG-core
rewrite (the FNV-descent dedup ruled out at N8).

Which — (A), (B), reject (rewrite instead), or something else?

## Answer
