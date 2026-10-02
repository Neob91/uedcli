+++
priority = "p2"
kind = "debug"
summary = "test_doc_links.py::test_markdown_anchors_resolve fails on master: dev/docs/superpowers/specs/2026-08-30-usage-md-split-design.md:243 QUOTES an example link `[Movers](#movers...)` inside prose and the test reads it as a real anchor. Pre-existing (33ba516); fix needs either the test to skip fenced/quoted links or an owner-approved spec edit."
+++

# bin/test red on master: doc-links test trips on a quoted example anchor in the usage-md-split spec

`test_markdown_anchors_resolve[dev/docs/superpowers/specs/2026-08-30-usage-md-split-design.md]`
fails: the spec's line 243 quotes `[Movers](#movers...)` as an EXAMPLE of a link being discussed,
and the checker resolves it as a genuine same-file anchor (`no heading '#movers...'`). Introduced
by `33ba516` (the diagram/photo rename catch-up), unrelated to any code change. Editing the spec
needs the owner's yes (dev/docs rule); alternatively teach the test to ignore links inside
backticked/quoted spans.
