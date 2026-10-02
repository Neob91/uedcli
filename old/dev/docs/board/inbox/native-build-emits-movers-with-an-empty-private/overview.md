+++
priority = "p2"
kind = "implement"
summary = "Native build emits Movers with an EMPTY private Model — a mover door has no geometry"
+++

# Native build emits Movers with an EMPTY private Model — a mover door has no geometry

`assemble` reserves every non-default brush actor's `{shape}Polys` with
`write_upolys_body([])` (an empty private Model); a STATIC brush's geometry lives in the world
BSP so that's fine, but now that Movers are (correctly) excluded from world CSG (2026-07-19),
a mover's brush geometry is in NEITHER the world model NOR its private Model → a native-built
mover is a geometry-less actor (no visible/collidable door). Surfaced by the mover-CSG-exclusion
cold review. Fix = populate a Mover's OWN private Model (its animated brush polys + the mover's
own BSP/bounds/hulls) at assembly, the way UnrealEd does — separate unbuilt native-mover work.
Until then the native build renders movers as empty actors. See `architecture.md` "World-CSG
brush selection" + `materialize._in_world_csg` docstring.
