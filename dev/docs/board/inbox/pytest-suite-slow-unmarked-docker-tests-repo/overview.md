+++
priority = "p2"
kind = "chore"
summary = "Offline `bin/test` run takes ~20min: two `uscript_*` tests run real docker+wine+UCC without an `integration` marker, and `test_board.py`/`test_doc_links.py` parametrize per-repo-file, inflating the suite to 14243 tests."
+++

# pytest suite slow: unmarked docker tests + repo-wide parametrize inflation

Timed full offline run (`UEDCLI_SKIP_NATIVE=1`, isolated cache dir): 14243 collected / 113 correctly
deselected by `-m "not integration"`, wall time **1196s (~20min)**.

## Cause 1 — heavy tests gated by a runtime `skipif`, not `@pytest.mark.integration`

Ten files use `@pytest.mark.skipif(not (_docker_up() and ...))` instead of the `integration` marker:
`test_uscript_realpkg.py:88`, `test_uscript_parser.py:413`, `test_uscript_lexer.py:168`,
`test_uscript_package.py:112`, `test_uscript_lower.py:138`, `test_uscript_reference.py:32`,
`test_uscript_ut99.py:84/95/105`, `test_uscript_conversation.py:127`, `test_uscript_dxorig.py:51`.

`_docker_up()` runs `docker info` at collection time. On any host with docker up (this sandbox
included), these tests run for real: each spins an ephemeral container (`uedcli/stub.py:382
ephemeral_build_container`) and drives `UCC.exe` under Wine (`uedcli/uscript/reference.py:42-101`,
`_WINE_TIMEOUT=180s`), ~2-3s+ each. `test_uscript_parser.py:415`
(`test_parses_decompiled_stock_packages`) even has a comment two lines above it reading
`── integration: parse the real decompiled corpus ───` but carries no `integration` marker —
plain misclassification. `-m "not integration"` does nothing for any of these.

## Cause 2 — two files parametrize over every repo file instead of looping inside one test

- `test_board.py`: **5563** tests. `_items()` walks `dev/docs/board/` (762 item dirs found here);
  `test_item_shape`, `test_frontmatter`, `test_dependencies_resolve`,
  `test_question_files_are_well_formed` each parametrize over all 762.
  `test_slug_references_resolve:266` parametrizes over `_tracked(...)` (line 105, its own
  `git ls-files -z`) — 2503 files.
- `test_doc_links.py`: **3684** tests. `test_markdown_links_resolve:164`,
  `test_markdown_anchors_resolve:177`, `test_prose_citations_into_the_new_trees_resolve:349` each
  parametrize over `_checked_docs()` (line 159, another `git ls-files -z`) — 1228 markdown files.

Together **9247 of 14243 collected tests (65%)** exist only because "check every file" was written
as one pytest item per file rather than a loop inside one test. Each instance is cheap alone but
pays full pytest per-item + the 5 autouse fixtures in `uedcli/tests/conftest.py` (each does at least
one `mkdir`+`chdir`+`monkeypatch`). The repo growing (more board items, more docs) grows the test
suite, not just the thing being checked. The three parametrize sources also call `git ls-files -z`
independently instead of sharing one result.

## Cause 3 (minor, concentrated) — `test_board_script.py` shells into the real `bin/board`

`test_ls_json_is_valid_json` (25.9s), `test_an_unclosed_frontmatter_is_malformed_not_parsed_to_eof`
(12.3s), `test_a_malformed_item_is_skipped_not_fatal` (11.9s) each invoke the real bash `bin/board`
over the actual ~762-item board tree — `bin/board`'s TOML reader is unbatched bash, O(items).

## Not investigated further (out of scope here)

`test_materialize_verb.py` has 6 tests each taking a consistent ~3.5s despite the editor/driver being
mocked (`test_the_path_pass_runs_on_both_build_paths_before_the_verify` and 5 siblings) — worth a
look at `run_materialize`'s package-search-path resolution, but not diagnosed.

## Suggested fix (not applied — filing only)

- Mark the docker-dependent `uscript_*` tests `@pytest.mark.integration` (in addition to or instead
  of the `skipif`), so `-m "not integration"` actually excludes them offline.
- Collapse `test_board.py`'s and `test_doc_links.py`'s per-file parametrize into a loop inside one
  test (assert-all, collect failures, one failure message listing every bad file) — same coverage,
  ~9000 fewer pytest items. Share one `git ls-files -z` result across the three call sites instead of
  three separate subprocess calls.
