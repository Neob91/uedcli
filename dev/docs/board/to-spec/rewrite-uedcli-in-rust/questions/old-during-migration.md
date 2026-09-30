# Is `old/` frozen for the whole migration, or patchable?

`old/` is meant to serve two roles during the migration: the subprocess-strangler fallback for
unported verbs, and (per `questions/testing-strategy.md`, if differential testing is adopted) the
correctness oracle each newly-ported verb gets checked against.

Not yet decided: if a real bug is found in `old/`'s behavior during the migration (not a
misunderstanding, an actual bug), does it get patched there, or does `old/` stay byte-for-byte
frozen from the moment of the PR #0 move?

Matters concretely: a frozen `old/` is a stable, trustworthy oracle but ships known bugs to users
via the strangler fallback for as long as that verb is unported. A patchable `old/` fixes those bugs
sooner but means the oracle's behavior can drift mid-migration, and patches to `old/` would need
their own review discipline (unclear if the "every PR to the new tree is reviewed" rule was meant to
extend to `old/` too, or only ever applies to the new tree).

## Answer

