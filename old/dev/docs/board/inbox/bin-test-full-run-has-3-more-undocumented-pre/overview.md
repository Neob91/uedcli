+++
priority = "p3"
kind = "debug"
summary = "bin/test full run has 3 more undocumented pre-existing failures beyond the known ones"
+++

# bin/test full run has 3 more undocumented pre-existing failures beyond the known ones

Found running `bin/test` (Step 6 of the `actor-survey-and-relation` Task 20 doc work, which touches
only files under `docs/`) as a sanity check. `18 failed, 6038 passed`. 15 of the 18 are already
documented pre-existing drift: the "known 2" (`test_doc_links.py::test_markdown_links_resolve`/
`test_markdown_anchors_resolve`) plus `test_native_roundtrip.py::test_native_lit_room_ships_light_export_refs`
(named together in `dev/docs/rules/tests.md`/`NATIVE-MATERIALIZE.md`), the 10 in board item
`offline-suite-has-10-undocumented-pre-existing`, and the 2 in
`test-import-boundary-py-2-pre-existing-failures`.

3 are not yet recorded anywhere:

- `test_command_isolation.py::test_low_dependency_family_loads_no_heavy_stack[docs]`
- `test_command_isolation.py::test_low_dependency_family_loads_no_heavy_stack[cache]`
- `test_board.py::test_slugs_are_unique_board_wide`

Confirmed unrelated to Task 20: `git diff 874f978c` (this item's own base commit) touches only
`docs/reference/actor/{README.md,relation.md,survey.md}`, `docs/reference/brush/{README.md,poly.md}`,
`docs/reference/level/graph.md` — none of the three failing tests, or any module/board content they
name, appear in that diff. Reran the full suite twice; identical 18-failure set both times (not a
parallel-run race).

Not investigated further — out of scope for a docs-only task. Whoever owns command isolation /
board-slug uniqueness should triage and either fix or fold into the existing pre-existing-red lists
above.
