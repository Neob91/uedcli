+++
priority = "p1"
kind = "implement"
summary = "RE + implement faithful PF_FakeBackdrop rendering in level photo --native"
+++

# Add PF_FakeBackdrop support to level photo --native

`level photo --native`'s documented v1 scope explicitly defers sky rendering: a `PF_FakeBackdrop`
surf currently just draws its assigned texture flatly, like any other opaque face — no sky-zone
projection (`docs/reference/level/photo.md`, `de-containerization-follow-on-spec-items/spec.md`
§10, `spikes/2026-07-16-native-preview-anchor/perf.md:38`). Owner decision (2026-09-12): don't ship
a draft approximation — RE what UED22 actually does (the core sky-zone projection, the
Mirrored+FakeBackdrop combo, and the missing-`SkyZoneInfo` case), then implement that faithfully.
Bumped to p1. Full scope in `spec.md`; next action is the RE spike it describes, not a plan.
