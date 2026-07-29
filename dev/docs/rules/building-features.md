# Building a feature

Take a work item that's ready to build (in the board's `to-build/` stage, with a written plan) and
ship it as one merged commit. Worktree and merge commands: [`worktrees.md`](worktrees.md).

1. Build the plan in a feature worktree, committing as you go; update user docs in the same change.
2. Check it: the formatter, linter, and type-checker pass; `bin/test` is green; read your own diff;
   run the new behavior and watch it work (the `verify` skill).
3. One subagent reviews the worktree's diff (`git diff base...HEAD`); fix the findings it confirms,
   re-test, and re-review if the fixes were large.
4. `git mv` the item into `done/` and cut its `overview.md` to a one-line record; then update the
   base to `origin`'s latest, squash-merge the worktree into it as one commit, and delete the worktree.
