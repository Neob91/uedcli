+++
priority = "p3"
kind = "debug"
summary = "Live-verify brush intersect/deintersect --solidity collision matches the per-face rule"
+++

# Live-verify brush intersect/deintersect --solidity collision matches the per-face rule

Spun off from `subtractive-csg-remaining-cli-surface` (owner ruling 2026-08-02: that item is
verify+document+close, no new CLI surface). The `--solidity` flag on `brush intersect` /
`brush deintersect` already EXISTS (`brushcsg.apply_solidity`, `brushcsg.py:297`; faithful per-face
default). No CLI work remains.

What is NOT yet verified: that a BUILT map's actual collision matches the per-face rule the CLI
applies — a face inherited from an additive stays solid, a face from a subtractive is forced solid,
a semisolid keeps its flags, etc. That is a live-editor spike (materialize the trunk, inspect the
built collision), not a code change.

Task: build a small trunk exercising each `--solidity` mode through `brush intersect`/`deintersect`,
materialize it, and confirm the built collision matches `apply_solidity`'s per-face rule. Pin the
finding with a committed regression test per `dev/docs/rules/spikes.md`.
