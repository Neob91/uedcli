+++
priority = "p2"
kind = "chore"
summary = "`qualify.export_and_qualify` no longer exists but six files still cite it"
+++

# `qualify.export_and_qualify` no longer exists but six files still cite it

It is
referenced as a live precedent by `apply.py`, `driver.py`, `stub.py`, `packages.py`,
`tests/test_packages.py`, `tests/test_driver.py`, and by docs including `decisions.md` and two
spikes — and, load-bearingly, by `quirks.md`'s "Consequence for warm materialize" line and SP-E's
fix-candidate-1 rationale ("it already boots its own ephemeral editor precisely because a reused
editor is untrustworthy"). Anything reasoning from that precedent is reasoning from a function that
was deleted. Found during the 2026-07-26 spec review.
