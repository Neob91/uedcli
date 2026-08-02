+++
priority = "p2"
kind = "debug"
summary = "master red: a stale/ item breaks test_ls_json_on_an_empty_stage, which asserts stale/ is empty by owner decision."
+++

# master red: stale/ item vs the empty-stage board test

`test_board_script::test_ls_json_on_an_empty_stage_is_an_empty_array` runs `bin/board ls stale --json`
and asserts `[]`, on the premise "stale/ is empty by owner decision". The 2026-08-02 board sweep
(commit `d9a1543`) moved `native-full-parity-handoff` into `stale/`, so the query now returns one item
and the test fails.

Not from the to-build run — present at `d9a1543`, before any feature merge. The test encodes an owner
decision, so reconciling it is the owner's call, not an agent edit: either the sweep should not have
populated `stale/`, or the test should target a different empty stage (e.g. `to-spike/` if it drains)
or drop the "stale is empty" premise. Left unfixed pending that call.
