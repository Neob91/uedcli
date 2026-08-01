+++
priority = "p3"
kind = "docs"
summary = "Slice 1 characterization: coverage scope and items leaning on existing tests"
+++

# Slice 1 characterization: coverage scope and items leaning on existing tests

Record of what Slice 1 (command-layer reorg) added and where it relied on existing coverage, so a
later slice knows which characterization test guards which move.

## Added this slice

- `uedcli/tests/parser_baseline.py` + `test_parser_baseline.py` + fixtures under
  `fixtures/parser_baseline/`: help screens, normalized action tree, argv corpus, non-CLI import
  closure. Regenerate with `python -m uedcli.tests.parser_baseline`.
- `test_dispatch_error_boundary.py`: one stderr/exit regression for every class in the `dispatch()`
  guard (via patching `_dispatch` to raise), plus `TimeoutError`-before-`OSError` precedence,
  broken-pipe exit 0, and a few genuine end-to-end triggers.
- `test_source_baseline.py`: trunk `LOCK_EX` before+during write; stash/prefab meta+folder preserved
  through an edit; labels neither persisted nor restored; the `from_env` announce is emitted inside
  `TrunkLevelSource.save`, once.
- `test_ordering_baseline.py`: source-free order/folder/label box rejections; `actor preview
  --from-t3d` before source resolution; empty-stdin inside/outside a project; materialize/preview
  validation before project resolution; `_mover_index` translation matrix; preview filled-render
  tailored error + point-only no-op; plain `find` touches no schema; brush-scale cheap checks before
  the class resolver; save-vs-output ordering (add = save-before-output, brush scale =
  output-before-save; failing save surfaces); stash/prefab preview prologue order.

## Items covered by PRE-EXISTING tests (cited so a move names its guard)

- Folder-only and label-only trunk delta writes: `test_folders.py`, `test_labels_delta_write.py`.
- Interleaved writers / rank override / unchanged-file: `test_level_source.py`.
- Stash/prefab source round-trip: `test_tree_flag.py`.
- Ambient-announce end-to-end (once per command, read-silent, explicit-tree-silent):
  `test_env_level_and_echo.py`.
- preview-game PlayerStart precheck before boot: `test_preview_game.py`
  (`test_render_shots_no_playerstart_errors_before_any_boot`). The preview-game **provider**
  cache-hit/PlayerStart-refusal gate is a Slice 2 addition (no provider exists yet in Slice 1), so it
  is not characterized here.

## Partial / not newly pinned (judgement calls to revisit before the relevant move)

- Resource-call matrix (spec item 3): plain `find` (no schema) and point-only preview (no class
  index) are newly pinned; wire-vs-flat preview and typed-field-only prop edits lean on
  `test_preview_faces.py` / `test_actor_prop.py` rather than dedicated new order probes.
- Output-before-save (spec item 7): `brush scale` is pinned as the representative branch; `actor
  rotate`, `apply-transform` and `poly align` were NOT each given a new dedicated order probe (same
  print-then-`src.save` shape; existing verb tests exercise them). Add one before moving each if its
  ordering is not otherwise guarded.
