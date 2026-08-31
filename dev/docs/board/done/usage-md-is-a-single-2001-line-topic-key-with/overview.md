+++
priority = "p1"
kind = "docs"
summary = "usage.md is a single 2001-line topic key with no section addressing"
+++

# usage.md is a single 2001-line topic key with no section addressing

Fixed by the `usage.md` split (`dev/docs/superpowers/specs/2026-08-30-usage-md-split-design.md`):
`docs/usage.md` is deleted, replaced by `docs/reference/` (one topic key per command/family) and
`docs/usage/` (one topic key per task guide). No more duplicate `## Actors` anchor, no more
82-heading single file.
