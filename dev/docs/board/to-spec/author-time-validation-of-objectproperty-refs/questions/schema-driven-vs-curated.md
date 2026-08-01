# Validate every schema-OBJECT-typed property, or a curated list of ref-carrying property names?

## Context

An object ref carries its kind in its class token, and the class schema already tells us which
properties are object-typed (`classdefaults` maps `ObjectProperty`/`ClassProperty` →
`typedprops.OBJECT`). Two ways to pick what to check:

- **Schema-driven (recommended).** Per actor, validate every property whose declared type is OBJECT.
  Substrate-agnostic, matches "the tool does not infer", and covers a new object prop automatically.
  Cost: the ingest gate resolves each actor's class schema — the same resolvable-path cost the
  class/texture gate and the mover gate already pay; `ClassDefaults` memoises per class.
- **Curated name list.** Hardcode `AmbientSound`/`Song`/`OpeningSound`/`Mesh`/… Cheaper and needs no
  extra schema resolve at ingest, but it is the per-substrate hardcoded knowledge `conventions.md`
  rejects and silently misses any prop off the list.

Recommendation: **schema-driven**, accepting the per-class schema resolve at the ingest gate.

## Answer

<!-- Empty = open. -->
