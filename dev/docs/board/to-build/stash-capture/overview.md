+++
priority = "p3"
kind = "implement"
summary = "`stash capture -` (stdin)"
+++

# `stash capture -` (stdin)

Read a T3D snippet from stdin directly into a
stash entry, without going through `actor add`. Useful for
`stash deintersect X | stash capture - --id baked`. Deferred from the generator-pattern spec
(2026-06-24); needs its own spec.
