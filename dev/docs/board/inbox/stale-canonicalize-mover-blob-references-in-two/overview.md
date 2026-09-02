+++
priority = "p3"
kind = "chore"
summary = "Stale `canonicalize_mover_blob` references in two more ephemeral docs"
+++

# Stale `canonicalize_mover_blob` references in two more ephemeral docs

board item `delete-the-ephemeral-spec-specs-2026-07-18` (5 places) and once more in board item `delete-the-ephemeral-spec-specs-2026-07-18`
still describe the deleted helper as shipped API ("**uedcli/movers.py** — gains a public
`canonicalize_mover_blob`"). Its sibling `spec.md` got a
STALE banner in the same batch; these were missed. Ephemeral docs, so lowest priority — but the
deleted name now appears nowhere else. (2026-07-25, round-4 cold reviews.)
