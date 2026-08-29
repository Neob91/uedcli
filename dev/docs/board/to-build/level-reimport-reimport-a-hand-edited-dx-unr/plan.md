# Plan — `level reimport`

Canonical plan: `docs/superpowers/plans/2026-08-29-level-reimport.md` (written via the
`writing-plans` skill, TDD task-by-task, against this item's `spec.md`).

Five tasks: (1) `reimport_ops.diff_actors` — classify actors by name; (2)
`reimport_ops.blast_radius_exceeded` + `compute_brush_ranks` — the guard and the brush-only
LIS-based order recompute; (3) the CLI parser; (4) the `_level_reimport` verb, wired and tested
against the committed `map_import_bounds` fixtures; (5) `docs/usage.md`.

Execute in a worktree per `dev/docs/rules/building-features.md`; each task is TDD (failing test →
implement → passing test → commit).
