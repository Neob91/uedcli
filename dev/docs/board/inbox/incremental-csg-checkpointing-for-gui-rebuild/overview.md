+++
priority = "p?"
kind = "unknown"
summary = "GUI Rebuild reprocesses every brush from scratch on any geometry edit; checkpoint CSG per brush-order position to cut this"
+++

# Incremental CSG checkpointing for GUI rebuild

`session_rebuild` (`uedcli/serve/app.py`) is the only GUI action that runs a CSG+lighting solve
(~24s on a real level, per `web/src/api.ts`'s own `postRebuild` doc comment). `build_scene`
(`uedcli/preview_native.py`) already caches two tiers by content hash: unchanged level -> reuse the
fully-lit scene; only light actors changed -> reuse the CSG solve and rerun just the (cheap) light
bake. Neither tier helps a geometry edit: any brush change forces
`uedcli_native.build_geometry_bspcsg(brushes)` to resolve CSG over the WHOLE brush list from empty
world, because the algorithm is order-dependent (each brush CSGs against the accumulated result of
every earlier brush, editor-faithful per `NATIVE-MATERIALIZE.md`).

Idea: checkpoint the native CSG solver's world-model state at each brush-order position (or at
sparse intervals). Editing brush N would replay only from the earliest changed order position
forward, reusing the checkpoint immediately before it, instead of resolving the whole level.

Not scoped. Open questions before this could go to spec:
- Checkpoint storage cost (a world `Model` per brush, or per N brushes, for a big level).
- Whether a checkpoint is safe to reuse across edits that reorder brushes (order_value changes),
  not just ones that only move/resize one brush in place.
- This touches the same CSG core the native-materialize byte-parity campaign
  (`NATIVE-MATERIALIZE.md`) is actively hardening for exact UED22 parity — any change here needs to
  preserve that fidelity, not just editor-preview speed.

Raised alongside `gui-unlit-fast-rebuild-button` (2026-09-27): that item decouples lighting from
CSG for a fast unlit preview; this item is the harder, un-scoped follow-on for the CSG cost itself.

Found uncommitted in an abandoned worktree (`gui-unlit-fast-rebuild`, created 2026-09-27, no
commits) and re-filed here verbatim so the finding isn't lost; original author unidentified. Related
to `incremental-gui-reload-only-re-resolve-actors` (the equivalent idea for Reload's per-actor
resolution, not CSG) and `native-preview-perf-an-8-shot-castle-batch` (skipping the collision-hull
pass for preview builds — a cheaper, narrower lever than checkpointing).
