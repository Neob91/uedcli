+++
priority = "p?"
kind = "unknown"
summary = "`actor scale`/`apply-transform` → `brush scale`/`brush apply-transform`"
+++

# `actor scale`/`apply-transform` → `brush scale`/`brush apply-transform`

— BUILT 2026-07-20 (WIDE
breaking, 2-reviewer cold-gated). Gate verified first: MainScale/PostScale are `ABrush` native fields
(not on Engine.Actor; no non-brush trunk actor carries them; a mesh uses DrawScale) → moved to the
`brush` namespace. As brush verbs they now REJECT a non-brush (point) actor all-or-nothing (new guard
+ tests). `actor rotate` stays. Reviewers caught the missing guard test (added) + this board item.
cli/dispatch/transform/doctor + usage/architecture/quirks + 4 test files; decision 2026-07-20 00:00
UTC. Commits `41b5a38ef`, `995388b9f`.
