+++
priority = "p2"
kind = "debug"
summary = "The SAME silent half-answer that 9.1 deleted from` `class show` `still lives in` `ClassIndex.ancestry`"
+++

# The SAME silent half-answer that 9.1 deleted from` `class show` `still lives in` `ClassIndex.ancestry`

The SAME silent half-answer that 9.1 deleted from` `class show` `still lives in`
`ClassIndex.ancestry`. `classindex.py:~168` catches a `SchemaError` from the super walk, prints a
"super chain of X truncated" note to stderr and returns the TRUNCATED chain — never raises. After
the 9.1 fix `class show` is safe only because its property walk errors out first; every OTHER
consumer of that chain still gets a silently wrong answer when an ancestor package is missing:
`descends_from` → `is_placeable` → `class list`/`--subclass-of` (a class simply stops being an
`Engine.Actor` descendant and vanishes from the listing), `_distance_below`, and bare-name ingest
qualification. Same decision applies (`direction.md` "No silent half-answers", 2026-07-24 21:58) —
but the fix is NOT mechanical: `class list` deliberately tolerates one unparseable `.u` without
aborting the whole listing, so the call is where to draw the line between "skip a broken package"
and "refuse to answer". Surfaced by the #9 build-review gate (2026-07-25).
