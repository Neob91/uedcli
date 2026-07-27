+++
priority = "p?"
kind = "unknown"
summary = "Native render `Bounds` (c0) + collision `LeafHulls` (cc) — faithful `FilterBound` emit"
+++

# Native render `Bounds` (c0) + collision `LeafHulls` (cc) — faithful `FilterBound` emit

(`uedcli-native/src/passes.rs::bsp_build_bounds`, 2026-07-18). Replaced the empty-Bounds +
approximate-hull stub with a verbatim port of the editor's `bspBuildBounds`/`FilterBound`/
`SplitPartitioner`/`BuildInfiniteFPoly` (recipe: `re-raw-zones/bounds-and-zonelayout.md` §1).
Ground-truth raw bytes: Bounds `0→484` entries (`12102 B`, length byte-EXACT, all IsValid=1),
LeafHulls `4028→3866` ints (`15466 B`, byte-EXACT length, **all 308 hull plane-ref sets
byte-identical**). Residual = ≤0.005-unit FBox float drift inherited from the not-yet-parity Point
pool (`pBase`), see [[82c-bounds-leafhulls-decode]]. Live-verified: `NativeCastle` boots headless
and renders a clean first-person frame (no OccludeBsp "Anomalous singularity").
