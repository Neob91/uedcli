# Bulk thinning pass over the board, or just an opportunistic rule — and is this item still worth keeping?

## Context

The item's original mechanism (extract spec-grade items to `dev/docs/specs/`) is obsolete — the
2026-06-25 reorg already moved specs/plans inside each item dir. What's left is trimming verbose
`overview.md` bodies (121 items >25 lines). Two ways to spend the effort:

- **Bulk pass**: sweep all 121 verbose items now. Maximal scannability, but real risk of trimming
  load-bearing findings (evidence, owner flags, rejected alternatives) across 121 hand edits.
- **Opportunistic rule** (recommended): thin an item only when you already have it open; keep trimming
  `done/` freely. Near-zero risk, spreads the cost, no dedicated effort.

Either way `done/` one-lining is already required and needs no decision.

Recommendation: adopt the opportunistic rule and close this item as mostly-superseded — the standing
"keep it short and plain" ruling already carries the intent. Confirm if you'd rather commission a
one-shot bulk pass instead.

## Answer

<!-- Empty = open. -->
