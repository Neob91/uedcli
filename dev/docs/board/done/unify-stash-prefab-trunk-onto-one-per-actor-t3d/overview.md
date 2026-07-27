+++
priority = "p?"
kind = "unknown"
summary = "Unify stash/prefab/trunk onto ONE per-actor T3D tree"
+++

# Unify stash/prefab/trunk onto ONE per-actor T3D tree

— BUILT 2026-07-18 (decision 2026-07-18 23:01 UTC + addendum; spec `specs/2026-07-18-unify-t3d-trees.md`; plan `plans/2026-07-18-build-unify-t3d-trees.md`). New shared `t3dtree.py` (per-actor tree I/O + rank algebra + body strip/inject + `check_safe_segment` + `write/read_sidecars`) is the SINGLE code path for all three trees; `trunk.py` thin re-exports; `stash_register.py`/`stashlib.py` rewritten to `actors/<name>/{actor.t3d, order_value, folder}` + sibling `meta.json`/`packages`; `tree_io.py` DELETED. **Hard cutover** (Andrzej): old single-blob prefabs give a clean exit-2 `old-format prefab 'X' — re-capture it` (verified live on `lantern`/`computer_console`), never a traceback; stale flat stashes read empty. **Folder persisted per member** (full trunk parity; `apply --folder` overrides). `test_t3d_tree_consistency.py` asserts the same actor set writes BYTE-IDENTICAL `actors/` trees as trunk/stash/prefab (the invariant, enforced). 1807 offline green; committed HEAD run green. **Consequence for this repo:** ~11 committed prefabs (`lantern`, `computer_console`{,_big,_aligned}, `road_corner`, `stairs`, `trimmer`, `wall/pillar`, `wall/wall`, `reception_desk_lume/stand`, `x`) are old-format and must be re-captured. Inbox follow-ups: folder/order verbs could take `--target stash|prefab` now; prune the ephemeral spec+plan.
