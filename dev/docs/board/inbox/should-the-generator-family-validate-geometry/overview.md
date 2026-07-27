+++
priority = "p3"
kind = "unknown"
summary = "Should the GENERATOR family validate geometry, not just class/texture refs?"
+++

# Should the GENERATOR family validate geometry, not just class/texture refs?

Today
  `brush build` (every shape) and `brush intersect`/`deintersect` validate only class + texture
  existence; `geometry.validate_brush` runs when geometry ENTERS THE TRUNK (`actor add`,
  `dispatch.py:1995`) and on `clip`/`replace`/`vertex move`/`bake`. So a generator's output that never
  reaches `actor add` — `brush build … > shape.t3d`, or piped into `brush intersect` — is never
  geometry-checked. Uniform today, and `decisions.md` 2026-07-25 10:20 UTC deliberately kept it that
  way rather than let the two new profile verbs become a two-verb exception. If early validation IS
  wanted, do it family-wide: one call in the shared `brush build` tail plus the intersect tail. Weigh
  the gain (an error at the step that owns the input) against the cost (a behaviour change to four
  existing verbs, and mostly a duplicate of a check one pipeline stage later). (Surfaced 2026-07-25.)

<!-- Surfaced by the profile-generator spec's cold-review gate (2026-07-25). -->
