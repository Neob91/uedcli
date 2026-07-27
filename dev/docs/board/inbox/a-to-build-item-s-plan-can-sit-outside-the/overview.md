+++
priority = "p2"
kind = "chore"
summary = "board/to-build/unified-asset-catalog's plan lives in an inbox item, so the link check skips a plan that is about to be executed."
+++

# A `to-build/` item's plan can sit outside the build queue, so it is not link-checked

`uedcli/tests/test_doc_links.py` exempts every item's `spec.md` and `plan.md` from the markdown-link
and prose-citation checks **except** under `board/to-build/`. The stated reason is that a
`to-build/` item is on-deck to be executed, so rot in its spec or plan is rot someone is about to
act on.

That reasoning assumes an item's plan lives in that item. It does not always. When several items
cited one plan before the migration, the plan was filed with the *least-advanced live* citer (the
rule that stops it being deleted while a live item still needs it). So:

- board item `unified-asset-catalog` sits in `to-build/` and its `overview.md` points at
  board item `the-unified-asset-catalog-spec-revision` for the plan;
- that item is in `inbox/`, so `plan.md` there is exempt;
- the build queue therefore has an item whose plan is unchecked, which is exactly the case the
  `to-build/` carve-out exists to prevent.

**Options, none yet chosen.**

- Extend the exemption: a `spec.md`/`plan.md` is checked if *any* `to-build/` item references its
  owning item's slug. Correct, but reintroduces the reference-following that deleting `_on_deck()`
  removed, and it fails open the same way if the reference form drifts.
- Move the plan into the `to-build/` item and have the inbox item reference it by slug. Simple, but
  it breaks the least-advanced-live rule, so the plan could be deleted when the build lands while
  the inbox item still needs it.
- Accept it and record it. Cheapest; the gap stays real.

`dev/docs/rationale/MIGRATION.md`'s exemption table says the nine files that lost checking did so
because the item that owns them is not in the build queue. That sentence is right for eight of them
and wrong for this one: the work that owns this plan *is* in the build queue.
