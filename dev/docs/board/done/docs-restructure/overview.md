+++
priority = "p1"
kind = "implement"
summary = "Retired the append-only decisions ledger and the single-file direction doc; replaced by the revised-in-place direction/ + rationale/ per-topic trees."
+++

# Docs restructure — done

The append-only decisions ledger and the derived single-file direction doc are deleted. Owner
decisions live in `dev/docs/direction/<topic>.md`, engineering rationale in
`dev/docs/rationale/<module>.md`, both revised in place. The mapping from each old ledger entry to
its new home is recoverable from git history.
