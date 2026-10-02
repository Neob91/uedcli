# `--from-group`: flag on `actor folder set`, or its own sub-verb? And keep the `--under PREFIX` nesting?

## Context

Two coupled surface calls.

**Home.**
- **`actor folder set --from-group` (recommended).** `--from-group` replaces `--to` (mutually
  exclusive; one required). Reuses `folder set`'s names/`-`/producer machinery; a migration is "set a
  folder, but derive it per-actor." Cost: `set` grows a second value-source mode.
- **A distinct sub-verb** (`actor folder from-group` / `actor folder migrate`). Cleaner separation,
  but duplicates the names/`-`/echo plumbing and adds a verb for a one-shot migration.

**Nesting.** The overview's motivating example files groups under a parent (`act2.cellblock`), so an
optional `--under PREFIX` (folder = `PREFIX.<group>`) covers it. Without it the recipe can only
produce top-level folders named exactly by the group. Recommend keeping `--under` — it is the whole
reason the example wasn't just `folder = group`.

Recommendation: `--from-group` on `folder set`, with an optional `--under PREFIX`.

## Answer

<!-- Empty = open. -->
