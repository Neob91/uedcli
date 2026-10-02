+++
priority = "p3"
kind = "debug"
summary = "usability-nit leftover: single-name verb given multiple names dumps top-level usage` — e.g"
+++

# usability-nit leftover: single-name verb given multiple names dumps top-level usage` — e.g

usability-nit leftover: single-name verb given multiple names dumps top-level usage` —
e.g. `actor move A B` (move takes ONE name) → argparse reports "unrecognized arguments: B" with the
TOP-LEVEL usage, not `actor move`'s. Wanted: a scoped error naming the offending extra + the verb.
This is an argparse wart (unrecognized-args surface at the root parser after subparser parse); a clean
fix needs either a per-subparser `parse_known_args` wrapper or intercepting `error()`. Not a small
mechanical change — deferred from the 2026-07-19 nits batch for a deliberate approach.
