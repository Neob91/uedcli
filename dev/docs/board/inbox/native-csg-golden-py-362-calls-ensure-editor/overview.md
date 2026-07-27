+++
priority = "p3"
kind = "chore"
summary = "`native/csg_golden.py:362` calls `ensure_editor(editor_id)` with no `state_dir`"
+++

# `native/csg_golden.py:362` calls `ensure_editor(editor_id)` with no `state_dir`

p3` **`native/csg_golden.py:362` calls `ensure_editor(editor_id)` with no `state_dir`** (now a
required kw-only arg → `TypeError`), and its `try/finally stop_editor` starts after the call, leaking
the wineprefix volume on an `EditorNotReadyError` give-up. Harness-only (native golden-capture spike),
pre-existing — clean up when next touching that harness.
