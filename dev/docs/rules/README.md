# rules/ — process rules, read on demand

Rules that bind the work but do not need to be in every session's context. Each has an observable
moment that triggers reading it; `CLAUDE.md`'s router names that moment and carries the one fact you
can't miss.

| Rule                  | Read it before |
|-----------------------|---
| `building-features.md`| building a `to-build/` item and merging it |
| `documentation.md`    | writing or restructuring docs |
| `worktrees.md`        | creating a worktree or squash-merging one |
| `tests.md`           | running tests |
| `spikes.md`          | starting or finishing a spike |
| `background-work.md` | starting a background job or long wait |

What stays in `CLAUDE.md` instead: a rule stays resident if it fires on essentially every change, or
if not paging it in causes a silent, unrecoverable mistake. So `CLAUDE.md` keeps Code & CLI
conventions, working with the owner, and the four always-on documentation rules.

The split is between the core and the detail, not between whole subjects: `documentation.md` and
`worktrees.md` each elaborate a section that still has a resident summary and a router line. Where a
moved rule is dangerous to get wrong from memory, the router line carries the hazard — for
worktrees, the `git diff --cached --quiet` check before `git merge --squash` (whose omission commits
over a concurrent session's staged work) and "ask before `git branch -D`".

Editing these rule docs needs the owner's approval, like the rest of `dev/docs/` (`CLAUDE.md`
"dev/docs — never edit without the owner's approval"). Only `dev/docs/board/` stays agent-operated.
