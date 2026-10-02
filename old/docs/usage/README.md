# Usage guides

Task-oriented workflows: how to accomplish something, mixing commands the way a real task does.
For a specific command's own flags and behavior, see [`docs/reference/`](../README.md).

## Composability / piping

How verbs chain via stdin — the CLI's core philosophy, described in
[docs/README.md](../README.md#the-composing-pattern). No guide lives here yet; a natural seed is
the multi-verb pipe examples already on [`reference/actor/find.md`](../reference/actor/find.md)
(`actor find --group cells | actor delete -`, and similar).

## Building & shaping geometry

- [CSG combining a stash](csg-combine-a-stash.md) — pipe a captured actor set through a CSG
  generator instead of applying it as-is.

Generator-then-edit patterns are a natural future addition here.

## Movers & animation

- [The mover keyframe workflow](mover-keyframes.md) — build a mover and author its keyframe stops.
- [The door mover flow](door-mover-flow.md) — turn existing door actors into a working mover via
  CSG deintersect.

Both cross-link to their fuller `leveldesign/` counterparts (editor procedure, trigger wiring,
engine caveats).

## Level lifecycle

Create → populate → materialize → photo → hand-edit in UnrealEd → reimport, as one round-trip
story. No guide lives here yet; see [`reference/level/`](../reference/level/README.md) for the
individual verbs.

## Discovery idioms

How to find X — techniques applying `actor find`'s filters in combination. No guide lives here yet.

## Sharing & reuse

Stash/prefab capture → promote → apply across levels. No guide lives here yet; see
[`reference/stash.md`](../reference/stash.md) and [`reference/prefab.md`](../reference/prefab.md).
