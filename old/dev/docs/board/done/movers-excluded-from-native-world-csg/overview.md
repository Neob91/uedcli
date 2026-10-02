+++
priority = "p?"
kind = "unknown"
summary = "Movers excluded from native world CSG (`_in_world_csg`)"
+++

# Movers excluded from native world CSG (`_in_world_csg`)

— BUILT 2026-07-19. Native's world-CSG
brush selection pulled in ANY brush-bearing actor, including **Movers** (`DeusExMover`, 23 in HK /
28 in UNATCO) — dynamic actors (doors/lifts) whose brushes UnrealEd keeps as private Models and
never CSGs into the world. Feeding them into CSG filled doorways solid and shattered empty-space
connectivity. Fix: `materialize._build_level_model`'s `csg_order` filters via the shared
`movers.is_mover` predicate; `_trunk_to_actorspecs` still emits movers as actors (emission is
independent of CSG). Measured (real builds, `shatter_probe.py`): HK leaf-blobs **21→2**, zones
**24→5** (= editor golden's 5); UNATCO leaf-blobs **18→7**, zones **20→9** (editor 7); castle
(no movers) byte-UNCHANGED (485 surfs / 1156 nodes / 43.04%, no-op). Regression:
`test_mover_excluded_from_world_csg_but_emitted_as_actor`. (That remnant — a Mover subclass not
named `*Mover`, e.g. `DeusEx.BreakableGlass`, still leaking into CSG — was CLOSED 2026-07-25 when
`is_mover` became the schema-aware class-hierarchy test; see the entry at the top of this file.)
