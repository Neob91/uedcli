Ship Option A (render the sky zone as an unlit sub-scene) or Option B (cull the face entirely) as
v1 for `PF_FakeBackdrop` support in `level photo --native`?

## Context

Today a `PF_FakeBackdrop` face just draws its assigned texture flatly — visibly wrong for any level
with a real skybox room, and a deliberate, documented v1 simplification (see `spec.md`, "Current
state"). No RE documentation of the real engine's sky-zone parallax projection exists in this repo,
so a fully faithful implementation (Option C in `spec.md`) is its own future RE spike, not this item.

Two draft-tier options are buildable now with no new RE work:

- **A — render the sky zone as an unlit sub-scene** (recommended): resolve the face's zone's
  `SkyZoneInfo`, reuse the existing mirror-render machinery to render that zone's geometry from the
  `SkyZoneInfo`'s fixed vantage, composite it onto the backdrop face unlit. Not true parallax (fixed
  vantage per shot, not camera-relative), but shows something real instead of a flat texture. Needs
  a zone→`SkyZoneInfo` resolution step (a pattern `native/materialize.py`'s `resolve_zone_actors`
  already has) plus one extra sub-render per FakeBackdrop face per shot.
- **B — cull the face** (treat like `PF_Invisible`): trivial, no sub-render cost, but doesn't
  actually show the sky room — just removes the wrong texture, leaving background/void.

Recommendation: **A**. It's the only option that improves what the viewer actually sees, the cost
(one bounded sub-render per backdrop face) mirrors what mirrors already pay, and it reuses proven
zone-resolution machinery. B is a reasonable fallback only if A's implementation cost turns out
higher than the mirror-reuse sketch suggests once someone is actually in the code.

## Answer

<!-- Empty = open. -->
