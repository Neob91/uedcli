+++
priority = "p1"
kind = "implement"
summary = "Done — every spec and plan now lives in the board item that owns it (owner decision 2.9)."
+++

# Finish the board migration — move specs and plans into item directories

**Done 2026-07-27.** All 71 specs and 27 plans moved out of `dev/docs/specs/` and
`dev/docs/plans/`, which are removed. Each landed in the item that owns it: the single citing item
where there was one, the least-advanced *live* citing item where several cited it (so the file
cannot be deleted while a live item still needs it), and a new `done/` item where nothing cited it.
An item that received two specs names the second `spec-<topic>.md`.

The three things that had to land in the same change all did:

1. `_EPHEMERAL` in `uedcli/tests/test_doc_links.py` became a path shape —
   `board/*/*/spec.md` and `board/*/*/plan.md`, exempt except under `to-build/` — and `_on_deck()`
   is deleted.
2. `CLAUDE.md`'s round-2 trigger is narrowed to an item's own `overview.md` and `questions/`, so a
   spec or plan under the board still earns its round 2.
3. The retired ledger (now `dev/docs/rationale/MIGRATION.md`) was frozen, so its two now-dangling links are exempted in the link test
   rather than edited.

**Remnant:** the exemption narrowed link coverage from 13 ephemeral files to 3. The before/after
list is in `dev/docs/rationale/MIGRATION.md`, "The link-check exemption boundary". One row there is
a genuine gap rather than a consequence — see board item
`a-to-build-item-s-plan-can-sit-outside-the`.
