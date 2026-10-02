+++
priority = "p1"
kind = "implement"
summary = "Fixed: /scene, /atlas, /lightmap now reuse /load's (search_files, index, defaults) instead of rebuilding it every request; /load and /rebuild deliberately untouched (spec.md/plan.md)"
+++

# GUI serve rebuilds ClassIndex on every request

Done. `uedcli/serve/app.py` gained a `_scene_inputs_ref` cache slot tied to `_trunk_ref`'s own
lifecycle and a `_current_scene_inputs()` accessor; `/scene`/`/atlas`/`/lightmap` read from it
instead of calling `_scene_inputs(project)` themselves, cutting a plain Reload's call count from 4
to 1. `/load`/`/rebuild` keep rebuilding fresh every time (they genuinely need to). A write-order
race between `_trunk_ref`/`_scene_inputs_ref` was found and fixed during code review. Full design
and review history: `spec.md`, `plan.md`.
