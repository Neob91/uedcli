+++
priority = "p?"
kind = "unknown"
summary = "Actor folders — hierarchical actor organization (the \"groups overhaul\")"
+++

# Actor folders — hierarchical actor organization (the "groups overhaul")

— BUILT 2026-07-18
(plan `plans/2026-07-18-actor-folders-plan.md`; spec
`specs/2026-07-18-actor-folders-hierarchical.md`; decisions 2026-07-18 12:14/12:32/12:45 UTC).
`Actor.folder: str|None` typed field + per-actor trunk `folder` sidecar (atomic write/remove);
the delta-write diff compares folder BOTH directions incl `"x"`→None. New pure `folderlib.py`
(path/pattern grammar + the §3 globstar match). `actor folder set --to <path> <names|->` /
`unset` / `get` (`(none)` sentinel); `actor add --folder`; `actor find --folder <pattern>` /
`--no-folder`; `actor show` `// uedcli-folder:` carrier (+ `--t3d-only`); `stash/prefab apply
--folder` (beside `--group`). ALL folder surfaces reject `--target stash|prefab`. Folder excluded
from the canonical hash / never emitted to the map. Folded into `architecture.md` ("Folders");
`unrealed/t3d.md` already documents the carrier. Tests: `test_folderlib.py`, `test_folders.py`.
**Deferred → inbox:** `folder rename <old> <new>`, exact-single-node match, `--from-group` bulk
migration sugar.
