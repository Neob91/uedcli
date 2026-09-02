# Confirm: the standalone repo was seeded fresh (no dx_lum history), and that is accepted?

## Context

The board note framed git-history handling as an open choice — a fresh repo vs a `filter-repo`/subtree
extraction of `Tools/uedcli/**` that preserves dx_lum's history. It was in fact done as a **fresh
copy**: `github.com:Neob91/uedcli` begins at a bare "Initial" commit (2026-07-25) with none of the
dx_lum history, and it is already pushed (`HEAD == origin/master`, 213 commits since).

Because the repo is published, recovering the old history now would mean re-seeding and force-pushing
over `origin/master` — a rewrite of published history, which the global rules forbid, and which would
break any existing clone. The practical window to preserve history closed at the first push.

So this is a confirmation, not a live fork:

- **Accept the fresh, no-history seed (recommended / only non-destructive option).** dx_lum's git log
  remains intact in the dx_lum repo for archaeology; uedcli's own history starts at "Initial".
- Re-seed to preserve history — rejected: forbidden history rewrite of a published repo.

Confirm the fresh seed is accepted so the item can close its history concern.

## Answer

<!-- Empty = open. -->
