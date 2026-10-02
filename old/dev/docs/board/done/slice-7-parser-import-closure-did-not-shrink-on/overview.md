+++
priority = "p3"
kind = "chore"
summary = "Slice 7: parser import-closure fixture unchanged by the editor-import removal"
+++

# Slice 7: parser import-closure did not shrink on editor-import removal

The plan (slice 7, step 1) expected removing the unused module-scope `editor` import from
`cli/dispatch.py` to shrink the parser import-closure fixture. It didn't:
`parser_baseline.compute_import_closure()` measures `build_parser()`'s closure, which only imports
`cli.dispatch` lazily inside `main()` and excludes `uedcli.cli*`, so `dispatch`'s module-scope imports
were never in that closure. The removal is still valid cleanup; no fixture change was committed because
none occurred. Recorded so the plan's wording isn't mistaken for a missed step.
