# stash

A **stash** is a private, machine-local register entry (a named, captured actor set living in
`.uedcli/stash/<id>/`). A stash, a prefab, and a level trunk are the **SAME on-disk format** — the
per-actor T3D tree `actors/<name>/{actor.t3d, order_value[, folder]}` — read/written through one
shared code path, with any per-box extras (`meta.json` capture anchor, `packages` deps) beside
`actors/`. It carries the set's texture-package deps and each member's folder.

```
stash capture [- [<names…>] | <names…>] [--id ID] [--force] [--from-t3d <FILE…>]
stash show    <id> [<names…>] [--summary]        # T3D dump (default), or a bbox/class/poly summary
stash list                                        # register ids
stash diagram <id> [<names…>] <diagram opts>      # composite render (like actor diagram)
stash drop    <id>
stash apply   <id> [--at X,Y,Z] [--group NAME | --no-group] [--folder PATH]
stash promote <id> --as <name> [--force] [--prefab-dir DIR]
```

- **`stash capture`** takes actors from the current level (empty names = all), from one-or-more T3D
  files via **`--from-t3d <FILE…>`** (multiple concatenate), or from a **`-` stdin T3D snippet**
  (`brush build cube | stash capture -`). A leading `-` reads the T3D from stdin as the source; any
  remaining names still select a subset. `-` is mutually exclusive with `--from-t3d` and `--tree`
  (each names a source); empty/whitespace-only stdin exits 2. `--id` defaults to an
  auto-slug from the first actor name; `--force` overwrites an existing id. Capture normalizes the set
  to its bbox-min corner and records the original world anchor. It reads the game's `.u` packages
  (an ingested Mover is folded to its base pose, needing the class hierarchy — see
  [Projects](../README.md#projects-uedclitoml)).
- **`stash apply`** is a **model-side merge into the current level** (no editor): it translates to
  the placement anchor, auto-allocates fresh names, sets Group, appends order, and unions the set's
  packages. **Without `--at`, it applies at the captured world anchor.** `--group` defaults to the id;
  `--no-group` strips it; `--folder PATH` also stamps a uedcli-side folder (independent of `--group`).
- **`stash promote`** copies a register entry into the durable prefab library (the sharing step) —
  see [`prefab`](prefab.md).
- **CSG-combining a stash** is not a stash verb: there is no `stash intersect`/CSG-combine verb — for
  the worked pipeline, see [CSG combining a stash](../usage/csg-combine-a-stash.md).

See also: [`prefab`](prefab.md), [`brush intersect`/`brush deintersect`](brush/intersect.md), [`actor diagram`](actor/diagram.md).
