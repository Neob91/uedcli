+++
priority = "p?"
kind = "unknown"
summary = "Offline spatial queries: `query los A B` / raycast"
+++

# Offline spatial queries: `query los A B` / raycast

The native `linecheck.rs` BSP ray
test (built for the light bake) can answer line-of-sight and hit-point questions with no editor and
no game: "can the guard at X see the door at Y", "what surface does this ray hit first". A stateless
query verb (actor-to-actor, point-to-point, `--from-actor --direction`) that prints hit/clear + the
hit surface — composes with `actor find`. Gameplay sight-line design (patrols, snipers, camera cones)
becomes checkable text. (AI brainstorm 2026-07-16.)
