+++
priority = "p1"
kind = "docs"
summary = "usage.md is a single 2001-line topic key with no section addressing"
+++

# usage.md is a single 2001-line topic key with no section addressing

`docs/usage.md` is 2001 lines, 49 H1 + 26 H2 headings (82 total), all under ONE topic key (`usage`).
Only 10 intra-file anchor links (`](#...)`) exist across those 82 headings, and there is no table of
contents. `docs show` has no section selector, so reading any part of it means fetching the whole
~35k-token file.

Compounding it:

- `## Actors` appears twice as separate H2 sections (`docs/usage.md:141` and `docs/usage.md:451`) —
  same anchor, a collision.
- The file's own `# Query verbs` (`:139`) / `# Mutating verbs` (`:446`) top-level split silently
  stops applying partway through: `# Movers` (`:954`), `# actor preview` (`:1127`), `# stash /
  prefab` (`:1326`) and later H1s are siblings of those two, not children of either.

NOTE: a rewrite — splitting `usage.md` by verb family into separate topic-keyed pages — is being
actively brainstormed/spec'd by the owner today. Don't duplicate this as new work in a future
session; check for that design (`dev/docs/superpowers/specs/` or a board item) before re-filing.
