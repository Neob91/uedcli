+++
priority = "p1"
kind = "implement"
summary = "Retired the append-only decisions ledger and the single-file direction doc; replaced by the revised-in-place direction/ + rationale/ per-topic trees."
+++

# Docs restructure — done

The append-only decisions ledger and the derived single-file direction doc are deleted. Owner
decisions live in `dev/docs/direction/<topic>.md`, engineering rationale in
`dev/docs/rationale/<module>.md`, both revised in place. `dev/docs/rationale/MIGRATION.md` maps every
one of the 227 old ledger entries to its new home.
