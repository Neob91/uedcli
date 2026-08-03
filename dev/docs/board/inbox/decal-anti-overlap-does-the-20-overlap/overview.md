+++
priority = "p3"
kind = "owner-question"
summary = "decal anti-overlap: does the 20% overlap tolerance apply to point-actor MARKERS too, or only decal-vs-decal?` — Andrzej said \"allow up to 20% overlap between de"
+++

# decal anti-overlap: does the 20% overlap tolerance apply to point-actor MARKERS too, or only decal-vs-decal?` — Andrzej said "allow up to 20% overlap between de

decal anti-overlap: does the 20% overlap tolerance apply to point-actor MARKERS too, or
  only decal-vs-decal?` — Andrzej said "allow up to 20% overlap between decals". The build applies the
  `_DECAL_OVERLAP_TOLERANCE` uniformly to ALL obstacles in the resolver's set, which includes point-actor
  marker footprints (they share the `occupied` obstacle list). So a number may currently sit up to 20%
  over a marker. Provisional reading; confirm or split the tolerance (0 for markers, 20% for decals).
  Recorded in spec amendments. Flagged by the build-review gate.

_(removed 2026-07-24: this `[debug]` rotation post-verify item was a duplicate — the fix landed as
the `Rotation` compare-time fold was generalized to every property by
the class-default contraction of 2026-07-25 00:36 UTC, and now falls out of the TYPED compare of
2026-07-25 02:15 UTC. Both halves of the original note are now wrong and are corrected here: the
equivalence does NOT live in `normalize_actor`, and the trunk does NOT store the editor's
zero-omitted spelling — the trunk stays faithful and the resolution to class defaults happens on the
throwaway compare view. My repro predated the fix.)_

<!-- ── small-fixes batch build (the 2026-07-25 small-fixes batch) ── -->
