+++
priority = "p1"
kind = "unknown"
summary = "RESOLVED (loads + renders clean) — native from-scratch `.dx` game-load"
+++

# RESOLVED (loads + renders clean) — native from-scratch `.dx` game-load

p1. The ULevel
no longer fails to instantiate and the renderer no longer crashes: `NativeCSG.dx` (real Rust CSG)
loads in the live game, possesses the player, and renders with 0 `OccludeBsp`/singularity/Critical.
Two fix clusters landed: (a) six from-scratch serialization/structure bugs for load
(export `RF_Load` flags; ULevel `TimeSeconds` 4-byte width; drop bogus `MyLevel` self-import;
name-table `RF_Load` flags 0x70010; valid 2-zone Model `NumZones`; every actor carries
`Level→LevelInfo` for the `Actors(0)==Level` assert); (b) the `FBspNode` field cross-wiring
(`iRenderBound=0` into an empty Bounds array crashed `URender::OccludeBsp` on a NULL FBox) —
fixed + documented in spike `50-model-ondisk-layout-and-render.md` (commit 51e47618b). Remaining
playability gap tracked separately above (collision/leaf-solidity) and lighting is N-4 (view is
black = unlit build). Original failure detail retained below for history.
