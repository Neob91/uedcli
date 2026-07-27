+++
priority = "p2"
kind = "debug"
summary = "`architecture.md` contradicts `direction/conventions.md` on half-answers"
+++

# `architecture.md` contradicts `direction/conventions.md` on half-answers

`architecture.md` says `ClassIndex` skips a single unparseable `.u` "with a stderr note (never
aborts)" — the exact warn-and-continue shape `conventions.md` "No silent half-answers, and no
fallbacks" forbids. Either the doc is stale or the code needs a ruling; `inbox.md:2939` already
notes the fix is not mechanical. Decide which side moves. *(packages drafter, 2026-07-26.)*
