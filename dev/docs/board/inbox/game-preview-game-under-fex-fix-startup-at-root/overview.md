+++
priority = "p2"
kind = "implement"
summary = "Make level photo --game run under FEX+wine-10 by fixing the startup/corruption at its root"
+++

# Game preview --game under FEX

`level materialize` (editor) now runs under FEX+wine-10 on arm64. `level photo --game` does NOT —
it still uses the qemu+wine-8 path (which works). Under FEX+wine-10 the game corrupts the object
system on the runtime menu→map `ClientTravel` (spike `2026-08-06-game-under-fex`: `ULevel::PostLoad`
AV / `StaticAllocateObject` assertion when the ~25-package menu graph is resident).

## Owner ruling (2026-08-06)

**Do NOT load the preview map as the boot map.** That breaks the warm `--game` setup, and the spike's
"load via the boot `LoadMap` path" workaround is rejected. **Keep the Travel mechanism unchanged** —
the warm standing game travels to preview maps as it does today. The task is to **fix the FEX game
startup/corruption at its root** so the normal menu→map `ClientTravel` works under FEX, not to route
around it.

## What that means

Root-cause and fix the FEX+wine-10 object-system corruption on `ClientTravel`-while-big-graph-resident
(the spike ruled out SoftDrv, `LIBGL_ALWAYS_SOFTWARE`, FEX memory-ordering, the 2 GiB VA ceiling,
audio — so it's deeper: a FEX/wine emulation issue in that allocation/GC path). Then `--game` renders
a frame under the same FEX runtime the editor uses (one runtime for both, the original goal).
Spike + evidence: `dev/docs/spikes/2026-08-06-game-under-fex/`.
