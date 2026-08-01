+++
priority = "p1"
kind = "owner-question"
summary = "actor-preview-faces: take over on the new cli/ structure, or leave to session bc54211?"
+++

# actor-preview-faces: take over, or leave to the other session?

You asked (goal) for `actor-preview-faces` to be finished. I did not build it, because it looks like
a live conflict:

- A separate branch/worktree `actor-preview-faces` (`bc54211`) exists, forked pre-reorg at `9fccd978`,
  clean tree, untouched ~4h+. Its commits are edge-x-ray / visibility-rule / doc-polish work.
- The wire/flat `--faces` work already landed on master and the command-layer reorg (`d4145f0`) moved
  it into `uedcli/cli/commands/actor/preview.py`. So `bc54211` is now pre-reorg and would conflict
  with the CLI move whenever it merges (it needs a rebase regardless of me).
- The item's remaining scope is S4 (`textured` faces, consumes the landed native-texture-decoder) and
  S5 (docs/rationale/board). S4 does not obviously appear on `bc54211`.

Building it myself risks duplicating or clobbering that session — the failure your board already
records under `two-sessions-were-assigned-native-texture`. So I stopped.

## What I need

Pick one:

1. **Take it over.** I build S4 (+S5) fresh in a new worktree off current master (`d4145f0`+), on the
   new `cli/` structure, and leave `bc54211` alone. (Confirm `bc54211` is not actively building S4.)
2. **Leave it** to session `bc54211` — I don't touch it.

## Answer

<!-- owner: 1 or 2, plus any constraint -->
