# Does a class shard get a general file-fact OVERRIDE field? (owner contradiction to resolve)

## Context

Spec §8.4, marked **[CARRIED — do not resolve]**; tracked in board item
`does-class-curation-get-a-general-file-fact`. Raised independently by two of three gate reviewers
(2026-07-26). Recorded here because it blocks this item's shard payload shape (§5).

The contradiction is inside `direction/asset-catalog.md` itself:

- it says class curation is "a description, plus **an override where the file fact is wrong**"; but
- its *Rejected* list kills "a curated-vs-derived override model for `placeable`".

This arm's shard payload is `{kind, ref, tags, description}` — **no** general override field — so as
specced a wrong file fact cannot be corrected. Either the direction topic drops the override clause, or
the shard gains a field. Only the owner can resolve a contradiction inside their own direction doc.

**Recommendation:** defer to the owner — do not add a field on our own read. Fold the answer into
`direction/asset-catalog.md` and board item `does-class-curation-get-a-general-file-fact`, not here.
(The texture-colours override is the one existing instance and stays either way.)

## Answer

<!-- Empty = open. -->
