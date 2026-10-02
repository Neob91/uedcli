# Spec DRAFT — thin the board entries to one-liners where possible

## Goal

Keep the board scannable by trimming verbose `overview.md` bodies to their essential lines.

## Current state

- 541 items. Median `overview.md` ~17 lines (~10 body after the frontmatter+title boilerplate), p90 36,
  **121 items >25 lines**. Inbox alone is 324 items.
- **The item's proposed mechanism is obsolete.** It says "extract spec-grade items to `dev/docs/specs/`
  (+ `plans/`), leaving a one-line pointer." There is no `dev/docs/specs/` or `plans/` tree: the
  2026-06-25 stage reorg moved `spec.md`/`plan.md` **inside each item dir** (`board/README.md`;
  `rules/documentation.md` "There is no separate specs or plans tree"). That half is already done.
- What remains is a plain hygiene chore, aligned with `CLAUDE.md` "Keep it short and plain / Delete
  first."

## Approach — the rule

- **`done/`**: already required to be a one-line reference line (`board/README.md`). Trim freely — the
  board is agent-operated, no owner ask.
- **Live items (`inbox/`, `to-spec/`, …)**: thin only restatement, hedging, and ceremony. **Never** cut
  load-bearing detail — a finding's evidence, an owner flag, a decision's rejected-alternatives.
  Spec-grade depth moves into the item's own `spec.md`, it is not deleted.
- **Opportunistically, not in bulk.** Thin an item when you already have it open, not as a one-shot
  rewrite of 121 items — a bulk pass over load-bearing findings is where detail gets lost.

## Recommendation

Adopt the opportunistic rule and close the "extract to `dev/docs/specs/`" mechanism as obsolete (the
reorg + the standing short-docs ruling already cover the intent). Do **not** run a bulk thinning pass.
Trimming a few bloated `done/` tails now is allowed without asking. This is a `kind = chore` item; per
`board/README.md` a chore goes straight to `to-build/` with no spec — so once the owner confirms the
rule, the lightest resolution is either a one-shot `done/`-trim task or simply closing the item.

## Test

None — board hygiene. `tests/test_board.py` already enforces the structural rules (frontmatter, slug
citations) that any trim must keep valid.

## Open questions

- One-time bulk thinning pass vs opportunistic-rule-only, and whether to just close this item as
  mostly-superseded by the reorg. See `questions/bulk-pass-or-opportunistic.md`.
