+++
priority = "p3"
kind = "chore"
summary = "Fixed — regenerate() now resolves state_dir and tears down the editor even if ensure_editor never becomes ready"
+++

# `native/csg_golden.py:362` calls `ensure_editor(editor_id)` with no `state_dir`

Fixed in `uedcli/native/csg_golden.py:regenerate()` — resolves `state_dir` via
`config.resolve_project()`/`config.state_dir()`, threads it to both `ensure_editor` and
`stop_editor`, and moved `ensure_editor` inside the `try:` so a failed spin-up still tears down.
Same fix applied to the `ephemeral_driver` test fixture in `test_csg_golden.py` (identical bug).
