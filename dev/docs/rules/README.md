# rules/ — process rules, read on demand

Rules that bind the work but do not need to be in every session's context. Each one has a specific,
observable moment that triggers reading it; `CLAUDE.md`'s router names that moment and carries the
single fact you cannot afford to miss.

| Rule                 | Read it before |
|----------------------|---
| `documentation.md`   | writing or restructuring docs |
| `worktrees.md`       | creating a worktree or squash-merging one |
| `tests.md`           | running tests |
| `spikes.md`          | starting or finishing a spike |
| `background-work.md` | starting a background job or long wait |

**What stays in `CLAUDE.md` instead of here**, and why: a rule stays resident if it fires on
essentially every change, or if the consequence of not paging it in is a silent, unrecoverable
mistake. So `CLAUDE.md` keeps Code & CLI conventions, working with the owner, and the four
always-on documentation rules.

The split is between the *core* and the *detail*, not between whole subjects: `documentation.md` and
`worktrees.md` each elaborate a section that still has a resident summary and a router line. Where a
moved rule is dangerous to get wrong from memory, the router line carries the specific hazard — for
worktrees, the `git diff --cached --quiet` check before `git merge --squash` (whose omission commits
over a concurrent session's staged work) and "ask before `git branch -D`".

Agents maintain this tree on their own — no confirmation needed, unlike `../direction/`
(`CLAUDE.md` "Direction docs").
