+++
priority = "p1"
kind = "debug"
summary = "Fixed: the changes-available banner is derived from trunk CONTENT (a digest of the per-actor stamps) instead of an in-memory event counter, per owner ruling 2026-10-03 (Option B)"
+++

# changes-available banner dies after a serve restart

Done. Owner-reported: "I feel like I'm not getting the yellow notification when the level changes
more and more these days."

Root cause: `/status` answered `ctx.generation[0] > session.last_seen_generation`, comparing two
counters with different lifetimes. `generation` lived in memory and restarted at 0 with the process;
`last_seen_generation` was persisted per session and only ever climbed. A session reused across a
`serve` restart therefore saw no banner until the counter caught back up with its own Load history —
and because the mark only grew, the blackout got LONGER the more the session was used, which is the
"more and more". Reproduced deterministically: after a restart the banner stayed down through 9 real
trunk changes. Sessions are deliberately persistent, so reuse across restarts is the designed
workflow, not an edge case.

The watcher was never at fault, and neither were added actors (the owner's first guess): probed
against the real `write_actor_tree` path for modify, ADD (a brand-new `actors/<name>/` dir),
modify-the-just-added, remove and add-then-modify, all six fired exactly once, on both a fast
filesystem and the slow bind mount. The push also worked; it just triggers a `/status` refetch
(`web/src/App.tsx`), and `/status` was the thing answering wrong.

Owner ruling 2026-10-03, Option B — derive it from content. `t3dtree.stamp_digest` hashes the
per-actor `ActorStamp` map `read_actor_tree_delta` already produces; `/status` compares the disk
against what the session has been shown. That asks the disk instead of trusting an event to have
been counted, so it is also right for a change that lands while `serve` is down and for a level
whose watcher started late — neither of which a counter can see. `_DIGEST_TTL_S` (1.0s against the
client's 3s poll) shares one read across every open window and is what makes the signal
self-healing: a missed watcher event now delays the banner, it cannot suppress it. Measured ~0.08s
warm / 0.67s cold per read at 2745 actors, 0.003s to hash.

Code review found four real defects in the first cut, all reproduced and all fixed here:

- The Load digest was a permanent strict SUBSET of the disk digest whenever an actor dir stats but
  does not read (an empty `actor.t3d`, or a directory where the body file belongs):
  `read_actor_tree_delta` pruned such names from its stamps map while `/status` hashed the raw
  stats. The banner then stuck ON forever and no Load could clear it. `TrunkRead.stamps` is now
  exactly `stamp_actor_tree`'s output, with the reuse branch guarded on
  `name in previous.level.actors` instead.
- The digest was recorded only by `/load`, but every window renders the level-shared trunk slot,
  which also advances under `_get_trunk`'s automatic initial Load — so after a restart the first
  `/scene` handed the user the new content with the banner still up. `/scene` now records the trunk
  it actually served, `is`-matched against that response.
- `session_load` published `trunk_cache_ref` under `ctx.trunk_lock` but `trunk_ref` after releasing
  it, so two interleaved Loads could leave B's cache paired with A's trunk permanently, at which
  point the `is`-match above stopped recording for good. All five cells now publish under one hold,
  as `_get_trunk` already did.
- `/scene`'s record was a disk write on a GET, which would recreate the `index.json` of a session
  deleted mid-request and clobber a concurrent rename. It is per-process state now; only `/load`
  persists, which is all that has to survive a restart.

Each fix is pinned by a test that fails when the fix is reverted (`test_serve_changes_available.py`,
plus the stamps-vs-actors invariant in `test_t3dtree_delta.py`/`test_serve_trunk_load.py`).
Two further findings were out of scope and filed instead: `a-corrupt-actor-t3d-makes-load-return-an`
and `scene-and-atlas-are-fetched-in-parallel-over-a`.
