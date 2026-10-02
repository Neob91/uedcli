+++
priority = "p2"
kind = "debug"
summary = "`DistanceFromPlayer`/`LastRenderTime` look like the same engine-runtime family as the mover `Saved*` fields, but are NOT in `normalize.COMPUTED_PROPS`"
+++

# `DistanceFromPlayer`/`LastRenderTime` look like the same engine-runtime family as the mover `Saved*` fields, but are NOT in `normalize.COMPUTED_PROPS`

Measured over the git-tracked
editor exports: `DistanceFromPlayer` on 27 898 of 47 524 actors (11 546 distinct values),
`LastRenderTime` 9 038 times — both plainly per-frame engine state (how far the actor was from the
player / when it was last drawn), on every actor class, not just movers. They do NOT currently
break the post-verify, because an offline UCC `batchexport` of a freshly built map does not emit
them (nothing has rendered yet) — but a trunk INGESTED from one of those exports carries them as
if they were authored content, and they would then ride into the built map. Decide whether they
join `COMPUTED_PROPS`; get evidence first (which write path emits them) rather than adding on
faith — the standing rule that kept `SavedTrigger` out. (Surfaced by a cold review of the mover
`Saved*` fix, 2026-07-25.)
