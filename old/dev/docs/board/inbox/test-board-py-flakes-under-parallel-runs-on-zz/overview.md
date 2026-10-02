+++
priority = "p3"
kind = "debug"
summary = "test_board.py's failure set shifts under parallel bin/test runs, though the count stays 18"
+++

# test_board.py flakes under parallel runs on the zz-malformed-probe fixture race

Found during the final whole-branch review's fix-round re-review for `actor-survey-and-relation`.

`test_board_script.py::test_a_malformed_item_is_skipped_not_fatal` writes directly into the real
`dev/docs/board/inbox/zz-malformed-probe/overview.md` and cleans it up in a `finally`. Under a
parallel `bin/test` run, other sessions/workers reading the live board tree (`test_board.py
::test_dependencies_resolve`, `::test_no_dependency_cycles`) can observe that file mid-write or
mid-cleanup, and fail on it instead of on their own usual baseline members.

Reproduced twice: both runs show 18 failures total (matching the documented pre-existing baseline
count), but the SET differs — `test_dependencies_resolve`/`test_no_dependency_cycles` fail instead of
`test_config.py::test_walk_up_hard_errors_on_an_unstatable_marker_instead_of_climbing_past` and
`test_dispatch.py::test_git_hint_reports_not_a_repo_outside_git`, which pass instead of their usual
fail. Running `test_board.py` alone (serial, no `-n`) reproduces the documented baseline exactly, with
no race — this only shows up in a full parallel run.

Likely needs `test_board_script.py`'s malformed-item fixture to write under `tmp_path` instead of the
real board tree, or a stronger `xdist_group` pin that also covers whatever reads `inbox/` during the
window. Not investigated further — found while re-verifying a different branch's merge readiness, not
this item's own scope.
