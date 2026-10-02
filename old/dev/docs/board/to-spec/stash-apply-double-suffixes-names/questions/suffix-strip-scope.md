# Strip the double suffix only in apply, or also in `actor add -` / `actor duplicate`?

## Context

The double suffix comes from re-suffixing an already-suffixed captured name. The same code pattern
(`stem = a.name; alloc_name(stem)`) lives in three re-ingest paths: `stash`/`prefab apply`
(`placement.py:92-93`) AND `actor add -` / `actor duplicate` (`edit.py:434-436`). So
`actor show Pillar_abc123 | actor add -` double-suffixes today exactly like apply.

Options:

1. Shared `trunk.strip_alloc_suffix` helper applied at ALL stem sites — apply, add, duplicate behave
   uniformly (recommended). Slightly wider than the board item's title.
2. Apply-only — minimal, but leaves `add -`/`duplicate` still double-suffixing, a new inconsistency.

Recommendation: option 1. The strip only affects the cosmetic stem (a fresh suffix is always
appended, so identity and collision-freedom are unchanged), and one helper keeps the three paths
from drifting.

## Answer

<!-- Empty = open. -->
