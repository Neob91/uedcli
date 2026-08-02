+++
priority = "p3"
kind = "docs"
summary = "Slice 3 cli/ move: doc-scope judgment calls"
+++

# Slice 3 cli/ move: doc-scope judgment calls

When moving `cli.py`->`cli/main.py` and `dispatch.py`->`cli/dispatch.py`, the slice brief
pre-approved updating "any `uedcli/cli.py`/`uedcli/dispatch.py` path mentions in
`dev/docs/rationale/*.md`" and the broken markdown link in `rationale/surface.md`. Calls made:

- Updated only full-path `uedcli/cli.py`/`uedcli/dispatch.py` mentions (and the `../../../uedcli/...`
  link targets) in rationale docs. Left bare colloquial module-name prose ("`dispatch.py` already
  carries...", "in `dispatch.py`...") in `driver.md`/`userdocs.md`/`reported-coordinates.md`
  unchanged — those name the module conceptually, and rewriting them exceeds the approved scope.
- Updated `rationale/MIGRATION.md` line 74's `uedcli/cli.py` -> `uedcli/cli/main.py`. It is a
  historical migration ledger, but the entry is a plain file-path token and the brief's pre-approval
  covers "any path mentions in rationale/*.md". Flagging in case the owner would rather it stay as
  the historical name.
- Left old-path references in OTHER board items' plans/specs and in frozen docs
  (the decisions ledger, `reviews/*`) untouched (out of scope). The stale-reference sweep over
  production/tests/scripts is clean.
- `parser_baseline.py` import-closure snippet: dropped the now-dead
  `not m.startswith('uedcli.dispatch')` exclusion (the boundary is entirely under `uedcli.cli` now).
  The measured service closure is unchanged and its fixture still matches.
