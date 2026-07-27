+++
priority = "p3"
kind = "debug"
summary = "Re-evaluate whether `_reject_nonlevel_target_for_folders` is STALE post-unify (2026-07-22)"
+++

# Re-evaluate whether `_reject_nonlevel_target_for_folders` is STALE post-unify (2026-07-22)

Folder verbs reject a `--tree stash|prefab` target (`dispatch.py:1707,3011-3021`), a guard from before
the unify-T3D-trees change gave stash/prefab real per-actor sidecar slots (folders now persist there —
`stashlib.py:101-109`). The actor-labels spec proposes labels ARE allowed on `--tree stash|prefab` (the
sidecar exists); if that's right, the folder guard is inconsistent and probably stale. Decide: drop the
folder guard too, or keep both trunk-only. Ref: `specs/2026-07-22-actor-labels.md` §11.4.
