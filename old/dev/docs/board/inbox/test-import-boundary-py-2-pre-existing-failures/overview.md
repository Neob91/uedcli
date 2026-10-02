+++
priority = "p2"
kind = "debug"
summary = "test_import_boundary.py: 2 pre-existing failures on master (serve.py cli imports, dispatch.py module-scope imports)"
+++

# test_import_boundary.py: 2 pre-existing failures on master (serve.py cli imports, dispatch.py module-scope imports)

`uedcli/tests/test_import_boundary.py` has 2 failing tests, confirmed pre-existing on `master` —
neither the failing test file nor any of the files it flags have any diff against `master` in this
session's worktree (`git diff master -- <path>` empty for all of them). Found while validating
Task 3/4 of the standalone-binary-build work — ran this file to check for regressions from an
unrelated change and got these instead.

1. `test_no_module_outside_cli_imports_a_cli_module` (rule 7: only `__main__.py` may import a `cli`
   module from outside `cli/`) — violated by `uedcli.serve.app` (imports `uedcli.cli.errors`,
   `uedcli.cli.errors.CommandError`, `uedcli.cli`, `uedcli.cli.resources`), `uedcli.serve.errors`
   (imports `uedcli.cli.errors`, `uedcli.cli.errors.CommandError`), and `uedcli.serve.levels`
   (imports `uedcli.cli.level_sources`, `uedcli.cli`).
2. `test_dispatch_module_scope_imports_only_the_error_owners` (rule 6) — `uedcli.cli.dispatch`
   imports something at module scope the rule doesn't allow (see the test's own assertion message
   for the exact offender list).

Not investigated further (out of scope for the binary-build work) — either the architecture rule
needs updating to allow `uedcli/serve/` to import from `uedcli/cli/` (if that's now intentional),
or these three `serve/` modules need to route through a non-`cli` home for `errors`/`resources`/
`level_sources`, or `cli/dispatch.py`'s module-scope imports need fixing. Run
`.venv/bin/python -m pytest uedcli/tests/test_import_boundary.py -v` to see the exact assertion
messages.
