+++
priority = "p1"
kind = "debug"
summary = "Native materialize `LIGHT APPLY` bake (`bake_lighting`, Rust) is far too slow / resource-heavy for a full DX level"
+++

# Native materialize `LIGHT APPLY` bake (`bake_lighting`, Rust) is far too slow / resource-heavy for a full DX level

An unbounded LIT build of the UNATCO trunk was SIGTERM'd
(systemd-oom, exit 143) at ~7 min; unlit builds are the only ones that complete. The N-4 per-lumel
BSP ray test over all surfaces × all participating lights needs a perf pass (or a coarser/optional
bake) before lit native maps of DX-scale content are feasible. Unlit maps render fine. (Found
2026-07-17.)
