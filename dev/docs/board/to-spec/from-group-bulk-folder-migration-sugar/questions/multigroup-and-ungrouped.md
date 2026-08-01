# `--from-group`: how to handle a multi-valued `Group=A,B` or an actor with no Group?

## Context

`--from-group` derives one folder path per actor from its engine `Group` value. A folder is
single-valued, so two cases have no unambiguous mapping:

- **Multi-group `Group=A,B`.** Options: (a) error naming the actor; (b) use the first group; (c) map
  to `A.B` (treat the comma list as a path). (b) and (c) both silently invent a filing the user never
  chose.
- **No `Group` at all.** Options: (a) error naming the actor; (b) skip it (leave unfoldered).

Recommendation for both: **error, exit 2, naming every offending actor** (batch all-or-nothing).
Rationale: conventions forbid silent half-answers and fallbacks — a comma group cannot be mapped to
one path, and an absent group cannot be derived, so guessing (first-group / skip) is exactly the
silently-wrong outcome the rule guards against. The user then fixes those actors explicitly (e.g.
`actor find --group A | actor folder set --to … -`) before re-running.

If the owner prefers migration to be lenient (skip ungrouped, take first of multi), say so here and
the spec flips to skip-with-stderr-note — but that trades the no-half-answer guarantee.

## Answer

<!-- Empty = open. -->
