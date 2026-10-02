# Should `list` take `-` to enumerate over a piped actor set?

## Context

The overview asks whether `list` reads `-`/stdin to scope enumeration to a piped actor set.

- **A — whole-box only (recommended).** `list` always enumerates the resolved level/`--tree` box.
  The stated need in `direction/organization.md` is "what folders/labels exist" — a whole-tree
  question. Simplest surface.
- **B — accept `-` (a stdin name list) to restrict the universe**, mirroring composable
  `actor find -`: `actor find --label lit | actor folder list -` would print the distinct folders
  among the `lit` actors. Empty stdin = clean no-op, exit 0 (convention). Consistent with the
  composable-find precedent, but adds a parsing path and an all-or-nothing name resolve for a
  secondary use.

Recommendation: **A** now. `-` scoping (B) is cheap to add later if wanted, and holding it back keeps
this item to two small verbs. Note: if B is chosen, `list` gains the same name-resolution error
paths as `folder get` (unknown name → exit 2).

## Answer

<!-- Empty = open. -->
