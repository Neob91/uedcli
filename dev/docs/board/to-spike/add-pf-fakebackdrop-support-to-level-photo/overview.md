+++
priority = "p3"
kind = "implement"
summary = "Add PF_FakeBackdrop support to level photo --native"
+++

# Add PF_FakeBackdrop support to level photo --native

`level photo --native`'s documented v1 scope explicitly defers sky rendering: a `PF_FakeBackdrop`
surf currently just draws its assigned texture flatly, like any other opaque face — no sky-zone
projection (`docs/reference/level/photo.md`, `de-containerization-follow-on-spec-items/spec.md`
§10, `spikes/2026-07-16-native-preview-anchor/perf.md:38`). That was the right call for a first
cut, but it means any level with a real skybox room renders visibly wrong in a draft photo (a flat,
static texture where the sky should recede). Pre-spec for giving `PF_FakeBackdrop` a real (if still
draft-tier) treatment. Full design in `spec.md`; the open call on which v1 treatment to ship is
parked in `questions/v1-visual-treatment.md`.
