# `event graph` — why the wiring analysis models Tags this way

`uedcli/eventgraph.py` builds the Tag↔Event trigger graph of a level: a directed edge `A → B` when
`A.Event == B.Tag`. It is pure, offline, model-side — string scanning over the parsed `Level`, no
editor.

## An unset `Tag` is not a matchable receiver

**Why it is this way:** `build_graph` indexes receivers only by an explicitly-set, non-empty `Tag`.
UnrealEngine defaults an unset `Tag` to the actor's class name at runtime, so honoring that default
would make every same-class actor a receiver of its own class name — and any unrelated `Event` that
happened to fire a string equal to a class name would wire itself to all of them. That floods the
graph with edges that are almost never the author's intent. The cost is that a mapper who
intentionally leaves `Tag` unset and fires the class name sees no edge; that pattern is rare, and the
explicit-`Tag` form is the norm.

**Rejected:**

- *Honor the class-name default* — wires every Trigger with no explicit Tag whenever an event name
  equals a class name; floods the graph with spurious edges.
- *Exit non-zero on lint findings* (like `level doctor`'s error gate) — `event graph` is primarily a
  wiring producer whose stdout feeds other tooling, so a non-zero exit would break an
  `event graph | …` pipe on a level that merely has an unfinished wire. Lint is advisory (stderr /
  `--json`); real errors still exit 2. This is the general producer-exits-0 rule in
  [`../direction/conventions.md`](../direction/conventions.md).

**Refs:** `uedcli/eventgraph.py` (`build_graph`, `lint_graph`) · `uedcli/tests/test_eventgraph.py`
(`test_unset_tag_is_not_a_matchable_receiver`, `test_empty_tag_value_is_absent`)
