+++
priority = "p?"
kind = "implement"
summary = "Level validation: BSP-error/leak surfacing on genuinely broken geometry"
+++

# Level validation: BSP-error/leak surfacing on genuinely broken geometry

`LSTAT LEVEL` ✅, `MAP REBUILD` warnings ✅ confirmed log-readable (2026-06-23). REMAINING: probe
a *genuinely broken* level (BSP leak, sealed-room failure), confirm `MAP REBUILD` warnings
identify it, then classify warnings into actionable feedback for the autonomous loop.
