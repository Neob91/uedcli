# Pathing v1 — scope split, and where does `PATHS BUILD` run?

## Context

This item ("AI pathing (`PATHS DEFINE`)") overlaps an existing item,
`level-build-paths-only-a-quality-escalation-knob`, which already proposes `level build` as a
standalone paths-only verb plus a `BSP REBUILD` `--quality` knob. They are the same build step from
two sides, so they must be reconciled rather than both grow a path-build implementation.

Note: the reachspec build is `PATHS BUILD` (LOWOPT/HIGHOPT), not `PATHS DEFINE` — DEFINE alone only
spawns marker actors and builds no edges (disassembly 2026-07-15, `unrealed/commands.md`).

Two decisions:

1. **Scope split.** Recommended: THIS item owns node authoring (via generic `actor build`/`actor
   add`, no dedicated verb unless an ergonomic gap appears) + offline `level doctor` checks
   (node spacing <50uu, likely-orphan nodes). The `PATHS BUILD` engine wiring + quality knob lives in
   (or this item depends on) `level-build-paths-only-…`. Alternative: fold everything into one item.

2. **Where does `PATHS BUILD` run?**
   - A standalone `level build` verb only (explicit rebuild — matches paths going stale after any
     geometry/actor change; the designer rebuilds when ready).
   - Also folded into `level apply`/`materialize`, the way `LIGHT APPLY` was, so every shipped map is
     navigable by default.
   - Both (fold into materialize + expose the standalone verb + quality knob).

   Recommendation: expose the standalone `level build`/quality knob; decide separately whether
   materialize auto-runs paths (folding it in makes every build slower and drags the crash-prone
   editor into the hot loop, but guarantees no stale-path ship).

There is NO native (editor-free) path builder — path building is editor-only for the foreseeable
future (native materialize is still fighting CSG/zone parity).

## Answer

<!-- Empty = open. -->
