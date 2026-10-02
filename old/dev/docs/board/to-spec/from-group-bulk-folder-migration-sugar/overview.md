+++
priority = "p3"
kind = "implement"
summary = "`--from-group` bulk folder-migration sugar"
+++

# `--from-group` bulk folder-migration sugar

p3. Deferred from actor-folders v1.
Existing `Group=`-organized levels start with EMPTY folders (independence — Group is never
auto-absorbed). Today's opt-in recipe is `actor find --group cellblock | actor folder set --to
act2.cellblock -`; a one-shot `--from-group` sugar could fold a whole level's flat groups into
folders in one call. Andrzej, 2026-07-18.
