+++
priority = "p?"
kind = "implement"
summary = "expose order_value as a human-readable CSG rank (CLI verb + GUI inspector field)"
+++

# expose order_value as a human-readable CSG rank

`order_value` is a per-actor LexoRank string (e.g. `"m00001"`): `level.order` — the CSG evaluation
order (`trunk.py`/`t3dtree.py`) — is the `(order_value, name)` sort over it. LexoRank is deliberately
not human-readable (it supports inserting between any two ranks with no renumbering), so nobody can
answer "which actor carves 5th?" by looking at it.

Today `order_value` is queryable nowhere in the CLI: it appears only in doctor/materialize
duplicate-rank warnings, never as a per-actor fact a user can ask for. In the GUI, the inspector
(`Inspector.tsx`) shows the raw string via `SceneActor.order_value` (`uedcli/serve/scene.py`).

**Goal:** expose a computed, human-readable **rank** — an actor's 1-based position in `level.order`
— on both surfaces: a new CLI query verb (`actor rank`) and a `SceneActor.csg_rank: int` field the
GUI inspector shows instead of the raw string.

See `spec.md` for the exact verb shape, the `csg_rank` field, and the call on whether the raw
`order_value` string still ships anywhere. See `plan.md` for the numbered build tasks.
