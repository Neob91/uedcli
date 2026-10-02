+++
priority = "p?"
kind = "implement"
summary = "AI pathing (`PATHS DEFINE`)"
+++

# AI pathing (`PATHS DEFINE`)

NPC/bot levels need NavigationPoints + `PATHS
DEFINE` (reachspecs are computed, rebuilt after geometry/actor changes; nodes ≥50uu apart).
`PATHS DEFINE` + `PATHS BUILD LOWOPT/HIGHOPT` confirmed live 2026-06-23. Implement as part of
`level build`.
