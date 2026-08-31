# prefab

A **prefab** is the durable, git-tracked, shareable form under the library root
(`<prefabs-dir>/<name>/`). A stash, a prefab, and a level trunk are the **SAME on-disk format** —
the per-actor T3D tree `actors/<name>/{actor.t3d, order_value[, folder]}` — read/written through one
shared code path, with any per-box extras (`meta.json` capture anchor, `packages` deps) beside
`actors/`. It carries the set's texture-package deps and each member's folder.

Its **reads are project-only** (they touch just the tracked dir); `apply` mutates the current level.
The library root is the resolved project's prefabs dir (the `uedcli.toml` `prefabs` key, default
`<root>/prefabs/`); override per-invocation with **`--prefab-dir DIR`**, placed **before** the
sub-verb (with the flag, no project is needed).

```
prefab [--prefab-dir DIR] list
prefab [--prefab-dir DIR] show  <name> [<names…>] [--summary]
prefab [--prefab-dir DIR] diagram <name> [<names…>] <diagram opts>
prefab [--prefab-dir DIR] apply <name> [--at X,Y,Z] [--group NAME | --no-group] [--folder PATH]
prefab [--prefab-dir DIR] drop  <name>
```

- **Unlike `stash apply`, `prefab apply` also defaults to the captured anchor** with no `--at`
  (`--at` overrides). `--group`/`--no-group`/`--folder` behave as in [`stash apply`](stash.md).

`prefab list`/`prefab drop` are read/manage verbs over the library, same shape as `show`/`diagram`/
`apply` above.

See also: [`stash`](stash.md) (`stash promote` fills the library), [`brush intersect`/`brush
deintersect`](brush/intersect.md), [`actor diagram`](actor/diagram.md).
