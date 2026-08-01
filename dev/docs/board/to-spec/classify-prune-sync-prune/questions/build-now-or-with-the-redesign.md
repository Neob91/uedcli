# Build `classify prune` now against the legacy manifest, or with the asset-catalog redesign?

## Context

This item (`classify prune` / `sync --prune`) removes `removed`-flagged rows from the current
name-keyed per-package texture manifest (`texture_catalog.py`).

`direction/asset-catalog.md` supersedes that whole catalog:
- The legacy name-keyed catalog is "**deleted, not migrated**".
- The new store is **hash-keyed shards, one file per asset**, with **no `stale`/`removed`/`changed`
  flags** — an "outdated entry" is a derived query (a shard whose identity resolves to nothing on the
  current path), surfaced by `classify list-outdated` and removed by `classify prune`.

So the direction already names a `classify prune`, but over a different store with different mechanics.
Building it now against the `removed` boolean is work on a store slated for deletion.

Options:
- **A — build now** against the legacy manifest (spec §Design A). Gives the catalog a working prune
  today; thrown away (or mechanically renamed) when the redesign lands. If chosen, also settle the
  data-loss gate for a **classified** removed row: WARN-and-prune (recommended) vs require `--force`.
- **B — fold into the redesign** (recommended): don't build against the legacy store; `classify prune`
  ships as part of the asset-catalog hash-keyed classify store, where `list-outdated`/`prune` are
  already specified. Move this item to `someday/` or close it as subsumed, and let the redesign item
  own the verb.

Recommendation: B — the direction already owns this verb in the target design, and A is throwaway on a
store marked for deletion. Confirm before either building or closing.

## Answer

<!-- Empty = open. -->
