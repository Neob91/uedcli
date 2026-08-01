# Exact-node folder match: a `--folder-exact PATH` flag, or a `=PATH` sigil on `--folder`?

## Context

`actor find` needs a way to match one folder node without its subtree (`castle.tower` but not
`castle.tower.roof`). The existing grammar cannot express it. Two surfaces:

- **`--folder-exact PATH` (recommended).** A distinct repeatable flag taking a literal path.
  Self-documenting in `--help`, independently repeatable, leaves `--folder`'s globstar grammar alone.
  Cost: one more flag in the folder dimension.
- **`=PATH` sigil on `--folder`.** `--folder =castle.tower` = exact node. `=` is outside the segment
  charset so it's an unambiguous marker. One flag, but a second hidden grammar mode inside
  `--folder`'s value — the kind of overloaded-flag help this project tends to avoid.

Recommendation: `--folder-exact`. A separate predicate reads clearly and keeps each flag's grammar
single-purpose.

## Answer

<!-- Empty = open. -->
