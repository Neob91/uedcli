+++
priority = "p2"
kind = "implement"
summary = "DONE: level materialize runs two advisory BSP health checks on a successful build (stderr, rc 0)"
+++

# BSP-issue detector — DONE

`level materialize` now runs two advisory, never-fatal BSP checks after a successful build+save
(owner design 2026-08-03): a build-output check (`bsp.editorlog` — UnrealEd MAP REBUILD warning
counts) and a built-model check (`bsp.builtmodel` — invisible-wall near-zero-area nodes + fall-through
non-collidable floor surfs, over `native.umodel`). Findings go to stderr; rc stays 0; `--no-bsp-check`
disables both. Reconcile of the superseded `bsp-issue-ground-truth-detector-d0-d1` spec, the D0-b
measurement, and a standalone pre-built-`.dx` verb are their own inbox items.
