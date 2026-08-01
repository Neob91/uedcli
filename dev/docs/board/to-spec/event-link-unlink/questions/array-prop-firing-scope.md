# Should v1 author only the scalar `Event`, or also Dispatcher `OutEvents(n)` / Counter array firers?

## Context

Some actors fire events through ARRAY properties, not the scalar `Event`: a Dispatcher fires each
`OutEvents(n)`, a Counter fires on threshold, etc. `event graph` reads the scalar `Event` only and
does not model these (`eventgraph.py:22-26`), and the owner already flagged multi-event coverage as
a candidate follow-up (inbox `unset-tag-treated-as-not-a-matchable-receiver`, point 3).

- (a) **v1 scalar `Event` only.** Matches the reader's scope, so `link`/`unlink` and `event graph`
  agree on what a wire is. A Dispatcher would need a separate array-aware path later. Recommended.
- (b) **Include array firers now** — e.g. `event link --to T --via OutEvents SOURCE` appends to the
  source's `OutEvents` array. Larger surface, and `event graph` still would not SHOW the resulting
  edges until the reader is extended too, so the two would disagree.

Recommendation: (a); file a follow-up to extend both reader and authors to array firers together, so
graph and link/unlink never drift.

## Answer

<!-- Empty = open. -->
