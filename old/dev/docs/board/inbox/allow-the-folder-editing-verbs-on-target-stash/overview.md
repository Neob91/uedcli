+++
priority = "p3"
kind = "implement"
summary = "Allow the folder-EDITING verbs on `--target stash|prefab`"
+++

# Allow the folder-EDITING verbs on `--target stash|prefab`

— the unify-T3D-trees
build (2026-07-19) made stash/prefab boxes persist a per-member `folder` sidecar (full trunk parity),
and `StashLevelSource`/`PrefabLevelSource` load/save now preserve it. But the folder-editing surfaces
(`actor folder set/unset/get`, `actor add --folder`, `actor find --folder/--no-folder`) still reject a
stash/prefab target via `_reject_nonlevel_target_for_folders` (deliberate scope line, NOT a storage
limitation now). Lifting it would let a captured subtree be re-organized in place. Needs its own small
design (does `find --folder` over a box make sense? all-or-nothing writes?) before building. Same note
applies to the CSG-order editing verbs (`actor order`) vs `_reject_nonlevel_target_for_order` — the
boxes carry `order_value` sidecars now, just not exposed to the ordering verbs.
