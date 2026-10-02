+++
priority = "p2"
kind = "debug"
summary = "`actor preview` with NO target set silently no-ops (exit 0, renders nothing) — should ERROR"
+++

# `actor preview` with NO target set silently no-ops (exit 0, renders nothing) — should ERROR

Fixed: `actor preview` with no names, no `-`, and no `--from-t3d` now exits 2 with
`actor preview: no actors to render — pass names or - (a piped set)`. The empty-`-`-stdin no-op stays
exit 0. `docs/usage.md` updated; regression tests `test_no_target_set_at_all_is_a_clean_error`,
`test_from_t3d_does_not_require_names`, and the existing `test_empty_stdin_is_a_clean_no_op` in
`test_actor_preview.py`.
