+++
priority = "p1"
kind = "implement"
summary = "actor preview: --faces textured is now the CSG-solved world (bspcsg core, per-view backface cull), flat deleted, black background."
+++

# actor preview: UnrealEd render parity — DONE

`--faces textured` redefined to the CSG-solved textured world via `preview_native.solve_world_surfaces`
(`build_geometry_bspcsg`) + a per-view backface cull; `flat` and the old per-brush textured deleted
(choices `wire`+`textured`); black background + re-tuned wire palette; mover magenta overlay + point
overlay; zero-surface → exit 2, point/mover-only → exit 0. Follow-ups boarded:
`actor-preview-parity-direction-home`, `fold-actor-preview-parity-knowledge-into-dev`,
`actor-preview-bspcsg-starts-from-an-empty-world`, `actor-preview-faces-textured-does-not-sort-the`.
