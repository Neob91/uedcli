+++
priority = "p2"
kind = "owner-question"
summary = "Two pointers in direction/process.md name a CLAUDE.md section that was moved out; the fix needs an explicit yes."
+++

# [OWNER — confirm] direction/process.md points at CLAUDE.md "Feature worktrees", a section that no longer exists

`CLAUDE.md` was trimmed from 689 lines to 331 (2026-07-27) by moving detail into `dev/docs/rules/`.
The worktree procedure now lives in `dev/docs/rules/worktrees.md`; `CLAUDE.md` keeps a four-line
summary and a router line inside its **Commits** section, and no longer has a section titled
"Feature worktrees".

`dev/docs/direction/process.md` cites that title twice. It is under `direction/`, so it cannot be
edited without the owner's yes (`CLAUDE.md` "Direction docs"). Nothing is broken — both are prose
citations, not markdown links, so `test_doc_links.py` stays green — but each now names a heading a
reader will not find.

## Proposed text, verbatim

Line 60, currently:

> branch. Procedure: `CLAUDE.md` "Feature worktrees". **An exception is the

becomes:

> branch. Procedure: [`../rules/worktrees.md`](../rules/worktrees.md). **An exception is the

Line 147, currently:

> `CLAUDE.md` "Direction docs" · "Review gates" · "Feature worktrees" ·

becomes:

> `CLAUDE.md` "Direction docs" · "Review gates" ·
> [`../rules/worktrees.md`](../rules/worktrees.md) ·

Nothing the doc *says* changes — these are pointers only.
