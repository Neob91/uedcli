+++
priority = "p2"
kind = "chore"
summary = "Document the day-to-day git-trunk dev workflow (doc only)"
+++

# Document the day-to-day git-trunk dev workflow (doc only)

Write a
short how-to for the CURRENT (post-session-store) loop: work on a git feature branch → edit the
T3D trunk model-side (`actor …`/`brush …`/`poly …`) → `level photo` to eyeball → `level
materialize --out <map>` to build the artifact → `git commit`/`git merge` into trunk (git is the
history + merge engine; per-actor `.t3d` files merge natively). Half of this is already decided
(`direction/trunk-and-editor.md`: the trunk is a git-committed T3D tree, map files demoted to build artifacts); the
gap is that the loop isn't written down. Doc only. *(Reframed 2026-07-18 from the old
`session start`/`apply --check`/`apply --to-t3d-tree` phrasing — sessions + the `apply` verb were
removed by the git-native migration, `direction/trunk-and-editor.md`, 2026-07-05 14:58.)* From Andrzej (was
to-resolve #1) / dump.md Part B2; originally 2026-06-25.
