+++
priority = "p2"
kind = "debug"
summary = "`brush vertex move` reaches the user as a bare Python traceback"
+++

# `brush vertex move` reaches the user as a bare Python traceback

Fixed: `_move` now catches the `ValueError` from `move_vertices` (selector matching no corner, etc.)
and re-raises `CommandError` → clean exit 2, no traceback. Regression test
`test_cli_move_no_matching_corner_is_clean_exit2` in `test_vertex.py`.
