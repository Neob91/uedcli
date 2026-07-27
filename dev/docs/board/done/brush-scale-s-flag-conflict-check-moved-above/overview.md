+++
priority = "p3"
kind = "chore"
summary = "`brush scale`'s flag-conflict check moved above the resolver — `inbox.md` CLOSED 2026-07-25"
+++

# `brush scale`'s flag-conflict check moved above the resolver — `inbox.md` CLOSED 2026-07-25

The `--to` + `--pivot`/`--pivot-actor` mutual-exclusion check sat below
`_mover_index`, so `brush scale --to 2,2,2 --pivot 0,0,0` with no games config blamed the missing
config instead of the conflicting flags. Now checked with the other cheap argument checks, pinned
by a regression that stubs the resolver seam to raise.
