+++
priority = "p3"
kind = "docs"
summary = "brush build cube prints T3D to stdout only; two of five agents in an unrelated dogfood exercise missed the required `| actor add -` and got an empty level"
+++

# brush build cube does not auto-add to the level

`brush build cube` (and presumably the other `brush build <shape>` generators) is a pure T3D
producer — it never touches the level on its own; the caller must pipe its output into
`actor add -`. That's documented (`actor add` persists it), but it's easy to miss on a first read:
`bin/uedcli brush build cube --help` doesn't call it out, only the top-level command family
description implies the two-step pattern.

Found independently by two of five agents in an unrelated dogfood exercise for `brush measure
relation` (2026-08-30): both ran `brush build cube ...` alone, got no error, and were confused why
the level stayed empty until they noticed the missing `| actor add -`.

Possible fix: a one-line reminder in `brush build <shape> --help`'s own text (not just the family
description) — e.g. "prints T3D to stdout; pipe into `actor add -` to add it to the level."
