+++
priority = "p2"
kind = "finding"
summary = "offline suite has 10 undocumented pre-existing failures beyond the known 2"
+++

# offline suite has 10 undocumented pre-existing failures beyond the known 2

Found running Task 9's final full-suite pass for the `unify-ue1-package-read-primitives-into-one-rust`
item. Docs (`dev/docs/rules/tests.md`, `NATIVE-MATERIALIZE.md`, `USCRIPT-COMPILER.md`) name exactly
two pre-existing reds as safe to ignore: `test_doc_links.py::test_markdown_links_resolve`/
`test_markdown_anchors_resolve`, and `test_native_roundtrip.py::test_native_lit_room_ships_light_export_refs`.

A full `bin/test` run (no `-k`) surfaces 10 more, unrelated to package-read-core and confirmed
pre-existing by running the same tests against this branch's merge-base commit (`f35fe372`, before
any of this item's work) in a separate worktree — same failures, same messages, there too:

- `test_board.py::test_item_shape`, `::test_frontmatter`, `::test_question_files_are_well_formed`
- `test_cli.py::test_parser_poly_scale_and_rotate_report_a_missing_by_identically`
- `test_config.py::test_walk_up_hard_errors_on_an_unstatable_marker_instead_of_climbing_past`
- `test_dispatch.py::test_git_hint_reports_not_a_repo_outside_git`
- `test_env_level_and_echo.py::test_preview_tree_with_map_is_rejected`
- `test_ingest_validation.py::test_texture_exists_qualified_and_missing`
- `test_ordering_baseline.py::test_preview_validates_flags_before_resolving_the_project`
- `test_preview_wire.py::test_faces_rejected_under_game`

Likely explanation: this project's own testing convention (`dev/docs/rules/tests.md`) is to run only
the tests relevant to the current change, never the whole suite — several projects' docs say so
explicitly. Nobody may have run the complete `bin/test` in a while, so unrelated drift across
several campaigns' CLI/config/board work accumulated unnoticed.

Not fixed here — out of scope for the package-read-core item, and each looks like a different
owner's area (CLI parser messages, project-config walk-up, board frontmatter, `--faces`/`--native`
preview wiring, texture-ingest validation). Whoever owns each area should triage and either fix or
add to the documented pre-existing-red list.
