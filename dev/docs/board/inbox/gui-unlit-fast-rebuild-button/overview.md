+++
priority = "p?"
kind = "unknown"
summary = "GUI unlit fast-rebuild button"
+++

# GUI unlit fast-rebuild button

Not scoped — found as a bare title (no body) in an abandoned, uncommitted worktree
(`gui-unlit-fast-rebuild`, created 2026-09-27), re-filed here so the finding isn't lost; original
author unidentified. The only surviving context is a cross-reference from the sibling item
`incremental-csg-checkpointing-for-gui-rebuild`, raised alongside it the same day: "that item
decouples lighting from CSG for a fast unlit preview." Read that item first — it has the actual
`session_rebuild`/`build_scene` cost breakdown this one would build on.

Whoever picks this up needs to reconstruct or re-derive the actual design (what "unlit" skips,
whether it's a separate button/endpoint or a Rebuild flag, how it interacts with the existing
geom_hash/light_hash cache tiers) — nothing beyond the one sentence above was ever written down.
