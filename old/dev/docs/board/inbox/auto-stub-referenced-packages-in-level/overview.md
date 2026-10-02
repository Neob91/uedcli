+++
priority = "p2"
kind = "implement"
summary = "AUTO-stub referenced packages in `level materialize` (capability, not safety)"
+++

# AUTO-stub referenced packages in `level materialize` (capability, not safety)

p2.
Since the uniform-mount cutover (direction/containers.md 2026-07-14 19:21) the editor mounts the whole composed
set, so v68 `.u` are on its Paths (shadowed by `/stubs` for STUBBED packages). The SAFETY hole is
already closed: `ensure_load`'s `unloadable_v68_packages` gate refuses an unstubbed v68 code package
with a clean error before any `OBJ LOAD` (no more wedge). What's LEFT is the capability — so a level
referencing a DeusEx class actually BUILDS: `run_materialize`/`render_shots` should
`stub_missing_packages(search_dirs=…)` the referenced v68-only packages before the editor load (the
pattern `qualify.export_and_qualify` uses), instead of erroring. Needs a working stub build (env
currently blocked by absent `Effects.u`).

Verify-note (levelbuild-friction #6): when this is wired, confirm mod decoration packs (`Endemia`)
actually stub. The friction log's "Endemia unstubbable" is unverified — it was never stubbed, only
never *attempted* (this gap). The one-hop M1 boundary in `stub_closure.resolve` is the only structural
limit: a must-stub v68 dep whose own direct dep is also v68-only is refused by a named error. A
decoration pack most likely deps only on `DeusEx`+`Engine` (one hop), so it should stub fine.
