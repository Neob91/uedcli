+++
priority = "p1"
kind = "implement"
summary = "The board becomes one directory per work item"
+++

# The board becomes one directory per work item

Spec: board item `the-board-is-being-restructured-into-one`.
Every stage (`inbox`, `to-spec`, `to-spike`, `to-plan`, `to-build`, `someday`, `stale`, `done`)
becomes a directory of item directories; an item is `overview.md` (required) plus optional
`spec.md`, `plan.md` and `questions/<q>.md`, and advances by one `git mv`. Fixes the three
problems named in the spec's §1: `inbox.md` is 357 KB / 4,042 lines / 293 bullets so any read is
enormous; **35% of recent commits touch that one file** so concurrent sessions collide; and the
68 entries waiting on the owner are invisible inside it. **~488 bullets migrate** — but the naive
bullet count is provably wrong (3 of `to-build`'s 7 are navigation prose and 2 real items are
`##` sections), so the plan's first pass is an inventory, not a conversion. Plus **71 specs and
26 plans** folding into their items.

**Spec gate: round 1 ran and returned a STRUCTURAL finding** — 86 files cite a spec or plan by
path across 400 lines, 78 of them durable, and an item's path encodes its stage. The owner ruled
(spec §2.9): specs and plans stay in the item directory and **everything references an item by
slug, never by path**. The spec was rewritten and re-enters the gate at round 1.

Four things a plan must respect: nothing is re-triaged or judged stale during the conversion
(owner decision 2.7 — the stale list is proposed in bulk at the very END); the migration runs
**on the base branch in batches, not in a worktree** (spec §4.2 — parked for the owner as an
exception to their own rule); `CLAUDE.md`'s round-2 trigger excludes `dev/docs/board/*`, so
moving specs under the board would silently kill every spec and plan round 2 unless that
exclusion is narrowed (§4.1); and `direction/process.md` carries a sentence this change makes
wrong, whose replacement is parked on [`inbox.md`](../../inbox/).
