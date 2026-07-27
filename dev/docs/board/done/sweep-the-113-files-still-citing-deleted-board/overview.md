+++
priority = "p1"
kind = "chore"
summary = "Done — the tree no longer cites a deleted board file or a deleted spec/plan path."
+++

# Sweep the files still citing deleted board paths

**Done 2026-07-27.** Both censuses in the migration's done-when now return nothing outside the two
files that may not be touched (`decisions.md`, frozen; `2026-06-20-open-questions-for-andrzej.md`,
the owner's).

What was repointed: 392 board-file citations became the stage directory (`board/inbox/`), 240
spec/plan path citations became ``board item `<slug>` `` — or a plain relative filename where the
citing file lives in the same item. The repo-root `README.md` and `dev/docs/README.md` describe
directories now; `uedcli/cli.py`'s `--within-bbox` help no longer sends a *user* into the developer
docs at all.

The four stale `CLAUDE.md` rules are corrected, including the bounce rule — an item that gains a
blocking question now stays where it is and gains a `questions/` file (owner ruling, 2026-07-27).

**Deliberately left standing:** board item `the-board-is-being-restructured-into-one`'s `spec.md`
keeps its `inbox.md:2935`-style measurements. They record the pre-migration file the spec was
written to convert; rewriting them would destroy the evidence rather than update it.
