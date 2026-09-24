+++
priority = "p3"
kind = "docs"
summary = "Slice 3 cli/ move: doc-scope judgment calls"
+++

# Slice 3 cli/ move: doc-scope judgment calls

When moving `cli.py`->`cli/main.py` and `dispatch.py`->`cli/dispatch.py`, updated only full-path
`uedcli/cli.py`/`uedcli/dispatch.py` mentions (and their markdown link targets) in `dev/docs/rationale/*.md`,
per the slice brief's pre-approved scope; left bare colloquial module-name prose and other board
items'/frozen docs' old-path references untouched as out of scope. Also dropped the now-dead
`not m.startswith('uedcli.dispatch')` exclusion from `parser_baseline.py`'s import-closure snippet
(measured closure and fixture unchanged).
