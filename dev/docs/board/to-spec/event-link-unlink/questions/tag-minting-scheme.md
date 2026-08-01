# What Tag should `event link` mint for a target that has none, and should `--tag` be exposed?

## Context

To wire `SOURCE → TARGET`, `link` sets `SOURCE.Event` to `TARGET.Tag`. If TARGET has no explicit
`Tag`, one must be minted and stored on TARGET — `event graph` ignores the class-name default, so
the wire is only real if the Tag is explicit and non-empty (see inbox
`unset-tag-treated-as-not-a-matchable-receiver`), and it must be round-trip stable (never
whitespace-only — inbox `tag-of-a-single-space-is-not-round-trip-stable`).

If TARGET already has an explicit Tag, `link` reuses it (a second source then shares the same
receiver identity). The decision is only about the MINT value:

- (a) **Target's Name** — e.g. `Door01` gets `Tag=Door01`. Unique (Names are unique), readable, and
  the wire is self-describing. Recommended.
- (b) **A random token** — `evt-<rand>`. Collision-proof by construction but opaque; harder to read
  in `event graph` output.
- (c) **Class-name-derived** — rejected: collides with the very default `event graph` treats as
  "no receiver".

Separately: expose **`--tag NAME`** to name the event/tag explicitly instead of auto-deriving? It
gives control (and enables the shared-bus fan-out in the CLI-shape question) at the cost of surface.
Recommendation: auto-derive from the Name in v1; add `--tag` only if the fan-out case is wanted.

## Answer

<!-- Empty = open. -->
