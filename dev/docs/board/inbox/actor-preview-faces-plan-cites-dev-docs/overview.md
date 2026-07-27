+++
priority = "p2"
kind = "debug"
summary = "The on-deck actor-preview-faces plan cites a rationale topic that was never written, so bin/test is red on master."
+++

# `actor-preview-faces` plan cites `rationale/preview.md`, which does not exist

`bin/test` is **red on master** (2026-07-27), independently of the board migration:

```
FAILED uedcli/tests/test_doc_links.py::test_prose_citations_into_the_new_trees_resolve[dev/docs/plans/2026-07-27-actor-preview-faces-plan.md]
  dev/docs/rationale/preview.md   (cited 3 times)
```

`dev/docs/rationale/` has no `preview.md`; the topics present are `MIGRATION`, `README`, `cli`,
`config`, `containers`, `driver`, `emit`, `mapimport`, `propedit`, `reported-coordinates`,
`surface`, `userdocs`.

**Why it is checked at all:** the plan is ephemeral, and ephemeral docs are normally exempt — but
it is referenced from `to-build.md`, so `_on_deck()` pulls it into the checked set. Working as
intended: an on-deck plan is about to be executed and must not carry rot.

**Two fixes, and the choice is not obvious.** Either write `dev/docs/rationale/preview.md` (the
plan expects a preview rationale topic, and the `--faces` work will need one anyway), or repoint
the three citations at whichever topic actually owns the reasoning. Whoever builds the `--faces`
item should decide — they know which.

Found while landing the board-migration scaffold; not caused by it.
