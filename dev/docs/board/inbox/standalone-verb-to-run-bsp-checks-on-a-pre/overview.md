+++
priority = "p3"
kind = "implement"
summary = "A verb to run the built-model BSP check on an existing .dx without rebuilding it"
+++

# Standalone verb to run BSP checks on a pre-built .dx

The materialize BSP checks (`done/bsp-issue-detector`) only run as a side effect of a build. There is
no way to run the built-model check (invisible walls + fall-through) on an already-built map without
rebuilding it — e.g. to audit a retail map, or a map built earlier.

The analysis is already reusable: `bsp.builtmodel.load_model_from_dx(bytes) -> Model` +
`analyze_built(model) -> list[Finding]` are pure and offline (no editor). A thin verb (e.g.
`level doctor --built --dx <path>`, the shape the old spec proposed) would wire them to a CLI path.
The build-output (editor-log) half has no offline equivalent — it needs the live rebuild — so a
standalone verb covers the built-model check only.

Deferred from the materialize work; needs an owner call on the verb surface (see the reconcile item
`reconcile-the-bsp-issue-ground-truth-detector`).
