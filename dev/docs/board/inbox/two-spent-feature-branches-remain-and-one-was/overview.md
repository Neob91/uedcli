+++
priority = "p3"
kind = "chore"
summary = "installer-url and level-import are fully landed but still exist; level-import was pushed to origin, which cannot be undone."
+++

# Two spent feature branches remain, and one was pushed to origin

Both branches' work is on master and neither has anything left to give — verified file by file
2026-07-27: every file each branch touched is byte-identical to master, or master is ahead.

| branch | how it landed | state |
|-----------------|-----------------------------------------------|---|
| `installer-url` | squashed at `2f002e0`, then 4 later commits cherry-picked | spent |
| `level-import` | squashed at `96823b5`; its only later contribution was a corrected test diagnosis, now on master | spent |

**Do not squash-merge either.** Both merged master only up to `1969b0c` — before the board
migration — so a squash of `level-import` deletes `bin/board`, both board tests and every item
directory, and restores `dev/docs/specs/` and `dev/docs/plans/`. That is what an attempted merge on
2026-07-27 was about to do before it was aborted.

**`level-import` is pushed to `origin` (was ahead 15).** The worktree rules say never push a feature
branch, precisely because it is squashed away and a remote branch cannot be deleted — so this is
permanent dead weight on the remote. Nothing to fix; recorded so nobody mistakes it for live work.

Locally, deleting either branch needs `git branch -D` (`-d` refuses — a squash records no merge),
which is destructive, so it needs the owner's yes. Their worktrees under `.claude/worktrees/` can go
with them. Leaving them costs nothing but confusion.
