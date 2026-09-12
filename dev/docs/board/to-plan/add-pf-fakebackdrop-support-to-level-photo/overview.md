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

**RE spike done and independently reviewed** (`dev/docs/spikes/2026-09-12-pf-fakebackdrop-re/`,
`dev/docs/unrealed/rendering.md`): `URender::OccludeBsp` drops the face's own draw and renders a
child scene from the level's sky actor's location (viewer rotation DIVIDED by the sky actor's own
rotation, no parallax), falling back to today's flat-texture behavior only when the level has no
sky actor at all. `PF_Mirrored`/`PF_FakeBackdrop` are mutually exclusive (backdrop wins); `PF_Unlit`
is irrelevant; recursion shares `PF_Mirrored`'s cap. 36 facts pinned byte-exact, 29 as
`uedcli/tests/test_engine_facts.py::test_pf_fakebackdrop_*`.

**Spec review (also independent) found the first design draft rested on two false premises** —
`AZoneInfo.SkyZone` is not an authored per-zone property (it's resolved level-globally at runtime
via `LinkToSkybox()`; there is exactly ONE sky actor per level, not a per-face/per-zone lookup), and
`render.rs`'s mirror path already HAS a recursion cap (1, not absent as first assumed). Owner
ruling: adopt the real engine's shared cap-3 (a deliberate, known change to existing mirror
behavior — see `spec.md` §5 for the cost). `spec.md` is now revised to match; next action is a real
task-by-task plan (`writing-plans` skill).
