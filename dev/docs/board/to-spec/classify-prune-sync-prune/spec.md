# Spec — `classify prune` / `sync --prune`

## Goal

Give the texture catalog a way to actually **remove** entries for textures that are gone from their
package. Today `sync` only marks a vanished texture `removed = true` and keeps its manifest row
forever; there is no verb to drop those rows. Deferred from the 2026-06-22 texture tool.

## Blocking concern — this may be throwaway work

`direction/asset-catalog.md` supersedes the 2026-06-22 name-keyed catalog this item targets. The
direction states plainly:

- "**There are no `stale`/`removed`/`changed` flags to maintain.** Change is a derived query, not
  stored state … the old classification becomes an **outdated entry** — a shard whose identity resolves
  to nothing on the current search path. `classify list-outdated` surfaces it … and `classify prune`
  removes it."
- "**The legacy name-keyed texture catalog is deleted, not migrated.**"

So the redesign already owns a `classify prune` — but over **hash-keyed shards keyed by identity**, not
over a `removed` boolean on a per-package name-keyed manifest. Building `prune` against the current
`texture_catalog.py` `removed` flag is work on a store the direction says will be deleted outright.
This is the first thing to settle — see `questions/build-now-or-with-the-redesign.md`.

The rest of this spec covers **Option A: build it now against the legacy manifest**, so the design is
ready if that is the owner's call.

## Current state (legacy manifest)

- `texture_catalog.TextureEntry` carries `removed: bool` (`uedcli/texture_catalog.py:54`).
- `reconcile` (`:172`) sets `removed=True` on a prior stem that the latest batchexport no longer
  produced and was not claimed as a rename source (`:224`). Removed entries persist in the manifest.
- `bucket` (`:231`) buckets `removed` first; `status_counts`/`list --removed` report them;
  `_entries` (`:296`) excludes them from `search`/`tags`. A removed entry can still be **resurrected**
  by `reconcile` if the texture returns (`:200`), which is why removal is a deliberate act, not
  automatic.
- No `prune` verb exists — `texture` sub-verbs are `sync|list|search|tags|classify {status,set}`
  (`uedcli/cli/parsers/texture.py`, `uedcli/cli/commands/texture.py`).
- Manifests are per-package JSON under the catalog dir, written atomically under a per-package flock
  (`save_manifest`, `_package_lock`).

## Design (Option A — legacy manifest)

Per `conventions.md` "Verbs compose", prune is a **mutating verb over a set**: it drops the `removed`
rows from the manifests. Two candidate surfaces; they are not both needed (`conventions.md`: no
back-compat, one spelling).

**Recommended: `texture classify prune`** (a peer of `classify status`/`set`), not `sync --prune`.
Rationale: `sync` is the discover/export/reconcile pass; deletion of curated rows is a distinct,
destructive act that should be its own verb, not a flag riding the most-run command. It also composes:
`prune` with no args prunes all packages; `--package P` scopes it; `--ref R` (or stdin `-`) prunes a
specific set — matching the mutating-verb stdin convention.

Surface:

```
texture classify prune [--package P] [--dry-run] [--catalog-dir DIR]
    help: "remove catalog rows for textures gone from their package (state 'removed'); "
          "by default all packages — restrict with --package"
    --dry-run  help: "list the refs that WOULD be pruned; write nothing"
```

Behavior: for each manifest (optionally filtered by `--package`), drop every `TextureEntry` whose
`removed` is true, atomic-save under the same per-package flock `classify set` uses. Print each pruned
ref to stdout (one per line, so it composes), a count to stderr. A manifest left with zero textures is
still written (an empty-but-tracked manifest), not deleted — deleting the JSON is a separate concern
and would surprise a `git`-tracked catalog.

Removing a `removed` row is safe because the entry holds no live classification a resurrection would
lose that `reconcile` couldn't re-derive: a removed texture that returns unchanged comes back with
`colors_source` re-derived; only human `tags`/`description` are lost. So prune of a **classified**
removed row is real data loss — see Edge cases.

### Interaction with the direction's `list-outdated`/`prune`

If Option A ships, name and shape it so the eventual redesign's `classify prune` (over shards) is a
drop-in rename, not a third spelling — same verb name, same "prints what it removed" contract,
`--dry-run`. That keeps the throwaway surface minimal.

## Edge cases & errors

| Case | Behavior | Exit |
|------------------------------------------|--------------------------------------------------|---
| No removed entries anywhere | print nothing to stdout, "0 pruned" to stderr | 0 |
| `--package P` not in catalog | exit 2, `no catalog for package: P` (matches `classify set`) | 2 |
| Pruning a **classified** removed row | prune it, but WARN to stderr naming the ref + that its tags/description are dropped (irrecoverable curation loss) — or require `--force` (owner call) | 0/2 |
| Corrupt manifest JSON | exit 2 naming the file (matches `_load_all`'s skip → here it must be a hard error since we write) | 2 |
| No project and no `--catalog-dir` | existing `ProjectError` exit 2 | 2 |
| `--dry-run` | print refs that would go, write nothing | 0 |

The classified-removed-row loss is the one genuine hazard: prune is meant for churn (a texture
renamed/deleted), but a removed row can still carry human classification. Recommend WARN-and-prune
with the ref named, since the whole point is to clear the row; a `--force` gate is the stricter
alternative. Flag for the owner in the question below rather than choosing silently.

## Tests

- `reconcile` a package so a stem goes `removed`, then `prune` → row gone, manifest still valid, ref
  printed.
- `prune --dry-run` → nothing written, refs listed.
- `prune --package` scoping; unknown package → exit 2.
- Pruning a classified removed row → the warn/force behavior chosen.
- Prune leaving an empty manifest → file remains, loads as an empty `Manifest`.

## Open questions

- **Build now vs with the asset-catalog redesign** — the blocking fork.
  `questions/build-now-or-with-the-redesign.md`.
- If built now: **WARN-and-prune vs `--force`** for a classified removed row (data-loss gate). Folded
  into the same question since it only matters under Option A.
