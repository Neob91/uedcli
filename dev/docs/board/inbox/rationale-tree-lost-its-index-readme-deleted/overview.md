+++
priority = "p3"
kind = "owner-question"
summary = "[OWNER] rationale/ tree lost its index (README deleted)"
+++

# [OWNER] rationale/ tree lost its index (README deleted)

dev/docs/rationale/README.md was deleted in the docs-prune (owner-approved as ledger
archaeology). It also served as the tree's index / entry-shape reference; `preview.md` and
`surface.md` linked to it, and those dead links were removed. The `rationale/` tree now has no
index.

## Decision for owner

Leave it indexless, or restore a lean `README.md` (entry shape + a one-line "what this tree is",
no ledger history). Default: leave as-is.
