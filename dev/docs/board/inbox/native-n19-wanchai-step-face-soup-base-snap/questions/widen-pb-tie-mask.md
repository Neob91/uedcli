# Question

WanChai N=19 fails on 3 `Step` soup-FPoly bases snapped by native's linear-scan dedup — the same
base-dedup class you ruled EXCLUDE at N8, but `d = 1.007e-3` exceeds the implemented `5e-4` PB-tie
mask. `dW = 0` here (Z-normal face; the node plane is bit-identical), so it is strictly more
inconsequential than the N8 case you excluded (which had a real `dW = 2.16e-4`).

Proposed: widen the gate's PB-tie mask so it also covers a base snap whose plane projection is inert.
Two options:

- (A) Raise `NODE_W_DEDUP_TOL` for the PB tie only to ~1.1e-3 (keep NW at 5e-4), still gated on
  "native base is a real own-Model point". Simplest; matches the N8 ruling's `±0.001`-band spirit.
- (B) Mask a PB tie when `dW = base·normal` is ~0 (in-plane-only snap) regardless of Euclidean `d`,
  still requiring native base ∈ own-Model.Points. Tighter to the actual inconsequence (plane
  unaffected), independent of the arbitrary `d` constant.

Either is an exclusion-set change and needs your yes (+ an opus inconsequence review per
NATIVE-MATERIALIZE.md). Not self-authorized. Alternative is the multi-week `bspcsg.rs` CSG-core
rewrite (the FNV-descent dedup you ruled out at N8).

Which — (A), (B), reject (rewrite instead), or something else?

## Answer
