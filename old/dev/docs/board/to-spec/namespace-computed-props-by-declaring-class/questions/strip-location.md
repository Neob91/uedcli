# Where does the computed-prop strip run — compare-only + schema-aware ingest, or a schema-free proven-safe bare-name strip?

## Context

Class-scoped matching needs the actor's ancestry (a class resolver), but `canonical_actor_t3d` — the
durable trunk emit, `MAP IMPORT` payload, `actor show`, stash/prefab bodies — must stay schema-free
(its bytes may not depend on which packages are installed). So the class-scoped strip cannot live
inside it. Two designs:

- **A. Compare-only + schema-aware ingest.** Remove the strip from `canonical_actor_t3d`/
  `normalize_actor` entirely; keep it in the already-schema-aware compare copy (`_actor_values`); add
  a schema-aware strip on the ingest path (`store_export.normalize_level`, which has a project) so
  imported map data is cleaned before it reaches the trunk. `canonical_actor_t3d` can then never
  mutate a real property again. Matches where the rest of the 2026-07-25 typed-compare work went.
- **B. Schema-free proven-safe bare-name strip.** Keep a bare-name strip in `canonical_actor_t3d`,
  but pin an offline audit test that fails if an entry's name is declared, with authored meaning, by
  a placeable class outside its intended scope. Smaller diff; the durable emit keeps a (test-guarded)
  power to over-strip; the audit test needs the game `.u`.

Recommendation: **A** — it removes the silent-data-loss shape rather than guarding it, at the cost of
the ingest gate gaining a class-resolver requirement (already true for class qualification on
`level import`).

## Answer

<!-- Empty = open. -->
