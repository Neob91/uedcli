+++
priority = "p?"
kind = "unknown"
summary = "Native from-scratch `.dx` game-load — loads + renders clean"
+++

# Native from-scratch `.dx` game-load — loads + renders clean

(2026-07-15). A natively
materialized `.dx` (real Rust CSG, no editor) now loads in the live game, possesses the player,
and renders with 0 `OccludeBsp`/singularity/Critical. Fixed: six load-blocking serialization/
structure bugs, then the `FBspNode` field cross-wiring (`iRenderBound=0` into an empty Bounds
array → NULL-FBox render crash; commit 51e47618b) — with a regression test pinning the crash
condition + the real on-disk field semantics (vs `DXOnly.dx`), and the spike doc
`50-model-ondisk-layout-and-render.md`. **Remnant:** the room isn't yet *playable* — the player
falls through the floor (BSP leaf/solidity not assigned; view is black = unlit). Promoted to
inbox "[plan] Native BSP leaf/solidity assignment" + N-4 lighting.
