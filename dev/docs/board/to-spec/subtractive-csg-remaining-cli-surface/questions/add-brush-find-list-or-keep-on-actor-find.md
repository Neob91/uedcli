# Add top-level `brush find` / `brush list`, or keep brush discovery on `actor find --kind brush`?

## Context

The overview asks to "unify the fragmented brush namespace" with `brush find`/`brush list`. But
`actor find --kind brush` already finds brushes, and `actor find --kind brush | actor show -` lists
them. A `brush find`/`brush list` would duplicate that, and `conventions.md` says prefer ONE stateless
`find` verb feeding the others, not a per-family clone.

- Option A (recommended): no `brush find`/`brush list`. Add `actor find --csg add|subtract` (this
  spec) so the one `find` verb covers "brushes, and by CSG type", and document that brush discovery
  lives on `actor find`.
- Option B: add `brush find`/`brush list` as brush-scoped conveniences — a second discovery surface to
  keep in sync with `actor find`.

Recommendation: A.

## Answer

<!-- Empty = open. -->
