+++
priority = "p3"
kind = "chore"
summary = "Stale `canonicalize_mover_blob` references in two more ephemeral docs"
+++

# Stale `canonicalize_mover_blob` references in two more ephemeral docs

`specs/2026-07-18-unify-t3d-trees.md` (5 places) and `plans/2026-07-18-build-unify-t3d-trees.md:53`
still describe the deleted helper as shipped API ("**uedcli/movers.py** — gains a public
`canonicalize_mover_blob`"). Its sibling `specs/2026-06-27-uedcli-native-dx-read-design.md` got a
STALE banner in the same batch; these were missed. Ephemeral docs, so lowest priority — but the
deleted name now appears nowhere else. (2026-07-25, round-4 cold reviews.)
