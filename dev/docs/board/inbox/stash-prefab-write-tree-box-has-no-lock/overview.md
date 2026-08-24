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

Fix: take the same per-box `flock` the trunk path uses before the staging swap. Regression test with
two writers.

Confirmed by direct read (flock present in trunk save, absent here).
