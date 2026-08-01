# Drop `level doctor --category` comma-split, or keep it as a back-compat alias?

## Context

Reconciling `level doctor --category` to the `class show --category` shape switches it from a
comma-split single string to a repeatable `action="append"` flag. The overview suggested "keep
accepting comma-lists for back-compat if cheap." But `direction/conventions.md` ("No back-compat
cruft — uedcli is unreleased") says a replaced spelling is deleted outright, no alias.

- **Drop it (recommended).** `--category A --category B` is the only spelling; `--category A,B`
  fails validation naming the token `'A,B'`. Matches `class show`, matches conventions, no
  dual-format code. Cost: any existing personal script/muscle-memory using commas breaks — but
  there are no external users.
- **Keep comma-split too.** Accept both `--category A,B` and repeated flags. Cost: exactly the
  dual-format support the convention forbids, and a category name can never contain a comma anyway.

## Answer

<!-- Empty = open. -->
