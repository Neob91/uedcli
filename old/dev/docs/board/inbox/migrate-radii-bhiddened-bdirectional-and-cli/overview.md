+++
priority = "p3"
kind = "chore"
summary = "Migrate radii/bHiddenEd/bDirectional and CLI/write-path resolution onto the shared Rust core"
depends-on = ["shared-rust-core-for-class-schema-resolution"]
+++

# Migrate radii/bHiddenEd/bDirectional and CLI/write-path resolution onto the shared Rust core

Follow-up to `gui-inspector-props-payload-redesign`'s v17 fix round. That spec's "one
implementation" goal is scoped to the Inspector-props path only (`effective_props.py`'s walk,
superseded by the shared core) — the owner's explicit call, 2026-09-24, matching the existing
Non-goal that already excludes actor metadata (folder, labels, sprite, radii). Several OTHER
resolution paths in this codebase read class defaults through separate, narrower code and were
deliberately left untouched by that pass:

- `uedcli/serve/scene.py`'s `_actor_radii` — collision/light/sound/volumetric radius overlays.
- `uedcli/serve/scene.py`'s `_is_hidden_ed` — the `bHiddenEd` viewport-visibility default.
- `uedcli/serve/scene.py`'s `_actor_directional_arrow` — the `bDirectional` arrow-gizmo default.
- The CLI's own class-display (`class show`) and the write path's validation
  (`propedit.effective_value`, `uprops.resolve_class_properties`/`resolve_class_defaults`,
  `classdefaults`, `normalize.compare_view`'s typed compare, materialize's post-verify).

The owner's stated intent: eventually everything that resolves class defaults should reuse the
shared core, once it exists and is proven out by the Inspector feature. Not scoped or sized here —
this item exists so the intent isn't lost, not as a commitment to do it next.
