+++
priority = "p2"
kind = "debug"
summary = "`actor preview` with NO target set silently no-ops (exit 0, renders nothing) — should ERROR"
+++

# `actor preview` with NO target set silently no-ops (exit 0, renders nothing) — should ERROR

`actor preview --focus X` (or any flags) with **no positional names and no `-`** hits
`_resolve_target_names(args.names)` → empty `raw` → `return 0` (`dispatch.py:3651-3654`) — a preview
command that produces no image and says nothing, exit 0. Violates direction.md "No silent
half-answers" (a command that can't satisfy the request must fail cleanly, exit 2, naming the problem).
Should error e.g. `actor preview: no actors to render — pass names or - (a piped set)`. **Keep the
DELIBERATE empty-`-`-stdin no-op distinct:** `actor find … | actor preview -` with empty stdin is a
clean exit-0 no-op (the composable-pipe convention) and must stay — only the *no-set-at-all* case
(no names, no `-`) should error. Cost me ~20 min of "exit 0 but no file" debugging. (Andrzej, 2026-07-25.)
