# Replace the by-name in-place `brush clip <name>`, or keep both the filter and the by-name form?

## Context

`brush clip` is becoming a T3D-stdin filter. The by-name in-place trunk edit (`brush clip WALL
--plane …`) could be kept alongside it, or deleted.

Options:

- **Replace it with the filter (recommended).** One spelling, per no-back-compat-cruft. A placed
  actor is clipped by `actor show X | brush clip - … | brush replace X -` — the same rotation-aware
  result, since `actor show` carries the actor's full transform. Loses nothing; costs one extra pipe
  stage for the in-place case, and the shape recipes get simpler (one pipe, not add-then-clip).
- **Keep both.** The in-place case stays a single short command. Cost: two clip code paths and two
  doc spellings to keep true — exactly the dual-form maintenance surface the conventions forbid for an
  unreleased tool.

Recommendation: replace. Delete the by-name form in the same change that adds the filter.

## Answer

<!-- Empty = open. -->
