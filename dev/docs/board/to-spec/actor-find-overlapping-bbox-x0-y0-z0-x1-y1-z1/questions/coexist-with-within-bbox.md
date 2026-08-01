# May `--within-bbox` and `--overlapping-bbox` be given together?

## Context

Both are single-valued spatial predicates on `actor find`. Two designs:

- **AND them (recommended).** No special-casing — they AND like every other `find` filter. Because a
  world AABB fully inside a box is also overlapping it, `within ⊆ overlapping`, so passing both just
  degenerates to `--within-bbox`. Harmless, and it keeps the "all filters AND" rule with zero extra
  code.
- **Mutually-exclusive argparse group.** Rejects `--within-bbox … --overlapping-bbox …` with exit 2.
  Signals that combining two region tests is probably a mistake, at the cost of one special case the
  other filters don't have.

Recommendation: AND (no mutual-exclusion). The combination is pointless but not wrong, and the
uniform "filters AND" rule is worth more than guarding a harmless no-win input.

## Answer

<!-- Empty = open. -->
