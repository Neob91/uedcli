+++
priority = "p1"
kind = "owner-question"
summary = "Does class curation get a general file-fact OVERRIDE field?"
+++

# Does class curation get a general file-fact OVERRIDE field?

`direction/asset-catalog.md` says curation is "a description, plus **an override where the file fact is
wrong**" — but its own *Rejected* list kills "a curated-vs-derived override model for `placeable`". The
two cannot both hold, and the catalog spec's shard payload carries `tags`/`description`/`colors` with no
general override, so as specced a wrong file-fact cannot be corrected at all. Raised independently by
two of three gate reviewers 2026-07-26. Either the topic drops the override clause, or the spec gains a
field — an implementer must not pick. (The §4b colours override is the one existing instance and stays
either way.)
