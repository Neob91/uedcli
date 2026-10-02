+++
priority = "p2"
kind = "owner-question"
summary = "build #2 feature was split across sessions/commits by the concurrent commit-sweep"
+++

# build #2 feature was split across sessions/commits by the concurrent commit-sweep

— **build #2 feature was split across sessions/commits by the concurrent
commit-sweep.** The `actor bbox`/`--json`/`--rotate` *dispatch.py* handlers landed in commit
`fa08513a4` (message "schema cache: surface unwritable-cache write failure…") — a DIFFERENT
session's sweep picked up my uncommitted dispatch.py hunks under an unrelated subject — while the
matching *cli.py* parser wiring stayed uncommitted, so HEAD briefly carried DEAD dispatch handlers
with no CLI entry point. The coherent feature (cli+dispatch+tests+docs) was finally committed whole
in `7e823a708`. Flagging the sweep behaviour: it can bisect a single feature across commits/authors
and mislabel it. (Andrzej: no action needed on the code — just awareness of the orchestration.)
