+++
priority = "p3"
kind = "chore"
summary = "bin/board shells out unbatched over ~762 items (25.9s/12.3s/11.9s in test_board_script.py); test_materialize_verb has 6 tests each ~3.5s despite mocking"
+++

# bin/board shells out unbatched over ~762 items; test_materialize_verb 3.5s mystery

Split out of `pytest-suite-slow-unmarked-docker-tests-repo` (now in `done/`) — these two findings
were noted there but not part of the applied fix (no suggested fix / not diagnosed).

## `bin/board`'s hand-rolled bash TOML reader is O(items), unbatched

`uedcli/tests/test_board_script.py::test_ls_json_is_valid_json` (25.9s),
`test_an_unclosed_frontmatter_is_malformed_not_parsed_to_eof` (12.3s),
`test_a_malformed_item_is_skipped_not_fatal` (11.9s) each invoke the real `bin/board` (bash, no venv)
over the actual ~762-item board tree. Would need a `bin/board` algorithm change, not a test change.

## `test_materialize_verb.py` — 6 tests, consistent ~3.5s each, editor/driver mocked

`test_the_path_pass_runs_on_both_build_paths_before_the_verify` and 5 siblings each take ~3.5s
despite the editor/driver being mocked — not diagnosed. Worth a look at `run_materialize`'s
package-search-path resolution.
