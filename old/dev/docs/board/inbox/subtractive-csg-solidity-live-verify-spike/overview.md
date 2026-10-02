+++
priority = "p3"
kind = "debug"
summary = "Live-verify that a built map's collision matches the per-face `--solidity` rule for `brush intersect`/`deintersect` (spike)."
+++

# subtractive CSG `--solidity`: live-verify built collision (spike)

Split from `subtractive-csg-remaining-cli-surface` (2026-08-02). `brush intersect`/`deintersect
--solidity` already exists (`brushcsg.apply_solidity`, `brushcsg.py:297`; faithful per-face default).
What is unverified is that the *built map's* in-engine collision actually matches the per-face
solidity rule the flag sets.

This is a live spike (drive a real materialize + collision probe), not a CLI change. Pin the result
with a committed regression per `dev/docs/rules/spikes.md`.
