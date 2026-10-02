+++
priority = "p2"
kind = "chore"
summary = "Docs restructure: concurrency"
+++

# Docs restructure: concurrency

A live worktree (`brush-profile-generators`)
holds the pre-restructure tree; git cannot auto-merge an append into a file that has become a
directory. Land only when no worktree is in flight, or state the manual reconciliation.
