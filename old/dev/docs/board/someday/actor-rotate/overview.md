+++
priority = "p3"
kind = "implement"
summary = "`actor rotate --to` (absolute base rotation)"
+++

# `actor rotate --to` (absolute base rotation)

`actor rotate` is
`--by`-only; `mover key rotate --to` introduced absolute keyframe rotation. A symmetric
`actor rotate --to` would let `mover key rotate 0`'s redirect point at an absolute base verb (it
currently points at `actor rotate --by` / a manual delta). Deferred from mover support
(`direction/generators.md`, 2026-06-25, Decision 10).
