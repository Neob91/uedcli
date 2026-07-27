+++
priority = "p3"
kind = "owner-question"
summary = "`--target` v1 — one LOW edge left (two others FIXED in post-build review)"
+++

# `--target` v1 — one LOW edge left (two others FIXED in post-build review)

p3. Of the three edges the `--target` build reviewers surfaced (2026-07-12): (a) corrupt-box
traceback and (b) emptied-stash "not found" were **FIXED** in the post-build multi-reviewer pass —
`StashLevelSource`/`PrefabLevelSource` `load` now catch a corrupt box → clean exit 2 (plus the
pre-existing `stash show`/lifecycle corrupt-`meta.json` traceback, guarded in the same pass), and
the stash existence oracle moved to a `meta.json`-keyed `FileStashRegister.exists()` so an emptied
stash stays targetable; all with regression tests. **Remaining (c):** `--target prefab/<name>`
requires a resolvable project (`_resolve_project` runs for all three kinds) even though the prefab
library root is repo-relative, not project-scoped — a minor over-constraint matching the spec's
"all three live under the project". Cheap to relax if it bites; left as-is.
