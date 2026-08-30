+++
priority = "p1"
kind = "docs"
summary = "docs/README.md under-enumerates uedcli's capabilities"
+++

# docs/README.md under-enumerates uedcli's capabilities

`docs/README.md` is the orientation page (`docs show index`) and names only: `preview`, `brush poly
list`, brush clip, stash/prefab, the texture catalog, and `uedcli docs`. It omits entire verb
families that are real and documented in `usage.md`:

- class discovery (`class list`/`show`/`search`/`tree`/`classify`)
- the sound and music catalogs (`sound`/`music` `list`/`show`/`search`/`classify`)
- `level import` / `level reimport`
- `level doctor`
- `event graph`
- folders and labels (hierarchical/flat actor organization)
- movers (as a CLI verb family, not just the leveldesign craft sense)
- `brush measure relation`
- substrate/cache utilities

An agent orienting off `docs show index` alone — the documented entry point — would not learn any
of these verb families exist at all.
