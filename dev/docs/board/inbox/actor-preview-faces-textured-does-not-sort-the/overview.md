+++
priority = "p2"
kind = "debug"
summary = "actor preview --faces textured solves the set in the ARRIVAL order of the actors, not the trunk's (order_value, name) CSG order, so a piped/named set can render a different parity image than materialize."
+++

# `actor preview --faces textured` does not sort the set into trunk CSG order (M4)

Boarded (not silently fixed) per `spec.md` §M4 of `actor-preview-unrealed-render-parity-new-csg`,
which says: "The plan must confirm `actor preview` already sorts its set that way before the solve; if
it does not, that is a separate finding to board, not a silent fix here."

## Evidence

`preview_native.solve_world_surfaces` iterates the actor list IN THE ORDER GIVEN and marshals them to
`build_geometry_bspcsg` in that order — its docstring: "in the order given — the actor-set order IS the
CSG evaluation order." But the caller does not sort:

- `uedcli/cli/commands/actor/preview.py:42` — `actors = [level.actors[n] for n in names]`, where
  `names = query.resolve_actor_names(level, raw)` returns names in **input order**
  (`uedcli/query.py`, "Returns canonical names in input order"), i.e. the order the user typed or the
  order a piped producer (`actor find … | actor preview -`) emitted — NOT the trunk's
  `(order_value, name)` order.
- `--from-t3d` renders actors in file/snippet order.

A subtract-before vs after an add changes the solve, so a set whose arrival order differs from the
trunk's effective CSG order renders a DIFFERENT `--faces textured` image than `level materialize`
produces — a silent parity divergence in the one tool meant to match the built world.

## Proposed

Sort the actor set by `(order_value, name)` before `solve_world_surfaces` when the source is a trunk
level (the `order_value` sidecar is available there; a `--from-t3d` snippet has no order and keeps file
order). Confirm against materialize's ordering (`materialize.levelinfo_first_order` / the
`(order_value, name)` sort). Owner call on whether `--from-t3d` should carry an order hint.
