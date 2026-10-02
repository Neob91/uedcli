+++
priority = "p3"
kind = "chore"
summary = "MAP EXPORT read path (_export_editor_level / Driver.map_export) is dead"
+++

# MAP EXPORT read path (_export_editor_level / Driver.map_export) is dead

Found while reducing `cli/dispatch.py` to routing + the error guard (command-layer reorg,
slice 10b). `dispatch._export_editor_level` (MAP EXPORT + parse — the editor read) had no caller
left: materialize goes through `apply.run_materialize`, photo through `preview_native`/
`preview_game`, and stash capture reads stdin T3D. Removing it left `Driver.map_export` with no
production caller at all.

Done in this slice: deleted the dead `_export_editor_level` (dispatch may hold only routing + the
guard), and repointed the now-broken symbol in `driver.py`'s module docstring
(`dispatch._export_editor_level` → `Driver.map_export`). The `test_stash_dispatch` guard that
patched `dispatch._export_editor_level` to prove `actor diagram` never drives the editor was dropped
(its `subprocess`/docker guard already proves the point).

Open for the owner:
- Prune `Driver.map_export` (and `driver.py`'s "Reading the level back goes through MAP EXPORT
  alone" claim, now describing a dead path)? It is UnrealEd/driver semantics, so not touched here.
- Or is a MAP EXPORT read expected to return on a future build/snapshot path, so the method stays?
