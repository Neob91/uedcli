+++
priority = "p3"
kind = "owner-question"
summary = "`actor diagram` overlays are POINT-actor-only (built 2026-07-21)"
+++

# `actor diagram` overlays are POINT-actor-only (built 2026-07-21)

`--show-collision`
/ `--show-light-range` / `--show-sound-range` resolve fields ONLY for point actors (`actor.brush is
None`), so a colliding BRUSH mover (`bCollideActors=True`) draws no cylinder. Chosen to keep the
"brush-only preview is schema-free / works with no game install" guarantee strict — resolving a
brush's collision would force a schema load for a brush actor. The `actor-preview` spec §3 says
"every previewed colliding actor"; this narrows it to point actors. Fine? If movers should show
collision, we'd resolve schema for brush actors too when an overlay flag is set (breaking the
schema-free-brush guarantee only under `--show-*`).
