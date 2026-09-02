+++
priority = "p3"
kind = "chore"
summary = "Slice 7: parser import-closure fixture unchanged by the editor-import removal"
+++

# Slice 7: parser import-closure did not shrink on editor-import removal

The plan (slice 7, step 1) says removing the unused module-scope `editor` import from
`cli/dispatch.py` shrinks the parser import-closure fixture. It does not.

`parser_baseline.compute_import_closure()` measures the closure of `build_parser()`, which imports
`cli.dispatch` only lazily inside `main()`, and the fixture explicitly excludes `uedcli.cli*`. So
`dispatch`'s module-scope imports (including `editor`) were never part of that closure. Regenerating
the fixture after the removal produced no diff.

The import removal is still a valid cleanup (the names were unused). No fixture change was committed
because none occurred. Not blocking; recorded so the plan's wording is not mistaken for a missed
step.
