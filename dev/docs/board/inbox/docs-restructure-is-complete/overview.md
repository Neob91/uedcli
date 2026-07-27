+++
priority = "p1"
kind = "owner-question"
summary = "DOCS RESTRUCTURE IS COMPLETE — one issue, everything that needs your eye"
+++

# DOCS RESTRUCTURE IS COMPLETE — one issue, everything that needs your eye

Thirteen `direction/<topic>.md` docs + `rationale/` now replace `direction.md` and the frozen
`decisions.md`. Resident context **1,063 → 686 lines**. Spec
`spec.md`, plan `plan.md`,
migration record `rationale/MIGRATION.md`.

**1. The thirteen topic docs.** Every decision in them was confirmed in session, but the prose
was written from subagent drafts afterwards — the *wording that landed* has not been read back by
you. `scope` · `terminology` · `organization` · `conventions` · `trunk-and-editor` ·
`materialize` · `safety` · `process` · `packages` · `containers` · `generators` ·
`projects-and-config` · `asset-catalog`.

**2. `asset-catalog.md` was written despite being HELD, and deliberately says nothing about the
two open arbitration items.** They are still `[decide]` below and decide whether ~46% of the
texture corpus decodes. The doc states the governing principle (the tool does not infer), the
colour exception, and the settled BC2/BC3 limit — and is silent on the mechanism, so confirming
it does not ratify them.

**3. `rationale/MIGRATION.md`'s 227-row entry index is a KEYWORD GUESS, not a disposition** —
**80 rows came back `?`**. Only the rows above the index, claimed by a topic's own sweep, are
authoritative. The table says so in its own header.

**4. NEITHER OLD FILE WAS DELETED, and that is deliberate.** `decisions.md` still holds the
*bodies* of ~200 entries whose substance no topic doc has absorbed; deleting it on a keyword
guess would destroy reasoning that only git would remember. `direction.md` is now thirteen
one-line pointers and is safe to delete whenever you say. Deletion needs your sign-off on what,
if anything, is dropped — that was the plan's design and it still holds.

**5. ~95 tracked files cite `decisions.md` by date.** Correct today (the file exists, frozen);
they become dangling the moment it goes. `test_no_citation_of_a_deleted_doc` makes that failure
loud rather than silent, so deletion cannot sneak past it.

**6. Three direction/code deltas** where confirmed direction now leads the tool (detail in
`rationale/MIGRATION.md`): label verbs reject `--tree stash|prefab` though your ruling says
accept; `stash apply`/`prefab apply` mint no batch label though the new rule says they must;
`actor folder list`/`actor label list` do not exist.

**7. Your name is swept from `CLAUDE.md`, `direction/`, `rationale/`, `rules/` and
`dev/docs/README.md`** — replaced with "the owner", pronouns neutral, parking tag `[OWNER —
confirm]`, trailer `Confirmed:`. It survives in ~20 files outside that scope (frozen
`decisions.md`, ephemeral specs/plans, board files, `architecture.md`, root `README.md`) and in
two FILENAMES (`dev/docs/owner-notes.md`, `dev/docs/2026-06-20-open-questions-for-owner.md`) —
untouched because the first reads "My own todolist, don't touch". Four commits carry the
pre-rename `Andrzej-confirmed:` trailer; history is never rewritten, so audit both spellings.
