+++
priority = "p1"
kind = "implement"
summary = "Fixed: /load's mesh/Mover resolution shares one ClassDefaults/TextureResolver per call instead of rebuilding per actor -- 13.3s -> 6.8s measured on a 487-actor level (spec.md/plan.md)"
+++

# load resolves mesh class defaults and texture skins once per actor, not once per distinct class/texture

Done. `_mesh_actor_polys`/`resolve_mover_actor_polys` now take an optional shared `ClassDefaults`
(threaded from `/load`'s own already-built one, same object `resolve_actor_sprites` already used);
`resolve_mesh_actor_polys` builds one `TextureResolver` per call instead of `resolve_skins` building
one per actor, unconditionally for every caller. Measured: `/load` against `showcase_bar` (487
actors) went from 13.3s to 6.8s; `resolve_class_defaults` calls 453→52, texture decodes 179→69. Full
design, review history, and before/after profile: `spec.md`, `plan.md`,
`dev/docs/spikes/2026-09-20-mesh-load-perf-profile/`.
