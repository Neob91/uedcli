# Feature worktrees

A feature is built in its own git worktree and squash-merged back into the branch it was branched
from. A worktree is a second working directory for the same repository on its own branch: separate
files on disk, shared git history, so nothing is cloned or pushed to move work between them.

Several agent sessions work this repo at once, and `git checkout` in the shared checkout would swap
the files under every other session mid-edit; a worktree cannot. That is also why this process never
switches the main checkout's branch. Why it is shaped this way:
[`../direction/process.md`](../direction/process.md).

The base is the branch the main checkout is already on — do not ask which branch, and do not switch
it. That one branch is both the branch-off point and the merge target.

A non-feature change — a doc correction, a chore sweep, a one-file fix — needs no worktree: it stays
on the checked-out branch and follows `CLAUDE.md` "Commits".

## 1. Create it

From the main checkout (the repo root — `CLAUDE.md`'s own directory):

```
base=$(git rev-parse --abbrev-ref HEAD)
git worktree add .claude/worktrees/<feature-slug> -b <feature-slug> "$base"
```

`.claude/worktrees/` is gitignored, so the second checkout is invisible to git, ripgrep and the test
runners. Never name a worktree `agent-*` — that prefix belongs to Claude Code's own agent isolation.

The harness equivalent is the `EnterWorktree` tool, which creates a worktree in the same directory
and moves the session into it. It branches from `origin/<default-branch>` unless the repo's
`.claude/settings.json` sets `worktree.baseRef: "head"` — which this repo does, so `EnterWorktree`
also branches from the current branch.

## 2. Build it there

Commit locally as you go — `CLAUDE.md` "Commits" applies inside a worktree exactly as in the main
checkout. A fresh worktree has no `.venv/` (gitignored), so the first `bin/test` there pays the
venv-creation cost once.

## 3. Never push the feature branch

It is squashed away on merge and a remote branch can never be deleted, so pushing one strands
permanent dead weight on `origin`. In-progress work is protected by local commits and by the branch
being short-lived. This is the one exception to `CLAUDE.md`'s "always push your work".

## 4. Squash-merge from the MAIN checkout

A squash merge must run where the base branch is checked out, the main checkout — one more reason not
to switch its branch:

```
git diff --cached --quiet || echo "index dirty — another session staged something; STOP"
git merge --squash <feature-slug>
git commit -m "<one short imperative subject>"
git push
```

Check the index first, as above. `git merge --squash` stages the whole merged result and the
following `git commit` commits everything staged, including whatever a concurrent session had staged.
If the index is not clean, stop and sort that out rather than committing over another session's work.

## 5. Clean up — but verify before deleting anything

Confirm the base now contains the work (`git diff <feature-slug> HEAD` prints nothing), then
`git worktree remove .claude/worktrees/<feature-slug>`.

The branch needs `git branch -D`, because `-d` refuses (a squash merge records no merge) — and
deleting a branch is destructive, so ask the owner first. Leaving the local branch costs nothing;
never delete it while that `git diff` is non-empty.

`ExitWorktree` with `action: "remove"` is the harness equivalent and needs `discard_changes: true`
after a squash merge, for the same reason `-d` refuses — say so plainly when asking, since that flag
is what discards the pre-squash commits.
