+++
priority = "p?"
kind = "unknown"
summary = "`--game --map` actor-relative poses + `--list-actors` query"
+++

# `--game --map` actor-relative poses + `--list-actors` query

— BUILT + live-verified 2026-07-17
(spec `specs/2026-07-17-game-actor-relative-poses.md`; decision 16:24). `at:@Actor`/`look:@Actor`/
`orbit:@Actor` now resolve against the RUNNING game for retail `--map` (link verbs `ListActors`/
`GetActorLocation`; `preview_shots.py` baked into the image; batch resolves + poses). `--list-actors
CLASS [--sample N]` query mode prints a map's actors (no screenshots) to compose `@Name` refs. Fixes
the `at:@PlayerStart` gap. Live: delivered 40 NON-PlayerStart shots across 5 OG maps entirely via
the CLI (`--list-actors Engine.PathNode --sample 8` → `at:@PathNodeN;rot:...`).
