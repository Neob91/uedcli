+++
priority = "p2"
kind = "implement"
summary = "class arm C4 prewarm warms schema cache only, not the catalog derived-row cache or preview pool"
+++

# class arm C4 prewarm warms schema cache only, not the catalog derived-row cache or preview pool

The class-arm spec (§2) describes `class prewarm` as the optional eager pass over a **catalog
derived cache** (`~/.uedcli/cache/catalog/v<N>/packages/class/<stat-key>.json`, one row per class)
plus the **content-addressed preview pool** (`previews/<hh>/<hash>.png`). Neither exists yet: C1 did
not build a catalog derived-row cache, and C2 shipped `class preview` without the preview pool
(board: `class-arm-c2-preview-cache-pool-not-built-list`, `class-arm-c2-remainder-angles-multi-ref-stdin`).

C4's `class prewarm` therefore warms the **one persistent derived cache the class arm reads today**:
the per-package **schema cache** (`~/.uedcli/cache/schema/`, discovery + property blobs). Warming it
makes a later offline `class list`/`search`/`show` start warm, because building the `ClassIndex` and
resolving property schemas read through it. `prewarm` does not render previews or resolve mesh facts.

Gaps left for when the arm continues:

- **Preview pool** — `prewarm` cannot warm previews (no pool to write to); `--force` re-renders
  nothing. Ships with the C2 preview-cache-pool item.
- **Catalog derived-row cache** (§2) — the per-`(kind, package)` class-row cache is unbuilt, so
  there is no per-class derived row to warm.
- **Class defaults are not persisted** (C0 was deferred — board notes on the C1 commit), so cold
  `show`/`preview` still re-resolve defaults corpus-wide. `prewarm` warms schema props, not defaults.

When the preview pool and the catalog derived cache land, extend `class prewarm` to eagerly build
them (respecting the spec's own byte budget + the never-evict-current-process rule) and update
`docs/usage.md`.
