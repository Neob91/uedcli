+++
priority = "p2"
kind = "debug"
summary = "`CLAUDE.md`'s \"The repo this tool lives in\" is factually wrong in this checkout"
+++

# `CLAUDE.md`'s "The repo this tool lives in" is factually wrong in this checkout

— it says uedcli lives at `Tools/uedcli/` inside `dx_lum` with `_scratch/` "two levels
up"; the git toplevel is `/home/neob91/Documents/Dev/uedcli`, `_scratch/` is at that root, and
there is no `Tools/`. Pre-existing, and the section stays permanently resident, so the error sits
in the most privileged position available. Scheduled for the docs-restructure plan's Task 9.
(`Tools/uplayctl/CLAUDE.md`, which mirrors these rules, is in a *different* repo — this
restructure silently desynchronises it.)
**RESOLVED 2026-07-26 (`ab0ad33`), Andrzej-decided:** the two sibling claims in this item are now
true rather than fixed-by-deletion — `.claude/worktrees/` was added to `.gitignore` (precisely,
not a blanket `.claude/`, so `settings.json` stays tracked), and `.claude/settings.json` was
created with `worktree.baseRef: "head"` so `EnterWorktree` branches from the current branch like
the manual procedure does. Reasoning belongs in `direction/process.md` when Task 4 lands it.
