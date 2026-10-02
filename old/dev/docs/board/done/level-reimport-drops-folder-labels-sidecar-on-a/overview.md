+++
priority = "p?"
kind = "debug"
summary = "level reimport drops folder/labels sidecar on a matched actor whose body changed — FIXED"
+++

# level reimport drops folder/labels sidecar on a matched actor whose body changed — FIXED

(2026-08-29.) Found and fixed before `level reimport` merged — see
`level-reimport-reimport-a-hand-edited-dx-unr`. `_level_reimport` now copies `folder`/`labels` from
`existing_level.actors` onto `new_level.actors[n]` for every `n in diff.changed`, before the write.
Regression test: `test_a_changed_matched_actor_keeps_its_folder_and_labels`
(`uedcli/tests/test_reimport_verb.py`).
