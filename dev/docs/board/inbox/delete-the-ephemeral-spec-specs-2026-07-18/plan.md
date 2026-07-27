# Build plan: unify stash/prefab/trunk onto ONE per-actor T3D tree

**Status:** building. Ephemeral — fold outcomes into `architecture.md`/`usage.md`, then delete.

**Authorities:** `decisions.md` `2026-07-18 23:01 UTC — INVARIANT: stash, prefab, and trunk MUST
share ONE T3D tree format` + its `(addendum) — unify-T3D-trees sub-choices`; spec
`spec.md` (the blueprint), overridden on TWO Andrzej-decided points
below.

## Reconciliation of the spec's "Open sub-choices" to the DECIDED answers

The spec presented two open sub-choices with recommendations; Andrzej decided AGAINST both
recommendations. This build follows the decisions, not the spec's recommendations:

- **Sub-choice (1) migration = HARD CUTOVER** (spec recommended (A) auto-convert-on-read + `prefab
  migrate`). No dual-read of the old single-blob prefab. `read_prefab` on an old-format prefab
  (`<name>.t3d` file, no new `<name>/actors/` dir) raises a dedicated `OldFormatPrefab` exception →
  dispatch surfaces a CLEAN exit-2 message `old-format prefab 'X' — re-capture it (the on-disk
  format changed)`, never a traceback. The `_read_old_prefab` reader, the new-dir-wins precedence,
  and the swap-then-unlink migration cleanup from the spec are all DROPPED (dead under a hard
  cutover). Old-format names still appear in `list_prefabs` so the actionable error surfaces on use
  (rather than a misleading "not found"). Stash old entries (throwaway) → treated as absent.
- **Sub-choice (2) folder = PERSISTED per member** (spec recommended (a) placement-time-only). Each
  stash/prefab member carries its own `folder` sidecar (full trunk parity). This threads a folder
  channel through capture → `write_stash`/`write_prefab` → `read_stash`/`read_prefab` → apply:
  - `_capture_from_t3d` gains a `folders` source map and returns a per-member `folders` dict.
  - `write_stash`/`write_prefab` gain `folders=` (name→folder|None); the sidecar is written via the
    shared `write_actor_tree` (`Actor.folder`).
  - `read_stash`/`read_prefab` return a 5th element `folders` (name→folder|None).
  - `StashLevelSource`/`PrefabLevelSource` load/save preserve folders (edits don't drop them).
  - `_apply_set` uses each member's stored folder as the placement default; `--folder` OVERRIDES all.
  - The trunk-only `--target stash|prefab` folder/order EDITING guards stay as-is (deferred; flagged
    to inbox) — the sidecars now exist but exposing the editing verbs on those targets is a separate
    scope.

## Production changes

- **NEW `uedcli/t3dtree.py`** — the ONE shared per-actor tree I/O: rank algebra (`rank_between`,
  `ranks_between`, `initial_ranks`, `append_rank`, `duplicate_ranks`), name alloc (`alloc_name`),
  body strip/inject (`dump_actor_body`/`load_actor_body`), `check_safe_segment` (public),
  `write_actor_tree`/`read_actor_tree` (moved verbatim from `trunk.py`'s `write_level`/
  `read_level_with_bodies`), `remove_actor`, and `write_sidecars`/`read_sidecars` for the beside-
  `actors/` extras (`packages` + `meta.json`).
- **`uedcli/trunk.py`** — thin re-exports over `t3dtree`; `read_level`/`write_level`/… names kept so
  callers/tests don't churn.
- **`uedcli/stash_register.py`** — `write_stash`/`read_stash` rewritten as wrappers over `t3dtree`
  (per-actor tree + sidecars + folder channel + `_ranks_for` preserve-then-append + stale-flat
  detection); `exists`/`list`/`drop` intact.
- **`uedcli/stashlib.py`** — `write_prefab`/`read_prefab`/`list_prefabs` rewritten (per-actor tree +
  sidecars + folder channel + `OldFormatPrefab` hard-cutover error); wrapper helpers `_level_from_blobs`,
  `_ranks_for`, `_read_ranks_if_present`. `referenced_packages`/`normalize_for_capture`/`translate`/
  `with_group`/`with_folder`/`validate_member_name`/`format_summary` unchanged.
- **`uedcli/movers.py`** — gains public `canonicalize_mover_blob` (relocated from `tree_io`).
- **`uedcli/dispatch.py`** — folder channel threaded (capture, promote, apply, LevelSources);
  `prefab drop` rmtree's the dir; `_read_prefab_or_exit`/`PrefabLevelSource.load` surface
  `OldFormatPrefab` cleanly; capture canonicalizes movers on external ingest.
- **DELETE `uedcli/tree_io.py`** — no production caller after this change.

## Tests
Consistency (byte-identical trunk/stash/prefab `actors/` trees), stash+prefab round-trip through the
shared path, folder persistence capture→store→read→apply + `--folder` override, rank stability,
sibling `meta.json`/`packages`, hard-cutover clean error (exit 2, no traceback), mover-at-capture
canonicalization. Update `test_stash_register`, `test_stashlib`, `test_stash_dispatch`,
`test_target_flag`, `test_apply`, `test_movers`. New: `test_t3d_tree_consistency`,
`test_prefab_migration`.
