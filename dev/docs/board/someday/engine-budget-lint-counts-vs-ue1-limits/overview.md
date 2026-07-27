+++
priority = "p?"
kind = "implement"
summary = "Engine-budget lint: counts vs UE1 limits"
+++

# Engine-budget lint: counts vs UE1 limits

After a native build (or parsing any
`.dx`), report node/surf/vert/light/zone counts against the engine's hard + practical ceilings
(64 zones, name-table/index widths, typical node budgets for the software renderer) and warn on
approach. Cheap once the native build exists; catches "castle grew past what the renderer likes"
before it manifests as mystery slowness. (AI brainstorm 2026-07-16.)
