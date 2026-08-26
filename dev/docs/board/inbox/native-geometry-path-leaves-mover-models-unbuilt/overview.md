+++
priority = "p2"
kind = "implement"
summary = "An editor-free build never runs MAP REBUILD, so no mover gets its private brush Model built and movers do not render."
+++

# The editor-free build path leaves mover models unbuilt

An editor-free build ships a pre-built world Model and never runs `MAP REBUILD`. Only
`MAP REBUILD` builds a mover's *private* brush Model (`csgPrepMovingBrush`), so on this path every
`Mover` ships with its polys but no BSP and does not render. UNATCO has 28 `DeusExMover`s (doors,
lifts).

`apply._materialize_native` WARNS to stderr naming every mover and continues, rather than refusing —
deliberately permissive, because `UEDCLI_NATIVE_MATERIALIZE=1` is a temporary test gate and refusing
would make it useless on exactly the retail maps it exists to test (owner, 2026-08-26). That
permissiveness goes away with the gate: a real CLI flag must not ship a knowingly-broken map.

Options, none tried:

- Build each mover's model natively too (a single-brush world build per mover is not the same thing
  as `csgPrepMovingBrush` — the editor also sets the moving-brush poly flags).
- Find an editor verb that preps movers without a world rebuild.
- Two passes: load unbuilt → `MAP REBUILD` → `MAP SAVE`, then splice the native world Model into
  that saved package host-side and reload. Keeps the editor's mover models; costs a package
  rewrite with ref remapping into the saved map's own tables.

Filed rather than fixed — the demo only needed world geometry. See
`editor-free-native-world-bsp-map-assembly`.
