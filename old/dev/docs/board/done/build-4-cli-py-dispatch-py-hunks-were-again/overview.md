+++
priority = "p2"
kind = "owner-question"
summary = "build #4 cli.py+dispatch.py hunks were again swept into a concurrent agent's commit"
+++

# build #4 cli.py+dispatch.py hunks were again swept into a concurrent agent's commit

— **build #4 cli.py+dispatch.py hunks were again swept into a concurrent
agent's commit.** My `event`-group parser + `_event_graph` handler landed inside commit
`cd364b6ac` (subject "class show --all: expand the whole super chain…") — a different session's
stage-by-path picked up my uncommitted cli.py/dispatch.py edits. Same orchestration hazard already
noted for build #2: the coherent feature (module+tests+docs, committed separately by me) is bisected
across commits/authors. No code action needed — awareness only.
