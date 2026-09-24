+++
priority = "p2"
kind = "implement"
summary = "Composable `actor find` — stdin name-set input for full boolean queries"
+++

# Composable `actor find` — stdin name-set input for full boolean queries

Shipped: `find` takes an optional trailing `-` (restrict positional) that reads a piped name-set as
the universe, with `--exclude` negating the filter predicate over it — the grep/universe model,
enabling AND/OR/NOT queries by pipe composition. `uedcli/cli/parsers/actor.py`,
`uedcli/tests/test_find_compose.py`, `docs/reference/actor/find.md`.
