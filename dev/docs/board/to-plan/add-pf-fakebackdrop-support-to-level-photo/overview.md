+++
priority = "p1"
kind = "implement"
summary = "Implement faithful PF_FakeBackdrop rendering in level photo --native"
+++

# Add PF_FakeBackdrop support to level photo --native

`level photo --native`'s documented v1 scope explicitly defers sky rendering: a `PF_FakeBackdrop`
surf currently just draws its assigned texture flatly, like any other opaque face — no sky-zone
projection (`docs/reference/level/photo.md`, `de-containerization-follow-on-spec-items/spec.md`
§10, `spikes/2026-07-16-native-preview-anchor/perf.md:38`). Owner decision (2026-09-12): don't ship
a draft approximation — RE what UED22 actually does, then implement that faithfully.

**RE spike done** (`dev/docs/spikes/2026-09-12-pf-fakebackdrop-re/`): `URender::OccludeBsp` drops
the face's own draw and renders a child scene from the `SkyZoneInfo` actor's location (viewer
rotation, sky-zone position, no parallax), shared per zone, falling back to today's flat-texture
behavior only when the zone has no `SkyZoneInfo`. `PF_Mirrored`/`PF_FakeBackdrop` are mutually
exclusive (backdrop wins); `PF_Unlit` is irrelevant; recursion shares `PF_Mirrored`'s depth-3 cap.
36 facts pinned byte-exact (12 as `uedcli/tests/test_engine_facts.py::test_pf_fakebackdrop_*`).
Full write-up + implementation-plan sketch in `spec.md`. Next action is a real task-by-task plan
(`writing-plans` skill).
