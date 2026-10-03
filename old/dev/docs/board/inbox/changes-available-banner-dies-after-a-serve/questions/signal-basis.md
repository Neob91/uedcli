# Should the changes-available signal stay a counter, or become content-derived?

## Context
The yellow "trunk changed -- Reload to see it" banner is driven entirely by `/status`'s
`changes_available`, which answers `ctx.generation[0] > session.last_seen_generation` -- an
in-memory per-level counter against a per-session mark persisted in `sessions/<sid>/index.json`.
The counter restarts at 0 with the `serve` process; the mark does not, so a session reused across a
restart sees no banner until the counter climbs back past its own high-water mark, and the blackout
grows the longer that session is used. Reproduced deterministically; full trace in `overview.md`.
The watcher itself is fine (all six change kinds, added actors included, fire exactly once).

## Options
**Option A — seed the counter at startup.** On `LevelContext` creation, initialise
`generation[0]` to the max `last_seen_generation` across that level's existing sessions instead of
0. Minimal, no on-disk format change, no new per-poll cost. Does NOT fix a change that lands while
`serve` is down or before the watcher starts — that still fires no settle event and so still never
shows a banner.

**Option B — derive it from trunk content.** Drop the counter; record what each session actually
Loaded (the `ActorStamp` map `read_actor_tree_delta` already produces and `TrunkCache` already
holds) and answer `changes_available` by diffing the current stamps against it. Correct by
construction across restarts, offline edits and a late-started watcher alike, since it asks the disk
rather than trusting an event to have been counted. Costs a stamp pass per `/status` — measured
~0.6s cold at 2745 actors, much less warm, against a 3s poll interval, so it needs either a short
server-side throttle or the poll moved onto the push.

**Option C — both.** B as the answer, A's seeding kept so the counter stays meaningful for the WS
push's own bookkeeping.

## Answer
