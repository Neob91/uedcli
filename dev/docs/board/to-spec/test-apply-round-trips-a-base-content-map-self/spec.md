# Spec DRAFT — the live materialize round-trip has no real coverage

## Goal

Give the live "build a level and verify it round-trips through the editor" path real integration
coverage. Today the one live test is an unconditional-skip placeholder.

## Current state

- **No test named `test_apply_round_trips_a_base_content_map` exists.** Searched the tree and all git
  history — the string appears only in board-migration commits and this item. The `level apply` verb it
  names was **removed** (`uedcli/tests/test_cli.py:385`, `uedcli/tests/test_dispatch.py:427`); "apply"
  is now `level materialize` → `apply.run_materialize` (`uedcli/apply.py:226`). The item is a stale
  paraphrase migrated from the legacy `todo.md`.
- The real live round-trip test is `test_materialize_builds_and_verifies_live`
  (`uedcli/tests/test_materialize_verb.py:331-334`): marked `integration`, body is a single
  `pytest.skip("integration: requires the dx-lum-uned container")`. It **builds nothing** — a
  placeholder that always skips, so it covers zero even when the container is up.
- The one live test that actually runs is `test_map_export_round_trip_has_actors`
  (`uedcli/tests/test_driver_integration.py:29`): exports the loaded map and asserts ≥1 actor. It does
  **not** mutate or materialize.
- Offline internals are well covered: `test_apply.py` (materialized order, referenced-packages, atomic
  install) and `test_materialize_verb.py` (class resolution, overwrite guard, teardown, verify wiring),
  all against a stubbed editor.
- `Maps/Entry.dx` is a real Deus Ex base-content map (the intro), not a repo fixture. It has no `Light`
  actor, so "self-skips because Entry.dx has no Light to move" describes a not-yet-written test, not one
  that runs.

**Real gap:** no live test drives an edit and materializes it end to end. The placeholder skips
unconditionally; the export test never mutates.

## Approach / design

Two separable pieces:

1. **Implement the existing placeholder.** Make `test_materialize_builds_and_verifies_live` build a
   small synthetic trunk into a `.dx` against `dx-lum-uned`, H3-verify, and assert the file exists and
   re-parses — the "one-actor trunk" its own comment already promises. Gate the skip on **container
   absence** only, not unconditionally. Small, deterministic, no game-install dependency.
2. **Base-content-map round-trip (the item's literal ask), only if wanted.** Load a real base map, move
   a real actor, materialize, verify the move survives. This needs the DX install present and a chosen
   map+actor that is **guaranteed** to exist. `Entry.dx` has no `Light`; a self-skip on a missing actor
   is exactly the fragility to avoid — pick the actor deterministically (a class the map is known to
   contain), never skip on its absence.

## Recommendation

Do (1): implement the stub as a synthetic build+verify gated on the container. This closes the "always
skips" hole cheaply and without a game-install dependency. Treat (2) as a richer, separate integration
test to add only if the owner wants live coverage over real game maps — see the open fork.

## Test

The deliverable *is* a test. The offline suite is unaffected; the filled/added test runs under
`bin/test uedcli -m integration` against the live container.

## Open questions

- Synthetic-trunk build+verify vs a real base-content-map round-trip — a testing-philosophy fork. See
  `questions/synthetic-vs-real-map-coverage.md`.
- If a real map: which map, and which guaranteed-present actor to move (never a self-skip).
