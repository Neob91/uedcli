+++
priority = "p?"
kind = "debug"
summary = "The rotate/scale default pivot has three open points the spec cannot durably hold"
+++

# The rotate/scale default pivot has three open points the spec cannot durably hold

`spec.md` §7 is the only home for these, and
specs are ephemeral — so they land here.
1. **Scope was never owner-confirmed.** The own-Location pivot is live on BOTH `actor rotate --by`
   and `brush scale --by` because they share `rotation.best_grid_pivot`. Splitting them would be
   the larger change, so sharing was kept — but it was an agent call, not a ruling.
2. **Residual displacement is unmeasured.** The pivot is a member's Location, not the selection
   centre, so a group still swings by that member's offset from the centre — zero for a lone
   actor, roughly half the inter-member spacing otherwise. No target was set for it.
3. **The long-lever off-grid residue is real and pre-existing.** Beyond ~11,438 uu from the pivot
   (`CLEAN_EPS / 8.742278e-08`) the GMath rotator dust exceeds the emitter's snap band, so a
   rotated `Location` lands genuinely off-grid: two actors 24,000 uu apart rotated 90° about their
   midpoint stored `X=11999.998951`. Orthogonal to the pivot choice. The obvious fix — an exact
   integer matrix for 90°-multiple deltas — would diverge from what UnrealEd computes for the same
   operation, against the byte-identity goal, so it needs a spike rather than a patch.
