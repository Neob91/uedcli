+++
priority = "p2"
kind = "chore"
summary = "Three of the five to-build items keep their spec or plan in an inbox item, so the link check skips artifacts that are about to be executed."
+++

# A `to-build/` item's spec or plan can sit outside the build queue, so it is not link-checked

`uedcli/tests/test_doc_links.py` exempts every item's `spec.md` and `plan.md` from the markdown-link
and prose-citation checks **except** under `board/to-build/`. The stated reason is that a
`to-build/` item is on-deck to be executed, so rot in its spec or plan is rot someone is about to
act on.

That reasoning assumes an item's spec and plan live in that item. They do not always. When several
items cited one file before the migration, it was filed with the *least-advanced live* citer — the
rule that stops it being deleted while a live item still needs it. Three of the five `to-build/`
items are affected:

- board item `unified-asset-catalog` — plan is in board item `the-unified-asset-catalog-spec-revision`
  (`inbox/`).
- board item `docs-restructure` — spec **and** plan are both in board item
  `docs-restructure-is-complete` (`inbox/`).
- board item `actor-preview-faces` — spec is in board item
  `four-actor-preview-faces-rulings-need-a-durable`, plan in board item
  `actor-preview-faces-plan-cites-dev-docs` (both `inbox/`).

So four of the nine files that lost link checking in the move are this case, not the ordinary one.

**Options, none yet chosen.**

- Extend the exemption: a `spec.md`/`plan.md` is checked if *any* `to-build/` item references its
  owning item's slug. Correct, but reintroduces the reference-following that deleting `_on_deck()`
  removed, and it fails open the same way if the reference form drifts.
- Move the file into the `to-build/` item and have the other item reference it by slug. Simple, but
  it breaks the least-advanced-live rule, so the file could be deleted when the build lands while
  the other item still needs it.
- Accept it and record it. Cheapest; the gap stays real.

Evidence and the full before/after list: `dev/docs/rationale/MIGRATION.md`, "The link-check
exemption boundary".
