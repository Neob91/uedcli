+++
priority = "p1"
kind = "owner-question"
summary = "The board is being restructured into one directory per work item, and two of your process rules need your yes before it can land"
+++

# The board is being restructured into one directory per work item, and two of your process rules need your yes before it can land

Spec:
[`dev/docs/specs/2026-07-27-board-per-item-directories.md`](spec.md).
You decided the shape live on 2026-07-27 (every stage the same, `git mv` to advance, blocking
questions as files, stale shelved not deleted, references by slug, TOML frontmatter, and no
`[spec]`/`[plan]` kinds because "each issue gets a plan"). Those decisions currently exist only in
an **ephemeral** spec, so they are parked here verbatim.

**(A) Proposed replacement for the LAST SENTENCE of the "Nothing load-bearing lives only in chat"
bullet in `direction/process.md` (line 53, from "The board is a set…"), staying inside the
bullet:**

> The board is a set of stages named for the *next action* an item needs, and **each work item is
> a directory** whose stage is the directory it sits in — including the inbox, the someday shelf,
> the stale shelf and the done tail, so advancing an item is a single `git mv`. An item is
> referenced by its **slug**, never by its path, because its path encodes the stage and the stage
> changes. Its directory holds an `overview.md` — priority, kind, a short description, what it
> depends on, then the detail — and may hold the item's `spec.md`, its `plan.md`, and a
> `questions/` directory. **A question file is a blocker**: the thing that must be answered before
> the item can be planned or built. It is answered by writing into its empty `## Answer` section,
> after which an agent folds the decision into its durable home and deletes the file. **Nothing is
> deleted to tidy the board** — work judged stale is shelved, and the shelving list is confirmed in
> bulk rather than applied item by item.

**(B) Succinctness, your ruling of 2026-07-27.** Already written into `CLAUDE.md`
("Documentation" and "Review gates"), which an agent maintains; this is the `direction/process.md`
wording, which needs your yes:

> Docs, docstrings and comments are as succinct as the meaning allows — facts, not bloat; length
> is earned by what must be explained. A reviewer flags any doc they cannot fully understand, or
> that is ambiguous.

*(A third item — a worktree exception for this migration — was here and is now RULED: you chose
base-branch committed batches on 2026-07-27. Recorded as spec §2.15, not awaiting anything.)*
*(2026-07-27.)*
