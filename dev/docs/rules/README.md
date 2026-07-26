# rules/ — process rules, read on demand

Rules that bind the work but do not need to be in every session's context. Each one has a specific,
observable moment that triggers reading it; `CLAUDE.md`'s router names that moment and carries the
single fact you cannot afford to miss.

| Rule | Read it before |
|-----------------------|---
| `tests.md` | running tests |
| `spikes.md` | starting or finishing a spike |
| `background-work.md` | starting a background job or long wait |

**What stays in `CLAUDE.md` instead of here**, and why: a rule stays resident if it applies
continuously, or if acting on a one-line router alone would be dangerous. "Feature worktrees" is the
clearest case — its router line cannot carry the `git diff --cached --quiet` check before
`git merge --squash` (whose omission commits over a concurrent session's staged work) or
"ask before `git branch -D`". Review gates, Documentation, Code & CLI conventions, the board flow
and Commits all fire on essentially every change, so paging them in each time costs more than
holding them.

Agents maintain this tree on their own — no confirmation needed, unlike `../direction/`
(`CLAUDE.md` "Direction docs").
