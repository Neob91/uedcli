+++
priority = "p?"
kind = "unknown"
summary = "`event graph`"
+++

# `event graph`

— BUILT 2026-07-18 (unattended build #4, to-build item 10). New `event graph
[--dot|--json]` verb + pure `eventgraph.py` module (`build_graph`/`lint_graph` + text/DOT/JSON
formatters): scans the selected level's trunk for the Tag↔Event trigger wiring (edge A→B when
`A.Event == B.Tag`) and lints dangling wires / unreachable receivers / unreachable movers /
cycles (Tarjan SCC → a real cycle path). Model-side, no editor; wiring→stdout, lint→stderr,
`--json` folds lint in; exit 0 even with findings (query verb). Load-bearing choices in
`direction/conventions.md` (2026-07-18 20:54 UTC): unset `Tag` NOT a matchable receiver; lint advisory. Tests
`test_eventgraph.py` (31, green); docs in usage.md + architecture.md. **Remnants (inbox):**
multi-event array props (Dispatcher `OutEvents`/Counter) not modelled; no `--strict` exit; tagless
movers not lint-flagged. NOTE: the cli.py+dispatch.py hunks were swept into concurrent commit
`cd364b6ac`; the module+tests+docs committed separately.
