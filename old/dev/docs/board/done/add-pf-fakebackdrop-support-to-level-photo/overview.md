+++
priority = "p1"
kind = "implement"
summary = "Implement faithful PF_FakeBackdrop rendering in level photo --native"
+++

# Add PF_FakeBackdrop support to level photo --native

Shipped (`c61c3d3d` and preceding commits): `render.rs` renders a `PF_FakeBackdrop` face as a sky
sub-render from the level's `SkyZoneInfo` actor (viewer rotation divided by the sky actor's own
rotation, no parallax), falling back to flat-texture only with no sky actor. Mirror's recursion cap
generalized 1→3 (shared budget, per the real engine). `uedcli-native/src/render.rs`,
`uedcli/preview_native.py`, `uedcli/tests/test_engine_facts.py`, `docs/reference/level/photo.md`.
