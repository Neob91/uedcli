+++
priority = "p2"
kind = "debug"
summary = "stash/prefab write_tree_box has no lock — concurrent writers silently clobber"
+++

# stash/prefab write_tree_box has no lock — concurrent writers silently clobber

`stashlib.py:185-217` (`write_tree_box`), reached via `stash_register.FileStashRegister.write_stash`
and `cli/level_sources.py` `StashLevelSource.save` / `PrefabLevelSource.save`. It does
load → mutate in memory → full non-delta rewrite (build in `.staging/`, `rmtree(dest)`,
`os.replace`). Unlike `TrunkLevelSource.save` (`cli/level_sources.py:115-119`, which takes
`fcntl.flock` on `.locks/level-<name>.lock` before writing), this path takes NO lock anywhere.

Trigger: two `uedcli` invocations edit the same box concurrently — e.g. two agents run
`actor prop set --tree prefab/hangar …`. Each load→mutate→save; whichever `os.replace` lands last
wins outright, the other's edit is gone — no conflict detection, no merge, no warning.

The docstring's accepted-risk language covers only the crash-during-`rmtree`→`os.replace` window
(recoverable: prefab is git-tracked, stash is throwaway). It does NOT cover two SUCCESSFUL concurrent
writers racing — that isn't crash-dependent and isn't accepted anywhere. For a shared, agent-editable
prefab between commits (the normal working state) this is real silent edit loss.

Fix: take a per-box `flock` (key off `dest`, e.g. `dest.parent/.locks/{dest.name}.lock` via
`config.self_ignoring_dir`, the pattern the trunk save and the catalog writers already use) before
the staging swap. `write_tree_box` is the one function both `write_stash` and `write_prefab` funnel
through and already has `dest` in scope. Regression test with two writers.

Caveat (double-check): a flock only serialises the two full-snapshot replacements so the last wins
CLEANLY (and closes the torn `rmtree`→`os.replace` window). It does NOT give the trunk's stronger
guarantee — the trunk composes disjoint concurrent edits via a per-actor content-diff/delta write
(`cli/level_sources.py:96-113`), whereas `write_tree_box` always rewrites the whole box. True
compose-parity would need a delta write here too; file separately if wanted.

Double-checked (self + Sonnet): bug CONFIRMED (no lock in `write_tree_box`, `write_stash`,
`write_prefab`, or either `*LevelSource.save`); fix safe and correctly scoped.
